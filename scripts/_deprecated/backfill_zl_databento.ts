/**
 * Backfill ZL daily data from Databento
 *
 * Run: npx tsx scripts/backfill_zl_databento.ts
 */

import 'dotenv/config';
import { Pool } from 'pg';

const DATABENTO_API_KEY = process.env.DATABENTO_API_KEY;
const DATABENTO_BASE_URL = "https://hist.databento.com/v0/timeseries.get_range";

if (!DATABENTO_API_KEY) {
  throw new Error("DATABENTO_API_KEY not set in environment");
}

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

function basicAuthHeader(): string {
  const token = Buffer.from(`${DATABENTO_API_KEY}:`).toString("base64");
  return `Basic ${token}`;
}

async function fetchDatabentoCsv(params: Record<string, string>): Promise<string> {
  const body = new URLSearchParams(params);

  const res = await fetch(DATABENTO_BASE_URL, {
    method: "POST",
    headers: {
      Authorization: basicAuthHeader(),
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body.toString(),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Databento API error ${res.status}: ${text}`);
  }

  return await res.text();
}

function parseTimestamp(value: string): Date | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const dt = new Date(trimmed);
  if (Number.isNaN(dt.getTime())) return null;
  return dt;
}

interface OhlcvBar {
  tsEvent: Date;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

function parseDatabentoOhlcvCsv(csv: string): OhlcvBar[] {
  const lines = csv
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));

  if (lines.length < 2) return [];

  const header = lines[0].split(",");
  const idx = {
    ts_event: header.indexOf("ts_event"),
    open: header.indexOf("open"),
    high: header.indexOf("high"),
    low: header.indexOf("low"),
    close: header.indexOf("close"),
    volume: header.indexOf("volume"),
  };

  if (idx.ts_event === -1 || idx.open === -1 || idx.high === -1 || idx.low === -1 || idx.close === -1) {
    throw new Error("Databento CSV missing required OHLCV columns");
  }

  const bars: OhlcvBar[] = [];
  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",");
    if (parts.length < header.length) continue;

    const ts = parseTimestamp(parts[idx.ts_event]);
    if (!ts) continue;

    const open = Number(parts[idx.open]);
    const high = Number(parts[idx.high]);
    const low = Number(parts[idx.low]);
    const close = Number(parts[idx.close]);
    const volume = idx.volume >= 0 ? Number(parts[idx.volume]) || 0 : 0;

    if (!Number.isFinite(open) || !Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(close)) {
      continue;
    }

    bars.push({ tsEvent: ts, open, high, low, close, volume });
  }

  bars.sort((a, b) => a.tsEvent.getTime() - b.tsEvent.getTime());
  return bars;
}

async function main() {
  console.log("Fetching ZL daily data from Databento...");

  // Fetch from Dec 1, 2025 to today (use T00:00:00Z for end to match Databento's available range)
  const startDate = "2025-12-01";
  const endDate = new Date().toISOString().split("T")[0];

  console.log(`Date range: ${startDate} to ${endDate}`);

  const csv = await fetchDatabentoCsv({
    dataset: "GLBX.MDP3",
    schema: "ohlcv-1d",
    symbols: "ZL.n.0",
    stype_in: "continuous",
    start: `${startDate}T00:00:00Z`,
    end: `${endDate}T00:00:00Z`,  // Use T00:00:00Z to match Databento availability
    encoding: "csv",
    pretty_ts: "true",
    pretty_px: "true",
  });

  const bars = parseDatabentoOhlcvCsv(csv);
  console.log(`Fetched ${bars.length} bars from Databento`);

  if (bars.length === 0) {
    console.log("No bars to insert");
    return;
  }

  // Insert into analytics.zl_price_1d
  const client = await pool.connect();
  let inserted = 0;
  let skipped = 0;

  try {
    for (const bar of bars) {
      const eventDate = new Date(Date.UTC(
        bar.tsEvent.getUTCFullYear(),
        bar.tsEvent.getUTCMonth(),
        bar.tsEvent.getUTCDate()
      ));

      const result = await client.query(
        `INSERT INTO analytics.zl_price_1d
          (event_date, open, high, low, close, volume, source, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, 'databento', NOW())
         ON CONFLICT (event_date) DO UPDATE SET
           open = EXCLUDED.open,
           high = EXCLUDED.high,
           low = EXCLUDED.low,
           close = EXCLUDED.close,
           volume = EXCLUDED.volume,
           source = EXCLUDED.source
         RETURNING (xmax = 0) as is_insert`,
        [eventDate, bar.open, bar.high, bar.low, bar.close, bar.volume]
      );

      if (result.rows[0]?.is_insert) {
        inserted++;
      } else {
        skipped++;
      }
    }

    console.log(`Done: ${inserted} inserted, ${skipped} updated/skipped`);

    // Verify final state
    const verify = await client.query(`
      SELECT COUNT(*) as total, MIN(event_date) as min, MAX(event_date) as max
      FROM analytics.zl_price_1d
      WHERE source = 'databento' AND event_date >= '2025-12-01'
    `);
    console.log("Verification:", verify.rows[0]);

  } finally {
    client.release();
    await pool.end();
  }
}

main().catch(console.error);
