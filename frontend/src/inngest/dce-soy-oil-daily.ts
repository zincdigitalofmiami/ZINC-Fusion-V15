/**
 * DCE Soybean Oil Daily Ingestion
 *
 * Fetches Dalian Commodity Exchange soybean oil futures price.
 * Source: Investing.com unofficial API (same pattern as CPO).
 *
 * NOTE: Investing.com blocks requests from residential IPs (Cloudflare).
 * This function works on Vercel server IPs but NOT from local dev.
 * For local testing, use Docker Inngest + the backfill event.
 *
 * Symbol: DCE_Y (mkt.futures_1d)
 * Schedule: Daily at 05:30 UTC (DCE closes ~15:00 CST = 07:00 UTC)
 * Table: mkt.futures_1d
 */

import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

// Investing.com asset ID for Dalian Soybean Oil Futures
// If this ID stops working, try: 49777, 8918, 12618
const INVESTING_ASSET_ID = 12617;

interface OhlcData {
  source: string;
  eventDate: string;
  open?: number;
  high?: number;
  low?: number;
  close: number;
}

async function fetchFromInvestingCom(): Promise<OhlcData | null> {
  const url = `https://api.investing.com/api/financialdata/${INVESTING_ASSET_ID}/historical/chart/?interval=P1D&pointscount=5`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  let res: Response;
  try {
    res = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        Accept: "application/json",
        "Domain-Id": "www",
      },
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeout);
    if (err instanceof Error && err.name === "AbortError") {
      console.warn("[DCE_Y] Investing.com API timed out after 15s");
      return null;
    }
    console.warn(`[DCE_Y] Investing.com fetch error: ${err}`);
    return null;
  }
  clearTimeout(timeout);

  if (!res.ok) {
    console.warn(`[DCE_Y] Investing.com API error: ${res.status}`);
    return null;
  }

  const json = await res.json();
  if (!json?.data || json.data.length === 0) {
    console.warn("[DCE_Y] Investing.com returned empty data");
    return null;
  }

  const latestCandle = json.data[json.data.length - 1];
  const [timestamp, open, high, low, close] = latestCandle;
  if (![open, high, low, close].every((v: unknown) => Number.isFinite(Number(v)))) {
    console.warn("[DCE_Y] Invalid OHLC values in response");
    return null;
  }
  const eventDate = new Date(timestamp).toISOString().split("T")[0];

  return {
    source: "investing_com",
    eventDate,
    open: Number(open),
    high: Number(high),
    low: Number(low),
    close: Number(close),
  };
}

export const dceSoyOilDaily = inngest.createFunction(
  {
    id: "dce-soy-oil-daily",
    name: "DCE Soybean Oil Daily",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "30 5 * * 1-5" }, // Weekdays at 05:30 UTC
  async ({ step, logger }) => {
    const data = await step.run("fetch-dce-soy-oil", async () => {
      logger.info("[DCE_Y] Fetching from Investing.com...");
      const result = await fetchFromInvestingCom();
      if (result) {
        logger.info(`[DCE_Y] Got price: ${result.close} for ${result.eventDate}`);
        return result;
      }
      logger.warn("[DCE_Y] Investing.com unavailable for this run");
      return null;
    });

    if (!data) {
      return { status: "upstream_unavailable", inserted: 0 };
    }

    const result = await step.run("insert-dce-soy-oil", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `INSERT INTO mkt.futures_1d
            (event_date, symbol, open, high, low, close, source, ingested_at)
           VALUES ($1, 'DCE_Y', $2, $3, $4, $5, $6, NOW())
           ON CONFLICT (event_date, symbol) DO UPDATE SET
             open = COALESCE(EXCLUDED.open, mkt.futures_1d.open),
             high = COALESCE(EXCLUDED.high, mkt.futures_1d.high),
             low = COALESCE(EXCLUDED.low, mkt.futures_1d.low),
             close = EXCLUDED.close,
             source = EXCLUDED.source,
             ingested_at = NOW()`,
          [data.eventDate, data.open, data.high, data.low, data.close, data.source],
        );
        return { status: "success", source: data.source, date: data.eventDate, close: data.close };
      } finally {
        client.release();
      }
    });

    logger.info("[DCE_Y] Daily update complete", result);
    return result;
  },
);
