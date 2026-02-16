/**
 * USDA FAS Export Sales (Weekly) Data Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Append-only inserts (no upserts)
 *
 * Source: https://apps.fas.usda.gov/export-sales/complete.htm
 * Inserts into: supply.usda_exports_1w
 *
 * Notes:
 * - Data in the report is labeled "1000 METRIC TONS" → stored as metric tons (× 1000).
 * - No schema creation, no synthetic values; insert-only with existence checks.
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.1.0
 * @date 2026-02-16
 */

import { createHash } from "crypto";
import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

const SOURCE_URL = "https://apps.fas.usda.gov/export-sales/complete.htm";

const MONTHS: Record<string, string> = {
  JANUARY: "01",
  FEBRUARY: "02",
  MARCH: "03",
  APRIL: "04",
  MAY: "05",
  JUNE: "06",
  JULY: "07",
  AUGUST: "08",
  SEPTEMBER: "09",
  OCTOBER: "10",
  NOVEMBER: "11",
  DECEMBER: "12",
};

function computeRowHash(
  eventDate: string,
  commodity: string,
  destinationCountry: string,
  netSalesMt: number | null,
  exportsMt: number | null,
  outstandingSalesMt: number | null
): string {
  return createHash("sha256")
    .update(
      `${eventDate}|${commodity}|${destinationCountry}|${netSalesMt ?? ""}|${exportsMt ?? ""}|${
        outstandingSalesMt ?? ""
      }`
    )
    .digest("hex");
}

// PoolClient helper functions removed — SQL inlined inside step.run() closures
// to prevent stale connections across Inngest durable execution boundaries.

function parseAsOfDate(preText: string): string {
  // Example: "U. S. EXPORT SALES AS OF JANUARY 01, 2026"
  const m = preText.match(
    /EXPORT SALES AS OF\s+([A-Z]+)\s+(\d{1,2}),\s*(\d{4})/i
  );
  if (!m) {
    throw new Error("Failed to parse report AS OF date from complete.htm");
  }
  const monthName = m[1].toUpperCase();
  const month = MONTHS[monthName];
  if (!month) throw new Error(`Unknown month name in report AS OF date: ${monthName}`);
  const day = String(m[2]).padStart(2, "0");
  const year = m[3];
  return `${year}-${month}-${day}`;
}

function inferWeekEnding(reportDateYmd: string, mmdd: string): string {
  const [y, m, d] = reportDateYmd.split("-").map((x) => Number(x));
  const reportMonthDay = m * 100 + d;
  const [mm, dd] = mmdd.split("/").map((x) => Number(x));
  const weekMonthDay = mm * 100 + dd;
  const year = weekMonthDay > reportMonthDay ? y - 1 : y;
  return `${year}-${String(mm).padStart(2, "0")}-${String(dd).padStart(2, "0")}`;
}

