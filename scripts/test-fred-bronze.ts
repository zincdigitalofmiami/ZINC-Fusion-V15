/**
 * FRED Daily Bronze - Manual Test Script
 * 
 * Tests the Bronze ingestion logic without Inngest cron.
 * Run with: npx tsx scripts/test-fred-bronze.ts
 */

import { Pool } from "pg";
import { createHash } from "crypto";
import * as dotenv from "dotenv";

dotenv.config();

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// Test with just 5 series to validate the pattern
const TEST_SERIES = [
  { id: "DFF", name: "Fed Funds Rate", tags: ["fed"] },
  { id: "VIXCLS", name: "VIX Index", tags: ["volatility"] },
  { id: "DCOILWTICO", name: "WTI Crude", tags: ["energy"] },
  { id: "DEXCHUS", name: "USD/CNY", tags: ["fx", "china"] },
  { id: "USEPUINDXD", name: "Policy Uncertainty", tags: ["trump_effect", "volatility"] },
];

function computeRowHash(seriesId: string, date: string, value: number): string {
  const payload = `${seriesId}|${date}|${value}`;
  return createHash("sha256").update(payload).digest("hex");
}

async function main() {
  const client = await pool.connect();
  
  console.log("=".repeat(60));
  console.log("FRED BRONZE INGESTION TEST");
  console.log("=".repeat(60));
  console.log();

  try {
    // Step 1: Create ingest run
    console.log("1. Creating ingest run...");
    const runResult = await client.query(
      `INSERT INTO ops.ingest_run (job_name, status, started_at)
       VALUES ('fred-daily-bronze-TEST', 'running', NOW())
       RETURNING id`
    );
    const runId = runResult.rows[0].id;
    console.log(`   ✅ Created run: ${runId}`);
    console.log();

    // Step 2: Fetch and insert test series
    let inserted = 0;
    let skipped = 0;
    let quarantined = 0;

    for (const series of TEST_SERIES) {
      console.log(`2. Processing ${series.id} (${series.name})...`);

      try {
        // Fetch from FRED
        const apiKey = process.env.FRED_API_KEY;
        if (!apiKey) throw new Error("FRED_API_KEY not set");

        const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${series.id}&api_key=${apiKey}&file_type=json&sort_order=desc&limit=1`;
        const response = await fetch(url);
        const json = await response.json();
        const obs = json.observations?.[0];

        if (!obs || obs.value === ".") {
          console.log(`   ⚠️  No data for ${series.id}`);
          skipped++;
          continue;
        }

        const value = parseFloat(obs.value);
        const rowHash = computeRowHash(series.id, obs.date, value);

        console.log(`   Date: ${obs.date}, Value: ${value}`);
        console.log(`   Hash: ${rowHash.substring(0, 16)}...`);

        // Check for duplicate
        const hashCheck = await client.query(
          `SELECT 1 FROM raw.fred_observations_1d WHERE row_hash = $1 LIMIT 1`,
          [rowHash]
        );

        if (hashCheck.rows.length > 0) {
          console.log(`   ⏭️  Skipped (duplicate hash)`);
          skipped++;
          continue;
        }

        // Check for revision
        const revCheck = await client.query(
          `SELECT revision_no FROM raw.fred_observations_1d 
           WHERE series_id = $1 AND event_date = $2
           ORDER BY revision_no DESC LIMIT 1`,
          [series.id, obs.date]
        );
        const revisionNo = revCheck.rows.length > 0 
          ? revCheck.rows[0].revision_no + 1 
          : 1;

        // Insert
        await client.query(
          `INSERT INTO raw.fred_observations_1d (
             series_id, value, event_date, knowledge_time,
             revision_no, is_preliminary, validation_status,
             source, source_url, ingestion_batch_id,
             row_hash, specialist_tags
           ) VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7, $8, $9, $10, $11)`,
          [
            series.id,
            value,
            obs.date,
            revisionNo,
            false,
            "validated",
            "fred_api",
            `https://fred.stlouisfed.org/series/${series.id}`,
            runId,
            rowHash,
            series.tags,
          ]
        );

        console.log(`   ✅ Inserted (revision ${revisionNo}), tags: [${series.tags.join(", ")}]`);
        inserted++;

      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error);
        console.log(`   ❌ Error: ${errorMsg}`);
        
        // Quarantine
        await client.query(
          `INSERT INTO ops.quarantined_record 
           (ingest_run_id, source_table, raw_payload, validation_errors, severity)
           VALUES ($1, $2, $3, $4, $5)`,
          [runId, "raw.fred_observations_1d", JSON.stringify({ series_id: series.id }), [errorMsg], "error"]
        );
        quarantined++;
      }

      console.log();
    }

    // Step 3: Update ingest run
    console.log("3. Completing ingest run...");
    await client.query(
      `UPDATE ops.ingest_run
       SET status = 'success',
           completed_at = NOW(),
           rows_attempted = $2,
           rows_inserted = $3,
           rows_skipped = $4,
           rows_quarantined = $5
       WHERE id = $1`,
      [runId, TEST_SERIES.length, inserted, skipped, quarantined]
    );
    console.log(`   ✅ Run completed`);
    console.log();

    // Step 4: Verify results
    console.log("4. Verification...");
    console.log("-".repeat(40));

    // Check ingest run
    const runCheck = await client.query(
      `SELECT job_name, status, rows_attempted, rows_inserted, rows_skipped, rows_quarantined
       FROM ops.ingest_run WHERE id = $1`,
      [runId]
    );
    console.log("   Ingest Run:");
    console.table(runCheck.rows);

    // Check recent FRED inserts
    const recentInserts = await client.query(
      `SELECT series_id, event_date::text, value, revision_no, specialist_tags
       FROM raw.fred_observations_1d
       WHERE ingestion_batch_id = $1
       ORDER BY series_id`,
      [runId]
    );
    console.log("   Inserted Records:");
    console.table(recentInserts.rows);

    // Check quarantine
    const quarantineCheck = await client.query(
      `SELECT source_table, validation_errors, severity
       FROM ops.quarantined_record
       WHERE ingest_run_id = $1`,
      [runId]
    );
    if (quarantineCheck.rows.length > 0) {
      console.log("   Quarantined Records:");
      console.table(quarantineCheck.rows);
    } else {
      console.log("   Quarantined: None (good!)");
    }

    console.log();
    console.log("=".repeat(60));
    console.log("TEST COMPLETE");
    console.log("=".repeat(60));
    console.log(`Summary: ${inserted} inserted, ${skipped} skipped, ${quarantined} quarantined`);

  } finally {
    client.release();
    await pool.end();
  }
}

main().catch(console.error);
