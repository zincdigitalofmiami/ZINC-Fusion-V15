/**
 * Data Freshness Audit
 */
import { Pool } from "pg";
import * as dotenv from "dotenv";
dotenv.config();

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

async function audit() {
  const client = await pool.connect();
  
  console.log("=".repeat(70));
  console.log("DATA FRESHNESS AUDIT - Source Verification");
  console.log("Today: 2026-01-11 (Sunday)");
  console.log("=".repeat(70));
  console.log();

  const tables = [
    "fred_observations_1d",
    "market_futures_1d",
    "market_futures_1h",
    "cftc_cot_1w",
    "yahoo_equity_1d",
    "fx_spot_1d",
    "epa_rin_prices_1d",
  ];

  for (const t of tables) {
    const r = await client.query(`
      SELECT 
        MAX(created_at) as latest_created,
        MAX(event_date) as latest_event_date,
        COUNT(*)::int as total_rows
      FROM raw.${t}
    `);
    
    const row = r.rows[0];
    console.log(`${t}:`);
    console.log(`  Latest created_at:  ${row.latest_created}`);
    console.log(`  Latest event_date:  ${row.latest_event_date}`);
    console.log(`  Total rows:         ${row.total_rows?.toLocaleString()}`);
    console.log();
  }

  client.release();
  await pool.end();
}

audit().catch(console.error);
