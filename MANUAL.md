# Job Application Agent — Complete Execution Manual

## Your Role vs. The Agent's Role

| You do (once)                       | Agent does (every run)              |
| ----------------------------------- | ----------------------------------- |
| Install dependencies                | Search job boards                   |
| Point Playwright at your Chrome     | Fetch & parse each JD               |
| Drop your base CV in /cvs/base.md   | Tailor CV per job                   |
| Fill config.json with your profile  | Auto-fill application forms         |
| Run `npm start` and approve batches | Detect CAPTCHAs and pause for you   |
| Solve CAPTCHAs when notified        | Log everything to local SQLite      |
| Review the tracker spreadsheet      | Resume after you signal it's solved |

---

## Part 1 — Best Target Websites (Ranked by Success Rate)

### Tier 1 — Highest ROI (Start Here)

**1. LinkedIn Easy Apply**

- Why: Single standardized flow. "Easy Apply" jobs skip external ATS entirely.
- Automation difficulty: Low — Playwright handles it cleanly.
- Success rate: High (your profile is already there, recruiters actively source here).
- Target: Filter `f_AL=true` (Easy Apply) + `f_WT=2` (Remote) in the URL.

**2. Greenhouse (via company career pages)**

- Why: Consistent HTML form structure across ALL companies using it. One adapter works everywhere.
- Automation difficulty: Low-Medium.
- Success rate: Very high — direct company applications rank above aggregator ones.
- How to find: Search `site:boards.greenhouse.io [your role]` on Google.

**3. Lever**

- Why: Same as Greenhouse — standardised. Used by many mid-size tech companies.
- Automation difficulty: Low-Medium.
- URL pattern: `jobs.lever.co/[company]`

**4. We Work Remotely (weworkremotely.com)**

- Why: Curated remote-only jobs. Less competition than LinkedIn. High signal-to-noise.
- Automation difficulty: Low — clean HTML, no login required to browse.
- Submissions redirect to company sites (Greenhouse/Lever mostly).

**5. Remotive.com**

- Why: API-accessible (no scraping needed), remote-only, good for tech/product/design roles.
- API: `https://remotive.com/api/remote-jobs?category=software-dev`
- Automation difficulty: Minimal — it's a clean REST API.

### Tier 2 — Secondary Targets

**6. Adzuna** — Has a real API. Good aggregator for volume.
**7. Wellfound (formerly AngelList)** — Best for startups. Requires login, has its own form flow.
**8. Himalayas.app** — Newer, curated, scraper-friendly, high quality remote roles.

### Avoid (for now)

- **Indeed** — Extremely aggressive bot detection, frequent CAPTCHAs, inconsistent form structure.
- **Workday** — Custom per-company, iframe hell, breaks constantly. Phase 3 at earliest.
- **ZipRecruiter** — High noise, low remote quality.

---

## Part 2 — System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      YOUR MACHINE                           │
│                                                             │
│  ┌──────────────┐     stdio      ┌────────────────────────┐ │
│  │    Claude    │◄──────────────►│     MCP Server         │ │
│  │  (Claude.ai  │                │   (Node.js, local)     │ │
│  │   Desktop)   │                └──────────┬─────────────┘ │
│  └──────────────┘                           │               │
│                                    ┌────────┴──────────┐    │
│                                    │                   │    │
│                            ┌───────▼──────┐   ┌───────▼──┐ │
│                            │  Playwright  │   │  SQLite  │ │
│                            │ (headed,your │   │   DB     │ │
│                            │  Chrome)     │   │          │ │
│                            └───────┬──────┘   └──────────┘ │
│                                    │                        │
│                         ┌──────────▼──────────┐            │
│                         │  Your logged-in      │            │
│                         │  Chrome profile      │            │
│                         │  (LinkedIn, etc.)    │            │
│                         └─────────────────────┘            │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Notifier: macOS/Windows native desktop notification │   │
│  │  → "CAPTCHA needed for [Company]. Click to resolve." │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Orchestration Flow (Per Job)

```
Claude
  │
  ├─1─► search_jobs(query, sources)
  │        └─► Returns list: [{title, company, url, platform}]
  │
  ├─2─► get_job_details(url)
  │        └─► Returns: full JD text, required skills, apply_url
  │
  ├─3─► [Claude evaluates fit vs your profile — skips weak matches]
  │
  ├─4─► tailor_cv(job_description, title, company)
  │        └─► Returns: cv_file_path (.docx), keyword_matches[]
  │
  ├─5─► [Human review gate — Claude shows you tailored CV summary + asks approval]
  │        └─► You: "yes" / "skip" / "tweak: [instruction]"
  │
  ├─6─► submit_application(apply_url, platform, cv_file_path)
  │        │
  │        ├─► [No CAPTCHA] → Form filled → Submitted → logged as "submitted" ✓
  │        │
  │        └─► [CAPTCHA detected]
  │                 │
  │                 ├─► Browser pauses on CAPTCHA page (stays open, visible)
  │                 ├─► Desktop notification sent to you
  │                 ├─► DB status → "captcha_hold"
  │                 └─► Claude polls check_captcha_status() every 30s
  │                              │
  │                              └─► You solve CAPTCHA in the browser window
  │                                  → Click "Done" in terminal / notification
  │                                  → Agent resumes from exact point
  │
  └─7─► list_applications() → Summary of session
```

