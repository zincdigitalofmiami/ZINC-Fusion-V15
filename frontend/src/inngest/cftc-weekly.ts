import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import pool from "@/lib/db";
import type { PoolClient } from "pg";

const CFTC_SOURCE_URL =
  "https://publicreporting.cftc.gov/resource/72hh-3qpy.json?$order=report_date_as_yyyy_mm_dd%20DESC&$limit=500";

function computeRowHash(payload: Record<string, unknown>): string {
  return createHash("sha256").update(JSON.stringify(payload)).digest("hex");
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

async function rowHashExists(client: PoolClient, rowHash: string): Promise<boolean> {
  const r = await client.query(`SELECT 1 FROM pos.cftc_1w WHERE row_hash=$1 LIMIT 1`, [
    rowHash,
  ]);
  return r.rows.length > 0;
}

async function eventSymbolExists(
  client: PoolClient,
  eventDate: string,
  symbol: string
): Promise<boolean> {
  const r = await client.query(
    `SELECT 1 FROM pos.cftc_1w WHERE event_date=$1::date AND symbol=$2 LIMIT 1`,
    [eventDate, symbol]
  );
  return r.rows.length > 0;
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

/**
 * Fetch weekly CFTC Commitments of Traders data
 * Runs every Friday at 4:00 PM ET (after CFTC release)
 */
export const cftcWeekly = inngest.createFunction(
  { id: "cftc-weekly", name: "CFTC Weekly COT", retries: 3, concurrency: [{ limit: 1 }] },
  { cron: "0 21 * * 5" }, // 4PM ET = 9PM UTC, Fridays only
  async ({ step, logger }) => {
    const results: { symbol: string; status: string; date?: string }[] = [];
    const client = await pool.connect();
    let runId: string | null = null;
    let rowsAttempted = 0;
    let rowsInserted = 0;
    let rowsSkipped = 0;
    let rowsQuarantined = 0;

    try {
      runId = await step.run("create-ingest-run", () => createIngestRun(client, "cftc-weekly"));
      logger.info(`Started ingest run: ${runId}`);

      // Fetch from CFTC API (Disaggregated Futures)
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

      // Process each contract
      for (const contract of CFTC_CONTRACTS) {
        await step.run(`ingest-${contract.symbol}`, async () => {
          // Find rows for this contract
          const contractRows = data.filter(
            (row) =>
              row.cftc_contract_market_code === contract.code ||
              row.contract_market_name?.toLowerCase().includes(contract.name.toLowerCase())
          );

          if (contractRows.length === 0) {
            results.push({ symbol: contract.symbol, status: "not_found" });
            return;
          }

          const recent = contractRows
            .filter((r) => r.report_date_as_yyyy_mm_dd)
            .sort((a, b) =>
              String(b.report_date_as_yyyy_mm_dd).localeCompare(String(a.report_date_as_yyyy_mm_dd))
            )
            .slice(0, 10); // Last ~10 weeks

          for (const row of recent) {
            const reportDate = row.report_date_as_yyyy_mm_dd;
            if (!reportDate) continue;

            const openInterest = parseInt(row.open_interest_all || "0");

            // Parse Disaggregated data fields
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
            rowsAttempted++;

            if (await eventSymbolExists(client, reportDate, contract.symbol)) {
              rowsSkipped++;
              continue;
            }

            if (await rowHashExists(client, rowHash)) {
              rowsSkipped++;
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
                reportDate,
                contract.symbol,
                openInterest,
                managedLong,
                managedShort,
                managedNet,
                prodMercLong,
                prodMercShort,
                prodMercNet,
                swapLong,
                swapShort,
                swapNet,
                otherLong,
                otherShort,
                otherNet,
                nonreptLong,
                nonreptShort,
                nonreptNet,
                payload.managed_money_net_pct_oi,
                payload.prod_merc_net_pct_oi,
                "cftc_api",
                rowHash,
              ]
            );
            rowsInserted++;
          }

          results.push({
            symbol: contract.symbol,
            status: "success",
            date: recent[0]?.report_date_as_yyyy_mm_dd,
          });
        });
      }

      await step.run("complete", () =>
        updateIngestRun(
          client,
          runId!,
          "success",
          rowsAttempted,
          rowsInserted,
          rowsSkipped,
          rowsQuarantined
        )
      );

      return {
        status: "complete",
        runId,
        date: new Date().toISOString().split("T")[0],
        inserted: rowsInserted,
        skipped: rowsSkipped,
        results,
        successCount: results.filter((r) => r.status === "success").length,
        errorCount: results.filter((r) => r.status !== "success").length,
      };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      if (runId) {
        await updateIngestRun(
          client,
          runId,
          "failed",
          rowsAttempted,
          rowsInserted,
          rowsSkipped,
          rowsQuarantined,
          msg
        );
      }
      throw error;
    } finally {
      client.release();
    }
  }
);
