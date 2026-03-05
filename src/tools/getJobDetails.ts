// src/tools/getJobDetails.ts
import { BrowserManager } from "../browser/BrowserManager.js";

type GetJobDetailsArgs = {
  url: string;
};

export async function getJobDetailsTool(args: GetJobDetailsArgs, browser: BrowserManager) {
  try {
    const page = await browser.goto(args.url);

    // Try common job description selectors in order of specificity
    const selectors = [
      ".job-description",
      ".job-details",
      "[data-testid='job-description']",
      ".description__text",
      ".jobsearch-jobDescriptionSection",
      "article",
      "main",
    ];

    let description = "";
    for (const sel of selectors) {
      try {
        const el = page.locator(sel).first();
        if (await el.count() > 0) {
          description = await el.innerText({ timeout: 3000 });
          if (description.length > 100) break;
        }
      } catch { /* try next */ }
    }

    if (!description) {
      description = await page.locator("body").innerText({ timeout: 5000 }).catch(() => "");
    }

    return {
      content: [{
        type: "text",
        text: JSON.stringify({
          url:         page.url(),
          title:       await page.title(),
          description: description.slice(0, 8000),
          apply_url:   page.url(),
        }, null, 2),
      }],
    };
  } catch (e: any) {
    return {
      content: [{ type: "text", text: `Error scraping job details: ${e.message}` }],
      isError: true,
    };
  }
}
