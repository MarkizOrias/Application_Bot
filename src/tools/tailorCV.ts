// src/tools/tailorCV.ts
// Reads your base CV, asks Claude to tailor it for the specific job,
// then generates a .docx file ready for upload.

import Anthropic              from "@anthropic-ai/sdk";
import * as fs                from "fs";
import * as path              from "path";
import { ApplicationStateDB } from "../state/ApplicationStateDB.js";
import { generateDocx }       from "../utils/generateDocx.js";

const client = new Anthropic();  // uses ANTHROPIC_API_KEY from env

type TailorArgs = {
  job_description: string;
  job_title: string;
  company: string;
  apply_url: string;
};

export async function tailorCVTool(args: TailorArgs, db: ApplicationStateDB) {
  const baseCV = fs.readFileSync("./cvs/base.md", "utf-8");

  // ── Ask Claude to tailor the CV ───────────────────────────────────────────
  const response = await client.messages.create({
    model: "claude-opus-4-6",
    max_tokens: 3000,
    messages: [{
      role: "user",
      content: `You are an expert CV writer and ATS specialist.

## Job Description
${args.job_description}

## User's Base CV (Markdown)
${baseCV}

## Task
Rewrite the CV specifically for the role of "${args.job_title}" at "${args.company}".

Rules:
1. Mirror exact keywords and phrases from the job description (for ATS matching)
2. Reorder EXPERIENCE bullets so the most relevant achievements appear first in each role
3. Rewrite the SUMMARY to speak directly to this role's requirements
4. Do NOT add skills or experiences the candidate doesn't have — only reframe existing ones
5. Keep the same structure (SUMMARY, SKILLS, EXPERIENCE, EDUCATION)
6. Return ONLY the tailored CV in Markdown. No preamble, no explanation.

Also append at the very end (for logging, not in the CV):
---KEYWORDS---
[comma-separated list of 10-15 key phrases you injected from the JD]
`,
    }],
  });

  const rawText = response.content[0].type === "text" ? response.content[0].text : "";

  // ── Split CV text from keyword log ────────────────────────────────────────
  const [cvMarkdown, keywordSection] = rawText.split("---KEYWORDS---");
  const keywords = (keywordSection ?? "")
    .trim()
    .split(",")
    .map((k) => k.trim())
    .filter(Boolean);

  // ── Detect platform from URL ──────────────────────────────────────────────
  const platform = detectPlatform(args.apply_url);

  // ── Write .docx file ──────────────────────────────────────────────────────
  const outputDir = "./cvs/output";
  fs.mkdirSync(outputDir, { recursive: true });
  const fileName = `${args.company.replace(/[^a-zA-Z0-9]/g, "_")}_${Date.now()}.docx`;
  const filePath = path.join(outputDir, fileName);
  await generateDocx(cvMarkdown.trim(), filePath);

  // ── Log to DB (status: pending_review — awaiting user approval) ───────────
  const record = db.createApplication({
    company:         args.company,
    role:            args.job_title,
    apply_url:       args.apply_url,
    platform,
    cv_file_path:    filePath,
    keyword_matches: keywords,
  });

  return {
    content: [{
      type: "text",
      text: JSON.stringify({
        application_id:  record.id,
        company:         args.company,
        role:            args.job_title,
        platform,
        cv_file_path:    filePath,
        keyword_matches: keywords,
        status:          "pending_review",
        message:         "CV tailored. Awaiting your approval before submitting.",
      }, null, 2),
    }],
  };
}

// ── Detect ATS platform from URL ──────────────────────────────────────────────
function detectPlatform(url: string): string {
  if (url.includes("linkedin.com"))       return "linkedin";
  if (url.includes("greenhouse.io"))      return "greenhouse";
  if (url.includes("lever.co"))           return "lever";
  if (url.includes("workday.com"))        return "workday";
  if (url.includes("wellfound.com"))      return "wellfound";
  return "generic";
}
