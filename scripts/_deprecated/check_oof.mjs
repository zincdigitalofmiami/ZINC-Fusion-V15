import { config } from 'dotenv';
config();
import { PrismaClient, Prisma } from './prisma/generated/prisma/index.js';

const DEFAULT_CHECK_DAYS = 30;
const DEFAULT_CHECK_DAYS_OOF = 180;
const REQUIRED_HORIZONS = [5, 21, 63, 126];

function parseCheckDays() {
  const raw = Number.parseInt(process.env.CHECK_DAYS ?? `${DEFAULT_CHECK_DAYS}`, 10);
  return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_CHECK_DAYS;
}

function parseCheckDaysOof() {
  const raw = Number.parseInt(process.env.CHECK_DAYS_OOF ?? `${DEFAULT_CHECK_DAYS_OOF}`, 10);
  return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_CHECK_DAYS_OOF;
}

function formatTable(schema, table) {
  return `${schema}.${table}`;
}

async function tableExists(prisma, schema, table) {
  const rows = await prisma.$queryRaw`
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = ${schema}
      AND table_name = ${table}
    LIMIT 1
  `;
  return rows.length > 0;
}

async function getColumns(prisma, schema, table) {
  const rows = await prisma.$queryRaw`
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = ${schema}
      AND table_name = ${table}
  `;
  return rows.map((row) => row.column_name);
}

async function requireTableColumns(prisma, schema, table, requiredColumns, errors) {
  const fullName = formatTable(schema, table);
  const exists = await tableExists(prisma, schema, table);
  if (!exists) {
    errors.push(`Missing table: ${fullName}`);
    return null;
  }
  const columns = await getColumns(prisma, schema, table);
  const columnSet = new Set(columns);
  const missing = requiredColumns.filter((col) => !columnSet.has(col));
  if (missing.length > 0) {
    errors.push(`Missing required columns in ${fullName}: ${missing.join(', ')}`);
    return null;
  }
  return columnSet;
}

function reportResults(errors, warnings) {
  if (warnings.length > 0) {
    console.warn('\n=== WARNINGS ===');
    warnings.forEach((warning) => console.warn(`- ${warning}`));
  }
  if (errors.length > 0) {
    console.error('\n=== VALIDATION FAILURES ===');
    errors.forEach((error) => console.error(`- ${error}`));
    process.exitCode = 1;
  } else {
    console.log('\nAll checks passed.');
  }
}

async function check() {
  const prisma = new PrismaClient({ accelerateUrl: process.env.PRISMA_DATABASE_URL });
  const checkDays = parseCheckDays();
  const checkDaysOof = parseCheckDaysOof();
  const errors = [];
  const warnings = [];

  try {
    const oofColumns = await requireTableColumns(
      prisma,
      'training',
      'oof_core_1d',
      ['trade_date', 'horizon_days', 'p30', 'p50', 'p70'],
      errors
    );

    if (!oofColumns || errors.length > 0) {
      reportResults(errors, warnings);
      return;
    }

    const rowCount = await prisma.$queryRaw`
      SELECT COUNT(*)::int as row_count
      FROM training.oof_core_1d
      WHERE trade_date >= (CURRENT_DATE - (${checkDaysOof} * INTERVAL '1 day'))
    `;
    const oofRows = rowCount[0]?.row_count ?? 0;
    console.log(`\nOOF Core rows (last ${checkDaysOof} days):`, oofRows);
    if (oofRows === 0) {
      errors.push(`No rows found in training.oof_core_1d for last ${checkDaysOof} days.`);
    }

    const horizonSummary = await prisma.$queryRaw`
      SELECT
        horizon_days::int as horizon_days,
        COUNT(*)::int as row_count,
        MIN(trade_date)::date as earliest,
        MAX(trade_date)::date as latest,
        SUM(CASE WHEN p30 IS NULL THEN 1 ELSE 0 END)::int as null_p30,
        SUM(CASE WHEN p50 IS NULL THEN 1 ELSE 0 END)::int as null_p50,
        SUM(CASE WHEN p70 IS NULL THEN 1 ELSE 0 END)::int as null_p70
      FROM training.oof_core_1d
      WHERE trade_date >= (CURRENT_DATE - (${checkDaysOof} * INTERVAL '1 day'))
      GROUP BY horizon_days
      ORDER BY horizon_days
    `;
    const presentHorizons = new Set(horizonSummary.map((row) => row.horizon_days));
    const missingHorizons = REQUIRED_HORIZONS.filter((h) => !presentHorizons.has(h));
    console.log('\n=== OOF CORE HORIZON SUMMARY (WINDOWED) ===');
    console.table(horizonSummary);
    if (missingHorizons.length > 0) {
      errors.push(`Missing horizon_days in training.oof_core_1d window: ${missingHorizons.join(', ')}`);
    }

    const nullIssues = horizonSummary.filter(
      (row) =>
        REQUIRED_HORIZONS.includes(row.horizon_days) &&
        (row.null_p30 > 0 || row.null_p50 > 0 || row.null_p70 > 0)
    );
    if (nullIssues.length > 0) {
      errors.push('Null quantiles found in training.oof_core_1d for required horizons (see summary).');
    }

    reportResults(errors, warnings);
  } catch (e) {
    console.error('Error:', e.message);
    process.exitCode = 1;
  } finally {
    await prisma.$disconnect();
  }
}

check();
