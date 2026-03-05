// src/state/ApplicationStateDB.ts
import Database from "better-sqlite3";
import { randomUUID } from "crypto";
import * as path from "path";
import * as fs from "fs";

export interface ApplicationRecord {
  id: string;
  company: string;
  role: string;
  apply_url: string;
  platform: string;
  cv_file_path: string;
  keyword_matches: string[];
  status: string;
  submitted_at?: string;
  error_message?: string;
  created_at: string;
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
  private db: Database.Database | null = null;
  private dbPath: string;

  constructor(dbPath: string) {
    this.dbPath = dbPath;
  }

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
        submitted_at    TEXT,
        error_message   TEXT,
        created_at      TEXT NOT NULL
      )
    `);
  }

  private get(): Database.Database {
    if (!this.db) throw new Error("DB not initialized. Call init() first.");
    return this.db;
  }

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

    this.get().prepare(`
      INSERT INTO applications
        (id, company, role, apply_url, platform, cv_file_path, keyword_matches, status, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      record.id, record.company, record.role, record.apply_url, record.platform,
      record.cv_file_path, JSON.stringify(record.keyword_matches), record.status, record.created_at,
    );

    return record;
  }

  getById(id: string): ApplicationRecord | null {
    const row = this.get().prepare("SELECT * FROM applications WHERE id = ?").get(id) as any;
    if (!row) return null;
    return this.deserialize(row);
  }

  updateStatus(id: string, status: string, extra: { submitted_at?: string; error_message?: string } = {}): void {
    this.get().prepare(`
      UPDATE applications
      SET status = ?,
          submitted_at  = COALESCE(?, submitted_at),
          error_message = COALESCE(?, error_message)
      WHERE id = ?
    `).run(status, extra.submitted_at ?? null, extra.error_message ?? null, id);
  }

  listApplications(args: { status_filter?: string; limit?: number } = {}): ApplicationRecord[] {
    const { status_filter, limit = 50 } = args;
    let query = "SELECT * FROM applications";
    const params: any[] = [];
    if (status_filter) {
      query += " WHERE status = ?";
      params.push(status_filter);
    }
    query += " ORDER BY created_at DESC LIMIT ?";
    params.push(limit);
    const rows = this.get().prepare(query).all(...params) as any[];
    return rows.map((r) => this.deserialize(r));
  }

  private deserialize(row: any): ApplicationRecord {
    return { ...row, keyword_matches: JSON.parse(row.keyword_matches ?? "[]") };
  }
}
