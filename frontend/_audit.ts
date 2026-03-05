import fs from 'fs';
import pg from 'pg';

// Manual env load (no dotenv dep)
const envContent = fs.readFileSync('.env.local', 'utf8');
for (const line of envContent.split('\n')) {
  const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=["']?(.*?)["']?\s*$/);
  if (match) process.env[match[1]] = match[2];
}

const pool = new pg.Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

const PREFERRED_DATE_COLUMNS = [
  'event_date',
  'trade_date',
  'report_month',
  'as_of_date',
  'week_ending',
  'forecast_date',
  'event_time',
  'deadline_date',
  'timestamp',
  'report_date',
  'prediction_date',
  'signed_date',
];

type TableRow = { s: string; t: string };
type CountRow = { c: string };
type ColumnRow = { column_name: string };
type MaxDateRow = { mx: string | null };

type AuditTableResult =
  | { full: string; error: string }
  | { full: string; rowCount: number; dateCol: string; maxDate: string; stale: string };

async function listUserTables(client: pg.PoolClient): Promise<TableRow[]> {
  const tables = await client.query<TableRow>(`
    SELECT table_schema AS s, table_name AS t
    FROM information_schema.tables
    WHERE table_type = 'BASE TABLE'
      AND table_schema NOT IN ('pg_catalog', 'information_schema', 'public')
    ORDER BY table_schema, table_name
  `);
  return tables.rows;
}

async function getRowCount(client: pg.PoolClient, schema: string, table: string): Promise<number> {
  const result = await client.query<CountRow>(`SELECT COUNT(*) AS c FROM "${schema}"."${table}"`);
  return parseInt(result.rows[0].c, 10);
}

async function getDateColumns(client: pg.PoolClient, schema: string, table: string): Promise<string[]> {
  const cols = await client.query<ColumnRow>(`
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = $1 AND table_name = $2
      AND (data_type LIKE '%date%' OR data_type LIKE '%timestamp%')
    ORDER BY ordinal_position
  `, [schema, table]);
  return cols.rows.map((c) => c.column_name);
}

function pickDateColumn(columns: string[]): string {
  for (const preferred of PREFERRED_DATE_COLUMNS) {
    if (columns.includes(preferred)) return preferred;
  }
  return columns[0];
}

async function getMaxDateText(
  client: pg.PoolClient,
  schema: string,
  table: string,
  column: string
): Promise<string | null | 'ERR'> {
  try {
    const result = await client.query<MaxDateRow>(`SELECT MAX("${column}")::text AS mx FROM "${schema}"."${table}"`);
    return result.rows[0].mx;
  } catch {
    return 'ERR';
  }
}

function computeStaleText(rawTimestamp: string): string {
  const days = Math.floor((Date.now() - new Date(rawTimestamp).getTime()) / 86400000);
  return `${days}d ago`;
}

function renderAuditRow(result: AuditTableResult): void {
  if ('error' in result) {
    console.log(`${result.full.padEnd(43)}| ERR: ${result.error.substring(0, 60)}`);
    return;
  }

  console.log(
    `${result.full.padEnd(43)}| ${String(result.rowCount).padStart(6)} | ${result.dateCol.padEnd(20)} | ${result.maxDate.padEnd(12)} | ${result.stale}`
  );
}

async function auditTable(client: pg.PoolClient, schema: string, table: string): Promise<AuditTableResult> {
  const full = `${schema}.${table}`;

  let rowCount = 0;
  try {
    rowCount = await getRowCount(client, schema, table);
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    return { full, error: message };
  }

  const dateColumns = await getDateColumns(client, schema, table);
  if (dateColumns.length === 0) {
    if (rowCount === 0) {
      return { full, rowCount, dateCol: '-', maxDate: 'EMPTY', stale: '** NO DATA **' };
    }
    return { full, rowCount, dateCol: '-', maxDate: 'no date col', stale: '' };
  }

  const dateCol = pickDateColumn(dateColumns);
  if (rowCount === 0) {
    return { full, rowCount, dateCol, maxDate: 'EMPTY', stale: '** NO DATA **' };
  }

  const maxDateRaw = await getMaxDateText(client, schema, table, dateCol);
  if (maxDateRaw === 'ERR') {
    return { full, rowCount, dateCol, maxDate: 'ERR', stale: '' };
  }
  if (!maxDateRaw) {
    return { full, rowCount, dateCol, maxDate: 'ALL NULL', stale: '' };
  }

  return {
    full,
    rowCount,
    dateCol,
    maxDate: maxDateRaw.substring(0, 10),
    stale: computeStaleText(maxDateRaw),
  };
}

async function audit() {
  const client = await pool.connect();
  try {
    const tables = await listUserTables(client);

    console.log('=== FULL DATABASE FRESHNESS AUDIT ===');
    console.log('SCHEMA.TABLE                               |   ROWS | DATE COL             | MAX DATE     | STALENESS');
    console.log('-'.repeat(110));

    for (const table of tables) {
      const result = await auditTable(client, table.s, table.t);
      renderAuditRow(result);
    }
  } finally {
    client.release();
    await pool.end();
  }
}

audit().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
