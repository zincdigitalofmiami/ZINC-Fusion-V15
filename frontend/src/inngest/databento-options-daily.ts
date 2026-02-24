/**
 * Databento Options Daily OHLCV Ingestion
 *
 * Fetches options on futures from Databento GLBX.MDP3 dataset.
 * Requires joining definition schema (for strike/expiry) with OHLCV schema (for prices).
 *
 * Runs every 8 hours to keep options data current.
 */

import { inngest, DB_CONCURRENCY } from "./client";
import {
  fetchDatabentoCsv,
  parseDatabentoStatisticsCsvOptions,
} from "@/lib/databento";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

// =============================================================================
// OPTIONS SYMBOL REGISTRY
// =============================================================================
// Standard options (.OPT parent symbology) + weekly options (product codes).
// NO FAKE DATA — all data from Databento API only.
//
//   dumpDefs  — historical definitions available in the Databento Data Dump
//               (GLBX-20260202-WH33638BK6, definition schema, 2010-06 → 2026-02)
//               20 parent symbols with ~15.7 years of strike/expiry metadata.
//               Path: /Volumes/Satechi Hub/Databento Data Dump/Options/
//   category  — asset class for filtering / shard prioritisation
//
// Symbols WITHOUT dumpDefs still work for daily ingestion (definitions fetched
// live from Databento API each run) but lack historical backfill potential.
// =============================================================================

type OptionCategory =
  | "agriculture"
  | "agriculture_weekly"
  | "energy"
  | "metals"
  | "equity"
  | "treasury"
  | "fx"
  | "fx_weekly"
  | "livestock";

interface OptionConfig {
  optSymbol: string;
  underlying: string;
  name: string;
  category: OptionCategory;
  dumpDefs: boolean; // true = definitions in Databento Data Dump (2010-2026)
}

