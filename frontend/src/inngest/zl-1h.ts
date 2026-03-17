import { inngest, DB_CONCURRENCY, RETRIES } from "./client";
import {
  fetchDatabentoCsvWithAvailableEndRetry,
  parseDatabentoOhlcvCsv,
} from "../lib/databento";
import dbPool from "@/lib/db";

const pool = dbPool;

// CME ZL session: Sun 19:00 CT → Fri 13:20 CT.  Guard uses 14:00 CT
// close so the :05 cron catches the final 13:00-13:20 bar.
const SESSION_OPEN_CT = 19 * 60;       // 19:00 CT in minutes
const SESSION_CLOSE_GUARD_CT = 14 * 60; // 14:00 CT (40-min buffer past 13:20)

function isWithinCmeSession(now = new Date()): boolean {
  const ct = new Date(
    now.toLocaleString("en-US", { timeZone: "America/Chicago" }),
  );
  const day = ct.getDay(); // 0=Sun, 6=Sat
  const minutes = ct.getHours() * 60 + ct.getMinutes();

  if (day === 6) return false; // Saturday — closed all day
  if (day === 0) return minutes >= SESSION_OPEN_CT; // Sunday opens 19:00 CT
  if (day >= 1 && day <= 4) {
    // Mon-Thu: open overnight until 13:20, re-opens 19:00.
    return minutes <= SESSION_CLOSE_GUARD_CT || minutes >= SESSION_OPEN_CT;
  }
  // Friday: open through 13:20 only (no evening reopen).
  return minutes <= SESSION_CLOSE_GUARD_CT;
}

/** How far back to look when the table already has data. */
const BACKFILL_WINDOW_DAYS = 3;
/** Cold-start window when the table is empty. */
const DEFAULT_WINDOW_DAYS = 14;

type HourlyBar = {
  eventTime: string; // ISO 8601 — Inngest steps serialize through JSON
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

/**
 * Group 1h bars into trade-date buckets using CME session rules.
 * Session = previous day 19:00 CT → trade date 13:20 CT.
 */
function groupByTradeDate(
  bars: HourlyBar[],
): Map<string, HourlyBar[]> {
  const buckets = new Map<string, HourlyBar[]>();
  for (const bar of bars) {
    const ct = new Date(
      new Date(bar.eventTime).toLocaleString("en-US", { timeZone: "America/Chicago" }),
    );
    const ctHour = ct.getHours();
    // Bars from 19:00+ CT belong to the NEXT calendar day's trade date.
    const tradeDate = new Date(ct);
    if (ctHour >= 19) {
      tradeDate.setDate(tradeDate.getDate() + 1);
    }
    // Skip weekends (Saturday trade dates shouldn't exist).
    const dow = tradeDate.getDay();
    if (dow === 0) tradeDate.setDate(tradeDate.getDate() + 1); // Sun→Mon
    if (dow === 6) continue; // Sat — skip
    const key = `${tradeDate.getFullYear()}-${String(tradeDate.getMonth() + 1).padStart(2, "0")}-${String(tradeDate.getDate()).padStart(2, "0")}`;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key)!.push(bar);
  }
  return buckets;
}

/**
 * ZL 1-hour bars from Databento → analytics.price_1h + daily rollup → analytics.price_1d.
 *
 * This is the PRIMARY chart data source.  It runs hourly, fetches the latest
 * available 1h bars from Databento, upserts them, and synthesizes daily OHLCV
 * bars so the chart never waits for the lagging ohlcv-1d schema.
 */
