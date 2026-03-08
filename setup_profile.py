#!/usr/bin/env python3
"""
setup_profile.py — Interactive profile configurator for Application Bot.

Reads config/base.md (your master CV in Markdown) and config/profile.json,
then lets you review and update every section via the terminal.
Run this once before your first scraping session, or whenever your CV changes.

Usage:
    python setup_profile.py
"""

import json
import re
import sys
from pathlib import Path

CONFIG_PATH = Path("config/profile.json")
BASE_MD_PATH = Path("config/base.md")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_json(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved -> {CONFIG_PATH.resolve()}")


def ask(prompt: str, default: str = "") -> str:
    display = f" [{default}]" if default else ""
    val = input(f"  {prompt}{display}: ").strip()
    return val if val else default


def confirm(prompt: str) -> bool:
    return input(f"  {prompt} [y/N]: ").strip().lower() == "y"


def hr(title: str = "") -> None:
    width = 60
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'─' * pad} {title} {'─' * pad}")
    else:
        print("─" * width)


# ---------------------------------------------------------------------------
# Section editors
# ---------------------------------------------------------------------------

def edit_personal(profile: dict) -> None:
    hr("Personal Details")
    p = profile["personal"]
    p["full_name"]  = ask("Full name",  p.get("full_name", ""))
    p["email"]      = ask("Email",      p.get("email", ""))
    p["phone"]      = ask("Phone",      p.get("phone", ""))
    p["linkedin"]   = ask("LinkedIn URL", p.get("linkedin", ""))
    p["github"]     = ask("GitHub URL",   p.get("github", ""))
    p["portfolio"]  = ask("Portfolio URL", p.get("portfolio", ""))
    p["location"]   = ask("Location (e.g. Basel, Switzerland (Remote))", p.get("location", ""))


def edit_work_auth(profile: dict) -> None:
    hr("Work Authorisation")
    wa = profile.setdefault("work_authorization", {})
    print("  Enter authorisation status for each region (leave blank to keep current).")
    for region in ["pl", "eu", "ch", "us"]:
        wa[region] = ask(f"  {region.upper()}", wa.get(region, ""))


def edit_preferences(profile: dict) -> None:
    hr("Job Preferences")
    prefs = profile["preferences"]

    print(f"\n  Current target roles:")
    for i, r in enumerate(prefs.get("roles", []), 1):
        print(f"    {i}. {r}")
    if confirm("  Replace roles list?"):
        print("  Enter roles one per line. Empty line to finish:")
        roles = []
        while True:
            r = input("    > ").strip()
            if not r:
                break
            roles.append(r)
        if roles:
            prefs["roles"] = roles

    sal = ask("Min salary (USD)", str(prefs.get("min_salary_usd", 70000)))
    try:
        prefs["min_salary_usd"] = int(sal)
    except ValueError:
        pass

    prefs["require_remote"] = confirm("Require remote?") if confirm("Change remote preference?") else prefs.get("require_remote", True)

    print(f"\n  Current excluded companies: {', '.join(prefs.get('exclude_companies', []))}")
    if confirm("  Replace excluded companies?"):
        print("  Enter company names one per line. Empty line to finish:")
        companies = []
        while True:
            c = input("    > ").strip()
            if not c:
                break
            companies.append(c)
        if companies:
            prefs["exclude_companies"] = companies


