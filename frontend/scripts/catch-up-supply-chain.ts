#!/usr/bin/env npx tsx
/**
 * catch-up-supply-chain.ts
 *
 * One-shot script to backfill stale supply chain data.
 * Runs locally against the production DATABASE_URL.
 *
 * Usage:
 *   cd frontend
 *   npx tsx scripts/catch-up-supply-chain.ts
 *
 * Sources backfilled:
 *   1. CFTC COT (pos.cftc_1w) — public API, no key needed
 *   2. EIA Biodiesel (supply.eia_biodiesel_1m) — needs EIA_API_KEY
 *   3. USDA Export Sales (supply.usda_exports_1w) — public HTML scrape
 */

import pg from "pg";
import { createHash } from "crypto";
import { readFileSync } from "fs";

// Load .env.local manually (no dotenv dependency)
try {
  const envContent = readFileSync(".env.local", "utf-8");
  for (const line of envContent.split("\n")) {
    const match = line.match(/^([A-Z_]+)="?([^"]*)"?\s*$/);
    if (match && !process.env[match[1]]) {
      process.env[match[1]] = match[2];
    }
  }
} catch {
  // .env.local not found, rely on existing env
}

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) {
  console.error("DATABASE_URL not set in .env.local");
  process.exit(1);
}

const pool = new pg.Pool({
  connectionString: DATABASE_URL,
  ssl: { rejectUnauthorized: false },
  max: 3,
});

function hash(input: string): string {
  return createHash("sha256").update(input).digest("hex");
}

/* ──────────────────────────────────────────────
   1. CFTC COT Backfill
   ────────────────────────────────────────────── */

const CFTC_CONTRACTS = [
  { code: "007601", symbol: "ZL", name: "Soybean Oil" },
  { code: "005602", symbol: "ZS", name: "Soybeans" },
  { code: "002602", symbol: "ZC", name: "Corn" },
  { code: "026603", symbol: "ZM", name: "Soybean Meal" },
  { code: "067651", symbol: "CL", name: "Crude Oil" },
  { code: "023651", symbol: "NG", name: "Natural Gas" },
  { code: "088691", symbol: "GC", name: "Gold" },
  { code: "084691", symbol: "SI", name: "Silver" },
  { code: "085692", symbol: "HG", name: "Copper" },
];

function cftcField(row: Record<string, string>, base: string, suffix = ""): string {
  const candidates = [
    `${base}${suffix}`,
    base,
    base.replace("swap_", "swap__") + suffix,
    base.replace("swap_", "swap__"),
  ];
  for (const key of candidates) {
    if (row[key] !== undefined && row[key] !== "") return row[key];
  }
  return "0";
}

