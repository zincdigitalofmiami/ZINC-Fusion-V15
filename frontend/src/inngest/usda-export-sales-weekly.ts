/**
 * USDA FAS Export Sales (Weekly) Data Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Upserts on (event_date, commodity, destination_country)
 *
 * Sources:
 *   - https://apps.fas.usda.gov/export-sales/soybeans.htm  (Soybeans)
 *   - https://apps.fas.usda.gov/export-sales/soyoil.htm    (Soybean Oil — USDA uses "soyoil" slug)
 *   - https://apps.fas.usda.gov/export-sales/soymeal.htm   (Soybean Meal)
 *   - https://apps.fas.usda.gov/export-sales/complete.htm   (Weekly transaction summary)
 *
 * Inserts into: supply.usda_exports_1w
 *
 * Country-level data captures ALL destinations with 6 numeric columns:
 *   1. Outstanding Sales THIS WEEK (current MY)
 *   2. Outstanding Sales YR AGO
 *   3. Accumulated Exports THIS WEEK (current MY)
 *   4. Accumulated Exports YR AGO
 *   5. Outstanding Sales NEXT MY (second year)
 *   6. Outstanding Sales NEXT MY (third year)
 *
 * @version 2.0.0
 * @date 2026-02-24
 */

import { createHash } from "crypto";
import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

// ---------------------------------------------------------------------------
//  Source URLs
// ---------------------------------------------------------------------------
const COMMODITY_PAGES: Array<{
  url: string;
  commodity: "Soybeans" | "Soybean Oil" | "Soybean Meal";
  myStart: string; // Marketing year start MM/DD
}> = [
  {
    url: "https://apps.fas.usda.gov/export-sales/soybeans.htm",
    commodity: "Soybeans",
    myStart: "09/01",
  },
  {
    url: "https://apps.fas.usda.gov/export-sales/soyoil.htm",
    commodity: "Soybean Oil",
    myStart: "10/01",
  },
  {
    url: "https://apps.fas.usda.gov/export-sales/soymeal.htm",
    commodity: "Soybean Meal",
    myStart: "10/01",
  },
];

const COMPLETE_URL = "https://apps.fas.usda.gov/export-sales/complete.htm";

// ---------------------------------------------------------------------------
//  Country abbreviation lookup — USDA FAS uses truncated names in the report
// ---------------------------------------------------------------------------
const COUNTRY_ABBREV: Record<string, string> = {
  "INDNSIA": "Indonesia",
  "KOR REP": "South Korea",
  "S ARAB": "Saudi Arabia",
  "U AR EM": "UAE",
  "COLOMB": "Colombia",
  "DOM REP": "Dominican Republic",
  "GUATMAL": "Guatemala",
  "HONDURA": "Honduras",
  "NICARAG": "Nicaragua",
  "SALVADR": "El Salvador",
  "TRINID": "Trinidad and Tobago",
  "BARBADO": "Barbados",
  "C RICA": "Costa Rica",
  "VENEZ": "Venezuela",
  "NETHLDS": "Netherlands",
  "PORTUGL": "Portugal",
  "SWITZLD": "Switzerland",
  "REP SAF": "South Africa",
  "MALAYSA": "Malaysia",
  "PAKISTN": "Pakistan",
  "BANGLADH": "Bangladesh",
  "SINGAPR": "Singapore",
  "THAILND": "Thailand",
  "PHIL": "Philippines",
  "LW WW I": "Low Value Shipments",
  "U KING": "United Kingdom",
  "HG KONG": "Hong Kong",
  "N ZEALD": "New Zealand",
  "SRI LKA": "Sri Lanka",
  "AUSTRAL": "Australia",
  "PARAGUA": "Paraguay",
  "ARGENT": "Argentina",
  "ECUAD": "Ecuador",
  "MOROC": "Morocco",
  "TUNISIA": "Tunisia",
  "SENEGAL": "Senegal",
  "NIGERIA": "Nigeria",
  "URUGUY": "Uruguay",
  "GUATEML": "Guatemala",
  "CAMROON": "Cameroon",
  "MOZAMBQ": "Mozambique",
  "TANZANA": "Tanzania",
  "IVORY C": "Ivory Coast",
  "PERU": "Peru",
  "N ZEAL": "New Zealand",
  "S LANKA": "Sri Lanka",
  "OPAC IS": "Pacific Islands",
  "F W IND": "French West Indies",
  "BELGIUM": "Belgium",
  "DENMARK": "Denmark",
  "IRELAND": "Ireland",
  "POLAND": "Poland",
  "ROMANIA": "Romania",
  "SURINAM": "Suriname",
  "GUYANA": "Guyana",
  "LIBYA": "Libya",
  "BURMA": "Burma",
};

