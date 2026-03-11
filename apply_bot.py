#!/usr/bin/env python3
"""
apply_bot.py — LinkedIn Easy Apply automation + persistent job tracker.

Handles:
  • attempt_easy_apply()   — navigate the full Easy Apply modal for one job
  • run_apply_session()    — orchestrate apply loop with skip/limit logic
  • Tracker CRUD           — load / upsert / mark-applied / save Excel tracker
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import anthropic
import pandas as pd
from dotenv import load_dotenv
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

load_dotenv()

TRACKER_PATH = Path("output/linkedin_tracker.xlsx")
LI_BLUE = "0A66C2"

TRACKER_COLS = [
    "title", "company", "location", "url",
    "easy_apply", "search_role", "scraped_at",
    "applied", "applied_at", "cv_path",
]


# ===========================================================================
# Tracker management
# ===========================================================================

def load_tracker() -> pd.DataFrame:
    """Load existing tracker or return an empty DataFrame with correct columns."""
    if TRACKER_PATH.exists():
        try:
            df = pd.read_excel(TRACKER_PATH, sheet_name="Tracker")
            return df.reindex(columns=TRACKER_COLS)
        except Exception as exc:
            print(f"  [tracker] Could not read tracker ({exc}) — starting fresh.")
    return pd.DataFrame(columns=TRACKER_COLS)


def upsert_jobs(df: pd.DataFrame, jobs: list[dict]) -> pd.DataFrame:
    """Add jobs not already in the tracker. Existing rows are never overwritten."""
    existing = set(df["url"].dropna().tolist())
    new_rows = []
    for job in jobs:
        if job.get("url") in existing:
            continue
        row = {col: job.get(col) for col in TRACKER_COLS}
        row["applied"] = False
        row["applied_at"] = None
        row["cv_path"] = None
        new_rows.append(row)
    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows, columns=TRACKER_COLS)], ignore_index=True)
        print(f"  [tracker] Added {len(new_rows)} new job(s).")
    return df


def mark_applied(df: pd.DataFrame, url: str, cv_path: Path | None = None) -> pd.DataFrame:
    """Mark a job as applied and record the timestamp and CV used."""
    mask = df["url"] == url
    if mask.any():
        df.loc[mask, "applied"] = True
        df.loc[mask, "applied_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        if cv_path:
            df.loc[mask, "cv_path"] = str(cv_path)
    return df


def already_applied(df: pd.DataFrame, url: str) -> bool:
    """Return True if the URL has been marked applied in the tracker."""
    rows = df.loc[df["url"] == url, "applied"]
    return bool(rows.any() and rows.iloc[0])


def save_tracker(df: pd.DataFrame) -> None:
    """Write tracker to Excel with LinkedIn-branded header formatting."""
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(TRACKER_PATH, index=False, sheet_name="Tracker")

    wb = load_workbook(TRACKER_PATH)
    ws = wb.active

    header_fill = PatternFill(start_color=LI_BLUE, end_color=LI_BLUE, fill_type="solid")
    header_font = Font(name="Calibri", color="FFFFFF", bold=True, size=11)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 20

    # Hyperlink URL column
    url_col_idx = None
    for idx, cell in enumerate(ws[1], 1):
        if str(cell.value).lower() == "url":
            url_col_idx = idx
            break

    body_font = Font(name="Calibri", size=10)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = body_font
            if url_col_idx and cell.column == url_col_idx and cell.value:
                cell.hyperlink = str(cell.value)
                cell.font = Font(name="Calibri", size=10, color="0563C1", underline="single")
                cell.value = "Open"

    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 55)

    ws.freeze_panes = "A2"
    wb.save(TRACKER_PATH)
    print(f"  [tracker] Saved -> {TRACKER_PATH.resolve()}")


# ===========================================================================
# Question-answering helpers
# ===========================================================================

def _exp_years(profile: dict) -> str:
    """Estimate total years of professional experience from the earliest job date."""
    all_years = []
    for e in profile.get("cv", {}).get("experience", []):
        for y in re.findall(r"\b(20\d{2}|19\d{2})\b", e.get("period", "")):
            all_years.append(int(y))
    if not all_years:
        return "7"
    return str(max(1, datetime.now().year - min(all_years)))


def _rule_answer(label: str, profile: dict) -> str | None:
    """Return a rule-based answer for common form labels, or None if no rule matches."""
    ll = label.lower().strip()
    p = profile["personal"]
    name_parts = p.get("full_name", "").split()

    rules = [
        (r"first\s*name",                       lambda: name_parts[0] if name_parts else ""),
        (r"last\s*name|surname|family\s*name",  lambda: name_parts[-1] if len(name_parts) > 1 else ""),
        (r"full\s*name",                         lambda: p.get("full_name", "")),
        (r"email",                               lambda: p.get("email", "")),
        (r"phone|mobile|telephone",              lambda: p.get("phone", "")),
        (r"\bcity\b|\btown\b",                   lambda: p.get("location", "").split(",")[0].strip()),
        (r"country",                             lambda: "Switzerland"),
        (r"linkedin",                            lambda: p.get("linkedin", "")),
        (r"github",                              lambda: p.get("github", "")),
        (r"portfolio|personal\s*url|website",    lambda: p.get("portfolio", "")),
        (r"years?.{0,30}experience|experience.{0,30}years?",
                                                 lambda: _exp_years(profile)),
        (r"salary|compensation|ctc|pay",         lambda: str(profile["preferences"].get("min_salary_usd", 70000))),
        (r"authoriz|eligible.{0,20}work|right\s*to\s*work|work\s*permit",
                                                 lambda: "Yes"),
        (r"require.{0,20}sponsor|need.{0,20}sponsor|visa\s*sponsor",
                                                 lambda: "No"),
        (r"relocat",                             lambda: "No"),
        (r"notice\s*period|notice\s*time",       lambda: "2 weeks"),
        (r"start\s*date|available\s*from|earliest\s*start",
                                                 lambda: "As soon as possible"),
        (r"how\s*did\s*you\s*hear|source|referred\s*by",
                                                 lambda: "LinkedIn"),
        (r"cover\s*letter",                      lambda: ""),
    ]

    for pattern, fn in rules:
        if re.search(pattern, ll):
            return fn()
    return None


def _haiku_answer(question: str, options: list[str], profile: dict) -> str:
    """Use Claude Haiku to answer questions that don't match any rule."""
    api_key = os.environ.get("API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    cv = profile.get("cv", {})
    snapshot = {
        "name": profile["personal"].get("full_name"),
        "location": profile["personal"].get("location"),
        "experience_years": _exp_years(profile),
        "work_auth": profile.get("work_authorization", {}),
        "last_title": (cv.get("experience") or [{}])[0].get("title", ""),
        "last_company": (cv.get("experience") or [{}])[0].get("company", ""),
        "min_salary_usd": profile["preferences"].get("min_salary_usd", 70000),
    }

    opts_line = f"\nChoose from (copy verbatim): {options}" if options else ""
    prompt = (
        f"You are filling a LinkedIn job application for this candidate.\n"
        f"Candidate: {json.dumps(snapshot)}\n"
        f"Question: {question}{opts_line}\n\n"
        "Return ONLY the answer — no explanation, no punctuation wrapper."
    )

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as exc:
        print(f"      [apply] Haiku Q&A error: {exc}")
        return options[0] if options else ""


# ===========================================================================
# Form interaction helpers
# ===========================================================================

def _get_label(page: Page, el) -> str:
    """Return the label text associated with a form element."""
    el_id = el.get_attribute("id")
    if el_id:
        lbl = page.query_selector(f"label[for='{el_id}']")
        if lbl:
            return lbl.inner_text().strip()

    # Walk up the DOM for a label/legend ancestor
    text = el.evaluate("""el => {
        let node = el.parentElement;
        for (let i = 0; i < 7; i++) {
            if (!node) break;
            const lbl = node.querySelector('label, legend, [class*="label"]');
            if (lbl && lbl.innerText.trim().length > 1) return lbl.innerText.trim();
            node = node.parentElement;
        }
        return '';
    }""")
    return (text or "").strip()


def _fill_inputs(page: Page, profile: dict) -> None:
    """Fill visible, empty text / number / tel / email inputs."""
    for inp in page.query_selector_all(
        "input[type='text'], input[type='number'], input[type='tel'], input[type='email']"
    ):
        try:
            if not inp.is_visible():
                continue
            if (inp.input_value() or "").strip():
                continue
            label = _get_label(page, inp)
            if not label:
                continue
            answer = _rule_answer(label, profile)
            if answer is None:
                answer = _haiku_answer(label, [], profile)
            if answer:
                inp.triple_click()
                inp.fill(answer)
        except Exception as exc:
            print(f"      [apply] input error: {exc}")


def _fill_textareas(page: Page, profile: dict) -> None:
    for ta in page.query_selector_all("textarea"):
        try:
            if not ta.is_visible() or (ta.input_value() or "").strip():
                continue
            label = _get_label(page, ta)
            if not label:
                continue
            answer = _rule_answer(label, profile) or _haiku_answer(label, [], profile)
            if answer:
                ta.fill(answer)
        except Exception as exc:
            print(f"      [apply] textarea error: {exc}")


def _fill_selects(page: Page, profile: dict) -> None:
    for sel in page.query_selector_all("select"):
        try:
            if not sel.is_visible():
                continue
            current = sel.input_value() or ""
            if current and current.lower() not in ("", "select an option", "-- none --"):
                continue
            label = _get_label(page, sel)
            if not label:
                continue

            # Collect human-readable option texts
            sel_id = sel.get_attribute("id")
            opt_sel = f"#{sel_id} option" if sel_id else "option"
            options = []
            for opt in page.query_selector_all(opt_sel):
                val = opt.get_attribute("value") or ""
                txt = opt.inner_text().strip()
                if val and txt and txt.lower() not in ("select an option", "-- none --", ""):
                    options.append(txt)

            answer = _rule_answer(label, profile)
            if answer is None:
                answer = _haiku_answer(label, options, profile)
            if not answer:
                continue

            # Try exact match first, then contains match
            matched = False
            for opt in page.query_selector_all(opt_sel):
                txt = opt.inner_text().strip()
                if txt.lower() == answer.lower():
                    sel.select_option(label=txt)
                    matched = True
                    break
            if not matched:
                for opt in page.query_selector_all(opt_sel):
                    txt = opt.inner_text().strip()
                    if answer.lower() in txt.lower() or txt.lower() in answer.lower():
                        sel.select_option(label=txt)
                        break
        except Exception as exc:
            print(f"      [apply] select error: {exc}")


def _fill_radios(page: Page, profile: dict) -> None:
    """Answer radio groups that have no selection yet."""
    names: set[str] = set()
    for r in page.query_selector_all("input[type='radio']"):
        n = r.get_attribute("name")
        if n:
            names.add(n)

    for name in names:
        try:
            radios = page.query_selector_all(f"input[type='radio'][name='{name}']")
            if not radios or any(r.is_checked() for r in radios):
                continue

            # Find the group question from fieldset legend or nearest label-like element
            safe_name = name.replace('"', '\\"')
            question = page.evaluate(f"""() => {{
                const r = document.querySelector('input[type="radio"][name="{safe_name}"]');
                if (!r) return '';
                let node = r.closest('fieldset') || r.parentElement;
                for (let i = 0; i < 7; i++) {{
                    if (!node) break;
                    const leg = node.querySelector('legend, [class*="label"]');
                    if (leg && leg.innerText.trim().length > 2) return leg.innerText.trim();
                    node = node.parentElement;
                }}
                return '';
            }}""")

            option_map: dict[str, object] = {}
            for r in radios:
                rid = r.get_attribute("id")
                lbl = page.query_selector(f"label[for='{rid}']") if rid else None
                if lbl:
                    option_map[lbl.inner_text().strip()] = r

            options = list(option_map.keys())
            if not options:
                continue

            answer = _rule_answer(question or options[0], profile)
            if answer is None:
                answer = _haiku_answer(question or "", options, profile)

            # Click best-matching radio
            clicked = False
            if answer:
                for txt, radio_el in option_map.items():
                    if answer.lower() == txt.lower() or answer.lower() in txt.lower():
                        radio_el.click()
                        clicked = True
                        break
            if not clicked:
                list(option_map.values())[0].click()
        except Exception as exc:
            print(f"      [apply] radio error: {exc}")


def _uncheck_optionals(page: Page) -> None:
    """Uncheck opt-in checkboxes for Follow, Featured/Top applicant, etc."""
    SPAM_PATTERNS = [
        "follow", "featured applicant", "top applicant", "top choice",
        "notify me", "receive email", "get email",
    ]
    for cb in page.query_selector_all("input[type='checkbox']"):
        try:
            if not cb.is_visible() or not cb.is_checked():
                continue
            label = _get_label(page, cb).lower()
            if any(pat in label for pat in SPAM_PATTERNS):
                cb.click()
                print(f"      [apply] Unchecked: '{label[:60]}'")
        except Exception:
            pass


def _upload_resume(page: Page, cv_path: Path) -> bool:
    """Upload the tailored CV PDF. Works even on hidden file inputs."""
    try:
        file_input = page.query_selector("input[type='file']")
        if not file_input:
            return False
        file_input.set_input_files(str(cv_path.resolve()))
        time.sleep(1.5)
        print(f"      [apply] Uploaded: {cv_path.name}")
        return True
    except Exception as exc:
        print(f"      [apply] Upload failed: {exc}")
        return False


def _advance(page: Page) -> str:
    """Click Submit / Review / Next. Returns which button was clicked, or 'stuck'."""
    for aria_label, key in [
        ("Submit application", "submit"),
        ("Review your application", "review"),
        ("Continue to next step", "next"),
    ]:
        btn = page.query_selector(f"button[aria-label='{aria_label}']")
        if btn and btn.is_visible() and btn.is_enabled():
            btn.click()
            return key

    # Fallback: scan button text
    for text, key in [("Submit application", "submit"), ("Review", "review"), ("Next", "next"), ("Continue", "next")]:
        for btn in page.query_selector_all("button"):
            try:
                if not (btn.is_visible() and btn.is_enabled()):
                    continue
                span = btn.query_selector("span")
                btn_text = (span.inner_text() if span else btn.inner_text()).strip()
                if btn_text == text:
                    btn.click()
                    return key
            except Exception:
                pass

    return "stuck"


def _close_modal(page: Page) -> None:
    """Dismiss the Easy Apply modal and confirm discard if prompted."""
    for sel in ["button[aria-label='Dismiss']", "button[aria-label='Close']",
                ".artdeco-modal__dismiss"]:
        btn = page.query_selector(sel)
        if btn and btn.is_visible():
            try:
                btn.click()
                time.sleep(0.8)
            except Exception:
                pass
            break

    # Confirm discard dialog
    for discard_sel in [
        "button[data-test-dialog-primary-btn]",
        "button[aria-label='Discard']",
        "button[data-control-name='discard_application_confirm_btn']",
    ]:
        btn = page.query_selector(discard_sel)
        if btn and btn.is_visible():
            try:
                btn.click()
            except Exception:
                pass
            return

    # Last resort: any visible "Discard" button
    for btn in page.query_selector_all("button"):
        try:
            if btn.is_visible() and "discard" in (btn.inner_text() or "").lower():
                btn.click()
                return
        except Exception:
            pass


# ===========================================================================
# Core modal handler
# ===========================================================================

def _run_modal(page: Page, profile: dict, cv_path: Path | None) -> bool:
    """Step through the Easy Apply modal. Returns True if successfully submitted."""
    MODAL_SEL = "div.jobs-easy-apply-modal, [data-test-modal-id='easy-apply-modal']"
    MAX_STEPS = 12
    cv_uploaded = False

    for step in range(MAX_STEPS):
        time.sleep(1.0)

        if not page.query_selector(MODAL_SEL):
            print("      [apply] Modal closed unexpectedly")
            return False

        # On the review/submit step there are no fields to fill — skip scanning
        is_review = bool(
            page.query_selector("button[aria-label='Submit application']")
            or page.query_selector("button[aria-label='Review your application']")
        )

        if not is_review:
            # Upload CV once (first step that has a file input)
            if cv_path and not cv_uploaded:
                if page.query_selector("input[type='file']"):
                    cv_uploaded = _upload_resume(page, cv_path)

            _uncheck_optionals(page)
            _fill_inputs(page, profile)
            _fill_textareas(page, profile)
            _fill_selects(page, profile)
            _fill_radios(page, profile)
            _uncheck_optionals(page)  # second pass — some appear after fills

        time.sleep(0.3)
        result = _advance(page)
        print(f"      [apply] Step {step + 1}: {result}")

        if result == "submit":
            time.sleep(2)
            # Check for form validation errors
            err = page.query_selector(
                ".artdeco-inline-feedback--error, .jobs-easy-apply-form-element__error"
            )
            if err:
                print(f"      [apply] Blocked by error: {err.inner_text()[:120]}")
                return False
            return True

        if result == "stuck":
            print(f"      [apply] No navigation button found at step {step + 1}")
            return False

    print("      [apply] Reached step limit without submitting")
    return False


# ===========================================================================
# Public API
# ===========================================================================

def attempt_easy_apply(page: Page, job: dict, profile: dict, cv_path: Path | None) -> bool:
    """
    Attempt to submit a LinkedIn Easy Apply for one job.
    Returns True if the application was submitted successfully.
    """
    title = job.get("title", "?")
    company = job.get("company", "?")
    print(f"    [apply] {title} @ {company}")

    try:
        # Navigate and wait only until DOM is ready, then wait for a job element
        page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)

        for sel in [
            ".jobs-apply-button",
            ".jobs-unified-top-card__job-title",
            ".job-details-jobs-unified-top-card__job-title",
            ".jobs-details__main-content",
        ]:
            try:
                page.wait_for_selector(sel, timeout=8000)
                break
            except Exception:
                pass

        time.sleep(0.5)
        print(f"      [apply] URL: {page.url[:90]}")

        # Find and click Easy Apply via JS.
        # LinkedIn renders this as either a <button> or an <a> tag depending
        # on the page version, so we search both by aria-label and by text.
        result = page.evaluate("""() => {
            // 1. aria-label match on any element (button OR anchor)
            let el = document.querySelector('[aria-label*="Easy Apply"]');
            // 2. text match across buttons and anchors
            if (!el) {
                el = [...document.querySelectorAll('button, a')].find(e =>
                    e.innerText && e.innerText.trim().includes('Easy Apply')
                );
            }
            if (!el || el.disabled) return null;
            // Detect already-applied state
            if (el.innerText && el.innerText.toLowerCase().includes('applied') &&
                !el.innerText.toLowerCase().includes('easy apply')) {
                return 'already_applied';
            }
            el.click();
            return el.innerText ? el.innerText.trim() : 'clicked';
        }""")

        if result is None:
            print("    [apply] No Easy Apply button — skipping")
            return False
        if result == "already_applied":
            print("    [apply] Already applied (button says Applied) — skipping")
            return False

        time.sleep(2)

        submitted = _run_modal(page, profile, cv_path)

        if not submitted:
            _close_modal(page)
            time.sleep(1)

        return submitted

    except Exception as exc:
        print(f"    [apply] Error: {exc}")
        try:
            _close_modal(page)
        except Exception:
            pass
        return False


