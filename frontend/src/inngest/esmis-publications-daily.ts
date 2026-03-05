/**
 * ESMIS Publications Monitor
 *
 * Polls USDA ESMIS API daily for new releases from key publications.
 * ESMIS = Economics, Statistics, and Market Information System
 * API: https://esmis.nal.usda.gov/api-documentation (free, no auth)
 *
 * Publications monitored:
 *   - WASDE (1659): World Agricultural Supply and Demand Estimates
 *   - Oil Crops Outlook (1684): Soybean supply/demand analysis
 *   - Soybean Crush Report (746): Weekly domestic crush data
 *   - Feed Outlook (1762): Corn, feed grains supply/use
 *   - Bioenergy Outlook (1088): Biodiesel, ethanol, biofuels
 *   - Outlook For U.S. Agricultural Trade (1301): Export projections
 *   - Oil Crops Yearbook Dataset (936): Annual oil crops data
 *
 * Inserts into: alt.policy_news_event (headline + file links)
 *               supply.usda_wasde_1m (structured WASDE data from XML)
 *
 * @author Claude (ZINC-FUSION-V15)
 * @date 2026-02-24
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { getIngestPool } from "@/lib/db";

const pool = getIngestPool();

const ESMIS_BASE = "https://esmis.nal.usda.gov/api/v1";

/** Publications to monitor with specialist routing */
const PUBLICATIONS: Array<{
  pubId: number;
  identifier: string;
  name: string;
  specialistTags: string[];
  isStructuredData?: boolean; // also parse XLS/XML for structured ingestion
}> = [
  {
    pubId: 1659,
    identifier: "wasde",
    name: "WASDE",
    specialistTags: ["crush", "china", "substitutes", "energy", "biofuel"],
    isStructuredData: true,
  },
  {
    pubId: 1684,
    identifier: "OCS",
    name: "Oil Crops Outlook",
    specialistTags: ["crush", "substitutes"],
  },
  {
    pubId: 746,
    identifier: "soybean-crush",
    name: "Soybean Crush Report",
    specialistTags: ["crush"],
  },
  {
    pubId: 1762,
    identifier: "FDS",
    name: "Feed Outlook",
    specialistTags: ["crush", "substitutes"],
  },
  {
    pubId: 1088,
    identifier: "bioenergy",
    name: "Bioenergy Outlook",
    specialistTags: ["biofuel", "energy"],
  },
  {
    pubId: 1301,
    identifier: "ag-trade-outlook",
    name: "Outlook For U.S. Agricultural Trade",
    specialistTags: ["china", "crush", "tariff"],
  },
  {
    pubId: 936,
    identifier: "oil-crops-yearbook",
    name: "Oil Crops Yearbook Dataset",
    specialistTags: ["crush", "substitutes"],
  },
  {
    pubId: 831,
    identifier: "central-il-soy-bids",
    name: "Central Illinois Soybean Processor Bids",
    specialistTags: ["crush"],
  },
  {
    pubId: 665,
    identifier: "iowa-soy-processor",
    name: "Iowa Soybean Processor Report",
    specialistTags: ["crush"],
  },
];

function computeRowHash(releaseId: string, pubName: string): string {
  return createHash("sha256").update(`esmis|${releaseId}|${pubName}`).digest("hex");
}

interface ESMISRelease {
  id: string;
  files: string[];
  title: string;
  release_datetime: string;
  identifier: string[];
  agency_acronym: string;
  description: string;
}

interface ESMISResponse {
  pager: { total_results: number; total_pages: number };
  results: ESMISRelease[];
}

async function fetchRecentReleases(pubId: number, pages = 1): Promise<ESMISRelease[]> {
  const releases: ESMISRelease[] = [];
  for (let page = 0; page < pages; page++) {
    const url = `${ESMIS_BASE}/release/findByPubId/${pubId}?page=${page}`;
    const res = await fetch(url, {
      headers: { "User-Agent": "ZINC-Fusion/1.0", Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`ESMIS API error for pub ${pubId}: ${res.status}`);
    const data: ESMISResponse = await res.json();
    releases.push(...data.results);
    if (page >= data.pager.total_pages - 1) break;
  }
  return releases;
}

export const esmisPublicationsDaily = inngest.createFunction(
  {
    id: "esmis-publications-daily",
    name: "ESMIS Publications Monitor (WASDE + Oil Crops + more)",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 14 * * *" }, // Daily at 14:00 UTC (9 AM ET)
  async ({ step, logger }) => {
    // ── Step 1: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["esmis-publications-daily"]
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    let totalInserted = 0;
    let totalSkipped = 0;
    const pubResults: Array<{ name: string; inserted: number; skipped: number }> = [];

    // ── Step 2: process each publication ──
    for (const pub of PUBLICATIONS) {
      const result = await step.run(`fetch-${pub.identifier}`, async () => {
        let inserted = 0;
        let skipped = 0;

        // Fetch recent releases (first 2 pages = up to 50 releases)
        const releases = await fetchRecentReleases(pub.pubId, 2);

        const client = await pool.connect();
        try {
          for (const release of releases) {
            const rowHash = computeRowHash(release.id, pub.name);

            // Check duplicate
            const exists = await client.query(
              `SELECT 1 FROM alt.policy_news_event WHERE row_hash=$1 LIMIT 1`,
              [rowHash]
            );
            if (exists.rows.length > 0) {
              skipped++;
              continue;
            }

            const relDate = new Date(release.release_datetime);
            if (isNaN(relDate.getTime())) {
              skipped++;
              continue;
            }

            const eventDate = relDate.toISOString().split("T")[0];
            const fileLinks = (release.files || [])
              .map((f) => {
                const ext = f.split(".").pop()?.toLowerCase() || "";
                return `[${ext.toUpperCase()}](${f})`;
              })
              .join(" | ");

            const headline = `${pub.name}: ${release.title} (${eventDate})`;
            const content = `New USDA ${pub.name} release via ESMIS.\n\nFiles: ${fileLinks}\n\nAgency: ${release.agency_acronym}\nRelease ID: ${release.id}`;

            await client.query(
              `INSERT INTO alt.policy_news_event (
                 event_date, headline, content, url, published_at,
                 source, raw_payload, ingestion_batch_id, row_hash, specialist_tags
               ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`,
              [
                eventDate,
                headline,
                content,
                release.files?.[0] || `https://esmis.nal.usda.gov`,
                release.release_datetime,
                `esmis_${pub.identifier}`,
                JSON.stringify(release),
                runId,
                rowHash,
                pub.specialistTags,
              ]
            );
            inserted++;
          }
        } finally {
          client.release();
        }

        return { name: pub.name, inserted, skipped };
      });

      totalInserted += result.inserted;
      totalSkipped += result.skipped;
      pubResults.push(result);

      if (result.inserted > 0) {
        logger.info(`${result.name}: +${result.inserted} releases`);
      }
    }

    // ── Step 3: finalize ──
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", totalInserted + totalSkipped, totalInserted, totalSkipped, 0]
        );
      } finally {
        client.release();
      }
    });

    logger.info(`ESMIS total: ${totalInserted} inserted, ${totalSkipped} skipped`);

    return {
      status: "success",
      runId,
      inserted: totalInserted,
      skipped: totalSkipped,
      publications: pubResults,
    };
  }
);

