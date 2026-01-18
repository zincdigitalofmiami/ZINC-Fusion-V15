import { inngest } from "./client";
import { createHash } from "crypto";
import { Pool, type PoolClient } from "pg";
import { XMLParser } from "fast-xml-parser";

const CORNELL_PUBLICATIONS_URL =
  "https://usda.library.cornell.edu/concern/publications?locale=en";

const CORNELL_BASE_URL = "https://usda.library.cornell.edu";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

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
  if (attr === "Production") return "production";
  if (attr === "Exports") return "exports";
  if (attr === "Ending Stocks") return "ending_stocks";
  if (attr === "Domestic Total") return "consumption";
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
  const matches = Array.from(html.matchAll(/href=\"([^\"]*wasde\\d{4}\\.xml)\"/gi));
  if (matches.length === 0) {
    throw new Error("Could not find any WASDE XML links on Cornell publications page");
  }

  let best: WasdeRelease | null = null;
  for (const m of matches) {
    const href = m[1];
    const idx = m.index ?? 0;
    const before = html.slice(Math.max(0, idx - 400), idx);
    const dtMatches = Array.from(before.matchAll(/datetime=\"([^\"]+)\"/gi));
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

function extractCommodityRows(
  parsed: any,
  srKey: string,
  commodity: string
): WasdeRow[] {
  const report = parsed?.Report?.[srKey]?.Report;
  if (!report) throw new Error(`Missing subreport ${srKey} in WASDE XML`);

  const matrix5 = report.matrix5;
  if (!matrix5) throw new Error(`Missing ${srKey}.Report.matrix5 in WASDE XML`);

  const regionGroups = toArray(matrix5?.m2_region_group2_Collection?.m2_region_group2);
  if (regionGroups.length === 0) throw new Error(`No region groups found for ${srKey} matrix5`);

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
      if (!cellValue) throw new Error(`Missing cell value for ${srKey} ${country} ${attributeRaw}`);

      rows.push({
        commodity,
        country,
        metric,
        value: parseFloatStrict(cellValue),
        unit: "MMT",
      });
    }
  }

  return rows;
}

async function fetchLatestWasdeRows(): Promise<{ release: WasdeRelease; rows: WasdeRow[] }> {
  const pubRes = await fetch(CORNELL_PUBLICATIONS_URL, { headers: { "User-Agent": "ZINC-Fusion/1.0" } });
  if (!pubRes.ok) throw new Error(`Cornell publications fetch failed: ${pubRes.status}`);
  const html = await pubRes.text();

  const release = findLatestWasdeRelease(html);
  const xmlRes = await fetch(release.xmlUrl, { headers: { "User-Agent": "ZINC-Fusion/1.0" } });
  if (!xmlRes.ok) throw new Error(`WASDE XML fetch failed: ${xmlRes.status}`);
  const xmlText = await xmlRes.text();

  const parser = new XMLParser({ ignoreAttributes: false });
  const parsed = parser.parse(xmlText);

  const rows: WasdeRow[] = [
    ...extractCommodityRows(parsed, "sr28", "Soybeans"),
    ...extractCommodityRows(parsed, "sr29", "Soybean Meal"),
    ...extractCommodityRows(parsed, "sr30", "Soybean Oil"),
  ];

  const expected = 3 * 5 * 4;
  if (rows.length !== expected) {
    const keySet = new Set(rows.map((r) => `${r.commodity}|${r.country}|${r.metric}`));
    throw new Error(
      `WASDE parse incomplete: expected ${expected} rows (3 commodities × 5 countries × 4 metrics), got ${rows.length} (unique keys=${keySet.size})`
    );
  }

  return { release, rows };
}

export const usdaWasdeMonthly = inngest.createFunction(
  { id: "usda-wasde-monthly", name: "USDA WASDE (Cornell XML) Bronze Ingestion", retries: 3 },
  { cron: "0 16 * * 1-5" },
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
        return await fetchLatestWasdeRows();
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

      if (existingCount === 60) {
        skipped = 60;
        await step.run("complete-skip", async () => {
          await updateIngestRun(client, runId!, "success", attempted, inserted, skipped, quarantined);
        });
        return { status: "skipped_already_ingested", runId, reportDate: release.reportDate };
      }
      if (existingCount > 0 && existingCount !== 60) {
        throw new Error(
          `Partial WASDE rows already exist for ${release.reportDate} (source=usda_wasde_cornell, count=${existingCount})`
        );
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
                 (event_date, commodity, country, metric, value, unit, source, source_url, raw_payload, ingestion_batch_id, row_hash, specialist_tags, ingested_at, knowledge_time)
               VALUES
                 ($1::date, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, NOW(), $13::timestamptz)`,
              [
                release.reportDate,
                row.commodity,
                row.country,
                row.metric,
                row.value,
                row.unit,
                "usda_wasde_cornell",
                release.xmlUrl,
                JSON.stringify({
                  source: "usda_wasde_cornell",
                  report_datetime: release.reportDateTime,
                  xml_url: release.xmlUrl,
                  commodity: row.commodity,
                  country: row.country,
                  metric: row.metric,
                  value: row.value,
                  unit: row.unit,
                  tables: {
                    Soybeans: "sr28.matrix5",
                    Soybean_Meal: "sr29.matrix5",
                    Soybean_Oil: "sr30.matrix5",
                  },
                }),
                runId,
                rowHash,
                ["crush"],
                release.reportDateTime,
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
        await updateIngestRun(client, runId!, "success", attempted, inserted, skipped, quarantined);
      });

      return { status: "success", runId, reportDate: release.reportDate, inserted };
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
