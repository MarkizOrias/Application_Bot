// src/tools/getJobDetails.ts
// Navigates to a job posting URL and extracts the full job description,
// company name, job title, and the direct apply URL.

import { BrowserManager } from "../browser/BrowserManager.js";

type GetJobDetailsArgs = {
  url: string;
};

export async function getJobDetailsTool(args: GetJobDetailsArgs, browser: BrowserManager) {
  const page = await browser.goto(args.url);

  let title       = "";
  let company     = "";
  let description = "";
  let applyUrl    = args.url;

  const url = args.url;

  if (url.includes("linkedin.com/jobs")) {
    // ── LinkedIn job posting ────────────────────────────────────────────────
    // Wait for the job title to load
    await page.waitForSelector(
      ".job-details-jobs-unified-top-card__job-title, h1.t-24",
      { timeout: 8000 }
    ).catch(() => {});

    title   = await browser.scrapeText(page,
      ".job-details-jobs-unified-top-card__job-title h1, h1.t-24");
    company = await browser.scrapeText(page,
      ".job-details-jobs-unified-top-card__company-name a, .jobs-unified-top-card__company-name");
    description = await browser.scrapeText(page,
      ".jobs-description__content .jobs-description-content__text, .job-details-jobs-unified-top-card__primary-description");
    applyUrl = args.url;  // LinkedIn Easy Apply stays on the same page

  } else if (url.includes("greenhouse.io")) {
    // ── Greenhouse board ────────────────────────────────────────────────────
    title       = await browser.scrapeText(page, "h1.app-title, h1");
    company     = await browser.scrapeText(page, ".company-name, header .employer");
    description = await browser.scrapeText(page, "#content, .job-post-wrapper, .job__description");
    applyUrl    = args.url;  // Apply form is inline on the same page

  } else if (url.includes("lever.co")) {
    // ── Lever board ─────────────────────────────────────────────────────────
    title       = await browser.scrapeText(page, ".posting-headline h2, h2.posting-name");
    company     = await browser.scrapeText(page, ".main-header-logo img[alt]")
                  .then(() => page.locator('.main-header-logo img').getAttribute('alt').catch(() => ""))
                  .catch(() => "");
    description = await browser.scrapeText(page, ".posting-description, .section-wrapper");
    applyUrl    = args.url;

  } else if (url.includes("weworkremotely.com")) {
    // ── We Work Remotely listing ─────────────────────────────────────────────
    title       = await browser.scrapeText(page, "h1.listing-header__title, h1");
    company     = await browser.scrapeText(page, ".company a, .listing-header__company");
    description = await browser.scrapeText(page, ".listing-container, [class*='description']");

    // Look for external apply link
    const applyBtn = page.locator('a:has-text("Apply for this Job"), a:has-text("Apply Now")').first();
    if (await applyBtn.count() > 0) {
      const href = await applyBtn.getAttribute("href");
      if (href) applyUrl = href.startsWith("http") ? href : `https://weworkremotely.com${href}`;
    }

  } else {
    // ── Generic fallback ────────────────────────────────────────────────────
    title = await page.title();
    description = await browser.scrapeText(page,
      "main, article, .job-description, #job-description, [class*='description'], [class*='content']");
    company = await browser.scrapeText(page,
      "[class*='company'], [class*='employer'], [itemprop='hiringOrganization'] [itemprop='name']");

    // Look for a generic Apply button pointing elsewhere
    const applyBtn = page.locator(
      'a:has-text("Apply"), a:has-text("Apply Now"), a:has-text("Apply for this job")'
    ).first();
    if (await applyBtn.count() > 0) {
      const href = await applyBtn.getAttribute("href");
      if (href) applyUrl = href.startsWith("http") ? href : new URL(href, args.url).href;
    }
  }

  return {
    content: [{
      type: "text",
      text: JSON.stringify({
        title:       title.trim(),
        company:     company.trim(),
        description: description.trim().slice(0, 6000),
        apply_url:   applyUrl,
        source_url:  args.url,
      }, null, 2),
    }],
  };
}
