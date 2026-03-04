// src/adapters/generic.ts
// Best-effort adapter for non-standard application forms.
// Targets common field name/id patterns found across most ATS providers.

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
    const fill = async (selector: string, value: string) => {
      if (!value) return;
      const el = page.locator(selector).first();
      if (await el.count() > 0 && await el.isVisible()) {
        await el.fill(value);
        await browser.humanDelay(150, 350);
      }
    };

    // ── Full name (single field) ───────────────────────────────────────────
    await fill(
      '[name="name"], [id="name"], [placeholder*="Full name" i], [placeholder*="Your name" i]',
      profile.full_name
    );

    // ── First / last name (split fields) ──────────────────────────────────
    const firstName = profile.full_name.split(" ")[0];
    const lastName  = profile.full_name.split(" ").slice(1).join(" ");
    await fill('[name="first_name"], [id="first_name"], [placeholder*="First name" i]', firstName);
    await fill('[name="last_name"],  [id="last_name"],  [placeholder*="Last name" i]',  lastName);

    // ── Contact details ────────────────────────────────────────────────────
    await fill('[name="email"],   [id="email"],   [type="email"]',           profile.email);
    await fill('[name="phone"],   [id="phone"],   [type="tel"]',             profile.phone);
    await fill('[name="linkedin"],[id="linkedin"],[placeholder*="LinkedIn" i]', profile.linkedin);
    await fill('[name="github"],  [id="github"],  [placeholder*="GitHub" i]',   profile.github);
    await fill('[name="website"], [id="website"], [placeholder*="Portfolio" i]', profile.portfolio);

    // ── Resume / CV upload ─────────────────────────────────────────────────
    const fileInput = page.locator('input[type="file"]').first();
    if (await fileInput.count() > 0) {
      await fileInput.setInputFiles(cvFilePath);
      await browser.humanDelay(1000, 2000);
    }

    // ── Cover letter ───────────────────────────────────────────────────────
    if (coverLetter) {
      const clInput = page.locator(
        'textarea[name*="cover"], textarea[id*="cover"], textarea[placeholder*="cover letter" i]'
      ).first();
      if (await clInput.count() > 0) {
        await clInput.fill(coverLetter);
        await browser.humanDelay(300, 600);
      }
    }

    // ── CAPTCHA check before submit ────────────────────────────────────────
    if (await browser.detectCaptcha(page)) {
      return { success: false, captchaDetected: true };
    }

    // ── Submit ─────────────────────────────────────────────────────────────
    const submitBtn = page.locator(
      'button[type="submit"], input[type="submit"], button:has-text("Submit"), button:has-text("Apply Now"), button:has-text("Apply")'
    ).first();

    if (await submitBtn.count() === 0) {
      return { success: false, error: "No submit button found on the page" };
    }

    await submitBtn.click();
    await browser.humanDelay(2000, 3500);

    // ── Post-submit CAPTCHA check ──────────────────────────────────────────
    if (await browser.detectCaptcha(page)) {
      return { success: false, captchaDetected: true };
    }

    // ── Detect success ─────────────────────────────────────────────────────
    const confirmed = await page.locator(
      '[class*="success"], [class*="confirmation"], [class*="thank"], ' +
      'h1:has-text("Thank"), h2:has-text("Thank"), p:has-text("successfully submitted")'
    ).count();

    return { success: confirmed > 0 };

  } catch (e: any) {
    return { success: false, error: e.message };
  }
}
