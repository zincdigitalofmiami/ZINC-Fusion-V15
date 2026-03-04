/**
 * Futures Legacy Symbols Nightly Sync
 *
 * Keeps legacy symbols in mkt.futures_1d fresh overnight using a strict
 * source priority:
 * 1) Internal/FRED-derived tables (preferred)
 * 2) Direct FRED API
 * 3) Yahoo (last resort fallback only)
 */

import { createHash } from "crypto";
import { type PoolClient } from "pg";
import { inngest, DB_CONCURRENCY } from "./client";
import { getIngestPool } from "@/lib/db";

const pool = getIngestPool();
const FRED_API_KEY = process.env.FRED_API_KEY;

type MarketRow = {
  eventDate: string;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close: number;
  volume?: number | null;
};

type SourceConfig =
  | { kind: "fx"; pair: string; sourceTag: string }
  | { kind: "etf"; symbol: string; sourceTag: string }
  | {
      kind: "econ";
      table: "econ.vol_indices_1d" | "econ.commodities_1d";
      seriesId: string;
      sourceTag: string;
    }
  | { kind: "fred"; seriesId: string; sourceTag: string }
  | { kind: "yahoo"; ticker: string; sourceTag: string };

interface LegacySymbolConfig {
  symbol: string;
  sources: SourceConfig[];
}

