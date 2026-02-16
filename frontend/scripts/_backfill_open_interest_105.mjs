import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import pg from 'pg';

const { Pool } = pg;

function parseDotEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  const raw = fs.readFileSync(filePath, 'utf8');
  for (const line of raw.split(/\r?\n/)) {
    const s = line.trim();
    if (!s || s.startsWith('#') || !s.includes('=')) continue;
    const i = s.indexOf('=');
    const k = s.slice(0, i).trim();
    let v = s.slice(i + 1).trim();
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      v = v.slice(1, -1);
    }
    if (!(k in process.env)) process.env[k] = v;
  }
}

function getDirectDbUrl() {
  const url = process.env.DIRECT_DATABASE_URL || process.env.POSTGRES_URL || process.env.DATABASE_URL;
  if (!url) throw new Error('No DB URL found (DIRECT_DATABASE_URL/POSTGRES_URL/DATABASE_URL)');
  if (url.startsWith('prisma+postgres://')) {
    throw new Error('Invalid DB URL: prisma+postgres:// (Accelerate) is not compatible with pg client.');
  }
  return url;
}

function ymd(d) {
  return d.toISOString().split('T')[0];
}

function basicAuthHeader(apiKey) {
  return `Basic ${Buffer.from(`${apiKey}:`).toString('base64')}`;
}