// Region headers that appear as parent rows with subtotals
const REGION_NAMES = new Set([
  "EUROPEAN UNION - 27",
  "OTHER EUROPE",
  "OTHER ASIA AND OCEANIA",
  "AFRICA",
  "WESTERN HEMISPHERE",
]);

// ---------------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------------
const MONTHS: Record<string, string> = {
  JANUARY: "01", FEBRUARY: "02", MARCH: "03", APRIL: "04",
  MAY: "05", JUNE: "06", JULY: "07", AUGUST: "08",
  SEPTEMBER: "09", OCTOBER: "10", NOVEMBER: "11", DECEMBER: "12",
};

function computeRowHash(
  eventDate: string,
  commodity: string,
  dest: string,
  outstanding: number | null,
  exports: number | null,
): string {
  return createHash("sha256")
    .update(`${eventDate}|${commodity}|${dest}|${outstanding ?? ""}|${exports ?? ""}`)
    .digest("hex");
}

function parseAsOfDate(preText: string): string {
  const m = preText.match(/AS OF\s+([A-Z]+)\s+(\d{1,2})\s*,?\s*(\d{4})/i);
  if (!m) throw new Error("Failed to parse report AS OF date");
  const month = MONTHS[m[1].toUpperCase()];
  if (!month) throw new Error(`Unknown month: ${m[1]}`);
  return `${m[3]}-${month}-${String(m[2]).padStart(2, "0")}`;
}

function parseMarketingYear(preText: string): string {
  const m = preText.match(/MARKETING YEAR\s+(\d{2}\/\d{2})\s*-\s*(\d{2}\/\d{2})/i);
  return m ? `${m[1]}-${m[2]}` : "";
}