async function catchUpCFTC(): Promise<number> {
  console.log("\n═══ CFTC COT Backfill ═══");

  // Find the gap
  const client = await pool.connect();
  try {
    const latestRes = await client.query(
      "SELECT MAX(event_date)::text as latest FROM pos.cftc_1w"
    );
    const latestDate = latestRes.rows[0]?.latest ?? "2000-01-01";
    console.log(`DB latest: ${latestDate}`);

    // Fetch last 1000 records (covers ~3 months of weekly data for all contracts)
    const url = `https://publicreporting.cftc.gov/resource/72hh-3qpy.json?$order=report_date_as_yyyy_mm_dd%20DESC&$limit=1000`;
    console.log("Fetching from CFTC API...");
    const res = await fetch(url, { headers: { "User-Agent": "ZINC-Fusion/1.0" } });
    if (!res.ok) throw new Error(`CFTC API error: ${res.status}`);
    const data: Record<string, string>[] = await res.json();
    console.log(`Got ${data.length} records from CFTC API`);

    let totalInserted = 0;
    let totalSkipped = 0;

    for (const contract of CFTC_CONTRACTS) {
      const rows = data.filter(
        (r) =>
          r.cftc_contract_market_code === contract.code ||
          r.contract_market_name?.toLowerCase().includes(contract.name.toLowerCase())
      );

      const recent = rows
        .filter((r) => r.report_date_as_yyyy_mm_dd)
        .sort((a, b) =>
          String(b.report_date_as_yyyy_mm_dd).localeCompare(String(a.report_date_as_yyyy_mm_dd))
        );

      let contractInserted = 0;

      for (const row of recent) {
        const reportDate = row.report_date_as_yyyy_mm_dd?.split("T")[0];
        if (!reportDate) continue;
        if (reportDate <= latestDate) {
          totalSkipped++;
          continue;
        }

        const openInterest = parseInt(cftcField(row, "open_interest", "_all"));
        const managedLong = parseInt(cftcField(row, "m_money_positions_long", "_all"));
        const managedShort = parseInt(cftcField(row, "m_money_positions_short", "_all"));
        const prodMercLong = parseInt(cftcField(row, "prod_merc_positions_long", "_all"));
        const prodMercShort = parseInt(cftcField(row, "prod_merc_positions_short", "_all"));
        const swapLong = parseInt(cftcField(row, "swap_positions_long", "_all"));
        const swapShort = parseInt(cftcField(row, "swap_positions_short", "_all"));
        const otherLong = parseInt(cftcField(row, "other_rept_positions_long", "_all"));
        const otherShort = parseInt(cftcField(row, "other_rept_positions_short", "_all"));
        const nonreptLong = parseInt(cftcField(row, "nonrept_positions_long", "_all"));
        const nonreptShort = parseInt(cftcField(row, "nonrept_positions_short", "_all"));

        const managedNet = managedLong - managedShort;
        const prodMercNet = prodMercLong - prodMercShort;
        const swapNet = swapLong - swapShort;
        const otherNet = otherLong - otherShort;
        const nonreptNet = nonreptLong - nonreptShort;

        const payload = {
          event_date: reportDate,
          symbol: contract.symbol,
          open_interest: openInterest,
          managed_money_long: managedLong,
          managed_money_short: managedShort,
          managed_money_net: managedNet,
          prod_merc_long: prodMercLong,
          prod_merc_short: prodMercShort,
          prod_merc_net: prodMercNet,
          swap_long: swapLong,
          swap_short: swapShort,
          swap_net: swapNet,
          other_rept_long: otherLong,
          other_rept_short: otherShort,
          other_rept_net: otherNet,
          nonrept_long: nonreptLong,
          nonrept_short: nonreptShort,
          nonrept_net: nonreptNet,
        };

        const rowHash = hash(JSON.stringify(payload));

        // Check for existing
        const exists = await client.query(
          `SELECT 1 FROM pos.cftc_1w WHERE event_date=$1::date AND symbol=$2 LIMIT 1`,
          [reportDate, contract.symbol]
        );
        if (exists.rows.length > 0) {
          totalSkipped++;
          continue;
        }

        await client.query(
          `INSERT INTO pos.cftc_1w
            (event_date, symbol, open_interest,
             managed_money_long, managed_money_short, managed_money_net,
             prod_merc_long, prod_merc_short, prod_merc_net,
             swap_long, swap_short, swap_net,
             other_rept_long, other_rept_short, other_rept_net,
             nonrept_long, nonrept_short, nonrept_net,
             managed_money_net_pct_oi, prod_merc_net_pct_oi,
             source, row_hash)
           VALUES ($1::date, $2, $3,
                   $4, $5, $6,
                   $7, $8, $9,
                   $10, $11, $12,
                   $13, $14, $15,
                   $16, $17, $18,
                   $19, $20,
                   $21, $22)`,
          [
            reportDate, contract.symbol, openInterest,
            managedLong, managedShort, managedNet,
            prodMercLong, prodMercShort, prodMercNet,
            swapLong, swapShort, swapNet,
            otherLong, otherShort, otherNet,
            nonreptLong, nonreptShort, nonreptNet,
            openInterest > 0 ? (managedNet / openInterest) * 100 : 0,
            openInterest > 0 ? (prodMercNet / openInterest) * 100 : 0,
            "cftc_api_catchup", rowHash,
          ]
        );
        contractInserted++;
        totalInserted++;
      }

      if (contractInserted > 0) {
        console.log(`  ${contract.symbol}: +${contractInserted} rows`);
      }
    }

    console.log(`CFTC: ${totalInserted} inserted, ${totalSkipped} skipped`);

    // Verify
    const verifyRes = await client.query(
      "SELECT MAX(event_date)::text as latest FROM pos.cftc_1w"
    );
    console.log(`CFTC now current through: ${verifyRes.rows[0]?.latest}`);

    // Check ZL prod_merc quality
    const qualRes = await client.query(`
      SELECT event_date::text, open_interest, prod_merc_long, prod_merc_short
      FROM pos.cftc_1w WHERE symbol='ZL' ORDER BY event_date DESC LIMIT 3
    `);
    for (const r of qualRes.rows) {
      const flag = r.prod_merc_long === 0 && r.prod_merc_short === 0 && r.open_interest > 0 ? " ⚠️ 0/0!" : " ✓";
      console.log(`  ZL ${r.event_date}: OI=${r.open_interest} PM=${r.prod_merc_long}/${r.prod_merc_short}${flag}`);
    }

    return totalInserted;
  } finally {
    client.release();
  }
}

