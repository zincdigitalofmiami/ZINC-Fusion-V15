import { describe, expect, it } from "vitest";

import type { DatabentoOhlcvBar } from "@/lib/databento";

import { mapDatabentoDailyQuotes } from "./zl-daily";

describe("zl-daily recent backfill mapping", () => {
  it("keeps the full recent daily window instead of only the latest bar", () => {
    const bars: DatabentoOhlcvBar[] = [
      {
        tsEvent: new Date("2026-03-11T00:00:00.000Z"),
        open: 44.1,
        high: 44.5,
        low: 43.9,
        close: 44.3,
        volume: 101,
      },
      {
        tsEvent: new Date("2026-03-12T00:00:00.000Z"),
        open: 44.3,
        high: 44.8,
        low: 44.2,
        close: 44.7,
        volume: 102,
      },
      {
        tsEvent: new Date("2026-03-13T00:00:00.000Z"),
        open: 44.7,
        high: 45.0,
        low: 44.4,
        close: 44.9,
        volume: 103,
      },
    ];

    const quotes = mapDatabentoDailyQuotes(bars);

    expect(quotes).toHaveLength(3);
    expect(quotes.map((quote) => quote.eventDate.toISOString().slice(0, 10))).toEqual([
      "2026-03-11",
      "2026-03-12",
      "2026-03-13",
    ]);
  });

  it("deduplicates repeated daily bars by trade date and keeps the latest payload", () => {
    const quotes = mapDatabentoDailyQuotes([
      {
        tsEvent: new Date("2026-03-13T00:00:00.000Z"),
        open: 44.7,
        high: 45.0,
        low: 44.4,
        close: 44.9,
        volume: 103,
      },
      {
        tsEvent: new Date("2026-03-13T23:59:59.000Z"),
        open: 44.8,
        high: 45.1,
        low: 44.5,
        close: 45.0,
        volume: 104,
      },
    ]);

    expect(quotes).toHaveLength(1);
    expect(quotes[0]).toMatchObject({
      open: 44.8,
      high: 45.1,
      low: 44.5,
      close: 45.0,
      volume: 104,
    });
  });
});
