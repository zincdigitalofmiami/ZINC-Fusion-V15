import { inngest } from "./client";
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

type ZlBar5mEvent = {
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

type ZlBar15mEvent = {
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

type ZlBar1hEvent = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
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

function validateBar5m(bar: ZlBar5mEvent): void {
  const ts = parseTimestamp(bar.timestamp);
  validateOhlc(bar.open, bar.high, bar.low, bar.close);
  validateRecent(ts, 48); // 48 hours max age for 5m bars
  if (bar.volume < 0) {
    throw new Error("Volume must be >= 0");
  }
  if (bar.previousClose != null && bar.previousClose <= 0) {
    throw new Error("previousClose must be > 0 when provided");
  }
}

function validateBar15m(bar: ZlBar15mEvent): void {
  const ts = parseTimestamp(bar.timestamp);
  validateOhlc(bar.open, bar.high, bar.low, bar.close);
  validateRecent(ts, 72);
  if (bar.volume < 0) {
    throw new Error("Volume must be >= 0");
  }
  if (bar.previousClose != null && bar.previousClose <= 0) {
    throw new Error("previousClose must be > 0 when provided");
  }
}

function validateBar1h(bar: ZlBar1hEvent): void {
  const ts = parseTimestamp(bar.timestamp);
  validateOhlc(bar.open, bar.high, bar.low, bar.close);
  validateRecent(ts, 168);
  if (bar.volume < 0) {
    throw new Error("Volume must be >= 0");
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

export const zlLive15m = inngest.createFunction(
  { id: "zl-live-15m", name: "ZL Live 15m Bars" },
  { event: "zl.bar.15m" },
  async ({ event }) => {
    // DEBUG: Write receipt to prove function was invoked
    const receiptClient = await pool.connect();
    try {
      await receiptClient.query(
        `INSERT INTO analytics.inngest_receipts (function_id, event_name, event_id, payload)
         VALUES ($1, $2, $3, $4)`,
        ["zl-live-15m", "zl.bar.15m", event.id ?? "unknown", JSON.stringify(event.data)]
      );
    } finally {
      receiptClient.release();
    }

    const bar = event.data as ZlBar15mEvent;
    validateBar15m(bar);
    const previousClose = bar.previousClose ?? null;
    const change = previousClose != null ? bar.close - previousClose : null;
    const changePct = previousClose != null ? (change! / previousClose) * 100 : null;
    const source = bar.source ?? "databento_live";

    const client = await pool.connect();
    try {
      await client.query(
        `INSERT INTO analytics.zl_price_15m
          (timestamp, open, high, low, close, volume, previous_close, change, change_percent, day_high, day_low, source, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
         ON CONFLICT (timestamp) DO UPDATE SET
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

    return { status: "ok", timestamp: bar.timestamp };
  }
);

export const zlLive1h = inngest.createFunction(
  { id: "zl-live-1h", name: "ZL Live 1h Bars" },
  { event: "zl.bar.1h" },
  async ({ event }) => {
    const bar = event.data as ZlBar1hEvent;
    validateBar1h(bar);
    const source = bar.source ?? "databento_live";

    const client = await pool.connect();
    try {
      await client.query(
        `INSERT INTO analytics.zl_price_1h
          (timestamp, open, high, low, close, volume, source, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
         ON CONFLICT (timestamp) DO UPDATE SET
           open = EXCLUDED.open,
           high = EXCLUDED.high,
           low = EXCLUDED.low,
           close = EXCLUDED.close,
           volume = EXCLUDED.volume,
           source = EXCLUDED.source`,
        [
          bar.timestamp,
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

    return { status: "ok", timestamp: bar.timestamp };
  }
);

export const zlLive1d = inngest.createFunction(
  { id: "zl-live-1d", name: "ZL Live 1d Bars" },
  { event: "zl.bar.1d" },
  async ({ event }) => {
    const bar = event.data as ZlBar1dEvent;
    validateBar1d(bar);
    const source = bar.source ?? "databento_live";

    const client = await pool.connect();
    try {
      await client.query(
        `INSERT INTO analytics.zl_price_1d
          (event_date, open, high, low, close, volume, source, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
         ON CONFLICT (event_date) DO UPDATE SET
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
  { id: "zl-live-1m", name: "ZL Live 1m Bars" },
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
          `INSERT INTO analytics.zl_price_1m
            (timestamp, open, high, low, close, volume, previous_close, change, change_percent, day_high, day_low, source, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
           ON CONFLICT (timestamp) DO UPDATE SET
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

    // Step 2: Check if we should aggregate to 5m bar
    // 5m bars close at :00, :05, :10, :15, :20, :25, :30, :35, :40, :45, :50, :55
    const ts = new Date(bar.timestamp);
    const minute = ts.getMinutes();
    const is5mBoundary = minute % 5 === 4; // :04, :09, :14, etc. complete the 5m bar

    if (is5mBoundary) {
      await step.run("aggregate-5m-bar", async () => {
        const client = await pool.connect();
        try {
          // Get the 5 most recent 1m bars ending at this timestamp
          const fiveMinStart = new Date(ts);
          fiveMinStart.setMinutes(Math.floor(minute / 5) * 5);
          fiveMinStart.setSeconds(0);
          fiveMinStart.setMilliseconds(0);

          const barsResult = await client.query(
            `SELECT open, high, low, close, volume, previous_close, day_high, day_low
             FROM analytics.zl_price_1m
             WHERE timestamp >= $1 AND timestamp <= $2
             ORDER BY timestamp ASC`,
            [fiveMinStart.toISOString(), bar.timestamp]
          );

          if (barsResult.rows.length >= 3) { // Need at least 3 bars for meaningful aggregation
            const bars = barsResult.rows;
            const aggregated = {
              open: bars[0].open,
              high: Math.max(...bars.map((b: { high: number }) => b.high)),
              low: Math.min(...bars.map((b: { low: number }) => b.low)),
              close: bars[bars.length - 1].close,
              volume: bars.reduce((sum: number, b: { volume: number }) => sum + (b.volume || 0), 0),
              previousClose: bars[0].previous_close,
              dayHigh: bars[bars.length - 1].day_high,
              dayLow: bars[bars.length - 1].day_low,
            };

            const aggChange = aggregated.previousClose != null
              ? aggregated.close - aggregated.previousClose
              : null;
            const aggChangePct = aggregated.previousClose != null
              ? (aggChange! / aggregated.previousClose) * 100
              : null;

            await client.query(
              `INSERT INTO analytics.zl_price_5m
                (timestamp, open, high, low, close, volume, previous_close, change, change_percent, day_high, day_low, source, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
               ON CONFLICT (timestamp) DO UPDATE SET
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
                fiveMinStart.toISOString(),
                aggregated.open,
                aggregated.high,
                aggregated.low,
                aggregated.close,
                aggregated.volume,
                aggregated.previousClose,
                aggChange,
                aggChangePct,
                aggregated.dayHigh,
                aggregated.dayLow,
                "aggregated_1m",
              ]
            );
          }
        } finally {
          client.release();
        }
      });
    }

    return {
      status: "ok",
      timestamp: bar.timestamp,
      aggregated5m: is5mBoundary
    };
  }
);

// =============================================================================
// ZL 5-MINUTE BARS (Direct ingestion, alternative to aggregation)
// =============================================================================

export const zlLive5m = inngest.createFunction(
  { id: "zl-live-5m", name: "ZL Live 5m Bars" },
  { event: "zl.bar.5m" },
  async ({ event }) => {
    const bar = event.data as ZlBar5mEvent;
    validateBar5m(bar);
    const previousClose = bar.previousClose ?? null;
    const change = previousClose != null ? bar.close - previousClose : null;
    const changePct = previousClose != null ? (change! / previousClose) * 100 : null;
    const source = bar.source ?? "databento_live";

    const client = await pool.connect();
    try {
      await client.query(
        `INSERT INTO analytics.zl_price_5m
          (timestamp, open, high, low, close, volume, previous_close, change, change_percent, day_high, day_low, source, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
         ON CONFLICT (timestamp) DO UPDATE SET
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

    return { status: "ok", timestamp: bar.timestamp };
  }
);
