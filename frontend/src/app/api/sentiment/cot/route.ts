import { NextResponse } from "next/server";
import { query } from "@/lib/db";

export const dynamic = "force-dynamic";

interface CotRow {
  event_date: string;
  symbol: string;
  open_interest: string | null;
  managed_money_long: string | null;
  managed_money_short: string | null;
  managed_money_net: string | null;
  prod_merc_long: string | null;
  prod_merc_short: string | null;
  prod_merc_net: string | null;
  swap_long: string | null;
  swap_short: string | null;
  swap_net: string | null;
  managed_money_net_pct_oi: number | null;
  prod_merc_net_pct_oi: number | null;
}

/**
 * GET /api/sentiment/cot
 * Returns the latest CFTC COT positioning for ZL (soybean oil)
 * plus a short history for sparklines / trend analysis.
 */
export async function GET() {
  try {
    const [latestRows, historyRows] = await Promise.all([
      // Latest COT report for ZL
      query<CotRow>(`
        SELECT
          event_date::text,
          symbol,
          open_interest::text,
          managed_money_long::text,
          managed_money_short::text,
          managed_money_net::text,
          prod_merc_long::text,
          prod_merc_short::text,
          prod_merc_net::text,
          swap_long::text,
          swap_short::text,
          swap_net::text,
          managed_money_net_pct_oi::float8,
          prod_merc_net_pct_oi::float8
        FROM pos.cftc_1w
        WHERE symbol = 'ZL'
        ORDER BY event_date DESC
        LIMIT 1
      `),
      // 12-week history for trend
      query<{
        event_date: string;
        managed_money_net: string;
        prod_merc_net: string;
        swap_net: string;
      }>(`
        SELECT
          event_date::text,
          managed_money_net::text,
          prod_merc_net::text,
          swap_net::text
        FROM pos.cftc_1w
        WHERE symbol = 'ZL'
        ORDER BY event_date DESC
        LIMIT 12
      `),
    ]);

    if (latestRows.length === 0) {
      return NextResponse.json(
        { error: "No COT data found for ZL" },
        { status: 404 },
      );
    }

    const latest = latestRows[0];

    // Compute managed money positioning as % of open interest for bar display
    const oi = Number(latest.open_interest) || null;
    const mmNet = Number(latest.managed_money_net) || 0;
    const pmNet = Number(latest.prod_merc_net) || 0;
    const swNet = Number(latest.swap_net) || 0;

    return NextResponse.json(
      {
        as_of_date: latest.event_date,
        symbol: "ZL",
        latest: {
          open_interest: Number(latest.open_interest),
          managed_money: {
            long: Number(latest.managed_money_long),
            short: Number(latest.managed_money_short),
            net: mmNet,
            net_pct_oi: latest.managed_money_net_pct_oi ?? (oi ? (mmNet / oi) * 100 : null),
          },
          producers: {
            long: Number(latest.prod_merc_long),
            short: Number(latest.prod_merc_short),
            net: pmNet,
            net_pct_oi: latest.prod_merc_net_pct_oi ?? (oi ? (pmNet / oi) * 100 : null),
          },
          swaps: {
            long: Number(latest.swap_long),
            short: Number(latest.swap_short),
            net: swNet,
            net_pct_oi: oi ? (swNet / oi) * 100 : null,
          },
        },
        history: historyRows
          .map((r) => ({
            event_date: r.event_date,
            managed_money_net: Number(r.managed_money_net),
            prod_merc_net: Number(r.prod_merc_net),
            swap_net: Number(r.swap_net),
          }))
          .reverse(),
      },
      {
        headers: {
          "Cache-Control": "s-maxage=600, stale-while-revalidate=1200",
        },
      },
    );
  } catch (error) {
    console.error("[/api/sentiment/cot] Error:", error);
    return NextResponse.json(
      { error: "Failed to fetch COT data", details: String(error) },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