---

## Part 3 — Step-by-Step Action Plan

### STEP 1 — Prerequisites (One-time, ~20 min)

**1.1 Install Node.js**

```bash
# Check if you have it
node --version   # needs v18+

# If not: https://nodejs.org (download LTS)
```

**1.2 Install Claude Desktop**
Download from https://claude.ai/download — this is what runs the MCP server locally.

**1.3 Find your Chrome profile path**

_macOS:_

```bash
# Default profile
ls ~/Library/Application\ Support/Google/Chrome/Default

# If you use multiple profiles, list them:
ls ~/Library/Application\ Support/Google/Chrome/
# Look for: Default, Profile 1, Profile 2, etc.
```

_Windows:_

```
C:\Users\[YourName]\AppData\Local\Google\Chrome\User Data\Default
```

_Linux:_

```bash
~/.config/google-chrome/Default
```

Write this path down — you'll need it in Step 3.
C:\Users\Georgi\AppData\Local\Google\Chrome\User Data\Default

**1.4 Set up the project**

Clone the repository, install dependencies, and compile TypeScript:

```bash
git clone https://github.com/MarkizOrias/Application_Bot.git
cd Application_Bot
npm install
npm run build        # compiles src/ → dist/
```

The compiled entry point will be at `dist/index.js` — that is the file you point Claude Desktop to in Step 4.

---

### STEP 2 — Set Up Your Base CV (~30 min, do this carefully)

Create `cvs/base.md` — this is the master CV the agent rewrites per job.

**Format it like this:**

```markdown
# [Your Name]

[email] | [phone] | [LinkedIn URL] | [GitHub URL] | [Location: Remote / City]

## SUMMARY

2-3 sentences. Write in third person. Include your top 3 skills explicitly.

## SKILLS

**Languages:** TypeScript, Python, Go
**Frameworks:** React, Node.js, FastAPI
**Infrastructure:** AWS, Docker, Kubernetes, Terraform
**Other:** REST APIs, GraphQL, CI/CD, Agile

## EXPERIENCE

### Senior Software Engineer — Acme Corp (Jan 2021 – Present)

- [Action verb] + [what you did] + [measurable outcome]
- Built distributed data pipeline processing 50M events/day using Kafka + Go
- Reduced deployment time by 60% by introducing GitHub Actions CI/CD

### [Previous Role] — [Company] ([dates])

- ...

## EDUCATION

BSc Computer Science — [University] (2018)

## CERTIFICATIONS

- AWS Solutions Architect Associate (2023)
```

**Why this format matters:** The agent does keyword injection at the bullet level. Well-structured bullets with measurable outcomes are much easier to tailor than prose paragraphs.

---

### STEP 3 — Fill Your Profile Config (~15 min)

Create `config/profile.json`:

```json
{
  "personal": {
    "full_name": "Jane Smith",
    "email": "jane@email.com",
    "phone": "+44 7911 123456",
    "linkedin": "https://linkedin.com/in/janesmith",
    "github": "https://github.com/janesmith",
    "portfolio": "https://janesmith.dev",
    "location": "London, UK (Remote)",
    "timezone": "GMT"
  },
  "work_authorization": {
    "uk": "Citizen",
    "eu": "Not authorized",
    "us": "Not authorized"
  },
  "preferences": {
    "roles": ["Senior Software Engineer", "Staff Engineer", "Backend Engineer"],
    "min_salary_usd": 80000,
    "exclude_companies": ["Amazon", "Accenture"],
    "require_remote": true,
    "max_applications_per_session": 15,
    "exclude_keywords": ["10+ years software engineering", "on-site required", "Java required"],
    "preferred_keywords": ["fintech", "automation", "Python", "Agile"]
  },
  "browser": {
    "chrome_profile_path": "C:\\Users\\YourName\\AppData\\Local\\Google\\Chrome\\User Data\\Default",
    "headless": false,
    "slow_mo_ms": 120
  },
  "job_sources": {
    "linkedin": { "enabled": true, "easy_apply_only": true },
    "greenhouse": { "enabled": true },
    "lever": { "enabled": true },
    "remotive": { "enabled": true },
    "weworkremotely": { "enabled": true },
    "himalayas": { "enabled": true }
  },
  "notifications": {
    "platform": "auto",
    "captcha_timeout_minutes": 10
  }
}
```