function toNumber(token: string): number | null {
  const t = token.trim();
  if (t === "-" || t === "*" || t === "") return null;
  // Remove footnote markers like "1467.8 5/"
  const cleaned = t.replace(/\s*\d+\/$/, "").replace(/,/g, "");
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

function multiplyKmtToMt(v: number | null): number | null {
  if (v === null) return null;
  return v * 1000;
}

function normalizeDestination(raw: string): string | null {
  const s = raw.trim().replace(/\s+/g, " ");
  const u = s.toUpperCase();
  if (u.startsWith("EUROPEAN UNION")) return "European Union";
  if (u === "CHINA") return "China";
  if (u === "JAPAN") return "Japan";
  if (u === "MEXICO") return "Mexico";
  if (u === "INDNSIA" || u === "INDONESIA") return "Indonesia";
  if (u.startsWith("TOTAL KNOWN & UNKNOWN")) return "TOTAL";
  if (u.startsWith("TOTAL UNKNOWN")) return "Unknown";
  if (u === "TOTAL") return "TOTAL";
  if (u === "UNKNOWN") return "Unknown";
  return null;
}

type SummaryRow = {
  commodity: "Soybeans" | "Soybean Oil" | "Soybean Meal";
  weekEnding: string; // YYYY-MM-DD
  netSalesKmt: number | null;
  exportsKmt: number | null;
  outstandingKmt: number | null;
};

function parseSummaryRows(preLines: string[], reportDateYmd: string): SummaryRow[] {
  const rows: SummaryRow[] = [];

  for (let i = 0; i < preLines.length; i++) {
    const line = preLines[i];
    const upper = line.toUpperCase();
    if (!line.includes(":")) continue;

    let commodity: SummaryRow["commodity"] | null = null;
    if (upper.startsWith("SOYBEANS")) commodity = "Soybeans";
    if (upper.startsWith("SOYBEAN OIL")) commodity = "Soybean Oil";
    if (upper.startsWith("SOYBEAN CAKE") || upper.startsWith("MEAL")) commodity = "Soybean Meal";
    if (!commodity) continue;

    // Example line:
    // SOYBEANS       : 01/01      1012.5 ... 1112.6   12229.0
    const m = line.match(/:\s*(\d{2}\/\d{2})\s+(.+)$/);
    if (!m) continue;

    const weekEnding = inferWeekEnding(reportDateYmd, m[1]);
    const tokens = m[2].trim().split(/\s+/);
    // tokens correspond to: new_sales, purchases, cancellations, exports, outstanding
    if (tokens.length < 5) continue;
    const newSales = toNumber(tokens[0]);
    const exports = toNumber(tokens[3]);
    const outstanding = toNumber(tokens[4]);

    rows.push({
      commodity,
      weekEnding,
      netSalesKmt: newSales,
      exportsKmt: exports,
      outstandingKmt: outstanding,
    });
  }

  return rows;
}

type DestinationRow = {
  commodity: "Soybeans" | "Soybean Oil" | "Soybean Meal";
  reportDate: string; // YYYY-MM-DD (as-of date)
  destinationCountry: string;
  outstandingSalesKmt: number | null;
  accumulatedExportsKmt: number | null;
};

function parseDestinationSection(
  preLines: string[],
  reportDateYmd: string,
  headerMatch: RegExp,
  commodity: DestinationRow["commodity"]
): DestinationRow[] {
  const out: DestinationRow[] = [];
  const startIdx = preLines.findIndex((l) => headerMatch.test(l.toUpperCase()));
  if (startIdx === -1) return out;

  for (let i = startIdx; i < preLines.length; i++) {
    const line = preLines[i];
    if (i !== startIdx && /MARKETING YEAR/.test(line.toUpperCase()) && /SOYBEAN/.test(line.toUpperCase())) {
      // Next commodity section.
      break;
    }

    const m = line.match(/^\s*([^:]{3,})\s*:\s*(.+)$/);
    if (!m) continue;

    const destination = normalizeDestination(m[1]);
    if (!destination) continue;

    const tokens = m[2].trim().split(/\s+/);
    // Expect at least 4 numeric cols: out_this_week, out_yr_ago, exp_this_week, exp_yr_ago, ...
    if (tokens.length < 4) continue;

    const outstandingThisWeek = toNumber(tokens[0]);
    const exportsThisWeek = toNumber(tokens[2]);

    out.push({
      commodity,
      reportDate: reportDateYmd,
      destinationCountry: destination,
      outstandingSalesKmt: outstandingThisWeek,
      accumulatedExportsKmt: exportsThisWeek,
    });
  }

  return out;
}

export const usdaExportSalesWeekly = inngest.createFunction(
  { id: "usda-export-sales-weekly", name: "USDA Export Sales (Weekly)", retries: 3, concurrency: [DB_CONCURRENCY] },
  { cron: "0 21 * * 4" }, // Thursdays 21:00 UTC
  async ({ step, logger }) => {
    if (!process.env.DATABASE_URL) throw new Error("DATABASE_URL not configured");

    // ── Step 1: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["usda-export-sales-weekly"]
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    logger.info(`Started ingest run: ${runId}`);

    // ── Step 2: fetch HTML from USDA FAS ──
    const html = await step.run("fetch", async () => {
      const res = await fetch(SOURCE_URL, { headers: { "User-Agent": "ZINC-Fusion/1.0" } });
      if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);
      return await res.text();
    });

    // ── Parse (pure computation, no DB needed) ──
    const preMatch = html.match(/<pre>([\s\S]*?)<\/pre>/i);
    if (!preMatch) throw new Error("Failed to extract <pre> content from complete.htm");
    const preText = preMatch[1];
    const reportDateYmd = parseAsOfDate(preText);
    const preLines = preText.split(/\r?\n/);
    logger.info(`Report AS OF: ${reportDateYmd}`);

    // Parse all rows (pure computation)
    const summaryRows = parseSummaryRows(preLines, reportDateYmd).filter((r) => r.weekEnding === reportDateYmd);
    const soyRows = parseDestinationSection(preLines, reportDateYmd, /^SOYBEANS\s+MARKETING YEAR/, "Soybeans");
    const mealRows = parseDestinationSection(preLines, reportDateYmd, /^SOYBEAN CAKE AND MEAL\s+MARKETING YEAR/, "Soybean Meal");
    const oilRows = parseDestinationSection(preLines, reportDateYmd, /^SOYBEAN OIL\s+MARKETING YEAR/, "Soybean Oil");

    // ── Step 3: insert all rows (one connection for the batch) ──
    const batchResult = await step.run("insert-all-rows", async () => {
      let attempted = 0;
      let inserted = 0;
      let skipped = 0;

      const client = await pool.connect();
      try {
        // 1) Totals from the weekly transaction summary
        for (const r of summaryRows) {
          attempted++;
          const destinationCountry = "TOTAL";

          const exists = await client.query(
            `SELECT 1 FROM supply.usda_exports_1w
             WHERE event_date=$1::date AND commodity=$2 AND COALESCE(destination_country,'')=COALESCE($3,'')
             LIMIT 1`,
            [r.weekEnding, r.commodity, destinationCountry]
          );
          if (exists.rows.length > 0) {
            skipped++;
            continue;
          }

          const netSalesMt = multiplyKmtToMt(r.netSalesKmt);
          const exportsMt = multiplyKmtToMt(r.exportsKmt);
          const outstandingMt = multiplyKmtToMt(r.outstandingKmt);
          const rowHash = computeRowHash(r.weekEnding, r.commodity, destinationCountry, netSalesMt, exportsMt, outstandingMt);

          await client.query(
            `INSERT INTO supply.usda_exports_1w
              (event_date, commodity, destination_country, net_sales_mt, exports_mt, outstanding_sales_mt,
               source, row_hash)
             VALUES ($1::date,$2,$3,$4,$5,$6,$7,$8)`,
            [r.weekEnding, r.commodity, destinationCountry, netSalesMt, exportsMt, outstandingMt, "usda_fas_export_sales", rowHash]
          );
          inserted++;
        }

        // 2) Destination breakdown
        for (const row of [...soyRows, ...mealRows, ...oilRows]) {
          attempted++;

          const exists = await client.query(
            `SELECT 1 FROM supply.usda_exports_1w
             WHERE event_date=$1::date AND commodity=$2 AND COALESCE(destination_country,'')=COALESCE($3,'')
             LIMIT 1`,
            [row.reportDate, row.commodity, row.destinationCountry]
          );
          if (exists.rows.length > 0) {
            skipped++;
            continue;
          }

          const netSalesMt = null;
          const exportsMt = multiplyKmtToMt(row.accumulatedExportsKmt);
          const outstandingMt = multiplyKmtToMt(row.outstandingSalesKmt);
          const rowHash = computeRowHash(row.reportDate, row.commodity, row.destinationCountry, netSalesMt, exportsMt, outstandingMt);

          await client.query(
            `INSERT INTO supply.usda_exports_1w
              (event_date, commodity, destination_country, net_sales_mt, exports_mt, outstanding_sales_mt,
               source, row_hash)
             VALUES ($1::date,$2,$3,$4,$5,$6,$7,$8)`,
            [row.reportDate, row.commodity, row.destinationCountry, netSalesMt, exportsMt, outstandingMt, "usda_fas_export_sales", rowHash]
          );
          inserted++;
        }
      } finally {
        client.release();
      }

      return { attempted, inserted, skipped };
    });

    // ── Step 4: finalize ingest run ──
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", batchResult.attempted, batchResult.inserted, batchResult.skipped, 0]
        );
      } finally {
        client.release();
      }
    });

    logger.info(`Completed: ${batchResult.inserted} inserted, ${batchResult.skipped} skipped`);

    return {
      status: "success",
      runId,
      attempted: batchResult.attempted,
      inserted: batchResult.inserted,
      skipped: batchResult.skipped,
      quarantined: 0,
      reportDate: reportDateYmd,
    };
  }
);