async function fetchDatabentoCsv(params, apiKey, timeoutMs = 180_000) {
  const body = new URLSearchParams(params);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch('https://hist.databento.com/v0/timeseries.get_range', {
      method: 'POST',
      headers: {
        Authorization: basicAuthHeader(apiKey),
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: body.toString(),
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Databento API ${res.status}: ${text.slice(0, 400)}`);
    }
    return await res.text();
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchWithRetry(params, apiKey, retries = 3) {
  let lastErr;
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      return await fetchDatabentoCsv(params, apiKey, 180_000);
    } catch (err) {
      lastErr = err;
      if (attempt === retries) break;
      const backoffMs = attempt * 2000;
      await new Promise((r) => setTimeout(r, backoffMs));
    }
  }
  throw lastErr;
}

async function upsertOiRows(client, symbol, rows) {
  if (!rows.length) return 0;

  const BATCH = 2000;
  let total = 0;

  for (let i = 0; i < rows.length; i += BATCH) {
    const chunk = rows.slice(i, i + BATCH);
    const dates = chunk.map((r) => r.eventDate);
    const symbols = chunk.map(() => symbol);
    const ois = chunk.map((r) => r.openInterest);

    await client.query(
      `INSERT INTO mkt.futures_1d
        (event_date, symbol, open_interest, source, ingested_at)
       SELECT u.event_date, u.symbol, u.open_interest, 'databento', NOW()
       FROM UNNEST($1::date[], $2::text[], $3::bigint[]) AS u(event_date, symbol, open_interest)
       ON CONFLICT (event_date, symbol) DO UPDATE SET
         open_interest = EXCLUDED.open_interest,
         source = 'databento',
         ingested_at = NOW()`,
      [dates, symbols, ois],
    );

    total += chunk.length;
  }

  return total;
}

async function main() {
  const frontendDir = process.cwd();
  const rootDir = path.resolve(frontendDir, '..');
  parseDotEnvFile(path.join(rootDir, '.env'));
  parseDotEnvFile(path.join(frontendDir, '.env'));

  const dbUrl = getDirectDbUrl();
  const apiKey = process.env.DATABENTO_API_KEY;
  if (!apiKey) throw new Error('DATABENTO_API_KEY not set');

  const databentoLib = await import(pathToFileURL(path.resolve(frontendDir, 'src/lib/databento.ts')).href);
  const parseDatabentoStatisticsCsv = databentoLib.parseDatabentoStatisticsCsv;

  const pool = new Pool({ connectionString: dbUrl, ssl: { rejectUnauthorized: false } });
  const client = await pool.connect();

  const endDate = new Date();
  endDate.setUTCHours(0, 0, 0, 0);

  const startedAt = new Date();
  console.log(`[start] ${startedAt.toISOString()} | endDate=${endDate.toISOString()}`);

  try {
    const beforeRes = await client.query(`SELECT COUNT(*)::bigint AS c FROM mkt.futures_1d WHERE open_interest IS NOT NULL`);
    const beforeCount = Number(beforeRes.rows[0].c);

    const symbolsRes = await client.query(`
      SELECT symbol, MIN(event_date)::date AS min_date, MAX(event_date)::date AS max_date
      FROM mkt.futures_1d
      GROUP BY symbol
      ORDER BY symbol
    `);

    const toUtcDate = (value) => {
      if (!value) return null;
      if (value instanceof Date) {
        return new Date(Date.UTC(
          value.getUTCFullYear(),
          value.getUTCMonth(),
          value.getUTCDate(),
        ));
      }
      const text = String(value).slice(0, 10);
      const parsed = new Date(`${text}T00:00:00Z`);
      return Number.isNaN(parsed.getTime()) ? null : parsed;
    };

    const universe = symbolsRes.rows
      .map((r) => ({
        symbol: String(r.symbol),
        minDate: toUtcDate(r.min_date),
        maxDate: toUtcDate(r.max_date),
      }))
      .filter((r) => r.minDate !== null);

    console.log(`[universe] symbols=${universe.length}`);

    const results = [];
    let totalUpserted = 0;

    for (const [idx, item] of universe.entries()) {
      const { symbol, minDate } = item;
      const continuous = (symbol === 'ZL' || symbol === 'ZS' || symbol === 'ZM')
        ? `${symbol}.n.0`
        : `${symbol}.c.0`;

      const startDate = minDate > endDate ? endDate : minDate;

      const params = {
        dataset: 'GLBX.MDP3',
        schema: 'statistics',
        symbols: continuous,
        stype_in: 'continuous',
        start: startDate.toISOString(),
        end: endDate.toISOString(),
        encoding: 'csv',
        pretty_ts: 'true',
        pretty_px: 'true',
      };

      const prefix = `[${idx + 1}/${universe.length}] ${symbol} (${continuous})`;
      process.stdout.write(`${prefix} fetch ${ymd(startDate)}..${ymd(endDate)} ... `);

      try {
        const csv = await fetchWithRetry(params, apiKey, 3);
        const bars = parseDatabentoStatisticsCsv(csv);

        if (!bars.length) {
          console.log('no_data');
          results.push({ symbol, status: 'no_data', rows: 0 });
          continue;
        }

        const byDate = new Map();
        for (const b of bars) {
          const d = ymd(new Date(Date.UTC(
            b.tsEvent.getUTCFullYear(),
            b.tsEvent.getUTCMonth(),
            b.tsEvent.getUTCDate(),
          )));
          byDate.set(d, Math.floor(b.openInterest));
        }

        const rows = [...byDate.entries()]
          .sort((a, b) => (a[0] < b[0] ? -1 : 1))
          .map(([eventDate, openInterest]) => ({ eventDate, openInterest }));

        const upserted = await upsertOiRows(client, symbol, rows);
        totalUpserted += upserted;

        console.log(`ok bars=${bars.length} unique_days=${rows.length} upserted=${upserted}`);
        results.push({ symbol, status: 'success', rows: upserted });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.log(`error ${msg}`);
        results.push({ symbol, status: 'error', rows: 0, error: msg });
      }
    }

    const afterRes = await client.query(`SELECT COUNT(*)::bigint AS c FROM mkt.futures_1d WHERE open_interest IS NOT NULL`);
    const afterCount = Number(afterRes.rows[0].c);

    const success = results.filter((r) => r.status === 'success').length;
    const noData = results.filter((r) => r.status === 'no_data').length;
    const error = results.filter((r) => r.status === 'error').length;

    console.log('\n[summary]');
    console.log(`symbols_total=${universe.length}`);
    console.log(`success=${success} no_data=${noData} error=${error}`);
    console.log(`rows_upserted_total=${totalUpserted}`);
    console.log(`open_interest_not_null_before=${beforeCount}`);
    console.log(`open_interest_not_null_after=${afterCount}`);
    console.log(`open_interest_not_null_delta=${afterCount - beforeCount}`);

    if (error > 0) {
      console.log('\n[errors]');
      for (const r of results.filter((x) => x.status === 'error')) {
        console.log(`${r.symbol}: ${r.error}`);
      }
    }
  } finally {
    client.release();
    await pool.end();
  }

  const endedAt = new Date();
  console.log(`\n[done] ${endedAt.toISOString()} duration_sec=${Math.round((endedAt - startedAt) / 1000)}`);
}

main().catch((err) => {
  console.error('[fatal]', err);
  process.exit(1);
});
