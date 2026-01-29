import { inngest } from "./client";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

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

/**
 * Board Crush Daily Calculator
 * Runs after market close to calculate daily crush spread and oil share
 *
 * Schedule: 6:00 PM CT Mon-Fri (after CME close at 5:00 PM CT)
 * Source: mkt.futures_1d (ZS, ZL, ZM)
 * Target: analytics.board_crush_1d
 */
export const boardCrushDaily = inngest.createFunction(
  { id: "board-crush-daily", name: "Board Crush Daily Calculator" },
  { cron: "TZ=America/Chicago 0 */8 * * *" }, // Every 8 hours (0:00, 8:00, 16:00 CT)
  async ({ step, logger }) => {
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
    });

    if (!components) {
      logger.warn("No crush components available for calculation");
      return { status: "no_data", reason: "Missing ZS, ZL, or ZM closes" };
    }

    // Step 2: Calculate board crush and oil share
    const crushResult = await step.run("calculate-crush", async () => {
      return calculateBoardCrush(components as CrushComponents);
    });

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
          UPDATE alt.tariff_deadlines
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
);