// Symbols currently present in mkt.futures_1d without direct overnight Databento coverage.
// FRED/internal first. Yahoo is explicit fallback.
const LEGACY_SYMBOLS: LegacySymbolConfig[] = [
  {
    symbol: "AUDUSD",
    sources: [
      { kind: "fx", pair: "AUD/USD", sourceTag: "fx_bridge" },
      { kind: "yahoo", ticker: "AUDUSD=X", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "EURUSD",
    sources: [
      { kind: "fx", pair: "EUR/USD", sourceTag: "fx_bridge" },
      { kind: "yahoo", ticker: "EURUSD=X", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "GBPUSD",
    sources: [
      { kind: "fx", pair: "GBP/USD", sourceTag: "fx_bridge" },
      { kind: "yahoo", ticker: "GBPUSD=X", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "USDBRL",
    sources: [
      { kind: "fx", pair: "BRL/USD", sourceTag: "fx_bridge" },
      { kind: "yahoo", ticker: "BRL=X", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "USDCAD",
    sources: [
      { kind: "fx", pair: "CAD/USD", sourceTag: "fx_bridge" },
      { kind: "yahoo", ticker: "CAD=X", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "USDCNY",
    sources: [
      { kind: "fx", pair: "CNY/USD", sourceTag: "fx_bridge" },
      { kind: "yahoo", ticker: "CNY=X", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "USDJPY",
    sources: [
      { kind: "fx", pair: "USD/JPY", sourceTag: "fx_bridge" },
      { kind: "yahoo", ticker: "JPY=X", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "DXY",
    sources: [
      { kind: "fx", pair: "DXY_BROAD", sourceTag: "fx_bridge" },
      { kind: "yahoo", ticker: "DX-Y.NYB", sourceTag: "yahoo_fallback" },
      { kind: "yahoo", ticker: "DXY", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "FXI",
    sources: [
      { kind: "etf", symbol: "FXI", sourceTag: "databento_etf_bridge" },
      { kind: "yahoo", ticker: "FXI", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "KWEB",
    sources: [
      { kind: "etf", symbol: "KWEB", sourceTag: "databento_etf_bridge" },
      { kind: "yahoo", ticker: "KWEB", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "BDRY",
    sources: [
      { kind: "etf", symbol: "BDRY", sourceTag: "databento_etf_bridge" },
      { kind: "yahoo", ticker: "BDRY", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "SBLK",
    sources: [
      { kind: "etf", symbol: "SBLK", sourceTag: "databento_etf_bridge" },
      { kind: "yahoo", ticker: "SBLK", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "SPX",
    sources: [
      {
        kind: "econ",
        table: "econ.vol_indices_1d",
        seriesId: "SP500",
        sourceTag: "fred_bridge",
      },
      { kind: "yahoo", ticker: "^GSPC", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "NDX",
    sources: [
      {
        kind: "econ",
        table: "econ.vol_indices_1d",
        seriesId: "NASDAQCOM",
        sourceTag: "fred_bridge",
      },
      { kind: "yahoo", ticker: "^NDX", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "VIX",
    sources: [
      {
        kind: "econ",
        table: "econ.vol_indices_1d",
        seriesId: "VIXCLS",
        sourceTag: "fred_bridge",
      },
      { kind: "yahoo", ticker: "^VIX", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "GVZ",
    sources: [
      {
        kind: "econ",
        table: "econ.vol_indices_1d",
        seriesId: "GVZCLS",
        sourceTag: "fred_bridge",
      },
      { kind: "yahoo", ticker: "^GVZ", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "VX",
    sources: [
      // Proxy from FRED VIX index first; VX futures fallback only if needed.
      {
        kind: "econ",
        table: "econ.vol_indices_1d",
        seriesId: "VIXCLS",
        sourceTag: "fred_proxy_bridge",
      },
      { kind: "yahoo", ticker: "VX=F", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "SB",
    sources: [
      {
        kind: "econ",
        table: "econ.commodities_1d",
        seriesId: "PSUGAISAUSDM",
        sourceTag: "fred_bridge",
      },
      { kind: "yahoo", ticker: "SB=F", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "RS",
    sources: [
      {
        kind: "econ",
        table: "econ.commodities_1d",
        seriesId: "WPU01830171",
        sourceTag: "fred_proxy_bridge",
      },
      { kind: "yahoo", ticker: "RS=F", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "KC",
    sources: [
      { kind: "fred", seriesId: "PCOFFOTMUSDM", sourceTag: "fred_api_bridge" },
      { kind: "yahoo", ticker: "KC=F", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "CC",
    sources: [
      { kind: "fred", seriesId: "PCOCOUSDM", sourceTag: "fred_api_bridge" },
      { kind: "yahoo", ticker: "CC=F", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "CT",
    sources: [
      { kind: "fred", seriesId: "PCOTTINDUSDM", sourceTag: "fred_api_bridge" },
      { kind: "yahoo", ticker: "CT=F", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "OJ",
    sources: [
      { kind: "fred", seriesId: "POJUUSDM", sourceTag: "fred_api_bridge" },
      { kind: "yahoo", ticker: "OJ=F", sourceTag: "yahoo_fallback" },
    ],
  },
  {
    symbol: "DJT",
    sources: [{ kind: "yahoo", ticker: "DJT", sourceTag: "yahoo_fallback" }],
  },
];

function computeRowHash(symbol: string, row: MarketRow, sourceTag: string): string {
  const key = [
    symbol,
    row.eventDate,
    row.open ?? "",
    row.high ?? "",
    row.low ?? "",
    row.close,
    row.volume ?? "",
    sourceTag,
  ].join("|");
  return createHash("sha256").update(key).digest("hex");
}

function toDateStringUtc(epochSeconds: number): string {
  const dt = new Date(epochSeconds * 1000);
  return new Date(Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth(), dt.getUTCDate()))
    .toISOString()
    .slice(0, 10);
}

function normalizeRows(rows: MarketRow[]): MarketRow[] {
  const byDate = new Map<string, MarketRow>();
  for (const row of rows) {
    if (!row.eventDate || !Number.isFinite(row.close) || row.close <= 0) {
      continue;
    }
    byDate.set(row.eventDate, row);
  }
  return [...byDate.values()].sort((a, b) => (a.eventDate < b.eventDate ? -1 : 1));
}

async function fetchFxRows(client: PoolClient, pair: string): Promise<MarketRow[]> {
  const r = await client.query(
    `SELECT event_date::date::text AS event_date, rate::double precision AS close
     FROM mkt.fx_1d
     WHERE pair = $1
     ORDER BY event_date DESC
     LIMIT 14`,
    [pair],
  );
  return normalizeRows(
    r.rows.map((x) => ({
      eventDate: x.event_date as string,
      close: Number(x.close),
    })),
  );
}

async function fetchEtfRows(client: PoolClient, symbol: string): Promise<MarketRow[]> {
  const r = await client.query(
    `SELECT event_date::date::text AS event_date, open, high, low, close, volume
     FROM mkt.etf_1d
     WHERE symbol = $1
     ORDER BY event_date DESC
     LIMIT 14`,
    [symbol],
  );
  return normalizeRows(
    r.rows.map((x) => ({
      eventDate: x.event_date as string,
      open: x.open !== null ? Number(x.open) : null,
      high: x.high !== null ? Number(x.high) : null,
      low: x.low !== null ? Number(x.low) : null,
      close: Number(x.close),
      volume: x.volume !== null ? Number(x.volume) : null,
    })),
  );
}

async function fetchEconRows(
  client: PoolClient,
  table: "econ.vol_indices_1d" | "econ.commodities_1d",
  seriesId: string,
): Promise<MarketRow[]> {
  const r = await client.query(
    `SELECT event_date::date::text AS event_date, value::double precision AS close
     FROM ${table}
     WHERE series_id = $1
     ORDER BY event_date DESC
     LIMIT 14`,
    [seriesId],
  );
  return normalizeRows(
    r.rows.map((x) => ({
      eventDate: x.event_date as string,
      close: Number(x.close),
    })),
  );
}

async function fetchFredApiRows(seriesId: string): Promise<MarketRow[]> {
  if (!FRED_API_KEY) return [];

  const url = new URL("https://api.stlouisfed.org/fred/series/observations");
  url.searchParams.set("series_id", seriesId);
  url.searchParams.set("api_key", FRED_API_KEY);
  url.searchParams.set("file_type", "json");
  url.searchParams.set("sort_order", "desc");
  url.searchParams.set("limit", "20");

  const res = await fetch(url.toString(), {
    headers: { "User-Agent": "ZINC-Fusion/1.0" },
  });
  if (!res.ok) return [];

  const json = (await res.json()) as {
    observations?: Array<{ date: string; value: string }>;
  };

  const rows: MarketRow[] = [];
  for (const obs of json.observations ?? []) {
    const v = Number(obs.value);
    if (!obs.date || !Number.isFinite(v) || v <= 0) continue;
    rows.push({
      eventDate: obs.date,
      close: v,
    });
  }
  return normalizeRows(rows);
}

async function fetchYahooRows(ticker: string): Promise<MarketRow[]> {
  const url = new URL(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}`);
  url.searchParams.set("interval", "1d");
  url.searchParams.set("range", "14d");

  const res = await fetch(url.toString(), {
    headers: { "User-Agent": "Mozilla/5.0" },
  });
  if (!res.ok) return [];

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

  const rows: MarketRow[] = [];
  for (let i = 0; i < timestamps.length; i++) {
    const close = quote.close?.[i];
    if (close == null || !Number.isFinite(close) || close <= 0) continue;
    rows.push({
      eventDate: toDateStringUtc(timestamps[i]),
      open: quote.open?.[i] ?? null,
      high: quote.high?.[i] ?? null,
      low: quote.low?.[i] ?? null,
      close,
      volume: quote.volume?.[i] ?? null,
    });
  }
  return normalizeRows(rows);
}

async function resolveRows(
  client: PoolClient,
  config: LegacySymbolConfig,
): Promise<{ rows: MarketRow[]; sourceTag: string } | null> {
  for (const source of config.sources) {
    let rows: MarketRow[] = [];
    if (source.kind === "fx") {
      rows = await fetchFxRows(client, source.pair);
    } else if (source.kind === "etf") {
      rows = await fetchEtfRows(client, source.symbol);
    } else if (source.kind === "econ") {
      rows = await fetchEconRows(client, source.table, source.seriesId);
    } else if (source.kind === "fred") {
      rows = await fetchFredApiRows(source.seriesId);
    } else if (source.kind === "yahoo") {
      rows = await fetchYahooRows(source.ticker);
    }

    if (rows.length > 0) {
      return { rows, sourceTag: source.sourceTag };
    }
  }

  return null;
}

async function upsertRows(
  client: PoolClient,
  symbol: string,
  rows: MarketRow[],
  sourceTag: string,
): Promise<number> {
  let written = 0;
  for (const row of rows) {
    const rowHash = computeRowHash(symbol, row, sourceTag);
    await client.query(
      `INSERT INTO mkt.futures_1d
        (event_date, symbol, open, high, low, close, volume, source, ingested_at, row_hash)
       VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, NOW(), $9)
       ON CONFLICT (event_date, symbol) DO UPDATE SET
         open = COALESCE(EXCLUDED.open, mkt.futures_1d.open),
         high = COALESCE(EXCLUDED.high, mkt.futures_1d.high),
         low = COALESCE(EXCLUDED.low, mkt.futures_1d.low),
         close = EXCLUDED.close,
         volume = COALESCE(EXCLUDED.volume, mkt.futures_1d.volume),
         source = EXCLUDED.source,
         ingested_at = NOW(),
         row_hash = EXCLUDED.row_hash`,
      [
        row.eventDate,
        symbol,
        row.open ?? null,
        row.high ?? null,
        row.low ?? null,
        row.close,
        row.volume ?? null,
        sourceTag,
        rowHash,
      ],
    );
    written++;
  }
  return written;
}

export const futuresLegacySymbolsNightly = inngest.createFunction(
  {
    id: "futures-legacy-symbols-nightly",
    name: "Futures Legacy Symbols Nightly (FRED-first)",
    retries: 2,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { cron: "TZ=America/Chicago 40 1 * * *" }, // 01:40 CT overnight
  async ({ step, logger }) => {
    const summary: Array<{
      symbol: string;
      status: "success" | "no_data" | "error";
      source?: string;
      rows?: number;
      error?: string;
    }> = [];

    for (const config of LEGACY_SYMBOLS) {
      await step.run(`sync-${config.symbol}`, async () => {
        const client = await pool.connect();
        try {
          const resolved = await resolveRows(client, config);
          if (!resolved) {
            summary.push({ symbol: config.symbol, status: "no_data" });
            return;
          }

          const written = await upsertRows(
            client,
            config.symbol,
            resolved.rows,
            resolved.sourceTag,
          );

          logger.info(
            `${config.symbol}: upserted ${written} rows via ${resolved.sourceTag}`,
          );
          summary.push({
            symbol: config.symbol,
            status: "success",
            source: resolved.sourceTag,
            rows: written,
          });
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          logger.error(`${config.symbol}: ${msg}`);
          summary.push({ symbol: config.symbol, status: "error", error: msg });
        } finally {
          client.release();
        }
      });
    }

    return {
      status: "complete",
      timestamp: new Date().toISOString(),
      results: summary,
      successCount: summary.filter((x) => x.status === "success").length,
      noDataCount: summary.filter((x) => x.status === "no_data").length,
      errorCount: summary.filter((x) => x.status === "error").length,
    };
  },
);
