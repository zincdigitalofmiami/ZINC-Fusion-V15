import { NextResponse } from "next/server";
import { query } from "@/lib/db";
import { getZlLiveSnapshot } from "@/lib/zl-live-snapshot";
import { resolveZlSentimentForAggregation } from "@/lib/sentiment-news";
import {
  buildTrumpEffectPayload,
  type ConfirmationInputs,
  type ExecutiveActionRow,
  type TrumpFeatureRow,
  type ZlResponseInputs,
} from "./trump-effect";

export const dynamic = "force-dynamic";
const TRUMP_FEATURE_STALE_DAYS = 7;
const DAY_MS = 24 * 60 * 60 * 1000;
const CORRELATION_LOOKBACK = 64;

interface CotMetricsRow {
  event_date: string;
  open_interest: string | null;
  managed_money_long: string | null;
  managed_money_short: string | null;
  managed_money_net: string | null;
  managed_money_net_pct_oi: number | null;
  prod_merc_long: string | null;
  prod_merc_short: string | null;
  prod_merc_net: string | null;
  prod_merc_net_pct_oi: number | null;
  swap_long: string | null;
  swap_short: string | null;
  swap_net: string | null;
  mu: string | null;
  sd: string | null;
  n: string | null;
  zscore: string | null;
  percentile: string | null;
}

interface CotHistoryRow {
  event_date: string;
  managed_money_net: string | null;
  prod_merc_net: string | null;
  swap_net: string | null;
}

interface CrudeLatestRow {
  event_date: string;
  close: number;
  ret_5d: string | null;
}

interface CrudeCorrRow {
  corr: number | null;
}

interface SentimentInputRow {
  headline: string | null;
  summary: string | null;
  content: string | null;
  source: string | null;
  zl_sentiment: string | null;
  specialist_tags: string[] | null;
}

export function countSentimentRows(rows: readonly SentimentInputRow[]) {
  return rows.reduce(
    (counts, row) => {
      const resolved = resolveZlSentimentForAggregation(
        row.zl_sentiment,
        row.headline,
        row.summary || row.content,
        row.source,
        row.specialist_tags,
      );
      if (!resolved.includeInCounts) {
        return counts;
      }

      if (resolved.sentiment === "bullish") counts.bullish += 1;
      else if (resolved.sentiment === "bearish") counts.bearish += 1;
      return counts;
    },
    { bullish: 0, bearish: 0 },
  );
}

function toNumber(value: number | string | null | undefined, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function formatCorrelationDirection(corr: number): string {
  if (corr >= 0.7) return "Strong positive";
  if (corr >= 0.4) return "Moderate positive";
  if (corr >= 0.1) return "Weak positive";
  if (corr > -0.1) return "Flat";
  if (corr > -0.4) return "Weak negative";
  if (corr > -0.7) return "Moderate negative";
  return "Strong negative";
}

function crudeImplicationFromCorrelation(corr: number): string {
  if (corr >= 0.4) {
    return "Energy-biofuel linkage is active. Crude rallies are likely to keep pressuring soybean oil.";
  }
  if (corr >= 0.1) {
    return "Crude is leaning supportive. Watch energy headlines because spillover into soybean oil is still present.";
  }
  if (corr > -0.1) {
    return "The crude link is muted right now. Soybean oil is trading more on its own fundamentals.";
  }
  return "Crude and soybean oil are moving apart. Treat energy shocks as a secondary input until the link tightens again.";
}

/* ── Fear & Greed composite ────────────────────────────────── */

function clamp(v: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, v));
}

type FearGreedComponentKey =
  | "vix"
  | "oil"
  | "uncertainty"
  | "inflation"
  | "iranWar"
  | "news"
  | "positioning"
  | "sentiment"
  | "zlTrend"
  | "dailyShock"
  | "china"
  | "neural";

type FearGreedComponent = {
  score: number;
  weight: number;
  raw: number;
};

const FEAR_GREED_COMPONENT_LABELS: Record<FearGreedComponentKey, string> = {
  vix: "VIX stress",
  oil: "oil shock",
  uncertainty: "macro uncertainty",
  inflation: "inflation expectations",
  iranWar: "Iran-war flow",
  news: "macro news velocity",
  positioning: "fund positioning",
  sentiment: "headline sentiment",
  zlTrend: "ZL price trend",
  dailyShock: "daily move shock",
  china: "China trade friction",
  neural: "neural geopolitical signal",
};

/** VIX → 0-100 greed scale: 12→100, 20→60, 30→20, 50+→0 */
function mapVixToFearGreed(vix: number): number {
  if (vix < 12) return 100;
  if (vix < 20) return clamp(100 - ((vix - 12) / 8) * 40, 60, 100);
  if (vix < 30) return clamp(60 - ((vix - 20) / 10) * 40, 20, 60);
  if (vix < 50) return clamp(20 - ((vix - 30) / 20) * 20, 0, 20);
  return 0;
}

/**
 * Buyer-centric price trend score:
 * - Rising ZL = worse for buyers (lower score)
 * - Falling ZL = better for buyers (higher score)
 */
function mapZlTrendToFearGreed(ret5d: number | null): number {
  if (ret5d == null || !Number.isFinite(ret5d)) return 50;
  if (ret5d <= -5) return 62;
  if (ret5d <= -2) return 56;
  if (ret5d <= 0) return 45;
  if (ret5d <= 2) return 34;
  if (ret5d <= 5) return 22;
  if (ret5d <= 10) return 12;
  return 6;
}

/**
 * Oversized daily moves are bad for execution regardless of direction.
 * Ratio compares absolute 1d move against expected daily sigma from 21d realized vol.
 */
function mapDailyShockToFearGreed(
  ret1dPct: number | null,
  realized21dPct: number | null,
): number {
  if (
    ret1dPct == null ||
    !Number.isFinite(ret1dPct) ||
    realized21dPct == null ||
    !Number.isFinite(realized21dPct)
  ) {
    return 50;
  }

  const dailySigmaPct = Math.max(realized21dPct / Math.sqrt(252), 0.4);
  const ratio = Math.abs(ret1dPct) / dailySigmaPct;

  if (ratio <= 0.75) return 58;
  if (ratio <= 1.25) return 42;
  if (ratio <= 1.75) return 28;
  if (ratio <= 2.5) return 14;
  return 6;
}

function mapChinaFrictionToFearGreed(chinaTradeFrictionCount: number): number {
  if (chinaTradeFrictionCount <= 1) return 50;
  if (chinaTradeFrictionCount <= 4) return 38;
  if (chinaTradeFrictionCount <= 8) return 26;
  if (chinaTradeFrictionCount <= 14) return 14;
  return 6;
}

