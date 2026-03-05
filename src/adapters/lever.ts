// src/adapters/lever.ts
// Lever job boards: jobs.lever.co/[company]/[job-id]
// Consistent form structure: name, email, phone, resume, links, cover letter.

import { Page }           from "playwright";
import { BrowserManager } from "../browser/BrowserManager.js";

export async function leverAdapter(
  page: Page,
  browser: BrowserManager,
  profile: any,
  cvFilePath: string,
  coverLetter?: string,
): Promise<{ success: boolean; captchaDetected?: boolean; error?: string }> {
  try {
    const fill = async (sel: string, val: string) => {
      if (!val) return;
      const el = page.locator(sel).first();
      if (await el.count() > 0) { await el.fill(val); await browser.humanDelay(150, 300); }
    };

    await fill('[name="name"]',                    profile.full_name);
    await fill('[name="email"]',                   profile.email);
    await fill('[name="phone"]',                   profile.phone);
    await fill('[name="org"]',                     "");                // current company, optional
    await fill('[name="urls[LinkedIn]"]',           profile.linkedin);
    await fill('[name="urls[GitHub]"]',             profile.github);
    await fill('[name="urls[Portfolio]"]',          profile.portfolio);

    // Resume upload
    const fileInput = page.locator('input[type="file"]').first();
    if (await fileInput.count() > 0) {
      await fileInput.setInputFiles(cvFilePath);
      await browser.humanDelay(1000, 1800);
    }

    // Cover letter
    if (coverLetter) {
      const clField = page.locator('textarea[name="comments"]').first();
      if (await clField.count() > 0) await clField.fill(coverLetter);
    }

    if (await browser.detectCaptcha(page)) return { success: false, captchaDetected: true };

    const submitBtn = page.locator('[type="submit"], button:has-text("Submit")').first();
    await submitBtn.click();
    await browser.humanDelay(2000, 3000);

    const success = await page.locator('[class*="success"], h2:has-text("Thank")').count() > 0;
    if (!success && await browser.detectCaptcha(page)) return { success: false, captchaDetected: true };

    return { success: true };
  } catch (e: any) {
    return { success: false, error: e.message };
  }
}