const OPTIONS_CONFIG: OptionConfig[] = [
  // ===== AGRICULTURE OPTIONS (STANDARD) — all in dump =====
  { optSymbol: "OZL.OPT", underlying: "ZL", name: "Soybean Oil Options",    category: "agriculture", dumpDefs: true  },
  { optSymbol: "OZS.OPT", underlying: "ZS", name: "Soybean Options",        category: "agriculture", dumpDefs: true  },
  { optSymbol: "OZM.OPT", underlying: "ZM", name: "Soybean Meal Options",   category: "agriculture", dumpDefs: true  },
  { optSymbol: "OZC.OPT", underlying: "ZC", name: "Corn Options",           category: "agriculture", dumpDefs: true  },
  { optSymbol: "OZW.OPT", underlying: "ZW", name: "Wheat Options",          category: "agriculture", dumpDefs: true  },
  { optSymbol: "OKE.OPT", underlying: "KE", name: "KC HRW Wheat Options",   category: "agriculture", dumpDefs: true  },

  // ===== AGRICULTURE WEEKLY OPTIONS — no dump (live defs only) =====
  { optSymbol: "1WC", underlying: "ZW", name: "Wheat Wed Weekly W1",        category: "agriculture_weekly", dumpDefs: false },
  { optSymbol: "1WB", underlying: "ZW", name: "Wheat Tue Weekly W1",        category: "agriculture_weekly", dumpDefs: false },
  { optSymbol: "1WA", underlying: "ZW", name: "Wheat Mon Weekly W1",        category: "agriculture_weekly", dumpDefs: false },
  { optSymbol: "1WD", underlying: "ZW", name: "Wheat Thu Weekly W1",        category: "agriculture_weekly", dumpDefs: false },
  { optSymbol: "2WA", underlying: "ZW", name: "Wheat Mon Weekly W2",        category: "agriculture_weekly", dumpDefs: false },
  { optSymbol: "1SD", underlying: "ZS", name: "Soybean Thu Weekly W1",      category: "agriculture_weekly", dumpDefs: false },
  { optSymbol: "1SA", underlying: "ZS", name: "Soybean Mon Weekly W1",      category: "agriculture_weekly", dumpDefs: false },
  { optSymbol: "ZL5", underlying: "ZL", name: "Soybean Oil Fri Weekly W5",  category: "agriculture_weekly", dumpDefs: false },
  { optSymbol: "CN5", underlying: "ZC", name: "Corn Weekly W5",             category: "agriculture_weekly", dumpDefs: false },
  { optSymbol: "OE1", underlying: "KE", name: "KC Wheat Fri Weekly W1",     category: "agriculture_weekly", dumpDefs: false },
  { optSymbol: "OE5", underlying: "KE", name: "KC Wheat Fri Weekly W5",     category: "agriculture_weekly", dumpDefs: false },

  // ===== ENERGY OPTIONS — LO, ON, OH, OB in dump =====
  { optSymbol: "LO.OPT", underlying: "CL", name: "Crude Oil Options",       category: "energy", dumpDefs: true  },
  { optSymbol: "ON.OPT", underlying: "NG", name: "Natural Gas Options",     category: "energy", dumpDefs: true  },
  { optSymbol: "OH.OPT", underlying: "HO", name: "Heating Oil Options",     category: "energy", dumpDefs: true  },
  { optSymbol: "OB.OPT", underlying: "RB", name: "RBOB Gasoline Options",   category: "energy", dumpDefs: true  },
  { optSymbol: "BZ.OPT", underlying: "BZ", name: "Brent Crude Options",     category: "energy", dumpDefs: false },

  // ===== METALS OPTIONS — OG, SO, HXE in dump =====
  { optSymbol: "OG.OPT", underlying: "GC", name: "Gold Options",            category: "metals", dumpDefs: true  },
  { optSymbol: "SO.OPT", underlying: "SI", name: "Silver Options",          category: "metals", dumpDefs: true  },
  { optSymbol: "HXE.OPT", underlying: "HG", name: "Copper Options",        category: "metals", dumpDefs: true  },
  { optSymbol: "PO.OPT", underlying: "PL", name: "Platinum Options",        category: "metals", dumpDefs: false },
  { optSymbol: "PAO.OPT", underlying: "PA", name: "Palladium Options",      category: "metals", dumpDefs: false },

  // ===== EQUITY INDEX OPTIONS — ES, NQ in dump =====
  { optSymbol: "ES.OPT", underlying: "ES", name: "E-mini S&P Options",      category: "equity", dumpDefs: true  },
  { optSymbol: "NQ.OPT", underlying: "NQ", name: "E-mini Nasdaq Options",   category: "equity", dumpDefs: true  },
  { optSymbol: "YM.OPT", underlying: "YM", name: "Mini Dow Options",        category: "equity", dumpDefs: false },
  { optSymbol: "RTO.OPT", underlying: "RTY", name: "E-mini Russell Options", category: "equity", dumpDefs: false },

  // ===== TREASURY OPTIONS — OZN, OZB, OZF in dump =====
  { optSymbol: "OZN.OPT", underlying: "ZN", name: "10Y Treasury Options",   category: "treasury", dumpDefs: true  },
  { optSymbol: "OZB.OPT", underlying: "ZB", name: "30Y Treasury Options",   category: "treasury", dumpDefs: true  },
  { optSymbol: "OZF.OPT", underlying: "ZF", name: "5Y Treasury Options",    category: "treasury", dumpDefs: true  },
  { optSymbol: "OZT.OPT", underlying: "ZT", name: "2Y Treasury Options",    category: "treasury", dumpDefs: false },

  // ===== FX OPTIONS (STANDARD) — EUU, JPU in dump =====
  { optSymbol: "EUU.OPT", underlying: "6E", name: "Euro FX Options",        category: "fx", dumpDefs: true  },
  { optSymbol: "JPU.OPT", underlying: "6J", name: "Yen FX Options",         category: "fx", dumpDefs: true  },
  { optSymbol: "GBU.OPT", underlying: "6B", name: "GBP Options",            category: "fx", dumpDefs: false },
  { optSymbol: "ADU.OPT", underlying: "6A", name: "AUD Options",            category: "fx", dumpDefs: false },
  { optSymbol: "CAU.OPT", underlying: "6C", name: "CAD Options",            category: "fx", dumpDefs: false },
  { optSymbol: "SFU.OPT", underlying: "6S", name: "CHF Options",            category: "fx", dumpDefs: false },
  { optSymbol: "6M.OPT", underlying: "6M", name: "MXN Options",             category: "fx", dumpDefs: false },
  { optSymbol: "NZU.OPT", underlying: "6N", name: "NZD Options",            category: "fx", dumpDefs: false },
  { optSymbol: "DX.OPT", underlying: "DX", name: "Dollar Index Options",    category: "fx", dumpDefs: false },

  // ===== FX WEEKLY OPTIONS - EUR/USD (6E) =====
  { optSymbol: "TU2", underlying: "6E", name: "EUR Tue Weekly W2",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "3EU", underlying: "6E", name: "EUR Fri Weekly W3",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "MO2", underlying: "6E", name: "EUR Mon Weekly W2",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "MO4", underlying: "6E", name: "EUR Mon Weekly W4",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "WE2", underlying: "6E", name: "EUR Wed Weekly W2",          category: "fx_weekly", dumpDefs: false },

  // ===== FX WEEKLY OPTIONS - JPY/USD (6J) =====
  { optSymbol: "MJ1", underlying: "6J", name: "JPY Mon Weekly W1",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "5JY", underlying: "6J", name: "JPY Fri Weekly W5",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "WJ3", underlying: "6J", name: "JPY Wed Weekly W3",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "WJ2", underlying: "6J", name: "JPY Wed Weekly W2",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "3JY", underlying: "6J", name: "JPY Fri Weekly W3",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "SJ5", underlying: "6J", name: "JPY Thu Weekly W5",          category: "fx_weekly", dumpDefs: false },

  // ===== FX WEEKLY OPTIONS - GBP/USD (6B) =====
  { optSymbol: "MB2", underlying: "6B", name: "GBP Mon Weekly W2",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "3BP", underlying: "6B", name: "GBP Fri Weekly W3",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "2BP", underlying: "6B", name: "GBP Fri Weekly W2",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "SB1", underlying: "6B", name: "GBP Thu Weekly W1",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "TG1", underlying: "6B", name: "GBP Tue Weekly W1",          category: "fx_weekly", dumpDefs: false },

  // ===== FX WEEKLY OPTIONS - AUD/USD (6A) =====
  { optSymbol: "WA1", underlying: "6A", name: "AUD Wed Weekly W1",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "WA2", underlying: "6A", name: "AUD Wed Weekly W2",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "SA1", underlying: "6A", name: "AUD Thu Weekly W1",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "MA1", underlying: "6A", name: "AUD Mon Weekly W1",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "2AD", underlying: "6A", name: "AUD Fri Weekly W2",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "TA2", underlying: "6A", name: "AUD Tue Weekly W2",          category: "fx_weekly", dumpDefs: false },

  // ===== FX WEEKLY OPTIONS - CAD/USD (6C) =====
  { optSymbol: "WD2", underlying: "6C", name: "CAD Wed Weekly W2",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "WD3", underlying: "6C", name: "CAD Wed Weekly W3",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "TL1", underlying: "6C", name: "CAD Tue Weekly W1",          category: "fx_weekly", dumpDefs: false },

  // ===== FX WEEKLY OPTIONS - CHF/USD (6S) =====
  { optSymbol: "4SF", underlying: "6S", name: "CHF Fri Weekly W4",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "5SF", underlying: "6S", name: "CHF Fri Weekly W5",          category: "fx_weekly", dumpDefs: false },
  { optSymbol: "2SF", underlying: "6S", name: "CHF Fri Weekly W2",          category: "fx_weekly", dumpDefs: false },

  // ===== LIVESTOCK OPTIONS — no dump =====
  { optSymbol: "HE.OPT", underlying: "HE", name: "Lean Hogs Options",      category: "livestock", dumpDefs: false },
  { optSymbol: "LE.OPT", underlying: "LE", name: "Live Cattle Options",     category: "livestock", dumpDefs: false },
  { optSymbol: "GF.OPT", underlying: "GF", name: "Feeder Cattle Options",   category: "livestock", dumpDefs: false },
];

