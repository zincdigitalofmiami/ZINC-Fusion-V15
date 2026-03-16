import { describe, expect, it, vi } from "vitest";

import {
  ZL_1M_INTRADAY_REFRESH_CRON,
  isWithinZlManagedSessionWindow,
  runZl1mIntradayRefresh,
} from "./zl-1m-backfill";

describe("zl-1m managed intraday refresh", () => {
  it("defines a session-aware managed cron schedule", () => {
    expect(ZL_1M_INTRADAY_REFRESH_CRON).toBe("TZ=America/Chicago */3 * * * *");
  });

  it("identifies in-session and out-of-session windows in Chicago time", () => {
    expect(
      isWithinZlManagedSessionWindow(new Date("2026-03-16T12:00:00.000Z")), // Mon 07:00 CT
    ).toBe(true);
    expect(
      isWithinZlManagedSessionWindow(new Date("2026-03-16T21:00:00.000Z")), // Mon 16:00 CT
    ).toBe(false);
    expect(
      isWithinZlManagedSessionWindow(new Date("2026-03-16T00:30:00.000Z")), // Sun 19:30 CT
    ).toBe(true);
    expect(
      isWithinZlManagedSessionWindow(new Date("2026-03-21T16:00:00.000Z")), // Sat 11:00 CT
    ).toBe(false);
  });

  it("runs the shared refresh helper with managed intraday options", async () => {
    const refreshMock = vi.fn().mockResolvedValue({
      skipped: false,
      upserted1m: 42,
      bars: [{ tsEvent: new Date("2026-03-16T14:31:00.000Z") }],
      effectiveEndIso: "2026-03-16T14:31:00.000Z",
    });

    const result = await runZl1mIntradayRefresh(
      refreshMock,
      new Date("2026-03-16T14:33:00.000Z"),
    );

    expect(refreshMock).toHaveBeenCalledWith({
      force: true,
      lookbackMinutes: 12 * 60,
      endLagMinutes: 2,
      maxBarsToUpsert: 720,
    });
    expect(result).toEqual({
      status: "success",
      upserted1m: 42,
      latestBar: "2026-03-16T14:31:00.000Z",
      age_seconds: 120,
    });
  });

  it("skips refresh outside session window", async () => {
    const refreshMock = vi.fn();

    const result = await runZl1mIntradayRefresh(
      refreshMock,
      new Date("2026-03-16T21:00:00.000Z"),
    );

    expect(refreshMock).not.toHaveBeenCalled();
    expect(result.status).toBe("skipped_outside_session");
  });
});