/* ──────────────────────────────────────────────
   2. EIA Biodiesel Backfill
   ────────────────────────────────────────────── */

const KB_TO_MGAL = 42 / 1000;

async function catchUpEIA(): Promise<number> {
  console.log("\n═══ EIA Biodiesel Backfill ═══");

  const EIA_API_KEY = process.env.EIA_API_KEY;
  if (!EIA_API_KEY) {
    console.warn("EIA_API_KEY not set, skipping EIA biodiesel backfill");
    return 0;
  }

  const client = await pool.connect();
  try {
    const latestRes = await client.query(
      "SELECT MAX(report_month)::text as latest FROM supply.eia_biodiesel_1m"
    );
    console.log(`DB latest: ${latestRes.rows[0]?.latest}`);

    // Fetch last 36 months
    const startDate = new Date();
    startDate.setMonth(startDate.getMonth() - 36);
    const startStr = `${startDate.getFullYear()}-${String(startDate.getMonth() + 1).padStart(2, "0")}`;

    const url = `https://api.eia.gov/v2/petroleum/sum/snd/data/?api_key=${EIA_API_KEY}&frequency=monthly&data[0]=value&facets[duoarea][]=NUS&facets[process][]=YNP&start=${startStr}&length=500&sort[0][column]=period&sort[0][direction]=desc`;

    console.log("Fetching from EIA API...");
    const res = await fetch(url);
    if (!res.ok) throw new Error(`EIA API error: ${res.status}`);
    const json = await res.json();
    const data = json.response.data;

    // Merge by period
    const byPeriod = new Map<string, { biodiesel: number | null; renewable: number | null }>();
    for (const point of data) {
      if (point.value === null || point.value === undefined) continue;
      if (point.product !== "EPOORDB" && point.product !== "EPOORDO") continue;

      const monthKey = point.period;
      if (!byPeriod.has(monthKey)) {
        byPeriod.set(monthKey, { biodiesel: null, renewable: null });
      }
      const record = byPeriod.get(monthKey)!;
      const mgal = Math.round(parseFloat(point.value) * KB_TO_MGAL * 100) / 100;

      if (point.product === "EPOORDB") {
        record.biodiesel = (record.biodiesel ?? 0) + mgal;
      } else {
        record.renewable = (record.renewable ?? 0) + mgal;
      }
    }

    console.log(`EIA API returned ${byPeriod.size} monthly records`);

    let inserted = 0;
    let updated = 0;
    let skipped = 0;

    for (const [period, values] of byPeriod) {
      const reportMonth = `${period}-01`;
      const rowHash = hash(`${reportMonth}|${values.biodiesel ?? "null"}|${values.renewable ?? "null"}`);

      const existing = await client.query(
        `SELECT row_hash FROM supply.eia_biodiesel_1m WHERE report_month = $1`,
        [reportMonth]
      );

      if (existing.rows.length > 0 && existing.rows[0].row_hash === rowHash) {
        skipped++;
        continue;
      }

      await client.query(
        `INSERT INTO supply.eia_biodiesel_1m
          (report_month, biodiesel_production_mgal, renewable_diesel_production_mgal,
           feedstock_soybean_oil_pct, capacity_utilization_pct, ingested_at, row_hash)
         VALUES ($1, $2, $3, NULL, NULL, NOW(), $4)
         ON CONFLICT (report_month) DO UPDATE SET
           biodiesel_production_mgal = EXCLUDED.biodiesel_production_mgal,
           renewable_diesel_production_mgal = EXCLUDED.renewable_diesel_production_mgal,
           ingested_at = NOW(),
           row_hash = EXCLUDED.row_hash`,
        [reportMonth, values.biodiesel, values.renewable, rowHash]
      );

      if (existing.rows.length > 0) {
        updated++;
      } else {
        inserted++;
      }
    }

    console.log(`EIA: ${inserted} inserted, ${updated} updated, ${skipped} unchanged`);

    const verifyRes = await client.query(
      "SELECT MAX(report_month)::text as latest, COUNT(*) as total FROM supply.eia_biodiesel_1m"
    );
    console.log(`EIA now: ${verifyRes.rows[0]?.total} rows, latest=${verifyRes.rows[0]?.latest}`);

    return inserted + updated;
  } finally {
    client.release();
  }
}