// Derived counts for logging / monitoring
const _DUMP_COVERED = OPTIONS_CONFIG.filter((c) => c.dumpDefs).length;   // 20
const _LIVE_ONLY    = OPTIONS_CONFIG.filter((c) => !c.dumpDefs).length;  // rest

/**
 * Unique underlyings from standard options (`.OPT` parent symbols only).
 * Weekly product codes are excluded — they don't independently indicate
 * staleness since they share underlyings with the standard contracts.
 * Exported for use by the options-staleness-check monitor.
 */
export const STANDARD_OPTIONS_UNDERLYINGS: readonly string[] = [
  ...new Set(
    OPTIONS_CONFIG
      .filter((c) => c.optSymbol.endsWith(".OPT"))
      .map((c) => c.underlying),
  ),
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
 * Parse definition CSV to build instrument_id -> option info mapping (includes raw_symbol for stats join)
 */
function parseDefinitionCsv(
  csv: string
): Map<
  string,
  { strike: number; expiration: string; optionType: string; rawSymbol: string }
> {
  const map = new Map<
    string,
    { strike: number; expiration: string; optionType: string; rawSymbol: string }
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
      rawSymbol,
    });
  }

  return map;
}

/**
 * Parse OHLCV CSV and join with definition map
 */
function parseOptionsOhlcvCsv(
  csv: string,
  defMap: Map<
    string,
    { strike: number; expiration: string; optionType: string; rawSymbol: string }
  >,
  underlying: string
): Array<{
  underlying: string;
  eventDate: string;
  expiration: string;
  strike: number;
  optionType: string;
  rawSymbol: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number;
  openInterest: number | null;
  bid: number | null;
  ask: number | null;
  change: number | null;
  premium: number | null;
  openingPriceStat: number | null;
  indicativeOpening: number | null;
  sessionLowStat: number | null;
  sessionHighStat: number | null;
  clearedVolume: number | null;
  fixingPrice: number | null;
  closeStat: number | null;
  vwap: number | null;
  impliedVolatility: number | null;
  delta: number | null;
}> {
  const results: Array<{
    underlying: string;
    eventDate: string;
    expiration: string;
    strike: number;
    optionType: string;
    rawSymbol: string;
    open: number | null;
    high: number | null;
    low: number | null;
    close: number;
    volume: number;
    openInterest: number | null;
    bid: number | null;
    ask: number | null;
    change: number | null;
    premium: number | null;
    openingPriceStat: number | null;
    indicativeOpening: number | null;
    sessionLowStat: number | null;
    sessionHighStat: number | null;
    clearedVolume: number | null;
    fixingPrice: number | null;
    closeStat: number | null;
    vwap: number | null;
    impliedVolatility: number | null;
    delta: number | null;
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
    open_interest: header.indexOf("open_interest"),
  };

  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",");

    const instrumentId = parts[idx.instrument_id]?.trim();
    const defInfo = defMap.get(instrumentId);
    if (!defInfo) continue;

    const ts = parseTimestamp(parts[idx.ts_event]);
    if (!ts || ts.getFullYear() < 2010) continue; // Never insert bad/epoch dates

    const close = Number(parts[idx.close]);
    if (!Number.isFinite(close) || close <= 0) continue;

    const open = Number(parts[idx.open]);
    const high = Number(parts[idx.high]);
    const low = Number(parts[idx.low]);
    const volume = Number(parts[idx.volume]) || 0;
    const openInterest = idx.open_interest >= 0 ? Number(parts[idx.open_interest]) : null;

    results.push({
      underlying,
      eventDate: ts.toISOString().split("T")[0],
      expiration: defInfo.expiration,
      strike: defInfo.strike,
      optionType: defInfo.optionType,
      rawSymbol: defInfo.rawSymbol,
      open: Number.isFinite(open) ? open : null,
      high: Number.isFinite(high) ? high : null,
      low: Number.isFinite(low) ? low : null,
      close,
      volume,
      openInterest: Number.isFinite(openInterest) ? openInterest : null,
      bid: null,
      ask: null,
      change: null,
      premium: null,
      openingPriceStat: null,
      indicativeOpening: null,
      sessionLowStat: null,
      sessionHighStat: null,
      clearedVolume: null,
      fixingPrice: null,
      closeStat: null,
      vwap: null,
      impliedVolatility: null,
      delta: null,
    });
  }

  return results;
}

