import { query } from "@/lib/db";
import { zlSessionContextCte } from "@/lib/zl-session";

export type ZlLivePriceSource = "1m" | "latest_price" | "1d";
export type ZlFreshnessState = "live" | "stale" | "fallback";
export type ZlSourceHealth = "ok" | "empty" | "error";

export interface ZlLiveSnapshot {
  price: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  timestamp: string;
  previous_close: number | null;
  change: number | null;
  change_pct: number | null;
  age_seconds: number;
  source: ZlLivePriceSource;
  live: boolean;
  degraded: boolean;
  freshness_state: ZlFreshnessState;
  degraded_reason: string | null;
  source_health: {
    one_minute: ZlSourceHealth;
    latest_price: ZlSourceHealth;
    daily: ZlSourceHealth;
  };
  source_errors: {
    one_minute: string | null;
    latest_price: string | null;
    daily: string | null;
  };
}

interface PriceTier {
  price: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  timestamp: string;
  previous_close: number | null;
  change: number | null;
  change_pct: number | null;
  age_seconds: number;
  source: ZlLivePriceSource;
}

interface SourceAttempt {
  value: PriceTier | null;
  status: ZlSourceHealth;
  error: string | null;
}

const LIVE_THRESHOLD_SECONDS = 5 * 60;

