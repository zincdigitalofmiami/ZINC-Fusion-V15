import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

// Glide API Configuration
const GLIDE_API_ENDPOINT = "https://api.glideapp.io/api/function/queryTables";
const GLIDE_APP_ID = "6nvONp42nj5tLQmMcqF3";
const GLIDE_BEARER_TOKEN = process.env.GLIDE_BEARER_TOKEN;

// Table IDs from Glide
const GLIDE_TABLES: Record<string, string> = {
  restaurants: "native-table-ojIjQjDcDAEOpdtZG5Ao",
  casinos: "native-table-Gy2xHsC7urEttrz80hS7",
  fryers: "native-table-r2BIqSLhezVbOKGeRJj8",
  export_list: "native-table-PLujVF4tbbiIi9fzrWg8",
  shifts: "native-table-K53E3SQsgOUB4wdCJdAN",
};

interface GlideRow {
  [key: string]: unknown;
}

async function fetchGlideTable(tableId: string): Promise<GlideRow[]> {
  if (!GLIDE_BEARER_TOKEN) {
    throw new Error("GLIDE_BEARER_TOKEN not configured");
  }

  const response = await fetch(GLIDE_API_ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${GLIDE_BEARER_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      appID: GLIDE_APP_ID,
      queries: [{ tableName: tableId, utc: true }],
    }),
  });

  if (!response.ok) {
    throw new Error(`Glide API error: ${response.status}`);
  }

  const data = await response.json();
  if (Array.isArray(data) && data.length > 0 && data[0].rows) {
    return data[0].rows;
  }
  return [];
}

async function syncTableToPostgres(
  tableName: string,
  rows: GlideRow[]
): Promise<number> {
  if (rows.length === 0) return 0;

  const client = await pool.connect();
  const fullTable = `vegas.vegas_${tableName}`;
  const shortTable = `vegas_${tableName}`;

  try {
    await client.query("BEGIN");

    // Fail loudly if the expected table doesn't exist (no silent DDL in prod).
    const exists = await client.query(
      `SELECT 1
       FROM information_schema.tables
       WHERE table_schema='vegas' AND table_name=$1
       LIMIT 1`,
      [shortTable]
    );
    if (exists.rows.length === 0) {
      throw new Error(
        `Missing table ${fullTable}. Create vegas.vegas_* tables via explicit migration; ingestion will not auto-create schemas/tables.`
      );
    }

    // Truncate for full refresh
    await client.query(`TRUNCATE TABLE ${fullTable}`);

    // Insert rows
    for (const row of rows) {
      const glideRowId = (row["$rowID"] as string) || null;
      await client.query(
        `INSERT INTO ${fullTable} (glide_row_id, data, ingested_at) VALUES ($1, $2, NOW())`,
        [glideRowId, JSON.stringify(row)]
      );
    }

    await client.query("COMMIT");
    return rows.length;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}

/**
 * Sync Vegas customer data from Glide API
 * Runs every 6 hours to keep data fresh
 */
export const glideVegasSync = inngest.createFunction(
  { id: "glide-vegas-sync", name: "Glide Vegas Sync", concurrency: [DB_CONCURRENCY] },
  { cron: "0 */6 * * *" }, // Every 6 hours
  async ({ step }) => {
    const results: { table: string; status: string; count?: number }[] = [];

    for (const [tableName, tableId] of Object.entries(GLIDE_TABLES)) {
      await step.run(`sync-${tableName}`, async () => {
        try {
          const rows = await fetchGlideTable(tableId);
          const count = await syncTableToPostgres(tableName, rows);
          results.push({ table: tableName, status: "success", count });
        } catch (error) {
          results.push({
            table: tableName,
            status: "error",
            count: 0,
          });
          console.error(`Failed to sync ${tableName}:`, error);
        }
      });
    }

    return {
      status: "complete",
      synced_at: new Date().toISOString(),
      results,
      totalRows: results.reduce((sum, r) => sum + (r.count || 0), 0),
    };
  }
);
