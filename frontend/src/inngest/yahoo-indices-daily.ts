/**
 * Yahoo Finance Indices Daily
 *
 * Dedicated daily fetch for VIX and DX (ICE US Dollar Index) from Yahoo Finance.
 *
 * These are NOT covered by Databento (GLBX.MDP3 = CME only; DX trades on ICE)
 * and FRED only provides close (no OHLCV). Yahoo gives full OHLCV + volume.
 *
 * Writes to mkt.futures_1d:
 *   - VIX  (^VIX)    — CBOE Volatility Index
 *   - DX   (DX-Y.NYB) — ICE US Dollar Index futures
 *
 * NOTE: symbol "DXY" in mkt.futures_1d is contaminated (FRED DTWEXBGS ~118
 * mixed with Yahoo DX ~97, two different instruments). This job writes to
 * symbol "DX" which is the correct ICE Dollar Index.
 *
 * Cron: daily at 01:00 CT (after US market close + settlement)
 * Event: yahoo.indices.daily (for manual trigger / backfill)
 */

import { createHash } from "crypto";
import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

// ---------------------------------------------------------------------------
//  Symbol config
// ---------------------------------------------------------------------------
interface YahooIndexConfig {
  /** Symbol written to mkt.futures_1d */
  dbSymbol: string;
  /** Yahoo Finance ticker */
  yahooTicker: string;
  /** Human-readable name for logging */
  name: string;
}

const INDICES: YahooIndexConfig[] = [
  { dbSymbol: "VIX", yahooTicker: "^VIX", name: "CBOE VIX" },
  { dbSymbol: "DX", yahooTicker: "DX-Y.NYB", name: "ICE US Dollar Index" },
];

// ---------------------------------------------------------------------------
//  Yahoo v8 chart API fetch
// ---------------------------------------------------------------------------
interface YahooBar {
  eventDate: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

function toDateStringUtc(epochSeconds: number): string {
  const dt = new Date(epochSeconds * 1000);
  return new Date(
    Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth(), dt.getUTCDate()),
  )
    .toISOString()
    .slice(0, 10);
}

async function fetchYahooBars(
  ticker: string,
  range: string,
): Promise<YahooBar[]> {
  const url = new URL(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}`,
  );
  url.searchParams.set("interval", "1d");
  url.searchParams.set("range", range);

  const res = await fetch(url.toString(), {
    headers: { "User-Agent": "Mozilla/5.0" },
  });

  if (!res.ok) {
    throw new Error(`Yahoo ${ticker} HTTP ${res.status}: ${await res.text()}`);
  }

  const json = (await res.json()) as {
    chart?: {
      result?: Array<{
        timestamp?: number[];
        indicators?: {
          quote?: Array<{
            open?: Array<number | null>;
            high?: Array<number | null>;
            low?: Array<number | null>;
            close?: Array<number | null>;
            volume?: Array<number | null>;
          }>;
        };
      }>;
    };
  };

  const result = json.chart?.result?.[0];
  const quote = result?.indicators?.quote?.[0];
  const timestamps = result?.timestamp ?? [];
  if (!quote || timestamps.length === 0) return [];

  const bars: YahooBar[] = [];
  for (let i = 0; i < timestamps.length; i++) {
    const close = quote.close?.[i];
    if (close == null || !Number.isFinite(close) || close <= 0) continue;

    bars.push({
      eventDate: toDateStringUtc(timestamps[i]),
      open: quote.open?.[i] ?? null,
      high: quote.high?.[i] ?? null,
      low: quote.low?.[i] ?? null,
      close,
      volume: quote.volume?.[i] ?? null,
    });
  }

  // Deduplicate by date (keep last)
  const byDate = new Map<string, YahooBar>();
  for (const bar of bars) {
    byDate.set(bar.eventDate, bar);
  }
  return [...byDate.values()].sort((a, b) =>
    a.eventDate < b.eventDate ? -1 : 1,
  );
}

// ---------------------------------------------------------------------------
//  DB upsert — matches mkt.futures_1d schema exactly
// ---------------------------------------------------------------------------
function computeRowHash(
  symbol: string,
  eventDate: string,
  close: number,
): string {
  return createHash("sha256")
    .update(`${symbol}|${eventDate}|${close}|yahoo_eod`)
    .digest("hex");
}

async function upsertBars(
  symbol: string,
  bars: YahooBar[],
  source: string,
): Promise<number> {
  const client = await pool.connect();
  let written = 0;
  try {
    for (const bar of bars) {
      const rowHash = computeRowHash(symbol, bar.eventDate, bar.close);
      await client.query(
        `INSERT INTO mkt.futures_1d
           (event_date, symbol, open, high, low, close, volume, source, ingested_at, row_hash)
         VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, NOW(), $9)
         ON CONFLICT (event_date, symbol) DO UPDATE SET
           open     = COALESCE(EXCLUDED.open, mkt.futures_1d.open),
           high     = COALESCE(EXCLUDED.high, mkt.futures_1d.high),
           low      = COALESCE(EXCLUDED.low, mkt.futures_1d.low),
           close    = EXCLUDED.close,
           volume   = COALESCE(EXCLUDED.volume, mkt.futures_1d.volume),
           source   = EXCLUDED.source,
           ingested_at = NOW(),
           row_hash = EXCLUDED.row_hash`,
        [
          bar.eventDate,
          symbol,
          bar.open,
          bar.high,
          bar.low,
          bar.close,
          bar.volume,
          source,
          rowHash,
        ],
      );
      written++;
    }
  } finally {
    client.release();
  }
  return written;
}

// ---------------------------------------------------------------------------
//  Inngest function — daily cron + manual event trigger
// ---------------------------------------------------------------------------
export const yahooIndicesDaily = inngest.createFunction(
  {
    id: "yahoo-indices-daily",
    name: "Yahoo VIX + DX Daily",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  [
    { cron: "TZ=America/Chicago 0 1 * * *" }, // 01:00 CT daily
    { event: "yahoo.indices.daily" },
  ],
  async ({ event, step, logger }) => {
    // Allow backfill range override via event data (default: 14d for cron)
    const range =
      (event?.data as { range?: string } | undefined)?.range ?? "14d";
    const source = "yahoo_eod";

    const results: Array<{
      symbol: string;
      status: "success" | "error" | "no_data";
      bars?: number;
      error?: string;
    }> = [];

    for (const idx of INDICES) {
      await step.run(`fetch-${idx.dbSymbol}`, async () => {
        try {
          const bars = await fetchYahooBars(idx.yahooTicker, range);
          if (bars.length === 0) {
            logger.warn(`${idx.name}: no data from Yahoo (range=${range})`);
            results.push({ symbol: idx.dbSymbol, status: "no_data" });
            return;
          }

          const written = await upsertBars(idx.dbSymbol, bars, source);
          logger.info(
            `${idx.name}: upserted ${written} bars [${bars[0].eventDate} → ${bars[bars.length - 1].eventDate}]`,
          );
          results.push({
            symbol: idx.dbSymbol,
            status: "success",
            bars: written,
          });
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          logger.error(`${idx.name}: ${msg}`);
          results.push({ symbol: idx.dbSymbol, status: "error", error: msg });
        }
      });
    }

    return {
      status: "complete",
      timestamp: new Date().toISOString(),
      range,
      results,
    };
  },
);