function toNumber(token: string): number | null {
  const t = token.trim();
  if (t === "-" || t === "*" || t === "") return null;
  const cleaned = t.replace(/\s*\d+\/$/, "").replace(/,/g, "");
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

function kmt(v: number | null): number | null {
  return v === null ? null : v * 1000;
}

/**
 * Resolve a raw USDA destination name to a normalized country name.
 * Returns the country name for ALL entries — never null (except blanks).
 */
function resolveCountry(raw: string): string | null {
  const s = raw.trim().replace(/\s+/g, " ");
  if (!s) return null;
  const u = s.toUpperCase();

  // Total / unknown rows
  if (u.startsWith("TOTAL KNOWN & UNKNOWN") || u === "GRAND TOTAL") return "TOTAL";
  if (u.startsWith("TOTAL KNOWN")) return "TOTAL KNOWN";
  if (u.startsWith("TOTAL UNKNOWN")) return "Unknown";
  if (u === "TOTAL") return "TOTAL";
  if (u.startsWith("EXPORTS FOR OWN")) return null; // skip metadata rows
  if (u.startsWith("OPTIONAL ORIGIN")) return null;

  // Known regions
  for (const region of REGION_NAMES) {
    if (u.startsWith(region)) return titleCase(region);
  }

  // Abbreviation lookup (case-insensitive)
  for (const [abbrev, full] of Object.entries(COUNTRY_ABBREV)) {
    if (u === abbrev.toUpperCase()) return full;
  }

  // Common full names
  if (u === "CHINA") return "China";
  if (u === "JAPAN") return "Japan";
  if (u === "INDIA") return "India";
  if (u === "MEXICO") return "Mexico";
  if (u === "TAIWAN") return "Taiwan";
  if (u === "CANADA") return "Canada";
  if (u === "EGYPT") return "Egypt";
  if (u === "ALGERIA") return "Algeria";
  if (u === "MOROCCO") return "Morocco";
  if (u === "HAITI") return "Haiti";
  if (u === "JAMAICA") return "Jamaica";
  if (u === "PANAMA") return "Panama";
  if (u === "IRAQ") return "Iraq";
  if (u === "ISRAEL") return "Israel";
  if (u === "FRANCE") return "France";
  if (u === "GERMANY") return "Germany";
  if (u === "GREECE") return "Greece";
  if (u === "ITALY") return "Italy";
  if (u === "SPAIN") return "Spain";
  if (u === "TURKEY") return "Turkey";
  if (u === "BAHRAIN") return "Bahrain";
  if (u === "JORDAN") return "Jordan";
  if (u === "KUWAIT") return "Kuwait";
  if (u === "LEBANON") return "Lebanon";
  if (u === "OMAN") return "Oman";
  if (u === "QATAR") return "Qatar";
  if (u === "NEPAL") return "Nepal";
  if (u === "LAOS") return "Laos";
  if (u === "VIETNAM") return "Vietnam";
  if (u === "CAMBODIA") return "Cambodia";

  // Fallback: title-case whatever we got — NEVER drop a country
  return titleCase(s);
}

function titleCase(s: string): string {
  return s
    .toLowerCase()
    .split(" ")
    .map((w) => (w.length > 2 ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ")
    .replace(/^(.)/, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
//  Parser for commodity-specific reports (soybeans, soybean oil, soybean meal)
// ---------------------------------------------------------------------------
interface CountryRow {
  commodity: "Soybeans" | "Soybean Oil" | "Soybean Meal";
  reportDate: string;
  marketingYear: string;
  destinationCountry: string;
  outstandingSalesKmt: number | null;
  outstandingSalesYrAgoKmt: number | null;
  accumulatedExportsKmt: number | null;
  accumulatedExportsYrAgoKmt: number | null;
  outstandingNextMyKmt: number | null;
  isRegion: boolean;
  parentRegion: string | null;
}

function parseCommodityPage(
  html: string,
  commodity: CountryRow["commodity"],
): CountryRow[] {
  // USDA commodity pages omit </pre> — fall back to </html> as boundary
  const preMatch = html.match(/<pre>([\s\S]*?)(?:<\/pre>|<\/html>)/i);
  if (!preMatch) return [];
  const preText = preMatch[1];
  const reportDate = parseAsOfDate(preText);
  const marketingYear = parseMarketingYear(preText);
  const lines = preText.split(/\r?\n/);

  const rows: CountryRow[] = [];
  let currentRegion: string | null = null;
  let pastHeader = false;

  for (const line of lines) {
    // Skip until we see the DESTINATION header
    if (!pastHeader) {
      if (/DESTINATION/i.test(line)) pastHeader = true;
      continue;
    }

    // Stop at the dashes before totals
    if (/^-{20,}/.test(line.trim()) && rows.length > 0) {
      // Parse total rows after the separator
    }

    // Skip blank/separator lines
    if (!line.includes(":")) continue;

    const m = line.match(/^(\s*)([^:]+):\s*(.*)$/);
    if (!m) continue;

    const indent = m[1].length;
    const rawDest = m[2].trim();
    const dataStr = m[3].trim();

    if (!rawDest || !dataStr) continue;

    const dest = resolveCountry(rawDest);
    if (!dest) continue;

    // Parse the 6 numeric columns
    const tokens = dataStr.split(/\s+/);
    if (tokens.length < 4) continue;

    const outstandingThisWeek = toNumber(tokens[0] || "");
    const outstandingYrAgo = toNumber(tokens[1] || "");
    const exportsThisWeek = toNumber(tokens[2] || "");
    const exportsYrAgo = toNumber(tokens[3] || "");
    const outstandingNextMy = toNumber(tokens[4] || "");
    // tokens[5] = third year (rarely non-zero, rolled into next MY)

    // Determine hierarchy: region header, indented sub-country, or standalone top-level
    const isRegion = indent <= 1 && REGION_NAMES.has(rawDest.toUpperCase().trim());
    const isIndented = indent > 1; // sub-country under a region
    if (isRegion) {
      currentRegion = dest;
    } else if (!isIndented) {
      // Top-level non-region entry (e.g., Japan, China, Taiwan, totals)
      // — clear region context so it's not assigned as a child
      currentRegion = null;
    }

    rows.push({
      commodity,
      reportDate,
      marketingYear,
      destinationCountry: dest,
      outstandingSalesKmt: outstandingThisWeek,
      outstandingSalesYrAgoKmt: outstandingYrAgo,
      accumulatedExportsKmt: exportsThisWeek,
      accumulatedExportsYrAgoKmt: exportsYrAgo,
      outstandingNextMyKmt: outstandingNextMy,
      isRegion,
      parentRegion: isIndented ? currentRegion : null,
    });
  }

  return rows;
}

// ---------------------------------------------------------------------------
//  Parser for complete.htm (weekly transaction summary — totals only)
// ---------------------------------------------------------------------------
interface SummaryRow {
  commodity: "Soybeans" | "Soybean Oil" | "Soybean Meal";
  weekEnding: string;
  netSalesKmt: number | null;
  exportsKmt: number | null;
  outstandingKmt: number | null;
}

function inferWeekEnding(reportDateYmd: string, mmdd: string): string {
  const [y, m, d] = reportDateYmd.split("-").map((x) => Number(x));
  const reportMonthDay = m * 100 + d;
  const [mm, dd] = mmdd.split("/").map((x) => Number(x));
  const weekMonthDay = mm * 100 + dd;
  const year = weekMonthDay > reportMonthDay ? y - 1 : y;
  return `${year}-${String(mm).padStart(2, "0")}-${String(dd).padStart(2, "0")}`;
}

function parseSummaryRows(preLines: string[], reportDateYmd: string): SummaryRow[] {
  const rows: SummaryRow[] = [];

  for (const line of preLines) {
    const upper = line.toUpperCase();
    if (!line.includes(":")) continue;

    let commodity: SummaryRow["commodity"] | null = null;
    if (upper.startsWith("SOYBEANS") && !upper.startsWith("SOYBEAN OIL") && !upper.startsWith("SOYBEAN CAKE"))
      commodity = "Soybeans";
    if (upper.startsWith("SOYBEAN OIL")) commodity = "Soybean Oil";
    if (upper.startsWith("SOYBEAN CAKE") || upper.startsWith("MEAL")) commodity = "Soybean Meal";
    if (!commodity) continue;

    const m = line.match(/:\s*(\d{2}\/\d{2})\s+(.+)$/);
    if (!m) continue;

    const weekEnding = inferWeekEnding(reportDateYmd, m[1]);
    const tokens = m[2].trim().split(/\s+/);
    if (tokens.length < 5) continue;

    rows.push({
      commodity,
      weekEnding,
      netSalesKmt: toNumber(tokens[0]),
      exportsKmt: toNumber(tokens[3]),
      outstandingKmt: toNumber(tokens[4]),
    });
  }

  return rows;
}

// ---------------------------------------------------------------------------
//  Inngest function
// ---------------------------------------------------------------------------
export const usdaExportSalesWeekly = inngest.createFunction(
  {
    id: "usda-export-sales-weekly",
    name: "USDA Export Sales (Weekly)",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 21 * * 4" }, // Thursdays 21:00 UTC
  async ({ step, logger }) => {
    if (!process.env.DATABASE_URL) throw new Error("DATABASE_URL not configured");

    // ── Step 1: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["usda-export-sales-weekly"],
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    logger.info(`Started ingest run: ${runId}`);

    // ── Step 2: fetch all 3 commodity pages + complete.htm in parallel ──
    const pages = await step.run("fetch-all-pages", async () => {
      const results: Record<string, string> = {};
      const fetches = [
        ...COMMODITY_PAGES.map(async (p) => {
          const res = await fetch(p.url, { headers: { "User-Agent": "ZINC-Fusion/2.0" } });
          if (!res.ok) throw new Error(`Fetch ${p.url} failed: ${res.status}`);
          results[p.commodity] = await res.text();
        }),
        (async () => {
          const res = await fetch(COMPLETE_URL, { headers: { "User-Agent": "ZINC-Fusion/2.0" } });
          if (!res.ok) throw new Error(`Fetch ${COMPLETE_URL} failed: ${res.status}`);
          results["complete"] = await res.text();
        })(),
      ];
      await Promise.all(fetches);
      return results;
    });

    // ── Step 3: parse all country-level data from commodity pages ──
    const allCountryRows: CountryRow[] = [];
    for (const page of COMMODITY_PAGES) {
      const html = pages[page.commodity];
      if (!html) continue;
      const rows = parseCommodityPage(html, page.commodity);
      allCountryRows.push(...rows);
    }

    // ── Step 4: parse summary totals from complete.htm ──
    const completeHtml = pages["complete"] ?? "";
    const preMatch = completeHtml.match(/<pre>([\s\S]*?)(?:<\/pre>|<\/html>)/i);
    let summaryRows: SummaryRow[] = [];
    let reportDateYmd = "";
    if (preMatch) {
      reportDateYmd = parseAsOfDate(preMatch[1]);
      summaryRows = parseSummaryRows(
        preMatch[1].split(/\r?\n/),
        reportDateYmd,
      ).filter((r) => r.weekEnding === reportDateYmd);
    }

    if (!reportDateYmd && allCountryRows.length > 0) {
      reportDateYmd = allCountryRows[0].reportDate;
    }

    logger.info(
      `Parsed: ${allCountryRows.length} country rows, ${summaryRows.length} summary rows, report date: ${reportDateYmd}`,
    );

    // ── Step 5: upsert country-level rows ──
    const countryResult = await step.run("upsert-country-rows", async () => {
      let upserted = 0;
      const client = await pool.connect();
      try {
        for (const row of allCountryRows) {
          const outMt = kmt(row.outstandingSalesKmt);
          const outYrAgoMt = kmt(row.outstandingSalesYrAgoKmt);
          const expMt = kmt(row.accumulatedExportsKmt);
          const expYrAgoMt = kmt(row.accumulatedExportsYrAgoKmt);
          const nextMyMt = kmt(row.outstandingNextMyKmt);
          const rowHash = computeRowHash(
            row.reportDate, row.commodity, row.destinationCountry, outMt, expMt,
          );

          await client.query(
            `INSERT INTO supply.usda_exports_1w
               (event_date, commodity, destination_country,
                outstanding_sales_mt, outstanding_sales_yr_ago_mt,
                exports_mt, exports_yr_ago_mt,
                outstanding_next_my_mt,
                is_region, parent_region, marketing_year,
                source, row_hash)
             VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
             ON CONFLICT (event_date, commodity, destination_country) DO UPDATE SET
               outstanding_sales_mt = EXCLUDED.outstanding_sales_mt,
               outstanding_sales_yr_ago_mt = EXCLUDED.outstanding_sales_yr_ago_mt,
               exports_mt = EXCLUDED.exports_mt,
               exports_yr_ago_mt = EXCLUDED.exports_yr_ago_mt,
               outstanding_next_my_mt = EXCLUDED.outstanding_next_my_mt,
               is_region = EXCLUDED.is_region,
               parent_region = EXCLUDED.parent_region,
               marketing_year = EXCLUDED.marketing_year,
               source = EXCLUDED.source,
               row_hash = EXCLUDED.row_hash,
               ingested_at = NOW()`,
            [
              row.reportDate, row.commodity, row.destinationCountry,
              outMt, outYrAgoMt, expMt, expYrAgoMt, nextMyMt,
              row.isRegion, row.parentRegion, row.marketingYear,
              "usda_fas_export_sales", rowHash,
            ],
          );
          upserted++;
        }
      } finally {
        client.release();
      }
      return upserted;
    });

    // ── Step 6: upsert summary totals (net_sales from complete.htm) ──
    const summaryResult = await step.run("upsert-summary-rows", async () => {
      let upserted = 0;
      const client = await pool.connect();
      try {
        for (const r of summaryRows) {
          const netSalesMt = kmt(r.netSalesKmt);
          const exportsMt = kmt(r.exportsKmt);
          const outstandingMt = kmt(r.outstandingKmt);
          const rowHash = computeRowHash(
            r.weekEnding, r.commodity, "TOTAL", outstandingMt, exportsMt,
          );

          await client.query(
            `INSERT INTO supply.usda_exports_1w
               (event_date, commodity, destination_country,
                net_sales_mt, exports_mt, outstanding_sales_mt,
                source, row_hash)
             VALUES ($1::date, $2, 'TOTAL', $3, $4, $5, $6, $7)
             ON CONFLICT (event_date, commodity, destination_country) DO UPDATE SET
               net_sales_mt = COALESCE(EXCLUDED.net_sales_mt, supply.usda_exports_1w.net_sales_mt),
               exports_mt = COALESCE(EXCLUDED.exports_mt, supply.usda_exports_1w.exports_mt),
               outstanding_sales_mt = COALESCE(EXCLUDED.outstanding_sales_mt, supply.usda_exports_1w.outstanding_sales_mt),
               source = EXCLUDED.source,
               row_hash = EXCLUDED.row_hash,
               ingested_at = NOW()`,
            [r.weekEnding, r.commodity, netSalesMt, exportsMt, outstandingMt, "usda_fas_export_sales", rowHash],
          );
          upserted++;
        }
      } finally {
        client.release();
      }
      return upserted;
    });

    // ── Step 7: finalize ingest run ──
    const totalRows = countryResult + summaryResult;
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", totalRows, totalRows, 0, 0],
        );
      } finally {
        client.release();
      }
    });

    logger.info(
      `Completed: ${countryResult} country rows + ${summaryResult} summary rows = ${totalRows} total`,
    );

    return {
      status: "success",
      runId,
      reportDate: reportDateYmd,
      countryRows: countryResult,
      summaryRows: summaryResult,
      totalRows,
    };
  },
);
