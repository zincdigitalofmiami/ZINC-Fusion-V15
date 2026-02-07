/**
 * Options Data Staleness Check
 *
 * Daily check that alerts if any options data is stale (>3 days old).
 * Runs at 7am CT on weekdays to catch issues before market open.
 *
 * NO FAKE DATA - This monitors real Databento-sourced data only.
 */

import { inngest } from "./client";
import pool from "@/lib/db";

interface StaleSymbol {
  underlying: string;
  latest: string;
  days_stale: number;
  row_count: number;
}

export const optionsStalenessCheck = inngest.createFunction(
  {
    id: "options-staleness-check",
    name: "Options Data Staleness Check",
    retries: 1,
    concurrency: [{ limit: 1 }],
  },
  { cron: "TZ=America/Chicago 0 7 * * 1-5" }, // 7am CT weekdays
  async ({ step, logger }) => {
    const staleThreshold = 3; // days

    const staleSymbols = await step.run("check-staleness", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query<StaleSymbol>(
          `
          SELECT
            underlying,
            MAX(event_date)::text as latest,
            (CURRENT_DATE - MAX(event_date))::int as days_stale,
            COUNT(*)::int as row_count
          FROM mkt.options_1d
          WHERE source = 'databento'
          GROUP BY underlying
          HAVING (CURRENT_DATE - MAX(event_date)) > $1
          ORDER BY days_stale DESC
          `,
          [staleThreshold]
        );
        return result.rows;
      } finally {
        client.release();
      }
    });

    const totalCoverage = await step.run("check-coverage", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query<{
          underlying: string;
          latest: string;
          days_stale: number;
          row_count: number;
        }>(
          `
          SELECT
            underlying,
            MAX(event_date)::text as latest,
            (CURRENT_DATE - MAX(event_date))::int as days_stale,
            COUNT(*)::int as row_count
          FROM mkt.options_1d
          WHERE source = 'databento'
          GROUP BY underlying
          ORDER BY underlying
          `
        );
        return result.rows;
      } finally {
        client.release();
      }
    });

    // Log staleness warnings
    if (staleSymbols.length > 0) {
      const staleList = staleSymbols
        .map((s) => `${s.underlying}(${s.days_stale}d)`)
        .join(", ");
      logger.error(`STALE OPTIONS DATA: ${staleList}`);

      // Log details for each stale symbol
      for (const sym of staleSymbols) {
        logger.warn(
          `  ${sym.underlying}: last data ${sym.latest}, ${sym.days_stale} days stale, ${sym.row_count} total rows`
        );
      }
    } else {
      logger.info(
        `All ${totalCoverage.length} options underlyings are fresh (within ${staleThreshold} days)`
      );
    }

    // Check for expected underlyings that are missing entirely
    const expectedUnderlyings = [
      "ZL",
      "ZS",
      "ZM",
      "ZC",
      "ZW",
      "CL",
      "NG",
      "HO",
      "RB",
      "GC",
      "SI",
      "HG",
      "ES",
      "NQ",
      "ZN",
      "ZB",
      "ZF",
      "6E",
      "6J",
      "6B",
      "6A",
      "6C",
    ];

    const presentUnderlyings = new Set(totalCoverage.map((r) => r.underlying));
    const missingUnderlyings = expectedUnderlyings.filter(
      (u) => !presentUnderlyings.has(u)
    );

    if (missingUnderlyings.length > 0) {
      logger.error(
        `MISSING OPTIONS UNDERLYINGS (no data at all): ${missingUnderlyings.join(", ")}`
      );
    }

    return {
      status: staleSymbols.length > 0 ? "stale_data_detected" : "all_fresh",
      timestamp: new Date().toISOString(),
      staleThreshold,
      staleCount: staleSymbols.length,
      staleSymbols: staleSymbols.map((s) => ({
        underlying: s.underlying,
        latestDate: s.latest,
        daysStale: s.days_stale,
      })),
      totalUnderlyings: totalCoverage.length,
      missingUnderlyings,
    };
  }
);
