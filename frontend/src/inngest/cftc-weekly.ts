import { inngest } from "./client";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

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

interface CftcRow {
  Report_Date_as_YYYY_MM_DD: string;
  Open_Interest_All: string;
  NonComm_Positions_Long_All: string;
  NonComm_Positions_Short_All: string;
  Comm_Positions_Long_All: string;
  Comm_Positions_Short_All: string;
  NonRept_Positions_Long_All: string;
  NonRept_Positions_Short_All: string;
}

/**
 * Fetch weekly CFTC Commitments of Traders data
 * Runs every Friday at 4:00 PM ET (after CFTC release)
 */
export const cftcWeekly = inngest.createFunction(
  { id: "cftc-weekly", name: "CFTC Weekly COT" },
  { cron: "0 21 * * 5" }, // 4PM ET = 9PM UTC, Fridays only
  async ({ step }) => {
    const results: { symbol: string; status: string; date?: string }[] = [];

    // Fetch from CFTC API (Disaggregated Futures)
    const data = await step.run("fetch-cftc", async () => {
      try {
        // CFTC Disaggregated Futures - current year
        const res = await fetch(
          "https://publicreporting.cftc.gov/resource/72hh-3qpy.json?$order=report_date_as_yyyy_mm_dd%20DESC&$limit=500"
        );
        return await res.json();
      } catch {
        return null;
      }
    });

    if (!data || !Array.isArray(data)) {
      return { status: "error", message: "Failed to fetch CFTC data" };
    }

    // Process each contract
    for (const contract of CFTC_CONTRACTS) {
      await step.run(`insert-${contract.symbol}`, async () => {
        // Find rows for this contract
        const contractRows = data.filter(
          (row: Record<string, string>) =>
            row.cftc_contract_market_code === contract.code ||
            row.contract_market_name?.toLowerCase().includes(contract.name.toLowerCase())
        );

        if (contractRows.length === 0) {
          results.push({ symbol: contract.symbol, status: "not_found" });
          return;
        }

        const client = await pool.connect();
        try {
          let inserted = 0;
          for (const row of contractRows.slice(0, 10)) {
            // Last 10 weeks
            const reportDate = row.report_date_as_yyyy_mm_dd;
            if (!reportDate) continue;

            const openInterest = parseInt(row.open_interest_all || "0");
            const nonCommLong = parseInt(row.noncomm_positions_long_all || "0");
            const nonCommShort = parseInt(row.noncomm_positions_short_all || "0");
            const commLong = parseInt(row.comm_positions_long_all || "0");
            const commShort = parseInt(row.comm_positions_short_all || "0");

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

            await client.query(
              `INSERT INTO raw.cftc_cot_1w
                (report_date, symbol, open_interest,
                 managed_money_long, managed_money_short, managed_money_net,
                 prod_merc_long, prod_merc_short, prod_merc_net,
                 swap_long, swap_short, swap_net,
                 other_rept_long, other_rept_short, other_rept_net,
                 nonrept_long, nonrept_short, nonrept_net,
                 managed_money_net_pct_oi, prod_merc_net_pct_oi,
                 source, ingested_at)
               VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, 'cftc_api', NOW())
               ON CONFLICT (report_date, symbol) DO UPDATE SET
                 open_interest = EXCLUDED.open_interest,
                 managed_money_long = EXCLUDED.managed_money_long,
                 managed_money_short = EXCLUDED.managed_money_short,
                 managed_money_net = EXCLUDED.managed_money_net,
                 prod_merc_long = EXCLUDED.prod_merc_long,
                 prod_merc_short = EXCLUDED.prod_merc_short,
                 prod_merc_net = EXCLUDED.prod_merc_net,
                 swap_long = EXCLUDED.swap_long,
                 swap_short = EXCLUDED.swap_short,
                 swap_net = EXCLUDED.swap_net,
                 other_rept_long = EXCLUDED.other_rept_long,
                 other_rept_short = EXCLUDED.other_rept_short,
                 other_rept_net = EXCLUDED.other_rept_net,
                 nonrept_long = EXCLUDED.nonrept_long,
                 nonrept_short = EXCLUDED.nonrept_short,
                 nonrept_net = EXCLUDED.nonrept_net,
                 managed_money_net_pct_oi = EXCLUDED.managed_money_net_pct_oi,
                 prod_merc_net_pct_oi = EXCLUDED.prod_merc_net_pct_oi,
                 ingested_at = EXCLUDED.ingested_at`,
              [
                reportDate,
                contract.symbol,
                openInterest,
                managedLong,
                managedShort,
                managedLong - managedShort,
                prodMercLong,
                prodMercShort,
                prodMercLong - prodMercShort,
                swapLong,
                swapShort,
                swapLong - swapShort,
                otherLong,
                otherShort,
                otherLong - otherShort,
                nonreptLong,
                nonreptShort,
                nonreptLong - nonreptShort,
                openInterest > 0 ? ((managedLong - managedShort) / openInterest) * 100 : 0,
                openInterest > 0 ? ((prodMercLong - prodMercShort) / openInterest) * 100 : 0,
              ]
            );
            inserted++;
          }
          results.push({
            symbol: contract.symbol,
            status: "success",
            date: contractRows[0]?.report_date_as_yyyy_mm_dd,
          });
        } catch (error) {
          results.push({ symbol: contract.symbol, status: "error" });
        } finally {
          client.release();
        }
      });
    }

    return {
      status: "complete",
      date: new Date().toISOString().split("T")[0],
      results,
      successCount: results.filter((r) => r.status === "success").length,
      errorCount: results.filter((r) => r.status !== "success").length,
    };
  }
);
