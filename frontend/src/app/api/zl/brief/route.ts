/**
 * ZL Procurement Brief - Consolidated Summary
 *
 * Combines: Live ZL price, 4 driver scores, forecasts at multiple horizons,
 * correlations, and actionable recommendations - all in plain English.
 *
 * Reads from: analytics, forecasts, econ, mkt schemas (NOT vegas.*)
 */

import { NextResponse } from "next/server";
import { query } from "@/lib/db";
import { calculateVixStress } from "@/lib/services/vix-service";
import { calculateCrushPressure } from "@/lib/services/crush-service";
import { calculateChinaTension } from "@/lib/services/china-service";
import { calculateTariffThreat } from "@/lib/services/policy-service";
import { fetchMarketDriversData } from "@/lib/services/market-drivers-queries";
import { scoreZlSentiment, type Sentiment } from "@/lib/sentiment-scorer";

export const dynamic = "force-dynamic";

// =============================================================================
// TYPES
// =============================================================================

interface PriceSummary {
  current: number;
  previousClose: number;
  change: number;
  changePct: number;
  weekHigh: number;
  weekLow: number;
  asOf: string;
}

interface ForecastHorizon {
  label: string;
  days: number;
  targetLow: number | null; // p30
  targetMid: number | null; // p50
  targetHigh: number | null; // p70
  expectedChange: string;
  expectedChangePct: string;
  direction: "UP" | "DOWN" | "FLAT" | "NO DATA";
  source: "model" | "unavailable";
}

interface DriverSummary {
  name: string;
  score: number;
  status: string;
  impact: string;
  rawValue: number | null; // The actual underlying value (VIX level, crush margin, etc.)
  unit: string; // e.g., 'VIX points', 'USD/bu', 'CNY/USD', 'index'
  asOfDate: string | null; // When this data was last updated
  source: "live" | "stale" | "unavailable";
}

interface CorrelationSummary {
  asset: string;
  correlation: number | null;
  direction: string;
  implication: string;
  lookbackDays: number;
  source: "calculated" | "unavailable";
}

interface EventPulseEvent {
  headline: string;
  source: string;
  event_date: string;
  sentiment: Sentiment;
  confidence: number;
  tags: string[];
  hoursAgo: number;
}

interface EventPulse {
  recentEvents: EventPulseEvent[];
  velocity: {
    last24h: number;
    last48h: number;
    last72h: number;
    baseline7d: number;
    velocityRatio: number;
  };
  netSentiment: {
    bullish: number;
    bearish: number;
    neutral: number;
    netScore: number;
    signal:
      | "STRONGLY_BULLISH"
      | "BULLISH"
      | "NEUTRAL"
      | "BEARISH"
      | "STRONGLY_BEARISH";
  };
}

interface VegasBrief {
  generatedAt: string;
  asOfDate: string;

  // Quick read
  tldr: string;
  recommendation:
    | "BUY NOW"
    | "WAIT"
    | "NORMAL SCHEDULE"
    | "LOCK IN COVERAGE"
    | "CHECK DATA";
  recommendationColor: string;

  // Price
  price: PriceSummary;

  // Forecasts
  forecasts: ForecastHorizon[];
  forecastsAvailable: boolean;

  // Drivers (simplified)
  drivers: DriverSummary[];
  driversSummary: string;

  // Correlations
  correlations: CorrelationSummary[];

  // Policy/context
  policyContext: string;

  // Risk factors
  keyRisks: string[];
  keyPositives: string[];

  // Event intelligence
  eventPulse: EventPulse;
  overrideReason?: string;

  // Data quality
  dataIssues: string[]; // Truly missing data (unavailable)
  stalenessWarnings: string[]; // Data exists but past SLA
  dataQuality: "good" | "partial" | "poor";
  dataStaleness?: {
    allFresh: boolean;
    staleSources: Array<{
      driver: string;
      daysStale: number | null;
      sla: number;
    }>;
  };
}

// =============================================================================
// DATA FETCHERS
// =============================================================================

async function getCurrentPrice(): Promise<PriceSummary | null> {
  try {
    // Waterfall: pick freshest price from 1m → 15m → 1h → 1d
    // (analytics.latest_price is only updated by the live 1m feed which may be stale)
    const freshest = await query<{
      price: number;
      timestamp: string;
      source: string;
    }>(`
      SELECT price, timestamp, source FROM (
        SELECT close AS price, timestamp::text, '1m' AS source
          FROM analytics.price_1m ORDER BY timestamp DESC LIMIT 1
      ) t1m
      UNION ALL
      SELECT price, timestamp, source FROM (
        SELECT close AS price, timestamp::text, '15m' AS source
          FROM analytics.price_15m ORDER BY timestamp DESC LIMIT 1
      ) t15m
      UNION ALL
      SELECT price, timestamp, source FROM (
        SELECT close AS price, timestamp::text, '1h' AS source
          FROM analytics.price_1h ORDER BY timestamp DESC LIMIT 1
      ) t1h
      UNION ALL
      SELECT price, timestamp, source FROM (
        SELECT close AS price, event_date::text AS timestamp, '1d' AS source
          FROM analytics.price_1d WHERE close IS NOT NULL ORDER BY event_date DESC LIMIT 1
      ) t1d
      ORDER BY timestamp DESC
      LIMIT 1
    `);

    // Get recent daily closes for week range
    const dailyCloses = await query<{ close: number; event_date: string }>(`
      SELECT close, event_date FROM analytics.price_1d
      ORDER BY event_date DESC LIMIT 6
    `);

    if (!freshest.length || !dailyCloses.length) return null;

    const current = freshest[0].price;
    const previousClose = dailyCloses[1]?.close ?? dailyCloses[0].close;
    const weekPrices = dailyCloses.map((r) => r.close);

    return {
      current,
      previousClose,
      change: current - previousClose,
      changePct: ((current - previousClose) / previousClose) * 100,
      weekHigh: Math.max(...weekPrices, current),
      weekLow: Math.min(...weekPrices, current),
      asOf: freshest[0].timestamp,
    };
  } catch (e) {
    console.error("Price fetch error:", e);
    return null;
  }
}

async function getForecasts(currentPrice: number): Promise<ForecastHorizon[]> {
  try {
    // Try production forecasts first (consolidated table with horizon column)
    const fcRows = await query<{
      horizon_days: number;
      price_p30: number;
      price_p50: number;
      price_p70: number;
    }>(`
      SELECT DISTINCT ON (horizon)
        horizon as horizon_days, price_p30::float, price_p50::float, price_p70::float
      FROM forecasts.production_1d
      WHERE horizon IN (5, 21, 63, 126)
      ORDER BY horizon, as_of_date DESC
    `);

    if (fcRows.length > 0) {
      return fcRows.map((f) => formatForecast(f, currentPrice));
    }

    // No model forecasts available - return empty (NO FAKE DATA)
    return getEmptyForecasts();
  } catch (e) {
    console.error("Forecast fetch error:", e);
    return getEmptyForecasts();
  }
}

