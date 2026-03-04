// src/tools/listApplications.ts
// Returns all tracked applications from the SQLite DB, with optional filtering.

import { ApplicationStateDB } from "../state/ApplicationStateDB.js";

type ListArgs = {
  status_filter?: string;
  limit?: number;
};

export async function listApplicationsTool(args: ListArgs, db: ApplicationStateDB) {
  const apps = db.listApplications(args.status_filter, args.limit ?? 50);

  const byStatus = apps.reduce<Record<string, number>>((acc, app) => {
    acc[app.status] = (acc[app.status] ?? 0) + 1;
    return acc;
  }, {});

  const summary = {
    total:        apps.length,
    by_status:    byStatus,
    applications: apps.map((a) => ({
      id:           a.id,
      company:      a.company,
      role:         a.role,
      platform:     a.platform,
      status:       a.status,
      created_at:   a.created_at,
      submitted_at: a.submitted_at ?? null,
      error:        a.error_message ?? null,
    })),
  };

  return {
    content: [{
      type: "text",
      text: JSON.stringify(summary, null, 2),
    }],
  };
}
