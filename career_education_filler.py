#!/usr/bin/env python3
"""
career_education_filler.py — Copy-paste ready data for job application forms.

Reads config/profile.json and prints / saves a structured text with every
field commonly required by online application questionnaires:

  Work experience
    Job title | Company | Location | From | To | Role description

  Education
    School / University | Degree | From | To

  Skills (flat list)

Output: printed to console + saved to output/career_filler_<timestamp>.txt

Usage:
    python career_education_filler.py
"""

import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Ensure box-drawing characters print cleanly on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CONFIG_PATH = Path("config/profile.json")
OUTPUT_DIR = Path("output")

MONTH_ABBR = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_period(period: str) -> tuple[str, str, str, str]:
    """
    Parse a period string like 'Sep 2024 – Present' or 'Nov 2017 – Feb 2020'.
    Returns (from_month, from_year, to_month, to_year).
    to_month / to_year are 'Present' / '' when still employed.
    """
    # Normalise dash variants (en-dash, em-dash, hyphen)
    period = period.replace("–", "-").replace("—", "-").strip()
    parts = [p.strip() for p in re.split(r"\s*-\s*", period, maxsplit=1)]

    def _parse_one(s: str) -> tuple[str, str]:
        s = s.strip()
        if s.lower() in ("present", "now", "current", "ongoing"):
            return "Present", ""
        # "Sep 2024" or "2024"
        m = re.match(r"([A-Za-z]+)\s+(\d{4})", s)
        if m:
            month_name = m.group(1).lower()[:3]
            month = MONTH_ABBR.get(month_name, m.group(1))
            return month, m.group(2)
        m = re.match(r"(\d{4})", s)
        if m:
            return "", m.group(1)
        return s, ""

    from_month, from_year = _parse_one(parts[0]) if parts else ("", "")
    to_month, to_year = _parse_one(parts[1]) if len(parts) > 1 else ("Present", "")
    return from_month, from_year, to_month, to_year


def _bullets_to_description(bullets: list[str]) -> str:
    """Join bullets into a single prose paragraph for text-area fields."""
    return " ".join(b.rstrip(".") + "." for b in bullets if b.strip())


def _flat_skills(skills_raw) -> list[str]:
    """Flatten skills whether stored as dict-of-lists or flat list."""
    if isinstance(skills_raw, dict):
        return [s for group in skills_raw.values() for s in group]
    return list(skills_raw or [])


def _rule(char: str = "─", width: int = 60) -> str:
    return char * width


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def format_experience(experience: list[dict]) -> str:
    lines = [_rule("═"), "WORK EXPERIENCE", _rule("═"), ""]
    for i, exp in enumerate(experience, 1):
        from_month, from_year, to_month, to_year = _parse_period(exp.get("period", ""))

        # Human-readable from/to
        from_str = f"{from_month} {from_year}".strip() if from_year else from_month
        to_str = (
            "Present"
            if to_month == "Present"
            else f"{to_month} {to_year}".strip() if to_year else to_month
        )

        # Numeric from/to (MM/YYYY) for forms that need it
        from_num = (
            f"{from_month}/{from_year}" if from_year and from_month not in ("Present", "")
            else from_year
        )
        to_num = (
            "Present"
            if to_month == "Present"
            else f"{to_month}/{to_year}" if to_year and to_month not in ("", "Present")
            else to_year
        )

        description = _bullets_to_description(exp.get("bullets", []))

        lines += [
            f"[{i}] {exp.get('title', '')}",
            _rule("─"),
            f"  Job title     : {exp.get('title', '')}",
            f"  Company       : {exp.get('company', '')}",
            f"  Location      : {exp.get('location', '')}",
            f"  From          : {from_str}  ({from_num})",
            f"  To            : {to_str}  ({to_num})",
            f"  Description   :",
            "",
        ]
        # Wrap description at ~90 chars for readability
        words = description.split()
        line_buf, current = [], ""
        for word in words:
            if len(current) + len(word) + 1 > 90:
                line_buf.append("    " + current.rstrip())
                current = word + " "
            else:
                current += word + " "
        if current.strip():
            line_buf.append("    " + current.rstrip())
        lines += line_buf
        lines.append("")

    return "\n".join(lines)


def format_education(education: list[dict]) -> str:
    lines = [_rule("═"), "EDUCATION", _rule("═"), ""]
    for i, edu in enumerate(education, 1):
        year_str = edu.get("year", "")
        # Parse "2017 – 2019" or "2017-2019"
        year_clean = year_str.replace("–", "-").replace("—", "-")
        year_parts = [p.strip() for p in year_clean.split("-", 1)]
        from_year = year_parts[0] if year_parts else ""
        to_year = year_parts[1] if len(year_parts) > 1 else ""

        # Degree / field split: "MSc Management, Major in Financial Management"
        degree_full = edu.get("degree", "")
        degree_parts = degree_full.split(",", 1)
        degree_title = degree_parts[0].strip()
        degree_field = degree_parts[1].strip() if len(degree_parts) > 1 else ""

        lines += [
            f"[{i}] {degree_full}",
            _rule("─"),
            f"  School / University : {edu.get('institution', '')}",
            f"  Degree              : {degree_title}",
            f"  Field / Major       : {degree_field}",
            f"  From                : {from_year}",
            f"  To                  : {to_year}",
            "",
        ]
    return "\n".join(lines)


def format_skills(skills_raw) -> str:
    skills = _flat_skills(skills_raw)
    lines = [_rule("═"), "SKILLS", _rule("═"), ""]
    for s in skills:
        lines.append(f"  • {s}")
    lines.append("")
    return "\n".join(lines)


def format_certifications(certs: list[str]) -> str:
    if not certs:
        return ""
    lines = [_rule("═"), "CERTIFICATIONS", _rule("═"), ""]
    for c in certs:
        lines.append(f"  • {c}")
    lines.append("")
    return "\n".join(lines)


def format_languages(langs: list[str]) -> str:
    if not langs:
        return ""
    lines = [_rule("═"), "LANGUAGES", _rule("═"), ""]
    for lang in langs:
        lines.append(f"  • {lang}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not CONFIG_PATH.exists():
        print(f"[!] {CONFIG_PATH} not found.")
        return

    with open(CONFIG_PATH, encoding="utf-8") as f:
        profile = json.load(f)

    personal = profile.get("personal", {})
    cv = profile.get("cv", {})

    header = "\n".join([
        _rule("═", 60),
        "APPLICATION FORM FILLER",
        f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Candidate : {personal.get('full_name', '')}",
        f"Email     : {personal.get('email', '')}",
        f"Phone     : {personal.get('phone', '')}",
        f"Location  : {personal.get('location', '')}",
        f"LinkedIn  : {personal.get('linkedin', '')}",
        _rule("═", 60),
        "",
    ])

    sections = [
        header,
        format_experience(cv.get("experience", [])),
        format_education(cv.get("education", [])),
        format_skills(cv.get("skills", [])),
        format_certifications(cv.get("certifications", [])),
        format_languages(cv.get("languages", [])),
    ]

    output = "\n".join(s for s in sections if s)

    # Print to console
    print(output)

    # Save to file
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = OUTPUT_DIR / f"career_filler_{timestamp}.txt"
    out_path.write_text(output, encoding="utf-8")
    print(_rule("─"))
    print(f"Saved -> {out_path.resolve()}")


if __name__ == "__main__":
    main()
