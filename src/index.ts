// src/index.ts  — MCP Server entry point
// Run via: node src/index.js  (compiled) or ts-node src/index.ts

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { BrowserManager }         from "./browser/BrowserManager.js";
import { CaptchaNotifier }        from "./notifier/CaptchaNotifier.js";
import { ApplicationStateDB }     from "./state/ApplicationStateDB.js";
import { searchJobsTool }         from "./tools/searchJobs.js";
import { getJobDetailsTool }      from "./tools/getJobDetails.js";
import { tailorCVTool }           from "./tools/tailorCV.js";
import { submitApplicationTool }  from "./tools/submitApplication.js";
import { checkCaptchaStatusTool } from "./tools/checkCaptchaStatus.js";
import { listApplicationsTool }   from "./tools/listApplications.js";
import config from "../config/profile.json";

// ─── Singletons shared across all tool calls ──────────────────────────────────
export const browser  = new BrowserManager(config.browser);
export const notifier = new CaptchaNotifier(config.notifications);
export const db       = new ApplicationStateDB("./data/applications.db");

// ─── MCP Server ───────────────────────────────────────────────────────────────
const server = new Server(
  { name: "job-application-agent", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "search_jobs",
      description: "Search remote job postings across LinkedIn Easy Apply, Remotive, We Work Remotely, and Himalayas.",
      inputSchema: {
        type: "object",
        properties: {
          query:       { type: "string"  },
          max_results: { type: "number"  },
          sources:     { type: "array", items: { type: "string" } },
        },
        required: ["query"],
      },
    },
    {
      name: "get_job_details",
      description: "Scrape full job description and apply URL from a posting page.",
      inputSchema: {
        type: "object",
        properties: { url: { type: "string" } },
        required: ["url"],
      },
    },
    {
      name: "tailor_cv",
      description: "Rewrite base CV for a specific job. Returns application_id and .docx path.",
      inputSchema: {
        type: "object",
        properties: {
          job_description: { type: "string" },
          job_title:       { type: "string" },
          company:         { type: "string" },
          apply_url:       { type: "string" },
        },
        required: ["job_description", "job_title", "company", "apply_url"],
      },
    },
    {
      name: "submit_application",
      description: "Auto-fill and submit the application in the headed browser. Returns: submitted | captcha_hold | error.",
      inputSchema: {
        type: "object",
        properties: {
          application_id: { type: "string" },
          apply_url:      { type: "string" },
          platform:       { type: "string", description: "linkedin | greenhouse | lever | generic" },
          cv_file_path:   { type: "string" },
          cover_letter:   { type: "string" },
        },
        required: ["application_id", "apply_url", "platform", "cv_file_path"],
      },
    },
    {
      name: "check_captcha_status",
      description: "Poll resolution of a captcha_hold application. Returns: pending | resolved | timed_out.",
      inputSchema: {
        type: "object",
        properties: { application_id: { type: "string" } },
        required: ["application_id"],
      },
    },
    {
      name: "list_applications",
      description: "List all tracked applications with statuses.",
      inputSchema: {
        type: "object",
        properties: {
          status_filter: { type: "string" },
          limit:         { type: "number" },
        },
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  try {
    switch (name) {
      case "search_jobs":          return await searchJobsTool(args as any);
      case "get_job_details":      return await getJobDetailsTool(args as any, browser);
      case "tailor_cv":            return await tailorCVTool(args as any, db);
      case "submit_application":   return await submitApplicationTool(args as any, browser, notifier, db);
      case "check_captcha_status": return await checkCaptchaStatusTool(args as any, notifier, db, browser);
      case "list_applications":    return await listApplicationsTool(args as any, db);
      default:
        return { content: [{ type: "text", text: `Unknown tool: ${name}` }], isError: true };
    }
  } catch (err: any) {
    return { content: [{ type: "text", text: `Tool error: ${err.message}` }], isError: true };
  }
});

async function main() {
  await db.init();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("[job-agent] MCP server running — Claude can now call tools.");
}

main().catch(console.error);
