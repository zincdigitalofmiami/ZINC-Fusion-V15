// Database Audit Script - Using pg directly
// Run with: npx tsx scripts/audit-db-pg.ts

import { Client } from 'pg';
import * as dotenv from 'dotenv';

dotenv.config();

const client = new Client({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

async function main() {
  await client.connect();
  
  console.log('='.repeat(70));
  console.log('ZINC-FUSION-V15 DATABASE AUDIT');
  console.log('='.repeat(70));
  console.log();

  // A. Database Identity
  console.log('A. DATABASE IDENTITY');
  console.log('-'.repeat(40));
  const identity = await client.query(`
    SELECT current_database() AS db,
           current_user AS "user",
           inet_server_addr()::text AS host,
           inet_server_port() AS port
  `);
  console.table(identity.rows);

  // B. Table Inventory with Row Counts
  console.log('\nB. TABLE INVENTORY (approx rows)');
  console.log('-'.repeat(40));
  const inventory = await client.query(`
    SELECT schemaname || '.' || relname AS table_name,
           n_live_tup AS approx_rows
    FROM pg_stat_user_tables
    WHERE schemaname IN ('raw','silver','gold','training','model','analytics','ops','metadata')
    ORDER BY schemaname, n_live_tup DESC
  `);
  console.table(inventory.rows);

  // C. Prisma Migration Status
  console.log('\nC. PRISMA MIGRATION TABLE');
  console.log('-'.repeat(40));
  try {
    const migrations = await client.query(`
      SELECT migration_name, finished_at, applied_steps_count, rolled_back_at
      FROM _prisma_migrations
      ORDER BY finished_at NULLS LAST, migration_name
    `);
    console.table(migrations.rows);
  } catch (e) {
    console.log('No _prisma_migrations table found (DB-truth mode)');
  }

  // D1. PIT Column Coverage
  console.log('\nD1. BRONZE PIT COLUMN COVERAGE (raw schema)');
  console.log('-'.repeat(40));
  const pitCoverage = await client.query(`
    SELECT table_name,
           SUM(CASE WHEN column_name IN ('event_date','event_time') THEN 1 ELSE 0 END)::int AS has_event,
           SUM(CASE WHEN column_name='knowledge_time' THEN 1 ELSE 0 END)::int AS has_knowledge,
           SUM(CASE WHEN column_name='row_hash' THEN 1 ELSE 0 END)::int AS has_row_hash,
           SUM(CASE WHEN column_name='revision_no' THEN 1 ELSE 0 END)::int AS has_revision,
           SUM(CASE WHEN column_name='supersedes_id' THEN 1 ELSE 0 END)::int AS has_supersedes,
           SUM(CASE WHEN column_name='specialist_tags' THEN 1 ELSE 0 END)::int AS has_tags,
           SUM(CASE WHEN column_name='validation_status' THEN 1 ELSE 0 END)::int AS has_validation
    FROM information_schema.columns
    WHERE table_schema='raw'
    GROUP BY table_name
    ORDER BY table_name
  `);
  console.table(pitCoverage.rows);

  // D2. Unique Constraints (upsert-forcing)
  console.log('\nD2. UNIQUE CONSTRAINTS IN RAW (upsert risk)');
  console.log('-'.repeat(40));
  const uniques = await client.query(`
    SELECT t.relname AS table_name,
           i.relname AS index_name,
           pg_get_indexdef(ix.indexrelid) AS index_def
    FROM pg_index ix
    JOIN pg_class t ON t.oid = ix.indrelid
    JOIN pg_class i ON i.oid = ix.indexrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'raw'
      AND ix.indisunique = TRUE
      AND i.relname NOT LIKE '%_pkey'
    ORDER BY t.relname, i.relname
  `);
  if (uniques.rows.length === 0) {
    console.log('✅ No non-PK unique constraints found - append-only safe!');
  } else {
    console.log('⚠️  Found unique constraints that may force upsert:');
    console.table(uniques.rows);
  }

  // D3. Row Hash Indexes
  console.log('\nD3. ROW_HASH INDEXES');
  console.log('-'.repeat(40));
  const hashIndexes = await client.query(`
    SELECT t.relname AS table_name,
           i.relname AS index_name
    FROM pg_index ix
    JOIN pg_class t ON t.oid = ix.indrelid
    JOIN pg_class i ON i.oid = ix.indexrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname='raw'
      AND i.relname ILIKE '%row_hash%'
    ORDER BY t.relname
  `);
  console.table(hashIndexes.rows);

  // F. Ops Infrastructure Check
  console.log('\nF. OPS INFRASTRUCTURE STATUS');
  console.log('-'.repeat(40));
  
  const ingestRunCount = await client.query(`
    SELECT COUNT(*)::int AS total_runs,
           COUNT(*) FILTER (WHERE status = 'running')::int AS running,
           COUNT(*) FILTER (WHERE status = 'success')::int AS success,
           COUNT(*) FILTER (WHERE status = 'failed')::int AS failed
    FROM ops.ingest_run
  `);
  console.log('Ingest Runs:');
  console.table(ingestRunCount.rows);

  const quarantineCount = await client.query(`
    SELECT COUNT(*)::int AS total_quarantined,
           COUNT(*) FILTER (WHERE resolution_status = 'pending')::int AS pending,
           COUNT(*) FILTER (WHERE resolution_status = 'resolved')::int AS resolved
    FROM ops.quarantined_record
  `);
  console.log('Quarantined Records:');
  console.table(quarantineCount.rows);

  // G. FRED Observations Quick Check
  console.log('\nG. FRED OBSERVATIONS SAMPLE (top 15 series by row count)');
  console.log('-'.repeat(40));
  const fredSample = await client.query(`
    SELECT series_id, 
           MIN(event_date)::text AS earliest,
           MAX(event_date)::text AS latest,
           COUNT(*)::int AS rows
    FROM raw.fred_observations_1d
    GROUP BY series_id
    ORDER BY rows DESC
    LIMIT 15
  `);
  console.table(fredSample.rows);

  // H. Summary counts
  console.log('\nH. SUMMARY COUNTS');
  console.log('-'.repeat(40));
  const summaryCounts = await client.query(`
    SELECT 
      (SELECT COUNT(*) FROM raw.fred_observations_1d) AS fred_rows,
      (SELECT COUNT(*) FROM raw.market_futures_1d) AS market_1d_rows,
      (SELECT COUNT(*) FROM raw.market_futures_1h) AS market_1h_rows,
      (SELECT COUNT(*) FROM raw.cftc_cot_1w) AS cftc_rows,
      (SELECT COUNT(*) FROM raw.fx_spot_1d) AS fx_rows
  `);
  console.table(summaryCounts.rows);

  console.log('\n' + '='.repeat(70));
  console.log('AUDIT COMPLETE');
  console.log('='.repeat(70));

  await client.end();
}

main().catch(console.error);
