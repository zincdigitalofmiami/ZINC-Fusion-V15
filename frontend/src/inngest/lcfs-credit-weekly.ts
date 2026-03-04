/**
 * LCFS Credit Price Ingestion (CARB Weekly Activity Report)
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Upserts on (event_date) conflict
 *
 * Fetches CARB's Weekly LCFS Credit Transfer Activity XLSX,
 * parses transfer-level rows (date completed, price, volume),
 * computes daily VWAP, and upserts into supply.lcfs_1d.
 *
 * Schedule: Weekly on Monday at 08:00 UTC.
 * CARB typically publishes by Friday, so Monday gives margin.
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.1.0
 * @date 2026-02-16
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { XMLParser } from "fast-xml-parser";
import JSZip from "jszip";
import { getIngestPool } from "@/lib/db";

const CARB_WEEKLY_PAGE =
  "https://ww2.arb.ca.gov/resources/documents/weekly-lcfs-credit-transfer-activity-reports";
const SOURCE_NAME = "carb_weekly_activity_xlsx";
const USER_AGENT = "ZINC-Fusion/1.0";
const pool = getIngestPool();

// PoolClient helper functions removed — SQL inlined inside step.run() closures
// to prevent stale connections across Inngest durable execution boundaries.

// ---------------------------------------------------------------------------
// XLSX parsing via JSZip + fast-xml-parser
// ---------------------------------------------------------------------------

interface SheetRow {
  [colIndex: number]: string | undefined;
}

/**
 * Minimal XLSX reader: extracts sheets as arrays of row dictionaries.
 * Mirrors the Python _read_xlsx_as_dataframes approach.
 */
async function readXlsxSheets(
  xlsxBuffer: ArrayBuffer,
): Promise<Map<string, Array<Record<string, string | null>>>> {
  const zip = await JSZip.loadAsync(xlsxBuffer);

  // 1. Shared strings
  const sharedStrings: string[] = [];
  const ssFile = zip.file("xl/sharedStrings.xml");
  if (ssFile) {
    const ssXml = await ssFile.async("text");
    const parser = new XMLParser({ ignoreAttributes: false });
    const parsed = parser.parse(ssXml);
    const sst = parsed?.sst ?? parsed?.["sst"];
    if (sst) {
      const siItems = Array.isArray(sst.si) ? sst.si : sst.si ? [sst.si] : [];
      for (const si of siItems) {
        if (typeof si === "string") {
          sharedStrings.push(si);
        } else if (si?.t !== undefined) {
          sharedStrings.push(
            typeof si.t === "object" ? (si.t["#text"] ?? "") : String(si.t),
          );
        } else if (si?.r) {
          // Rich text: concatenate all <t> nodes
          const runs = Array.isArray(si.r) ? si.r : [si.r];
          const text = runs
            .map((r: Record<string, unknown>) => {
              const t = r?.t;
              if (typeof t === "object" && t !== null) {
                return (t as Record<string, string>)["#text"] ?? "";
              }
              return t !== undefined ? String(t) : "";
            })
            .join("");
          sharedStrings.push(text);
        } else {
          sharedStrings.push("");
        }
      }
    }
  }

  // 2. Workbook sheet names
  const sheetNames: string[] = [];
  const wbFile = zip.file("xl/workbook.xml");
  if (wbFile) {
    const wbXml = await wbFile.async("text");
    const parser = new XMLParser({ ignoreAttributes: false });
    const parsed = parser.parse(wbXml);
    const sheets =
      parsed?.workbook?.sheets?.sheet ?? parsed?.Workbook?.Sheets?.Sheet;
    if (sheets) {
      const sheetList = Array.isArray(sheets) ? sheets : [sheets];
      for (const s of sheetList) {
        sheetNames.push(s["@_name"] ?? `sheet${sheetNames.length + 1}`);
      }
    }
  }

  // 3. Parse worksheet files
  const sheetFiles = Object.keys(zip.files)
    .filter(
      (p) => p.startsWith("xl/worksheets/sheet") && p.endsWith(".xml"),
    )
    .sort();

  const result = new Map<string, Array<Record<string, string | null>>>();

  for (let i = 0; i < sheetFiles.length; i++) {
    const sheetPath = sheetFiles[i];
    const name = i < sheetNames.length ? sheetNames[i] : `sheet${i + 1}`;
    const wsXml = await zip.file(sheetPath)!.async("text");
    const parser = new XMLParser({
      ignoreAttributes: false,
      isArray: (tagName) =>
        tagName === "row" || tagName === "c",
    });
    const parsed = parser.parse(wsXml);
    const sheetData =
      parsed?.worksheet?.sheetData ?? parsed?.Worksheet?.SheetData;
    if (!sheetData) continue;

    const xmlRows = Array.isArray(sheetData.row)
      ? sheetData.row
      : sheetData.row
        ? [sheetData.row]
        : [];

    // Build sparse rows
    const rows: SheetRow[] = [];
    let maxCol = 0;

    for (const xmlRow of xmlRows) {
      const cells = Array.isArray(xmlRow.c) ? xmlRow.c : xmlRow.c ? [xmlRow.c] : [];
      const rowValues: SheetRow = {};
      for (const cell of cells) {
        const ref: string = cell["@_r"] ?? "";
        if (!ref) continue;
        const colIdx = colRefToIndex(ref);
        maxCol = Math.max(maxCol, colIdx);

        const cellType: string | undefined = cell["@_t"];
        const vNode = cell.v;
        if (vNode === undefined || vNode === null) continue;
        const raw = String(vNode);

        if (cellType === "s" && /^\d+$/.test(raw)) {
          const sIdx = parseInt(raw, 10);
          rowValues[colIdx] =
            sIdx < sharedStrings.length ? sharedStrings[sIdx] : raw;
        } else {
          rowValues[colIdx] = raw;
        }
      }
      rows.push(rowValues);
    }

    // Find header row (first non-empty)
    let headerIdx = -1;
    for (let r = 0; r < rows.length; r++) {
      const vals = Object.values(rows[r]);
      if (vals.some((v) => v !== undefined && v.trim() !== "")) {
        headerIdx = r;
        break;
      }
    }
    if (headerIdx < 0) continue;

    const header: string[] = [];
    for (let c = 0; c <= maxCol; c++) {
      header.push(rows[headerIdx][c]?.trim() ?? "");
    }

    const dataRows: Array<Record<string, string | null>> = [];
    for (let r = headerIdx + 1; r < rows.length; r++) {
      const rec: Record<string, string | null> = {};
      let hasAny = false;
      for (let c = 0; c <= maxCol; c++) {
        const hdr = header[c];
        if (!hdr) continue;
        const val = rows[r][c] ?? null;
        rec[hdr] = val;
        if (val !== null) hasAny = true;
      }
      if (hasAny) dataRows.push(rec);
    }

    result.set(name, dataRows);
  }

  return result;
}

