// src/browser/BrowserManager.ts
// Launches and manages a single headed Chrome instance using your real profile.
// Your saved sessions / cookies mean you arrive already logged in everywhere.

import { chromium, Browser, BrowserContext, Page } from "playwright";
import * as readline from "readline";

interface BrowserConfig {
  chrome_profile_path: string;
  headless: boolean;
  slow_mo_ms: number;
}

export class BrowserManager {
  private context: BrowserContext | null = null;
  private activePage: Page | null = null;
  private config: BrowserConfig;

  constructor(config: BrowserConfig) {
    this.config = config;
  }

  // ── Launch (or reuse) the browser ──────────────────────────────────────────
  async getContext(): Promise<BrowserContext> {
    if (this.context) return this.context;

    // persistentContext = uses your real Chrome profile directory.
    // This is the key: Playwright opens Chrome with your cookies/sessions intact.
    this.context = await chromium.launchPersistentContext(
      this.config.chrome_profile_path,
      {
        headless:   this.config.headless ?? false,
        slowMo:     this.config.slow_mo_ms ?? 120,
        channel:    "chrome",           // uses YOUR installed Chrome, not bundled Chromium
        args: [
          "--disable-blink-features=AutomationControlled", // hides automation flag
          "--no-first-run",
          "--no-default-browser-check",
        ],
        // Mimic a real user agent
        userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
      }
    );

    // Patch navigator.webdriver to prevent detection
    await this.context.addInitScript(() => {
      Object.defineProperty(navigator, "webdriver", { get: () => undefined });
    });

    return this.context;
  }

  // ── Open a new page (or reuse existing) ───────────────────────────────────
  async getPage(): Promise<Page> {
    const ctx = await this.getContext();
    if (this.activePage && !this.activePage.isClosed()) return this.activePage;

    this.activePage = await ctx.newPage();
    return this.activePage;
  }

  // ── Navigate with human-like delay ────────────────────────────────────────
  async goto(url: string): Promise<Page> {
    const page = await this.getPage();
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await this.humanDelay(800, 1600);
    return page;
  }

  // ── Check for CAPTCHA on current page ─────────────────────────────────────
  async detectCaptcha(page: Page): Promise<boolean> {
    const captchaSelectors = [
      'iframe[src*="recaptcha"]',
      'iframe[src*="hcaptcha"]',
      '[class*="captcha"]',
      '[id*="captcha"]',
      ".cf-challenge-running",            // Cloudflare
      "#challenge-stage",                 // Cloudflare
      'iframe[title="reCAPTCHA"]',
      '[aria-label*="CAPTCHA"]',
    ];
    for (const sel of captchaSelectors) {
      if (await page.locator(sel).count() > 0) return true;
    }
    return false;
  }

  // ── Wait for user to solve CAPTCHA, then signal resume ────────────────────
  // The browser stays open and visible on the CAPTCHA page.
  // User solves it, then presses Enter in the terminal.
  async waitForCaptchaResolution(timeoutMs: number = 600_000): Promise<"resolved" | "timed_out"> {
    console.error("\n⚠️  CAPTCHA DETECTED — browser is paused.");
    console.error("   → Solve the CAPTCHA in the open Chrome window.");
    console.error("   → Then press ENTER here to resume.\n");

    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        rl.close();
        resolve("timed_out");
      }, timeoutMs);

      const rl = readline.createInterface({ input: process.stdin });
      rl.once("line", () => {
        clearTimeout(timer);
        rl.close();
        resolve("resolved");
      });
    });
  }

  // ── Simulate human typing (not instant fill) ──────────────────────────────
  async humanType(page: Page, selector: string, text: string): Promise<void> {
    await page.locator(selector).click();
    await this.humanDelay(200, 400);
    // Type character by character with slight variation
    for (const char of text) {
      await page.keyboard.type(char, { delay: 40 + Math.random() * 60 });
    }
  }

  // ── Upload a file to a file input ─────────────────────────────────────────
  async uploadFile(page: Page, inputSelector: string, filePath: string): Promise<void> {
    const input = page.locator(inputSelector);
    await input.setInputFiles(filePath);
    await this.humanDelay(500, 1000);
  }

  // ── Scrape text content cleanly ───────────────────────────────────────────
  async scrapeText(page: Page, selector: string): Promise<string> {
    try {
      return await page.locator(selector).innerText({ timeout: 5000 });
    } catch {
      return "";
    }
  }

  // ── Random human-like delay ───────────────────────────────────────────────
  async humanDelay(minMs = 300, maxMs = 900): Promise<void> {
    const delay = minMs + Math.random() * (maxMs - minMs);
    await new Promise((r) => setTimeout(r, delay));
  }

  // ── Close browser at end of session ──────────────────────────────────────
  async close(): Promise<void> {
    if (this.context) {
      await this.context.close();
      this.context = null;
      this.activePage = null;
    }
  }
}
