/**
 * Databento Options Daily OHLCV Ingestion
 *
 * Fetches options on futures from Databento GLBX.MDP3 dataset.
 * Requires joining definition schema (for strike/expiry) with OHLCV schema (for prices).
 *
 * Runs every 8 hours to keep options data current.
 */

import { inngest } from "./client";
import { Pool } from "pg";
import { fetchDatabentoCsv } from "@/lib/databento";
import { createHash } from "crypto";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// Options products to fetch (parent symbology: OPTROOT.OPT)
// These map option root symbols to their underlying futures
const OPTIONS_CONFIG = [
  // Agriculture Options
  { optSymbol: "OZL.OPT", underlying: "ZL", name: "Soybean Oil Options" },
  { optSymbol: "OZS.OPT", underlying: "ZS", name: "Soybean Options" },
  { optSymbol: "OZM.OPT", underlying: "ZM", name: "Soybean Meal Options" },
  { optSymbol: "OZC.OPT", underlying: "ZC", name: "Corn Options" },
  { optSymbol: "OZW.OPT", underlying: "ZW", name: "Wheat Options" },
  // Energy Options
  { optSymbol: "LO.OPT", underlying: "CL", name: "Crude Oil Options" },
  { optSymbol: "ON.OPT", underlying: "NG", name: "Natural Gas Options" },
  { optSymbol: "OH.OPT", underlying: "HO", name: "Heating Oil Options" },
  { optSymbol: "OB.OPT", underlying: "RB", name: "RBOB Gasoline Options" },
  // Metals Options
  { optSymbol: "OG.OPT", underlying: "GC", name: "Gold Options" },
  { optSymbol: "SO.OPT", underlying: "SI", name: "Silver Options" },
  { optSymbol: "HXE.OPT", underlying: "HG", name: "Copper Options" },
  // Equity Index Options
  { optSymbol: "ES.OPT", underlying: "ES", name: "E-mini S&P Options" },
  { optSymbol: "NQ.OPT", underlying: "NQ", name: "E-mini Nasdaq Options" },
  // Treasury Options
  { optSymbol: "OZN.OPT", underlying: "ZN", name: "10Y Treasury Options" },
  { optSymbol: "OZB.OPT", underlying: "ZB", name: "30Y Treasury Options" },
  { optSymbol: "OZF.OPT", underlying: "ZF", name: "5Y Treasury Options" },
  // FX Options
  { optSymbol: "EUU.OPT", underlying: "6E", name: "Euro FX Options" },
  { optSymbol: "JPU.OPT", underlying: "6J", name: "Yen FX Options" },
];

interface OptionResult {
  underlying: string;
  status: "success" | "error" | "no_data";
  rowsInserted?: number;
  error?: string;
}

/**
 * Parse strike from raw option symbol (e.g., "OZLH6 C6000" -> 6000)
 */
function parseStrikeFromSymbol(rawSymbol: string): number | null {
  const match = rawSymbol.match(/[CP](\d+)/);
  return match ? parseInt(match[1], 10) : null;
}

/**
 * Compute row_hash for idempotency
 */
function computeRowHash(
  underlying: string,
  eventDate: string,
  expiration: string,
  strike: number,
  optionType: string
): string {
  const hashInput = `${underlying}|${eventDate}|${expiration}|${strike}|${optionType}`;
  return createHash("sha256").update(hashInput).digest("hex");
}

/**
 * Parse timestamp from various formats
 */
function parseTimestamp(value: string): Date | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (/^\d+$/.test(trimmed)) {
    const num = Number(trimmed);
    if (!Number.isFinite(num)) return null;
    const ms = Math.floor(num / 1_000_000);
    return new Date(ms);
  }
  const dt = new Date(trimmed);
  if (Number.isNaN(dt.getTime())) return null;
  return dt;
}

/**
 * Parse definition CSV to build instrument_id -> option info mapping
 */
