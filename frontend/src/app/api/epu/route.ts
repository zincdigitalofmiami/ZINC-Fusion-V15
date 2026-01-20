import { NextRequest, NextResponse } from "next/server";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

/**
 * EPU Factor Thresholds (from refresh_trump_effect_features.py)
 * Used for classification and visualization
 */
const EPU_THRESHOLDS = {
  low: 80, // Below 80 = calm policy environment
  normal: 120, // 80-120 = typical uncertainty
  elevated: 160, // 120-160 = elevated uncertainty
  crisis: 200, // Above 200 = crisis-level uncertainty
};

const VIX_THRESHOLDS = {
  calm: 15,
  normal: 20,
  elevated: 25,
  stress: 35,
};

/**
 * Calculate EPU factor (0.8 to 1.5 scale)
 */
function calculateEpuFactor(epuValue: number | null): number {
  if (epuValue === null) return 1.0;

  if (epuValue < EPU_THRESHOLDS.low) return 0.8;
  if (epuValue < EPU_THRESHOLDS.normal) return 1.0;
  if (epuValue < EPU_THRESHOLDS.elevated) {
    const pct =
      (epuValue - EPU_THRESHOLDS.normal) /
      (EPU_THRESHOLDS.elevated - EPU_THRESHOLDS.normal);
    return 1.0 + 0.3 * pct;
  }
  if (epuValue < EPU_THRESHOLDS.crisis) {
    const pct =
      (epuValue - EPU_THRESHOLDS.elevated) /
      (EPU_THRESHOLDS.crisis - EPU_THRESHOLDS.elevated);
    return 1.3 + 0.2 * pct;
  }
  return 1.5;
}

/**
 * Classify EPU level for visualization
 */
function classifyEpuLevel(
  epuValue: number | null
): "low" | "normal" | "elevated" | "crisis" | "unknown" {
  if (epuValue === null) return "unknown";
  if (epuValue < EPU_THRESHOLDS.low) return "low";
  if (epuValue < EPU_THRESHOLDS.normal) return "normal";
  if (epuValue < EPU_THRESHOLDS.elevated) return "elevated";
  return "crisis";
}