> **Windows path format:** Use double backslashes in the JSON string: `C:\\Users\\YourName\\...`
> **macOS path format:** Use the forward-slash path as-is: `/Users/YourName/Library/Application Support/Google/Chrome/Default`

---

### STEP 4 — Build and Register the MCP Server with Claude Desktop (~10 min)

**4.1 Build the project first** (must do this before registering, and after every code change):

```bash
cd Application_Bot
npm run build
```

This compiles `src/` into `dist/`. The server entry point is `dist/index.js`.

**4.2 Register with Claude Desktop**

Open Claude Desktop → Settings → Developer → Edit Config.

Add to `claude_desktop_config.json`:

_Windows:_
```json
{
  "mcpServers": {
    "job-agent": {
      "command": "node",
      "args": ["C:\\Users\\Georgi\\Application_Bot\\dist\\index.js"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

_macOS / Linux:_
```json
{
  "mcpServers": {
    "job-agent": {
      "command": "node",
      "args": ["/Users/YourName/Application_Bot/dist/index.js"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

> The path must point to `dist/index.js` (the compiled output), **not** `src/index.js`.

Restart Claude Desktop. You should see the tool icon appear in the chat bar — hover over it to confirm "job-agent" tools are listed.

---

### STEP 5 — Log Into All Job Sites in Your Chrome Profile (One-time, ~10 min)

Open your regular Chrome (the profile you pointed to in config). Log in and stay logged in:

- [ ] linkedin.com — go to Jobs, confirm you're signed in
- [ ] wellfound.com — sign in
- [ ] himalayas.app — sign in (optional but helps track applied)

LinkedIn is the most important. The others (Greenhouse, Lever, Remotive, WWR) don't require login to apply — they just need your data filled in.

**Important:** After logging in, close Chrome completely before running the agent. Playwright needs exclusive access to the profile — two Chrome instances can't share the same profile simultaneously.

---

### STEP 6 — Run a Session

Open Claude Desktop and start with:

```
Search for remote [Senior Backend Engineer] roles across LinkedIn Easy Apply,
Remotive, We Work Remotely, and Greenhouse boards.
Filter for roles matching my profile in config.json.
For each strong match, tailor my CV and show me a summary before applying.
Max 10 applications this session.
```

Claude will:

1. Call `search_jobs` across all enabled sources
2. Call `get_job_details` on each promising result
3. Score each job against your profile (internally — it reasons about fit)
4. For each match: call `tailor_cv`, show you the tailored summary + keyword diff
5. Wait for your "yes / skip / tweak" per job (or you can say "auto-approve all")
6. Call `submit_application` — browser opens visibly and you watch it fill forms
7. If CAPTCHA: you get a desktop notification, browser stays on that page, you solve it, press Enter in terminal, agent continues

---

### STEP 7 — Monitor & Review

```bash
# See all applications logged today
sqlite3 data/applications.db \
  "SELECT company, role, status, submitted_at FROM applications ORDER BY created_at DESC LIMIT 20;"
```

Or ask Claude: _"Show me a summary of all applications from today's session."_

---

## Part 4 — CAPTCHA Handling In Detail

When Playwright detects a CAPTCHA (by checking for known CAPTCHA selectors or a sudden navigation block):

**What happens automatically:**

1. Browser freezes — does NOT close the tab
2. `node-notifier` fires a native desktop notification:
   > 🔒 **CAPTCHA Required**
   > _Spotify — Senior Backend Engineer_
   > Solve it in the Chrome window, then press **Enter** in the terminal.
3. DB status for this application → `captcha_hold`
4. Claude polls `check_captcha_status()` every 30 seconds
5. A 10-minute timeout begins (configurable)

**Your action:**

1. Click on the Chrome window the agent opened (it's still on the CAPTCHA page)
2. Solve the CAPTCHA normally (checkbox, image grid, etc.)
3. Press **Enter** in the terminal where the MCP server is running
4. Agent immediately resumes — fills remaining fields and submits

**Timeout scenario:** If you don't solve it within 10 minutes, the application is logged as `captcha_timeout` and the agent moves on to the next job. You can manually requeue it later.

---

## Part 5 — Maintenance & Ongoing Use

**Weekly:** Run a session with `max_applications_per_session: 20`. Review the tracker.

**When a site breaks:** Greenhouse and Lever are very stable. LinkedIn's Easy Apply HTML changes occasionally — check GitHub for community-maintained Playwright selectors.

**Improving results over time:** After a few sessions, look at which roles you approved vs. skipped. Refine `preferences` in config.json. Add `exclude_keywords: ["10+ years", "on-site required"]` to auto-skip obvious mismatches before Claude even surfaces them.

**CV tuning:** After 2 weeks, compare callback rates. If low, beef up the SKILLS and SUMMARY sections in `cvs/base.md` — those are the sections the agent rewrites most aggressively.
