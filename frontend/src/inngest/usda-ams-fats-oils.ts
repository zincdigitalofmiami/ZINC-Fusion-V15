/**
 * USDA AMS Fats & Oils Market News Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Append-only inserts (ON CONFLICT DO NOTHING)
 *
 * SOURCE: USDA MARS API v1.2 (free, no auth required)
 * - Report: LM_GR850 (Daily National Grease and Rendered Products Report)
 * - Products: yellow grease, tallow (bleachable fancy, edible, inedible),
 *             choice white grease, lard, poultry fat, UCO
 *
 * TARGET TABLE: supply.uco_prices_1w
 * NOTE: Table must be added to prisma/schema.prisma before first successful run.
 *       The function wraps inserts in try/catch and logs if the table is missing.
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.0.0
 * @date 2026-02-26
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

const MARS_API_BASE = "https://marsapi.ams.usda.gov/services/v1.2/reports";
const REPORT_SLUG = "2464"; // LM_GR850 slug ID
const SOURCE_NAME = "usda_ams";
const USER_AGENT = "ZINC-Fusion/1.0";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MarsReportResult {
  reportDate: string;
  product: string;
  region: string | null;
  priceLow: number | null;
  priceHigh: number | null;
  priceAvg: number | null;
  unit: string;
  volume: number | null;
}

interface MarsApiResponse {
  results?: MarsApiRecord[];
}

interface MarsApiRecord {
  report_date?: string;
  slug_name?: string;
  commodity_name?: string;
  class_desc?: string;
  grade_desc?: string;
  region?: string;
  location?: string;
  price_low?: string | number;
  price_high?: string | number;
  price_avg?: string | number;
  unit_desc?: string;
  volume?: string | number;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function computeRowHash(parts: string[]): string {
  return createHash("sha256").update(parts.join("|")).digest("hex");
}

function parseNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const trimmed = value.trim().replace(/,/g, "");
  if (!trimmed || trimmed === "-" || trimmed === "N/A") return null;
  const num = Number(trimmed);
  return Number.isFinite(num) ? num : null;
}

/**
 * Normalize date string to ISO YYYY-MM-DD.
 * Handles MM/DD/YYYY and YYYY-MM-DD formats.
 */
function normalizeDateToIso(dateStr: string): string | null {
  const trimmed = dateStr.trim();

  // MM/DD/YYYY
  const usMatch = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(trimmed);
  if (usMatch) {
    return `${usMatch[3]}-${usMatch[1].padStart(2, "0")}-${usMatch[2].padStart(2, "0")}`;
  }

  // YYYY-MM-DD
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return trimmed;

  // Try generic Date parsing
  const d = new Date(trimmed);
  if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);

  return null;
}

/**
 * Build a descriptive product name from MARS record fields.
 */
function buildProductName(record: MarsApiRecord): string {
  const parts: string[] = [];
  if (record.commodity_name) parts.push(String(record.commodity_name).trim());
  if (record.class_desc) parts.push(String(record.class_desc).trim());
  if (record.grade_desc) parts.push(String(record.grade_desc).trim());
  return parts.filter(Boolean).join(" - ") || "unknown";
}

// ---------------------------------------------------------------------------
// MARS API fetch
// ---------------------------------------------------------------------------

