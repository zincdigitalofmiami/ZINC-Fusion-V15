/**
 * GET /api/zl/chart
 *
 * Legacy chart contract kept for compatibility.
 * Delegates to the canonical session-aware /api/zl/price-1d route so there is
 * only one backend path for ZL daily chart bars.
 */
import { NextRequest, NextResponse } from "next/server";
import { GET as getPrice1d } from "../price-1d/route";

interface Price1dPayload {
  symbol: string;
  interval: string;
  count: number;
  data: Array<{
    timestamp: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>;
  live_rollup?: boolean;
  live_rollup_source_table?: string | null;
  live_rollup_latest_intraday_ts?: string | null;
}

export async function GET(request: NextRequest) {
  const response = await getPrice1d(request);
  if (!response.ok) {
    return response;
  }

  const payload = (await response.json()) as Price1dPayload;
  const series = (payload.data ?? []).map((row) => ({
    time: row.timestamp,
    open: row.open,
    high: row.high,
    low: row.low,
    close: row.close,
    volume: row.volume,
  }));

  return NextResponse.json(
    {
      symbol: payload.symbol ?? "ZL",
      interval: "1d",
      count: series.length,
      live_rollup: payload.live_rollup ?? false,
      live_rollup_source_table: payload.live_rollup_source_table ?? null,
      live_rollup_latest_intraday_ts: payload.live_rollup_latest_intraday_ts ?? null,
      series,
    },
    { headers: new Headers(response.headers) },
  );
}
