import { config } from 'dotenv';
config();
import { PrismaClient, Prisma } from './prisma/generated/prisma/index.js';

const BIG11_BUCKETS = [
  'crush',
  'china',
  'fx',
  'fed',
  'tariff',
  'energy',
  'biofuel',
  'palm',
  'volatility',
  'substitutes',
  'trump_effect',
];

const DEFAULT_CHECK_DAYS = 30;

function parseCheckDays() {
  const raw = Number.parseInt(process.env.CHECK_DAYS ?? `${DEFAULT_CHECK_DAYS}`, 10);
  return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_CHECK_DAYS;
}

function formatTable(schema, table) {
  return `${schema}.${table}`;
}

function isSafeIdentifier(value) {
  return /^[a-z_][a-z0-9_]*$/.test(value);
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
  const errors = [];
  const warnings = [];

  try {
    const signalColumns = await requireTableColumns(
      prisma,
      'training',
      'specialist_signals_1d',
      ['as_of_date', 'bucket', 'signal_1'],
      errors
    );
    const matrixColumns = await requireTableColumns(
      prisma,
      'training',
      'matrix_1d',
      ['trade_date'],
      errors
    );

    if (errors.length > 0) {
      reportResults(errors, warnings);
      return;
    }

    const forbiddenSignalColumns = ['horizon', 'horizon_days'];
    const presentForbiddenSignalColumns = forbiddenSignalColumns.filter((col) => signalColumns.has(col));
    if (presentForbiddenSignalColumns.length > 0) {
      errors.push(
        `Forbidden horizon columns present in training.specialist_signals_1d: ${presentForbiddenSignalColumns.join(', ')}`
      );
    }

    const signalsWindowStats = await prisma.$queryRaw`
      SELECT
        COUNT(*)::int as rows,
        COUNT(DISTINCT as_of_date)::int as days
      FROM training.specialist_signals_1d
      WHERE as_of_date >= (CURRENT_DATE - (${checkDays} * INTERVAL '1 day'))
    `;
    const signalRows = signalsWindowStats[0]?.rows ?? 0;
    const signalDays = signalsWindowStats[0]?.days ?? 0;
    console.log(`\nSignals window rows (last ${checkDays} days):`, signalRows);
    console.log(`Signals window distinct days:`, signalDays);
    if (signalRows === 0) {
      errors.push(`No rows found in training.specialist_signals_1d for last ${checkDays} days.`);
    }

    const signalFreshness = await prisma.$queryRaw`
      SELECT MAX(as_of_date)::date as max_as_of_date
      FROM training.specialist_signals_1d
      WHERE as_of_date >= (CURRENT_DATE - (${checkDays} * INTERVAL '1 day'))
    `;
    console.log('Signals max as_of_date (windowed):', signalFreshness[0]?.max_as_of_date ?? 'n/a');

    const bucketStats = await prisma.$queryRaw`
      SELECT
        LOWER(bucket) as bucket,
        COUNT(*)::int as rows,
        COUNT(DISTINCT as_of_date)::int as days
      FROM training.specialist_signals_1d
      WHERE as_of_date >= (CURRENT_DATE - (${checkDays} * INTERVAL '1 day'))
      GROUP BY LOWER(bucket)
      ORDER BY bucket
    `;
    console.log('\n=== SPECIALIST SIGNALS BUCKET COVERAGE ===');
    console.table(bucketStats);

    const presentBuckets = new Set(bucketStats.map((row) => row.bucket));
    const missingBuckets = BIG11_BUCKETS.filter((bucket) => !presentBuckets.has(bucket));
    if (missingBuckets.length > 0) {
      errors.push(`Missing buckets in training.specialist_signals_1d window: ${missingBuckets.join(', ')}`);
    }

    const unexpectedBuckets = bucketStats
      .map((row) => row.bucket)
      .filter((bucket) => !BIG11_BUCKETS.includes(bucket));
    if (unexpectedBuckets.length > 0) {
      warnings.push(`Unexpected buckets present: ${unexpectedBuckets.join(', ')}`);
    }

    if (signalDays >= 5) {
      const lowCoverage = bucketStats
        .map((row) => ({
          bucket: row.bucket,
          ratio: signalDays > 0 ? row.days / signalDays : 0,
          days: row.days,
        }))
        .filter((row) => row.ratio < 0.5);
      if (lowCoverage.length > 0) {
        warnings.push(
          `Low bucket coverage (<50% of days): ${lowCoverage
            .map((row) => `${row.bucket} (${row.days}/${signalDays})`)
            .join(', ')}`
        );
      }
    }

    const duplicateRows = await prisma.$queryRaw`
      SELECT
        as_of_date::date as as_of_date,
        LOWER(bucket) as bucket,
        COUNT(*)::int as dupes
      FROM training.specialist_signals_1d
      WHERE as_of_date >= (CURRENT_DATE - (${checkDays} * INTERVAL '1 day'))
      GROUP BY as_of_date, LOWER(bucket)
      HAVING COUNT(*) > 1
      ORDER BY as_of_date DESC, bucket
      LIMIT 5
    `;
    if (duplicateRows.length > 0) {
      errors.push('Duplicate rows detected in training.specialist_signals_1d (sample shown below).');
      console.log('\n=== DUPLICATE SIGNAL ROWS (SAMPLE) ===');
      console.table(duplicateRows);
    }

    const nullSignalCount = await prisma.$queryRaw`
      SELECT COUNT(*)::int as null_count
      FROM training.specialist_signals_1d
      WHERE as_of_date >= (CURRENT_DATE - (${checkDays} * INTERVAL '1 day'))
        AND signal_1 IS NULL
    `;
    if ((nullSignalCount[0]?.null_count ?? 0) > 0) {
      errors.push(`Null signal_1 rows found in training.specialist_signals_1d window: ${nullSignalCount[0].null_count}`);
    }

    const requiredSigColumns = BIG11_BUCKETS.map((bucket) => `sig_${bucket}_1`);
    const missingSigColumns = requiredSigColumns.filter((col) => !matrixColumns.has(col));
    if (missingSigColumns.length > 0) {
      errors.push(`Missing required sig columns in training.matrix_1d: ${missingSigColumns.join(', ')}`);
      reportResults(errors, warnings);
      return;
    }

    const optionalSigColumns = [
      ...BIG11_BUCKETS.map((bucket) => `sig_${bucket}_2`),
      ...BIG11_BUCKETS.map((bucket) => `sig_${bucket}_conf`),
    ];
    const missingOptional = optionalSigColumns.filter((col) => !matrixColumns.has(col));
    if (missingOptional.length > 0) {
      warnings.push(`Optional sig columns missing in training.matrix_1d: ${missingOptional.join(', ')}`);
    }

    const matrixWindowCount = await prisma.$queryRaw`
      SELECT COUNT(*)::int as row_count
      FROM training.matrix_1d
      WHERE trade_date >= (CURRENT_DATE - (${checkDays} * INTERVAL '1 day'))
    `;
    const matrixRows = matrixWindowCount[0]?.row_count ?? 0;
    console.log(`\nMatrix window rows (last ${checkDays} days):`, matrixRows);
    if (matrixRows === 0) {
      errors.push(`No rows found in training.matrix_1d for last ${checkDays} days.`);
    }

    const matrixFreshness = await prisma.$queryRaw`
      SELECT MAX(trade_date)::date as max_trade_date
      FROM training.matrix_1d
      WHERE trade_date >= (CURRENT_DATE - (${checkDays} * INTERVAL '1 day'))
    `;
    console.log('Matrix max trade_date (windowed):', matrixFreshness[0]?.max_trade_date ?? 'n/a');

    for (const column of requiredSigColumns) {
      if (!isSafeIdentifier(column)) {
        errors.push(`Unsafe column name detected for query: ${column}`);
        continue;
      }
      const nullCount = await prisma.$queryRaw`
        SELECT COUNT(*)::int as null_count
        FROM training.matrix_1d
        WHERE trade_date >= (CURRENT_DATE - (${checkDays} * INTERVAL '1 day'))
          AND ${Prisma.raw(column)} IS NULL
      `;
      if ((nullCount[0]?.null_count ?? 0) > 0) {
        errors.push(`Null values found in training.matrix_1d.${column} for last ${checkDays} days: ${nullCount[0].null_count}`);
      }
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
