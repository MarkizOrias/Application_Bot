# Application Bot — High-Level Workflow Description

## Overview

An end-to-end, AI-powered job application automation system that searches LinkedIn, generates tailored CVs and cover letters using Claude AI, and autonomously submits Easy Apply applications — all from a single configured candidate profile.

---

## System Components

### 1. Candidate Profile (`config/profile.json`)
Single source of truth for the candidate. Stores personal details, full CV data (experience, education, skills, certifications), job preferences (target roles, salary floor, excluded companies/keywords), and LinkedIn search configuration.

### 2. LinkedIn Scraper (`linkedin_scraper.py`)
- Launches Chrome with remote debugging (CDP) and attaches via Playwright
- Searches LinkedIn Jobs for each configured target role (remote, sorted by recency, Easy Apply filtered)
- Scrolls and extracts job cards: title, company, location, URL
- Enriches each card by clicking into the detail panel to capture the job description and apply-button type
- Filters out excluded companies and blacklisted keywords
- De-duplicates against the persistent tracker to skip already-applied jobs

### 3. CV Generator (`cv_generator.py`)
- Receives job + description for each scraped listing
- Calls **Claude Opus** to tailor the candidate's master CV: reorders skills, rewrites the summary, selects and highlights the most relevant experience bullets to match the specific job description
- Renders a professional, branded PDF CV using ReportLab (A4, LinkedIn-blue accents, headshot support)
- Performs a fit-check: if Claude determines the profile is a poor match, the job is logged to a mismatch log and skipped — no CV generated, no application submitted

### 4. Apply Bot (`apply_bot.py`)
- Navigates to the job URL and clicks the Easy Apply button
- Steps through the multi-page modal automatically (up to 12 steps)
- **File upload**: uploads the tailored CV PDF at the resume step
- **Form filling**: scrapes all unfilled fields (text, number, textarea, select, radio) from each modal step, sends them in a single batch to **Claude Haiku** with full candidate context, receives answers as JSON, and fills the DOM — handling React-controlled inputs, URN-format IDs, and toggle-style radio buttons
- **Spam prevention**: unchecks opt-in checkboxes (Follow, Featured Applicant, etc.)
- Detects stuck states and validation errors, closes the modal cleanly on failure
- Marks the application as submitted in the persistent tracker (Excel) with timestamp and CV path

### 5. Offline Application Generator (`generate_application.py`)
A standalone mode for manual job applications. Reads a job description from `config/job_description.md` and produces:
- **Tailored CV PDF** — Claude-optimised for the specific role
- **Cover Letter DOCX** — Claude Opus writes 3 professional paragraphs, rendered as a branded Word document
- **Career Form Filler TXT** — pre-formatted copy-paste data for manual application portals
- **Application Tracker entry** — appended to `cv/tracker.xlsx`

### 6. Persistent Tracking
- **`output/linkedin_tracker.xlsx`** — rows per job: title, company, URL (hyperlinked), easy_apply flag, applied status, timestamp, CV path. LinkedIn-blue branded header, frozen pane.
- **`output/mismatch_log.json`** — jobs Claude determined were not a profile fit, with reason and timestamp, preventing re-evaluation on future runs.

---

## End-to-End Flow

```
Profile JSON
    │
    ▼
LinkedIn Search (per role)
    │  scrape + enrich job cards
    ▼
Filter & De-duplicate
    │  exclude companies/keywords, skip already applied/mismatched
    ▼
Claude Opus — CV Tailoring + Fit Check
    │  generate tailored CV dict  ──── mismatch? ──► log & skip
    ▼
ReportLab — Render PDF CV
    │
    ▼
LinkedIn Easy Apply Modal
    │  upload CV → Claude Haiku fills each form step → submit
    ▼
Tracker Update (Excel)
    │  mark applied, record timestamp + CV path
    ▼
Session Summary
```

---

## AI Usage

| Step | Model | Purpose |
|------|-------|---------|
| CV tailoring & fit-check | Claude Opus 4.6 | Rewrite CV to match JD; determine if candidate is a good fit |
| Cover letter (offline mode) | Claude Opus 4.6 | Write 3-paragraph tailored cover letter |
| Easy Apply form filling | Claude Haiku 4.5 | Answer all modal form fields in a single batch call |

---

## Key Design Decisions

- **One card at a time**: scrape → tailor → apply is processed per job, not in bulk batches, so failures don't block the session
- **Persistent state**: tracker + mismatch log survive between sessions; no duplicate applications
- **Session limit**: configurable max applications per run protects against rate-limiting and unintended mass-apply
- **Graceful degradation**: modal errors, stuck states, and validation failures close cleanly without crashing the session
- **Profile-driven**: all preferences (roles, salary, exclusions, work authorisation) live in one JSON file; no code changes needed to retarget searches