function parseDefinitionCsv(
  csv: string
): Map<string, { strike: number; expiration: string; optionType: string }> {
  const map = new Map<
    string,
    { strike: number; expiration: string; optionType: string }
  >();

  const lines = csv
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));

  if (lines.length < 2) return map;

  const header = lines[0].split(",");
  const idx = {
    instrument_id: header.indexOf("instrument_id"),
    raw_symbol: header.indexOf("raw_symbol"),
    expiration: header.indexOf("expiration"),
    instrument_class: header.indexOf("instrument_class"),
  };

  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",");

    const instClass = parts[idx.instrument_class]?.trim();
    if (instClass !== "C" && instClass !== "P") continue; // Only options

    const instrumentId = parts[idx.instrument_id]?.trim();
    const rawSymbol = parts[idx.raw_symbol]?.trim() || "";
    const expirationStr = parts[idx.expiration]?.trim();

    const strike = parseStrikeFromSymbol(rawSymbol);
    if (!strike || strike <= 0) continue;

    const exp = parseTimestamp(expirationStr);
    if (!exp) continue;

    map.set(instrumentId, {
      strike,
      expiration: exp.toISOString().split("T")[0],
      optionType: instClass,
    });
  }

  return map;
}

/**
 * Parse OHLCV CSV and join with definition map
 */
function parseOptionsOhlcvCsv(
  csv: string,
  defMap: Map<string, { strike: number; expiration: string; optionType: string }>,
  underlying: string
): Array<{
  underlying: string;
  eventDate: string;
  expiration: string;
  strike: number;
  optionType: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number;
}> {
  const results: Array<{
    underlying: string;
    eventDate: string;
    expiration: string;
    strike: number;
    optionType: string;
    open: number | null;
    high: number | null;
    low: number | null;
    close: number;
    volume: number;
  }> = [];

  const lines = csv
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));

  if (lines.length < 2) return results;

  const header = lines[0].split(",");
  const idx = {
    ts_event: header.indexOf("ts_event"),
    instrument_id: header.indexOf("instrument_id"),
    open: header.indexOf("open"),
    high: header.indexOf("high"),
    low: header.indexOf("low"),
    close: header.indexOf("close"),
    volume: header.indexOf("volume"),
  };

  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",");

    const instrumentId = parts[idx.instrument_id]?.trim();
    const defInfo = defMap.get(instrumentId);
    if (!defInfo) continue;

    const ts = parseTimestamp(parts[idx.ts_event]);
    if (!ts) continue;

    const close = Number(parts[idx.close]);
    if (!Number.isFinite(close) || close <= 0) continue;

    const open = Number(parts[idx.open]);
    const high = Number(parts[idx.high]);
    const low = Number(parts[idx.low]);
    const volume = Number(parts[idx.volume]) || 0;

    results.push({
      underlying,
      eventDate: ts.toISOString().split("T")[0],
      expiration: defInfo.expiration,
      strike: defInfo.strike,
      optionType: defInfo.optionType,
      open: Number.isFinite(open) ? open : null,
      high: Number.isFinite(high) ? high : null,
      low: Number.isFinite(low) ? low : null,
      close,
      volume,
    });
  }

  return results;
}

