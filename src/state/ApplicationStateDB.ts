// src/state/ApplicationStateDB.ts
// SQLite-backed store for all application records.
// Uses better-sqlite3 (synchronous API — safe on single-threaded MCP server).

import Database, { Database as DBType } from "better-sqlite3";
import { randomUUID } from "crypto";
import * as fs from "fs";
import * as path from "path";

export interface ApplicationRecord {
  id: string;
  company: string;
  role: string;
  apply_url: string;
  platform: string;
  cv_file_path: string;
  keyword_matches: string[];
  status: string;
  created_at: string;
  submitted_at?: string;
  error_message?: string;
}

interface CreateApplicationArgs {
  company: string;
  role: string;
  apply_url: string;
  platform: string;
  cv_file_path: string;
  keyword_matches: string[];
}

export class ApplicationStateDB {
  private db!: DBType;
  private dbPath: string;

  constructor(dbPath: string) {
    this.dbPath = dbPath;
  }

  // ── Must be called once at startup before any tool call ───────────────────
  async init(): Promise<void> {
    const dir = path.dirname(this.dbPath);
    fs.mkdirSync(dir, { recursive: true });

    this.db = new Database(this.dbPath);
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS applications (
        id              TEXT PRIMARY KEY,
        company         TEXT NOT NULL,
        role            TEXT NOT NULL,
        apply_url       TEXT NOT NULL,
        platform        TEXT NOT NULL,
        cv_file_path    TEXT NOT NULL,
        keyword_matches TEXT NOT NULL DEFAULT '[]',
        status          TEXT NOT NULL DEFAULT 'pending_review',
        created_at      TEXT NOT NULL,
        submitted_at    TEXT,
        error_message   TEXT
      )
    `);
  }

  // ── Insert a new application record ───────────────────────────────────────
  createApplication(args: CreateApplicationArgs): ApplicationRecord {
    const record: ApplicationRecord = {
      id:              randomUUID(),
      company:         args.company,
      role:            args.role,
      apply_url:       args.apply_url,
      platform:        args.platform,
      cv_file_path:    args.cv_file_path,
      keyword_matches: args.keyword_matches,
      status:          "pending_review",
      created_at:      new Date().toISOString(),
    };

    this.db.prepare(`
      INSERT INTO applications
        (id, company, role, apply_url, platform, cv_file_path, keyword_matches, status, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      record.id,
      record.company,
      record.role,
      record.apply_url,
      record.platform,
      record.cv_file_path,
      JSON.stringify(record.keyword_matches),
      record.status,
      record.created_at,
    );

    return record;
  }

  // ── Fetch single record by ID ──────────────────────────────────────────────
  getById(id: string): ApplicationRecord | null {
    const row = this.db.prepare("SELECT * FROM applications WHERE id = ?").get(id) as any;
    if (!row) return null;
    return { ...row, keyword_matches: JSON.parse(row.keyword_matches) };
  }

  // ── Update status (and optional extra fields) ─────────────────────────────
  updateStatus(
    id: string,
    status: string,
    extra: { submitted_at?: string; error_message?: string } = {},
  ): void {
    if (extra.submitted_at) {
      this.db.prepare(
        "UPDATE applications SET status = ?, submitted_at = ? WHERE id = ?"
      ).run(status, extra.submitted_at, id);
    } else if (extra.error_message) {
      this.db.prepare(
        "UPDATE applications SET status = ?, error_message = ? WHERE id = ?"
      ).run(status, extra.error_message, id);
    } else {
      this.db.prepare(
        "UPDATE applications SET status = ? WHERE id = ?"
      ).run(status, id);
    }
  }

  // ── List applications with optional filter + limit ────────────────────────
  listApplications(statusFilter?: string, limit: number = 50): ApplicationRecord[] {
    let query = "SELECT * FROM applications";
    const params: any[] = [];

    if (statusFilter) {
      query += " WHERE status = ?";
      params.push(statusFilter);
    }

    query += " ORDER BY created_at DESC LIMIT ?";
    params.push(limit);

    const rows = this.db.prepare(query).all(...params) as any[];
    return rows.map((row) => ({ ...row, keyword_matches: JSON.parse(row.keyword_matches) }));
  }
}