function mapNeuralToFearGreed(
  neuralSignal: number | null,
  neuralConfidence: number | null,
): number {
  if (neuralSignal == null || !Number.isFinite(neuralSignal)) return 40;

  const confidence =
    neuralConfidence != null && Number.isFinite(neuralConfidence)
      ? clamp(neuralConfidence, 0, 1)
      : 0.5;
  const magnitude = Math.min(1, Math.abs(neuralSignal));
  const directionalPenalty = neuralSignal > 0 ? 14 : 3;
  const score = 52 - magnitude * 45 * (0.5 + confidence * 0.5) - directionalPenalty;
  return clamp(Math.round(score), 3, 70);
}

function formatDriverList(labels: string[]): string {
  if (labels.length === 0) return "macro pressure";
  if (labels.length === 1) return labels[0];
  if (labels.length === 2) return `${labels[0]} and ${labels[1]}`;
  return `${labels[0]}, ${labels[1]}, and ${labels[2]}`;
}

function buildFearGreedInterpretation(
  score: number,
  components: Record<FearGreedComponentKey, FearGreedComponent>,
): string {
  const rankedContributions = (Object.entries(components) as [
    FearGreedComponentKey,
    FearGreedComponent,
  ][])
    .map(([key, component]) => ({
      key,
      contribution: (component.score - 50) * component.weight,
    }))
    .sort((a, b) => a.contribution - b.contribution);

  const dominantDrags = rankedContributions
    .filter((entry) => entry.contribution < 0)
    .slice(0, 3)
    .map((entry) => FEAR_GREED_COMPONENT_LABELS[entry.key]);
  const dragSummary = formatDriverList(dominantDrags);
  const macroStressStillHigh =
    components.uncertainty.score <= 25 ||
    components.iranWar.score <= 25 ||
    components.inflation.score <= 25 ||
    components.vix.score <= 30 ||
    components.zlTrend.score <= 25;

  if (score <= 20) {
    return `Risk-off conditions are extreme; ${dragSummary} are driving the composite lower. Assume procurement pressure remains elevated until these drags ease.`;
  }
  if (score <= 45) {
    return `Risk tone is defensive; ${dragSummary} are the dominant drags right now. Treat rebounds as fragile unless these inputs improve.`;
  }
  if (score <= 58 && macroStressStillHigh) {
    return `The headline score sits near neutral, but regime risk is not balanced; ${dragSummary} still show material stress. Use this as a caution signal, not a green light.`;
  }
  if (score <= 58) {
    return "Signals are mixed and close to neutral. Use price structure and positioning for tactical timing.";
  }
  if (score <= 75) {
    return "Risk appetite is elevated, but monitor macro stress inputs for reversal risk.";
  }
  return "Risk appetite appears stretched; avoid treating this alone as a timing trigger.";
}

function computeFearGreed(
  vix: number | null,
  mmPercentile: number | null,
  bullish: number,
  bearish: number,
  uncertaintyIndex: number | null,
  inflationExpectation: number | null,
  crudeRet5d: number | null,
  iranWarNewsCount: number,
  macroNewsCount: number,
  zlRet5d: number | null,
  zlRet1d: number | null,
  realized21d: number | null,
  chinaTradeFrictionCount: number,
  neuralSignal: number | null,
  neuralConfidence: number | null,
) {
  const total = bullish + bearish;
  const sentimentRaw = total > 0 ? bullish / total : 0.5;
  const vixScore = vix != null ? mapVixToFearGreed(vix) : 50;
  const posScore = clamp(mmPercentile ?? 50, 0, 100);
  const sentScore = clamp(sentimentRaw * 100, 0, 100);

  const uncertaintyScore =
    uncertaintyIndex == null
      ? 45
      : uncertaintyIndex < 80
        ? 70
        : uncertaintyIndex < 120
          ? 58
          : uncertaintyIndex < 170
            ? 42
            : uncertaintyIndex < 220
              ? 25
              : uncertaintyIndex < 280
                ? 12
                : 6;

  const inflationScore =
    inflationExpectation == null
      ? 45
      : inflationExpectation < 1.8
        ? 62
        : inflationExpectation < 2.1
          ? 52
          : inflationExpectation < 2.3
            ? 40
            : inflationExpectation < 2.5
              ? 30
              : inflationExpectation < 2.7
                ? 20
                : inflationExpectation < 3
                  ? 12
                  : 6;

  const oilScore =
    crudeRet5d == null
      ? 45
      : crudeRet5d <= -10
        ? 48
        : crudeRet5d <= -5
          ? 46
          : crudeRet5d <= 0
            ? 44
            : crudeRet5d <= 3
              ? 45
              : crudeRet5d <= 6
                ? 28
                : crudeRet5d <= 10
                  ? 16
                  : 8;

  const iranWarScore =
    iranWarNewsCount <= 0
      ? 56
      : iranWarNewsCount <= 2
        ? 46
        : iranWarNewsCount <= 5
          ? 30
          : iranWarNewsCount <= 9
            ? 18
            : iranWarNewsCount <= 14
              ? 10
              : 4;

  const newsScore =
    macroNewsCount <= 5
      ? 58
      : macroNewsCount <= 12
        ? 46
        : macroNewsCount <= 20
          ? 34
          : macroNewsCount <= 30
            ? 24
            : 14;

  const zlTrendScore = mapZlTrendToFearGreed(zlRet5d);
  const dailyShockScore = mapDailyShockToFearGreed(zlRet1d, realized21d);
  const chinaScore = mapChinaFrictionToFearGreed(chinaTradeFrictionCount);
  const neuralScore = mapNeuralToFearGreed(neuralSignal, neuralConfidence);

  const components: Record<FearGreedComponentKey, FearGreedComponent> = {
    vix: { score: Math.round(vixScore), weight: 0.13, raw: vix ?? 0 },
    oil: { score: Math.round(oilScore), weight: 0.07, raw: crudeRet5d ?? 0 },
    uncertainty: {
      score: Math.round(uncertaintyScore),
      weight: 0.16,
      raw: uncertaintyIndex ?? 0,
    },
    inflation: {
      score: Math.round(inflationScore),
      weight: 0.15,
      raw: inflationExpectation ?? 0,
    },
    iranWar: {
      score: Math.round(iranWarScore),
      weight: 0.14,
      raw: iranWarNewsCount,
    },
    news: { score: Math.round(newsScore), weight: 0.06, raw: macroNewsCount },
    positioning: {
      score: Math.round(posScore),
      weight: 0.03,
      raw: mmPercentile ?? 50,
    },
    sentiment: {
      score: Math.round(sentScore),
      weight: 0.02,
      raw: sentimentRaw,
    },
    zlTrend: {
      score: Math.round(zlTrendScore),
      weight: 0.08,
      raw: zlRet5d ?? 0,
    },
    dailyShock: {
      score: Math.round(dailyShockScore),
      weight: 0.05,
      raw: zlRet1d ?? 0,
    },
    china: {
      score: Math.round(chinaScore),
      weight: 0.06,
      raw: chinaTradeFrictionCount,
    },
    neural: {
      score: Math.round(neuralScore),
      weight: 0.05,
      raw: neuralSignal ?? 0,
    },
  };

  const totalWeight = Object.values(components).reduce(
    (sum, component) => sum + component.weight,
    0,
  );
  const weightedScore = Object.values(components).reduce(
    (sum, component) => sum + component.score * component.weight,
    0,
  );
  const composite = Math.round(weightedScore / totalWeight);

  const score = clamp(composite, 0, 100);

  const zone =
    score <= 20 ? "extreme_fear"
    : score <= 45 ? "fear"
    : score <= 58 ? "neutral"
    : score <= 75 ? "greed"
    : "extreme_greed";

  const label =
    score <= 20 ? "Extreme Fear"
    : score <= 45 ? "Fear"
    : score <= 58 ? "Neutral"
    : score <= 75 ? "Greed"
    : "Extreme Greed";

  const interpretation = buildFearGreedInterpretation(score, components);

  return {
    score,
    zone,
    label,
    interpretation,
    components,
  };
}