function colRefToIndex(cellRef: string): number {
  const letters = cellRef.replace(/[^A-Z]/gi, "").toUpperCase();
  let idx = 0;
  for (const ch of letters) {
    idx = idx * 26 + (ch.charCodeAt(0) - 64);
  }
  return idx - 1;
}

// ---------------------------------------------------------------------------
// Activity row extraction + VWAP
// ---------------------------------------------------------------------------

interface ActivityRow {
  eventDate: string; // YYYY-MM-DD
  price: number;
  volume: number;
}

interface VwapRow {
  eventDate: string; // YYYY-MM-DD
  priceUsdPerMt: number;
  volumeMt: number;
}

/**
 * Identify the best sheet containing LCFS activity data.
 * Heuristic: sheet with columns matching "date completed", "price", "volume".
 */
function extractActivityRows(
  sheets: Map<string, Array<Record<string, string | null>>>,
): ActivityRow[] {
  let bestSheet: Array<Record<string, string | null>> | null = null;
  let bestScore = -1;
  let bestCols: {
    dateCol: string;
    priceCol: string;
    volumeCol: string;
  } | null = null;

  for (const [, rows] of sheets) {
    if (!rows.length) continue;
    const colNames = Object.keys(rows[0]);
    const normMap = new Map<string, string>();
    for (const col of colNames) {
      normMap.set(col.toLowerCase().replace(/\s+/g, " ").trim(), col);
    }

    let score = 0;
    let dateCol: string | undefined;
    let priceCol: string | undefined;
    let volumeCol: string | undefined;

    for (const [norm, raw] of normMap) {
      if (norm === "date completed" || norm.startsWith("date completed")) {
        score += 2;
        dateCol = raw;
      }
      if (norm === "price" || norm.endsWith("price") || norm.includes("price")) {
        score += 1;
        priceCol = raw;
      }
      if (
        norm === "volume" ||
        norm.endsWith("volume") ||
        norm.includes("volume")
      ) {
        score += 1;
        volumeCol = raw;
      }
    }

    if (score > bestScore && dateCol && priceCol && volumeCol) {
      bestScore = score;
      bestSheet = rows;
      bestCols = { dateCol, priceCol, volumeCol };
    }
  }

  if (!bestSheet || !bestCols || bestScore < 3) {
    throw new Error(
      "Could not locate an activity log sheet with date/price/volume columns",
    );
  }

  const result: ActivityRow[] = [];
  for (const row of bestSheet) {
    const rawDate = row[bestCols.dateCol];
    const rawPrice = row[bestCols.priceCol];
    const rawVolume = row[bestCols.volumeCol];

    if (!rawDate || !rawPrice || !rawVolume) continue;

    const price = parseFloat(rawPrice);
    const volume = parseFloat(rawVolume);
    if (!Number.isFinite(price) || !Number.isFinite(volume)) continue;
    if (price <= 0 || volume <= 0) continue;

    const eventDate = parseActivityDate(rawDate);
    if (!eventDate) continue;

    result.push({ eventDate, price, volume });
  }

  return result;
}

