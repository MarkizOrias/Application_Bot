// src/tools/searchJobs.ts
// Aggregates job listings from multiple sources.
// Remotive & Adzuna: clean REST APIs (no scraping needed).
// LinkedIn: URL-based search with Playwright (your session, already logged in).
// We Work Remotely & Himalayas: lightweight HTML scraping.

import axios from "axios";
import { BrowserManager } from "../browser/BrowserManager.js";

type SearchArgs = {
  query: string;
  max_results?: number;
  sources?: string[];
};

type JobListing = {
  title: string;
  company: string;
  url: string;
  platform: string;
  snippet: string;
  tags?: string[];
};

export async function searchJobsTool(args: SearchArgs, browser: BrowserManager) {
  const { query, max_results = 10, sources = ["remotive", "weworkremotely", "linkedin", "himalayas"] } = args;
  const results: JobListing[] = [];

  const fetchers: Record<string, () => Promise<JobListing[]>> = {
    remotive:       () => fetchRemotive(query, max_results),
    weworkremotely: () => fetchWWR(query, max_results),
    linkedin:       () => fetchLinkedIn(query, max_results, browser),
    himalayas:      () => fetchHimalayas(query, max_results),
    adzuna:         () => fetchAdzuna(query, max_results),
  };

  await Promise.allSettled(
    sources.map(async (src) => {
      if (fetchers[src]) {
        const jobs = await fetchers[src]().catch((e) => {
          console.error(`[search] ${src} failed: ${e.message}`);
          return [] as JobListing[];
        });
        results.push(...jobs);
      }
    })
  );

  // Deduplicate by URL
  const seen = new Set<string>();
  const unique = results.filter((j) => {
    if (seen.has(j.url)) return false;
    seen.add(j.url);
    return true;
  });

  return {
    content: [{
      type: "text",
      text: JSON.stringify({ total: unique.length, jobs: unique }, null, 2),
    }],
  };
}

// ── Remotive API (free, no key required) ─────────────────────────────────────
async function fetchRemotive(query: string, limit: number): Promise<JobListing[]> {
  const res = await axios.get("https://remotive.com/api/remote-jobs", {
    params: { search: query, limit },
    timeout: 10_000,
  });
  return res.data.jobs.slice(0, limit).map((j: any) => ({
    title:    j.title,
    company:  j.company_name,
    url:      j.url,
    platform: "remotive",
    snippet:  j.description?.replace(/<[^>]+>/g, "").slice(0, 200) ?? "",
    tags:     j.tags,
  }));
}

// ── We Work Remotely (simple HTML, no auth) ──────────────────────────────────
async function fetchWWR(query: string, limit: number): Promise<JobListing[]> {
  const url = `https://weworkremotely.com/remote-jobs/search?term=${encodeURIComponent(query)}`;
  const res = await axios.get(url, {
    headers: { "User-Agent": "Mozilla/5.0" },
    timeout: 10_000,
  });

  const matches = [...res.data.matchAll(/<li class="feature"[\s\S]*?<a href="(.*?)"[\s\S]*?<span class="title">(.*?)<\/span>[\s\S]*?<span class="company">(.*?)<\/span>/g)];

  return matches.slice(0, limit).map(([, href, title, company]) => ({
    title:    title.trim(),
    company:  company.trim(),
    url:      `https://weworkremotely.com${href}`,
    platform: "weworkremotely",
    snippet:  "",
  }));
}

// ── LinkedIn Easy Apply search (uses the shared logged-in BrowserManager) ────
// Constructs a URL with remote + Easy Apply filters, scrapes listings.
async function fetchLinkedIn(query: string, limit: number, browser: BrowserManager): Promise<JobListing[]> {
  // f_WT=2 → remote  |  f_AL=true → Easy Apply only  |  sortBy=DD → most recent
  const searchUrl = `https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(query)}&f_WT=2&f_AL=true&sortBy=DD`;

  const page = await browser.goto(searchUrl);
  await page.waitForTimeout(2000);

  const jobs = await page.evaluate((lim) => {
    const cards = [...document.querySelectorAll(".jobs-search__results-list li")].slice(0, lim);
    return cards.map((card) => ({
      title:    card.querySelector(".base-search-card__title")?.textContent?.trim() ?? "",
      company:  card.querySelector(".base-search-card__subtitle")?.textContent?.trim() ?? "",
      url:      (card.querySelector("a.base-card__full-link") as HTMLAnchorElement)?.href ?? "",
      platform: "linkedin",
      snippet:  "",
    }));
  }, limit);

  return jobs.filter((j) => j.url);
}

// ── Himalayas (JSON API, no key) ──────────────────────────────────────────────
async function fetchHimalayas(query: string, limit: number): Promise<JobListing[]> {
  const res = await axios.get(`https://himalayas.app/jobs/api`, {
    params: { q: query, limit },
    timeout: 10_000,
  });
  return (res.data.jobs ?? []).slice(0, limit).map((j: any) => ({
    title:    j.title,
    company:  j.companyName,
    url:      j.applicationLink ?? j.url,
    platform: "himalayas",
    snippet:  j.description?.slice(0, 200) ?? "",
    tags:     j.skills,
  }));
}

// ── Adzuna (requires free API key — sign up at api.adzuna.com) ───────────────
async function fetchAdzuna(query: string, limit: number): Promise<JobListing[]> {
  const appId  = process.env.ADZUNA_APP_ID;
  const appKey = process.env.ADZUNA_APP_KEY;
  if (!appId || !appKey) return [];

  const res = await axios.get(`https://api.adzuna.com/v1/api/jobs/gb/search/1`, {
    params: {
      app_id:           appId,
      app_key:          appKey,
      results_per_page: limit,
      what:             query,
      where:            "remote",
    },
    timeout: 10_000,
  });
  return (res.data.results ?? []).map((j: any) => ({
    title:    j.title,
    company:  j.company.display_name,
    url:      j.redirect_url,
    platform: "adzuna",
    snippet:  j.description?.slice(0, 200) ?? "",
  }));
}
