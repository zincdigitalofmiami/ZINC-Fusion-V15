import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { type PoolClient } from "pg";
import { XMLParser } from "fast-xml-parser";
import dbPool from "@/lib/db";

const CORNELL_PUBLICATIONS_URL =
  "https://usda.library.cornell.edu/concern/publications?locale=en";

const CORNELL_BASE_URL = "https://usda.library.cornell.edu";

const pool = dbPool;

// Minimum acceptable rows (allow partial data rather than failing completely)
// Full expected: 3 commodities × 5 countries × 4 metrics = 60
// Minimum: at least get core soy complex data (3 commodities × 2 countries × 2 metrics = 12)
const MIN_ACCEPTABLE_ROWS = 12;
const IDEAL_ROW_COUNT = 60;

function computeRowHash(parts: string[]): string {
  return createHash("sha256").update(parts.join("|")).digest("hex");
}

function normalizeWhitespace(value: string): string {
  return value.replace(/\r/g, " ").replace(/\n/g, " ").replace(/\s+/g, " ").trim();
}

function parseIsoDate(isoDateTime: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})T/.exec(isoDateTime);
  if (!match) throw new Error(`Unexpected datetime format: ${JSON.stringify(isoDateTime)}`);
  return match[1];
}

function parseFloatStrict(value: string): number {
  const trimmed = value.trim();
  const num = Number(trimmed);
  if (!Number.isFinite(num)) throw new Error(`Non-numeric WASDE value: ${JSON.stringify(value)}`);
  return num;
}

function mapCountry(rawRegion: string): string | null {
  const region = normalizeWhitespace(rawRegion).replace(/^\s+/, "");
  if (region.startsWith("World Less China")) return null;
  if (region.startsWith("World")) return "World";
  if (region === "United States") return "United States";
  if (region === "Argentina") return "Argentina";
  if (region === "Brazil") return "Brazil";
  if (region === "China") return "China";
  return null;
}

function mapMetric(rawAttribute: string): string | null {
  const attr = normalizeWhitespace(rawAttribute);
  // Primary metrics
  if (attr === "Production") return "production";
  if (attr === "Exports") return "exports";
  if (attr === "Ending Stocks") return "ending_stocks";
  if (attr === "Domestic Total") return "consumption";
  // Alternative metric names USDA sometimes uses
  if (attr === "Total Production") return "production";
  if (attr === "Total Exports") return "exports";
  if (attr === "Stocks") return "ending_stocks";
  if (attr === "Domestic Consumption") return "consumption";
  if (attr === "Domestic Use") return "consumption";
  if (attr === "Crushings") return "consumption";
  return null;
}

