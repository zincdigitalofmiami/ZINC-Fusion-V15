/**
 * GET /api/zl/live
 *
 * Returns the freshest ZL price available from the slim serving contract:
 *   1m -> latest_price -> 1d
 *
 * Response always includes:
 *   - price, change, change_pct
 *   - source: which table provided the price ("1m" | "latest_price" | "1d")
 *   - live: true only if the chosen non-daily source is < 5 min old
 *   - age_seconds: how old the price is
 */
import { NextResponse } from "next/server";
import { query } from "@/lib/db";

// ---------------------------------------------------------------------------
// Each tier returns the same shape
// ---------------------------------------------------------------------------
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
  source: string;
}

// ---------------------------------------------------------------------------
// Tier 1: 1-minute bars (freshest possible)
// ---------------------------------------------------------------------------
async function getFrom1m(): Promise<PriceTier | null> {
  const rows = await query<{
    timestamp: string;
    close: number;
    open: number;
    high: number;
    low: number;
    volume: number;
    previous_close: number | null;
    change: number | null;
    change_percent: number | null;
    day_high: number | null;
    day_low: number | null;
  }>(`
    SELECT timestamp, close, open, high, low, volume,
           previous_close, change, change_percent, day_high, day_low
    FROM analytics.price_1m
    WHERE timestamp >= CURRENT_DATE::timestamptz
    ORDER BY timestamp DESC LIMIT 1
  `);
  if (rows.length === 0) return null;
  const r = rows[0];
  return {
    price: r.close,
    open: r.open,
    high: r.day_high ?? r.high,
    low: r.day_low ?? r.low,
    volume: r.volume,
    timestamp: r.timestamp,
    previous_close: r.previous_close,
    change: r.change,
    change_pct: r.change_percent,
    age_seconds: Math.round(
      (Date.now() - new Date(r.timestamp).getTime()) / 1000,
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
    SELECT
      lp.price::float8 AS price,
      COALESCE(lp.timestamp, lp.updated_at)::text AS timestamp,
      prev.close::float8 AS previous_close
    FROM analytics.latest_price lp
    LEFT JOIN LATERAL (
      SELECT close
      FROM analytics.price_1d
      WHERE close IS NOT NULL
        AND event_date < CURRENT_DATE
      ORDER BY event_date DESC
      LIMIT 1
    ) prev ON TRUE
    WHERE lp.id = 1
      AND lp.price IS NOT NULL
      AND COALESCE(lp.timestamp, lp.updated_at) >= CURRENT_DATE::timestamptz
    LIMIT 1
  `);
  if (rows.length === 0) return null;
  const r = rows[0];
  const previousClose = r.previous_close;
  const change = previousClose != null ? r.price - previousClose : null;
  const changePct = previousClose != null ? (change! / previousClose) * 100 : null;
  return {
    price: r.price,
    open: r.price,
    high: r.price,
    low: r.price,
    volume: 0,
    timestamp: r.timestamp,
    previous_close: previousClose,
    change,
    change_pct: changePct,
    age_seconds: Math.round(
      (Date.now() - new Date(r.timestamp).getTime()) / 1000,
    ),
    source: "latest_price",
  };
}

// ---------------------------------------------------------------------------
// Tier 3: Daily bars (always exists, may be days old on weekends)
// ---------------------------------------------------------------------------
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
  const r = rows[0];
  const prevClose = r.prev_close ?? r.open;
  const change = r.close - prevClose;
  const changePct = prevClose !== 0 ? (change / prevClose) * 100 : 0;
  return {
    price: r.close,
    open: r.open,
    high: r.high,
    low: r.low,
    volume: r.volume,
    timestamp: r.event_date,
    previous_close: prevClose,
    change,
    change_pct: changePct,
    age_seconds: Math.round(
      (Date.now() - new Date(r.event_date).getTime()) / 1000,
    ),
    source: "1d",
  };
}

// ---------------------------------------------------------------------------
// HANDLER — waterfall through all timeframes, always return something
// ---------------------------------------------------------------------------
const LIVE_THRESHOLD_SECONDS = 5 * 60; // <5 min = market is trading right now

export async function GET() {
  try {
    // Query all sources in parallel, then apply the explicit serving-order
    // waterfall rather than sorting by timestamp.
    const [t1m, latestPrice, t1d] = await Promise.all([
      getFrom1m().catch(() => null),
      getFromLatestPrice().catch(() => null),
      getFrom1d().catch(() => null),
    ]);

    const best = t1m ?? latestPrice ?? t1d;

    if (!best) {
      return NextResponse.json(
        {
          symbol: "ZL",
          price: null,
          timestamp: null,
          updated_at: new Date().toISOString(),
          source: "none",
          live: false,
          error: "No ZL price data in the active serving tables",
        },
        { headers: { "Cache-Control": "no-store, max-age=0" } },
      );
    }

    if (best.source !== "1d" && best.change == null && t1d) {
      best.previous_close = t1d.previous_close;
      best.change = best.price - (t1d.previous_close ?? best.open);
      best.change_pct = t1d.previous_close
        ? ((best.price - t1d.previous_close) / t1d.previous_close) * 100
        : null;
    }

    const isLive =
      best.source !== "1d" && best.age_seconds < LIVE_THRESHOLD_SECONDS;

    return NextResponse.json(
      {
        symbol: "ZL",
        price: best.price,
        timestamp: best.timestamp,
        volume: best.volume,
        open: best.open,
        high: best.high,
        low: best.low,
        updated_at: new Date().toISOString(),
        previous_close: best.previous_close,
        change: best.change,
        change_pct: best.change_pct,
        source: best.source,
        live: isLive,
        age_seconds: best.age_seconds,
      },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  } catch (error) {
    console.error("ZL live price error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Price fetch failed" },
      { status: 500 },
    );
  }
}