/* ──────────────────────────────────────────────
   3. USDA Export Sales Backfill
   ────────────────────────────────────────────── */

const MONTHS: Record<string, string> = {
  JANUARY: "01", FEBRUARY: "02", MARCH: "03", APRIL: "04",
  MAY: "05", JUNE: "06", JULY: "07", AUGUST: "08",
  SEPTEMBER: "09", OCTOBER: "10", NOVEMBER: "11", DECEMBER: "12",
};

function parseAsOfDate(preText: string): string {
  const m = preText.match(/EXPORT SALES AS OF\s+([A-Z]+)\s+(\d{1,2}),\s*(\d{4})/i);
  if (!m) throw new Error("Failed to parse report AS OF date");
  const month = MONTHS[m[1].toUpperCase()];
  if (!month) throw new Error(`Unknown month: ${m[1]}`);
  return `${m[3]}-${month}-${String(m[2]).padStart(2, "0")}`;
}

function inferWeekEnding(reportDateYmd: string, mmdd: string): string {
  const [y, m, d] = reportDateYmd.split("-").map(Number);
  const reportMonthDay = m * 100 + d;
  const [mm, dd] = mmdd.split("/").map(Number);
  const weekMonthDay = mm * 100 + dd;
  const year = weekMonthDay > reportMonthDay ? y - 1 : y;
  return `${year}-${String(mm).padStart(2, "0")}-${String(dd).padStart(2, "0")}`;
}

