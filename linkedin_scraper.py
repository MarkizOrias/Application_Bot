#!/usr/bin/env python3
"""
LinkedIn Job Scraper - Phase 1 of Application Bot
Automatically kills any running Chrome, launches a fresh instance with remote
debugging on port 9222, attaches via CDP, and saves job listings to Excel.

Usage:
    python linkedin_scraper.py

The script handles Chrome startup automatically. Log in to LinkedIn if prompted.
"""

import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

CONFIG_PATH = Path("config/profile.json")
OUTPUT_DIR = Path("output")

# LinkedIn brand blue for header styling
LI_BLUE = "0A66C2"


CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_USER_DATA = r"C:\Temp\chrome-debug"
CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"


# ---------------------------------------------------------------------------
# Chrome lifecycle
# ---------------------------------------------------------------------------

def launch_chrome() -> None:
    """Kill all Chrome processes, then start a fresh instance with CDP enabled."""
    print("Killing existing Chrome processes...")
    subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
    time.sleep(1.5)

    print("Launching Chrome with remote debugging...")
    subprocess.Popen([
        CHROME_EXE,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={CHROME_USER_DATA}",
        "--start-maximized",
    ])
    # Give Chrome time to start and open the debug port
    time.sleep(3)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_profile() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------

def build_search_url(role: str, easy_apply: bool) -> str:
    """Build a LinkedIn jobs search URL for a given role."""
    from urllib.parse import urlencode
    params = {
        "keywords": role,
        "f_WT": "2",        # Remote only
        "sortBy": "DD",     # Most recent first
    }
    if easy_apply:
        params["f_AL"] = "true"
    return "https://www.linkedin.com/jobs/search/?" + urlencode(params)


# ---------------------------------------------------------------------------
# Scraping helpers
# ---------------------------------------------------------------------------

def scroll_to_load(page, rounds: int = 4) -> None:
    """Scroll the results panel to trigger lazy-loading of job cards."""
    for _ in range(rounds):
        page.keyboard.press("End")
        time.sleep(1.2)


def extract_card(card) -> dict | None:
    """Extract fields from a single job-card element. Returns None on failure."""

    # Title & URL  (multiple selector fallbacks)
    title_el = (
        card.query_selector("a.job-card-list__title--link")
        or card.query_selector("a.job-card-container__link")
        or card.query_selector("a[data-control-name='jobcard_title']")
        or card.query_selector("strong.job-card-search__title")
    )

    company_el = (
        card.query_selector(".job-card-container__company-name")
        or card.query_selector(".artdeco-entity-lockup__subtitle span")
        or card.query_selector("[data-tracking-control-name*='company']")
    )

    location_el = (
        card.query_selector(".job-card-container__metadata-item")
        or card.query_selector(".artdeco-entity-lockup__caption li")
        or card.query_selector(".job-card-container__metadata-wrapper li")
    )

    title = title_el.inner_text().strip() if title_el else None
    if not title:
        return None

    company = company_el.inner_text().strip() if company_el else ""
    location = location_el.inner_text().strip() if location_el else ""

    href = title_el.get_attribute("href") if title_el else ""
    if href and not href.startswith("http"):
        href = "https://www.linkedin.com" + href

    # Normalise URL to a clean /jobs/view/<id>/ form
    match = re.search(r"/jobs/view/(\d+)", href or "")
    clean_url = f"https://www.linkedin.com/jobs/view/{match.group(1)}/" if match else href

    # Easy Apply badge present?
    easy_apply_badge = card.query_selector(".job-card-container__apply-method")
    easy_apply = bool(easy_apply_badge)

    return {
        "title": title,
        "company": company,
        "location": location,
        "url": clean_url,
        "easy_apply": easy_apply,
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "applied": False,
    }


def scrape_cards(page, max_per_search: int = 25) -> list[dict]:
    """Wait for cards, scroll to load more, then extract all visible cards."""
    jobs = []

    # Wait for the results list
    try:
        page.wait_for_selector(
            "ul.scaffold-layout__list-container li, "
            ".jobs-search__results-list li, "
            "[data-job-id]",
            timeout=18000,
        )
    except PlaywrightTimeout:
        print("    [warn] Results list timed out - page may need login or CAPTCHA")
        return jobs

    scroll_to_load(page)

    # Try each known container selector
    cards = (
        page.query_selector_all("li.jobs-search-results__list-item")
        or page.query_selector_all("ul.scaffold-layout__list-container > li")
        or page.query_selector_all(".jobs-search__results-list > li")
    )

    print(f"    Found {len(cards)} cards on page")

    for card in cards[:max_per_search]:
        try:
            job = extract_card(card)
            if job:
                jobs.append(job)
        except Exception as exc:
            print(f"    [warn] Card extraction error: {exc}")

    return jobs


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def is_excluded(job: dict, profile: dict) -> tuple[bool, str]:
    """Return (True, reason) if the job should be skipped, else (False, '')."""
    prefs = profile["preferences"]

    # Excluded companies (case-insensitive)
    blocked = {c.lower() for c in prefs.get("exclude_companies", [])}
    if job["company"].lower() in blocked:
        return True, f"excluded company '{job['company']}'"

    # Keyword exclusions checked against title
    title_lower = job["title"].lower()
    for kw in prefs.get("exclude_keywords", []):
        if kw.lower() in title_lower:
            return True, f"exclude keyword '{kw}'"

    return False, ""


