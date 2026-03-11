#!/usr/bin/env python3
"""
CV Generator - Phase 2 of Application Bot
For each job listing, fetches the job description via Playwright, calls Claude
to generate a tailored CV, and saves it as a PDF to output/cvs/.

Usage (standalone, needs a live Playwright page passed in):
    Called from linkedin_scraper.py after scraping jobs.
"""

import json
import os
import re
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

load_dotenv()

CONFIG_PATH = Path("config/profile.json")
OUTPUT_DIR = Path("output")
CVS_DIR = OUTPUT_DIR / "cvs"
MEDIA_DIR = Path("media")

# Brand colour matching the LinkedIn scraper
BRAND_BLUE = colors.HexColor("#0A66C2")
DARK_TEXT = colors.HexColor("#1B1B1B")
MID_GREY = colors.HexColor("#555555")
LIGHT_GREY = colors.HexColor("#F3F3F3")


# ---------------------------------------------------------------------------
# Profile loader
# ---------------------------------------------------------------------------

def load_profile() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Job description scraper
# ---------------------------------------------------------------------------

def fetch_job_description(page, url: str, prefetched: str | None = None) -> str:
    """Return the 'About the job' text. Uses prefetched if available, otherwise navigates."""
    if prefetched and len(prefetched) > 100:
        return prefetched

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)

        # Wait for the job details pane to render
        try:
            page.wait_for_selector("#job-details, .jobs-description", timeout=12000)
        except Exception:
            pass

        time.sleep(1.5)

        # --- Expand the truncated description ---
        # LinkedIn renders an inline "... more" button as a <button> with text
        # "more" (and sometimes aria-expanded="false") inside the description div.
        # We try JS-based clicks so visibility/overlap doesn't block us.
        expanded = page.evaluate("""() => {
            const candidates = [
                // standard show-more button class
                ...document.querySelectorAll('button.show-more-less-html__button--more'),
                // any button whose text is exactly "more" or "See more"
                ...[...document.querySelectorAll('button')].filter(b =>
                    /^\\s*(see\\s+)?more\\s*$/i.test(b.innerText)
                ),
                // footer "Show more" link scoped to the description section only
                ...document.querySelectorAll(
                    '.jobs-description__footer-button, #job-details button[aria-expanded="false"], .jobs-description button[aria-expanded="false"]'
                ),
            ];
            for (const btn of candidates) {
                try { btn.click(); return true; } catch(e) {}
            }
            return false;
        }""")

        if expanded:
            time.sleep(1.0)   # let the DOM update after expand

        # --- Read the description ---
        # Try selectors from most to least specific; skip if result is tiny
        selectors = [
            "#job-details",
            ".jobs-description__content",
            ".jobs-description-content__text",
            ".show-more-less-html__markup",
            "[class*='jobs-description-content']",
            "article.jobs-description__container",
            ".jobs-box__html-content",
        ]

        for sel in selectors:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 100:
                    return text[:4500]

        # Last-resort: locate the "About the job" heading and walk up to its
        # section container, then grab all text inside it.
        text = page.evaluate("""() => {
            const heading = [...document.querySelectorAll('h1,h2,h3,h4')]
                .find(h => /about the job/i.test(h.innerText));
            if (!heading) return '';
            // walk up until we find a container with meaningful content
            let el = heading.parentElement;
            for (let i = 0; i < 5; i++) {
                if (el && el.innerText && el.innerText.length > 200) return el.innerText;
                if (el) el = el.parentElement;
            }
            return '';
        }""")

        if text and len(text) > 100:
            return text[:4500]

        print(f"    [warn] Could not find description element on {url}")
        return ""

    except Exception as exc:
        print(f"    [warn] Failed to fetch job description: {exc}")
        return ""


# ---------------------------------------------------------------------------
# Claude CV generation
# ---------------------------------------------------------------------------