function formatForecast(
  f: {
    horizon_days: number;
    price_p30: number;
    price_p50: number;
    price_p70: number;
  },
  currentPrice: number,
): ForecastHorizon {
  const labels: Record<number, string> = {
    5: "1 Week",
    21: "1 Month",
    63: "1 Quarter",
    126: "6 Months",
  };

  const change = f.price_p50 - currentPrice;
  const changePct = (change / currentPrice) * 100;

  return {
    label: labels[f.horizon_days] || `${f.horizon_days}d`,
    days: f.horizon_days,
    targetLow: f.price_p30,
    targetMid: f.price_p50,
    targetHigh: f.price_p70,
    expectedChange: (change >= 0 ? "+$" : "-$") + Math.abs(change).toFixed(2),
    expectedChangePct: (changePct >= 0 ? "+" : "") + changePct.toFixed(1) + "%",
    direction: changePct > 2 ? "UP" : changePct < -2 ? "DOWN" : "FLAT",
    source: "model",
  };
}

// NO FAKE FORECASTS - return placeholders that clearly indicate no model data
function getEmptyForecasts(): ForecastHorizon[] {
  return [
    {
      label: "1 Week",
      days: 5,
      targetLow: null,
      targetMid: null,
      targetHigh: null,
      expectedChange: "--",
      expectedChangePct: "--",
      direction: "NO DATA",
      source: "unavailable",
    },
    {
      label: "1 Month",
      days: 21,
      targetLow: null,
      targetMid: null,
      targetHigh: null,
      expectedChange: "--",
      expectedChangePct: "--",
      direction: "NO DATA",
      source: "unavailable",
    },
    {
      label: "1 Quarter",
      days: 63,
      targetLow: null,
      targetMid: null,
      targetHigh: null,
      expectedChange: "--",
      expectedChangePct: "--",
      direction: "NO DATA",
      source: "unavailable",
    },
    {
      label: "6 Months",
      days: 126,
      targetLow: null,
      targetMid: null,
      targetHigh: null,
      expectedChange: "--",
      expectedChangePct: "--",
      direction: "NO DATA",
      source: "unavailable",
    },
  ];
}

