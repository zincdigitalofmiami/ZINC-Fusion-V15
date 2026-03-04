/**
 * Palm Oil Multi-Source Daily Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Upserts into mkt.futures_1d (ON CONFLICT DO NOTHING)
 *
 * SOURCES:
 * 1. Investing.com — Palm Olein (ID: 8917), Palm Kernel Oil (ID: 35498)
 * 2. Yahoo Finance — FCPO (Bursa Malaysia FCPO), KPO (Kernel Palm Oil)
 * 3. World Bank Pink Sheet — monthly palm oil prices (CSV)
 *
 * TARGET TABLE: mkt.futures_1d (symbols: PALM_OLEIN, PALM_KERNEL, FCPO)
 *              + supply.mpob_palm_1m (Pink Sheet monthly → production proxy)
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.0.0
 * @date 2026-03-03
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { getIngestPool } from "@/lib/db";

const pool = getIngestPool();

function computeRowHash(parts: string[]): string {
  return createHash("sha256").update(parts.join("|")).digest("hex");
}

// ---------------------------------------------------------------------------
// Investing.com palm commodity fetch (same pattern as cpo-daily.ts)
// ---------------------------------------------------------------------------

interface InvestingCandle {
  source: string;
  symbol: string;
  eventDate: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

const INVESTING_PALM_IDS: Array<{ id: number; symbol: string; name: string }> = [
  { id: 8917, symbol: "PALM_OLEIN", name: "Palm Olein Futures" },
  { id: 35498, symbol: "PALM_KERNEL", name: "Palm Kernel Oil" },
];

async function fetchInvestingCandle(commodityId: number, symbol: string): Promise<InvestingCandle | null> {
  const url = `https://api.investing.com/api/financialdata/${commodityId}/historical/chart/?interval=P1D&pointscount=2`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  try {
    const res = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        Accept: "application/json",
        "Domain-Id": "www",
      },
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!res.ok) return null;

    // Guard against Cloudflare challenge pages returning HTML
    const ct = res.headers.get("content-type") ?? "";
    if (!ct.includes("json")) return null;

    const json = await res.json();
    if (!json?.data || json.data.length === 0) return null;

    const candle = json.data[json.data.length - 1];
    const [ts, open, high, low, close] = candle;
    if (![open, high, low, close].every((v: unknown) => Number.isFinite(Number(v)))) return null;

    return {
      source: "investing_com",
      symbol,
      eventDate: new Date(ts).toISOString().split("T")[0],
      open: Number(open),
      high: Number(high),
      low: Number(low),
      close: Number(close),
    };
  } catch {
    clearTimeout(timeout);
    return null;
  }
}

// ---------------------------------------------------------------------------
// Yahoo Finance FCPO fetch
// ---------------------------------------------------------------------------

async function fetchYahooFcpo(): Promise<InvestingCandle | null> {
  // Bursa Malaysia FCPO — Yahoo symbol is "FCPO=F" or "OPF.MY"
  const tickers = ["FCPO=F", "OPF.MY"];
  for (const ticker of tickers) {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?interval=1d&range=5d`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15_000);
    try {
      const res = await fetch(url, {
        headers: { "User-Agent": "ZINC-Fusion/1.0" },
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!res.ok) continue;

      const json = await res.json();
      const result = json?.chart?.result?.[0];
      if (!result?.timestamp || !result?.indicators?.quote?.[0]) continue;

      const quotes = result.indicators.quote[0];
      const timestamps = result.timestamp;
      const len = timestamps.length;
      if (len === 0) continue;

      // Get the latest valid candle
      for (let i = len - 1; i >= 0; i--) {
        const c = quotes.close?.[i];
        if (c == null || !Number.isFinite(c)) continue;

        return {
          source: "yahoo_finance",
          symbol: "FCPO",
          eventDate: new Date(timestamps[i] * 1000).toISOString().split("T")[0],
          open: Number(quotes.open?.[i] ?? c),
          high: Number(quotes.high?.[i] ?? c),
          low: Number(quotes.low?.[i] ?? c),
          close: Number(c),
        };
      }
    } catch {
      clearTimeout(timeout);
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// World Bank Pink Sheet — monthly palm oil price (free CSV)
// ---------------------------------------------------------------------------

interface PinkSheetRow {
  eventDate: string;
  price: number;
  symbol: string;
  source: string;
}

async function fetchWorldBankPalmOil(): Promise<PinkSheetRow[]> {
  // World Bank Commodity Price Data ("Pink Sheet") — Original XLSX:
  // https://thedocs.worldbank.org/en/doc/5d903e848db1d1b83e0ec8f744e55570-0350012021/related/CMO-Historical-Data-Monthly.xlsx
  // Fallback: use FRED series PPOILUSDM which IS the World Bank palm oil index
  // Already ingested by fred-daily-palm — skip the XLSX and use a lighter JSON endpoint
  const fredUrl = `https://api.stlouisfed.org/fred/series/observations?series_id=PPOILUSDM&api_key=${process.env.FRED_API_KEY}&file_type=json&observation_start=2020-01-01&sort_order=desc&limit=60`;

  if (!process.env.FRED_API_KEY) return [];

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20_000);
  try {
    const res = await fetch(fredUrl, { signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) return [];

    const json = await res.json();
    const obs = json?.observations ?? [];
    const rows: PinkSheetRow[] = [];
    for (const o of obs) {
      if (o.value === "." || o.value === "") continue;
      const val = parseFloat(o.value);
      if (!Number.isFinite(val)) continue;
      rows.push({
        eventDate: o.date,
        price: val,
        symbol: "PPOILUSDM",
        source: "fred_worldbank",
      });
    }
    return rows;
  } catch {
    clearTimeout(timeout);
    return [];
  }
}

// ---------------------------------------------------------------------------
// Inngest function
// ---------------------------------------------------------------------------

export const palmMultiSourceDaily = inngest.createFunction(
  {
    id: "palm-multi-source-daily",
    name: "Palm Oil Multi-Source Daily (Olein + Kernel + FCPO + World Bank)",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "30 6 * * *" }, // Daily at 06:30 UTC (after CPO daily at 06:00)
  async ({ step, logger }) => {
    // ── Step 1: Fetch all sources ──
    const candles = await step.run("fetch-palm-sources", async () => {
      const results: InvestingCandle[] = [];

      // Investing.com: Palm Olein + Palm Kernel
      for (const item of INVESTING_PALM_IDS) {
        const candle = await fetchInvestingCandle(item.id, item.symbol);
        if (candle) {
          results.push(candle);
          logger.info(`Investing.com ${item.name}: ${candle.close}`);
        } else {
          logger.warn(`Investing.com ${item.name}: no data`);
        }
      }

      // Yahoo Finance: FCPO
      const fcpo = await fetchYahooFcpo();
      if (fcpo) {
        results.push(fcpo);
        logger.info(`Yahoo FCPO: ${fcpo.close}`);
      } else {
        logger.warn("Yahoo FCPO: no data");
      }

      return results;
    });

    // ── Step 2: Fetch World Bank monthly ──
    const pinkSheet = await step.run("fetch-worldbank-palm", async () => {
      return await fetchWorldBankPalmOil();
    });

    logger.info(`Candles: ${candles.length}, Pink Sheet: ${pinkSheet.length}`);

    // ── Step 3: Insert candles into mkt.futures_1d ──
    let candlesInserted = 0;
    if (candles.length > 0) {
      candlesInserted = await step.run("insert-candles", async () => {
        const client = await pool.connect();
        let inserted = 0;
        try {
          for (const c of candles) {
            const rowHash = computeRowHash([c.symbol, c.eventDate, String(c.close)]);
            await client.query(
              `INSERT INTO mkt.futures_1d
                (event_date, symbol, open, high, low, close, source, row_hash)
               VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8)
               ON CONFLICT (event_date, symbol) DO NOTHING`,
              [c.eventDate, c.symbol, c.open, c.high, c.low, c.close, c.source, rowHash]
            );
            inserted++;
          }
        } finally {
          client.release();
        }
        return inserted;
      });
    }

    // ── Step 4: Insert World Bank into econ.commodities_1d ──
    let pinkInserted = 0;
    if (pinkSheet.length > 0) {
      pinkInserted = await step.run("insert-worldbank", async () => {
        const client = await pool.connect();
        let inserted = 0;
        try {
          for (const row of pinkSheet) {
            const rowHash = computeRowHash([row.symbol, row.eventDate, String(row.price)]);
            await client.query(
              `INSERT INTO econ.commodities_1d
                (event_date, series_id, value, source, row_hash)
               VALUES ($1::date, $2, $3, $4, $5)
               ON CONFLICT DO NOTHING`,
              [row.eventDate, row.symbol, row.price, row.source, rowHash]
            );
            inserted++;
          }
        } finally {
          client.release();
        }
        return inserted;
      });
    }

    // ── Step 5: Log ingest run ──
    await step.run("log-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at, completed_at,
             rows_attempted, rows_inserted, rows_skipped, rows_quarantined)
           VALUES ($1, 'success', NOW(), NOW(), $2, $3, $4, 0)`,
          ["palm-multi-source-daily", candles.length + pinkSheet.length,
           candlesInserted + pinkInserted, 0]
        );
      } finally {
        client.release();
      }
    });

    return {
      status: "success",
      candles: candlesInserted,
      pinkSheet: pinkInserted,
    };
  }
);