export const databentoOptionsDaily = inngest.createFunction(
  {
    id: "databento-options-daily",
    name: "Databento Options Daily OHLCV",
    retries: 2,
  },
  { cron: "TZ=America/Chicago 30 */8 * * *" }, // Every 8 hours at :30 (0:30, 8:30, 16:30 CT)
  async ({ step, logger }) => {
    const results: OptionResult[] = [];

    // Calculate date range: last 5 days to handle weekends/holidays
    const endDate = new Date();
    endDate.setUTCDate(endDate.getUTCDate() - 1);
    const startDate = new Date(endDate);
    startDate.setUTCDate(startDate.getUTCDate() - 5);

    const startStr = startDate.toISOString().split("T")[0];
    const endStr = endDate.toISOString().split("T")[0];

    logger.info(`Fetching options data from ${startStr} to ${endStr}`);

    for (const config of OPTIONS_CONFIG) {
      await step.run(`fetch-${config.underlying}-options`, async () => {
        try {
          logger.info(`Fetching ${config.name} (${config.optSymbol})`);

          // Step 1: Fetch definitions
          const defCsv = await fetchDatabentoCsv({
            dataset: "GLBX.MDP3",
            schema: "definition",
            symbols: config.optSymbol,
            stype_in: "parent",
            start: startStr,
            end: endStr,
            encoding: "csv",
            pretty_ts: "true",
          });

          const defMap = parseDefinitionCsv(defCsv);
          if (defMap.size === 0) {
            logger.info(`No definitions for ${config.underlying}`);
            results.push({ underlying: config.underlying, status: "no_data" });
            return;
          }

          logger.info(
            `${config.underlying}: ${defMap.size} option definitions`
          );

          // Step 2: Fetch OHLCV
          const ohlcvCsv = await fetchDatabentoCsv({
            dataset: "GLBX.MDP3",
            schema: "ohlcv-1d",
            symbols: config.optSymbol,
            stype_in: "parent",
            start: startStr,
            end: endStr,
            encoding: "csv",
            pretty_ts: "true",
            pretty_px: "true",
          });

          const optionBars = parseOptionsOhlcvCsv(
            ohlcvCsv,
            defMap,
            config.underlying
          );
          if (optionBars.length === 0) {
            logger.info(`No OHLCV data for ${config.underlying}`);
            results.push({ underlying: config.underlying, status: "no_data" });
            return;
          }

          logger.info(`${config.underlying}: ${optionBars.length} option bars`);

          // Step 3: Insert into database
          const client = await pool.connect();
          try {
            let inserted = 0;
            for (const bar of optionBars) {
              const rowHash = computeRowHash(
                bar.underlying,
                bar.eventDate,
                bar.expiration,
                bar.strike,
                bar.optionType
              );

              await client.query(
                `INSERT INTO mkt.options_1d
                  (underlying, event_date, expiration, strike, option_type, 
                   open, high, low, close, volume, source, ingested_at, row_hash)
                 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'databento', NOW(), $11)
                 ON CONFLICT (underlying, event_date, expiration, strike, option_type) 
                 DO UPDATE SET
                   open = COALESCE(EXCLUDED.open, mkt.options_1d.open),
                   high = COALESCE(EXCLUDED.high, mkt.options_1d.high),
                   low = COALESCE(EXCLUDED.low, mkt.options_1d.low),
                   close = EXCLUDED.close,
                   volume = COALESCE(EXCLUDED.volume, mkt.options_1d.volume),
                   source = 'databento',
                   ingested_at = NOW()`,
                [
                  bar.underlying,
                  bar.eventDate,
                  bar.expiration,
                  bar.strike,
                  bar.optionType,
                  bar.open,
                  bar.high,
                  bar.low,
                  bar.close,
                  bar.volume,
                  rowHash,
                ]
              );
              inserted++;
            }

            logger.info(`${config.underlying}: inserted ${inserted} rows`);
            results.push({
              underlying: config.underlying,
              status: "success",
              rowsInserted: inserted,
            });
          } finally {
            client.release();
          }
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : String(err);
          logger.error(`Failed ${config.underlying}: ${errorMsg}`);
          results.push({
            underlying: config.underlying,
            status: "error",
            error: errorMsg,
          });
        }
      });
    }

    const successCount = results.filter((r) => r.status === "success").length;
    const totalRows = results.reduce(
      (sum, r) => sum + (r.rowsInserted || 0),
      0
    );

    return {
      status: "complete",
      timestamp: new Date().toISOString(),
      dateRange: { start: startStr, end: endStr },
      results,
      successCount,
      errorCount: results.filter((r) => r.status === "error").length,
      totalRowsInserted: totalRows,
    };
  }
);