async function getDriverScores(): Promise<{
  drivers: DriverSummary[];
  avgScore: number;
  summary: string;
  dataIssues: string[];
  stalenessWarnings: string[];
}> {
  const dataIssues: string[] = []; // Truly missing data (no value at all)
  const stalenessWarnings: string[] = []; // Data exists but past SLA freshness

  try {
    // Fetch ALL market driver data via the shared data layer (23 parallel queries)
    // Plus Trump Effect data (specialist signal + action score)
    const [rawData, trumpSignalData, trumpActionData] = await Promise.all([
      fetchMarketDriversData(),
      query<{ signal: number; as_of_date: string }>(`
        SELECT signal_1::float8 as signal, as_of_date::text
        FROM training.specialist_signals_1d
        WHERE bucket = 'trump_effect' AND as_of_date >= CURRENT_DATE - INTERVAL '45 days' AND abstained = false
        ORDER BY as_of_date DESC LIMIT 1
      `).catch(() => [] as { signal: number; as_of_date: string }[]),
      query<{ score: number; as_of_date: string }>(`
        SELECT (features->>'weighted_action_score')::float8 as score, as_of_date::text
        FROM training.specialist_features_trump_effect
        ORDER BY as_of_date DESC LIMIT 1
      `).catch(() => [] as { score: number; as_of_date: string }[]),
    ]);

    // Extract values from rawData
    const vix = rawData.vix;
    const vixDate = rawData.vixDate;
    const crush = rawData.crush;
    const crushDate = rawData.crushDate;
    const cny = rawData.cnyRate;
    const cnyDate = rawData.cnyDate;
    const tpu = rawData.tpu;
    const tpuDate = rawData.tpuDate;

    // Trump Effect data
    const trumpAction = trumpActionData[0]?.score ?? null;
    const trumpDate =
      trumpActionData[0]?.as_of_date ?? trumpSignalData[0]?.as_of_date ?? null;

    // Track truly MISSING data (no value at all) — these are critical
    if (!vix) dataIssues.push("VIX data unavailable");
    if (!crush) dataIssues.push("Crush margin data unavailable");
    if (!cny) dataIssues.push("CNY/USD rate unavailable");
    if (!tpu) dataIssues.push("Trade policy index unavailable");
    if (trumpAction === null) dataIssues.push("Trump Effect data unavailable");

    // Check data freshness with per-source SLA thresholds
    // Stale data is a WARNING, not a critical issue — the data still has value
    const today = new Date();
    const checkFreshness = (
      dateStr: string | null,
      name: string,
      slaDays = 3,
    ): "live" | "stale" | "unavailable" => {
      if (!dateStr) return "unavailable";
      const dataDate = new Date(dateStr);
      const daysDiff = Math.floor(
        (today.getTime() - dataDate.getTime()) / (1000 * 60 * 60 * 24),
      );
      if (daysDiff > slaDays) {
        stalenessWarnings.push(
          `${name} data is ${daysDiff} days old (SLA: ${slaDays}d)`,
        );
        return "stale";
      }
      return "live";
    };

    // Score calculations — FULL multi-component scorers matching /api/market-drivers
    const vixScore =
      vix !== null
        ? calculateVixStress(
            vix,
            rawData.vix3m,
            rawData.ovx,
            rawData.realizedVol,
            rawData.vixZlCorr,
            rawData.hedgeCount,
            rawData.volSignal,
          ).score
        : null;
    const crushScore =
      crush !== null
        ? calculateCrushPressure(
            crush,
            rawData.oilShare,
            rawData.oilShare5dAgo,
            rawData.crushSignal,
          ).score
        : null;
    const chinaScore =
      cny !== null
        ? calculateChinaTension(
            rawData.hgChange20d,
            rawData.hgChange5d,
            cny,
            rawData.cnyChange20d,
            rawData.bdiyChange20d,
            rawData.soyChinaNews,
            rawData.totalNews,
            rawData.chinaSignal,
          ).score
        : null;
    const tariffScore =
      tpu !== null
        ? calculateTariffThreat(
            tpu,
            rawData.emv,
            rawData.legislationCount,
            rawData.soyTariffNews,
            rawData.tariffSignal,
          ).score
        : null;
    // Trump Effect: weighted_action_score (0–2 scale) → 0–100
    const trumpScore =
      trumpAction !== null ? Math.min(100, Math.round(trumpAction * 50)) : null;

    // Only average scores that actually have data
    const validScores = [
      vixScore,
      crushScore,
      chinaScore,
      tariffScore,
      trumpScore,
    ].filter((s): s is number => s !== null);
    const avgScore =
      validScores.length > 0
        ? validScores.reduce((a, b) => a + b, 0) / validScores.length
        : 0;

    const drivers: DriverSummary[] = [
      {
        name: "Markets",
        score: vixScore ?? 0,
        status:
          vixScore === null
            ? "NO DATA"
            : vixScore >= 65
              ? "PANIC"
              : vixScore >= 50
                ? "NERVOUS"
                : vixScore <= 35
                  ? "CALM"
                  : "OK",
        impact:
          vixScore === null
            ? "VIX data unavailable — score excluded from average"
            : vixScore >= 65
              ? "Funds dumping commodities, wild swings"
              : vixScore <= 35
                ? "Stable, fundamentals-driven pricing"
                : "Normal volatility",
        rawValue: vix,
        unit: "VIX points",
        asOfDate: vixDate,
        source: checkFreshness(vixDate, "VIX", 3),
      },
      {
        name: "Crush",
        score: crushScore ?? 0,
        status:
          crushScore === null
            ? "NO DATA"
            : crushScore >= 65
              ? "TIGHT"
              : crushScore <= 35
                ? "FLUSH"
                : "NORMAL",
        impact:
          crushScore === null
            ? "Crush data unavailable — score excluded from average"
            : crushScore >= 65
              ? `Plants slowing at USD ${crush!.toFixed(2)}/bu - supply tightening`
              : crushScore <= 35
                ? `Plants running full at USD ${crush!.toFixed(2)}/bu - plenty of oil`
                : `Normal margins at USD ${crush!.toFixed(2)}/bu`,
        rawValue: crush,
        unit: "USD/bushel",
        asOfDate: crushDate,
        source: checkFreshness(crushDate, "Crush", 5),
      },
      {
        name: "China",
        score: chinaScore ?? 0,
        status:
          chinaScore === null
            ? "NO DATA"
            : chinaScore >= 65
              ? "FROZEN"
              : "BRAZIL PREFERRED",
        impact:
          chinaScore === null
            ? "FX data unavailable — score excluded from average"
            : chinaScore >= 65
              ? "Trade disrupted, soy demand weak"
              : `Brazil beats US (CNY at ${cny!.toFixed(2)}) - 13% tariff gap`,
        rawValue: cny,
        unit: "CNY/USD",
        asOfDate: cnyDate,
        source: checkFreshness(cnyDate, "CNY", 5),
      },
      {
        name: "Tariffs",
        score: tariffScore ?? 0,
        status:
          tariffScore === null
            ? "NO DATA"
            : tariffScore >= 65
              ? "WAR RISK"
              : tariffScore >= 50
                ? "NOISY"
                : "QUIET",
        impact:
          tariffScore === null
            ? "Policy index unavailable — score excluded from average"
            : tariffScore >= 65
              ? `TPU at ${tpu!.toFixed(0)} - escalation risk, stay defensive`
              : tariffScore <= 35
                ? "Policy stable, no new threats"
                : "Headlines, no action",
        rawValue: tpu,
        unit: "index",
        asOfDate: tpuDate,
        source: checkFreshness(tpuDate, "TPU", 45),
      },
      {
        name: "Trump Effect",
        score: trumpScore ?? 0,
        status:
          trumpScore === null
            ? "NO DATA"
            : trumpScore >= 65
              ? "HIGH IMPACT"
              : trumpScore >= 40
                ? "ELEVATED"
                : "LOW",
        impact:
          trumpScore === null
            ? "Trump Effect data unavailable — score excluded from average"
            : trumpScore >= 65
              ? `Action velocity high (${trumpAction!.toFixed(2)}) - executive actions disrupting markets`
              : trumpScore >= 40
                ? `Moderate activity (${trumpAction!.toFixed(2)}) - watch for escalation`
                : `Low action velocity (${trumpAction!.toFixed(2)}) - policy stable`,
        rawValue: trumpAction,
        unit: "action score",
        asOfDate: trumpDate,
        source: checkFreshness(trumpDate, "Trump Effect", 7),
      },
    ];

    const missingCount = 5 - validScores.length;
    const staleCount = stalenessWarnings.length;
    const summary =
      missingCount >= 4
        ? `${missingCount} of 5 drivers have no data. Brief is unreliable.`
        : missingCount >= 2
          ? `${missingCount} drivers unavailable. Scores based on ${validScores.length}/5 drivers.`
          : staleCount > 0 && avgScore >= 60
            ? `Multiple headwinds. ${staleCount} source${staleCount > 1 ? "s" : ""} past SLA but usable.`
            : avgScore >= 60
              ? "Multiple headwinds. Markets nervous, trade uncertain."
              : avgScore <= 40
                ? "Favorable conditions. Stable markets, solid crush."
                : staleCount > 0
                  ? `Mixed picture. ${staleCount} source${staleCount > 1 ? "s" : ""} past freshness SLA.`
                  : "Mixed picture. No clear direction.";

    return { drivers, avgScore, summary, dataIssues, stalenessWarnings };
  } catch (e) {
    console.error("Driver fetch error:", e);
    // Return unavailable drivers - NO FAKE SCORES
    return {
      drivers: [
        {
          name: "Markets",
          score: 0,
          status: "ERROR",
          impact: "Database query failed",
          rawValue: null,
          unit: "VIX points",
          asOfDate: null,
          source: "unavailable",
        },
        {
          name: "Crush",
          score: 0,
          status: "ERROR",
          impact: "Database query failed",
          rawValue: null,
          unit: "USD/bushel",
          asOfDate: null,
          source: "unavailable",
        },
        {
          name: "China",
          score: 0,
          status: "ERROR",
          impact: "Database query failed",
          rawValue: null,
          unit: "CNY/USD",
          asOfDate: null,
          source: "unavailable",
        },
        {
          name: "Tariffs",
          score: 0,
          status: "ERROR",
          impact: "Database query failed",
          rawValue: null,
          unit: "index",
          asOfDate: null,
          source: "unavailable",
        },
        {
          name: "Trump Effect",
          score: 0,
          status: "ERROR",
          impact: "Database query failed",
          rawValue: null,
          unit: "action score",
          asOfDate: null,
          source: "unavailable",
        },
      ],
      avgScore: 0,
      summary:
        "DATABASE ERROR: Unable to fetch driver data. Do not rely on this brief.",
      dataIssues: ["Database connection failed"],
      stalenessWarnings: [],
    };
  }
}