/**
 * GET /api/epu
 *
 * Policy Uncertainty Factor API - Primary chart endpoint
 *
 * Returns EPU data with neural factors for charting:
 * - US Economic Policy Uncertainty Index (USEPUINDXD)
 * - China Trade Policy Uncertainty (CHNMAINLANDTPU)
 * - VIX for market stress context
 * - ZL prices for correlation
 * - Calculated neural factors
 *
 * Query params:
 * - days: number of days back (default 365, max 3650)
 * - series: 'all' | 'us' | 'china' (default 'all')
 * - include_zl: boolean - include ZL price overlay (default true)
 * - include_vix: boolean - include VIX overlay (default true)
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const days = Math.max(30, Math.min(parseInt(searchParams.get("days") || "365", 10), 3650));
    const series = searchParams.get("series") || "all";
    const includeZl = searchParams.get("include_zl") !== "false";
    const includeVix = searchParams.get("include_vix") !== "false";

    // Fetch US EPU (daily)
    const epuResult = await pool.query(
      `SELECT
        event_date,
        value as epu_value,
        series_id
      FROM econ.activity_1d
      WHERE series_id = 'USEPUINDXD'
        AND event_date >= CURRENT_DATE - $1::interval
      ORDER BY event_date ASC`,
      [`${days} days`]
    );

    // Fetch China TPU if requested
    let chinaTpuData: Record<string, number> = {};
    if (series === "all" || series === "china") {
      const chinaTpuResult = await pool.query(
        `SELECT
          event_date,
          value as china_tpu_value
        FROM econ.activity_1d
        WHERE series_id = 'CHNMAINLANDTPU'
          AND event_date >= CURRENT_DATE - $1::interval
        ORDER BY event_date ASC`,
        [`${days} days`]
      );
      chinaTpuData = Object.fromEntries(
        chinaTpuResult.rows.map((r) => [
          r.event_date.toISOString().split("T")[0],
          parseFloat(r.china_tpu_value),
        ])
      );
    }

    // Fetch VIX if requested
    let vixData: Record<string, number> = {};
    if (includeVix) {
      const vixResult = await pool.query(
        `SELECT
          event_date,
          value as vix_value
        FROM econ.vol_indices_1d
        WHERE series_id = 'VIXCLS'
          AND event_date >= CURRENT_DATE - $1::interval
        ORDER BY event_date ASC`,
        [`${days} days`]
      );
      vixData = Object.fromEntries(
        vixResult.rows.map((r) => [
          r.event_date.toISOString().split("T")[0],
          parseFloat(r.vix_value),
        ])
      );
    }

    // Fetch ZL prices if requested
    let zlData: Record<string, number> = {};
    if (includeZl) {
      const zlResult = await pool.query(
        `SELECT
          event_date,
          close as zl_close
        FROM mkt.futures_1d
        WHERE symbol = 'ZL'
          AND event_date >= CURRENT_DATE - $1::interval
        ORDER BY event_date ASC`,
        [`${days} days`]
      );
      zlData = Object.fromEntries(
        zlResult.rows.map((r) => [
          r.event_date.toISOString().split("T")[0],
          parseFloat(r.zl_close),
        ])
      );
    }

    // Build combined data with neural factors
    const data = epuResult.rows.map((row) => {
      const dateKey = row.event_date.toISOString().split("T")[0];
      const epuValue = parseFloat(row.epu_value);
      const chinaTpu = chinaTpuData[dateKey] || null;
      const vix = vixData[dateKey] || null;
      const zlClose = zlData[dateKey] || null;

      // Calculate neural factors
      const epuFactor = calculateEpuFactor(epuValue);
      const epuLevel = classifyEpuLevel(epuValue);

      return {
        date: dateKey,
        // Core EPU data
        epu: epuValue,
        epu_factor: Math.round(epuFactor * 1000) / 1000,
        epu_level: epuLevel,
        // China TPU (if available)
        china_tpu: chinaTpu,
        // Market context
        vix: vix,
        zl_close: zlClose,
        // Combined stress indicator
        combined_uncertainty:
          chinaTpu !== null
            ? Math.round((epuValue * 0.6 + chinaTpu * 0.4) * 100) / 100
            : epuValue,
      };
    });

    // Calculate summary statistics
    const epuValues = data.map((d) => d.epu).filter((v) => v !== null);
    const recentEpu = epuValues.slice(-30);

    const summary = {
      current: {
        epu: epuValues[epuValues.length - 1] || null,
        epu_factor: data[data.length - 1]?.epu_factor || 1.0,
        epu_level: data[data.length - 1]?.epu_level || "unknown",
        china_tpu: data[data.length - 1]?.china_tpu || null,
        vix: data[data.length - 1]?.vix || null,
        zl_close: data[data.length - 1]?.zl_close || null,
      },
      period: {
        avg_epu: Math.round((epuValues.reduce((a, b) => a + b, 0) / epuValues.length) * 100) / 100,
        max_epu: Math.max(...epuValues),
        min_epu: Math.min(...epuValues),
        avg_30d: Math.round((recentEpu.reduce((a, b) => a + b, 0) / recentEpu.length) * 100) / 100,
      },
      thresholds: EPU_THRESHOLDS,
      vix_thresholds: VIX_THRESHOLDS,
    };

    // Identify crisis periods
    const crisisPeriods = [];
    let inCrisis = false;
    let crisisStart: string | null = null;

    for (const d of data) {
      if (d.epu >= EPU_THRESHOLDS.crisis && !inCrisis) {
        inCrisis = true;
        crisisStart = d.date;
      } else if (d.epu < EPU_THRESHOLDS.crisis && inCrisis) {
        inCrisis = false;
        if (crisisStart) {
          crisisPeriods.push({ start: crisisStart, end: d.date });
        }
      }
    }
    // Handle ongoing crisis
    if (inCrisis && crisisStart) {
      crisisPeriods.push({ start: crisisStart, end: null });
    }

    return NextResponse.json({
      meta: {
        endpoint: "/api/epu",
        description: "Policy Uncertainty Factor - Neural Enhanced",
        series_included: {
          us_epu: true,
          china_tpu: series === "all" || series === "china",
          vix: includeVix,
          zl: includeZl,
        },
        days_requested: days,
        count: data.length,
        last_updated: new Date().toISOString(),
      },
      summary,
      crisis_periods: crisisPeriods,
      data,
    });
  } catch (error) {
    console.error("EPU API error:", error);
    return NextResponse.json(
      {
        error: "Failed to fetch EPU data",
        details: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}
