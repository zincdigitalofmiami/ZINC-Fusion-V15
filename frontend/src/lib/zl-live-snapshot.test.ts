import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getZlLiveSnapshot } from "./zl-live-snapshot";
import { query } from "./db";

vi.mock("./db", () => ({
  query: vi.fn(),
}));

const queryMock = vi.mocked(query);

describe("zl-live-snapshot freshness and fallback classification", () => {
  beforeEach(() => {
    queryMock.mockReset();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-16T14:33:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("marks aged 1m source as stale/degraded", async () => {
    queryMock.mockImplementation(async (sql: string) => {
      if (sql.includes("FROM analytics.price_1m")) {
        return [
          {
            timestamp: "2026-03-16T14:20:00.000Z",
            close: 66.8,
            open: 66.1,
            high: 66.9,
            low: 66.0,
            volume: 5000,
            previous_close: 65.9,
          },
        ];
      }
      if (sql.includes("FROM analytics.latest_price")) {
        return [];
      }
      if (sql.includes("FROM analytics.price_1d a")) {
        return [
          {
            event_date: "2026-03-14",
            close: 65.9,
            open: 65.4,
            high: 66.0,
            low: 65.3,
            volume: 9000,
            prev_close: 65.2,
          },
        ];
      }
      throw new Error(`Unexpected SQL: ${sql}`);
    });

    const snapshot = await getZlLiveSnapshot();

    expect(snapshot).not.toBeNull();
    expect(snapshot?.source).toBe("1m");
    expect(snapshot?.freshness_state).toBe("stale");
    expect(snapshot?.degraded).toBe(true);
    expect(snapshot?.live).toBe(false);
    expect(snapshot?.degraded_reason).toBe("intraday_1m_stale");
  });

  it("falls back after 1m failure with explicit source health/error metadata", async () => {
    queryMock.mockImplementation(async (sql: string) => {
      if (sql.includes("FROM analytics.price_1m")) {
        throw new Error("1m outage");
      }
      if (sql.includes("FROM analytics.latest_price")) {
        return [
          {
            price: 66.5,
            timestamp: "2026-03-16T14:30:00.000Z",
            previous_close: 65.9,
          },
        ];
      }
      if (sql.includes("FROM analytics.price_1d a")) {
        return [
          {
            event_date: "2026-03-14",
            close: 65.9,
            open: 65.4,
            high: 66.0,
            low: 65.3,
            volume: 9000,
            prev_close: 65.2,
          },
        ];
      }
      throw new Error(`Unexpected SQL: ${sql}`);
    });

    const snapshot = await getZlLiveSnapshot();

    expect(snapshot).not.toBeNull();
    expect(snapshot?.source).toBe("latest_price");
    expect(snapshot?.freshness_state).toBe("fallback");
    expect(snapshot?.degraded).toBe(true);
    expect(snapshot?.live).toBe(false);
    expect(snapshot?.degraded_reason).toBe("fallback_after_1m_error");
    expect(snapshot?.source_health).toEqual({
      one_minute: "error",
      latest_price: "ok",
      daily: "ok",
    });
    expect(snapshot?.source_errors.one_minute).toContain("1m outage");
  });
});
