// src/adapters/linkedin.ts
// Handles LinkedIn Easy Apply flow.
// Easy Apply keeps everything in a right-side drawer — no external redirect.
// Your profile session is already active (logged in via Chrome profile).

import { Page }          from "playwright";
import { BrowserManager } from "../browser/BrowserManager.js";

export async function linkedinAdapter(
  page: Page,
  browser: BrowserManager,
  profile: any,
  cvFilePath: string,
  coverLetter?: string,
): Promise<{ success: boolean; captchaDetected?: boolean; error?: string }> {
  try {
    // ── 1. Click "Easy Apply" button ─────────────────────────────────────────
    const easyApplyBtn = page.locator('button:has-text("Easy Apply")').first();
    await easyApplyBtn.waitFor({ timeout: 8000 });
    await easyApplyBtn.click();
    await browser.humanDelay(800, 1200);

    // ── 2. Step through the multi-step drawer ────────────────────────────────
    // LinkedIn Easy Apply is a wizard with 1-5 steps depending on the job.
    // Each step has a "Next" or "Review" or "Submit application" button.

    let maxSteps = 6;
    while (maxSteps-- > 0) {
      // Check for CAPTCHA mid-flow
      if (await browser.detectCaptcha(page)) {
        return { success: false, captchaDetected: true };
      }

      // ── Contact info step ── (usually pre-filled from your LI profile)
      await fillIfVisible(page, browser, 'input[id*="phoneNumber"]', profile.phone);

      // ── Resume upload step ──
      const resumeUpload = page.locator('input[type="file"]').first();
      if (await resumeUpload.count() > 0) {
        await resumeUpload.setInputFiles(cvFilePath);
        await browser.humanDelay(1000, 2000);
      }

      // ── Cover letter step ──
      if (coverLetter) {
        const coverLetterField = page.locator('textarea[id*="coverLetter"], [aria-label*="cover letter"]').first();
        if (await coverLetterField.count() > 0) {
          await coverLetterField.click();
          await coverLetterField.fill(coverLetter);
          await browser.humanDelay(400, 800);
        }
      }

      // ── Yes/No radio questions (common: "Are you authorized to work?") ──
      await answerRadioQuestions(page, profile);

      // ── Text input questions ──
      await answerTextQuestions(page, profile, browser);

      // ── Check which button is available ──────────────────────────────────
      const submitBtn = page.locator('button:has-text("Submit application")');
      const nextBtn   = page.locator('button:has-text("Next")');
      const reviewBtn = page.locator('button:has-text("Review")');

      if (await submitBtn.count() > 0) {
        await submitBtn.click();
        await browser.humanDelay(1500, 2500);
        // Confirm dialog appears sometimes
        const confirmBtn = page.locator('button:has-text("Done")');
        if (await confirmBtn.count() > 0) await confirmBtn.click();
        return { success: true };
      } else if (await reviewBtn.count() > 0) {
        await reviewBtn.click();
      } else if (await nextBtn.count() > 0) {
        await nextBtn.click();
      } else {
        return { success: false, error: "Could not find Next/Submit button" };
      }

      await browser.humanDelay(600, 1000);
    }

    return { success: false, error: "Exceeded max steps in LinkedIn Easy Apply" };

  } catch (e: any) {
    return { success: false, error: e.message };
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function fillIfVisible(page: Page, browser: BrowserManager, selector: string, value: string) {
  const el = page.locator(selector).first();
  if (await el.count() > 0 && await el.isVisible()) {
    await el.fill("");
    await el.fill(value);
    await browser.humanDelay(200, 400);
  }
}

// Common yes/no questions LinkedIn jobs ask:
// "Are you comfortable working remotely?", "Are you authorized to work in [country]?"
async function answerRadioQuestions(page: Page, profile: any) {
  const fieldsets = page.locator("fieldset");
  const count = await fieldsets.count();

  for (let i = 0; i < count; i++) {
    const fs = fieldsets.nth(i);
    const legend = await fs.locator("legend").first().innerText().catch(() => "");

    const legLower = legend.toLowerCase();
    if (legLower.includes("authorized") || legLower.includes("legally") ||
        legLower.includes("remote")     || legLower.includes("legally eligible")) {
      const yesOption = fs.locator('label:has-text("Yes")').first();
      if (await yesOption.count() > 0) await yesOption.click();
    }
  }
}

// Salary, years of experience, notice period etc.
async function answerTextQuestions(page: Page, profile: any, browser: BrowserManager) {
  const inputs = page.locator(".jobs-easy-apply-form-section__grouping input[type=text], " +
                              ".jobs-easy-apply-form-section__grouping input[type=number]");
  const count = await inputs.count();

  for (let i = 0; i < count; i++) {
    const input = inputs.nth(i);
    const labelEl = page.locator(`label[for="${await input.getAttribute("id")}"]`);
    const label = await labelEl.innerText().catch(() => "");
    const labelLower = label.toLowerCase();

    let answer = "";
    if (labelLower.includes("salary") || labelLower.includes("compensation")) {
      answer = String(profile.min_salary_usd ?? profile.min_salary_gbp ?? "");
    } else if (labelLower.includes("years") && labelLower.includes("experience")) {
      answer = "7";
    } else if (labelLower.includes("notice") || labelLower.includes("availability")) {
      answer = "2 weeks";
    } else if (labelLower.includes("linkedin")) {
      answer = profile.linkedin ?? "";
    } else if (labelLower.includes("github") || labelLower.includes("portfolio")) {
      answer = profile.github ?? profile.portfolio ?? "";
    }

    if (answer && !(await input.inputValue())) {
      await input.fill(answer);
      await browser.humanDelay(150, 350);
    }
  }
}