# ---------------------------------------------------------------------------
# Excel output
# ---------------------------------------------------------------------------

def save_excel(jobs: list[dict], path: Path) -> None:
    """Write jobs list to a formatted Excel file."""
    df = pd.DataFrame(jobs)

    # Column order
    col_order = ["title", "company", "location", "search_role", "easy_apply",
                 "url", "applied", "scraped_at"]
    df = df[[c for c in col_order if c in df.columns]]

    df.to_excel(path, index=False, sheet_name="Listings")

    # --- Formatting with openpyxl ---
    wb = load_workbook(path)
    ws = wb.active

    # Header row styling
    header_fill = PatternFill(start_color=LI_BLUE, end_color=LI_BLUE, fill_type="solid")
    header_font = Font(name="Calibri", color="FFFFFF", bold=True, size=11)

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.row_dimensions[1].height = 20

    # Make URL column a hyperlink and style body rows
    url_col_idx = None
    for idx, cell in enumerate(ws[1], start=1):
        if str(cell.value).lower() == "url":
            url_col_idx = idx
            break

    body_font = Font(name="Calibri", size=10)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = body_font
            if url_col_idx and cell.column == url_col_idx and cell.value:
                cell.hyperlink = cell.value
                cell.font = Font(name="Calibri", size=10, color="0563C1", underline="single")
                cell.value = "Open"

    # Auto-size columns
    for col in ws.columns:
        max_len = max(
            (len(str(cell.value or "")) for cell in col),
            default=10,
        )
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = min(max_len + 4, 55)

    # Freeze header row
    ws.freeze_panes = "A2"

    wb.save(path)
    print(f"\nSaved {len(jobs)} listings -> {path.resolve()}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    profile = load_profile()
    prefs = profile["preferences"]
    li_cfg = profile["job_sources"]["linkedin"]

    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = OUTPUT_DIR / f"linkedin_listings_{timestamp}.xlsx"

    easy_apply = li_cfg.get("easy_apply_only", True)

    print("=" * 60)
    print("LinkedIn Job Scraper")
    print("=" * 60)
    print(f"Easy Apply only: {easy_apply}")
    print(f"Roles to search: {len(prefs['roles'])}")
    print(f"Output         : {output_path}")
    print("=" * 60)
    print()

    launch_chrome()

    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(CDP_URL)
        except Exception as exc:
            print(f"[!] Could not connect to Chrome: {exc}")
            return

        # Reuse the existing context (your logged-in session)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()

        # Warm-up: make sure we're logged in
        print("Opening LinkedIn...")
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        if "login" in page.url or "authwall" in page.url:
            print("\n[!] LinkedIn is asking for login.")
            print("    Please log in manually in the browser, then press Enter here to continue.")
            input("    Press Enter once logged in > ")

        # --- Search each role ---
        for role in prefs["roles"]:
            url = build_search_url(role, easy_apply)
            print(f"\nSearching: {role}")
            print(f"  URL: {url}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)

                cards = scrape_cards(page)
                new_count = 0

                for job in cards:
                    # De-duplicate by URL
                    if job["url"] in seen_urls:
                        continue

                    excluded, reason = is_excluded(job, profile)
                    if excluded:
                        print(f"  [-] Skip  : {job['title']} @ {job['company']} ({reason})")
                        continue

                    job["search_role"] = role
                    seen_urls.add(job["url"])
                    all_jobs.append(job)
                    new_count += 1
                    print(f"  [+] Added : {job['title']} @ {job['company']} | {job['location']}")

                print(f"  --> {new_count} new jobs added (total so far: {len(all_jobs)})")

            except PlaywrightTimeout:
                print(f"  [!] Timeout navigating to search for '{role}' - skipping")
            except Exception as exc:
                print(f"  [!] Error on '{role}': {exc}")

            time.sleep(1.5)  # Polite delay between searches

        context.close()

    # --- Save results ---
    if all_jobs:
        save_excel(all_jobs, output_path)
    else:
        print("\nNo jobs collected. Check selectors or LinkedIn login state.")


if __name__ == "__main__":
    main()