/**
 * Parse a date string from the CARB XLSX.
 * Handles both Excel serial numbers (>1000) and ISO/human date strings.
 */
function parseActivityDate(raw: string): string | null {
  const trimmed = raw.trim();
  const num = parseFloat(trimmed);

  // Excel serial date: number > 1000 means days since 1899-12-30
  if (Number.isFinite(num) && num > 1000 && /^\d+(\.\d+)?$/.test(trimmed)) {
    // Excel epoch: 1899-12-30
    const epoch = new Date(1899, 11, 30);
    const ms = epoch.getTime() + num * 86_400_000;
    const d = new Date(ms);
    if (isNaN(d.getTime())) return null;
    return d.toISOString().slice(0, 10);
  }

  // Try standard date parsing
  const d = new Date(trimmed);
  if (!isNaN(d.getTime())) {
    return d.toISOString().slice(0, 10);
  }

  return null;
}

function computeDailyVwap(activity: ActivityRow[]): VwapRow[] {
  const byDate = new Map<
    string,
    { dollarSum: number; volumeSum: number }
  >();

  for (const row of activity) {
    const existing = byDate.get(row.eventDate) ?? {
      dollarSum: 0,
      volumeSum: 0,
    };
    existing.dollarSum += row.price * row.volume;
    existing.volumeSum += row.volume;
    byDate.set(row.eventDate, existing);
  }

  const result: VwapRow[] = [];
  for (const [eventDate, agg] of byDate) {
    if (agg.volumeSum === 0) continue;
    result.push({
      eventDate,
      priceUsdPerMt: agg.dollarSum / agg.volumeSum,
      volumeMt: agg.volumeSum,
    });
  }

  result.sort((a, b) => a.eventDate.localeCompare(b.eventDate));
  return result;
}

// ---------------------------------------------------------------------------
// CARB page scraping
// ---------------------------------------------------------------------------

function findActivityXlsxUrl(html: string): string {
  // Match href with both single and double quotes, and .xlsx/.XLSX extensions
  const hrefPattern = /href=["']([^"']+\.xlsx)["']/gi;
  let match: RegExpExecArray | null;
  const candidates: string[] = [];

  while ((match = hrefPattern.exec(html)) !== null) {
    const href = match[1];
    const lower = href.toLowerCase();
    // Relaxed matching: require any 2 of 4 keywords (weekly, lcfs, credit, activity)
    let keywordHits = 0;
    if (lower.includes("weekly")) keywordHits++;
    if (lower.includes("lcfs")) keywordHits++;
    if (lower.includes("credit")) keywordHits++;
    if (lower.includes("activity")) keywordHits++;

    if (keywordHits >= 2) {
      candidates.push(
        href.startsWith("http") ? href : `https://ww2.arb.ca.gov${href}`,
      );
    }
  }

  if (candidates.length === 0) {
    throw new Error(
      "Could not find Weekly LCFS Credit Activity .xlsx link on CARB page",
    );
  }

  // Return last match (most recent, CARB lists newest first)
  return candidates[candidates.length - 1];
}

// ---------------------------------------------------------------------------
// Inngest function
// ---------------------------------------------------------------------------

