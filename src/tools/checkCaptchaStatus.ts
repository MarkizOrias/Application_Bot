// src/tools/checkCaptchaStatus.ts
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
  const status = notifier.getStatus(args.application_id);

  // Sync notifier state to DB
  if (status === "resolved") {
    db.updateStatus(args.application_id, "submitted");
  } else if (status === "timed_out") {
    db.updateStatus(args.application_id, "captcha_timeout");
  }

  return {
    content: [{
      type: "text",
      text: JSON.stringify({ application_id: args.application_id, status }, null, 2),
    }],
  };
}
