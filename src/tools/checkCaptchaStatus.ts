// src/tools/checkCaptchaStatus.ts
// Polls the in-memory captcha state for a given application_id.
// Called by Claude every 30 s while waiting for the user to solve a CAPTCHA.

import { CaptchaNotifier }    from "../notifier/CaptchaNotifier.js";
import { ApplicationStateDB } from "../state/ApplicationStateDB.js";
import { BrowserManager }     from "../browser/BrowserManager.js";

type CheckCaptchaArgs = {
  application_id: string;
};

export async function checkCaptchaStatusTool(
  args: CheckCaptchaArgs,
  notifier: CaptchaNotifier,
  db: ApplicationStateDB,
  browser: BrowserManager,
) {
  const captchaStatus = notifier.getStatus(args.application_id);
  const app           = db.getById(args.application_id);

  return {
    content: [{
      type: "text",
      text: JSON.stringify({
        application_id: args.application_id,
        captcha_status: captchaStatus,
        db_status:      app?.status ?? "not_found",
        company:        app?.company,
        role:           app?.role,
        message:        statusMessage(captchaStatus),
      }, null, 2),
    }],
  };
}

function statusMessage(status: string): string {
  switch (status) {
    case "pending":   return "CAPTCHA is still pending — waiting for you to solve it in the browser.";
    case "resolved":  return "CAPTCHA was resolved. Resuming application.";
    case "timed_out": return "CAPTCHA timed out. Application was skipped.";
    default:          return "No CAPTCHA hold found for this application.";
  }
}
