import { inngest, DB_CONCURRENCY, RETRIES } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

/**
 * Board Crush Calculation:
 * - 1 bushel soybeans (60 lbs) yields 11 lbs oil + 44 lbs meal (48% protein)
 * - Board Crush = ZS_price - (ZL_price × 0.11) - (ZM_price × 0.022)
 *   where 0.022 = 44 lbs / 2000 lbs per ton
 * - Oil Share = (ZL × 0.11) / ((ZL × 0.11) + (ZM × 0.022))
 *
 * Source: CME Group Soybean Crush Spreads
 * https://www.cmegroup.com/trading/agricultural/grain-and-oilseed/soybean-crush-spreads.html
 */

interface CrushComponents {
  tradeDate: string; // ISO date string (Inngest serializes Date to string)
  zsClose: number;
  zlClose: number;
  zmClose: number;
}

interface CrushResult extends CrushComponents {
  boardCrush: number;
  oilShare: number;
}

type BoardCrushStep = {
  run(id: string, fn: () => Promise<unknown>): Promise<unknown>;
};

type BoardCrushLogger = {
  info(message: string): void;
  warn(message: string): void;
};

function calculateBoardCrush(components: CrushComponents): CrushResult {
  const { zsClose, zlClose, zmClose } = components;

  // CME standard conversion factors
  const oilValue = zlClose * 0.11;      // 11 lbs oil per bushel
  const mealValue = zmClose * 0.022;    // 44 lbs meal / 2000 lbs per ton

  // Board crush: revenue from products minus soybean cost
  const boardCrush = (oilValue + mealValue) - (zsClose / 100);

  // Oil share: percentage of crush value from oil
  const oilShare = oilValue / (oilValue + mealValue);

  return {
    ...components,
    boardCrush: Math.round(boardCrush * 10000) / 10000,
    oilShare: Math.round(oilShare * 1000000) / 1000000,
  };
}

async function runBoardCrushDaily(step: BoardCrushStep, logger: BoardCrushLogger) {
  // Step 1: Fetch latest closes for ZS, ZL, ZM from mkt.futures_1d
  const components = await step.run("fetch-crush-components", async () => {
    const client = await pool.connect();
    try {
      // Get most recent event_date with all three symbols
      const result = await client.query<{
        event_date: Date;
        zs_close: string;
        zl_close: string;
        zm_close: string;
      }>(`
        WITH latest_date AS (
          SELECT event_date
          FROM mkt.futures_1d
          WHERE symbol IN ('ZS', 'ZL', 'ZM')
            AND close IS NOT NULL
          GROUP BY event_date
          HAVING COUNT(DISTINCT symbol) = 3
          ORDER BY event_date DESC
          LIMIT 1
        )
        SELECT
          f.event_date,
          MAX(CASE WHEN f.symbol = 'ZS' THEN f.close END)::text as zs_close,
          MAX(CASE WHEN f.symbol = 'ZL' THEN f.close END)::text as zl_close,
          MAX(CASE WHEN f.symbol = 'ZM' THEN f.close END)::text as zm_close
        FROM mkt.futures_1d f
        JOIN latest_date ld ON f.event_date = ld.event_date
        WHERE f.symbol IN ('ZS', 'ZL', 'ZM')
        GROUP BY f.event_date
      `);

      if (!result.rows.length) {
        return null;
      }

      const row = result.rows[0];
      // Convert Date to ISO string for Inngest serialization
      const eventDate = row.event_date instanceof Date
        ? row.event_date.toISOString().split('T')[0]
        : String(row.event_date).split('T')[0];
      return {
        tradeDate: eventDate,
        zsClose: parseFloat(row.zs_close),
        zlClose: parseFloat(row.zl_close),
        zmClose: parseFloat(row.zm_close),
      };
    } finally {
      client.release();
    }
  }) as CrushComponents | null;

  if (!components) {
    logger.warn("No crush components available for calculation");
    return { status: "no_data", reason: "Missing ZS, ZL, or ZM closes" };
  }

  // Step 2: Calculate board crush and oil share
  const crushResult = await step.run("calculate-crush", async () => {
    return calculateBoardCrush(components as CrushComponents);
  }) as CrushResult;

  logger.info(`Calculated crush for ${crushResult.tradeDate}: board_crush=${crushResult.boardCrush}, oil_share=${crushResult.oilShare}`);

  // Step 3: Upsert into analytics.board_crush_1d
  await step.run("upsert-board-crush", async () => {
    const client = await pool.connect();
    try {
      await client.query(
        `INSERT INTO analytics.board_crush_1d
          (trade_date, zs_close, zl_close, zm_close, board_crush, oil_share, created_at)
         VALUES ($1, $2, $3, $4, $5, $6, NOW())
         ON CONFLICT (trade_date) DO UPDATE SET
           zs_close = EXCLUDED.zs_close,
           zl_close = EXCLUDED.zl_close,
           zm_close = EXCLUDED.zm_close,
           board_crush = EXCLUDED.board_crush,
           oil_share = EXCLUDED.oil_share,
           created_at = NOW()`,
        [
          crushResult.tradeDate,
          crushResult.zsClose,
          crushResult.zlClose,
          crushResult.zmClose,
          crushResult.boardCrush,
          crushResult.oilShare,
        ]
      );
    } finally {
      client.release();
    }
  });

  // Step 4: Also update tariff deadlines countdown
  await step.run("update-tariff-deadlines", async () => {
    const client = await pool.connect();
    try {
      await client.query(`
        UPDATE alt.tariff_deadlines_static
        SET days_to_expiry = deadline_date - CURRENT_DATE,
            last_updated = NOW()
        WHERE is_active = true
      `);
    } finally {
      client.release();
    }
  });

  return {
    status: "success",
    tradeDate: crushResult.tradeDate,
    zsClose: crushResult.zsClose,
    zlClose: crushResult.zlClose,
    zmClose: crushResult.zmClose,
    boardCrush: crushResult.boardCrush,
    oilShare: crushResult.oilShare,
  };
}

