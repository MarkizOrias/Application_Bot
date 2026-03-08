# Application Bot

An automated job-application pipeline that scrapes LinkedIn for relevant listings, then uses the **Anthropic Claude API** to generate a tailor-made CV in PDF format for each position — all driven by a single source-of-truth profile.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
  - [1. Anthropic API Key](#1-anthropic-api-key)
  - [2. Fill your CV — base.md](#2-fill-your-cv--basemd)
  - [3. Update profile.json via setup script](#3-update-profilejson-via-setup-script)
  - [4. Add media assets](#4-add-media-assets)
- [Running the Bot](#running-the-bot)
- [Output](#output)
- [Workflow Diagram](#workflow-diagram)
- [Customisation](#customisation)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    linkedin_scraper.py                  │
│                                                         │
│  1. Launches Chrome with CDP (remote debugging)         │
│  2. Searches LinkedIn for each role in profile.json     │
│  3. Collects up to JOBS_LIMIT job cards                 │
│  4. Filters out excluded companies / keywords           │
│  5. Saves all listings → output/linkedin_listings.xlsx  │
│                                                         │
│  For each job (up to JOBS_LIMIT):                       │
│     └─► cv_generator.py                                 │
│           ├─ Navigates to job URL, expands description  │
│           ├─ Calls Claude (claude-opus-4-6) with:       │
│           │    • config/profile.json  (master CV data)  │
│           │    • Job description text                   │
│           ├─ Claude returns tailored CV as JSON         │
│           └─ Renders PDF → output/cvs/<company>_<role>  │
└─────────────────────────────────────────────────────────┘
```

**Data flow:**

```
config/base.md          ← Your real CV in Markdown (source of truth)
      │
      ▼
setup_profile.py        ← Parses base.md, writes structured data into
      │                    config/profile.json
      ▼
config/profile.json     ← Machine-readable profile: personal info,
      │                    preferences, full CV content
      │
      ├──► linkedin_scraper.py  ──► output/linkedin_listings_<ts>.xlsx
      │
      └──► cv_generator.py
                │
                ├── Playwright: fetches live job description
                ├── Claude API: generates tailored CV JSON
                └── ReportLab: renders PDF with photo + company logos
                         └──► output/cvs/cv_<n>_<company>_<title>.pdf
```

---

## Project Structure

```
application_bot/
├── config/
│   ├── base.md            # Your master CV in Markdown — edit this
│   └── profile.json       # Machine-readable profile (auto-generated via setup_profile.py)
├── media/
│   ├── Photo.png          # Your profile photo (used in CV header)
│   └── <Company>.png      # Employer logos (matched by company name)
├── output/
│   ├── linkedin_listings_<timestamp>.xlsx
│   └── cvs/
│       └── cv_<n>_<company>_<title>.pdf
├── linkedin_scraper.py    # Phase 1: scrape + Phase 2 trigger
├── cv_generator.py        # Phase 2: description fetch + Claude + PDF
├── setup_profile.py       # One-time profile configurator
├── requirements.txt
├── .env                   # API key (never commit)
└── README.md
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | `python --version` |
| Google Chrome | Latest | Must be installed at default path |
| Anthropic API key | — | [console.anthropic.com](https://console.anthropic.com) |

---

## Installation

### 1. Clone and enter the repo

```bash
git clone <repo-url>
cd application_bot
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright browser bindings

```bash
playwright install chromium
```

> Playwright manages its own browser binaries separately from your system Chrome.
> The scraper connects to **your installed Chrome** via CDP; Playwright chromium is only used as a fallback.

---

## Configuration

### 1. Anthropic API Key

Create a `.env` file in the project root (or update via the setup script):

```
API_KEY = "sk-ant-api03-..."
```

> **Never commit `.env` to version control.** It is already listed in `.gitignore`.

---

### 2. Fill your CV — `config/base.md`

`base.md` is the **single source of truth** for your CV content. Write it in standard Markdown following this structure:

```markdown
# Your Full Name

email | phone | linkedin | github | portfolio

## SUMMARY

2–3 sentences describing your professional background.

## SKILLS

**Operations & Finance:** Skill 1, Skill 2, Skill 3
**Technical:** Python, SQL, Git
**Methodology:** Agile, Process Automation

## EXPERIENCE

### Job Title — Company Name (Month Year – Month Year)

_City, Country_

- Achievement or responsibility 1
- Achievement or responsibility 2

### Next Job Title — Company Name (Month Year – Month Year)

_City, Country_

- Achievement or responsibility

## EDUCATION

**Degree Name, Major**
University Name | Year – Year

## CERTIFICATIONS

- Certification Name — Issuer (Year)
```

**Tips for good CV output:**
- Keep bullet points to 1–2 lines; Claude will tailor them to each job
- Use consistent date format: `Month Year – Month Year`
- Skill group names become keys in `profile.json` — use descriptive category names

---

### 3. Update profile.json via setup script

Run the interactive configurator after editing `base.md`:

```bash
python setup_profile.py
```

The script will:

1. Ask you to confirm / update **personal details** (name, email, phone, links, location)
2. Set **work authorisation** per region (PL, EU, CH, US)
3. Configure **job preferences** — target roles, min salary, excluded companies, remote preference
4. **Parse `base.md` automatically** and import summary, skills, experience, education, and certifications into `profile.json`
5. Optionally update your **Anthropic API key** in `.env`
6. Show guidance on **media assets**

> You can re-run `setup_profile.py` at any time. It only saves when you choose **Save & exit**.

---

### 4. Add media assets

Place PNG files in the `media/` directory:

| File | Purpose |
|---|---|
| `Photo.png` | Your profile photo — displayed top-left in every generated CV |
| `<Company Name>.png` | Employer logo — displayed above that company's experience entries |

**Logo matching** is fuzzy: `"UBS Switzerland AG.png"` will match any company named `"UBS Switzerland AG"` in your experience. The first word of the filename is also tried as a fallback (so `"State Street.png"` matches `"State Street Bank International GmbH"`).

Recommended photo dimensions: **300 × 375 px** (4:5 portrait ratio).

---

## Running the Bot

```bash
python linkedin_scraper.py
```

**What happens step by step:**

1. All existing Chrome processes are killed and a fresh instance is launched with CDP on port `9222`
2. The script connects to Chrome via Playwright CDP
3. If LinkedIn requires login, you are prompted to log in manually in the browser, then press Enter
4. For each role listed in `preferences.roles`, a LinkedIn jobs search URL is built and opened
5. Job cards are scraped until `JOBS_LIMIT` is reached (default: `3` for testing — change in `linkedin_scraper.py` line `345`)
6. Each job is checked against `exclude_companies` and `exclude_keywords`; skipped jobs are logged
7. For each accepted job, `cv_generator.py` is called:
   - The bot navigates to the job's URL and expands the "About the job" section
   - The full job description text is extracted
   - Claude (`claude-opus-4-6`) receives your master CV + the job description and returns a tailored CV as JSON
   - ReportLab renders the JSON into a professional A4 PDF with your photo and employer logos
8. A formatted Excel file with all listings is saved to `output/`

> **To run in production mode** (more than 3 jobs), change `JOBS_LIMIT = 3` to your desired number in `linkedin_scraper.py`.

---

## Output

| File | Description |
|---|---|
| `output/linkedin_listings_<timestamp>.xlsx` | All scraped job listings with hyperlinks, filterable in Excel |
| `output/cvs/cv_<n>_<company>_<title>.pdf` | Tailored A4 CV for each job |

**PDF layout:**
- Header: profile photo (left) · name, contact info, clickable links (right)
- Professional Summary — rewritten by Claude for this specific role
- Core Skills — 3-column grid, most relevant skills first
- Professional Experience — company logo above each employer group, tailored bullet points
- Education · Certifications · Languages

---

## Workflow Diagram

```
You                  setup_profile.py         linkedin_scraper.py        cv_generator.py
 │                          │                         │                        │
 ├─ edit base.md ──────────►│                         │                        │
 ├─ run setup ─────────────►│                         │                        │
 │                          ├─ parse base.md           │                        │
 │                          ├─ prompt review           │                        │
 │                          └─ write profile.json ────►│                        │
 │                                                     │                        │
 ├─ run scraper ───────────────────────────────────────►                        │
 │                                                     ├─ launch Chrome         │
 │                                                     ├─ search LinkedIn       │
 │                                                     ├─ scrape job cards      │
 │                                                     ├─ filter jobs           │
 │                                                     ├─ save Excel            │
 │                                                     └─ for each job ────────►│
 │                                                                              ├─ fetch description
 │                                                                              ├─ call Claude API
 │                                                                              └─ render PDF
 │
 └─ review output/cvs/*.pdf
```

---

## Customisation

| What | Where | How |
|---|---|---|
| Number of jobs to process | `linkedin_scraper.py` line `345` | Change `JOBS_LIMIT = 3` |
| Target roles | `config/profile.json` → `preferences.roles` | Edit list or use `setup_profile.py` |
| Excluded companies | `config/profile.json` → `preferences.exclude_companies` | Add/remove company names |
| Easy Apply only | `config/profile.json` → `job_sources.linkedin.easy_apply_only` | Set `true` / `false` |
| CV font / colours | `cv_generator.py` → top-level constants | Change `BRAND_BLUE`, font sizes in `_build_styles()` |
| Claude model | `cv_generator.py` → `generate_tailored_cv()` | Change `model="claude-opus-4-6"` |
| Photo size in CV | `cv_generator.py` → `render_cv_pdf()` | Change `height_cm=3.2` in `_scaled_image(photo_path, ...)` |

---

## Troubleshooting

**Chrome won't connect**
- Ensure Chrome is installed at `C:\Program Files\Google\Chrome\Application\chrome.exe`
- Check that port `9222` is not blocked by a firewall or used by another process
- If the script crashes mid-run, manually close all Chrome windows and retry

**LinkedIn asks for login every run**
- The script uses a temporary Chrome profile at `C:\Temp\chrome-debug`
- Log in once; Chrome will persist the session in that directory across runs

**Job description is empty**
- LinkedIn occasionally changes its DOM structure; check the selectors in `cv_generator.py` → `fetch_job_description()`
- The bot will still generate a CV using only the job title and company name

**Claude returns invalid JSON**
- Rare but possible; the bot logs the error and continues with the next job
- Try re-running — the API response is non-deterministic

**PDF looks misaligned / logos wrong**
- Ensure logo PNG filenames match company names in `profile.json` (case-insensitive partial match)
- Photo should be a clean portrait image without heavy transparency around the edges
