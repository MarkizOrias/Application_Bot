// src/tools/listApplications.ts
import { ApplicationStateDB } from "../state/ApplicationStateDB.js";

type ListArgs = {
  status_filter?: string;
  limit?: number;
};

export async function listApplicationsTool(args: ListArgs, db: ApplicationStateDB) {
  const records = db.listApplications(args);
  return {
    content: [{
      type: "text",
      text: JSON.stringify({ total: records.length, applications: records }, null, 2),
    }],
  };
}
