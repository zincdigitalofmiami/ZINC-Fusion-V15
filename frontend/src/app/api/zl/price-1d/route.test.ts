import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { GET } from "./route";
import { query } from "@/lib/db";

vi.mock("@/lib/db", () => ({
  query: vi.fn(),
}));

const queryMock = vi.mocked(query);

function makeRequest() {
  return new NextRequest("http://localhost/api/zl/price-1d?days=30");
}

describe("api/zl/price-1d live rollup contract", () => {
  beforeEach(() => {
    queryMock.mockReset();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-16T14:33:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("prefers healthy same-session 1m rollup over latest_price fallback", async () => {
    queryMock.mockImplementation(async (sql: string) => {
      if (sql.includes("FROM analytics.price_1d") && sql.includes("event_date as timestamp")) {
        return [
          {
            timestamp: "2026-03-14",
            open: "66.00",
            high: "66.80",
            low: "65.90",
            close: "66.50",
            volume: "1000",
            source: "databento",
          },
        ];
      }
      if (sql.includes("FROM analytics.price_1m")) {
        expect(sql).toContain("GROUP BY sb.trade_date");
        return [
          {
            timestamp: "2026-03-16",
            open: 66.4,
            high: 67.0,
            low: 66.1,
            close: 66.9,
            volume: 7424,
            source: "intraday_rollup_1m",
            latest_ts: "2026-03-16T14:30:00.000Z",
            bar_count: 220,
          },
        ];
      }
      if (sql.includes("FROM analytics.latest_price")) {
        throw new Error("latest_price fallback should not be used when 1m rollup exists");
      }
      throw new Error(`Unexpected SQL: ${sql}`);
    });

    const response = await GET(makeRequest());
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.live_rollup_source_table).toBe("analytics.price_1m");
    expect(payload.live_rollup_state).toBe("live");
    expect(payload.live_rollup_degraded).toBe(false);
    expect(payload.live_rollup_error).toBeNull();
    expect(payload.data[payload.data.length - 1].source).toBe("intraday_rollup_1m");
  });

  it("marks stale intraday rollup as degraded when age breaches threshold", async () => {
    queryMock.mockImplementation(async (sql: string) => {
      if (sql.includes("FROM analytics.price_1d") && sql.includes("event_date as timestamp")) {
        return [];
      }
      if (sql.includes("FROM analytics.price_1m")) {
        expect(sql).toContain("GROUP BY sb.trade_date");
        return [
          {
            timestamp: "2026-03-16",
            open: 66.4,
            high: 67.0,
            low: 66.1,
            close: 66.9,
            volume: 7424,
            source: "intraday_rollup_1m",
            latest_ts: "2026-03-16T14:00:00.000Z",
            bar_count: 120,
          },
        ];
      }
      if (sql.includes("FROM analytics.latest_price")) {
        return [];
      }
      throw new Error(`Unexpected SQL: ${sql}`);
    });

    const response = await GET(makeRequest());
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.live_rollup_state).toBe("stale");
    expect(payload.live_rollup_degraded).toBe(true);
    expect(payload.live_rollup_age_seconds).toBeGreaterThan(5 * 60);
    expect(payload.live_rollup_error).toBeNull();
  });

  it("falls back to latest_price with observable error when 1m rollup query fails", async () => {
    queryMock.mockImplementation(async (sql: string) => {
      if (sql.includes("FROM analytics.price_1d") && sql.includes("event_date as timestamp")) {
        return [];
      }
      if (sql.includes("FROM analytics.price_1m")) {
        expect(sql).toContain("GROUP BY sb.trade_date");
        throw new Error("rollup exploded");
      }
      if (sql.includes("FROM analytics.latest_price")) {
        return [
          {
            trade_date: "2026-03-16",
            price: 66.86,
            timestamp: "2026-03-16T14:10:00.000Z",
            updated_at: "2026-03-16T14:10:01.000Z",
          },
        ];
      }
      throw new Error(`Unexpected SQL: ${sql}`);
    });

    const response = await GET(makeRequest());
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.live_rollup_source_table).toBe("analytics.latest_price");
    expect(payload.live_rollup_state).toBe("fallback");
    expect(payload.live_rollup_degraded).toBe(true);
    expect(payload.live_rollup_error).toContain("rollup exploded");
    expect(payload.data[payload.data.length - 1].source).toBe("latest_price_fallback");
  });
});
