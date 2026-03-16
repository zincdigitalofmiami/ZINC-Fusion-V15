import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";
import { getZlLiveSnapshot } from "@/lib/zl-live-snapshot";

vi.mock("@/lib/zl-live-snapshot", () => ({
  getZlLiveSnapshot: vi.fn(),
}));

const getZlLiveSnapshotMock = vi.mocked(getZlLiveSnapshot);

describe("api/zl/live freshness contract", () => {
  beforeEach(() => {
    getZlLiveSnapshotMock.mockReset();
  });

  it("exposes stale/degraded state when 1m data breaches freshness threshold", async () => {
    getZlLiveSnapshotMock.mockResolvedValue({
      price: 66.82,
      open: 66.12,
      high: 67.01,
      low: 66.03,
      volume: 9021,
      timestamp: "2026-03-16T14:20:00.000Z",
      previous_close: 65.98,
      change: 0.84,
      change_pct: 1.27,
      age_seconds: 780,
      source: "1m",
      live: false,
      degraded: true,
      freshness_state: "stale",
      degraded_reason: "intraday_1m_stale",
      source_health: {
        one_minute: "ok",
        latest_price: "ok",
        daily: "ok",
      },
      source_errors: {
        one_minute: null,
        latest_price: null,
        daily: null,
      },
    });

    const response = await GET();
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.symbol).toBe("ZL");
    expect(payload.source).toBe("1m");
    expect(payload.live).toBe(false);
    expect(payload.degraded).toBe(true);
    expect(payload.freshness_state).toBe("stale");
    expect(payload.degraded_reason).toBe("intraday_1m_stale");
    expect(payload.source_health).toEqual({
      one_minute: "ok",
      latest_price: "ok",
      daily: "ok",
    });
    expect(payload.source_errors).toEqual({
      one_minute: null,
      latest_price: null,
      daily: null,
    });
  });

  it("keeps fallback responses usable but clearly non-live", async () => {
    getZlLiveSnapshotMock.mockResolvedValue({
      price: 66.4,
      open: 66.4,
      high: 66.4,
      low: 66.4,
      volume: 0,
      timestamp: "2026-03-16T14:15:00.000Z",
      previous_close: 65.9,
      change: 0.5,
      change_pct: 0.76,
      age_seconds: 1080,
      source: "latest_price",
      live: false,
      degraded: true,
      freshness_state: "fallback",
      degraded_reason: "fallback_latest_price",
      source_health: {
        one_minute: "empty",
        latest_price: "ok",
        daily: "ok",
      },
      source_errors: {
        one_minute: null,
        latest_price: null,
        daily: null,
      },
    });

    const response = await GET();
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.source).toBe("latest_price");
    expect(payload.live).toBe(false);
    expect(payload.degraded).toBe(true);
    expect(payload.freshness_state).toBe("fallback");
    expect(payload.degraded_reason).toBe("fallback_latest_price");
  });
});
