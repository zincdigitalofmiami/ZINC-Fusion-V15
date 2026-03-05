/**
 * Panama Canal Daily Operations & Transit Data
 *
 * Scrapes daily canal operations from pancanal.com for:
 * - Vessel transit counts (Panamax / Neopanamax)
 * - Draft restrictions (affects grain bulk carrier capacity)
 * - Wait times (affects shipping costs & delivery timelines)
 *
 * Critical for: tariff specialist, crush specialist (export logistics),
 * china specialist (shipping route competitiveness)
 *
 * Source: https://www.pancanal.com/en/daily-canal-operations/
 * Backup: ACP Advisories RSS
 *
 * Table: supply.panama_canal_1d
 *
 * @author Claude (ZINC-FUSION-V15)
 * @date 2026-03-04
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CanalDayRecord {
  eventDate: string;
  transitsPanamax: number | null;
  transitsNeopanamax: number | null;
  transitsTotal: number | null;
  maxDraftFt: number | null;
  bookingSlots: number | null;
  advisoryText: string | null;
}

// ---------------------------------------------------------------------------
// Table DDL
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Scraping Logic
// ---------------------------------------------------------------------------

async function scrapePanamaCanal(): Promise<CanalDayRecord[]> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);

  try {
    const res = await fetch(
      "https://www.pancanal.com/en/daily-canal-operations/",
      {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
          Accept: "text/html,application/xhtml+xml",
        },
        signal: controller.signal,
      },
    );

    if (!res.ok) {
      console.warn(`Panama Canal page returned ${res.status}`);
      return [];
    }

    const html = await res.text();
    return parseOperationsPage(html);
  } finally {
    clearTimeout(timeout);
  }
}

function parseOperationsPage(html: string): CanalDayRecord[] {
  const records: CanalDayRecord[] = [];

  // Extract draft restriction
  const draftPattern = /(?:draft|TFW)\s*[:=]?\s*(\d{1,2}(?:\.\d+)?)\s*(?:feet|ft|')/gi;
  const draftMatch = draftPattern.exec(html);
  const globalDraftFt = draftMatch ? parseFloat(draftMatch[1]) : null;

  // Extract advisory/restriction text
  const advisoryPatterns = [
    /(?:advisory|restriction|notice)[:\s]*([^<]{10,200})/gi,
    /(?:draft\s+(?:limit|restriction))[:\s]*([^<]{10,200})/gi,
  ];

  let advisoryText: string | null = null;
  for (const pattern of advisoryPatterns) {
    const match = pattern.exec(html);
    if (match) {
      advisoryText = match[1].replace(/\s+/g, " ").trim();
      break;
    }
  }

  // Parse table rows for transit data
  const rowPattern = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
  let rowMatch;

  while ((rowMatch = rowPattern.exec(html)) !== null) {
    const rowHtml = rowMatch[1];
    const tdPattern = /<td[^>]*>([\s\S]*?)<\/td>/gi;
    const cells: string[] = [];
    let tdMatch;
    while ((tdMatch = tdPattern.exec(rowHtml)) !== null) {
      cells.push(tdMatch[1].replace(/<[^>]+>/g, "").trim());
    }

    if (cells.length < 2) continue;

    const firstCell = cells[0];
    const dateMatch = firstCell.match(
      /(\d{4}-\d{2}-\d{2}|\d{1,2}\/\d{1,2}\/\d{2,4}|\w+ \d{1,2},?\s*\d{4})/,
    );

    if (dateMatch) {
      let eventDate: string;
      try {
        const d = new Date(dateMatch[1]);
        if (isNaN(d.getTime())) continue;
        eventDate = d.toISOString().split("T")[0];
      } catch {
        continue;
      }

      const numbers = cells
        .slice(1)
        .map((c) => parseInt(c.replace(/,/g, ""), 10))
        .filter((n) => Number.isFinite(n));

      if (numbers.length >= 1) {
        records.push({
          eventDate,
          transitsPanamax: numbers[0] ?? null,
          transitsNeopanamax: numbers[1] ?? null,
          transitsTotal:
            numbers.length >= 3
              ? numbers[2]
              : numbers[0] + (numbers[1] ?? 0),
          maxDraftFt: globalDraftFt,
          bookingSlots: numbers.length >= 4 ? numbers[3] : null,
          advisoryText,
        });
      }
    }
  }

  // If no table data, still capture advisory
  if (records.length === 0 && advisoryText) {
    const today = new Date().toISOString().split("T")[0];
    records.push({
      eventDate: today,
      transitsPanamax: null,
      transitsNeopanamax: null,
      transitsTotal: null,
      maxDraftFt: globalDraftFt,
      bookingSlots: null,
      advisoryText,
    });
  }

  return records;
}

async function fetchACPAdvisories(): Promise<CanalDayRecord[]> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);

  try {
    const res = await fetch(
      "https://www.pancanal.com/en/maritime-services/advisories-to-shipping/",
      {
        headers: {
          "User-Agent": "Mozilla/5.0 (compatible; ZINC-Fusion/1.0)",
          Accept: "text/html",
        },
        signal: controller.signal,
      },
    );

    if (!res.ok) return [];

    const html = await res.text();
    const records: CanalDayRecord[] = [];
    const advisoryPattern =
      /<a[^>]*href="([^"]*advisory[^"]*)"[^>]*>([^<]+)<\/a>/gi;
    let match;

    while ((match = advisoryPattern.exec(html)) !== null) {
      const title = match[2].trim();
      const dateMatch = title.match(
        /(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\w+ \d{1,2},?\s*\d{4})/,
      );

      if (dateMatch) {
        try {
          const d = new Date(dateMatch[1]);
          if (!isNaN(d.getTime())) {
            records.push({
              eventDate: d.toISOString().split("T")[0],
              transitsPanamax: null,
              transitsNeopanamax: null,
              transitsTotal: null,
              maxDraftFt: null,
              bookingSlots: null,
              advisoryText: title,
            });
          }
        } catch {
          // skip
        }
      }
    }

    return records.slice(0, 10);
  } finally {
    clearTimeout(timeout);
  }
}

// ---------------------------------------------------------------------------
// Inngest Function
// ---------------------------------------------------------------------------

export const panamaCanalDaily = inngest.createFunction(
  {
    id: "panama-canal-daily",
    name: "Panama Canal Operations Daily",
    retries: 2,
    concurrency: [DB_CONCURRENCY],
  },
  [{ cron: "0 14 * * *" }, { event: "panama/canal-daily" }],
  async ({ step, logger }) => {
    logger.info("Fetching Panama Canal daily operations");

    await step.run("assert-table-contract", async () => {
      const client = await pool.connect();
      try {
        const { rows } = await client.query<{
          regclass_name: string | null;
        }>(`SELECT to_regclass('supply.panama_canal_1d')::text AS regclass_name`);
        if (!rows[0]?.regclass_name) {
          throw new Error(
            "Missing table supply.panama_canal_1d. Apply Prisma migrations before running panama-canal-daily."
          );
        }
      } finally {
        client.release();
      }
    });

    const opsRecords = await step.run("scrape-operations", async () => {
      return scrapePanamaCanal();
    });

    const advisoryRecords = await step.run("fetch-advisories", async () => {
      return fetchACPAdvisories();
    });

    // Merge: ops takes priority, supplement with advisories
    const allRecords = [...opsRecords];
    const seenDates = new Set(opsRecords.map((r) => r.eventDate));

    for (const adv of advisoryRecords) {
      if (!seenDates.has(adv.eventDate)) {
        allRecords.push(adv);
        seenDates.add(adv.eventDate);
      } else {
        const existing = allRecords.find((r) => r.eventDate === adv.eventDate);
        if (existing && adv.advisoryText && !existing.advisoryText) {
          existing.advisoryText = adv.advisoryText;
        }
      }
    }

    logger.info(
      `Panama Canal: ${opsRecords.length} ops + ${advisoryRecords.length} advisories → ${allRecords.length} total`,
    );

    const result = await step.run("upsert-panama-data", async () => {
      const client = await pool.connect();
      let inserted = 0;
      let skipped = 0;

      try {
        for (const record of allRecords) {
          const rowHash = createHash("sha256")
            .update(
              `${record.eventDate}|${record.transitsTotal}|${record.maxDraftFt}|${record.advisoryText?.slice(0, 50)}`,
            )
            .digest("hex");

          const existing = await client.query(
            `SELECT row_hash FROM supply.panama_canal_1d WHERE event_date = $1`,
            [record.eventDate],
          );

          if (existing.rows.length > 0 && existing.rows[0].row_hash === rowHash) {
            skipped++;
            continue;
          }

          await client.query(
            `INSERT INTO supply.panama_canal_1d
              (event_date, transits_panamax, transits_neopanamax, transits_total,
               max_draft_ft, booking_slots, advisory_text, source, row_hash, ingested_at)
             VALUES ($1, $2, $3, $4, $5, $6, $7, 'pancanal', $8, NOW())
             ON CONFLICT (event_date) DO UPDATE SET
               transits_panamax = COALESCE(EXCLUDED.transits_panamax, supply.panama_canal_1d.transits_panamax),
               transits_neopanamax = COALESCE(EXCLUDED.transits_neopanamax, supply.panama_canal_1d.transits_neopanamax),
               transits_total = COALESCE(EXCLUDED.transits_total, supply.panama_canal_1d.transits_total),
               max_draft_ft = COALESCE(EXCLUDED.max_draft_ft, supply.panama_canal_1d.max_draft_ft),
               booking_slots = COALESCE(EXCLUDED.booking_slots, supply.panama_canal_1d.booking_slots),
               advisory_text = COALESCE(EXCLUDED.advisory_text, supply.panama_canal_1d.advisory_text),
               row_hash = EXCLUDED.row_hash,
               ingested_at = NOW()`,
            [
              record.eventDate,
              record.transitsPanamax,
              record.transitsNeopanamax,
              record.transitsTotal,
              record.maxDraftFt,
              record.bookingSlots,
              record.advisoryText,
              rowHash,
            ],
          );
          inserted++;
        }

        return { inserted, skipped };
      } finally {
        client.release();
      }
    });

    logger.info(`Panama Canal: inserted=${result.inserted}, skipped=${result.skipped}`);

    return {
      status: "success",
      source: "pancanal.com",
      opsRecords: opsRecords.length,
      advisoryRecords: advisoryRecords.length,
      ...result,
    };
  },
);
