import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

type ZlBar1mEvent = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  previousClose: number | null;
  dayHigh: number | null;
  dayLow: number | null;
  source?: string;
};

type ZlBar1dEvent = {
  eventDate: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source?: string;
};

function parseTimestamp(value: string): Date {
  const ts = new Date(value);
  if (Number.isNaN(ts.getTime())) {
    throw new Error(`Invalid timestamp: ${value}`);
  }
  return ts;
}

function validateOhlc(open: number, high: number, low: number, close: number): void {
  if (!Number.isFinite(open) || !Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(close)) {
    throw new Error("Invalid OHLC values");
  }
  if (open <= 0 || high <= 0 || low <= 0 || close <= 0) {
    throw new Error("OHLC values must be > 0");
  }
  if (high < low) {
    throw new Error("Invalid OHLC: high < low");
  }
}

function validateRecent(ts: Date, maxAgeHours: number): void {
  const now = Date.now();
  const ageMs = now - ts.getTime();
  if (ageMs < -5 * 60 * 1000) {
    throw new Error("Timestamp is in the future");
  }
  if (ageMs > maxAgeHours * 60 * 60 * 1000) {
    throw new Error("Timestamp too old for live ingestion");
  }
}

function validateBar1m(bar: ZlBar1mEvent): void {
  const ts = parseTimestamp(bar.timestamp);
  validateOhlc(bar.open, bar.high, bar.low, bar.close);
  validateRecent(ts, 24); // 24 hours max age for 1m bars
  if (bar.volume < 0) {
    throw new Error("Volume must be >= 0");
  }
  if (bar.previousClose != null && bar.previousClose <= 0) {
    throw new Error("previousClose must be > 0 when provided");
  }
}

function validateBar1d(bar: ZlBar1dEvent): void {
  const ts = parseTimestamp(bar.eventDate);
  validateOhlc(bar.open, bar.high, bar.low, bar.close);
  validateRecent(ts, 400);
  if (bar.volume < 0) {
    throw new Error("Volume must be >= 0");
  }
}

export const zlLive1d = inngest.createFunction(
  { id: "zl-live-1d", name: "ZL Live 1d Bars", concurrency: [DB_CONCURRENCY] },
  { event: "zl.bar.1d" },
  async ({ event }) => {
    const bar = event.data as ZlBar1dEvent;
    validateBar1d(bar);
    const source = bar.source ?? "databento_live";

    const client = await pool.connect();
    try {
      await client.query(
        `INSERT INTO analytics.price_1d
          (event_date, open, high, low, close, volume, source, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
         ON CONFLICT (symbol, event_date) DO UPDATE SET
           open = EXCLUDED.open,
           high = EXCLUDED.high,
           low = EXCLUDED.low,
           close = EXCLUDED.close,
           volume = EXCLUDED.volume,
           source = EXCLUDED.source`,
        [
          bar.eventDate,
          bar.open,
          bar.high,
          bar.low,
          bar.close,
          bar.volume,
          source,
        ]
      );
    } finally {
      client.release();
    }

    return { status: "ok", eventDate: bar.eventDate };
  }
);

// =============================================================================
// ZL 1-MINUTE BARS
// =============================================================================

export const zlLive1m = inngest.createFunction(
  { id: "zl-live-1m", name: "ZL Live 1m Bars", concurrency: [DB_CONCURRENCY] },
  { event: "zl.bar.1m" },
  async ({ event, step }) => {
    const bar = event.data as ZlBar1mEvent;
    validateBar1m(bar);
    const previousClose = bar.previousClose ?? null;
    const change = previousClose != null ? bar.close - previousClose : null;
    const changePct = previousClose != null ? (change! / previousClose) * 100 : null;
    const source = bar.source ?? "databento_live";

    // Step 1: Insert 1m bar
    await step.run("insert-1m-bar", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `INSERT INTO analytics.price_1m
            (timestamp, open, high, low, close, volume, previous_close, change, change_percent, day_high, day_low, source, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
           ON CONFLICT (symbol, timestamp) DO UPDATE SET
             open = EXCLUDED.open,
             high = EXCLUDED.high,
             low = EXCLUDED.low,
             close = EXCLUDED.close,
             volume = EXCLUDED.volume,
             previous_close = EXCLUDED.previous_close,
             change = EXCLUDED.change,
             change_percent = EXCLUDED.change_percent,
             day_high = EXCLUDED.day_high,
             day_low = EXCLUDED.day_low,
             source = EXCLUDED.source`,
          [
            bar.timestamp,
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
            previousClose,
            change,
            changePct,
            bar.dayHigh,
            bar.dayLow,
            source,
          ]
        );
      } finally {
        client.release();
      }
    });

    await step.run("update-latest-price", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE analytics.latest_price
           SET price = $1,
               timestamp = $2,
               updated_at = NOW()
           WHERE id = 1
             AND (timestamp IS NULL OR timestamp <= $2)`,
          [bar.close, bar.timestamp],
        );
      } finally {
        client.release();
      }
    });

    return {
      status: "ok",
      timestamp: bar.timestamp,
    };
  }
);
