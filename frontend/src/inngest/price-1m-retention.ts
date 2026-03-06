import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;
const RETENTION_DAYS = 14;

export const price1mRetentionCleanup = inngest.createFunction(
  {
    id: "price-1m-retention-cleanup",
    name: "Price 1m Retention Cleanup",
    retries: 1,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "15 6 * * *" },
  async ({ logger }) => {
    const client = await pool.connect();
    try {
      const result = await client.query(
        `DELETE FROM analytics.price_1m
         WHERE timestamp < NOW() - ($1::int * INTERVAL '1 day')`,
        [RETENTION_DAYS],
      );

      const deleted = result.rowCount ?? 0;
      logger.info(
        { deleted, retentionDays: RETENTION_DAYS },
        "Deleted expired 1m ZL price rows",
      );

      return {
        status: "success",
        retention_days: RETENTION_DAYS,
        deleted_rows: deleted,
      };
    } finally {
      client.release();
    }
  },
);
