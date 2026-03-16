import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest, NextResponse } from "next/server";

import { GET } from "./route";
import { GET as getPrice1d } from "../price-1d/route";

vi.mock("../price-1d/route", () => ({
  GET: vi.fn(),
}));

const getPrice1dMock = vi.mocked(getPrice1d);

describe("api/zl/chart compatibility route", () => {
  beforeEach(() => {
    getPrice1dMock.mockReset();
  });

  it("passes through rollup freshness/degraded metadata from price-1d", async () => {
    getPrice1dMock.mockResolvedValue(
      NextResponse.json(
        {
          symbol: "ZL",
          interval: "1d",
          count: 1,
          live_rollup: true,
          live_rollup_source_table: "analytics.price_1m",
          live_rollup_latest_intraday_ts: "2026-03-16T14:00:00.000Z",
          live_rollup_state: "stale",
          live_rollup_degraded: true,
          live_rollup_age_seconds: 1980,
          live_rollup_error: "rollup timeout",
          data: [
            {
              timestamp: "2026-03-16",
              open: 66.2,
              high: 66.9,
              low: 66.1,
              close: 66.8,
              volume: 5210,
            },
          ],
        },
        { headers: { "Cache-Control": "public, s-maxage=60" } },
      ),
    );

    const response = await GET(
      new NextRequest("http://localhost/api/zl/chart?days=365"),
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.symbol).toBe("ZL");
    expect(payload.live_rollup).toBe(true);
    expect(payload.live_rollup_source_table).toBe("analytics.price_1m");
    expect(payload.live_rollup_state).toBe("stale");
    expect(payload.live_rollup_degraded).toBe(true);
    expect(payload.live_rollup_age_seconds).toBe(1980);
    expect(payload.live_rollup_error).toBe("rollup timeout");
    expect(payload.series).toEqual([
      {
        time: "2026-03-16",
        open: 66.2,
        high: 66.9,
        low: 66.1,
        close: 66.8,
        volume: 5210,
      },
    ]);
  });

  it("returns non-ok upstream response unchanged", async () => {
    getPrice1dMock.mockResolvedValue(
      NextResponse.json({ error: "upstream down" }, { status: 503 }),
    );

    const response = await GET(new NextRequest("http://localhost/api/zl/chart"));
    const payload = await response.json();

    expect(response.status).toBe(503);
    expect(payload).toEqual({ error: "upstream down" });
  });
});
