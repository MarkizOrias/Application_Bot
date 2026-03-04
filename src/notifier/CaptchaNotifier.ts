// src/notifier/CaptchaNotifier.ts
// Sends native desktop notifications when CAPTCHA is required.
// Tracks hold/resolve state per application_id.

import notifier from "node-notifier";

interface NotifierConfig {
  platform: "auto" | "macos" | "windows" | "linux";
  captcha_timeout_minutes: number;
}

type CaptchaState = {
  status: "pending" | "resolved" | "timed_out";
  detectedAt: Date;
  resolvedAt?: Date;
};

export class CaptchaNotifier {
  private states: Map<string, CaptchaState> = new Map();
  private config: NotifierConfig;

  constructor(config: NotifierConfig) {
    this.config = config;
  }

  // ── Notify user that CAPTCHA is blocking applicationId ───────────────────
  async notifyCaptchaRequired(applicationId: string, company: string, role: string): Promise<void> {
    this.states.set(applicationId, {
      status: "pending",
      detectedAt: new Date(),
    });

    // Native desktop notification (works on macOS, Windows, Linux)
    notifier.notify({
      title:    "CAPTCHA Required — Job Agent Paused",
      message:  `${company} · ${role}\n\nSolve CAPTCHA in Chrome, then press Enter in terminal.`,
      sound:    true,
      wait:     false,    // non-blocking
    });

    console.error(`\n[CAPTCHA] Application ${applicationId} is on hold.`);
    console.error(`         Company: ${company} | Role: ${role}`);
    console.error(`         Timeout: ${this.config.captcha_timeout_minutes} minutes\n`);
  }

  // ── Called when user signals CAPTCHA is solved ────────────────────────────
  async markResolved(applicationId: string): Promise<void> {
    const state = this.states.get(applicationId);
    if (state) {
      state.status = "resolved";
      state.resolvedAt = new Date();
      this.states.set(applicationId, state);
    }
  }

  // ── Called when timeout elapses ───────────────────────────────────────────
  async markTimedOut(applicationId: string): Promise<void> {
    const state = this.states.get(applicationId);
    if (state) {
      state.status = "timed_out";
      this.states.set(applicationId, state);
    }
    notifier.notify({
      title:   "Job Agent — CAPTCHA Timeout",
      message: `Application ${applicationId} timed out. Moving to next job.`,
      sound:   false,
    });
  }

  // ── Poll status (called by check_captcha_status tool) ────────────────────
  getStatus(applicationId: string): "pending" | "resolved" | "timed_out" | "unknown" {
    const state = this.states.get(applicationId);
    if (!state) return "unknown";

    // Auto-expire if timeout has passed
    if (state.status === "pending") {
      const elapsedMinutes = (Date.now() - state.detectedAt.getTime()) / 60_000;
      if (elapsedMinutes >= this.config.captcha_timeout_minutes) {
        state.status = "timed_out";
        this.states.set(applicationId, state);
      }
    }
    return state.status;
  }

  // ── Notify user the agent has resumed after CAPTCHA ──────────────────────
  notifyResumed(company: string): void {
    notifier.notify({
      title:   "Job Agent — Resumed",
      message: `Continuing application to ${company}...`,
      sound:   false,
    });
  }
}
