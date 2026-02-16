/**
 * CFTC Weekly Commitments of Traders (Disaggregated Futures) Data Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Append-only inserts (no upserts)
 *
 * SOURCE: https://publicreporting.cftc.gov/resource/72hh-3qpy.json
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.1.0
 * @date 2026-02-16
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

// PoolClient helper functions removed — SQL inlined inside step.run() closures
// to prevent stale connections across Inngest durable execution boundaries.

const CFTC_SOURCE_URL =
  "https://publicreporting.cftc.gov/resource/72hh-3qpy.json?$order=report_date_as_yyyy_mm_dd%20DESC&$limit=500";

function computeRowHash(payload: Record<string, unknown>): string {
  return createHash("sha256").update(JSON.stringify(payload)).digest("hex");
}

// CFTC contract codes for key commodities
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

export const cftcWeekly = inngest.createFunction(
  { id: "cftc-weekly", name: "CFTC Weekly COT", retries: 3, concurrency: [DB_CONCURRENCY] },
  { cron: "0 21 * * 5" }, // 4PM ET = 9PM UTC, Fridays only
  async ({ step, logger }) => {
    // ── Step 1: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["cftc-weekly"]
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    logger.info(`Started ingest run: ${runId}`);

    // ── Step 2: fetch from CFTC API ──
    const data = await step.run("fetch-cftc", async () => {
      const res = await fetch(CFTC_SOURCE_URL, {
        headers: { "User-Agent": "ZINC-Fusion/1.0" },
      });
      if (!res.ok) {
        throw new Error(`Failed to fetch CFTC data: ${res.status}`);
      }
      const json = await res.json();
      if (!Array.isArray(json)) {
        throw new Error("Unexpected CFTC response format (expected array)");
      }
      return json as Record<string, string>[];
    });

    // ── Step 3: process each contract ──
    const contractResults: { symbol: string; status: string; date?: string; attempted: number; inserted: number; skipped: number }[] = [];

    for (const contract of CFTC_CONTRACTS) {
      const outcome = await step.run(`ingest-${contract.symbol}`, async () => {
        let attempted = 0, inserted = 0, skipped = 0;

        // Find rows for this contract
        const contractRows = data.filter(
          (row) =>
            row.cftc_contract_market_code === contract.code ||
            row.contract_market_name?.toLowerCase().includes(contract.name.toLowerCase())
        );

        if (contractRows.length === 0) {
          return { symbol: contract.symbol, status: "not_found" as const, attempted: 0, inserted: 0, skipped: 0 };
        }

        const recent = contractRows
          .filter((r) => r.report_date_as_yyyy_mm_dd)
          .sort((a, b) =>
            String(b.report_date_as_yyyy_mm_dd).localeCompare(String(a.report_date_as_yyyy_mm_dd))
          )
          .slice(0, 10);

        const client = await pool.connect();
        try {
          for (const row of recent) {
            const reportDate = row.report_date_as_yyyy_mm_dd;
            if (!reportDate) continue;

            const openInterest = parseInt(row.open_interest_all || "0");
            const managedLong = parseInt(row.m_money_positions_long_all || "0");
            const managedShort = parseInt(row.m_money_positions_short_all || "0");
            const prodMercLong = parseInt(row.prod_merc_positions_long_all || "0");
            const prodMercShort = parseInt(row.prod_merc_positions_short_all || "0");
            const swapLong = parseInt(row.swap_positions_long_all || "0");
            const swapShort = parseInt(row.swap_positions_short_all || "0");
            const otherLong = parseInt(row.other_rept_positions_long_all || "0");
            const otherShort = parseInt(row.other_rept_positions_short_all || "0");
            const nonreptLong = parseInt(row.nonrept_positions_long_all || "0");
            const nonreptShort = parseInt(row.nonrept_positions_short_all || "0");

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
              managed_money_net_pct_oi: openInterest > 0 ? (managedNet / openInterest) * 100 : 0,
              prod_merc_net_pct_oi: openInterest > 0 ? (prodMercNet / openInterest) * 100 : 0,
              source: "cftc_api",
            };

            const rowHash = computeRowHash(payload);
            attempted++;

            const existsSymbol = await client.query(
              `SELECT 1 FROM pos.cftc_1w WHERE event_date=$1::date AND symbol=$2 LIMIT 1`,
              [reportDate, contract.symbol]
            );
            if (existsSymbol.rows.length > 0) {
              skipped++;
              continue;
            }

            const existsHash = await client.query(
              `SELECT 1 FROM pos.cftc_1w WHERE row_hash=$1 LIMIT 1`,
              [rowHash]
            );
            if (existsHash.rows.length > 0) {
              skipped++;
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
                payload.managed_money_net_pct_oi, payload.prod_merc_net_pct_oi,
                "cftc_api", rowHash,
              ]
            );
            inserted++;
          }
        } finally {
          client.release();
        }

        return {
          symbol: contract.symbol,
          status: "success" as const,
          date: recent[0]?.report_date_as_yyyy_mm_dd,
          attempted,
          inserted,
          skipped,
        };
      });

      contractResults.push(outcome);
    }

    // Aggregate counters
    let totalAttempted = 0, totalInserted = 0, totalSkipped = 0;
    for (const r of contractResults) {
      totalAttempted += r.attempted;
      totalInserted += r.inserted;
      totalSkipped += r.skipped;
    }

    // ── Step 4: finalize ingest run ──
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", totalAttempted, totalInserted, totalSkipped, 0]
        );
      } finally {
        client.release();
      }
    });

    logger.info(`Completed: ${totalInserted} inserted, ${totalSkipped} skipped`);

    return {
      status: "complete",
      runId,
      date: new Date().toISOString().split("T")[0],
      inserted: totalInserted,
      skipped: totalSkipped,
      results: contractResults.map(r => ({ symbol: r.symbol, status: r.status, date: r.date })),
      successCount: contractResults.filter((r) => r.status === "success").length,
      errorCount: contractResults.filter((r) => r.status !== "success").length,
    };
  }
);
