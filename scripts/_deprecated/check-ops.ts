/**
 * Quick DB check for fred-daily ingestion run
 * @deprecated Use Inngest dashboard instead
 */
import { Pool } from "pg";
import * as dotenv from "dotenv";
dotenv.config();

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

async function check() {
  const client = await pool.connect();
  
  console.log("=== OPS.INGEST_RUN - Latest Runs ===\n");
  
  const runs = await client.query(`
    SELECT job_name, status, started_at, completed_at, 
           rows_inserted, rows_skipped, rows_quarantined, error_message
    FROM ops.ingest_run 
    ORDER BY started_at DESC 
    LIMIT 5
  `);
  
  console.table(runs.rows);
  
  client.release();
  await pool.end();
}

check().catch(console.error);
