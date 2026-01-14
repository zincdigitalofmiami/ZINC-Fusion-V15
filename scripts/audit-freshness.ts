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
  console.log(`Today: ${new Date().toISOString().slice(0, 10)}`);
  console.log("=".repeat(70));
  console.log();

  const tables: Array<{
    table: string;
    eventColumn: string;
    ingestedColumn: string;
  }> = [
    { table: "fred_observations_1d", eventColumn: "event_date", ingestedColumn: "created_at" },
    { table: "market_futures_1d", eventColumn: "event_date", ingestedColumn: "ingested_at" },
    { table: "market_futures_1h", eventColumn: "event_time", ingestedColumn: "created_at" },
    { table: "cftc_cot_1w", eventColumn: "event_date", ingestedColumn: "ingested_at" },
    { table: "yahoo_equity_1d", eventColumn: "event_date", ingestedColumn: "created_at" },
    { table: "fx_spot_1d", eventColumn: "event_date", ingestedColumn: "created_at" },
    { table: "epa_rin_prices_1d", eventColumn: "event_date", ingestedColumn: "created_at" },
  ];

  for (const t of tables) {
    const r = await client.query(`
      SELECT 
        MAX(${t.ingestedColumn}) as latest_ingested,
        MAX(${t.eventColumn}) as latest_event_date,
        COUNT(*)::int as total_rows
      FROM raw.${t.table}
    `);
    
    const row = r.rows[0];
    console.log(`${t.table}:`);
    console.log(`  Latest ingested:    ${row.latest_ingested}`);
    console.log(`  Latest event_date:  ${row.latest_event_date}`);
    console.log(`  Total rows:         ${row.total_rows?.toLocaleString()}`);
    console.log();
  }

  client.release();
  await pool.end();
}

audit().catch(console.error);
