/**
 * GET /api/zl/live
 *
 * Returns the FRESHEST ZL price available, cascading through all timeframes:
 *   1m → 15m → 1h → 1d
 *
 * Response always includes:
 *   - price, change, change_pct
 *   - source: which table provided the price ("1m" | "15m" | "1h" | "1d")
 *   - live: true only if 1m data is < 5 min old (market is actively trading)
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
    FROM analytics.zl_price_1m
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

// ---------------------------------------------------------------------------
// Tier 2: 15-minute bars
// ---------------------------------------------------------------------------
async function getFrom15m(): Promise<PriceTier | null> {
  const rows = await query<{
    timestamp: string;
    close: number;
    open: number;
    high: number;
    low: number;
    volume: number;
  }>(`
    SELECT timestamp, close, open, high, low, volume
    FROM analytics.zl_price_15m
    ORDER BY timestamp DESC LIMIT 1
  `);
  if (rows.length === 0) return null;
  const r = rows[0];
  return {
    price: r.close,
    open: r.open,
    high: r.high,
    low: r.low,
    volume: r.volume,
    timestamp: r.timestamp,
    previous_close: null,
    change: null,
    change_pct: null,
    age_seconds: Math.round(
      (Date.now() - new Date(r.timestamp).getTime()) / 1000,
    ),
    source: "15m",
  };
}

// ---------------------------------------------------------------------------
// Tier 3: 1-hour bars
// ---------------------------------------------------------------------------
async function getFrom1h(): Promise<PriceTier | null> {
  const rows = await query<{
    timestamp: string;
    close: number;
    open: number;
    high: number;
    low: number;
    volume: number;
  }>(`
    SELECT timestamp, close, open, high, low, volume
    FROM analytics.zl_price_1h
    ORDER BY timestamp DESC LIMIT 1
  `);
  if (rows.length === 0) return null;
  const r = rows[0];
  return {
    price: r.close,
    open: r.open,
    high: r.high,
    low: r.low,
    volume: r.volume,
    timestamp: r.timestamp,
    previous_close: null,
    change: null,
    change_pct: null,
    age_seconds: Math.round(
      (Date.now() - new Date(r.timestamp).getTime()) / 1000,
    ),
    source: "1h",
  };
}

// ---------------------------------------------------------------------------
// Tier 4: Daily bars (always exists, may be days old on weekends)
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
           (SELECT b.close FROM analytics.zl_price_1d b
            WHERE b.event_date < a.event_date AND b.close IS NOT NULL
            ORDER BY b.event_date DESC LIMIT 1) AS prev_close
    FROM analytics.zl_price_1d a
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
    // Fire all 4 queries in parallel — pick the freshest one
    const [t1m, t15m, t1h, t1d] = await Promise.all([
      getFrom1m().catch(() => null),
      getFrom15m().catch(() => null),
      getFrom1h().catch(() => null),
      getFrom1d().catch(() => null),
    ]);

    // Waterfall: use the freshest (lowest age_seconds) tier that returned data
    const tiers = [t1m, t15m, t1h, t1d].filter(Boolean) as PriceTier[];
    if (tiers.length === 0) {
      return NextResponse.json({
        symbol: "ZL",
        price: null,
        timestamp: null,
        updated_at: new Date().toISOString(),
        source: "none",
        live: false,
        error: "No ZL price data in any table",
      });
    }

    // Sort by freshness (lowest age wins)
    tiers.sort((a, b) => a.age_seconds - b.age_seconds);
    const best = tiers[0];

    // If we have 1m data AND change/change_pct are null, fill from 1d
    if (best.source !== "1d" && best.change == null && t1d) {
      best.previous_close = t1d.previous_close;
      best.change = best.price - (t1d.previous_close ?? best.open);
      best.change_pct = t1d.previous_close
        ? ((best.price - t1d.previous_close) / t1d.previous_close) * 100
        : null;
    }

    const isLive =
      best.source === "1m" && best.age_seconds < LIVE_THRESHOLD_SECONDS;

    return NextResponse.json({
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
    });
  } catch (error) {
    console.error("ZL live price error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Price fetch failed" },
      { status: 500 },
    );
  }
}