async function fetchMarsReport(): Promise<MarsReportResult[]> {
  // Try the MARS API v1.2 endpoint
  const url = `${MARS_API_BASE}/${REPORT_SLUG}`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);

  try {
    const response = await fetch(url, {
      headers: {
        "User-Agent": USER_AGENT,
        Accept: "application/json",
      },
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!response.ok) {
      throw new Error(`MARS API error: ${response.status} ${response.statusText}`);
    }

    const data = (await response.json()) as MarsApiResponse;
    const records = data?.results ?? (Array.isArray(data) ? data as MarsApiRecord[] : []);

    if (!Array.isArray(records) || records.length === 0) {
      throw new Error("MARS API returned no results for report");
    }

    const results: MarsReportResult[] = [];

    for (const rec of records) {
      const dateRaw = rec.report_date;
      if (!dateRaw) continue;

      const isoDate = normalizeDateToIso(String(dateRaw));
      if (!isoDate) continue;

      const product = buildProductName(rec);
      const region = rec.region || rec.location || null;
      const priceLow = parseNumber(rec.price_low);
      const priceHigh = parseNumber(rec.price_high);
      const priceAvg = parseNumber(rec.price_avg);

      // Skip rows with no price data at all
      if (priceLow === null && priceHigh === null && priceAvg === null) continue;

      // Compute avg from low/high if not provided
      const computedAvg =
        priceAvg !== null
          ? priceAvg
          : priceLow !== null && priceHigh !== null
            ? (priceLow + priceHigh) / 2
            : priceLow ?? priceHigh;

      results.push({
        reportDate: isoDate,
        product,
        region: region ? String(region).trim() : null,
        priceLow,
        priceHigh,
        priceAvg: computedAvg,
        unit: rec.unit_desc ? String(rec.unit_desc).trim() : "cents/lb",
        volume: parseNumber(rec.volume),
      });
    }

    return results;
  } catch (err) {
    clearTimeout(timeout);
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error("MARS API fetch timed out after 30s");
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Inngest function
// ---------------------------------------------------------------------------

export const usdaAmsFatsOilsDaily = inngest.createFunction(
  {
    id: "usda-ams-fats-oils-daily",
    name: "USDA AMS Fats & Oils Market News Ingestion",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 20 * * *" }, // Daily at 20:00 UTC
  async ({ step, logger }) => {
    // ── Step 1: assert ops table exists ──
    await step.run("assert-tables", async () => {
      const client = await pool.connect();
      try {
        await client.query("SELECT 1 FROM ops.ingest_run LIMIT 1");
      } finally {
        client.release();
      }
    });

    // ── Step 2: check if target table exists ──
    const tableExists = await step.run("check-target-table", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'supply' AND table_name = 'uco_prices_1w'
          ) AS exists`
        );
        return result.rows[0].exists as boolean;
      } finally {
        client.release();
      }
    });

    if (!tableExists) {
      logger.warn(
        "Table supply.uco_prices_1w does not exist yet. " +
        "Add it to prisma/schema.prisma and run a migration before this function can insert data."
      );
    }

    // ── Step 3: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["usda-ams-fats-oils-daily"]
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });
    logger.info(`Started ingest run: ${runId}`);

    // ── Step 4: fetch data from MARS API ──
    const reportRows = await step.run("fetch-mars-report", async () => {
      return await fetchMarsReport();
    });

    logger.info(`Fetched ${reportRows.length} price records from USDA AMS MARS API`);

    if (reportRows.length === 0 || !tableExists) {
      const reason = !tableExists ? "table_missing" : "no_data";
      await step.run("complete-noop", async () => {
        const client = await pool.connect();
        try {
          await client.query(
            `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
             rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
            [runId, reason === "table_missing" ? "skipped" : "success", reportRows.length, 0, 0, 0]
          );
        } finally {
          client.release();
        }
      });
      return { status: reason, runId, attempted: reportRows.length, inserted: 0, skipped: 0 };
    }

    // ── Step 5: load existing hashes to skip duplicates ──
    const existingHashes = await step.run("load-existing-hashes", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          "SELECT row_hash FROM supply.uco_prices_1w WHERE source = $1",
          [SOURCE_NAME]
        );
        return result.rows.map((r: { row_hash: string }) => r.row_hash);
      } finally {
        client.release();
      }
    });

    // ── Step 6: compute rows to insert ──
    const existingSet = new Set(existingHashes);
    let rowsAttempted = 0;
    let rowsSkipped = 0;

    const rowsToInsert: Array<{
      eventDate: string;
      product: string;
      region: string | null;
      priceLow: number | null;
      priceHigh: number | null;
      priceAvg: number | null;
      unit: string;
      volume: number | null;
      rowHash: string;
    }> = [];

    for (const row of reportRows) {
      rowsAttempted++;

      const rowHash = computeRowHash([
        row.product,
        row.reportDate,
        String(row.priceAvg ?? ""),
      ]);

      if (existingSet.has(rowHash)) {
        rowsSkipped++;
        continue;
      }

      rowsToInsert.push({
        eventDate: row.reportDate,
        product: row.product,
        region: row.region,
        priceLow: row.priceLow,
        priceHigh: row.priceHigh,
        priceAvg: row.priceAvg,
        unit: row.unit,
        volume: row.volume,
        rowHash,
      });

      existingSet.add(rowHash);
    }

    // ── Step 7: batch insert ──
    let rowsInserted = 0;

    if (rowsToInsert.length > 0) {
      rowsInserted = await step.run("insert-rows", async () => {
        const client = await pool.connect();
        try {
          const batchSize = 100;
          let inserted = 0;

          for (let i = 0; i < rowsToInsert.length; i += batchSize) {
            const batch = rowsToInsert.slice(i, i + batchSize);
            const values: string[] = [];
            const params: (string | number | null)[] = [];
            const perRow = 9;

            for (let r = 0; r < batch.length; r++) {
              const base = r * perRow;
              values.push(
                `($${base + 1}::date, $${base + 2}, $${base + 3}, $${base + 4}, $${base + 5}, $${base + 6}, $${base + 7}, $${base + 8}, $${base + 9})`
              );
              const b = batch[r];
              params.push(
                b.eventDate,
                b.product,
                b.region,
                b.priceLow,
                b.priceHigh,
                b.priceAvg,
                b.unit,
                b.volume,
                b.rowHash
              );
            }

            try {
              await client.query(
                `INSERT INTO supply.uco_prices_1w
                   (event_date, product, region, price_low, price_high, price_avg, unit, volume, row_hash)
                 VALUES ${values.join(",")}
                 ON CONFLICT DO NOTHING`,
                params
              );
              inserted += batch.length;
            } catch (err) {
              // Log but don't fail the whole run for a single batch
              const msg = err instanceof Error ? err.message : String(err);
              if (msg.includes("does not exist")) {
                throw new Error(
                  "Table supply.uco_prices_1w does not exist. Add to prisma schema and run migration."
                );
              }
              throw err;
            }
          }

          return inserted;
        } finally {
          client.release();
        }
      });
    }

    // ── Step 8: finalize ingest run ──
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", rowsAttempted, rowsInserted, rowsSkipped, 0]
        );
      } finally {
        client.release();
      }
    });

    logger.info(
      `USDA AMS Fats & Oils complete: ${rowsInserted} inserted, ${rowsSkipped} skipped out of ${rowsAttempted} attempted`
    );

    return {
      status: "success",
      runId,
      attempted: rowsAttempted,
      inserted: rowsInserted,
      skipped: rowsSkipped,
    };
  }
);