def run_apply_session(
    page: Page,
    jobs: list[dict],
    profile: dict,
    cv_map: dict,
) -> None:
    """
    For each job in `jobs` (up to max_applications_per_session):
      - skip if already applied (per tracker)
      - attempt Easy Apply with the matching tailored CV
      - update and save the tracker
    """
    df = load_tracker()
    # Only track jobs that passed the CV relevance check (have a generated CV)
    relevant_jobs = [j for j in jobs if j.get("url") in cv_map]
    df = upsert_jobs(df, relevant_jobs)

    max_apps = profile["preferences"].get("max_applications_per_session", 15)
    applied_count = 0

    for job in jobs:
        if applied_count >= max_apps:
            print(f"\n[apply] Session limit reached ({max_apps} applications).")
            break

        url = job.get("url", "")

        if already_applied(df, url):
            print(f"  [apply] Skip (already applied): {job.get('title')} @ {job.get('company')}")
            continue

        if not job.get("easy_apply"):
            print(f"  [apply] External apply — see URL in tracker: {job.get('title')} @ {job.get('company')}")
            continue

        cv_path = cv_map.get(url)
        success = attempt_easy_apply(page, job, profile, cv_path)

        if success:
            df = mark_applied(df, url, cv_path)
            applied_count += 1
            print(f"    [apply] ✓ Applied ({applied_count}/{max_apps})")

        time.sleep(3)  # polite delay between applications

    save_tracker(df)
    print(f"\n[apply] Session complete — {applied_count} application(s) submitted.")
