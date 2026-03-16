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
import { getZlLiveSnapshot } from "@/lib/zl-live-snapshot";

export async function GET() {
  try {
    const best = await getZlLiveSnapshot();

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
        live: best.live,
        age_seconds: best.age_seconds,
        degraded: best.degraded,
        freshness_state: best.freshness_state,
        degraded_reason: best.degraded_reason,
        source_health: best.source_health,
        source_errors: best.source_errors,
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