/**
 * Board Crush Daily Calculator
 * Runs after market close to calculate daily crush spread and oil share
 *
 * Schedule: 6:00 PM CT Mon-Fri (after CME close at 5:00 PM CT)
 * Source: mkt.futures_1d (ZS, ZL, ZM)
 * Target: analytics.board_crush_1d
 */
export const boardCrushDaily = inngest.createFunction(
  {
    id: "board-crush-daily",
    name: "Board Crush Daily Calculator",
    retries: RETRIES.CRON_INGEST,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "TZ=America/Chicago 0 6 * * *" }, // Daily at 06:00 CT
  async ({ step, logger }) => {
    return runBoardCrushDaily(step, logger);
  }
);

export const boardCrushDailyManual = inngest.createFunction(
  {
    id: "board-crush-daily-manual",
    name: "Board Crush Daily Calculator (Manual)",
    retries: RETRIES.MANUAL,
    concurrency: [DB_CONCURRENCY],
  },
  { event: "board-crush-daily" },
  async ({ step, logger }) => {
    return runBoardCrushDaily(step, logger);
  }
);

/**
 * Board Crush Historical Backfill
 *
 * Calculates board crush for all historical dates where ZS, ZL, ZM are available.
 * Data available from 2000-05-15 (when ZM started trading).
 *
 * Event payload:
 * - startDate?: string (ISO date, default "2000-05-15")
 * - endDate?: string (ISO date, default yesterday)
 * - batchSize?: number (default 500 days per batch)
 */
interface BackfillParams {
  startDate?: string;
  endDate?: string;
  batchSize?: number;
}