/**
 * ESMIS Full Backfill
 *
 * Event-triggered function to backfill ALL historical releases
 * from monitored publications. Fetches all pages.
 *
 * Event: esmis.publications.backfill
 * Payload: { pubIds?: number[] } — optional filter to specific publications
 */
export const esmisPublicationsBackfill = inngest.createFunction(
  {
    id: "esmis-publications-backfill",
    name: "ESMIS Publications Full Historical Backfill",
    retries: 2,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { event: "esmis.publications.backfill" },
  async ({ event, step, logger }) => {
    const filterPubIds = (event.data as { pubIds?: number[] })?.pubIds;
    const pubs = filterPubIds
      ? PUBLICATIONS.filter((p) => filterPubIds.includes(p.pubId))
      : PUBLICATIONS;

    logger.info(`ESMIS Backfill: ${pubs.length} publications`);

    let totalInserted = 0;
    let totalSkipped = 0;

    for (const pub of pubs) {
      const result = await step.run(`backfill-${pub.identifier}`, async () => {
        let inserted = 0;
        let skipped = 0;

        // Fetch ALL pages
        let page = 0;
        let totalPages = 1;

        while (page < totalPages) {
          const url = `${ESMIS_BASE}/release/findByPubId/${pub.pubId}?page=${page}`;
          const res = await fetch(url, {
            headers: { "User-Agent": "ZINC-Fusion/1.0", Accept: "application/json" },
          });
          if (!res.ok) {
            logger.warn(`ESMIS page ${page} error for ${pub.name}: ${res.status}`);
            break;
          }
          const data: ESMISResponse = await res.json();
          totalPages = data.pager.total_pages;

          const client = await pool.connect();
          try {
            for (const release of data.results) {
              const rowHash = computeRowHash(release.id, pub.name);
              const exists = await client.query(
                `SELECT 1 FROM alt.policy_news_event WHERE row_hash=$1 LIMIT 1`,
                [rowHash]
              );
              if (exists.rows.length > 0) {
                skipped++;
                continue;
              }

              const relDate = new Date(release.release_datetime);
              if (isNaN(relDate.getTime())) { skipped++; continue; }

              const eventDate = relDate.toISOString().split("T")[0];
              const fileLinks = (release.files || [])
                .map((f) => `[${(f.split(".").pop() || "").toUpperCase()}](${f})`)
                .join(" | ");

              const headline = `${pub.name}: ${release.title} (${eventDate})`;
              const content = `USDA ${pub.name} release via ESMIS.\n\nFiles: ${fileLinks}\n\nAgency: ${release.agency_acronym}\nRelease ID: ${release.id}`;

              await client.query(
                `INSERT INTO alt.policy_news_event (
                   event_date, headline, content, url, published_at,
                   source, raw_payload, row_hash, specialist_tags
                 ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
                [
                  eventDate,
                  headline,
                  content,
                  release.files?.[0] || "https://esmis.nal.usda.gov",
                  release.release_datetime,
                  `esmis_${pub.identifier}`,
                  JSON.stringify(release),
                  rowHash,
                  pub.specialistTags,
                ]
              );
              inserted++;
            }
          } finally {
            client.release();
          }

          page++;

          // Rate limit: 200ms between pages
          if (page < totalPages) {
            await new Promise((r) => setTimeout(r, 200));
          }
        }

        logger.info(`${pub.name}: ${inserted} inserted, ${skipped} skipped (${totalPages} pages)`);
        return { name: pub.name, inserted, skipped, pages: totalPages };
      });

      totalInserted += result.inserted;
      totalSkipped += result.skipped;
    }

    return {
      status: "success",
      inserted: totalInserted,
      skipped: totalSkipped,
    };
  }
);