const OPTIONS_SHARD_CRONS = [
  "TZ=America/Chicago 5 0 * * *",
  "TZ=America/Chicago 5 3 * * *",
  "TZ=America/Chicago 5 6 * * *",
  "TZ=America/Chicago 5 9 * * *",
  "TZ=America/Chicago 5 12 * * *",
  "TZ=America/Chicago 5 15 * * *",
  "TZ=America/Chicago 5 18 * * *",
  "TZ=America/Chicago 5 21 * * *",
];

function splitIntoShards<T>(items: T[], shardCount: number): T[][] {
  const shards = Array.from({ length: shardCount }, () => [] as T[]);
  items.forEach((item, idx) => {
    shards[idx % shardCount].push(item);
  });
  return shards;
}

const OPTIONS_SHARDS = splitIntoShards(OPTIONS_CONFIG, OPTIONS_SHARD_CRONS.length);

type StepLike = {
  run: (
    id: string,
    fn: () => Promise<unknown> | unknown,
  ) => Promise<unknown>;
};

type LoggerLike = {
  info: (msg: string) => void;
  warn: (msg: string) => void;
  error: (msg: string) => void;
};

async function runOptionsShard(
  shardConfigs: typeof OPTIONS_CONFIG,
  shardIndex: number,
  shardCount: number,
  step: StepLike,
  logger: LoggerLike,
) {
  const results: OptionResult[] = [];

  // Calculate date range: last 5 days to handle weekends/holidays
  const endDate = new Date();
  const startDate = new Date(endDate);
  startDate.setUTCDate(startDate.getUTCDate() - 5);

  const startStr = startDate.toISOString().split("T")[0];
  const endStr = endDate.toISOString().split("T")[0];

  logger.info(
    `Options shard ${shardIndex}/${shardCount}: fetching ${shardConfigs.length} symbols from ${startStr} to ${endStr}`,
  );

  for (const config of shardConfigs) {
    await step.run(
      `fetch-options-shard-${shardIndex}-${config.underlying}-${config.optSymbol}`,
      async () => {
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

          logger.info(`${config.underlying}: ${defMap.size} option definitions`);

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
            config.underlying,
          );
          if (optionBars.length === 0) {
            logger.info(`No OHLCV data for ${config.underlying}`);
            results.push({ underlying: config.underlying, status: "no_data" });
            return;
          }

          // Step 2b: Fetch statistics (open_interest, bid, ask, change, settlement)
          let statsByKey = parseDatabentoStatisticsCsvOptions("");
          try {
            const statsCsv = await fetchDatabentoCsv({
              dataset: "GLBX.MDP3",
              schema: "statistics",
              symbols: config.optSymbol,
              stype_in: "parent",
              start: startStr,
              end: endStr,
              encoding: "csv",
              pretty_ts: "true",
              pretty_px: "true",
            });
            statsByKey = parseDatabentoStatisticsCsvOptions(statsCsv);
            logger.info(
              `${config.underlying}: stats lookup ${statsByKey.size} symbol-date keys`,
            );
          } catch (err) {
            logger.warn(
              `Statistics fetch failed for ${config.underlying}, continuing with OHLCV only: ${err}`,
            );
          }

          // Merge all 15 statistics into bars by (rawSymbol, eventDate)
          for (const bar of optionBars) {
            const key = `${bar.rawSymbol}_${bar.eventDate}`;
            const stats = statsByKey.get(key);
            if (stats) {
              bar.openInterest = stats.openInterest ?? bar.openInterest;
              bar.bid = stats.bid ?? bar.bid;
              bar.ask = stats.ask ?? bar.ask;
              bar.change = stats.change ?? bar.change;
              bar.premium = stats.settlement ?? bar.premium;
              bar.openingPriceStat = stats.openingPriceStat ?? bar.openingPriceStat;
              bar.indicativeOpening = stats.indicativeOpening ?? bar.indicativeOpening;
              bar.sessionLowStat = stats.sessionLowStat ?? bar.sessionLowStat;
              bar.sessionHighStat = stats.sessionHighStat ?? bar.sessionHighStat;
              bar.clearedVolume = stats.clearedVolume ?? bar.clearedVolume;
              bar.fixingPrice = stats.fixingPrice ?? bar.fixingPrice;
              bar.closeStat = stats.closeStat ?? bar.closeStat;
              bar.vwap = stats.vwap ?? bar.vwap;
              bar.impliedVolatility = stats.impliedVolatility ?? bar.impliedVolatility;
              bar.delta = stats.delta ?? bar.delta;
            }
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
                bar.optionType,
              );

              await client.query(
                `INSERT INTO mkt.options_1d
                  (underlying, event_date, expiration, strike, option_type,
                   open, high, low, close, volume, open_interest, bid, ask, change, premium,
                   opening_price_stat, indicative_opening, session_low_stat, session_high_stat,
                   cleared_volume, fixing_price, close_stat, vwap, implied_volatility, delta,
                   source, ingested_at, row_hash)
                 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                   $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, 'databento', NOW(), $26)
                 ON CONFLICT (underlying, event_date, expiration, strike, option_type)
                 DO UPDATE SET
                   open = COALESCE(EXCLUDED.open, mkt.options_1d.open),
                   high = COALESCE(EXCLUDED.high, mkt.options_1d.high),
                   low = COALESCE(EXCLUDED.low, mkt.options_1d.low),
                   close = EXCLUDED.close,
                   volume = COALESCE(EXCLUDED.volume, mkt.options_1d.volume),
                   open_interest = COALESCE(EXCLUDED.open_interest, mkt.options_1d.open_interest),
                   bid = COALESCE(EXCLUDED.bid, mkt.options_1d.bid),
                   ask = COALESCE(EXCLUDED.ask, mkt.options_1d.ask),
                   change = COALESCE(EXCLUDED.change, mkt.options_1d.change),
                   premium = COALESCE(EXCLUDED.premium, mkt.options_1d.premium),
                   opening_price_stat = COALESCE(EXCLUDED.opening_price_stat, mkt.options_1d.opening_price_stat),
                   indicative_opening = COALESCE(EXCLUDED.indicative_opening, mkt.options_1d.indicative_opening),
                   session_low_stat = COALESCE(EXCLUDED.session_low_stat, mkt.options_1d.session_low_stat),
                   session_high_stat = COALESCE(EXCLUDED.session_high_stat, mkt.options_1d.session_high_stat),
                   cleared_volume = COALESCE(EXCLUDED.cleared_volume, mkt.options_1d.cleared_volume),
                   fixing_price = COALESCE(EXCLUDED.fixing_price, mkt.options_1d.fixing_price),
                   close_stat = COALESCE(EXCLUDED.close_stat, mkt.options_1d.close_stat),
                   vwap = COALESCE(EXCLUDED.vwap, mkt.options_1d.vwap),
                   implied_volatility = COALESCE(EXCLUDED.implied_volatility, mkt.options_1d.implied_volatility),
                   delta = COALESCE(EXCLUDED.delta, mkt.options_1d.delta),
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
                  bar.openInterest,
                  bar.bid,
                  bar.ask,
                  bar.change,
                  bar.premium,
                  bar.openingPriceStat,
                  bar.indicativeOpening,
                  bar.sessionLowStat,
                  bar.sessionHighStat,
                  bar.clearedVolume,
                  bar.fixingPrice,
                  bar.closeStat,
                  bar.vwap,
                  bar.impliedVolatility,
                  bar.delta,
                  rowHash,
                ],
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
      },
    );
  }

  const successCount = results.filter((r) => r.status === "success").length;
  const totalRows = results.reduce((sum, r) => sum + (r.rowsInserted || 0), 0);
  const shardSymbols = shardConfigs.map((s) => s.underlying).join(",");

  return {
    status: "complete",
    timestamp: new Date().toISOString(),
    shardIndex,
    shardCount,
    symbols: shardSymbols,
    dateRange: { start: startStr, end: endStr },
    results,
    successCount,
    errorCount: results.filter((r) => r.status === "error").length,
    totalRowsInserted: totalRows,
  };
}

export const databentoOptionsDailyShards = OPTIONS_SHARDS.map((shard, index) =>
  inngest.createFunction(
    {
      id: `databento-options-daily-shard-${index + 1}`,
      name: `Databento Options Daily OHLCV Shard ${index + 1}/${OPTIONS_SHARDS.length}`,
      retries: 2,
      concurrency: [DB_CONCURRENCY],
    },
    { cron: OPTIONS_SHARD_CRONS[index] },
    async ({ step, logger }) =>
      runOptionsShard(shard, index + 1, OPTIONS_SHARDS.length, step, logger),
  ),
);