async function createIngestRun(client: PoolClient, jobName: string): Promise<string> {
  const result = await client.query(
    `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
    [jobName]
  );
  return result.rows[0].id;
}

async function updateIngestRun(
  client: PoolClient,
  runId: string,
  status: string,
  attempted: number,
  inserted: number,
  skipped: number,
  quarantined: number,
  errorMessage?: string
): Promise<void> {
  await client.query(
    `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
     rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6, error_message=$7 WHERE id=$1`,
    [runId, status, attempted, inserted, skipped, quarantined, errorMessage]
  );
}

type WasdeRelease = {
  reportDateTime: string;
  reportDate: string;
  xmlUrl: string;
};

function findLatestWasdeRelease(html: string): WasdeRelease {
  const matches = Array.from(html.matchAll(/href="([^"]*wasde\d{4}\.xml)"/gi));
  if (matches.length === 0) {
    throw new Error("Could not find any WASDE XML links on Cornell publications page");
  }

  let best: WasdeRelease | null = null;
  for (const m of matches) {
    const href = m[1];
    const idx = m.index ?? 0;
    const before = html.slice(Math.max(0, idx - 400), idx);
    const dtMatches = Array.from(before.matchAll(/datetime="([^"]+)"/gi));
    const dt = dtMatches.length ? dtMatches[dtMatches.length - 1][1] : null;
    if (!dt) continue;

    const reportDate = parseIsoDate(dt);
    const xmlUrl = href.startsWith("http") ? href : `${CORNELL_BASE_URL}${href}`;

    if (!best || dt > best.reportDateTime) {
      best = { reportDateTime: dt, reportDate, xmlUrl };
    }
  }

  if (!best) throw new Error("Found WASDE XML links but could not parse any report datetime");
  return best;
}

type WasdeRow = {
  commodity: string;
  country: string;
  metric: string;
  value: number;
  unit: string;
};

function toArray<T>(value: T | T[] | undefined): T[] {
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

interface WasdeXmlParsed {
  Report?: Record<string, { Report?: WasdeSubReport }>;
}

interface WasdeSubReport {
  matrix5?: {
    m2_region_group2_Collection?: {
      m2_region_group2?: WasdeRegionGroup | WasdeRegionGroup[];
    };
  };
}

interface WasdeRegionGroup {
  "@_region5"?: string;
  m2_attribute_group2_Collection?: {
    m2_attribute_group2?: WasdeAttributeGroup | WasdeAttributeGroup[];
  };
}

interface WasdeAttributeGroup {
  "@_attribute5"?: string;
  Cell?: {
    "@_cell_value5"?: string;
  };
}

function extractCommodityRows(
  parsed: WasdeXmlParsed,
  srKey: string,
  commodity: string,
  logger?: { warn: (msg: string) => void }
): WasdeRow[] {
  const report = parsed?.Report?.[srKey]?.Report;
  if (!report) {
    logger?.warn(`Missing subreport ${srKey} in WASDE XML - skipping ${commodity}`);
    return [];
  }

  const matrix5 = report.matrix5;
  if (!matrix5) {
    logger?.warn(`Missing ${srKey}.Report.matrix5 in WASDE XML - skipping ${commodity}`);
    return [];
  }

  const regionGroups = toArray(matrix5?.m2_region_group2_Collection?.m2_region_group2);
  if (regionGroups.length === 0) {
    logger?.warn(`No region groups found for ${srKey} matrix5 - skipping ${commodity}`);
    return [];
  }

  const rows: WasdeRow[] = [];
  for (const rg of regionGroups) {
    const regionRaw: string | undefined = rg?.["@_region5"];
    if (!regionRaw) continue;
    const country = mapCountry(regionRaw);
    if (!country) continue;

    const attributeGroups = toArray(rg?.m2_attribute_group2_Collection?.m2_attribute_group2);
    for (const ag of attributeGroups) {
      const attributeRaw: string | undefined = ag?.["@_attribute5"];
      if (!attributeRaw) continue;
      const metric = mapMetric(attributeRaw);
      if (!metric) continue;

      const cellValue: string | undefined = ag?.Cell?.["@_cell_value5"];
      if (!cellValue) {
        logger?.warn(`Missing cell value for ${srKey} ${country} ${attributeRaw} - skipping`);
        continue;
      }

      try {
        rows.push({
          commodity,
          country,
          metric,
          value: parseFloatStrict(cellValue),
          unit: "MMT",
        });
      } catch {
        logger?.warn(`Failed to parse value for ${commodity}/${country}/${metric}: ${cellValue}`);
      }
    }
  }

  return rows;
}

async function fetchLatestWasdeRows(logger?: { info: (msg: string) => void; warn: (msg: string) => void }): Promise<{ release: WasdeRelease; rows: WasdeRow[] }> {
  const fetchWithTimeout = async (url: string, timeoutMs: number): Promise<Response> => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, {
        headers: { "User-Agent": "ZINC-Fusion/1.0" },
        signal: controller.signal,
      });
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        throw new Error(`WASDE fetch timed out after ${timeoutMs}ms: ${url}`);
      }
      throw err;
    } finally {
      clearTimeout(timeout);
    }
  };

  const pubRes = await fetchWithTimeout(CORNELL_PUBLICATIONS_URL, 20000);
  if (!pubRes.ok) throw new Error(`Cornell publications fetch failed: ${pubRes.status}`);
  const html = await pubRes.text();

  const release = findLatestWasdeRelease(html);
  const xmlRes = await fetchWithTimeout(release.xmlUrl, 20000);
  if (!xmlRes.ok) throw new Error(`WASDE XML fetch failed: ${xmlRes.status}`);
  const xmlText = await xmlRes.text();

  const parser = new XMLParser({ ignoreAttributes: false });
  const parsed = parser.parse(xmlText);

  // Extract rows from each commodity section, allowing partial failures
  const rows: WasdeRow[] = [
    ...extractCommodityRows(parsed, "sr28", "Soybeans", logger),
    ...extractCommodityRows(parsed, "sr29", "Soybean Meal", logger),
    ...extractCommodityRows(parsed, "sr30", "Soybean Oil", logger),
  ];

  // Log extraction summary
  const byCommodity = rows.reduce((acc, r) => {
    acc[r.commodity] = (acc[r.commodity] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);
  logger?.info(`WASDE extraction: ${rows.length} rows - ${JSON.stringify(byCommodity)}`);

  // Validate we have minimum acceptable data
  if (rows.length < MIN_ACCEPTABLE_ROWS) {
    const keySet = new Set(rows.map((r) => `${r.commodity}|${r.country}|${r.metric}`));
    throw new Error(
      `WASDE parse failed: got ${rows.length} rows (minimum ${MIN_ACCEPTABLE_ROWS} required). ` +
      `Expected ~${IDEAL_ROW_COUNT} rows (3 commodities × 5 countries × 4 metrics). ` +
      `Unique keys: ${keySet.size}. This may indicate USDA changed their XML format.`
    );
  }

  // Warn if we got partial data but continue
  if (rows.length < IDEAL_ROW_COUNT) {
    logger?.warn(
      `WASDE partial data: got ${rows.length}/${IDEAL_ROW_COUNT} expected rows. ` +
      `Proceeding with available data.`
    );
  }

  return { release, rows };
}

export const usdaWasdeMonthly = inngest.createFunction(
  { id: "usda-wasde-monthly", name: "USDA WASDE (Cornell XML) Data Ingestion", retries: 3, concurrency: [DB_CONCURRENCY, { limit: 1 }] },
  { cron: "22 */8 * * *" }, // Every 8 hours at :22 UTC to catch monthly WASDE releases
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;
    let attempted = 0;
    let inserted = 0;
    let skipped = 0;
    let quarantined = 0;

    try {
      await step.run("assert-tables", async () => {
        await client.query("SELECT 1 FROM ops.ingest_run LIMIT 1");
        await client.query("SELECT 1 FROM supply.usda_wasde_1m LIMIT 1");
      });

      runId = await step.run("create-ingest-run", async () => {
        return await createIngestRun(client, "usda-wasde-monthly");
      });

      const { release, rows } = await step.run("fetch-wasde", async () => {
        return await fetchLatestWasdeRows(logger);
      });

      logger.info(`Latest WASDE release: ${release.reportDateTime} (${release.xmlUrl})`);

      const existingCount = await step.run("check-existing", async () => {
        const r = await client.query(
          `SELECT COUNT(*)::int AS n
           FROM supply.usda_wasde_1m
           WHERE event_date = $1::date AND source = 'usda_wasde_cornell'`,
          [release.reportDate]
        );
        return Number(r.rows[0].n);
      });

      // Skip if we already have data for this report (any amount indicates already processed)
      if (existingCount >= rows.length) {
        skipped = existingCount;
        await step.run("complete-skip", async () => {
          await updateIngestRun(client, runId!, "success", attempted, inserted, skipped, quarantined);
        });
        return { status: "skipped_already_ingested", runId, reportDate: release.reportDate, existingCount };
      }

      // If partial data exists, delete and re-ingest to ensure consistency
      if (existingCount > 0) {
        await step.run("delete-partial", async () => {
          await client.query(
            `DELETE FROM supply.usda_wasde_1m
             WHERE event_date = $1::date AND source = 'usda_wasde_cornell'`,
            [release.reportDate]
          );
          logger.warn(`Deleted ${existingCount} partial rows for ${release.reportDate} before re-ingesting`);
        });
      }

      await step.run("insert-rows", async () => {
        await client.query("BEGIN");
        try {
          for (const row of rows) {
            attempted++;
            const rowHash = computeRowHash([
              "usda_wasde_cornell",
              release.reportDate,
              row.commodity,
              row.country,
              row.metric,
              String(row.value),
              release.xmlUrl,
            ]);

            await client.query(
              `INSERT INTO supply.usda_wasde_1m
                 (event_date, commodity, country, metric, value, unit, source, row_hash)
               VALUES
                 ($1::date, $2, $3, $4, $5, $6, $7, $8)
               ON CONFLICT (event_date, commodity, country, metric) DO UPDATE SET
                 value = EXCLUDED.value,
                 unit = EXCLUDED.unit,
                 source = EXCLUDED.source,
                 row_hash = EXCLUDED.row_hash,
                 ingested_at = NOW()`,
              [
                release.reportDate,
                row.commodity,
                row.country,
                row.metric,
                row.value,
                row.unit,
                "usda_wasde_cornell",
                rowHash,
              ]
            );
            inserted++;
          }
          await client.query("COMMIT");
        } catch (e) {
          await client.query("ROLLBACK");
          throw e;
        }
      });

      await step.run("complete", async () => {
        const status = inserted === IDEAL_ROW_COUNT ? "success" : "partial_success";
        await updateIngestRun(client, runId!, status, attempted, inserted, skipped, quarantined);
      });

      return {
        status: inserted === IDEAL_ROW_COUNT ? "success" : "partial_success",
        runId,
        reportDate: release.reportDate,
        inserted,
        expected: IDEAL_ROW_COUNT,
      };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      if (runId) {
        await updateIngestRun(client, runId, "failed", attempted, inserted, skipped, quarantined, msg);
      }
      throw error;
    } finally {
      client.release();
    }
  }
);