def edit_cv_from_base_md(profile: dict) -> None:
    hr("CV Data (parsed from config/base.md)")

    if not BASE_MD_PATH.exists():
        print(f"  [warn] {BASE_MD_PATH} not found — skipping CV import.")
        print("  Create config/base.md with your CV in Markdown and re-run.")
        return

    text = BASE_MD_PATH.read_text(encoding="utf-8")

    # ── Summary ──────────────────────────────────────────────────────────
    summary_match = re.search(r"##\s+SUMMARY\s*\n+(.*?)(?=\n##|\Z)", text, re.S)
    summary = summary_match.group(1).strip() if summary_match else ""

    # ── Skills ───────────────────────────────────────────────────────────
    skills_match = re.search(r"##\s+SKILLS\s*\n+(.*?)(?=\n##|\Z)", text, re.S)
    raw_skills = skills_match.group(1).strip() if skills_match else ""
    skill_groups: dict[str, list[str]] = {}
    for line in raw_skills.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # "**Category:** item1, item2" pattern
        cat_match = re.match(r"\*\*(.+?):\*\*\s*(.*)", line)
        if cat_match:
            cat_key = cat_match.group(1).lower().replace(" ", "_").replace("&", "and")
            items = [s.strip() for s in cat_match.group(2).split(",") if s.strip()]
            skill_groups[cat_key] = items

    # ── Experience ───────────────────────────────────────────────────────
    exp_match = re.search(r"##\s+EXPERIENCE\s*\n+(.*?)(?=\n##|\Z)", text, re.S)
    exp_text = exp_match.group(1).strip() if exp_match else ""
    experience = []
    # Each entry starts with "### Title — Company (Period)"
    entries = re.split(r"\n(?=###)", exp_text)
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        header = re.match(r"###\s+(.+?)\s+[—–-]+\s+(.+?)\s+\((.+?)\)", entry)
        if not header:
            # fallback: "### Title — Company (Period)" without parens on period
            header = re.match(r"###\s+(.+?)\s+[—–-]+\s+(.+)", entry)
            if not header:
                continue
            title = header.group(1).strip()
            company_period = header.group(2).strip()
            period = ""
            company = company_period
        else:
            title = header.group(1).strip()
            company = header.group(2).strip()
            period = header.group(3).strip()

        location_match = re.search(r"_(.+?)_", entry)
        location = location_match.group(1).strip() if location_match else ""

        bullets = re.findall(r"^-\s+(.+)$", entry, re.M)

        experience.append({
            "title": title,
            "company": company,
            "period": period,
            "location": location,
            "bullets": bullets,
        })

    # ── Education ────────────────────────────────────────────────────────
    edu_match = re.search(r"##\s+EDUCATION\s*\n+(.*?)(?=\n##|\Z)", text, re.S)
    edu_text = edu_match.group(1).strip() if edu_match else ""
    education = []
    for line in edu_text.splitlines():
        line = line.strip()
        if not line:
            continue
        # "**Degree**" on one line, institution | year on next
        deg_match = re.match(r"\*\*(.+?)\*\*", line)
        if deg_match:
            current_degree = deg_match.group(1).strip()
        elif "|" in line and education == [] or (education and "institution" not in education[-1]):
            parts = line.split("|")
            education.append({
                "degree": current_degree if "current_degree" in dir() else "",
                "institution": parts[0].strip(),
                "year": parts[1].strip() if len(parts) > 1 else "",
            })

    # ── Certifications ───────────────────────────────────────────────────
    cert_match = re.search(r"##\s+CERTIFICATIONS\s*\n+(.*?)(?=\n##|\Z)", text, re.S)
    cert_text = cert_match.group(1).strip() if cert_match else ""
    certifications = [
        re.sub(r"^-\s+", "", line).strip()
        for line in cert_text.splitlines()
        if line.strip().startswith("-")
    ]

    # ── Preview & Confirm ────────────────────────────────────────────────
    print(f"\n  Parsed from base.md:")
    print(f"    Summary     : {summary[:80]}{'…' if len(summary) > 80 else ''}")
    print(f"    Skill groups: {list(skill_groups.keys())}")
    print(f"    Experience  : {len(experience)} entries")
    for e in experience:
        print(f"      • {e['title']} @ {e['company']} ({e['period']})")
    print(f"    Education   : {len(education)} entries")
    print(f"    Certs       : {len(certifications)}")

    if not confirm("\n  Apply this data to config/profile.json?"):
        print("  Skipped.")
        return

    cv = profile.setdefault("cv", {})
    if summary:
        cv["summary"] = summary
    if skill_groups:
        cv["skills"] = skill_groups
    if experience:
        cv["experience"] = experience
    if education:
        cv["education"] = education
    if certifications:
        cv["certifications"] = certifications

    print("  CV section updated from base.md.")


def edit_api_key() -> None:
    hr("API Key")
    env_path = Path(".env")
    current = ""
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "API_KEY" in line:
                current = line.split("=", 1)[-1].strip().strip('"')
                break
    masked = f"{current[:8]}…{current[-4:]}" if len(current) > 12 else "(not set)"
    print(f"  Current API_KEY: {masked}")
    if confirm("  Update Anthropic API key?"):
        key = input("  Paste new key: ").strip()
        if key:
            env_path.write_text(f'API_KEY = "{key}"\n', encoding="utf-8")
            print("  .env updated.")


def edit_media() -> None:
    hr("Media Assets")
    media_dir = Path("media")
    media_dir.mkdir(exist_ok=True)
    print(f"  Place the following PNG files in {media_dir.resolve()}:")
    print("    Photo.png              — your profile photo")
    print("    <Company Name>.png     — logo for each employer in your CV")
    print("  Example: 'UBS Switzerland AG.png', 'Credit Suisse AG.png'")
    print("  The filename must match (or partially match) the company name in profile.json.")
    existing = list(media_dir.glob("*.png"))
    if existing:
        print(f"\n  Currently present: {', '.join(f.name for f in existing)}")
    else:
        print("\n  No PNG files found yet.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("\n" + "═" * 60)
    print("  Application Bot — Profile Setup")
    print("═" * 60)
    print("  This wizard updates config/profile.json.")
    print("  Press Enter to keep the current value shown in [brackets].\n")

    if not CONFIG_PATH.exists():
        print(f"  [error] {CONFIG_PATH} not found. Run from the project root.")
        sys.exit(1)

    profile = load_json()

    sections = {
        "1": ("Personal details",           lambda: edit_personal(profile)),
        "2": ("Work authorisation",          lambda: edit_work_auth(profile)),
        "3": ("Job preferences & roles",     lambda: edit_preferences(profile)),
        "4": ("Import CV from base.md",      lambda: edit_cv_from_base_md(profile)),
        "5": ("Anthropic API key (.env)",    edit_api_key),
        "6": ("Media assets guide",          edit_media),
        "7": ("Save & exit",                 None),
    }

    while True:
        hr("Menu")
        for key, (label, _) in sections.items():
            print(f"  {key}. {label}")
        choice = input("\n  Choose section: ").strip()

        if choice == "7":
            save_json(profile)
            print("\n  All done. You can now run:  python linkedin_scraper.py\n")
            break
        elif choice in sections:
            label, fn = sections[choice]
            fn()
        else:
            print("  Invalid choice.")


if __name__ == "__main__":
    main()
