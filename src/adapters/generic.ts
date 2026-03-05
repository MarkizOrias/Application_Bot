// src/adapters/generic.ts
// Generic fallback adapter for unknown platforms — tries common selectors.
import { Page }           from "playwright";
import { BrowserManager } from "../browser/BrowserManager.js";

export async function genericAdapter(
  page: Page,
  browser: BrowserManager,
  profile: any,
  cvFilePath: string,
  coverLetter?: string,
): Promise<{ success: boolean; captchaDetected?: boolean; error?: string }> {
  try {
    const [firstName, ...lastParts] = profile.full_name.split(" ");
    const lastName = lastParts.join(" ");

    const fill = async (sel: string, val: string) => {
      if (!val) return;
      const el = page.locator(sel).first();
      if (await el.count() > 0) { await el.fill(val); await browser.humanDelay(150, 300); }
    };

    // Try split first/last name fields
    const firstFilled = await (async () => {
      for (const sel of ['[name="first_name"]', '[id="first_name"]', '[name="firstName"]']) {
        const el = page.locator(sel).first();
        if (await el.count() > 0) {
          await el.fill(firstName);
          await browser.humanDelay(150, 300);
          return true;
        }
      }
      return false;
    })();

    if (firstFilled) {
      for (const sel of ['[name="last_name"]', '[id="last_name"]', '[name="lastName"]']) {
        const el = page.locator(sel).first();
        if (await el.count() > 0) { await el.fill(lastName); await browser.humanDelay(150, 300); break; }
      }
    } else {
      // Fallback: full name field
      await fill('[name="name"], [id="name"]', profile.full_name);
    }

    await fill('[type="email"], [name="email"], [id="email"]', profile.email);
    await fill('[type="tel"],   [name="phone"], [id="phone"]', profile.phone);

    // Resume upload
    const fileInput = page.locator('input[type="file"]').first();
    if (await fileInput.count() > 0) {
      await fileInput.setInputFiles(cvFilePath);
      await browser.humanDelay(1000, 2000);
    }

    // Cover letter
    if (coverLetter) {
      const clField = page.locator("textarea").first();
      if (await clField.count() > 0) {
        await clField.fill(coverLetter);
        await browser.humanDelay(300, 600);
      }
    }

    if (await browser.detectCaptcha(page)) return { success: false, captchaDetected: true };

    const submitBtn = page.locator('[type="submit"], button:has-text("Submit"), button:has-text("Apply")').first();
    if (await submitBtn.count() > 0) {
      await submitBtn.click();
      await browser.humanDelay(2000, 3000);
      if (await browser.detectCaptcha(page)) return { success: false, captchaDetected: true };
      return { success: true };
    }

    return { success: false, error: "Could not find submit button" };
  } catch (e: any) {
    return { success: false, error: e.message };
  }
}