function toNumber(token: string): number | null {
  const t = token.trim();
  if (t === "-" || t === "*" || t === "") return null;
  const cleaned = t.replace(/\s*\d+\/$/, "").replace(/,/g, "");
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

function normalizeDestination(raw: string): string | null {
  const u = raw.trim().replace(/\s+/g, " ").toUpperCase();
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

async function catchUpUSDAExports(): Promise<number> {
  console.log("\n═══ USDA Export Sales Backfill ═══");

  const client = await pool.connect();
  try {
    const latestRes = await client.query(
      "SELECT MAX(event_date)::text as latest FROM supply.usda_exports_1w"
    );
    console.log(`DB latest: ${latestRes.rows[0]?.latest}`);

    console.log("Fetching USDA FAS complete.htm...");
    const res = await fetch("https://apps.fas.usda.gov/export-sales/complete.htm", {
      headers: { "User-Agent": "ZINC-Fusion/1.0" },
    });
    if (!res.ok) throw new Error(`USDA fetch error: ${res.status}`);
    const html = await res.text();

    const preMatch = html.match(/<pre>([\s\S]*?)<\/pre>/i);
    if (!preMatch) throw new Error("Failed to extract <pre> content");
    const preText = preMatch[1];
    const reportDateYmd = parseAsOfDate(preText);
    console.log(`Report AS OF: ${reportDateYmd}`);

    const preLines = preText.split(/\r?\n/);

    // Parse summary rows (weekly transaction data)
    type SummaryRow = {
      commodity: "Soybeans" | "Soybean Oil" | "Soybean Meal";
      weekEnding: string;
      netSalesKmt: number | null;
      exportsKmt: number | null;
      outstandingKmt: number | null;
    };

    const summaryRows: SummaryRow[] = [];
    for (let i = 0; i < preLines.length; i++) {
      const line = preLines[i];
      const upper = line.toUpperCase();
      if (!line.includes(":")) continue;

      let commodity: SummaryRow["commodity"] | null = null;
      if (upper.startsWith("SOYBEANS")) commodity = "Soybeans";
      if (upper.startsWith("SOYBEAN OIL")) commodity = "Soybean Oil";
      if (upper.startsWith("SOYBEAN CAKE") || upper.startsWith("MEAL")) commodity = "Soybean Meal";
      if (!commodity) continue;

      const m = line.match(/:\s*(\d{2}\/\d{2})\s+(.+)$/);
      if (!m) continue;

      const weekEnding = inferWeekEnding(reportDateYmd, m[1]);
      const tokens = m[2].trim().split(/\s+/);
      if (tokens.length < 5) continue;

      summaryRows.push({
        commodity,
        weekEnding,
        netSalesKmt: toNumber(tokens[0]),
        exportsKmt: toNumber(tokens[3]),
        outstandingKmt: toNumber(tokens[4]),
      });
    }

    // Parse destination sections
    type DestRow = {
      commodity: string;
      reportDate: string;
      destinationCountry: string;
      outstandingSalesKmt: number | null;
      accumulatedExportsKmt: number | null;
    };

    function parseDestSection(headerMatch: RegExp, commodity: string): DestRow[] {
      const out: DestRow[] = [];
      const startIdx = preLines.findIndex((l) => headerMatch.test(l.toUpperCase()));
      if (startIdx === -1) return out;

      for (let i = startIdx; i < preLines.length; i++) {
        const line = preLines[i];
        if (i !== startIdx && /MARKETING YEAR/.test(line.toUpperCase()) && /SOYBEAN/.test(line.toUpperCase())) break;

        const m = line.match(/^\s*([^:]{3,})\s*:\s*(.+)$/);
        if (!m) continue;

        const dest = normalizeDestination(m[1]);
        if (!dest) continue;

        const tokens = m[2].trim().split(/\s+/);
        if (tokens.length < 4) continue;

        out.push({
          commodity,
          reportDate: reportDateYmd,
          destinationCountry: dest,
          outstandingSalesKmt: toNumber(tokens[0]),
          accumulatedExportsKmt: toNumber(tokens[2]),
        });
      }
      return out;
    }

    const currentWeekSummary = summaryRows.filter((r) => r.weekEnding === reportDateYmd);
    const soyRows = parseDestSection(/^SOYBEANS\s+MARKETING YEAR/, "Soybeans");
    const mealRows = parseDestSection(/^SOYBEAN CAKE AND MEAL\s+MARKETING YEAR/, "Soybean Meal");
    const oilRows = parseDestSection(/^SOYBEAN OIL\s+MARKETING YEAR/, "Soybean Oil");

    let inserted = 0;
    let skipped = 0;

    // Insert summary rows
    for (const r of currentWeekSummary) {
      const dest = "TOTAL";
      const exists = await client.query(
        `SELECT 1 FROM supply.usda_exports_1w
         WHERE event_date=$1::date AND commodity=$2 AND COALESCE(destination_country,'')=COALESCE($3,'')
         LIMIT 1`,
        [r.weekEnding, r.commodity, dest]
      );
      if (exists.rows.length > 0) { skipped++; continue; }

      const netMt = r.netSalesKmt !== null ? r.netSalesKmt * 1000 : null;
      const expMt = r.exportsKmt !== null ? r.exportsKmt * 1000 : null;
      const outMt = r.outstandingKmt !== null ? r.outstandingKmt * 1000 : null;
      const rowHash = hash(`${r.weekEnding}|${r.commodity}|${dest}|${netMt}|${expMt}|${outMt}`);

      await client.query(
        `INSERT INTO supply.usda_exports_1w
          (event_date, commodity, destination_country, net_sales_mt, exports_mt, outstanding_sales_mt, source, row_hash)
         VALUES ($1::date,$2,$3,$4,$5,$6,$7,$8)`,
        [r.weekEnding, r.commodity, dest, netMt, expMt, outMt, "usda_fas_catchup", rowHash]
      );
      inserted++;
    }

    // Insert destination rows
    for (const row of [...soyRows, ...mealRows, ...oilRows]) {
      const exists = await client.query(
        `SELECT 1 FROM supply.usda_exports_1w
         WHERE event_date=$1::date AND commodity=$2 AND COALESCE(destination_country,'')=COALESCE($3,'')
         LIMIT 1`,
        [row.reportDate, row.commodity, row.destinationCountry]
      );
      if (exists.rows.length > 0) { skipped++; continue; }

      const expMt = row.accumulatedExportsKmt !== null ? row.accumulatedExportsKmt * 1000 : null;
      const outMt = row.outstandingSalesKmt !== null ? row.outstandingSalesKmt * 1000 : null;
      const rowHash = hash(`${row.reportDate}|${row.commodity}|${row.destinationCountry}|null|${expMt}|${outMt}`);

      await client.query(
        `INSERT INTO supply.usda_exports_1w
          (event_date, commodity, destination_country, net_sales_mt, exports_mt, outstanding_sales_mt, source, row_hash)
         VALUES ($1::date,$2,$3,$4,$5,$6,$7,$8)`,
        [row.reportDate, row.commodity, row.destinationCountry, null, expMt, outMt, "usda_fas_catchup", rowHash]
      );
      inserted++;
    }

    console.log(`USDA Exports: ${inserted} inserted, ${skipped} already existed`);

    const verifyRes = await client.query(
      "SELECT MAX(event_date)::text as latest FROM supply.usda_exports_1w"
    );
    console.log(`USDA Exports now current through: ${verifyRes.rows[0]?.latest}`);

    return inserted;
  } finally {
    client.release();
  }
}

/* ──────────────────────────────────────────────
   Main
   ────────────────────────────────────────────── */

async function main() {
  console.log("╔══════════════════════════════════════════╗");
  console.log("║  Supply Chain Catch-Up Script            ║");
  console.log("║  ZINC-FUSION-V15                        ║");
  console.log("╚══════════════════════════════════════════╝");
  console.log(`Database: ${DATABASE_URL!.split("@")[1]?.split("?")[0] ?? "***"}`);
  console.log(`Time: ${new Date().toISOString()}`);

  const results: Record<string, number> = {};

  try {
    results.cftc = await catchUpCFTC();
  } catch (err) {
    console.error("CFTC failed:", err);
    results.cftc = -1;
  }

  try {
    results.eia = await catchUpEIA();
  } catch (err) {
    console.error("EIA failed:", err);
    results.eia = -1;
  }

  try {
    results.usda_exports = await catchUpUSDAExports();
  } catch (err) {
    console.error("USDA Exports failed:", err);
    results.usda_exports = -1;
  }

  console.log("\n╔══════════════════════════════════════════╗");
  console.log("║  Summary                                ║");
  console.log("╠══════════════════════════════════════════╣");
  for (const [source, count] of Object.entries(results)) {
    const status = count < 0 ? "FAILED" : count === 0 ? "no change" : `+${count} rows`;
    console.log(`║  ${source.padEnd(20)} ${status.padEnd(18)} ║`);
  }
  console.log("╠══════════════════════════════════════════╣");
  console.log("║  MPOB Palm: SKIPPED (USDA API key bad)  ║");
  console.log("║  EPA RIN:   SKIPPED (WebSocket needed)  ║");
  console.log("╚══════════════════════════════════════════╝");

  await pool.end();
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