export const zl1h = inngest.createFunction(
  {
    id: "zl-1h",
    name: "ZL 1h Bars (Databento)",
    retries: RETRIES.CRON_INGEST,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "5 * * * *" },
  async ({ step, logger }) => {
    // Skip outside CME session hours (Sat all day, Sun before 19:00 CT,
    // Fri after ~14:00 CT).  Saves Databento API calls.
    if (!isWithinCmeSession()) {
      return { status: "skipped", message: "Outside CME session window" };
    }

    // Compute fetch window: start from last stored bar (minus overlap), end at NOW.
    const { startStr, endStr } = await step.run("compute-window", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query<{ ts: Date | null }>(
          `SELECT MAX(timestamp) AS ts FROM analytics.price_1h`,
        );
        const lastTs = result.rows[0]?.ts
          ? new Date(result.rows[0].ts)
          : null;
        const end = new Date();
        const startMs = lastTs
          ? lastTs.getTime() - BACKFILL_WINDOW_DAYS * 86_400_000
          : end.getTime() - DEFAULT_WINDOW_DAYS * 86_400_000;
        return {
          startStr: new Date(Math.max(0, startMs)).toISOString(),
          endStr: end.toISOString(),
        };
      } finally {
        client.release();
      }
    });

    // Fetch 1h bars from Databento (auto-clamps end to available_end on 422).
    const bars: HourlyBar[] = await step.run("fetch-databento-1h", async () => {
      try {
        const { csv } = await fetchDatabentoCsvWithAvailableEndRetry(
          {
            dataset: "GLBX.MDP3",
            schema: "ohlcv-1h",
            symbols: "ZL.n.0",
            stype_in: "continuous",
            start: startStr,
            end: endStr,
            encoding: "csv",
            pretty_ts: "true",
            pretty_px: "true",
          },
          15_000,
        );
        return parseDatabentoOhlcvCsv(csv).map((b) => ({
          eventTime: b.tsEvent.toISOString(),
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
          volume: b.volume ?? 0,
        }));
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        logger.warn(`Databento 1h fetch failed: ${msg}`);
        return [];
      }
    });

    if (bars.length === 0) {
      return { status: "no_data", message: "No hourly bars returned" };
    }

    // Upsert 1h bars.
    const upsertedCount = await step.run("upsert-1h-bars", async () => {
      const client = await pool.connect();
      let count = 0;
      try {
        for (const bar of bars) {
          await client.query(
            `INSERT INTO analytics.price_1h
              (timestamp, open, high, low, close, volume, source, created_at)
             VALUES ($1, $2, $3, $4, $5, $6, 'databento', NOW())
             ON CONFLICT (symbol, timestamp) DO UPDATE SET
               open = EXCLUDED.open, high = EXCLUDED.high,
               low = EXCLUDED.low, close = EXCLUDED.close,
               volume = EXCLUDED.volume, source = EXCLUDED.source`,
            [bar.eventTime, bar.open, bar.high, bar.low, bar.close, bar.volume],
          );
          count++;
        }
      } finally {
        client.release();
      }
      return count;
    });

    // Synthesize daily bars from 1h buckets and upsert into price_1d.
    const dailyCount = await step.run("synthesize-daily-bars", async () => {
      const buckets = groupByTradeDate(bars);
      const client = await pool.connect();
      let count = 0;
      try {
        for (const [tradeDate, sessionBars] of buckets) {
          if (sessionBars.length === 0) continue;
          sessionBars.sort((a, b) => a.eventTime.localeCompare(b.eventTime));
          const o = sessionBars[0].open;
          const c = sessionBars[sessionBars.length - 1].close;
          const h = Math.max(...sessionBars.map((b) => b.high));
          const l = Math.min(...sessionBars.map((b) => b.low));
          const v = sessionBars.reduce((s, b) => s + b.volume, 0);

          await client.query(
            `INSERT INTO analytics.price_1d
              (event_date, open, high, low, close, volume, source, created_at)
             VALUES ($1, $2, $3, $4, $5, $6, 'databento_1h_rollup', NOW())
             ON CONFLICT (symbol, event_date) DO UPDATE SET
               open = EXCLUDED.open, high = EXCLUDED.high,
               low = EXCLUDED.low, close = EXCLUDED.close,
               volume = EXCLUDED.volume, source = EXCLUDED.source
             WHERE analytics.price_1d.source IS DISTINCT FROM 'databento'`,
            [tradeDate, o, h, l, c, v],
          );
          count++;
        }
      } finally {
        client.release();
      }
      return count;
    });

    // Update latest_price from the newest bar.
    await step.run("update-latest-price", async () => {
      const newest = bars[bars.length - 1];
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE analytics.latest_price
           SET price = $1, timestamp = $2, updated_at = NOW()
           WHERE id = 1 AND (timestamp IS NULL OR timestamp < $2)`,
          [newest.close, newest.eventTime],
        );
      } finally {
        client.release();
      }
    });

    const lastBar = bars[bars.length - 1];
    return {
      status: "success",
      symbol: "ZL",
      hourlyBars: upsertedCount,
      dailyBars: dailyCount,
      latestBar: lastBar.eventTime,
    };
  },
);
