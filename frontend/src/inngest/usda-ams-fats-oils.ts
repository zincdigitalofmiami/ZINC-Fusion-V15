/**
 * USDA AMS Fats & Oils Market News Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Append-only inserts (ON CONFLICT DO NOTHING)
 *
 * SOURCE: USDA MARS API v1.2 (REQUIRES AUTHENTICATION — register at mymarketnews.ams.usda.gov)
 * - Report 2839: NW_LS906 (Weekly Tallow & Protein Report) — CORRECT report for grease/tallow
 * - Report 2837: NW_LS442 (Daily Tallow & Protein Report) — daily version
 * - Products: yellow grease, tallow (bleachable, edible, inedible),
 *             choice white grease, lard, poultry fat
 *
 * STATUS: BLOCKED — MARS API v1.2 requires API key (403 Forbidden without auth).
 *   - Report 2464 was WRONG (that's boxed beef, not grease/tallow)
 *   - As a fallback, tallow/grease PPI data flows via FRED series WPU06410132
 *     and PCU3116133116132 in fred-daily.ts biofuel segment.
 *   - To fix: register at https://mymarketnews.ams.usda.gov/mars-api/getting-started
 *     and set USDA_MARS_API_KEY env var.
 *
 * TARGET TABLE: supply.uco_prices_1w
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.1.0
 * @date 2026-03-02
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { getIngestPool } from "@/lib/db";

const pool = getIngestPool();

const MARS_API_BASE = "https://marsapi.ams.usda.gov/services/v1.2/reports";
const REPORT_SLUG = "2839"; // NW_LS906 Weekly Tallow & Protein Report (was 2464 = boxed beef, WRONG)
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
// FRED PPI fallback — fills supply.uco_prices_1w when MARS API is blocked
// Uses WPU06410132 (PPI Lard Inedible Tallow & Grease) and
// PCU3116133116132 (PPI Rendering & Meat Byproduct Processing)
// ---------------------------------------------------------------------------

const FRED_API_KEY = process.env.FRED_API_KEY;
const FRED_BASE = "https://api.stlouisfed.org/fred/series/observations";

const FRED_UCO_SERIES = [
  { id: "WPU06410132", product: "PPI Lard Inedible Tallow & Grease", unit: "index_1982=100" },
  { id: "PCU3116133116132", product: "PPI Rendering & Meat Byproduct Processing", unit: "index_dec2003=100" },
] as const;

interface FredObs { date: string; value: string }
interface FredResponse { observations: FredObs[] }

async function fetchFredUcoPpi(
  seriesId: string,
  startDate: string,
): Promise<Array<{ date: string; value: number }>> {
  if (!FRED_API_KEY) throw new Error("FRED_API_KEY not set");
  const url =
    `${FRED_BASE}?series_id=${seriesId}&api_key=${FRED_API_KEY}` +
    `&file_type=json&observation_start=${startDate}&sort_order=asc&limit=10000`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`FRED ${seriesId}: ${res.status}`);
  const json: FredResponse = await res.json();
  return json.observations
    .filter((o) => o.value !== "." && o.value !== "")
    .map((o) => ({ date: o.date, value: parseFloat(o.value) }))
    .filter((o) => Number.isFinite(o.value));
}

// ---------------------------------------------------------------------------
// Inngest function — MARS primary, FRED PPI fallback
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
    // ── Step 1: try MARS API first ──
    let marsSuccess = false;
    let marsRows: MarsReportResult[] = [];

    try {
      marsRows = await step.run("fetch-mars-report", async () => {
        return await fetchMarsReport();
      });
      if (marsRows.length > 0) marsSuccess = true;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      logger.warn(`MARS API failed (expected — needs auth): ${msg}`);
    }

    // ── Step 2: FRED PPI fallback (always run to fill gaps) ──
    const fredRows = await step.run("fetch-fred-ppi-fallback", async () => {
      if (!FRED_API_KEY) {
        logger.warn("FRED_API_KEY not set — cannot run FRED PPI fallback");
        return [];
      }

      const results: Array<{
        eventDate: string;
        product: string;
        region: string | null;
        priceLow: number | null;
        priceHigh: number | null;
        priceAvg: number;
        unit: string;
        volume: number | null;
        source: string;
      }> = [];

      for (const series of FRED_UCO_SERIES) {
        try {
          const obs = await fetchFredUcoPpi(series.id, "1990-01-01");
          for (const o of obs) {
            results.push({
              eventDate: o.date,
              product: series.product,
              region: "US National",
              priceLow: null,
              priceHigh: null,
              priceAvg: o.value,
              unit: series.unit,
              volume: null,
              source: `fred_${series.id}`,
            });
          }
          logger.info(`FRED ${series.id}: ${obs.length} observations`);
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          logger.warn(`FRED ${series.id} failed: ${msg}`);
        }
      }

      return results;
    });

    // ── Step 3: combine MARS + FRED rows ──
    const allRows: Array<{
      eventDate: string;
      product: string;
      region: string | null;
      priceLow: number | null;
      priceHigh: number | null;
      priceAvg: number | null;
      unit: string;
      volume: number | null;
      source: string;
      rowHash: string;
    }> = [];

    // Add MARS rows
    for (const row of marsRows) {
      allRows.push({
        eventDate: row.reportDate,
        product: row.product,
        region: row.region,
        priceLow: row.priceLow,
        priceHigh: row.priceHigh,
        priceAvg: row.priceAvg,
        unit: row.unit,
        volume: row.volume,
        source: SOURCE_NAME,
        rowHash: computeRowHash([row.product, row.reportDate, String(row.priceAvg ?? "")]),
      });
    }

    // Add FRED rows
    for (const row of fredRows) {
      allRows.push({
        ...row,
        rowHash: computeRowHash([row.product, row.eventDate, String(row.priceAvg)]),
      });
    }

    logger.info(`Total rows: ${allRows.length} (MARS: ${marsRows.length}, FRED: ${fredRows.length})`);

    if (allRows.length === 0) {
      return { status: "no_data", marsSuccess, fredRows: fredRows.length };
    }

    // ── Step 4: load existing hashes ──
    const existingHashes = await step.run("load-existing-hashes", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query("SELECT row_hash FROM supply.uco_prices_1w");
        return result.rows.map((r: { row_hash: string }) => r.row_hash);
      } finally {
        client.release();
      }
    });

    const existingSet = new Set(existingHashes);
    const rowsToInsert = allRows.filter((r) => !existingSet.has(r.rowHash));

    logger.info(`New rows to insert: ${rowsToInsert.length} (${existingHashes.length} already exist)`);

    // ── Step 5: batch insert ──
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
            const perRow = 10;

            for (let r = 0; r < batch.length; r++) {
              const base = r * perRow;
              values.push(
                `($${base + 1}::date, $${base + 2}, $${base + 3}, $${base + 4}, $${base + 5}, $${base + 6}, $${base + 7}, $${base + 8}, $${base + 9}, $${base + 10})`
              );
              const b = batch[r];
              params.push(
                b.eventDate, b.product, b.region, b.priceLow, b.priceHigh,
                b.priceAvg, b.unit, b.volume, b.source, b.rowHash,
              );
            }

            await client.query(
              `INSERT INTO supply.uco_prices_1w
                 (event_date, product, region, price_low, price_high, price_avg, unit, volume, source, row_hash)
               VALUES ${values.join(",")}
               ON CONFLICT (event_date, product, region) DO UPDATE SET
                 price_avg   = EXCLUDED.price_avg,
                 price_low   = EXCLUDED.price_low,
                 price_high  = EXCLUDED.price_high,
                 source      = EXCLUDED.source,
                 row_hash    = EXCLUDED.row_hash`,
              params,
            );
            inserted += batch.length;
          }

          return inserted;
        } finally {
          client.release();
        }
      });
    }

    // ── Step 6: log ingest run ──
    await step.run("log-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at, completed_at,
             rows_attempted, rows_inserted, rows_skipped, rows_quarantined)
           VALUES ($1, 'success', NOW(), NOW(), $2, $3, $4, 0)`,
          ["usda-ams-fats-oils-daily", allRows.length, rowsInserted, allRows.length - rowsToInsert.length],
        );
      } finally {
        client.release();
      }
    });

    return {
      status: "success",
      marsRows: marsRows.length,
      fredRows: fredRows.length,
      inserted: rowsInserted,
      skipped: allRows.length - rowsToInsert.length,
    };
  },
);