def generate_tailored_cv(profile: dict, job: dict, description: str) -> dict:
    """Send profile + job description to Claude and return tailored CV as dict."""
    api_key = os.environ.get("API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    cv_data = profile.get("cv", {})
    personal = profile["personal"]

    # Flatten skills dict into a single list for the prompt
    raw_skills = cv_data.get("skills", {})
    if isinstance(raw_skills, dict):
        all_skills = [s for group in raw_skills.values() for s in group]
    else:
        all_skills = raw_skills
    cv_for_prompt = {**cv_data, "skills": all_skills}

    prompt = f"""You are an expert CV writer. Create a highly tailored CV for this candidate \
applying to the specific role below. Prioritise skills, achievements, and terminology \
that directly match the job description.

=== CANDIDATE MASTER CV ===
{json.dumps(cv_for_prompt, indent=2)}

=== PERSONAL DETAILS ===
Name     : {personal['full_name']}
Email    : {personal['email']}
Phone    : {personal['phone']}
LinkedIn : {personal['linkedin']}
GitHub   : {personal.get('github', '')}
Location : {personal['location']}

=== TARGET JOB ===
Title   : {job['title']}
Company : {job['company']}
Location: {job['location']}
URL     : {job.get('url', '')}

=== JOB DESCRIPTION ===
{description or '(No description available — tailor to the job title and company.)'}

=== INSTRUCTIONS ===
- Write a 2-3 sentence professional summary that directly addresses THIS role.
- Select exactly 9 of the most relevant skills (no more, no fewer) and list them first.
- Keep every skill label SHORT — maximum 4 words, ideally 2-3. \
  Use concise forms: "Analytical Problem-Solving" not "Troubleshooting & Analytical Problem-Solving", \
  "Workflow Design" not "Conversational Flow & Workflow Design".
- For each experience entry, rewrite bullet points to emphasise impact most \
relevant to this job (keep dates and company names unchanged).
- Return ONLY valid JSON — no markdown fences, no extra text.

Return this exact JSON structure:
{{
  "summary": "...",
  "skills": ["skill1", "skill2"],
  "experience": [
    {{
      "title": "...",
      "company": "...",
      "period": "...",
      "bullets": ["...", "..."]
    }}
  ],
  "education": [
    {{
      "degree": "...",
      "institution": "...",
      "year": "..."
    }}
  ],
  "certifications": ["..."],
  "languages": ["..."]
}}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if not raw:
        raise ValueError("Claude returned an empty response")

    # Strip any accidental code fences
    if "```" in raw:
        raw = re.sub(r"```(?:json)?", "", raw).strip()
        raw = raw.rstrip("`").strip()

    if not raw:
        raise ValueError("Response was empty after stripping markdown fences")

    # If Claude wrote a narrative explanation instead of JSON it means the job
    # is a mismatch — raise a distinct error so the caller can skip cleanly.
    if not raw.lstrip().startswith("{"):
        first_line = raw.splitlines()[0][:120]
        raise ValueError(f"JOB_MISMATCH: {first_line}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"    [cv] Raw Claude response (first 300 chars): {raw[:300]}")
        raise


# ---------------------------------------------------------------------------
# PDF rendering helpers
# ---------------------------------------------------------------------------

def _build_styles() -> dict:
    styles = {
        "name": ParagraphStyle(
            "name",
            fontSize=22,
            leading=26,
            textColor=BRAND_BLUE,
            fontName="Helvetica-Bold",
            alignment=TA_LEFT,
        ),
        "contact": ParagraphStyle(
            "contact",
            fontSize=8.5,
            leading=13,
            textColor=MID_GREY,
            fontName="Helvetica",
            alignment=TA_LEFT,
        ),
        "section_heading": ParagraphStyle(
            "section_heading",
            fontSize=10,
            leading=14,
            textColor=BRAND_BLUE,
            fontName="Helvetica-Bold",
            spaceBefore=10,
            spaceAfter=2,
        ),
        "summary": ParagraphStyle(
            "summary",
            fontSize=9.5,
            leading=14,
            textColor=DARK_TEXT,
            fontName="Helvetica",
        ),
        "job_title": ParagraphStyle(
            "job_title",
            fontSize=9.5,
            leading=13,
            textColor=DARK_TEXT,
            fontName="Helvetica-Bold",
        ),
        "job_meta": ParagraphStyle(
            "job_meta",
            fontSize=8.5,
            leading=12,
            textColor=MID_GREY,
            fontName="Helvetica-Oblique",
        ),
        "bullet": ParagraphStyle(
            "bullet",
            fontSize=9,
            leading=13,
            textColor=DARK_TEXT,
            fontName="Helvetica",
            leftIndent=12,
            spaceAfter=1,
        ),
        "skill_item": ParagraphStyle(
            "skill_item",
            fontSize=8,
            leading=10,
            textColor=DARK_TEXT,
            fontName="Helvetica",
            spaceAfter=0,
            spaceBefore=0,
        ),
        "edu_main": ParagraphStyle(
            "edu_main",
            fontSize=9.5,
            leading=13,
            textColor=DARK_TEXT,
            fontName="Helvetica-Bold",
        ),
        "edu_sub": ParagraphStyle(
            "edu_sub",
            fontSize=8.5,
            leading=12,
            textColor=MID_GREY,
            fontName="Helvetica",
        ),
    }
    return styles


def _divider():
    return HRFlowable(
        width="100%", thickness=0.5, color=BRAND_BLUE, spaceAfter=4, spaceBefore=2
    )


def _section(title: str, styles: dict):
    return [
        Paragraph(title.upper(), styles["section_heading"]),
        _divider(),
    ]


def _scaled_image(path: Path, height_cm: float, hAlign: str = "LEFT") -> RLImage:
    """Return an RLImage scaled to the requested height, preserving aspect ratio."""
    with PILImage.open(path) as img:
        w_px, h_px = img.size
    aspect = w_px / h_px
    h = height_cm * cm
    img_obj = RLImage(str(path), width=h * aspect, height=h)
    img_obj.hAlign = hAlign
    return img_obj


def _find_logo(company: str) -> Path | None:
    """Fuzzy-match a company name to a logo file in media/."""
    if not MEDIA_DIR.exists():
        return None
    company_lower = company.lower()
    for logo_path in MEDIA_DIR.glob("*.png"):
        stem = logo_path.stem.lower()
        # match if either string contains the other (handles "UBS Switzerland AG" ↔ "UBS Switzerland AG.png")
        if stem in company_lower or company_lower in stem:
            return logo_path
        # also try first word of logo name (e.g. "state" in "state street bank international gmbh")
        first_word = stem.split()[0]
        if first_word and first_word in company_lower:
            return logo_path
    return None


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

def render_cv_pdf(cv: dict, profile: dict, job: dict, output_path: Path) -> None:
    """Render the tailored CV dict as a professional A4 PDF with photo and logos."""
    CVS_DIR.mkdir(parents=True, exist_ok=True)

    personal = profile["personal"]
    styles = _build_styles()

    LEFT_MARGIN = 1.8 * cm
    RIGHT_MARGIN = 1.8 * cm
    USABLE_W = A4[0] - LEFT_MARGIN - RIGHT_MARGIN
    PHOTO_COL = 2.6 * cm
    TEXT_COL = USABLE_W - PHOTO_COL - 0.3 * cm   # 0.3 gap between columns

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=RIGHT_MARGIN,
        leftMargin=LEFT_MARGIN,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
    )

    story = []

    # ------------------------------------------------------------------ Header
    # Left side: name + contact lines
    # Right side: photo

    name_para = Paragraph(personal["full_name"], styles["name"])

    contact_parts = [
        personal.get("email", ""),
        personal.get("phone", ""),
        personal.get("location", ""),
    ]
    contact_line = "  |  ".join(p for p in contact_parts if p)
    contact_para = Paragraph(contact_line, styles["contact"])

    link_parts = []
    if personal.get("linkedin"):
        link_parts.append(f'<link href="{personal["linkedin"]}">LinkedIn</link>')
    if personal.get("github"):
        link_parts.append(f'<link href="{personal["github"]}">GitHub</link>')
    if personal.get("portfolio"):
        link_parts.append(f'<link href="{personal["portfolio"]}">Portfolio</link>')
    links_para = Paragraph("  |  ".join(link_parts), styles["contact"]) if link_parts else Spacer(1, 1)

    photo_path = MEDIA_DIR / "Photo.png"
    if photo_path.exists():
        photo_img = _scaled_image(photo_path, height_cm=3.2, hAlign="LEFT")
        header_data = [[
            photo_img,
            [name_para, Spacer(1, 3), contact_para, Spacer(1, 2), links_para],
        ]]
        header_table = Table(
            header_data,
            colWidths=[PHOTO_COL, TEXT_COL],
        )
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN",  (0, 0), (0, 0),  "LEFT"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (0, 0),  0),
            ("RIGHTPADDING",  (1, 0), (1, 0),  0),
            ("LEFTPADDING",   (1, 0), (1, 0),  8),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
    else:
        # No photo — centred layout fallback
        story.append(Paragraph(personal["full_name"], styles["name"]))
        story.append(Spacer(1, 3))
        story.append(contact_para)
        story.append(links_para)

    story.append(Spacer(1, 6))

    # --------------------------------------------------------------- Summary
    if cv.get("summary"):
        story += _section("Professional Summary", styles)
        story.append(Paragraph(cv["summary"], styles["summary"]))
        story.append(Spacer(1, 4))

    # ----------------------------------------------------------------- Skills
    if cv.get("skills"):
        story += _section("Core Skills", styles)
        skill_list = cv["skills"][:9]   # 3 cols × 3 rows max
        cols = 3
        col_w = USABLE_W / cols
        rows = [skill_list[i : i + cols] for i in range(0, len(skill_list), cols)]
        while len(rows[-1]) < cols:
            rows[-1].append("")
        table_data = [
            [Paragraph(f"• {s}", styles["skill_item"]) for s in row]
            for row in rows
        ]
        t = Table(table_data, colWidths=[col_w] * cols)
        t.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 2),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(t)
        story.append(Spacer(1, 4))

    # -------------------------------------------------------------- Experience
    if cv.get("experience"):
        story += _section("Professional Experience", styles)

        # Group consecutive entries by company so the logo appears only once per company
        from itertools import groupby
        for company, group in groupby(cv["experience"], key=lambda e: e.get("company", "")):
            entries = list(group)
            logo_path = _find_logo(company)

            # Logo once above all entries for this company
            if logo_path:
                story.append(_scaled_image(logo_path, height_cm=0.85))
                story.append(Spacer(1, 3))

            for exp in entries:
                story.append(Paragraph(exp.get("title", ""), styles["job_title"]))
                story.append(Paragraph(
                    f"{company}   ·   {exp.get('period', '')}",
                    styles["job_meta"],
                ))
                for bullet in exp.get("bullets", []):
                    story.append(Paragraph(f"• {bullet}", styles["bullet"]))
                story.append(Spacer(1, 5))

    # --------------------------------------------------------------- Education
    if cv.get("education"):
        story += _section("Education", styles)
        for edu in cv["education"]:
            story.append(Paragraph(edu.get("degree", ""), styles["edu_main"]))
            sub = f"{edu.get('institution', '')}   ·   {edu.get('year', '')}"
            story.append(Paragraph(sub, styles["edu_sub"]))
            story.append(Spacer(1, 3))

    # --------------------------------------------------------- Certifications
    if cv.get("certifications"):
        story += _section("Certifications", styles)
        for cert in cv["certifications"]:
            story.append(Paragraph(f"• {cert}", styles["bullet"]))
        story.append(Spacer(1, 4))

    # --------------------------------------------------------------- Languages
    if cv.get("languages"):
        story += _section("Languages", styles)
        story.append(Paragraph("  |  ".join(cv["languages"]), styles["skill_item"]))

    doc.build(story)
    print(f"    [cv] Saved PDF -> {output_path.resolve()}")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def generate_cvs_for_jobs(jobs: list[dict], profile: dict, page, limit: int = 3) -> dict:
    """For each of the first `limit` jobs, scrape description, generate and save a tailored CV PDF.
    Returns a dict mapping job URL -> PDF Path for successfully generated CVs."""
    CVS_DIR.mkdir(parents=True, exist_ok=True)
    target_jobs = jobs[:limit]
    results: dict = {}

    print(f"\n{'=' * 60}")
    print(f"CV Generator — processing {len(target_jobs)} job(s)")
    print(f"Output dir: {CVS_DIR.resolve()}")
    print("=" * 60)

    next_idx = len(list(CVS_DIR.glob("cv_*.pdf"))) + 1
    for i, job in enumerate(target_jobs, start=next_idx):
        filename = f"cv_{i:02d}.pdf"
        output_path = CVS_DIR / filename

        print(f"\n[{i}/{len(target_jobs)}] {job['title']} @ {job['company']}")

        print("    Fetching job description...")
        description = fetch_job_description(page, job["url"], job.get("description"))
        if description:
            print(f"    Description: {len(description)} chars")
        else:
            print("    Description: (empty - proceeding with title/company only)")

        print("    Calling Claude to tailor CV...")
        try:
            tailored_cv = generate_tailored_cv(profile, job, description)
        except ValueError as exc:
            if str(exc).startswith("JOB_MISMATCH"):
                print(f"    [skip] Not a match — {str(exc)[13:]}")
            else:
                print(f"    [error] Claude generation failed: {exc}")
            continue
        except Exception as exc:
            print(f"    [error] Claude generation failed: {exc}")
            continue

        print("    Rendering PDF...")
        try:
            render_cv_pdf(tailored_cv, profile, job, output_path)
            results[job["url"]] = output_path
        except Exception as exc:
            print(f"    [error] PDF render failed: {exc}")
            continue

        time.sleep(1.5)  # polite pause between API calls

    print(f"\n[cv] Done. {len(results)}/{len(target_jobs)} CV(s) saved to {CVS_DIR.resolve()}")
    return results
