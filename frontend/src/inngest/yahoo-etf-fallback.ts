/**
 * Yahoo Finance ETF Fallback Daily
 *
 * Provides a Yahoo Finance fallback for ETF OHLCV data when Databento fails
 * or is unavailable. Runs 1 hour after the Databento ETF cron (9 PM ET vs
 * 8 PM ET) and only inserts rows for dates that Databento did not cover.
 *
 * Writes to mkt.etf_1d with source = 'yahoo'.
 * Does NOT overwrite existing Databento rows (source precedence: databento > yahoo).
 *
 * Triggers:
 *   Cron:  daily 21:00 ET (weekdays) — 14-day rolling window gap-fill
 *   Event: etf/yahoo-fallback         — manual trigger, optional { range: "3mo" }
 *   Event: etf/yahoo-backfill         — backfill, optional { symbols?: string[], days?: number }
 *
 * 23 ETFs across 9 categories — same universe as databento-etf-daily.ts
 */

import { createHash } from "crypto";
import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

// ---------------------------------------------------------------------------
//  ETF config — symbol + Yahoo ticker + specialist tags
// ---------------------------------------------------------------------------
interface EtfConfig {
  /** Symbol written to mkt.etf_1d */
  symbol: string;
  /** Yahoo Finance ticker (same as symbol for ETFs) */
  yahooTicker: string;
  /** Human-readable name */
  name: string;
  /** Specialist tags for this ETF */
  tags: string[];
}

const ETF_SYMBOLS: EtfConfig[] = [
  // China Complex
  { symbol: "FXI",  yahooTicker: "FXI",  name: "iShares China Large-Cap",        tags: ["china"] },
  { symbol: "MCHI", yahooTicker: "MCHI", name: "iShares MSCI China",             tags: ["china"] },
  { symbol: "KWEB", yahooTicker: "KWEB", name: "KraneShares China Internet",     tags: ["china"] },

  // Precious Metals
  { symbol: "GLD", yahooTicker: "GLD", name: "SPDR Gold",                        tags: ["substitutes"] },
  { symbol: "SLV", yahooTicker: "SLV", name: "iShares Silver",                   tags: ["substitutes"] },

  // Shipping
  { symbol: "BDRY", yahooTicker: "BDRY", name: "Breakwave Dry Bulk Shipping",    tags: ["china", "tariff"] },
  { symbol: "GOEX", yahooTicker: "GOEX", name: "Global X Gold Explorers",        tags: ["china", "tariff"] },

  // Energy
  { symbol: "USO", yahooTicker: "USO", name: "United States Oil Fund",           tags: ["energy", "biofuel"] },
  { symbol: "UNG", yahooTicker: "UNG", name: "United States Natural Gas",        tags: ["energy", "biofuel"] },
  { symbol: "XLE", yahooTicker: "XLE", name: "Energy Select Sector SPDR",        tags: ["energy", "biofuel"] },
  { symbol: "XOP", yahooTicker: "XOP", name: "SPDR Oil & Gas Exploration",       tags: ["energy", "biofuel"] },
  { symbol: "OIH", yahooTicker: "OIH", name: "VanEck Oil Services",             tags: ["energy", "biofuel"] },

  // Treasuries
  { symbol: "TLT", yahooTicker: "TLT", name: "iShares 20+ Year Treasury",       tags: ["fed"] },
  { symbol: "IEF", yahooTicker: "IEF", name: "iShares 7-10 Year Treasury",       tags: ["fed"] },

  // Broad Market
  { symbol: "SPY", yahooTicker: "SPY", name: "SPDR S&P 500",                     tags: ["volatility"] },
  { symbol: "QQQ", yahooTicker: "QQQ", name: "Invesco QQQ (Nasdaq 100)",         tags: ["volatility"] },

  // Ag Commodities
  { symbol: "DBA",  yahooTicker: "DBA",  name: "Invesco DB Agriculture",         tags: ["crush", "substitutes"] },
  { symbol: "CORN", yahooTicker: "CORN", name: "Teucrium Corn",                  tags: ["crush", "substitutes"] },
  { symbol: "WEAT", yahooTicker: "WEAT", name: "Teucrium Wheat",                 tags: ["crush", "substitutes"] },
  { symbol: "SOYB", yahooTicker: "SOYB", name: "Teucrium Soybean",              tags: ["crush", "substitutes"] },

  // Dollar
  { symbol: "UUP", yahooTicker: "UUP", name: "Invesco DB US Dollar",             tags: ["fx"] },

  // Green Energy
  { symbol: "ICLN", yahooTicker: "ICLN", name: "iShares Global Clean Energy",    tags: ["biofuel", "energy"] },
  { symbol: "TAN",  yahooTicker: "TAN",  name: "Invesco Solar",                  tags: ["biofuel", "energy"] },
  { symbol: "LIT",  yahooTicker: "LIT",  name: "Global X Lithium & Battery",     tags: ["biofuel", "energy"] },
];