// Calculate REAL correlations from database price data (63-day rolling)
async function getCorrelations(): Promise<CorrelationSummary[]> {
  // LIMIT 64 to get 63 log-returns after the LAG
  const LOOKBACK = 64; // 64 prices → 63 log-returns → 3-month rolling correlation

  try {
    // Calculate correlations on LOG RETURNS (not price levels) to avoid spurious correlation
    const correlationQueries = await Promise.all([
      // ZL vs Soybean Meal (ZM)
      query<{ corr: number }>(`
        WITH zl AS (SELECT event_date, LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) as ret
                    FROM mkt.futures_1d WHERE symbol = 'ZL' ORDER BY event_date DESC LIMIT ${LOOKBACK}),
             zm AS (SELECT event_date, LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) as ret
                    FROM mkt.futures_1d WHERE symbol = 'ZM' ORDER BY event_date DESC LIMIT ${LOOKBACK})
        SELECT CORR(zl.ret, zm.ret)::float8 as corr FROM zl JOIN zm ON zl.event_date = zm.event_date
        WHERE zl.ret IS NOT NULL AND zm.ret IS NOT NULL
      `).catch(() => [{ corr: null }]),

      // ZL vs Soybeans (ZS)
      query<{ corr: number }>(`
        WITH zl AS (SELECT event_date, LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) as ret
                    FROM mkt.futures_1d WHERE symbol = 'ZL' ORDER BY event_date DESC LIMIT ${LOOKBACK}),
             zs AS (SELECT event_date, LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) as ret
                    FROM mkt.futures_1d WHERE symbol = 'ZS' ORDER BY event_date DESC LIMIT ${LOOKBACK})
        SELECT CORR(zl.ret, zs.ret)::float8 as corr FROM zl JOIN zs ON zl.event_date = zs.event_date
        WHERE zl.ret IS NOT NULL AND zs.ret IS NOT NULL
      `).catch(() => [{ corr: null }]),

      // ZL vs Crude Oil (CL)
      query<{ corr: number }>(`
        WITH zl AS (SELECT event_date, LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) as ret
                    FROM mkt.futures_1d WHERE symbol = 'ZL' ORDER BY event_date DESC LIMIT ${LOOKBACK}),
             cl AS (SELECT event_date, LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) as ret
                    FROM mkt.futures_1d WHERE symbol = 'CL' ORDER BY event_date DESC LIMIT ${LOOKBACK})
        SELECT CORR(zl.ret, cl.ret)::float8 as corr FROM zl JOIN cl ON zl.event_date = cl.event_date
        WHERE zl.ret IS NOT NULL AND cl.ret IS NOT NULL
      `).catch(() => [{ corr: null }]),

      // ZL vs VIX (inverse relationship expected)
      query<{ corr: number }>(`
        WITH zl AS (SELECT event_date, LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) as ret
                    FROM mkt.futures_1d WHERE symbol = 'ZL' ORDER BY event_date DESC LIMIT ${LOOKBACK}),
             vix AS (SELECT event_date, LN(value / NULLIF(LAG(value) OVER (ORDER BY event_date), 0)) as ret
                     FROM econ.vol_indices_1d WHERE series_id = 'VIXCLS' ORDER BY event_date DESC LIMIT ${LOOKBACK})
        SELECT CORR(zl.ret, vix.ret)::float8 as corr FROM zl JOIN vix ON zl.event_date = vix.event_date
        WHERE zl.ret IS NOT NULL AND vix.ret IS NOT NULL
      `).catch(() => [{ corr: null }]),

      // ZL vs Corn (ZC) - competing biofuel feedstock
      query<{ corr: number }>(`
        WITH zl AS (SELECT event_date, LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) as ret
                    FROM mkt.futures_1d WHERE symbol = 'ZL' ORDER BY event_date DESC LIMIT ${LOOKBACK}),
             zc AS (SELECT event_date, LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) as ret
                    FROM mkt.futures_1d WHERE symbol = 'ZC' ORDER BY event_date DESC LIMIT ${LOOKBACK})
        SELECT CORR(zl.ret, zc.ret)::float8 as corr FROM zl JOIN zc ON zl.event_date = zc.event_date
        WHERE zl.ret IS NOT NULL AND zc.ret IS NOT NULL
      `).catch(() => [{ corr: null }]),

      // ZL vs Palm Oil (CPO) - global substitution competitor
      query<{ corr: number }>(`
        WITH zl AS (SELECT event_date, LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) as ret
                    FROM mkt.futures_1d WHERE symbol = 'ZL' ORDER BY event_date DESC LIMIT ${LOOKBACK}),
             cpo AS (SELECT event_date, LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) as ret
                     FROM mkt.futures_1d WHERE symbol = 'CPO' ORDER BY event_date DESC LIMIT ${LOOKBACK})
        SELECT CORR(zl.ret, cpo.ret)::float8 as corr FROM zl JOIN cpo ON zl.event_date = cpo.event_date
        WHERE zl.ret IS NOT NULL AND cpo.ret IS NOT NULL
      `).catch(() => [{ corr: null }]),
    ]);

    const [zmCorr, zsCorr, clCorr, vixCorr, zcCorr, cpoCorr] =
      correlationQueries.map((r) => r[0]?.corr ?? null);

    const formatDirection = (corr: number | null): string => {
      if (corr === null) return "No data";
      if (corr >= 0.7) return "Strong positive";
      if (corr >= 0.4) return "Moderate positive";
      if (corr >= 0.1) return "Weak positive";
      if (corr >= -0.1) return "Uncorrelated";
      if (corr >= -0.4) return "Weak negative";
      if (corr >= -0.7) return "Moderate negative";
      return "Strong negative";
    };

    return [
      {
        asset: "Soybean Meal (ZM)",
        correlation: zmCorr,
        direction: formatDirection(zmCorr),
        implication:
          zmCorr !== null && zmCorr > 0.5
            ? "Crush economics linked. Strong meal supports crush and oil supply."
            : "Crush relationship currently weak.",
        lookbackDays: LOOKBACK,
        source: zmCorr !== null ? "calculated" : "unavailable",
      },
      {
        asset: "Soybeans (ZS)",
        correlation: zsCorr,
        direction: formatDirection(zsCorr),
        implication:
          zsCorr !== null && zsCorr > 0.6
            ? "Bean prices drive oil. Watch bean fundamentals."
            : "Oil trading independently of beans currently.",
        lookbackDays: LOOKBACK,
        source: zsCorr !== null ? "calculated" : "unavailable",
      },
      {
        asset: "Crude Oil (CL)",
        correlation: clCorr,
        direction: formatDirection(clCorr),
        implication:
          clCorr !== null && clCorr > 0.3
            ? "Energy complex link via biofuels. Crude rallies support soybean oil."
            : "Limited energy complex correlation currently.",
        lookbackDays: LOOKBACK,
        source: clCorr !== null ? "calculated" : "unavailable",
      },
      {
        asset: "VIX (Fear Index)",
        correlation: vixCorr,
        direction: formatDirection(vixCorr),
        implication:
          vixCorr !== null && vixCorr < -0.2
            ? "Risk-off hurts commodities. Wait out volatility spikes."
            : "Limited vol spillover currently - fundamentals driving.",
        lookbackDays: LOOKBACK,
        source: vixCorr !== null ? "calculated" : "unavailable",
      },
      {
        asset: "Corn (ZC)",
        correlation: zcCorr,
        direction: formatDirection(zcCorr),
        implication:
          zcCorr !== null && zcCorr > 0.4
            ? "Ag complex moving together. Broad commodity theme."
            : "Oil trading on its own fundamentals vs corn.",
        lookbackDays: LOOKBACK,
        source: zcCorr !== null ? "calculated" : "unavailable",
      },
      {
        asset: "Palm Oil (CPO)",
        correlation: cpoCorr,
        direction: formatDirection(cpoCorr),
        implication:
          cpoCorr !== null && cpoCorr > 0.4
            ? "Global substitution link active. Palm and soybean oil moving together."
            : "Substitution link weak. Regional factors dominating.",
        lookbackDays: LOOKBACK,
        source: cpoCorr !== null ? "calculated" : "unavailable",
      },
    ];
  } catch (e) {
    console.error("Correlation calculation error:", e);
    // Return empty correlations - NO FAKE DATA
    return [
      {
        asset: "Soybean Meal (ZM)",
        correlation: null,
        direction: "Data unavailable",
        implication: "Unable to calculate",
        lookbackDays: LOOKBACK,
        source: "unavailable",
      },
      {
        asset: "Soybeans (ZS)",
        correlation: null,
        direction: "Data unavailable",
        implication: "Unable to calculate",
        lookbackDays: LOOKBACK,
        source: "unavailable",
      },
      {
        asset: "Crude Oil (CL)",
        correlation: null,
        direction: "Data unavailable",
        implication: "Unable to calculate",
        lookbackDays: LOOKBACK,
        source: "unavailable",
      },
      {
        asset: "VIX (Fear Index)",
        correlation: null,
        direction: "Data unavailable",
        implication: "Unable to calculate",
        lookbackDays: LOOKBACK,
        source: "unavailable",
      },
      {
        asset: "Corn (ZC)",
        correlation: null,
        direction: "Data unavailable",
        implication: "Unable to calculate",
        lookbackDays: LOOKBACK,
        source: "unavailable",
      },
      {
        asset: "Palm Oil (CPO)",
        correlation: null,
        direction: "Data unavailable",
        implication: "Unable to calculate",
        lookbackDays: LOOKBACK,
        source: "unavailable",
      },
    ];
  }
}