export const boardCrushBackfill = inngest.createFunction(
  {
    id: "board-crush-backfill",
    name: "Board Crush Historical Backfill",
    retries: RETRIES.EVENT_INGEST,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { event: "board-crush.backfill" },
  async ({ event, step, logger }) => {
    const params = event.data as BackfillParams;
    const startDate = params.startDate ?? "2000-05-15";
    const endDate = params.endDate ?? new Date(Date.now() - 86400000).toISOString().split("T")[0];
    const batchSize = params.batchSize ?? 500;

    logger.info(`Board Crush Backfill: ${startDate} to ${endDate}, batch size ${batchSize}`);

    // Step 1: Check existing data to avoid duplicates
    const existingRange = await step.run("check-existing-data", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(`
          SELECT MIN(trade_date) as min_date, MAX(trade_date) as max_date, COUNT(*) as count
          FROM analytics.board_crush_1d
        `);
        return result.rows[0];
      } finally {
        client.release();
      }
    });

    logger.info(`Existing board crush: ${existingRange.count} rows, ${existingRange.min_date} to ${existingRange.max_date}`);

    // Step 2: Fetch all dates with complete data (ZS, ZL, ZM all present)
    const allComponents = await step.run("fetch-all-crush-components", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query<{
          event_date: Date;
          zs_close: string;
          zl_close: string;
          zm_close: string;
        }>(`
          SELECT
            f.event_date,
            MAX(CASE WHEN f.symbol = 'ZS' THEN f.close END)::text as zs_close,
            MAX(CASE WHEN f.symbol = 'ZL' THEN f.close END)::text as zl_close,
            MAX(CASE WHEN f.symbol = 'ZM' THEN f.close END)::text as zm_close
          FROM mkt.futures_1d f
          WHERE f.symbol IN ('ZS', 'ZL', 'ZM')
            AND f.close IS NOT NULL
            AND f.event_date >= $1
            AND f.event_date <= $2
          GROUP BY f.event_date
          HAVING COUNT(DISTINCT f.symbol) = 3
          ORDER BY f.event_date
        `, [startDate, endDate]);

        return result.rows.map(row => ({
          tradeDate: row.event_date instanceof Date
            ? row.event_date.toISOString().split('T')[0]
            : String(row.event_date).split('T')[0],
          zsClose: parseFloat(row.zs_close),
          zlClose: parseFloat(row.zl_close),
          zmClose: parseFloat(row.zm_close),
        }));
      } finally {
        client.release();
      }
    });

    logger.info(`Found ${allComponents.length} dates with complete data`);

    if (allComponents.length === 0) {
      return { status: "no_data", startDate, endDate };
    }

    // Step 3: Calculate and insert in batches
    let totalInserted = 0;
    let totalSkipped = 0;

    for (let i = 0; i < allComponents.length; i += batchSize) {
      const batch = allComponents.slice(i, i + batchSize);
      const batchNum = Math.floor(i / batchSize) + 1;

      const batchResult = await step.run(`insert-batch-${batchNum}`, async () => {
        const client = await pool.connect();
        let inserted = 0;
        let skipped = 0;

        try {
          for (const components of batch) {
            const crushResult = calculateBoardCrush(components as CrushComponents);

            // Check if already exists (skip if unchanged)
            const existing = await client.query(
              `SELECT board_crush FROM analytics.board_crush_1d WHERE trade_date = $1`,
              [crushResult.tradeDate]
            );

            if (existing.rows.length > 0) {
              skipped++;
              continue;
            }

            await client.query(
              `INSERT INTO analytics.board_crush_1d
                (trade_date, zs_close, zl_close, zm_close, board_crush, oil_share, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW())
               ON CONFLICT (trade_date) DO NOTHING`,
              [
                crushResult.tradeDate,
                crushResult.zsClose,
                crushResult.zlClose,
                crushResult.zmClose,
                crushResult.boardCrush,
                crushResult.oilShare,
              ]
            );
            inserted++;
          }
        } finally {
          client.release();
        }

        return { inserted, skipped };
      });

      totalInserted += batchResult.inserted;
      totalSkipped += batchResult.skipped;
      logger.info(`Batch ${batchNum}: inserted ${batchResult.inserted}, skipped ${batchResult.skipped}`);
    }

    return {
      status: "success",
      startDate,
      endDate,
      totalDates: allComponents.length,
      inserted: totalInserted,
      skipped: totalSkipped,
    };
  }
);