export const lcfsCreditWeekly = inngest.createFunction(
  {
    id: "lcfs-credit-weekly",
    name: "CARB LCFS Credit Price Ingestion",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 8 * * 1" }, // Monday 08:00 UTC
  async ({ step, logger }) => {
    // ── Step 1: assert tables exist ──
    await step.run("assert-tables", async () => {
      const client = await pool.connect();
      try {
        await client.query("SELECT 1 FROM ops.ingest_run LIMIT 1");
        await client.query("SELECT 1 FROM supply.lcfs_1d LIMIT 1");
      } finally {
        client.release();
      }
    });

    // ── Step 2: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["lcfs-credit-weekly"],
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    // ── Step 3: fetch XLSX from CARB ──
    const { xlsxUrl, xlsxBuffer, batchId } = await step.run(
      "fetch-xlsx",
      async () => {
        logger.info("Fetching CARB weekly LCFS activity page...");
        const pageController = new AbortController();
        const pageTimeout = setTimeout(() => pageController.abort(), 60_000);
        let pageRes: Response;
        try {
          pageRes = await fetch(CARB_WEEKLY_PAGE, {
            headers: { "User-Agent": USER_AGENT },
            signal: pageController.signal,
          });
          clearTimeout(pageTimeout);
        } catch (err) {
          clearTimeout(pageTimeout);
          if (err instanceof Error && err.name === "AbortError") {
            throw new Error("CARB page fetch timed out after 60s");
          }
          throw err;
        }
        if (!pageRes.ok) {
          throw new Error(
            `CARB page fetch failed: ${pageRes.status} ${pageRes.statusText}`,
          );
        }
        const html = await pageRes.text();
        const url = findActivityXlsxUrl(html);
        logger.info(`Found activity XLSX: ${url}`);

        logger.info("Downloading activity XLSX...");
        const xlsxController = new AbortController();
        const xlsxTimeout = setTimeout(() => xlsxController.abort(), 90_000);
        let xlsxRes: Response;
        try {
          xlsxRes = await fetch(url, {
            headers: { "User-Agent": USER_AGENT },
            signal: xlsxController.signal,
          });
          clearTimeout(xlsxTimeout);
        } catch (err) {
          clearTimeout(xlsxTimeout);
          if (err instanceof Error && err.name === "AbortError") {
            throw new Error("XLSX download timed out after 90s");
          }
          throw err;
        }
        if (!xlsxRes.ok) {
          throw new Error(
            `XLSX download failed: ${xlsxRes.status} ${xlsxRes.statusText}`,
          );
        }
        const buffer = await xlsxRes.arrayBuffer();
        const batch = createHash("sha256")
          .update(`${url}|${buffer.byteLength}`)
          .digest("hex")
          .slice(0, 16);

        return {
          xlsxUrl: url,
          xlsxBuffer: Buffer.from(buffer).toString("base64"),
          batchId: batch,
        };
      },
    );

    // ── Step 4: parse XLSX and compute VWAP (pure computation) ──
    const vwapRows = await step.run("parse-compute-vwap", async () => {
      const buffer = Buffer.from(xlsxBuffer, "base64");
      logger.info(
        `Parsing XLSX (${(buffer.length / 1024).toFixed(0)} KB)...`,
      );
      const sheets = await readXlsxSheets(buffer.buffer as ArrayBuffer);
      logger.info(
        `Found ${sheets.size} sheet(s): ${Array.from(sheets.keys()).join(", ")}`,
      );

      const activity = extractActivityRows(sheets);
      logger.info(`Extracted ${activity.length} activity rows`);

      const vwap = computeDailyVwap(activity);
      logger.info(
        `Computed ${vwap.length} daily VWAP rows (${vwap.length > 0 ? vwap[0].eventDate : "?"} → ${vwap.length > 0 ? vwap[vwap.length - 1].eventDate : "?"})`,
      );
      return vwap;
    });

    if (vwapRows.length === 0) {
      logger.warn("No LCFS VWAP rows computed — skipping upsert");
      await step.run("complete-empty", async () => {
        const client = await pool.connect();
        try {
          await client.query(
            `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
             rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
            [runId, "success", 0, 0, 0, 0],
          );
        } finally {
          client.release();
        }
      });
      return { status: "empty", runId, xlsxUrl };
    }

    // ── Step 5: upsert VWAP rows ──
    const upsertResult = await step.run("upsert-rows", async () => {
      let upserted = 0;
      const client = await pool.connect();
      try {
        await client.query("BEGIN");
        try {
          for (const row of vwapRows) {
            await client.query(
              `INSERT INTO supply.lcfs_1d (event_date, price_usd_per_mt, source, ingestion_batch_id)
               VALUES ($1::date, $2, $3, $4)
               ON CONFLICT (event_date) DO UPDATE SET
                 price_usd_per_mt = EXCLUDED.price_usd_per_mt,
                 source = EXCLUDED.source,
                 ingestion_batch_id = EXCLUDED.ingestion_batch_id,
                 created_at = NOW()`,
              [row.eventDate, row.priceUsdPerMt, SOURCE_NAME, batchId],
            );
            upserted++;
          }
          await client.query("COMMIT");
        } catch (e) {
          await client.query("ROLLBACK");
          throw e;
        }
      } finally {
        client.release();
      }
      return { attempted: vwapRows.length, upserted };
    });

    // ── Step 6: finalize ingest run ──
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", upsertResult.attempted, upsertResult.upserted, 0, 0],
        );
      } finally {
        client.release();
      }
    });

    logger.info(
      `LCFS ingestion complete: ${upsertResult.upserted} rows upserted (batch ${batchId})`,
    );

    return {
      status: "success",
      runId,
      xlsxUrl,
      inserted: upsertResult.upserted,
      dateRange:
        vwapRows.length > 0
          ? `${vwapRows[0].eventDate} → ${vwapRows[vwapRows.length - 1].eventDate}`
          : null,
    };
  },
);