// ---------------------------------------------------------------------------
//  Yahoo v8 chart API — response types and parser
// ---------------------------------------------------------------------------
interface YahooBar {
  eventDate: string; // YYYY-MM-DD
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

type YahooChartResponse = {
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

function toDateStringUtc(epochSeconds: number): string {
  const dt = new Date(epochSeconds * 1000);
  return new Date(
    Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth(), dt.getUTCDate()),
  )
    .toISOString()
    .slice(0, 10);
}

function parseBars(json: YahooChartResponse): YahooBar[] {
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
//  Yahoo v8 fetch helpers
// ---------------------------------------------------------------------------

/** Fetch with `range` param (e.g. "14d", "3mo") — good for short windows */
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

  // 422 = no data available — skip gracefully
  if (res.status === 422) return [];

  if (!res.ok) {
    throw new Error(`Yahoo ${ticker} HTTP ${res.status}: ${await res.text()}`);
  }
  return parseBars((await res.json()) as YahooChartResponse);
}

/** Fetch with explicit period1/period2 UNIX timestamps — daily resolution for any window */
async function fetchYahooPeriod(
  ticker: string,
  period1: number,
  period2: number,
): Promise<YahooBar[]> {
  const url = new URL(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}`,
  );
  url.searchParams.set("interval", "1d");
  url.searchParams.set("period1", String(period1));
  url.searchParams.set("period2", String(period2));

  const res = await fetch(url.toString(), {
    headers: { "User-Agent": "Mozilla/5.0" },
  });

  // 422 = no data for period (e.g. ticker didn't exist yet) — not fatal
  if (res.status === 422) return [];

  if (!res.ok) {
    throw new Error(`Yahoo ${ticker} HTTP ${res.status}: ${await res.text()}`);
  }
  return parseBars((await res.json()) as YahooChartResponse);
}

// ---------------------------------------------------------------------------
//  Row hash + DB upsert for mkt.etf_1d
// ---------------------------------------------------------------------------

function computeRowHash(
  symbol: string,
  eventDate: string,
  open: number | null,
  high: number | null,
  low: number | null,
  close: number,
  volume: number | null,
): string {
  const hashInput = `${symbol}|${eventDate}|${open ?? ""}|${high ?? ""}|${low ?? ""}|${close}|${volume ?? ""}`;
  return createHash("sha256").update(hashInput).digest("hex");
}

/**
 * Check which dates already have data for a symbol in mkt.etf_1d.
 * Returns a Set of YYYY-MM-DD strings that already have rows (any source).
 */
async function getExistingDates(
  symbol: string,
  since: string,
): Promise<Set<string>> {
  const client = await pool.connect();
  try {
    const result = await client.query(
      `SELECT event_date::text AS d
       FROM mkt.etf_1d
       WHERE symbol = $1
         AND event_date >= $2::date
         AND close IS NOT NULL`,
      [symbol, since],
    );
    return new Set(result.rows.map((r: { d: string }) => r.d.slice(0, 10)));
  } finally {
    client.release();
  }
}

/**
 * Upsert a single Yahoo bar into mkt.etf_1d.
 * Uses ON CONFLICT ... DO UPDATE only when the existing row is also from yahoo
 * (source precedence: databento > yahoo — never overwrite databento).
 */
async function upsertYahooBar(
  symbol: string,
  bar: YahooBar,
  specialistTags: string[],
): Promise<void> {
  const rowHash = computeRowHash(
    symbol,
    bar.eventDate,
    bar.open,
    bar.high,
    bar.low,
    bar.close,
    bar.volume,
  );

  const client = await pool.connect();
  try {
    await client.query(
      `INSERT INTO mkt.etf_1d
         (symbol, event_date, open, high, low, close, volume,
          source, row_hash, specialist_tags, created_at)
       VALUES ($1, $2::date, $3, $4, $5, $6, $7,
               'yahoo', $8, $9, NOW())
       ON CONFLICT (symbol, event_date) DO UPDATE SET
         open     = COALESCE(EXCLUDED.open, mkt.etf_1d.open),
         high     = COALESCE(EXCLUDED.high, mkt.etf_1d.high),
         low      = COALESCE(EXCLUDED.low, mkt.etf_1d.low),
         close    = EXCLUDED.close,
         volume   = COALESCE(EXCLUDED.volume, mkt.etf_1d.volume),
         source   = EXCLUDED.source,
         row_hash = EXCLUDED.row_hash,
         specialist_tags = EXCLUDED.specialist_tags
       WHERE mkt.etf_1d.source != 'databento'`,
      [
        symbol,
        bar.eventDate,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
        rowHash,
        specialistTags,
      ],
    );
  } finally {
    client.release();
  }
}

// ---------------------------------------------------------------------------
//  Inngest function — daily cron fallback (gap-fill after Databento)
// ---------------------------------------------------------------------------
export const yahooEtfFallbackDaily = inngest.createFunction(
  {
    id: "yahoo-etf-fallback-daily",
    name: "Yahoo ETF Fallback Daily",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  [
    { cron: "TZ=America/New_York 0 21 * * 1-5" }, // 9 PM ET weekdays
    { event: "etf/yahoo-fallback" },
  ],
  async ({ event, step, logger }) => {
    const range =
      (event?.data as { range?: string } | undefined)?.range ?? "14d";
    const source = "yahoo";

    const results: Array<{
      symbol: string;
      status: "success" | "error" | "no_data" | "skipped";
      inserted?: number;
      skippedDates?: number;
      error?: string;
    }> = [];

    for (const etf of ETF_SYMBOLS) {
      await step.run(`fallback-${etf.symbol}`, async () => {
        try {
          const bars = await fetchYahooBars(etf.yahooTicker, range);
          if (bars.length === 0) {
            logger.info(`${etf.name} (${etf.symbol}): no Yahoo data (range=${range})`);
            results.push({ symbol: etf.symbol, status: "no_data" });
            return;
          }

          // Check which dates already have data (any source)
          const earliestDate = bars[0].eventDate;
          const existingDates = await getExistingDates(etf.symbol, earliestDate);

          let inserted = 0;
          let skipped = 0;
          for (const bar of bars) {
            if (existingDates.has(bar.eventDate)) {
              skipped++;
              continue;
            }

            await upsertYahooBar(etf.symbol, bar, etf.tags);
            inserted++;
          }

          logger.info(
            `${etf.name} (${etf.symbol}): inserted ${inserted}, skipped ${skipped} existing [${bars[0].eventDate} -> ${bars[bars.length - 1].eventDate}]`,
          );
          results.push({
            symbol: etf.symbol,
            status: inserted > 0 ? "success" : "skipped",
            inserted,
            skippedDates: skipped,
          });
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          logger.error(`${etf.name} (${etf.symbol}): ${msg}`);
          results.push({ symbol: etf.symbol, status: "error", error: msg });
        }
      });
    }

    return {
      status: "complete",
      source,
      timestamp: new Date().toISOString(),
      range,
      results,
      successCount: results.filter((r) => r.status === "success").length,
      skippedCount: results.filter((r) => r.status === "skipped").length,
      errorCount: results.filter((r) => r.status === "error").length,
    };
  },
);

// ---------------------------------------------------------------------------
//  Inngest function — event-triggered backfill (year-by-year chunks)
// ---------------------------------------------------------------------------
export const yahooEtfBackfill = inngest.createFunction(
  {
    id: "yahoo-etf-backfill",
    name: "Yahoo ETF Backfill",
    retries: 2,
    concurrency: [DB_CONCURRENCY],
  },
  { event: "etf/yahoo-backfill" },
  async ({ event, step, logger }) => {
    const data = event.data as
      | { symbols?: string[]; days?: number }
      | undefined;
    const targetSymbols = data?.symbols;
    const days = data?.days ?? 365; // default 1 year

    const symbolsToFetch = targetSymbols
      ? ETF_SYMBOLS.filter((e) => targetSymbols.includes(e.symbol))
      : ETF_SYMBOLS;

    const now = new Date();
    const endEpoch = Math.floor(now.getTime() / 1000);
    const startEpoch = endEpoch - days * 86400;

    // For large ranges (>365 days) use year-by-year chunks to avoid
    // Yahoo v8 monthly downsampling
    const useChunks = days > 365;

    const totals: Record<string, number> = {};

    for (const etf of symbolsToFetch) {
      if (useChunks) {
        // Year-by-year chunked backfill
        let totalInserted = 0;
        const startDate = new Date(startEpoch * 1000);
        const startYear = startDate.getUTCFullYear();
        const endYear = now.getUTCFullYear();

        for (let year = startYear; year <= endYear; year++) {
          const inserted = await step.run(
            `backfill-${etf.symbol}-${year}`,
            async () => {
              const p1 = Math.floor(
                new Date(Date.UTC(year, 0, 1)).getTime() / 1000,
              );
              const p2 = Math.floor(
                new Date(Date.UTC(year + 1, 0, 1)).getTime() / 1000,
              );

              const bars = await fetchYahooPeriod(etf.yahooTicker, p1, p2);
              if (bars.length === 0) {
                logger.info(`${etf.symbol} ${year}: no data`);
                return 0;
              }

              let count = 0;
              for (const bar of bars) {
                await upsertYahooBar(etf.symbol, bar, etf.tags);
                count++;
              }

              logger.info(
                `${etf.symbol} ${year}: ${count} bars [${bars[0].eventDate} -> ${bars[bars.length - 1].eventDate}]`,
              );
              return count;
            },
          );

          totalInserted += inserted as number;
        }

        totals[etf.symbol] = totalInserted;
        logger.info(
          `${etf.name}: backfill complete — ${totalInserted} total bars (${startYear}-${endYear})`,
        );
      } else {
        // Single-range fetch for smaller windows
        const inserted = await step.run(
          `backfill-${etf.symbol}`,
          async () => {
            const bars = await fetchYahooPeriod(
              etf.yahooTicker,
              startEpoch,
              endEpoch,
            );
            if (bars.length === 0) {
              logger.info(`${etf.symbol}: no data for ${days}d backfill`);
              return 0;
            }

            let count = 0;
            for (const bar of bars) {
              await upsertYahooBar(etf.symbol, bar, etf.tags);
              count++;
            }

            logger.info(
              `${etf.symbol}: ${count} bars [${bars[0].eventDate} -> ${bars[bars.length - 1].eventDate}]`,
            );
            return count;
          },
        );

        totals[etf.symbol] = inserted as number;
      }
    }

    return {
      status: "complete",
      timestamp: new Date().toISOString(),
      days,
      chunked: useChunks,
      totals,
    };
  },
);