async function getSourceAttempt(
  read: () => Promise<PriceTier | null>,
): Promise<SourceAttempt> {
  try {
    const value = await read();
    return {
      value,
      status: value ? "ok" : "empty",
      error: null,
    };
  } catch (error) {
    return {
      value: null,
      status: "error",
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function getFrom1m(): Promise<PriceTier | null> {
  const rows = await query<{
    timestamp: string;
    close: number;
    open: number;
    high: number;
    low: number;
    volume: number;
    previous_close: number | null;
  }>(`
    WITH ${zlSessionContextCte()}
      , session_bars AS (
        SELECT timestamp, open, high, low, close, COALESCE(volume, 0) AS volume
        FROM analytics.price_1m
        CROSS JOIN session_bounds sb
        WHERE timestamp >= sb.session_start_utc
          AND timestamp <= sb.session_cutoff_utc
          AND close IS NOT NULL
        ORDER BY timestamp ASC
      ),
      session_stats AS (
        SELECT
          (ARRAY_AGG(session_bars.open ORDER BY session_bars.timestamp ASC))[1] AS session_open,
          MAX(session_bars.high) AS session_high,
          MIN(session_bars.low) AS session_low,
          SUM(session_bars.volume)::float8 AS session_volume
        FROM session_bars
      ),
      latest_bar AS (
        SELECT timestamp, open, high, low, close, volume
        FROM session_bars
        ORDER BY timestamp DESC
        LIMIT 1
      )
    SELECT
      latest_bar.timestamp::text AS timestamp,
      latest_bar.close::float8 AS close,
      COALESCE(session_stats.session_open, latest_bar.open)::float8 AS open,
      COALESCE(session_stats.session_high, latest_bar.high)::float8 AS high,
      COALESCE(session_stats.session_low, latest_bar.low)::float8 AS low,
      COALESCE(session_stats.session_volume, latest_bar.volume)::float8 AS volume,
      prev.close::float8 AS previous_close
    FROM latest_bar
    CROSS JOIN session_stats
    CROSS JOIN session_bounds sb
    LEFT JOIN LATERAL (
      SELECT close
      FROM analytics.price_1d
      WHERE close IS NOT NULL
        AND event_date < sb.trade_date
      ORDER BY event_date DESC
      LIMIT 1
    ) prev ON TRUE
  `);

  if (rows.length === 0) return null;

  const row = rows[0];
  const previousClose = row.previous_close;
  const change = previousClose != null ? row.close - previousClose : null;
  const changePct =
    previousClose != null ? (change! / previousClose) * 100 : null;

  return {
    price: row.close,
    open: row.open,
    high: row.high,
    low: row.low,
    volume: row.volume,
    timestamp: row.timestamp,
    previous_close: previousClose,
    change,
    change_pct: changePct,
    age_seconds: Math.round(
      (Date.now() - new Date(row.timestamp).getTime()) / 1000,
    ),
    source: "1m",
  };
}

async function getFromLatestPrice(): Promise<PriceTier | null> {
  const rows = await query<{
    price: number;
    timestamp: string;
    previous_close: number | null;
  }>(`
    WITH ${zlSessionContextCte()}
    SELECT
      lp.price::float8 AS price,
      COALESCE(lp.timestamp, lp.updated_at)::text AS timestamp,
      prev.close::float8 AS previous_close
    FROM analytics.latest_price lp
    CROSS JOIN session_bounds sb
    LEFT JOIN LATERAL (
      SELECT close
      FROM analytics.price_1d
      WHERE close IS NOT NULL
        AND event_date < sb.trade_date
      ORDER BY event_date DESC
      LIMIT 1
    ) prev ON TRUE
    WHERE lp.id = 1
      AND lp.price IS NOT NULL
      AND COALESCE(lp.timestamp, lp.updated_at) >= sb.session_start_utc
      AND COALESCE(lp.timestamp, lp.updated_at) <= sb.session_cutoff_utc
    LIMIT 1
  `);

  if (rows.length === 0) return null;

  const row = rows[0];
  const previousClose = row.previous_close;
  const change = previousClose != null ? row.price - previousClose : null;
  const changePct =
    previousClose != null ? (change! / previousClose) * 100 : null;

  return {
    price: row.price,
    open: row.price,
    high: row.price,
    low: row.price,
    volume: 0,
    timestamp: row.timestamp,
    previous_close: previousClose,
    change,
    change_pct: changePct,
    age_seconds: Math.round(
      (Date.now() - new Date(row.timestamp).getTime()) / 1000,
    ),
    source: "latest_price",
  };
}

async function getFrom1d(): Promise<PriceTier | null> {
  const rows = await query<{
    event_date: string;
    close: number;
    open: number;
    high: number;
    low: number;
    volume: number;
    prev_close: number | null;
  }>(`
    SELECT a.event_date::text, a.close, a.open, a.high, a.low, a.volume,
           (SELECT b.close FROM analytics.price_1d b
            WHERE b.event_date < a.event_date AND b.close IS NOT NULL
            ORDER BY b.event_date DESC LIMIT 1) AS prev_close
    FROM analytics.price_1d a
    WHERE a.close IS NOT NULL
    ORDER BY a.event_date DESC LIMIT 1
  `);

  if (rows.length === 0) return null;

  const row = rows[0];
  const previousClose = row.prev_close ?? row.open;
  const change = row.close - previousClose;
  const changePct = previousClose !== 0 ? (change / previousClose) * 100 : 0;

  return {
    price: row.close,
    open: row.open,
    high: row.high,
    low: row.low,
    volume: row.volume,
    timestamp: row.event_date,
    previous_close: previousClose,
    change,
    change_pct: changePct,
    age_seconds: Math.round(
      (Date.now() - new Date(row.event_date).getTime()) / 1000,
    ),
    source: "1d",
  };
}

export async function getZlLiveSnapshot(): Promise<ZlLiveSnapshot | null> {
  const [from1m, fromLatestPrice, from1d] = await Promise.all([
    getSourceAttempt(() => getFrom1m()),
    getSourceAttempt(() => getFromLatestPrice()),
    getSourceAttempt(() => getFrom1d()),
  ]);

  const best = from1m.value ?? fromLatestPrice.value ?? from1d.value;
  if (!best) return null;

  let previousClose = best.previous_close;
  let change = best.change;
  let changePct = best.change_pct;

  if (best.source !== "1d" && best.change == null && from1d.value) {
    previousClose = from1d.value.previous_close;
    change = best.price - (from1d.value.previous_close ?? best.open);
    changePct = from1d.value.previous_close
      ? ((best.price - from1d.value.previous_close) / from1d.value.previous_close) * 100
      : null;
  }

  const freshnessState: ZlFreshnessState =
    best.source === "1m"
      ? best.age_seconds < LIVE_THRESHOLD_SECONDS
        ? "live"
        : "stale"
      : "fallback";

  const degraded = freshnessState !== "live";
  let degradedReason: string | null = null;
  if (freshnessState === "stale") {
    degradedReason = "intraday_1m_stale";
  } else if (best.source === "latest_price") {
    degradedReason =
      from1m.status === "error"
        ? "fallback_after_1m_error"
        : "fallback_latest_price";
  } else if (best.source === "1d") {
    degradedReason =
      from1m.status === "error"
        ? "fallback_daily_after_1m_error"
        : fromLatestPrice.status === "error"
          ? "fallback_daily_after_latest_price_error"
          : "fallback_daily";
  }

  return {
    ...best,
    previous_close: previousClose,
    change,
    change_pct: changePct,
    live: freshnessState === "live",
    degraded,
    freshness_state: freshnessState,
    degraded_reason: degradedReason,
    source_health: {
      one_minute: from1m.status,
      latest_price: fromLatestPrice.status,
      daily: from1d.status,
    },
    source_errors: {
      one_minute: from1m.error,
      latest_price: fromLatestPrice.error,
      daily: from1d.error,
    },
  };
}
