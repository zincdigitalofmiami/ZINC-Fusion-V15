#!/usr/bin/env npx tsx
/**
 * backfill-vol-indices.ts
 *
 * One-shot backfill of CBOE vol indices + EMV/EPU trackers from FRED API.
 * Fetches full history for each series and batch-upserts into econ.vol_indices_1d.
 *
 * Usage: cd frontend && npx tsx scripts/backfill-vol-indices.ts
 */

import pg from "pg";
import { createHash } from "crypto";
import { readFileSync } from "fs";

// Load .env.local
try {
  const envContent = readFileSync(".env.local", "utf-8");
  for (const line of envContent.split("\n")) {
    const match = line.match(/^([A-Z_]+)="?([^"]*)"?\s*$/);
    if (match) {
      const key = match[1];
      const val = match[2];
      if (!process.env[key]) {
        process.env[key] = val;
      }
    }
  }
} catch { /* ignore */ }

const DB = process.env.DATABASE_URL;
const FRED_KEY = (process.env.FRED_API_KEY || "").trim();
if (!DB) { console.error("DATABASE_URL not set"); process.exit(1); }
if (!FRED_KEY) { console.error("FRED_API_KEY not set"); process.exit(1); }

const pool = new pg.Pool({ connectionString: DB, ssl: { rejectUnauthorized: false }, max: 3 });

const SERIES = [
  // CBOE cross-asset VIX
  { id: "VXNCLS", name: "CBOE Nasdaq 100 VIX" },
  { id: "RVXCLS", name: "CBOE Russell 2000 VIX" },
  { id: "VXDCLS", name: "CBOE DJIA VIX" },
  { id: "VXEWZCLS", name: "CBOE Brazil ETF VIX" },
  // EMV macro trackers (release 279)
  { id: "EMVOVERALLEMV", name: "EMV: Overall" },
  { id: "WLEMUINDXD", name: "Equity Market Uncertainty (Daily)" },
  { id: "EMVMACROBUS", name: "EMV: Business Outlook" },
  { id: "EMVMACROINFLATION", name: "EMV: Inflation" },
  { id: "EMVMACROINTEREST", name: "EMV: Interest Rates" },
  { id: "EMVEXRATES", name: "EMV: Exchange Rates" },
  { id: "EMVFINCRISES", name: "EMV: Financial Crises" },
  { id: "EMVMONETARYPOL", name: "EMV: Monetary Policy" },
  { id: "EMVCOMMMKT", name: "EMV: Commodity Markets" },
  { id: "INFECTDISEMVTRACKD", name: "EMV: Infectious Disease (Daily)" },
  // EPU categorical indices (release 279)
  { id: "EPUMONETARY", name: "EPU: Monetary Policy" },
  { id: "EPUFISCAL", name: "EPU: Fiscal Policy" },
  { id: "EPUFINREG", name: "EPU: Financial Regulation" },
  { id: "EPUNATSEC", name: "EPU: National Security" },
  { id: "EPUTAXES", name: "EPU: Taxes" },
  { id: "EPUGOVTSPEND", name: "EPU: Government Spending" },
  { id: "EPUSOVDEBT", name: "EPU: Sovereign Debt/Currency" },
  // Global/regional EPU
  { id: "GEPUCURRENT", name: "Global EPU Index" },
  { id: "EUEPUINDXM", name: "Europe EPU Index" },
  { id: "CHNMAINLANDEPU", name: "China EPU Index (Mainland)" },
  // EMV policy trackers
  { id: "EMVELECTGOVRN", name: "EMV: Elections & Governance" },
  { id: "EMVIMMIGRATION", name: "EMV: Immigration" },
  { id: "EMVGOVTSPEND", name: "EMV: Govt Spending & Deficit" },
  { id: "EMVFISCALPOL", name: "EMV: Fiscal Policy" },
  { id: "EMVTAXESEMV", name: "EMV: Taxes" },
  { id: "EMVAGRPOLICY", name: "EMV: Agricultural Policy" },
  { id: "EMVENRGYENVREG", name: "EMV: Energy & Environmental Reg" },
  { id: "EMVNATSEC", name: "EMV: National Security Policy" },
];

interface FredObs { date: string; value: string }

async function backfillSeries(seriesId: string, name: string): Promise<number> {
  const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${seriesId}&api_key=${FRED_KEY}&file_type=json&limit=100000`;
  const res = await fetch(url);
  if (!res.ok) { console.error(`  ${seriesId}: HTTP ${res.status}`); return 0; }
  const data = await res.json() as { observations: FredObs[] };
  const obs = (data.observations || []).filter((o: FredObs) => o.value !== "." && o.value !== "");

  if (obs.length === 0) {
    console.log(`  ${name} (${seriesId}): no valid observations`);
    return 0;
  }

  // Batch insert in chunks of 500
  const client = await pool.connect();
  let inserted = 0;
  const BATCH = 500;
  try {
    for (let i = 0; i < obs.length; i += BATCH) {
      const batch = obs.slice(i, i + BATCH);
      const values: string[] = [];
      const params: (string | number)[] = [];

      for (let r = 0; r < batch.length; r++) {
        const o = batch[r];
        const val = parseFloat(o.value);
        if (!Number.isFinite(val)) continue;
        const rowHash = createHash("sha256").update(`${seriesId}|${o.date}|${o.value}|FRED`).digest("hex");
        const base = values.length * 5;
        values.push(`($${base + 1}, $${base + 2}::date, $${base + 3}, $${base + 4}, $${base + 5})`);
        params.push(seriesId, o.date, val, "FRED", rowHash);
      }

      if (values.length === 0) continue;

      await client.query(
        `INSERT INTO econ.vol_indices_1d (series_id, event_date, value, source, row_hash)
         VALUES ${values.join(",")}
         ON CONFLICT (series_id, event_date) DO UPDATE SET value = EXCLUDED.value, row_hash = EXCLUDED.row_hash`,
        params
      );
      inserted += values.length;
    }
  } finally { client.release(); }
  console.log(`  ${name} (${seriesId}): ${inserted} rows [${obs[0]?.date} → ${obs[obs.length - 1]?.date}]`);
  return inserted;
}

async function main() {
  console.log("=== Vol Indices + EMV/EPU Full Backfill ===");
  console.log(`Series to backfill: ${SERIES.length}`);
  let total = 0;
  for (const s of SERIES) {
    total += await backfillSeries(s.id, s.name);
    await new Promise(r => setTimeout(r, 300)); // FRED rate limit
  }
  console.log(`\nTotal: ${total} rows across ${SERIES.length} series`);

  // Verify new series
  const client = await pool.connect();
  const res = await client.query(
    `SELECT series_id, COUNT(*) as rows, MIN(event_date)::text as first, MAX(event_date)::text as latest
     FROM econ.vol_indices_1d
     WHERE series_id IN (${SERIES.map((_, i) => `$${i + 1}`).join(",")})
     GROUP BY series_id ORDER BY series_id`,
    SERIES.map(s => s.id)
  );
  console.table(res.rows);
  client.release();
  await pool.end();
}

main().catch(e => { console.error(e); process.exit(1); });