// =============================================================================
// EVENT PULSE — Real-time event intelligence from DB + live GDELT news
// =============================================================================

/**
 * Fetch live headlines from Google News RSS (free, no API key, no rate limits).
 * Supplements the DB-sourced events with real-time global news about
 * commodities, energy, and geopolitical events affecting soybean oil.
 */
async function fetchLiveHeadlines(): Promise<
  Array<{
    headline: string;
    source: string;
    event_date: string;
  }>
> {
  try {
    // Two targeted queries: one for commodity/ag, one for geopolitical
    // Use separate RSS feeds for better recent coverage
    const queries = [
      "soybean oil crude oil soybeans commodities",
      'Iran war sanctions tariff "Strait of Hormuz" "oil prices"',
    ];
    // Fetch both in parallel (Google News RSS has no rate limit)
    const allItems: Array<{
      headline: string;
      source: string;
      event_date: string;
    }> = [];
    const seenTitles = new Set<string>();

    await Promise.all(
      queries.map(async (q) => {
        try {
          const url = `https://news.google.com/rss/search?q=${encodeURIComponent(q)}&hl=en-US&gl=US&ceid=US:en`;
          const resp = await fetch(url, { signal: AbortSignal.timeout(8000) });
          if (!resp.ok) return;
          const xml = await resp.text();
          const blocks = xml.split("<item>").slice(1);
          for (const raw of blocks) {
            const block = raw.split("</item>")[0] || "";
            const titleMatch = block.match(/<title>([^<]+)<\/title>/);
            const pubMatch = block.match(/<pubDate>([^<]+)<\/pubDate>/);
            if (!titleMatch) continue;

            const fullTitle = titleMatch[1]
              .replace(/&amp;/g, "&")
              .replace(/&lt;/g, "<")
              .replace(/&gt;/g, ">")
              .replace(/&#39;/g, "'");
            if (seenTitles.has(fullTitle)) continue;
            seenTitles.add(fullTitle);

            const dashIdx = fullTitle.lastIndexOf(" - ");
            const headline =
              dashIdx > 0 ? fullTitle.slice(0, dashIdx) : fullTitle;
            const source =
              dashIdx > 0 ? fullTitle.slice(dashIdx + 3) : "Google News";

            let eventDate: string;
            try {
              eventDate = new Date(pubMatch?.[1] || "").toISOString();
            } catch {
              eventDate = new Date().toISOString();
            }

            allItems.push({ headline, source, event_date: eventDate });
          }
        } catch {
          /* individual query failure ok */
        }
      }),
    );

    console.log(
      `[LiveHeadlines] Parsed ${allItems.length} total headlines from ${queries.length} queries`,
    );
    return allItems;
  } catch (e) {
    console.error("[LiveHeadlines] Fetch error (non-fatal):", e);
    return []; // Fail silently — DB events still work
  }
}

async function getEventPulse(): Promise<EventPulse> {
  const emptyPulse: EventPulse = {
    recentEvents: [],
    velocity: {
      last24h: 0,
      last48h: 0,
      last72h: 0,
      baseline7d: 0,
      velocityRatio: 0,
    },
    netSentiment: {
      bullish: 0,
      bearish: 0,
      neutral: 0,
      netScore: 0,
      signal: "NEUTRAL",
    },
  };

  try {
    // Fetch DB events + live GDELT headlines in parallel
    const [rows, liveHeadlines] = await Promise.all([
      query<{
        headline: string;
        summary: string | null;
        source: string;
        event_date: string;
        tags: string[];
      }>(`
        WITH combined AS (
          SELECT headline, summary, 'ProFarmer' AS source, event_date, specialist_tags AS tags
          FROM alt.profarmer_news_event
          WHERE event_date >= NOW() - INTERVAL '7 days'

          UNION ALL

          SELECT title AS headline, CONCAT(document_type, ' — ', agency) AS summary,
                 COALESCE(source, 'Federal Register') AS source, event_date, specialist_tags AS tags
          FROM alt.legislation_1d
          WHERE event_date >= NOW() - INTERVAL '7 days'

          UNION ALL

          SELECT headline, NULL AS summary, source, event_date, specialist_tags AS tags
          FROM alt.policy_news_event
          WHERE event_date >= NOW() - INTERVAL '7 days'

          UNION ALL

          SELECT headline, NULL AS summary, source, event_date, specialist_tags AS tags
          FROM alt.executive_actions_event
          WHERE event_date >= NOW() - INTERVAL '7 days'

          UNION ALL

          SELECT headline, summary, source, event_date, specialist_tags AS tags
          FROM alt.econ_news_event
          WHERE event_date >= NOW() - INTERVAL '7 days'

          UNION ALL

          SELECT headline, NULL AS summary, source, event_date, specialist_tags AS tags
          FROM econ.news_event
          WHERE event_date >= NOW() - INTERVAL '7 days'
        )
        SELECT * FROM combined ORDER BY event_date DESC
      `),
      fetchLiveHeadlines(),
    ]);

    const now = new Date();

    // Score DB events
    const scoredDb = rows.map((r) => {
      const sentimentResult = scoreZlSentiment(r.headline, r.summary);
      const eventDate = new Date(r.event_date);
      const hoursAgo = Math.round(
        (now.getTime() - eventDate.getTime()) / (1000 * 60 * 60),
      );
      return {
        headline: r.headline,
        source: r.source,
        event_date: r.event_date,
        sentiment: sentimentResult.sentiment,
        confidence: sentimentResult.confidence,
        bullScore: sentimentResult.bullScore,
        bearScore: sentimentResult.bearScore,
        tags: (r.tags || []).slice(0, 4),
        hoursAgo,
      };
    });

    // Score GDELT headlines (live news supplement)
    const scoredLive = liveHeadlines.map((g) => {
      const sentimentResult = scoreZlSentiment(g.headline, null);
      const eventDate = new Date(g.event_date);
      const hoursAgo = Math.max(
        0,
        Math.round((now.getTime() - eventDate.getTime()) / (1000 * 60 * 60)),
      );
      return {
        headline: g.headline,
        source: g.source,
        event_date: g.event_date,
        sentiment: sentimentResult.sentiment,
        confidence: sentimentResult.confidence,
        bullScore: sentimentResult.bullScore,
        bearScore: sentimentResult.bearScore,
        tags: ["LIVE"] as string[],
        hoursAgo,
      };
    });

    // Merge: DB events + GDELT live news, dedup by headline similarity
    const seenHeadlines = new Set(
      scoredDb.map((e) => e.headline.toLowerCase().slice(0, 60)),
    );
    const uniqueLive = scoredLive.filter((g) => {
      const key = g.headline.toLowerCase().slice(0, 60);
      if (seenHeadlines.has(key)) return false;
      seenHeadlines.add(key);
      return true;
    });

    const scored = [...scoredDb, ...uniqueLive];

    // Debug: log merge stats with hoursAgo distribution
    const liveNonNeutral = uniqueLive.filter((e) => e.sentiment !== "neutral");
    const liveWithin72h = uniqueLive.filter((e) => e.hoursAgo <= 72);
    const liveWithin168h = uniqueLive.filter((e) => e.hoursAgo <= 168);
    console.log(
      `[EventPulse] DB: ${scoredDb.length}, Live: ${scoredLive.length}, Unique: ${uniqueLive.length}, NonNeutral: ${liveNonNeutral.length}, within72h: ${liveWithin72h.length}, within168h: ${liveWithin168h.length}, hoursAgoRange: ${uniqueLive.length > 0 ? `${Math.min(...uniqueLive.map((e) => e.hoursAgo))}-${Math.max(...uniqueLive.map((e) => e.hoursAgo))}` : "empty"}`,
    );

    if (scored.length === 0) return emptyPulse;

    // Velocity metrics (DB events for baseline, all events for current)
    const dbLast24h = scoredDb.filter((e) => e.hoursAgo <= 24).length;
    const liveLast24h = uniqueLive.filter((e) => e.hoursAgo <= 24).length;
    const last24h = dbLast24h + liveLast24h;
    const last48h = scored.filter((e) => e.hoursAgo <= 48).length;
    const last72h = scored.filter((e) => e.hoursAgo <= 72).length;
    const baseline7d = scoredDb.length / 7; // baseline from DB only (stable denominator)
    const velocityRatio =
      baseline7d > 0 ? last24h / baseline7d : last24h > 0 ? last24h : 0;

    // Aggregate sentiment: DB events from 48h, LIVE news from 168h (broader window)
    // Weight LIVE non-neutral events higher — they're real-time news vs admin filings
    const recent48h = scored.filter((e) =>
      e.tags.includes("LIVE") ? e.hoursAgo <= 168 : e.hoursAgo <= 48,
    );
    let bullish = 0,
      bearish = 0,
      neutral = 0;
    let weightedBull = 0,
      weightedBear = 0;

    for (const e of recent48h) {
      const isLiveNews = e.tags.includes("LIVE");
      const liveBoost = isLiveNews ? 1.5 : 1.0; // Live news gets 50% weight boost

      if (e.sentiment === "bullish") {
        bullish++;
        weightedBull += e.confidence * (e.bullScore - e.bearScore) * liveBoost;
      } else if (e.sentiment === "bearish") {
        bearish++;
        weightedBear += e.confidence * (e.bearScore - e.bullScore) * liveBoost;
      } else {
        neutral++;
      }
    }

    const netScore = weightedBull - weightedBear;

    let signal: EventPulse["netSentiment"]["signal"] = "NEUTRAL";
    if (netScore > 3) signal = "STRONGLY_BULLISH";
    else if (netScore > 1) signal = "BULLISH";
    else if (netScore < -3) signal = "STRONGLY_BEARISH";
    else if (netScore < -1) signal = "BEARISH";

    // Top 10 events: LIVE news with sentiment always first, then DB events
    // LIVE news gets 168h window (Google News covers broader range), DB stays at 72h
    const top10 = scored
      .filter((e) =>
        e.tags.includes("LIVE") ? e.hoursAgo <= 168 : e.hoursAgo <= 72,
      )
      .sort((a, b) => {
        const aLive = a.tags.includes("LIVE") ? 1 : 0;
        const bLive = b.tags.includes("LIVE") ? 1 : 0;
        // Live non-neutral news gets massive priority boost
        const aStrength =
          (a.sentiment !== "neutral" ? a.confidence + 0.3 : 0) +
          aLive * 2.0 +
          (a.hoursAgo <= 24 ? 0.5 : 0);
        const bStrength =
          (b.sentiment !== "neutral" ? b.confidence + 0.3 : 0) +
          bLive * 2.0 +
          (b.hoursAgo <= 24 ? 0.5 : 0);
        return bStrength - aStrength || a.hoursAgo - b.hoursAgo;
      })
      .slice(0, 10)
      .map(({ bullScore: _b, bearScore: _br, ...rest }) => rest);

    return {
      recentEvents: top10,
      velocity: {
        last24h,
        last48h,
        last72h,
        baseline7d: Math.round(baseline7d * 10) / 10,
        velocityRatio: Math.round(velocityRatio * 10) / 10,
      },
      netSentiment: {
        bullish,
        bearish,
        neutral,
        netScore: Math.round(netScore * 100) / 100,
        signal,
      },
    };
  } catch (e) {
    console.error("Event pulse fetch error:", e);
    return emptyPulse;
  }
}

function getPolicyContext(_avgScore: number): string {
  // Policy context last reviewed: 2026-02-16
  // Update when: RFS finalized, 45Z credit changes, tariff structure changes
  return (
    `BIOFUELS DRIVING DEMAND: EPA's 2026 RFS proposals boost biomass-based diesel targets to ~5.6B gallons. ` +
    `45Z tax credit (clean fuel) supports renewable diesel economics. Soy oil now ~40%+ of U.S. production goes to biofuels. ` +
    `CHINA REALITY: U.S. faces permanent 13% tariff vs Brazil's 3%. We only compete when Brazil runs short. ` +
    `Don't count on China surprises - price your coverage on domestic biofuel demand, not exports.`
  );
}

// =============================================================================
// BRIEF GENERATION
// =============================================================================

function generateTLDR(
  price: PriceSummary,
  fcHorizons: ForecastHorizon[],
  driverData: {
    drivers: DriverSummary[];
    avgScore: number;
    dataIssues: string[];
  },
): string {
  const f1m = fcHorizons.find((f) => f.days === 21) || fcHorizons[1];
  const f6m = fcHorizons.find((f) => f.days === 126) || fcHorizons[3];

  const priceDesc = `Soybean oil (ZL) at $${price.current.toFixed(2)}/lb`;
  const change =
    price.changePct >= 0
      ? `up ${price.changePct.toFixed(1)}% today`
      : `down ${Math.abs(price.changePct).toFixed(1)}% today`;

  let outlook: string;
  if (driverData.dataIssues.length >= 4) {
    outlook =
      "LIMITED DATA - most indicators unavailable, proceed with caution";
  } else if (driverData.avgScore >= 60) {
    outlook = "CAUTIOUS - multiple headwinds (volatility, trade uncertainty)";
  } else if (driverData.avgScore <= 40) {
    outlook = "FAVORABLE - stable markets, strong crush economics";
  } else {
    outlook = "MIXED - no clear direction, normal buying conditions";
  }

  // Build forecast summary only if model data available
  let forecastSummary: string;
  if (f1m?.targetMid !== null && f6m?.targetMid !== null) {
    forecastSummary =
      `1-month target: $${f1m.targetMid.toFixed(2)} (${f1m.expectedChangePct}). ` +
      `6-month target: $${f6m.targetMid.toFixed(2)} (${f6m.expectedChangePct}).`;
  } else {
    forecastSummary = `Model forecasts not yet available - prices based on current drivers only.`;
  }

  return (
    `${priceDesc}, ${change}. Outlook: ${outlook}. ${forecastSummary} ` +
    `Biofuel demand strong (45Z credit, RFS increases), China buying from Brazil (13% tariff gap). ` +
    `Key watch: VIX, crush margins, trade headlines.`
  );
}

function getRecommendation(
  avgScore: number,
  dataIssues: string[],
  eventPulse?: EventPulse,
  forecastDirection?: "UP" | "DOWN" | "FLAT" | "NO DATA",
  forecastChangePct?: number,
): {
  text:
    | "BUY NOW"
    | "WAIT"
    | "NORMAL SCHEDULE"
    | "LOCK IN COVERAGE"
    | "CHECK DATA";
  color: string;
  overrideReason?: string;
} {
  // Only trigger CHECK DATA for truly MISSING data (unavailable),
  // NOT for stale data. Stale data still has value and is scored.
  if (dataIssues.length >= 4) {
    return { text: "CHECK DATA", color: "#6B7280" };
  }

  // --- Event-driven posture overrides (evaluated BEFORE score-based logic) ---
  // These can ESCALATE the posture but never downgrade it.
  // IMPORTANT: If the model strongly predicts a price DROP (>8%), temper the
  // bullish override — the spike may be temporary and buying at the top is costly.
  if (eventPulse) {
    const { velocity, netSentiment } = eventPulse;
    const topHeadline = eventPulse.recentEvents[0]?.headline;
    const modelPredictsDrop =
      forecastDirection === "DOWN" &&
      forecastChangePct !== undefined &&
      forecastChangePct < -8;

    // Strong bearish event signal — override to LOCK IN COVERAGE
    if (netSentiment.netScore < -3) {
      return {
        text: "LOCK IN COVERAGE",
        color: "#DC2626",
        overrideReason: `Strong bearish signal from recent events${topHeadline ? `: "${topHeadline}"` : ""}`,
      };
    }
    // High velocity + bearish — override to LOCK IN COVERAGE
    if (velocity.velocityRatio > 2.0 && netSentiment.netScore < -2) {
      return {
        text: "LOCK IN COVERAGE",
        color: "#DC2626",
        overrideReason: `Unusually high bearish event activity (${velocity.velocityRatio}x normal)${topHeadline ? `: "${topHeadline}"` : ""}`,
      };
    }

    // Bullish event signals — supply disruption driving prices UP
    // But if model predicts significant drop, events may be priced in already
    if (netSentiment.netScore > 3) {
      if (modelPredictsDrop) {
        // Events say crisis, model says prices revert — HIGH VOLATILITY regime
        return {
          text: "WAIT",
          color: "#EF4444",
          overrideReason: `Supply disruption headlines but model forecasts ${forecastChangePct?.toFixed(0)}% retracement — spike may be temporary. Wait for pullback${topHeadline ? `. Catalyst: "${topHeadline}"` : ""}`,
        };
      }
      return {
        text: "LOCK IN COVERAGE",
        color: "#DC2626",
        overrideReason: `Prices rising on supply disruption — lock in before further escalation${topHeadline ? `: "${topHeadline}"` : ""}`,
      };
    }
    // High velocity + bullish — supply shock in progress
    if (velocity.velocityRatio > 2.0 && netSentiment.netScore > 2) {
      if (modelPredictsDrop) {
        return {
          text: "WAIT",
          color: "#EF4444",
          overrideReason: `Event velocity elevated (${velocity.velocityRatio}x) but model sees ${forecastChangePct?.toFixed(0)}% downside — wait for pullback`,
        };
      }
      return {
        text: "LOCK IN COVERAGE",
        color: "#DC2626",
        overrideReason: `High event velocity (${velocity.velocityRatio}x normal) with prices rising — lock in coverage now`,
      };
    }
  }

  // --- Standard score-based logic ---
  if (avgScore >= 65) {
    return { text: "WAIT", color: "#EF4444" };
  } else if (avgScore >= 50) {
    return { text: "NORMAL SCHEDULE", color: "#F97316" };
  } else if (avgScore >= 35) {
    return { text: "NORMAL SCHEDULE", color: "#EAB308" };
  } else {
    return { text: "LOCK IN COVERAGE", color: "#22C55E" };
  }
}

function getKeyRisks(driverData: {
  drivers: DriverSummary[];
  avgScore: number;
}): string[] {
  const risks: string[] = [];

  const vix = driverData.drivers.find((d) => d.name === "Markets");
  const tariff = driverData.drivers.find((d) => d.name === "Tariffs");
  const china = driverData.drivers.find((d) => d.name === "China");
  const crush = driverData.drivers.find((d) => d.name === "Crush");

  if (vix && vix.score >= 50) {
    risks.push(
      "Market volatility elevated - prices could swing on any headline",
    );
  }
  if (tariff && tariff.score >= 50) {
    risks.push(
      "Trade policy noise - China could pull back if tensions escalate",
    );
  }
  if (china && china.score >= 60) {
    risks.push("China demand weak - exports not providing price support");
  }
  if (crush && crush.score >= 60) {
    risks.push("Crush margins tight - some plants may slow, tightening supply");
  }

  // Always include these structural risks
  risks.push(
    "South America (Brazil/Argentina) record crops pressuring global supplies",
  );

  return risks.slice(0, 4);
}

function getKeyPositives(driverData: {
  drivers: DriverSummary[];
  avgScore: number;
}): string[] {
  const positives: string[] = [];

  const vix = driverData.drivers.find((d) => d.name === "Markets");
  const crush = driverData.drivers.find((d) => d.name === "Crush");

  // Always include biofuel tailwind
  positives.push(
    "EPA 2026 RFS increases boost biofuel demand - >50% of soybean oil to biodiesel/renewable diesel",
  );
  positives.push(
    "45Z clean fuel tax credit supports renewable diesel economics through 2027",
  );

  if (vix && vix.score <= 40) {
    positives.push("Markets calm - fundamentals-driven pricing, tight spreads");
  }
  if (crush && crush.score <= 40) {
    positives.push(
      "Crush margins strong - plants running full, reliable supply",
    );
  }

  positives.push(
    "Record U.S. crush forecast (~2.57B bushels) keeps domestic supply flowing",
  );

  return positives.slice(0, 4);
}

// =============================================================================
// MAIN HANDLER
// =============================================================================

export async function GET() {
  try {
    const now = new Date();
    const asOfDate = now.toISOString().split("T")[0];

    // Fetch all data
    const price = await getCurrentPrice();

    if (!price) {
      return NextResponse.json(
        {
          error: "Price data unavailable",
          message: "Unable to fetch current ZL price",
        },
        { status: 503 },
      );
    }

    const [fcHorizons, driverData, correlations, eventPulse] =
      await Promise.all([
        getForecasts(price.current),
        getDriverScores(),
        getCorrelations(),
        getEventPulse(),
      ]);

    const policyContext = getPolicyContext(driverData.avgScore);
    // Get 1-month forecast for recommendation logic
    const fc1m = fcHorizons.find((f) => f.days === 21) || fcHorizons[1];
    const fc1mChangePct =
      fc1m?.targetMid && price
        ? ((fc1m.targetMid - price.current) / price.current) * 100
        : undefined;
    const recommendation = getRecommendation(
      driverData.avgScore,
      driverData.dataIssues,
      eventPulse,
      fc1m?.direction,
      fc1mChangePct,
    );

    // Check if forecasts are available (not all placeholders)
    const forecastsAvailable = fcHorizons.some((f) => f.source === "model");

    // Determine overall data quality
    // Only truly unavailable sources count as "poor" — stale data is "partial"
    const unavailableDrivers = driverData.drivers.filter(
      (d) => d.source === "unavailable",
    ).length;
    const staleDrivers = driverData.drivers.filter(
      (d) => d.source === "stale",
    ).length;
    const unavailableCorrs = correlations.filter(
      (c) => c.source === "unavailable",
    ).length;
    let dataQuality: "good" | "partial" | "poor";
    if (unavailableDrivers >= 3 || unavailableCorrs >= 4) {
      dataQuality = "poor";
    } else if (
      unavailableDrivers >= 1 ||
      staleDrivers >= 2 ||
      unavailableCorrs >= 2 ||
      !forecastsAvailable
    ) {
      dataQuality = "partial";
    } else {
      dataQuality = "good";
    }

    // Compute staleness summary from driver dates
    const staleSources = driverData.drivers
      .filter((d) => d.source === "stale")
      .map((d) => {
        const daysStale = d.asOfDate
          ? Math.floor(
              (now.getTime() - new Date(d.asOfDate).getTime()) /
                (1000 * 60 * 60 * 24),
            )
          : null;
        const slaMap: Record<string, number> = {
          Markets: 3,
          VIX: 3,
          Crush: 5,
          China: 5,
          Tariffs: 45,
          "Trump Effect": 7,
        };
        return { driver: d.name, daysStale, sla: slaMap[d.name] ?? 3 };
      });

    const brief: VegasBrief = {
      generatedAt: now.toISOString(),
      asOfDate,

      tldr: generateTLDR(price, fcHorizons, driverData),
      recommendation: recommendation.text,
      recommendationColor: recommendation.color,

      price,
      forecasts: fcHorizons,
      forecastsAvailable,

      drivers: driverData.drivers,
      driversSummary: driverData.summary,

      correlations,
      policyContext,

      keyRisks: getKeyRisks(driverData),
      keyPositives: getKeyPositives(driverData),

      eventPulse,
      overrideReason: recommendation.overrideReason,

      dataIssues: driverData.dataIssues,
      stalenessWarnings: driverData.stalenessWarnings,
      dataQuality,
      dataStaleness: {
        allFresh: staleSources.length === 0,
        staleSources,
      },
    };

    return NextResponse.json(brief);
  } catch (error) {
    console.error("Vegas brief generation failed:", error);
    return NextResponse.json(
      {
        error: "Brief generation failed",
        details: String(error),
      },
      { status: 500 },
    );
  }
}
