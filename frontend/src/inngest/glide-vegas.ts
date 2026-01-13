import { inngest } from "./client";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// Glide API Configuration
const GLIDE_API_ENDPOINT = "https://api.glideapp.io/api/function/queryTables";
const GLIDE_APP_ID = "6nvONp42nj5tLQmMcqF3";
const GLIDE_BEARER_TOKEN =
  process.env.GLIDE_BEARER_TOKEN || "460c9ee4-edcb-43cc-86b5-929e2bb94351";

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
  const fullTable = `ops.vegas_${tableName}`;

  try {
    await client.query("BEGIN");

    // Create schema if not exists
    await client.query("CREATE SCHEMA IF NOT EXISTS ops");

    // Create table if not exists
    await client.query(`
      CREATE TABLE IF NOT EXISTS ${fullTable} (
        id SERIAL PRIMARY KEY,
        glide_row_id TEXT,
        data JSONB NOT NULL,
        ingested_at TIMESTAMPTZ DEFAULT NOW()
      )
    `);

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
  { id: "glide-vegas-sync", name: "Glide Vegas Sync" },
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
