// Database Audit Script for Bronze Contract Verification
// Run with: node scripts/audit-db.mjs

import { PrismaClient } from '../prisma/generated/prisma/index.js';

const prisma = new PrismaClient();

async function main() {
  console.log('='.repeat(70));
  console.log('ZINC-FUSION-V15 DATABASE AUDIT');
  console.log('='.repeat(70));
  console.log();

  // A. Database Identity
  console.log('A. DATABASE IDENTITY');
  console.log('-'.repeat(40));
  const identity = await prisma.$queryRaw`
    SELECT current_database() AS db,
           current_user AS "user",
           inet_server_addr()::text AS host,
           inet_server_port() AS port
  `;
  console.table(identity);

  // B. Table Inventory with Row Counts
  console.log('\nB. TABLE INVENTORY (approx rows)');
  console.log('-'.repeat(40));
  const inventory = await prisma.$queryRaw`
    SELECT schemaname || '.' || relname AS table_name,
           n_live_tup AS approx_rows
    FROM pg_stat_user_tables
    WHERE schemaname IN ('mkt','econ','alt','pos','supply','features','training','model','forecasts','analytics','ops','metadata')
    ORDER BY schemaname, n_live_tup DESC
  `;
  console.table(inventory);

  // C. Prisma Migration Status
  console.log('\nC. PRISMA MIGRATION TABLE');
  console.log('-'.repeat(40));
  try {
    const migrations = await prisma.$queryRaw`
      SELECT migration_name, finished_at, applied_steps_count, rolled_back_at
      FROM _prisma_migrations
      ORDER BY finished_at NULLS LAST, migration_name
    `;
    console.table(migrations);
  } catch (e) {
    console.log('No _prisma_migrations table found (DB-truth mode)');
  }

  // D1. PIT Column Coverage
  console.log('\nD1. BRONZE PIT COLUMN COVERAGE (landing schemas)');
  console.log('-'.repeat(40));
  const pitCoverage = await prisma.$queryRaw`
    SELECT table_schema || '.' || table_name AS table_name,
           SUM(CASE WHEN column_name IN ('event_date','event_time') THEN 1 ELSE 0 END)::int AS has_event,
           SUM(CASE WHEN column_name='knowledge_time' THEN 1 ELSE 0 END)::int AS has_knowledge,
           SUM(CASE WHEN column_name='row_hash' THEN 1 ELSE 0 END)::int AS has_row_hash,
           SUM(CASE WHEN column_name='revision_no' THEN 1 ELSE 0 END)::int AS has_revision,
           SUM(CASE WHEN column_name='supersedes_id' THEN 1 ELSE 0 END)::int AS has_supersedes,
           SUM(CASE WHEN column_name='specialist_tags' THEN 1 ELSE 0 END)::int AS has_tags,
           SUM(CASE WHEN column_name='validation_status' THEN 1 ELSE 0 END)::int AS has_validation
    FROM information_schema.columns
    WHERE table_schema IN ('mkt','econ','alt','pos','supply')
    GROUP BY table_schema, table_name
    ORDER BY table_schema, table_name
  `;
  console.table(pitCoverage);

  // D2. Unique Constraints (upsert-forcing)
  console.log('\nD2. UNIQUE CONSTRAINTS IN LANDING SCHEMAS (upsert risk)');
  console.log('-'.repeat(40));
  const uniques = await prisma.$queryRaw`
    SELECT n.nspname || '.' || t.relname AS table_name,
           i.relname AS index_name,
           pg_get_indexdef(ix.indexrelid) AS index_def
    FROM pg_index ix
    JOIN pg_class t ON t.oid = ix.indrelid
    JOIN pg_class i ON i.oid = ix.indexrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname IN ('mkt','econ','alt','pos','supply')
      AND ix.indisunique = TRUE
      AND i.relname NOT LIKE '%_pkey'
    ORDER BY n.nspname, t.relname, i.relname
  `;
  if (uniques.length === 0) {
    console.log('✅ No non-PK unique constraints found - append-only safe!');
  } else {
    console.log('⚠️  Found unique constraints that may force upsert:');
    console.table(uniques);
  }

  // D3. Row Hash Indexes
  console.log('\nD3. ROW_HASH INDEXES');
  console.log('-'.repeat(40));
  const hashIndexes = await prisma.$queryRaw`
    SELECT n.nspname || '.' || t.relname AS table_name,
           i.relname AS index_name
    FROM pg_index ix
    JOIN pg_class t ON t.oid = ix.indrelid
    JOIN pg_class i ON i.oid = ix.indexrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname IN ('mkt','econ','alt','pos','supply')
      AND i.relname ILIKE '%row_hash%'
    ORDER BY n.nspname, t.relname
  `;
  console.table(hashIndexes);

  // F. Ops Infrastructure Check
  console.log('\nF. OPS INFRASTRUCTURE STATUS');
  console.log('-'.repeat(40));
  
  // Check ingest_run exists and count
  const ingestRunCount = await prisma.$queryRaw`
    SELECT COUNT(*)::int AS total_runs,
           COUNT(*) FILTER (WHERE status = 'running')::int AS running,
           COUNT(*) FILTER (WHERE status = 'success')::int AS success,
           COUNT(*) FILTER (WHERE status = 'failed')::int AS failed
    FROM ops.ingest_run
  `;
  console.log('Ingest Runs:');
  console.table(ingestRunCount);

  // Check quarantined_record
  const quarantineCount = await prisma.$queryRaw`
    SELECT COUNT(*)::int AS total_quarantined,
           COUNT(*) FILTER (WHERE resolution_status = 'pending')::int AS pending,
           COUNT(*) FILTER (WHERE resolution_status = 'resolved')::int AS resolved
    FROM ops.quarantined_record
  `;
  console.log('Quarantined Records:');
  console.table(quarantineCount);

  // G. Economic Data Sample (FRED Rates)
  console.log('\nG. ECONOMIC DATA SAMPLE (econ.rates_1d)');
  console.log('-'.repeat(40));
  const econSample = await prisma.$queryRaw`
    SELECT series_id,
           MIN(event_date)::text AS earliest,
           MAX(event_date)::text AS latest,
           COUNT(*)::int AS rows
    FROM econ.rates_1d
    GROUP BY series_id
    ORDER BY rows DESC
    LIMIT 10
  `;
  console.table(econSample);

  console.log('\n' + '='.repeat(70));
  console.log('AUDIT COMPLETE');
  console.log('='.repeat(70));
}

main()
  .catch(console.error)
  .finally(() => prisma.$disconnect());
