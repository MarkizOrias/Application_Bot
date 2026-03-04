// src/tools/submitApplication.ts
// The core automation tool. Navigates to apply URL, fills form, uploads CV.
// If CAPTCHA detected: pauses, notifies user, waits for resolution, resumes.

import { BrowserManager }     from "../browser/BrowserManager.js";
import { CaptchaNotifier }    from "../notifier/CaptchaNotifier.js";
import { ApplicationStateDB } from "../state/ApplicationStateDB.js";
import { linkedinAdapter }    from "../adapters/linkedin.js";
import { greenhouseAdapter }  from "../adapters/greenhouse.js";
import { leverAdapter }       from "../adapters/lever.js";
import { genericAdapter }     from "../adapters/generic.js";
import config from "../../config/profile.json" assert { type: "json" };

type SubmitArgs = {
  application_id: string;
  apply_url: string;
  platform: "linkedin" | "greenhouse" | "lever" | "generic";
  cv_file_path: string;
  cover_letter?: string;
};

export async function submitApplicationTool(
  args: SubmitArgs,
  browser: BrowserManager,
  notifier: CaptchaNotifier,
  db: ApplicationStateDB,
) {
  const app = db.getById(args.application_id);
  if (!app) {
    return err(`Application ${args.application_id} not found in DB`);
  }

  db.updateStatus(args.application_id, "submitting");

  try {
    // 1. Navigate to application page (browser already logged in via your profile)
    const page = await browser.goto(args.apply_url);

    // 2. Pre-submission CAPTCHA check
    if (await browser.detectCaptcha(page)) {
      return await handleCaptcha(args, app, browser, notifier, db);
    }

    // 3. Dispatch to platform-specific adapter
    const adapterResult = await runAdapter(args, page, browser, config.personal);

    // 4. Post-submission CAPTCHA check (some sites show it mid-flow)
    if (adapterResult.captchaDetected) {
      return await handleCaptcha(args, app, browser, notifier, db);
    }

    if (adapterResult.success) {
      const now = new Date().toISOString();
      db.updateStatus(args.application_id, "submitted", { submitted_at: now });
      return ok(`✅ Submitted — ${app.company} · ${app.role}`);
    } else {
      db.updateStatus(args.application_id, "error", { error_message: adapterResult.error });
      return err(`Adapter error: ${adapterResult.error}`);
    }

  } catch (e: any) {
    db.updateStatus(args.application_id, "error", { error_message: e.message });
    return err(`Unhandled error: ${e.message}`);
  }
}

// ── CAPTCHA hold/resume flow ──────────────────────────────────────────────────
async function handleCaptcha(
  args: SubmitArgs,
  app: any,
  browser: BrowserManager,
  notifier: CaptchaNotifier,
  db: ApplicationStateDB,
) {
  db.updateStatus(args.application_id, "captcha_hold");

  // Fire desktop notification
  await notifier.notifyCaptchaRequired(args.application_id, app.company, app.role);

  // Wait for user to press Enter (or timeout)
  const timeoutMs = (config.notifications?.captcha_timeout_minutes ?? 10) * 60 * 1000;
  const resolution = await browser.waitForCaptchaResolution(timeoutMs);

  if (resolution === "timed_out") {
    await notifier.markTimedOut(args.application_id);
    db.updateStatus(args.application_id, "captcha_timeout");
    return {
      content: [{
        type: "text",
        text: `captcha_hold — timed out after ${config.notifications.captcha_timeout_minutes} minutes. Application ${args.application_id} skipped.`,
      }],
    };
  }

  // User resolved CAPTCHA — mark and notify
  await notifier.markResolved(args.application_id);
  notifier.notifyResumed(app.company);

  // Brief pause to let the page settle after CAPTCHA solve
  await browser.humanDelay(1500, 2500);

  // Resume form filling from where we were — re-run adapter
  const page = await browser.getPage();
  const resumeResult = await runAdapter(args, page, browser, config.personal);

  if (resumeResult.success) {
    const now = new Date().toISOString();
    db.updateStatus(args.application_id, "submitted", { submitted_at: now });
    return ok(`✅ Submitted (after CAPTCHA) — ${app.company} · ${app.role}`);
  } else {
    db.updateStatus(args.application_id, "error", { error_message: resumeResult.error });
    return err(`Resume failed: ${resumeResult.error}`);
  }
}

// ── Adapter router ────────────────────────────────────────────────────────────
async function runAdapter(
  args: SubmitArgs,
  page: any,
  browser: BrowserManager,
  profile: any,
): Promise<{ success: boolean; captchaDetected?: boolean; error?: string }> {
  switch (args.platform) {
    case "linkedin":   return linkedinAdapter(page, browser, profile, args.cv_file_path, args.cover_letter);
    case "greenhouse": return greenhouseAdapter(page, browser, profile, args.cv_file_path, args.cover_letter);
    case "lever":      return leverAdapter(page, browser, profile, args.cv_file_path, args.cover_letter);
    default:           return genericAdapter(page, browser, profile, args.cv_file_path, args.cover_letter);
  }
}

// ── Response helpers ──────────────────────────────────────────────────────────
const ok  = (text: string) => ({ content: [{ type: "text", text }] });
const err = (text: string) => ({ content: [{ type: "text", text }], isError: true });