/* ── Route handler ─────────────────────────────────────────── */

export async function GET() {
  try {
    // Wrap each query so a single failure doesn't take down the whole endpoint
    const safe = async <T,>(p: Promise<T[]>): Promise<T[]> => {
      try { return await p; } catch (e) { console.error('[metrics] query failed:', e); return []; }
    };
    const safeValue = async <T,>(p: Promise<T>): Promise<T | null> => {
      try { return await p; } catch (e) { console.error('[metrics] value fetch failed:', e); return null; }
    };

    const [
      livePriceSnapshot,
      priceResult,
      returnsResult,
      rvolResult,
      cotResult,
      cotHistoryResult,
      crudeLatestResult,
      crudeCorrelationResult,
      maResult,
      rsiResult,
      vixResult,
      ovxResult,
      uncertaintyResult,
      inflationExpectationResult,
      crushResult,
      signalsResult,
      trumpResult,
      sentimentRatioResult,
      iranWarNewsResult,
      macroNewsResult,
      chinaTradeFrictionNewsResult,
    ] = await Promise.all([
      // 1. Current ZL price from the serving contract.
      safeValue(getZlLiveSnapshot()),

      // 2. Latest ZL daily row for open interest and hard fallback.
      safe(query<{
        event_date: string;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: string;
        open_interest: string;
      }>(
        `SELECT event_date::text, open, high, low, close, volume, open_interest
         FROM mkt.futures_1d
         WHERE symbol = 'ZL' AND close IS NOT NULL
         ORDER BY event_date DESC LIMIT 1`,
      )),

      // 3. Returns (5d, 21d, 63d)
      safe(query<{
        close: number;
        ret_1d: string;
        ret_5d: string;
        ret_21d: string;
        ret_63d: string;
      }>(
        `WITH ordered AS (
           SELECT event_date,
                  close,
                  LAG(close,  1) OVER (ORDER BY event_date) as c1,
                  LAG(close,  5) OVER (ORDER BY event_date) as c5,
                  LAG(close, 21) OVER (ORDER BY event_date) as c21,
                  LAG(close, 63) OVER (ORDER BY event_date) as c63
           FROM mkt.futures_1d
           WHERE symbol = 'ZL' AND close IS NOT NULL
         )
         SELECT close,
                ROUND(((close - c1)  / NULLIF(c1, 0)  * 100)::numeric, 2) as ret_1d,
                ROUND(((close - c5)  / NULLIF(c5, 0)  * 100)::numeric, 2) as ret_5d,
                ROUND(((close - c21) / NULLIF(c21, 0) * 100)::numeric, 2) as ret_21d,
                ROUND(((close - c63) / NULLIF(c63, 0) * 100)::numeric, 2) as ret_63d
         FROM ordered
         ORDER BY event_date DESC
         LIMIT 1`,
      )),

      // 4. 21-day realized volatility (annualized)
      safe(query<{ rvol_21d: string }>(
        `WITH lr AS (
           SELECT LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) as r
           FROM mkt.futures_1d WHERE symbol = 'ZL' AND close IS NOT NULL
           ORDER BY event_date DESC LIMIT 30
         )
         SELECT ROUND((STDDEV(r) * SQRT(252) * 100)::numeric, 2) as rvol_21d
         FROM lr WHERE r IS NOT NULL`,
      )),

      // 5. Latest COT snapshot + positioning statistics.
      safe(query<CotMetricsRow>(
        `WITH stats AS (
           SELECT AVG(managed_money_net) AS mu,
                  STDDEV(managed_money_net) AS sd,
                  COUNT(*) AS n
           FROM pos.cftc_1w
           WHERE symbol = 'ZL'
         ),
         latest AS (
           SELECT event_date::text AS event_date,
                  open_interest::text AS open_interest,
                  managed_money_long::text AS managed_money_long,
                  managed_money_short::text AS managed_money_short,
                  managed_money_net::text AS managed_money_net,
                  managed_money_net_pct_oi::float8 AS managed_money_net_pct_oi,
                  prod_merc_long::text AS prod_merc_long,
                  prod_merc_short::text AS prod_merc_short,
                  prod_merc_net::text AS prod_merc_net,
                  prod_merc_net_pct_oi::float8 AS prod_merc_net_pct_oi,
                  swap_long::text AS swap_long,
                  swap_short::text AS swap_short,
                  swap_net::text AS swap_net
           FROM pos.cftc_1w
           WHERE symbol = 'ZL'
           ORDER BY event_date DESC
           LIMIT 1
         ),
         prank AS (
           SELECT COUNT(*)::float
                    / NULLIF(
                        (SELECT COUNT(*) FROM pos.cftc_1w WHERE symbol = 'ZL'),
                        0
                      ) AS pctile
           FROM pos.cftc_1w
           WHERE symbol = 'ZL'
             AND managed_money_net < (
               SELECT managed_money_net
               FROM pos.cftc_1w
               WHERE symbol = 'ZL'
               ORDER BY event_date DESC
               LIMIT 1
             )
         )
         SELECT l.event_date,
                l.open_interest,
                l.managed_money_long,
                l.managed_money_short,
                l.managed_money_net,
                l.managed_money_net_pct_oi,
                l.prod_merc_long,
                l.prod_merc_short,
                l.prod_merc_net,
                l.prod_merc_net_pct_oi,
                l.swap_long,
                l.swap_short,
                l.swap_net,
                ROUND(s.mu::numeric, 0)::text AS mu,
                ROUND(s.sd::numeric, 0)::text AS sd,
                s.n::text AS n,
                ROUND(
                  (
                    NULLIF(l.managed_money_net, '')::numeric - s.mu::numeric
                  ) / NULLIF(s.sd, 0)::numeric,
                  3
                )::text AS zscore,
                ROUND((COALESCE(p.pctile, 0) * 100)::numeric, 1)::text AS percentile
         FROM latest l
         CROSS JOIN stats s
         LEFT JOIN prank p ON TRUE`,
      )),

      // 6. Recent COT history for the participant cards.
      safe(query<CotHistoryRow>(
        `SELECT event_date::text AS event_date,
                managed_money_net::text AS managed_money_net,
                prod_merc_net::text AS prod_merc_net,
                swap_net::text AS swap_net
         FROM pos.cftc_1w
         WHERE symbol = 'ZL'
         ORDER BY event_date DESC
         LIMIT 12`,
      )),

      // 7. Latest crude oil daily snapshot for the biofuel cross-card.
      safe(query<CrudeLatestRow>(
        `WITH ordered AS (
           SELECT event_date,
                  close,
                  LAG(close, 5) OVER (ORDER BY event_date) AS close_5d_ago
           FROM mkt.futures_1d
           WHERE symbol = 'CL' AND close IS NOT NULL
         )
         SELECT event_date::text AS event_date,
                close::float8 AS close,
                ROUND(
                  ((close - close_5d_ago) / NULLIF(close_5d_ago, 0) * 100)::numeric,
                  2
                )::text AS ret_5d
         FROM ordered
         ORDER BY event_date DESC
         LIMIT 1`,
      )),

      // 8. 63-trading-day rolling correlation on log returns: ZL vs CL.
      safe(query<CrudeCorrRow>(
        `WITH zl AS (
           SELECT event_date,
                  LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) AS ret
           FROM mkt.futures_1d
           WHERE symbol = 'ZL'
           ORDER BY event_date DESC
           LIMIT ${CORRELATION_LOOKBACK}
         ),
         cl AS (
           SELECT event_date,
                  LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) AS ret
           FROM mkt.futures_1d
           WHERE symbol = 'CL'
           ORDER BY event_date DESC
           LIMIT ${CORRELATION_LOOKBACK}
         )
         SELECT CORR(zl.ret, cl.ret)::float8 AS corr
         FROM zl
         JOIN cl ON zl.event_date = cl.event_date
         WHERE zl.ret IS NOT NULL AND cl.ret IS NOT NULL`,
      )),

      // 9. Moving averages
      safe(query<{
        close: string;
        sma20: string;
        sma50: string;
        sma200: string;
      }>(
        `WITH ordered AS (
           SELECT event_date,
                  close,
                  AVG(close) OVER (ORDER BY event_date ROWS BETWEEN  19 PRECEDING AND CURRENT ROW) as sma20,
                  AVG(close) OVER (ORDER BY event_date ROWS BETWEEN  49 PRECEDING AND CURRENT ROW) as sma50,
                  AVG(close) OVER (ORDER BY event_date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) as sma200
           FROM mkt.futures_1d
           WHERE symbol = 'ZL' AND close IS NOT NULL
         )
         SELECT ROUND(close::numeric, 2) as close,
                ROUND(sma20::numeric, 2) as sma20,
                ROUND(sma50::numeric, 2) as sma50,
                ROUND(sma200::numeric, 2) as sma200
         FROM ordered
         ORDER BY event_date DESC
         LIMIT 1`,
      )),

      // 10. Compute RSI-14
      safe(query<{ rsi_14: string }>(
        `WITH changes AS (
           SELECT close - LAG(close) OVER (ORDER BY event_date) as chg
           FROM mkt.futures_1d WHERE symbol = 'ZL' AND close IS NOT NULL
           ORDER BY event_date DESC LIMIT 30
         ),
         gl AS (
           SELECT CASE WHEN chg > 0 THEN chg ELSE 0 END as gain,
                  CASE WHEN chg < 0 THEN ABS(chg) ELSE 0 END as loss
           FROM changes WHERE chg IS NOT NULL
         )
         SELECT ROUND((100 - 100 / (1 + AVG(gain) / NULLIF(AVG(loss), 0)))::numeric, 1) as rsi_14
         FROM gl`,
      )),

      // 11. VIX + z-score (1y)
      safe(query<{ vix: string; vix_avg_1y: string; vix_z: string }>(
        `WITH stats AS (
           SELECT AVG(value) as mu, STDDEV(value) as sd
           FROM econ.vol_indices_1d WHERE series_id = 'VIXCLS'
           AND event_date > CURRENT_DATE - INTERVAL '1 year'
         ),
         latest AS (
           SELECT value FROM econ.vol_indices_1d WHERE series_id = 'VIXCLS'
           ORDER BY event_date DESC LIMIT 1
         )
         SELECT ROUND(l.value::numeric, 2) as vix,
                ROUND(s.mu::numeric, 2) as vix_avg_1y,
                ROUND(((l.value - s.mu) / NULLIF(s.sd, 0))::numeric, 3) as vix_z
         FROM stats s, latest l`,
      )),

      // 12. OVX (oil volatility)
      safe(query<{ ovx: string }>(
        `SELECT ROUND(value::numeric, 2) as ovx
         FROM econ.vol_indices_1d WHERE series_id = 'OVXCLS'
         ORDER BY event_date DESC LIMIT 1`,
      )),

      // 12b. Uncertainty index (monthly)
      safe(query<{ value: string; event_date: string }>(
        `SELECT value::text AS value, event_date::text AS event_date
         FROM econ.vol_indices_1d
         WHERE series_id = 'USEPUINDXM' AND value IS NOT NULL
         ORDER BY event_date DESC
         LIMIT 1`,
      )),

      // 12c. Inflation expectations (5Y breakeven)
      safe(query<{ value: string; event_date: string }>(
        `SELECT value::text AS value, event_date::text AS event_date
         FROM econ.inflation_1d
         WHERE series_id = 'T5YIE' AND value IS NOT NULL
         ORDER BY event_date DESC
         LIMIT 1`,
      )),

      // 13. Board crush + oil share z-scores
      safe(query<{
        crush_now: string;
        crush_z: string;
        os_now: string;
        os_z: string;
        n: string;
      }>(
        `WITH stats AS (
           SELECT AVG(board_crush) as mu, STDDEV(board_crush) as sd,
                  AVG(oil_share) as os_mu, STDDEV(oil_share) as os_sd,
                  COUNT(*) as n
           FROM analytics.board_crush_1d
         ),
         latest AS (
           SELECT board_crush as bc, oil_share as os
           FROM analytics.board_crush_1d ORDER BY trade_date DESC LIMIT 1
         )
         SELECT ROUND(l.bc::numeric, 4) as crush_now,
                ROUND(((l.bc::numeric - s.mu::numeric) / NULLIF(s.sd::numeric, 0))::numeric, 3) as crush_z,
                ROUND(l.os::numeric, 4) as os_now,
                ROUND(((l.os::numeric - s.os_mu::numeric) / NULLIF(s.os_sd::numeric, 0))::numeric, 3) as os_z,
                s.n
         FROM stats s, latest l`,
      )),

      // 14. Specialist signals (latest per bucket)
      safe(query<{
        bucket: string;
        signal_1: number;
        signal_2: number;
        confidence: number;
        model_type: string;
        as_of_date: string;
        abstained: boolean;
      }>(
        `SELECT DISTINCT ON (bucket)
                bucket, signal_1, signal_2, confidence, model_type,
                as_of_date::text, abstained
         FROM training.specialist_signals_1d
         ORDER BY bucket, as_of_date DESC`,
      )),

      // 15. Trump Effect (latest row)
      safe(query<TrumpFeatureRow>(
        `WITH latest_any AS (
           SELECT as_of_date::text                              AS as_of_date,
                  (features->>'weighted_action_score')::float8 AS weighted_action_score,
                  (features->>'neural_signal')::float8         AS neural_signal,
                  (features->>'neural_confidence')::float8     AS neural_confidence,
                  (features->>'action_velocity')::float8       AS action_velocity,
                  (features->>'action_acceleration')::float8   AS action_acceleration,
                  (features->>'total_actions_7d')::int         AS total_actions_7d,
                  (features->>'total_actions_30d')::int        AS total_actions_30d,
                  (features->>'eo_count_7d')::int              AS eo_count_7d
           FROM training.specialist_features_trump_effect
           ORDER BY as_of_date DESC
           LIMIT 1
         )
         SELECT la.as_of_date,
                la.as_of_date                                  AS latest_any_as_of,
                CASE
                  WHEN la.weighted_action_score IS NOT NULL
                   AND la.action_velocity IS NOT NULL
                  THEN 'latest_valid'
                  ELSE 'latest_fallback'
                END::text                                      AS selection_mode,
                la.weighted_action_score,
                la.neural_signal,
                la.neural_confidence,
                la.action_velocity,
                la.action_acceleration,
                la.total_actions_7d,
                la.total_actions_30d,
                la.eo_count_7d
         FROM latest_any la`,
      )),

      // 16. News sentiment rows (7d) — scored with the same rules as the page headlines.
      safe(query<SentimentInputRow>(
        `SELECT headline, summary, content, source, zl_sentiment, specialist_tags
         FROM (
           SELECT headline,
                  summary,
                  content,
                  'ProFarmer'::text AS source,
                  NULL::text AS zl_sentiment,
                  COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags
           FROM alt.profarmer_news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'

           UNION ALL

           SELECT title AS headline,
                  CONCAT(document_type, ' — ', agency) AS summary,
                  NULL::text AS content,
                  COALESCE(source, 'Federal Register') AS source,
                  NULL::text AS zl_sentiment,
                  COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags
           FROM alt.legislation_1d
           WHERE event_date >= NOW() - INTERVAL '7 days'

           UNION ALL

           SELECT headline,
                  NULL::text AS summary,
                  content,
                  source,
                  zl_sentiment,
                  COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags
           FROM alt.policy_news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'

           UNION ALL

           SELECT headline,
                  NULL::text AS summary,
                  content,
                  source,
                  zl_sentiment,
                  COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags
           FROM alt.executive_actions_event
           WHERE event_date >= NOW() - INTERVAL '7 days'

           UNION ALL

           SELECT headline,
                  summary,
                  content,
                  source,
                  NULL::text AS zl_sentiment,
                  COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags
           FROM alt.econ_news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'

           UNION ALL

           SELECT headline,
                  NULL::text AS summary,
                  content,
                  source,
                  zl_sentiment,
                  COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags
           FROM econ.news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'
         ) sentiment_rows`,
      )),

      // 17. Iran-war / Hormuz headline velocity (7d)
      safe(query<{ count: number }>(
        `SELECT COUNT(*)::int as count
         FROM (
           SELECT headline, content
           FROM alt.policy_news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'

           UNION ALL

           SELECT headline, content
           FROM alt.econ_news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'

           UNION ALL

           SELECT headline, content
           FROM alt.profarmer_news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'
         ) n
         WHERE (
           headline ILIKE '%iran%' OR headline ILIKE '%israel%' OR headline ILIKE '%hormuz%'
           OR headline ILIKE '%strait of hormuz%' OR headline ILIKE '%middle east%'
           OR headline ILIKE '%war%' OR headline ILIKE '%missile%' OR headline ILIKE '%red sea%'
           OR content ILIKE '%iran%' OR content ILIKE '%hormuz%' OR content ILIKE '%war%'
         )`,
      )),

      // 18. Macro-risk news velocity (7d)
      safe(query<{ count: number }>(
        `SELECT COUNT(*)::int as count
         FROM (
           SELECT headline, content
           FROM alt.policy_news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'

           UNION ALL

           SELECT headline, content
           FROM alt.econ_news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'

           UNION ALL

           SELECT headline, content
           FROM alt.profarmer_news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'
         ) n
         WHERE (
           headline ILIKE '%inflation%' OR headline ILIKE '%cpi%' OR headline ILIKE '%ppi%'
           OR headline ILIKE '%interest rate%' OR headline ILIKE '%federal reserve%'
           OR headline ILIKE '%uncertainty%' OR headline ILIKE '%vix%' OR headline ILIKE '%volatility%'
           OR headline ILIKE '%crude%' OR headline ILIKE '%oil%'
           OR headline ILIKE '%iran%' OR headline ILIKE '%hormuz%' OR headline ILIKE '%war%'
           OR content ILIKE '%inflation%' OR content ILIKE '%interest rate%'
           OR content ILIKE '%uncertainty%' OR content ILIKE '%vix%'
           OR content ILIKE '%oil price%' OR content ILIKE '%iran%' OR content ILIKE '%war%'
         )`,
      )),

      // 19. China diplomacy/trade friction velocity (7d)
      safe(query<{ count: number }>(
        `SELECT COUNT(*)::int as count
         FROM (
           SELECT headline, content
           FROM alt.policy_news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'

           UNION ALL

           SELECT headline, content
           FROM alt.econ_news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'

           UNION ALL

           SELECT headline, content
           FROM alt.profarmer_news_event
           WHERE event_date >= NOW() - INTERVAL '7 days'
         ) n
         WHERE (
           (headline ILIKE '%china%' OR headline ILIKE '%beijing%' OR content ILIKE '%china%')
           AND (
             headline ILIKE '%trade%' OR headline ILIKE '%tariff%' OR headline ILIKE '%meeting%'
             OR headline ILIKE '%talk%' OR headline ILIKE '%summit%' OR headline ILIKE '%deal%'
             OR headline ILIKE '%import%' OR headline ILIKE '%export%' OR headline ILIKE '%buy%'
             OR headline ILIKE '%purchase%' OR headline ILIKE '%retaliat%' OR headline ILIKE '%ban%'
             OR content ILIKE '%soybean%' OR content ILIKE '%soy oil%' OR content ILIKE '%purchase%'
           )
         )`,
      )),
    ]);

    const latestDailyPrice = priceResult[0];
    const price = livePriceSnapshot
      ? {
          as_of: livePriceSnapshot.timestamp,
          close: livePriceSnapshot.price,
          open:
            livePriceSnapshot.source === "latest_price"
              ? null
              : livePriceSnapshot.open,
          high:
            livePriceSnapshot.source === "latest_price"
              ? null
              : livePriceSnapshot.high,
          low:
            livePriceSnapshot.source === "latest_price"
              ? null
              : livePriceSnapshot.low,
          volume:
            livePriceSnapshot.source === "latest_price"
              ? null
              : livePriceSnapshot.volume,
          source: livePriceSnapshot.source,
          live: livePriceSnapshot.live,
        }
      : latestDailyPrice
        ? {
            as_of: latestDailyPrice.event_date,
            close: latestDailyPrice.close,
            open: latestDailyPrice.open,
            high: latestDailyPrice.high,
            low: latestDailyPrice.low,
            volume: Number(latestDailyPrice.volume),
            source: "mkt_futures_1d",
            live: false,
          }
        : null;
    const returns = returnsResult[0];
    const rvol = rvolResult[0];
    const cot = cotResult[0] ?? null;
    const cotHistory = cotHistoryResult;
    const crudeLatest = crudeLatestResult[0] ?? null;
    const crudeCorrelation = crudeCorrelationResult[0] ?? null;
    const ma = maResult[0];
    const rsi = rsiResult[0];
    const vixData = vixResult[0];
    const ovxData = ovxResult[0];
    const uncertaintyData = uncertaintyResult[0] ?? null;
    const inflationData = inflationExpectationResult[0] ?? null;
    const crush = crushResult[0];
    const trump = trumpResult[0] ?? null;
    const sentimentCounts = countSentimentRows(sentimentRatioResult);
    const iranWarNewsCount = iranWarNewsResult[0]?.count ?? 0;
    const macroNewsCount = macroNewsResult[0]?.count ?? 0;
    const chinaTradeFrictionNewsCount =
      chinaTradeFrictionNewsResult[0]?.count ?? 0;
    const neuralSignal = trump?.neural_signal ?? null;
    const neuralConfidence = trump?.neural_confidence ?? null;
    const [trumpActions, trumpConfirmationRows, trumpZlResponseRows]: [
      ExecutiveActionRow[],
      ConfirmationInputs[],
      ZlResponseInputs[],
    ] =
      trump?.as_of_date
        ? await Promise.all([
            safe(
              query<ExecutiveActionRow>(
                `WITH action_events AS (
                   SELECT event_date::text AS event_date,
                          document_type,
                          zl_sentiment,
                          headline,
                          content
                   FROM alt.executive_actions_event
                   WHERE event_date >= ($1::date - INTERVAL '29 days')
                     AND event_date <= $1::date

                   UNION ALL

                   SELECT event_date::text AS event_date,
                          CASE
                            WHEN title ILIKE '%executive order%' THEN 'executive_order'
                            WHEN title ILIKE '%proclamation%' THEN 'proclamation'
                            WHEN title ILIKE '%memorandum%' THEN 'memorandum'
                            WHEN title ILIKE '%nomination%' OR title ILIKE '%appoint%' THEN 'nomination'
                            ELSE 'presidential_document'
                          END AS document_type,
                          NULL::text AS zl_sentiment,
                          title AS headline,
                          NULL::text AS content
                   FROM alt.legislation_1d
                   WHERE document_type = 'Presidential Document'
                     AND event_date >= ($1::date - INTERVAL '29 days')
                     AND event_date <= $1::date
                 )
                 SELECT event_date, document_type, zl_sentiment, headline, content
                 FROM action_events
                 ORDER BY event_date DESC`,
                [trump.as_of_date],
              ),
            ),
            safe(
              query<ConfirmationInputs>(
                `WITH date_window AS (
                   SELECT ($1::date - INTERVAL '6 days')::date AS start_date,
                          $1::date AS end_date
                 ),
                 policy_rows AS (
                   SELECT COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags,
                          COALESCE(headline, '')                     AS headline,
                          ''::text                                   AS summary,
                          COALESCE(content, '')                      AS content
                   FROM alt.policy_news_event, date_window w
                   WHERE event_date >= w.start_date AND event_date <= w.end_date

                   UNION ALL

                   SELECT COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags,
                          COALESCE(headline, '')                     AS headline,
                          COALESCE(summary, '')                      AS summary,
                          COALESCE(content, '')                      AS content
                   FROM alt.econ_news_event, date_window w
                   WHERE event_date >= w.start_date AND event_date <= w.end_date
                 ),
                 market_rows AS (
                   SELECT COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags,
                          COALESCE(headline, '')                     AS headline,
                          COALESCE(content, '')                      AS content
                   FROM econ.news_event, date_window w
                   WHERE event_date >= w.start_date AND event_date <= w.end_date
                 ),
                 regulatory_rows AS (
                   SELECT COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags,
                          COALESCE(title, '')                        AS title
                   FROM alt.legislation_1d, date_window w
                   WHERE event_date >= w.start_date
                     AND event_date <= w.end_date
                     AND document_type <> 'Presidential Document'
                 )
                 SELECT
                   (
                     SELECT COUNT(*)::int
                     FROM policy_rows p
                     WHERE (
                       p.specialist_tags && ARRAY['tariff','trump_effect','china','biofuel','fed','energy','crush']::text[]
                       OR (p.headline || ' ' || p.summary || ' ' || p.content) ~* '(tariff|trade|executive order|presidential|soybean oil|biofuel|renewable fuel|sanction|regulation)'
                     )
                   ) AS independent_policy_items_7d,
                   (
                     SELECT COUNT(*)::int
                     FROM market_rows m
                     WHERE (
                       m.specialist_tags && ARRAY['tariff','trump_effect','china','biofuel','fed','energy','crush']::text[]
                       OR (m.headline || ' ' || m.content) ~* '(tariff|trade|executive order|presidential|soybean oil|biofuel|renewable fuel|sanction|regulation)'
                     )
                   ) AS market_news_items_7d,
                   (
                     SELECT COUNT(*)::int
                     FROM regulatory_rows r
                     WHERE (
                       r.specialist_tags && ARRAY['tariff','trump_effect','china','biofuel','fed','energy','crush']::text[]
                       OR r.title ~* '(soybean|soy oil|biofuel|renewable fuel|tariff|trade|energy|commodity|regulation)'
                     )
                   ) AS regulatory_follow_through_7d`,
                [trump.as_of_date],
              ),
            ),
            safe(
              query<ZlResponseInputs>(
                `WITH anchor_close AS (
                   SELECT close::float8 AS close, event_date
                   FROM mkt.futures_1d
                   WHERE symbol = 'ZL'
                     AND close IS NOT NULL
                     AND event_date <= $1::date
                   ORDER BY event_date DESC
                   LIMIT 1
                 ),
                 prev_1d AS (
                   SELECT close::float8 AS close
                   FROM mkt.futures_1d
                   WHERE symbol = 'ZL'
                     AND close IS NOT NULL
                     AND event_date <= ($1::date - INTERVAL '1 day')
                   ORDER BY event_date DESC
                   LIMIT 1
                 ),
                 prev_5d AS (
                   SELECT close::float8 AS close
                   FROM mkt.futures_1d
                   WHERE symbol = 'ZL'
                     AND close IS NOT NULL
                     AND event_date <= ($1::date - INTERVAL '5 days')
                   ORDER BY event_date DESC
                   LIMIT 1
                 ),
                 start_7d AS (
                   SELECT close::float8 AS close
                   FROM mkt.futures_1d
                   WHERE symbol = 'ZL'
                     AND close IS NOT NULL
                     AND event_date <= ($1::date - INTERVAL '6 days')
                   ORDER BY event_date DESC
                   LIMIT 1
                 ),
                 rvol AS (
                   WITH lr AS (
                     SELECT LN(close / NULLIF(LAG(close) OVER (ORDER BY event_date), 0)) AS r
                     FROM mkt.futures_1d
                     WHERE symbol = 'ZL'
                       AND close IS NOT NULL
                       AND event_date <= $1::date
                     ORDER BY event_date DESC
                     LIMIT 30
                   )
                   SELECT (STDDEV(r) * SQRT(252) * 100)::float8 AS realized_vol_21d
                   FROM lr
                   WHERE r IS NOT NULL
                 )
                 SELECT ac.close                                            AS close_anchor,
                        p1.close                                            AS close_prev_1d,
                        p5.close                                            AS close_prev_5d,
                        s7.close                                            AS close_start_7d,
                        r.realized_vol_21d                                  AS realized_vol_21d,
                        ac.event_date::text                                 AS anchor_price_date
                 FROM anchor_close ac
                 LEFT JOIN prev_1d p1 ON TRUE
                 LEFT JOIN prev_5d p5 ON TRUE
                 LEFT JOIN start_7d s7 ON TRUE
                 LEFT JOIN rvol r ON TRUE`,
                [trump.as_of_date],
              ),
            ),
          ])
        : [[], [], []];
    const trumpEffect = buildTrumpEffectPayload(
      trump,
      trumpActions,
      trumpConfirmationRows[0] ?? null,
      trumpZlResponseRows[0] ?? null,
    );
    const parseDateOnly = (value: string | null | undefined): Date | null => {
      if (!value) return null;
      const parsed = new Date(value);
      if (Number.isNaN(parsed.getTime())) return null;
      return new Date(
        Date.UTC(
          parsed.getUTCFullYear(),
          parsed.getUTCMonth(),
          parsed.getUTCDate(),
          0,
          0,
          0,
          0,
        ),
      );
    };
    const nowUtc = new Date();
    const todayUtc = new Date(
      Date.UTC(
        nowUtc.getUTCFullYear(),
        nowUtc.getUTCMonth(),
        nowUtc.getUTCDate(),
        0,
        0,
        0,
        0,
      ),
    );
    const selectedAsOf = parseDateOnly(trump?.as_of_date);
    const latestAnyAsOf = parseDateOnly(trump?.latest_any_as_of);
    const selectedAgeDays =
      selectedAsOf != null
        ? Math.max(
            0,
            Math.floor((todayUtc.getTime() - selectedAsOf.getTime()) / DAY_MS),
          )
        : null;
    const latestAnyAgeDays =
      latestAnyAsOf != null
        ? Math.max(
            0,
            Math.floor((todayUtc.getTime() - latestAnyAsOf.getTime()) / DAY_MS),
          )
        : null;
    const trumpEffectStatus = trump
      ? {
          selected_as_of: trump.as_of_date,
          latest_any_as_of: trump.latest_any_as_of,
          selection_mode: trump.selection_mode,
          selected_age_days: selectedAgeDays,
          latest_any_age_days: latestAnyAgeDays,
          selected_is_stale:
            selectedAgeDays != null && selectedAgeDays > TRUMP_FEATURE_STALE_DAYS,
          latest_row_missing_score: trump.weighted_action_score == null,
          latest_row_missing_velocity: trump.action_velocity == null,
        }
      : null;

    // Compute composite sentiment score from specialist signals
    const signals = signalsResult.filter((s) => !s.abstained);
    const weightedSum = signals.reduce(
      (acc, s) => acc + s.signal_1 * s.confidence,
      0,
    );
    const totalConf = signals.reduce((acc, s) => acc + s.confidence, 0);
    const compositeSignal = totalConf > 0 ? weightedSum / totalConf : 0;

    // Trend status from MAs
    const priceNum = price?.close ?? null;
    const sma20 = ma ? Number(ma.sma20) : null;
    const sma50 = ma ? Number(ma.sma50) : null;
    const sma200 = ma ? Number(ma.sma200) : null;
    const aboveSma20 = priceNum != null && sma20 != null ? priceNum > sma20 : false;
    const aboveSma50 = priceNum != null && sma50 != null ? priceNum > sma50 : false;
    const aboveSma200 =
      priceNum != null && sma200 != null ? priceNum > sma200 : false;
    const trendScore =
      (aboveSma20 ? 1 : 0) + (aboveSma50 ? 1 : 0) + (aboveSma200 ? 1 : 0);
    const trend =
      priceNum == null || sma20 == null || sma50 == null || sma200 == null
        ? "unknown"
        : trendScore === 3
          ? "strong_uptrend"
          : trendScore === 2
            ? "uptrend"
            : trendScore === 1
              ? "mixed"
              : "downtrend";

    // Compute Fear & Greed composite
    const fearGreed = computeFearGreed(
      vixData ? Number(vixData.vix) : null,
      cot ? toNumber(cot.percentile, 50) : null,
      sentimentCounts.bullish,
      sentimentCounts.bearish,
      uncertaintyData ? toNumber(uncertaintyData.value) : null,
      inflationData ? toNumber(inflationData.value) : null,
      crudeLatest ? toNumber(crudeLatest.ret_5d) : null,
      iranWarNewsCount,
      macroNewsCount,
      returns ? toNumber(returns.ret_5d) : null,
      returns ? toNumber(returns.ret_1d) : null,
      rvol ? toNumber(rvol.rvol_21d) : null,
      chinaTradeFrictionNewsCount,
      neuralSignal,
      neuralConfidence,
    );

    const cotOpenInterest = cot ? toNumber(cot.open_interest) : 0;
    const managedMoneyNet = cot ? toNumber(cot.managed_money_net) : 0;
    const producersNet = cot ? toNumber(cot.prod_merc_net) : 0;
    const swapsNet = cot ? toNumber(cot.swap_net) : 0;

    const cotPayload = cot
      ? {
          as_of_date: cot.event_date,
          symbol: "ZL",
          latest: {
            open_interest: cotOpenInterest,
            managed_money: {
              long: toNumber(cot.managed_money_long),
              short: toNumber(cot.managed_money_short),
              net: managedMoneyNet,
              net_pct_oi:
                cot.managed_money_net_pct_oi != null
                  ? toNumber(cot.managed_money_net_pct_oi)
                  : cotOpenInterest > 0
                    ? Number(((managedMoneyNet / cotOpenInterest) * 100).toFixed(2))
                    : 0,
            },
            producers: {
              long: toNumber(cot.prod_merc_long),
              short: toNumber(cot.prod_merc_short),
              net: producersNet,
              net_pct_oi:
                cot.prod_merc_net_pct_oi != null
                  ? toNumber(cot.prod_merc_net_pct_oi)
                  : cotOpenInterest > 0
                    ? Number(((producersNet / cotOpenInterest) * 100).toFixed(2))
                    : 0,
            },
            swaps: {
              long: toNumber(cot.swap_long),
              short: toNumber(cot.swap_short),
              net: swapsNet,
              net_pct_oi:
                cotOpenInterest > 0
                  ? Number(((swapsNet / cotOpenInterest) * 100).toFixed(2))
                  : 0,
            },
          },
          history: cotHistory
            .map((row) => ({
              event_date: row.event_date,
              managed_money_net: toNumber(row.managed_money_net),
              prod_merc_net: toNumber(row.prod_merc_net),
              swap_net: toNumber(row.swap_net),
            }))
            .reverse(),
        }
      : null;

    const crudeCorrValue =
      crudeCorrelation?.corr != null && Number.isFinite(crudeCorrelation.corr)
        ? Number(crudeCorrelation.corr.toFixed(3))
        : null;

    return NextResponse.json({
      as_of: price?.as_of ?? latestDailyPrice?.event_date ?? null,

      price: {
        close: price?.close ?? null,
        open: price?.open ?? null,
        high: price?.high ?? null,
        low: price?.low ?? null,
        volume: price?.volume ?? null,
        open_interest: latestDailyPrice ? Number(latestDailyPrice.open_interest) : null,
        source: price?.source ?? null,
        live: price?.live ?? false,
      },

      returns: {
        ret_1d: returns ? Number(returns.ret_1d) : null,
        ret_5d: returns ? Number(returns.ret_5d) : null,
        ret_21d: returns ? Number(returns.ret_21d) : null,
        ret_63d: returns ? Number(returns.ret_63d) : null,
      },

      volatility: {
        realized_21d: rvol ? Number(rvol.rvol_21d) : null,
        vix: vixData ? Number(vixData.vix) : null,
        vix_avg_1y: vixData ? Number(vixData.vix_avg_1y) : null,
        vix_z: vixData ? Number(vixData.vix_z) : null,
        ovx: ovxData ? Number(ovxData.ovx) : null,
      },

      technicals: {
        rsi_14: rsi ? Number(rsi.rsi_14) : null,
        sma20,
        sma50,
        sma200,
        trend,
        above_sma20: aboveSma20,
        above_sma50: aboveSma50,
        above_sma200: aboveSma200,
      },

      positioning: {
        mm_net: cot ? toNumber(cot.managed_money_net) : null,
        mm_avg: cot ? toNumber(cot.mu) : null,
        mm_std: cot ? toNumber(cot.sd) : null,
        mm_zscore: cot ? toNumber(cot.zscore) : null,
        mm_percentile: cot ? toNumber(cot.percentile) : null,
        mm_pct_oi:
          cot
            ? cot.managed_money_net_pct_oi != null
              ? toNumber(cot.managed_money_net_pct_oi)
              : cotOpenInterest > 0
                ? Number(((managedMoneyNet / cotOpenInterest) * 100).toFixed(2))
                : 0
            : null,
        prod_net: cot ? producersNet : null,
        swap_net: cot ? swapsNet : null,
        history_weeks: cot ? toNumber(cot.n) : null,
      },

      cot: cotPayload,

      crudeCross: crudeLatest
        ? {
            as_of: crudeLatest.event_date,
            close: toNumber(crudeLatest.close),
            ret_5d: toNumber(crudeLatest.ret_5d),
            correlation_63d: crudeCorrValue,
            direction:
              crudeCorrValue != null
                ? formatCorrelationDirection(crudeCorrValue)
                : "Data pending",
            implication:
              crudeCorrValue != null
                ? crudeImplicationFromCorrelation(crudeCorrValue)
                : "Need synchronized ZL and crude daily history to calculate the live biofuel correlation.",
            lookback_days: CORRELATION_LOOKBACK - 1,
          }
        : null,

      crush: {
        board_crush: crush ? Number(crush.crush_now) : null,
        crush_zscore: crush ? Number(crush.crush_z) : null,
        oil_share: crush ? Number(crush.os_now) : null,
        oil_share_zscore: crush ? Number(crush.os_z) : null,
        sample_size: crush ? Number(crush.n) : null,
      },

      specialists: signals.map((s) => ({
        bucket: s.bucket,
        signal: Number(s.signal_1.toFixed(3)),
        signal_2:
          s.signal_2 == null ? null : Number(s.signal_2.toFixed(3)),
        confidence: Number(s.confidence.toFixed(2)),
        model_type: s.model_type,
        as_of: s.as_of_date,
      })),

      composite: {
        signal: Number(compositeSignal.toFixed(3)),
        contributing_models: signals.length,
        interpretation:
          compositeSignal > 0.3
            ? "bullish"
            : compositeSignal < -0.3
              ? "bearish"
              : "neutral",
      },

      fearGreed,

      trumpEffect,
      trumpEffectStatus,
    }, {
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    console.error("Metrics API error:", err);
    return NextResponse.json(
      { error: "Failed to compute metrics" },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
