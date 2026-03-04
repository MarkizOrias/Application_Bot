// src/adapters/greenhouse.ts
// Greenhouse boards have a consistent structure across ALL companies using them.
// URL pattern: boards.greenhouse.io/[company]/jobs/[id]
// No login required — just fill the form directly.

import { Page }          from "playwright";
import { BrowserManager } from "../browser/BrowserManager.js";

export async function greenhouseAdapter(
  page: Page,
  browser: BrowserManager,
  profile: any,
  cvFilePath: string,
  coverLetter?: string,
): Promise<{ success: boolean; captchaDetected?: boolean; error?: string }> {
  try {
    // ── Standard Greenhouse fields ────────────────────────────────────────────
    await fillField(page, browser, '#first_name',            profile.full_name.split(" ")[0]);
    await fillField(page, browser, '#last_name',             profile.full_name.split(" ").slice(1).join(" "));
    await fillField(page, browser, '#email',                 profile.email);
    await fillField(page, browser, '#phone',                 profile.phone);
    await fillField(page, browser, '#job_application_linkedin_profile_url', profile.linkedin);

    // ── Resume upload ─────────────────────────────────────────────────────────
    const resumeInput = page.locator('#resume, input[name="resume"], input[type="file"]').first();
    if (await resumeInput.count() > 0) {
      await resumeInput.setInputFiles(cvFilePath);
      await browser.humanDelay(1000, 2000);
    }

    // ── Cover letter ──────────────────────────────────────────────────────────
    if (coverLetter) {
      const clInput = page.locator('#cover_letter, textarea[name="cover_letter"]').first();
      if (await clInput.count() > 0) {
        await clInput.fill(coverLetter);
        await browser.humanDelay(300, 600);
      }
    }

    // ── Custom questions (varies per company, Greenhouse renders them consistently) ──
    await answerCustomQuestions(page, profile, browser);

    // ── CAPTCHA check before submit ───────────────────────────────────────────
    if (await browser.detectCaptcha(page)) {
      return { success: false, captchaDetected: true };
    }

    // ── Submit ────────────────────────────────────────────────────────────────
    const submitBtn = page.locator('#submit_app, button[type="submit"], input[type="submit"]').first();
    await submitBtn.waitFor({ timeout: 5000 });
    await submitBtn.click();

    // Wait for confirmation page
    await page.waitForURL(/confirmation|thank-you|success/, { timeout: 10_000 })
      .catch(() => {}); // Some companies don't redirect, just show a banner

    const confirmed = await page.locator('[class*="success"], [class*="confirmation"], h2:has-text("Thank")').count();
    if (confirmed > 0 || page.url().includes("confirmation")) {
      return { success: true };
    }

    // Check for CAPTCHA that appeared after submit
    if (await browser.detectCaptcha(page)) {
      return { success: false, captchaDetected: true };
    }

    return { success: false, error: "Submission unclear — no confirmation detected" };

  } catch (e: any) {
    return { success: false, error: e.message };
  }
}

async function fillField(page: Page, browser: BrowserManager, selector: string, value: string) {
  if (!value) return;
  const el = page.locator(selector).first();
  if (await el.count() > 0) {
    await el.fill(value);
    await browser.humanDelay(150, 350);
  }
}

// Greenhouse custom questions are rendered as standard HTML inputs/selects/textareas
// with descriptive labels — we use label text to infer answers.
async function answerCustomQuestions(page: Page, profile: any, browser: BrowserManager) {
  // Dropdowns
  const selects = page.locator("select");
  const selectCount = await selects.count();
  for (let i = 0; i < selectCount; i++) {
    const sel = selects.nth(i);
    const labelFor = await sel.getAttribute("id");
    const label = labelFor
      ? await page.locator(`label[for="${labelFor}"]`).innerText().catch(() => "")
      : "";
    const labelLower = label.toLowerCase();

    if (labelLower.includes("country") || labelLower.includes("location")) {
      await sel.selectOption({ label: "United Kingdom" }).catch(() => {});
    } else if (labelLower.includes("experience")) {
      await sel.selectOption({ index: 3 }).catch(() => {});  // typically "5+ years"
    }
    await browser.humanDelay(100, 200);
  }

  // Free text questions
  const textareas = page.locator("textarea:not([name='cover_letter'])");
  const taCount = await textareas.count();
  for (let i = 0; i < taCount; i++) {
    const ta = textareas.nth(i);
    const current = await ta.inputValue();
    if (!current) {
      await ta.fill("Please see my CV and cover letter for details.");
      await browser.humanDelay(150, 300);
    }
  }
}
