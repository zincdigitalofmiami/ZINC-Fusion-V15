// frontend/src/lib/services/policy-service.ts
import { query } from "@/lib/db";
import {
  AgencyActivity,
  ExecutiveEvent,
  LegislationEvent,
  PolicyUncertaintyIndex,
  TariffDeadline,
  TariffComponents,
  TrumpEffectMetric,
  RegimeState,
} from "@/components/policy/types";

// ===========================================
// SCORING CONSTANTS (Matched to Python Logic)
// Source: src/fusion/features/trump_effect.py
// ===========================================

// EPU regime thresholds from Python feature engine
const EPU_THRESHOLDS = {
  LOW: 75,
  NORMAL: 125,
  ELEVATED: 175,
  HIGH: 250,
};

export interface PolicyNewsItem {
  id: number;
  event_date: string;
  headline: string;
  url: string | null;
  source: string | null;
  specialist_tags: string[];
  published_at: string | null;
}

export class PolicyService {
  /**
   * Fetches recent legislation events from the Federal Register
   */
  static async getLegislationEvents(limit = 100): Promise<LegislationEvent[]> {
    const sql = `
      SELECT
        id, event_date, document_number, title, agency,
        document_type, action, specialist_tags, url, source
      FROM alt.legislation_1d
      ORDER BY event_date DESC
      LIMIT $1
    `;
    const rows = await query<LegislationEvent>(sql, [limit]);
    return rows.map((row) => ({
      ...row,
      event_date: new Date(row.event_date).toISOString().split("T")[0],
    }));
  }

  /**
   * Fetches executive actions - only high-level presidential actions
   * (Executive Orders, Presidential Memoranda, Proclamations)
   */
  static async getExecutiveEvents(limit = 50): Promise<ExecutiveEvent[]> {
    const sql = `
      SELECT
        id, event_date, headline, content, url,
        document_type, zl_sentiment, specialist_tags
      FROM alt.executive_actions_event
      WHERE document_type IN ('executive_order', 'presidential_memorandum', 'proclamation')
        OR document_type IS NULL
      ORDER BY event_date DESC
      LIMIT $1
    `;
    const rows = await query<ExecutiveEvent>(sql, [limit]);
    return rows.map((row) => ({
      ...row,
      event_date: new Date(row.event_date).toISOString().split("T")[0],
    }));
  }

  /**
   * Fetches upcoming tariff and trade policy deadlines
   */
  static async getTariffDeadlines(): Promise<TariffDeadline[]> {
    const sql = `
      SELECT
        id, deadline_name, deadline_date,
        (deadline_date - CURRENT_DATE)::int as days_to_expiry,
        renewal_probability, policy_type, description, is_active
      FROM alt.tariff_deadlines_static
      WHERE is_active = true
      ORDER BY (deadline_date - CURRENT_DATE) ASC
    `;
    const rows = await query<TariffDeadline>(sql);
    return rows.map((row) => ({
      ...row,
      deadline_date: new Date(row.deadline_date).toISOString().split("T")[0],
      renewal_probability: row.renewal_probability
        ? Number(row.renewal_probability)
        : null,
    }));
  }

  /**
   * Returns real totals for the header summary line.
   */
  static async getSummaryCounts(): Promise<{
    uniqueAgencies: number;
    activeEvents: number;
  }> {
    const sql = `
      SELECT
        (SELECT COUNT(DISTINCT agency) FROM alt.legislation_1d
         WHERE agency IS NOT NULL
           AND event_date >= CURRENT_DATE - INTERVAL '90 days')::int as unique_agencies,
        (SELECT COUNT(*) FROM alt.legislation_1d
         WHERE event_date >= CURRENT_DATE - INTERVAL '90 days')::int
        +
        (SELECT COUNT(*) FROM alt.executive_actions_event
         WHERE event_date >= CURRENT_DATE - INTERVAL '90 days'
           AND (document_type IN ('executive_order', 'presidential_memorandum', 'proclamation')
                OR document_type IS NULL))::int as active_events
    `;
    const rows = await query<{
      unique_agencies: number;
      active_events: number;
    }>(sql);
    return {
      uniqueAgencies: rows[0]?.unique_agencies ?? 0,
      activeEvents: rows[0]?.active_events ?? 0,
    };
  }

  /**
   * Aggregates ZL-RELEVANT legislation frequency by agency.
   * Filters to trade, tariff, biofuel, agriculture, energy, and sanctions filings.
   * Raw agency counts without keyword filtering are meaningless (SEC always tops).
   */
  static async getAgencyHeatmap(): Promise<AgencyActivity[]> {
    const sql = `
      SELECT
        agency,
        COUNT(*)::int as count,
        0 as sentiment_score
      FROM alt.legislation_1d
      WHERE agency IS NOT NULL
        AND event_date >= CURRENT_DATE - INTERVAL '90 days'
        AND (
          title ILIKE '%trade%' OR title ILIKE '%tariff%'
          OR title ILIKE '%import%' OR title ILIKE '%export%'
          OR title ILIKE '%biofuel%' OR title ILIKE '%biodiesel%'
          OR title ILIKE '%renewable fuel%' OR title ILIKE '%renewable diesel%'
          OR title ILIKE '%soybean%' OR title ILIKE '%vegetable oil%'
          OR title ILIKE '%ethanol%' OR title ILIKE '%clean fuel%'
          OR title ILIKE '%petroleum%' OR title ILIKE '%crude%'
          OR title ILIKE '%sanction%' OR title ILIKE '%embargo%'
          OR title ILIKE '%agriculture%' OR title ILIKE '%grain%'
          OR title ILIKE '%oilseed%' OR title ILIKE '%palm%'
          OR title ILIKE '%energy%' OR title ILIKE '%fuel%'
          OR title ILIKE '%customs%' OR title ILIKE '%duty%'
          OR title ILIKE '%rin %' OR title ILIKE '%rfs%'
          OR title ILIKE '%epa%' OR title ILIKE '%environmental protection%'
        )
      GROUP BY agency
      ORDER BY count DESC
      LIMIT 15
    `;
    const rows = await query<AgencyActivity>(sql);
    return rows;
  }

  /**
   * Fetches Trump 2.0 Effect metrics (Velocity, Acceleration, Score)
   */
  static async getTrumpEffectMetrics(days = 120): Promise<TrumpEffectMetric[]> {
    const sql = `
      SELECT
        as_of_date as date,
        (features->>'action_velocity')::float8 as velocity,
        (features->>'action_acceleration')::float8 as acceleration,
        (features->>'weighted_action_score')::float8 as score,
        (features->>'neural_signal')::float8 as neural_signal,
        (features->>'neural_confidence')::float8 as neural_confidence,
        (features->>'epu_7d')::float8 as epu_7d
      FROM training.specialist_features_trump_effect
      ORDER BY as_of_date DESC
      LIMIT $1
    `;
    const rows = await query<TrumpEffectMetric>(sql, [days]);
    return rows.map((row) => ({
      ...row,
      date: new Date(row.date).toISOString().split("T")[0],
    }));
  }

  /**
   * Fetches Executive Actions joined with ZL price performance.
   * Shows ALL recent executive actions with price impact when available,
   * prioritizing those with significant ZL moves but not excluding others.
   */
  static async getShockwaveEvents(limit = 20): Promise<ExecutiveEvent[]> {
    const sql = `
      SELECT
        e.id,
        e.event_date,
        e.headline,
        e.content,
        e.url,
        e.document_type,
        e.zl_sentiment,
        e.specialist_tags,
        m.close as zl_price_close,
        m.returns_1d as price_return_1d
      FROM alt.executive_actions_event e
      LEFT JOIN mkt.futures_1d m
        ON e.event_date = m.event_date AND m.symbol = 'ZL'
      WHERE e.event_date >= CURRENT_DATE - INTERVAL '90 days'
      ORDER BY
        CASE WHEN ABS(COALESCE(m.returns_1d, 0)) > 0.01 THEN 0 ELSE 1 END,
        e.event_date DESC
      LIMIT $1
    `;
    const rows = await query<ExecutiveEvent>(sql, [limit]);
    return rows.map((row) => ({
      ...row,
      event_date: new Date(row.event_date).toISOString().split("T")[0],
    }));
  }

  /**
   * Fetches Economic Policy Uncertainty (EPU) indices
   */
  static async getPolicyUncertaintyIndices(): Promise<
    PolicyUncertaintyIndex[]
  > {
    const sql = `
       SELECT event_date as date, value, series_id
       FROM econ.vol_indices_1d
       WHERE series_id IN ('USEPUINDXD', 'EPUTRADE', 'EMVTRADEPOLEMV')
         AND event_date >= NOW() - INTERVAL '180 days'
       ORDER BY event_date ASC
    `;

    const rows = await query<PolicyUncertaintyIndex>(sql);
    return rows.map((row) => ({
      ...row,
      date: new Date(row.date).toISOString().split("T")[0],
    }));
  }

  /**
   * Fetches recent news articles from Google News + ProFarmer (alt.policy_news_event).
   * Used by the Policy Intelligence page news feed and AI briefing.
   */
  static async getPolicyNews(limit = 50, daysBack = 7): Promise<PolicyNewsItem[]> {
    const sql = `
      SELECT
        id, event_date, headline, url, source,
        specialist_tags, published_at
      FROM alt.policy_news_event
      WHERE event_date >= CURRENT_DATE - INTERVAL '${daysBack} days'
        AND headline IS NOT NULL
      ORDER BY event_date DESC, published_at DESC NULLS LAST
      LIMIT $1
    `;
    const rows = await query<PolicyNewsItem>(sql, [limit]);
    return rows.map((row) => ({
      ...row,
      event_date: new Date(row.event_date).toISOString().split("T")[0],
      published_at: row.published_at
        ? new Date(row.published_at).toISOString()
        : null,
    }));
  }

  static async getRegimeStatus(): Promise<RegimeState> {
    // Macro threat model inputs:
    // Iran war + oil + inflation + uncertainty + VIX + broad news flow.
    const [
      dailyUncertainty,
      monthlyUncertainty,
      vixData,
      oilMoveData,
      inflationData,
      specialistData,
      legisCount,
      iranWarNewsCount,
      macroNewsCount,
    ] = await Promise.all([
      query<{ val: number; dt: string }>(`
        SELECT value::float8 as val, event_date::text as dt FROM econ.vol_indices_1d
        WHERE series_id = 'USEPUINDXD' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      query<{ val: number; dt: string }>(`
        SELECT value::float8 as val, event_date::text as dt FROM econ.vol_indices_1d
        WHERE series_id = 'USEPUINDXM' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      query<{ val: number; dt: string }>(`
        SELECT value::float8 as val, event_date::text as dt FROM econ.vol_indices_1d
        WHERE series_id = 'VIXCLS' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      query<{ chg_5d: number | null; dt: string }>(`
        WITH cl AS (
          SELECT close::float8 as close, event_date::text as event_date,
                 ROW_NUMBER() OVER (ORDER BY event_date DESC) as rn
          FROM mkt.futures_1d
          WHERE symbol = 'CL' AND close IS NOT NULL
          LIMIT 6
        )
        SELECT
          CASE
            WHEN (SELECT close FROM cl WHERE rn = 6) > 0
              THEN ((SELECT close FROM cl WHERE rn = 1) - (SELECT close FROM cl WHERE rn = 6))
                   / (SELECT close FROM cl WHERE rn = 6)
            ELSE NULL
          END::float8 AS chg_5d,
          (SELECT event_date FROM cl WHERE rn = 1) AS dt
      `),
      query<{ val: number; dt: string }>(`
        SELECT value::float8 as val, event_date::text as dt
        FROM econ.inflation_1d
        WHERE series_id = 'T5YIE' AND value IS NOT NULL
        ORDER BY event_date DESC
        LIMIT 1
      `),
      query<{ signal: number; dt: string }>(`
        SELECT (features->>'neural_signal')::float8 as signal, as_of_date::text as dt
        FROM training.specialist_features_trump_effect
        WHERE (features->>'neural_signal') IS NOT NULL
        ORDER BY as_of_date DESC LIMIT 1
      `),
      query<{ count: number }>(`
        SELECT COUNT(*)::int as count FROM alt.legislation_1d
        WHERE event_date >= CURRENT_DATE - INTERVAL '14 days'
        AND (
          title ILIKE '%iran%' OR title ILIKE '%israel%' OR title ILIKE '%war%' OR title ILIKE '%sanction%'
          OR title ILIKE '%crude%' OR title ILIKE '%oil%' OR title ILIKE '%energy%'
          OR title ILIKE '%inflation%' OR title ILIKE '%interest rate%' OR title ILIKE '%federal reserve%'
          OR title ILIKE '%uncertainty%' OR title ILIKE '%volatility%'
        )
      `),
      query<{ count: number }>(`
        SELECT COUNT(*)::int as count FROM (
          SELECT headline, content FROM alt.profarmer_news_event
          WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
          UNION ALL
          SELECT headline, content FROM alt.policy_news_event
          WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
          UNION ALL
          SELECT headline, content FROM alt.econ_news_event
          WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
        ) combined
        WHERE
          headline ILIKE '%iran%' OR headline ILIKE '%israel%' OR headline ILIKE '%hormuz%'
          OR headline ILIKE '%middle east%' OR headline ILIKE '%war%' OR headline ILIKE '%missile%'
          OR content ILIKE '%strait of hormuz%' OR content ILIKE '%iran%' OR content ILIKE '%war%'
      `),
      query<{ count: number }>(`
        SELECT COUNT(*)::int as count FROM (
          SELECT headline, content FROM alt.profarmer_news_event
          WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
          UNION ALL
          SELECT headline, content FROM alt.policy_news_event
          WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
          UNION ALL
          SELECT headline, content FROM alt.econ_news_event
          WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
        ) combined
        WHERE
          headline ILIKE '%inflation%' OR headline ILIKE '%cpi%' OR headline ILIKE '%ppi%'
          OR headline ILIKE '%federal reserve%' OR headline ILIKE '%fed%' OR headline ILIKE '%interest rate%'
          OR headline ILIKE '%uncertainty%' OR headline ILIKE '%volatility%' OR headline ILIKE '%vix%'
          OR headline ILIKE '%crude%' OR headline ILIKE '%oil%' OR headline ILIKE '%energy%'
          OR headline ILIKE '%iran%' OR headline ILIKE '%hormuz%' OR headline ILIKE '%war%'
          OR content ILIKE '%inflation%' OR content ILIKE '%interest rate%'
          OR content ILIKE '%uncertainty%' OR content ILIKE '%oil price%' OR content ILIKE '%vix%'
      `),
    ]);

    const uncertaintyIndex =
      dailyUncertainty[0]?.val ?? monthlyUncertainty[0]?.val ?? 100;
    const vix = vixData[0]?.val ?? null;
    const oilChange5d = oilMoveData[0]?.chg_5d ?? null;
    const inflationExpectation = inflationData[0]?.val ?? null;
    const specialistSignal = specialistData[0]?.signal ?? null;
    const lCount = legisCount[0]?.count ?? 0;
    const iranWarNews = iranWarNewsCount[0]?.count ?? 0;
    const nCount = macroNewsCount[0]?.count ?? 0;

    const threat = calculateTariffThreat(
      uncertaintyIndex,
      null,
      lCount,
      nCount,
      specialistSignal,
      {
        uncertaintyIndex,
        vix,
        oilChange5d,
        inflationExpectation,
        iranWarNews,
        macroNewsCount: nCount,
      },
    );

    return {
      score: threat.score,
      label: threat.level as RegimeState["label"],
      headline: threat.headline,
      components: {
        uncertainty_index: uncertaintyIndex,
        vix: vix ?? 0,
        oil_change_5d: oilChange5d ?? 0,
        inflation_expectation: inflationExpectation ?? 0,
        iran_war_news: iranWarNews,
        news_velocity: nCount,
        legis_velocity: lCount,
      },
      tariff_components: threat.components,
      freshness: {
        uncertainty_date:
          dailyUncertainty[0]?.dt ?? monthlyUncertainty[0]?.dt ?? null,
        vix_date: vixData[0]?.dt ?? null,
        oil_date: oilMoveData[0]?.dt ?? null,
        inflation_date: inflationData[0]?.dt ?? null,
        specialist_date: specialistData[0]?.dt ?? null,
      },
    };
  }
}

// ===========================================
// EXPORTED HELPER FUNCTIONS (API SUPPORT)
// ===========================================

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function scoreTpu(value: number): { score: number; regime: string } {
  // Kept as export name for compatibility; now treated as macro uncertainty.
  if (!Number.isFinite(value)) return { score: 50, regime: "watch" };
  if (value <= EPU_THRESHOLDS.LOW) return { score: 25, regime: "contained" };
  if (value <= EPU_THRESHOLDS.NORMAL) {
    const t = (value - EPU_THRESHOLDS.LOW) / (EPU_THRESHOLDS.NORMAL - EPU_THRESHOLDS.LOW);
    return { score: 25 + t * 20, regime: "watch" };
  }
  if (value <= EPU_THRESHOLDS.ELEVATED) {
    const t =
      (value - EPU_THRESHOLDS.NORMAL) /
      (EPU_THRESHOLDS.ELEVATED - EPU_THRESHOLDS.NORMAL);
    return { score: 45 + t * 20, regime: "elevated_risk" };
  }
  if (value <= EPU_THRESHOLDS.HIGH) {
    const t = (value - EPU_THRESHOLDS.ELEVATED) / (EPU_THRESHOLDS.HIGH - EPU_THRESHOLDS.ELEVATED);
    return { score: 65 + t * 15, regime: "high_alert" };
  }
  const excess = Math.min(1, (value - EPU_THRESHOLDS.HIGH) / 150);
  return { score: 80 + excess * 20, regime: "systemic_shock" };
}

export function scoreEmv(value: number | null): { score: number } {
  // Kept as export name for compatibility; EMV is treated as a secondary uncertainty signal.
  if (value === null || !Number.isFinite(value)) return { score: 50 };
  return { score: clamp((value / 300) * 100, 0, 100) };
}

export function scoreLegislationVelocity(count: number): number {
  // Small additive kicker only; this is no longer the core driver.
  return clamp(count * 1.2, 0, 12);
}

function scoreVixRisk(vix: number | null): number {
  if (vix === null || !Number.isFinite(vix)) return 50;
  if (vix < 15) return 20;
  if (vix < 20) return 35;
  if (vix < 25) return 50;
  if (vix < 30) return 65;
  if (vix < 40) return 82;
  return 100;
}

function scoreOilRisk(change5d: number | null): number {
  if (change5d === null || !Number.isFinite(change5d)) return 50;
  if (change5d <= -0.08) return 20;
  if (change5d <= -0.03) return 35;
  if (change5d <= 0.02) return 50;
  if (change5d <= 0.05) return 65;
  if (change5d <= 0.1) return 80;
  return 95;
}

function scoreInflationRisk(value: number | null): number {
  // T5YIE is in percent terms; elevated inflation expectations generally lift
  // commodity risk premia for soybean oil buyers.
  if (value === null || !Number.isFinite(value)) return 50;
  if (value < 1.8) return 35;
  if (value < 2.1) return 50;
  if (value < 2.3) return 65;
  if (value < 2.5) return 78;
  if (value < 2.8) return 88;
  return 96;
}

export function scoreNewsVelocity(count: number, maxCount = 24): number {
  if (!Number.isFinite(count) || count <= 0) return 0;
  return clamp((count / maxCount) * 100, 0, 100);
}

export interface MacroThreatContext {
  uncertaintyIndex?: number | null;
  vix?: number | null;
  oilChange5d?: number | null;
  inflationExpectation?: number | null;
  iranWarNews?: number | null;
  macroNewsCount?: number | null;
}

export function calculateTariffThreat(
  tpu: number,
  _emv: number | null,
  legislationCount: number,
  soyTariffNews: number,
  specialistSignal: number | null,
  context?: MacroThreatContext,
): {
  score: number;
  level: string;
  regime: string;
  headline: string;
  components: TariffComponents;
} {
  const uncertaintyValue = context?.uncertaintyIndex ?? tpu;
  const { score: uncertaintyScore } = scoreTpu(uncertaintyValue);
  const vixScore = scoreVixRisk(context?.vix ?? null);
  const oilScore = scoreOilRisk(context?.oilChange5d ?? null);
  const inflationScore = scoreInflationRisk(context?.inflationExpectation ?? null);
  const iranWarNewsCount = Math.max(0, Math.round(context?.iranWarNews ?? 0));
  const macroNewsCount = Math.max(
    0,
    Math.round(context?.macroNewsCount ?? soyTariffNews),
  );
  const iranWarNewsScore = scoreNewsVelocity(iranWarNewsCount, 10);
  const macroNewsScore = scoreNewsVelocity(
    Math.max(macroNewsCount, soyTariffNews),
    28,
  );

  const legislationAdj = scoreLegislationVelocity(legislationCount);
  const specialistAdj =
    specialistSignal !== null && Number.isFinite(specialistSignal)
      ? clamp(-specialistSignal * 8, -8, 8)
      : 0;

  const weightedScore =
    uncertaintyScore * 0.23 +
    vixScore * 0.17 +
    oilScore * 0.14 +
    inflationScore * 0.19 +
    iranWarNewsScore * 0.17 +
    macroNewsScore * 0.1;

  const score = clamp(weightedScore + legislationAdj + specialistAdj, 0, 100);

  let level: string;
  let regime: string;
  if (score >= 80) {
    level = "Systemic Shock";
    regime = "systemic_shock";
  } else if (score >= 65) {
    level = "High Alert";
    regime = "high_alert";
  } else if (score >= 50) {
    level = "Elevated Risk";
    regime = "elevated_risk";
  } else if (score >= 35) {
    level = "Watch";
    regime = "watch";
  } else {
    level = "Contained";
    regime = "contained";
  }

  const headline =
    score >= 80
      ? "Systemic macro shock: inflation, war-risk flow, and volatility are all elevated."
      : score >= 65
        ? "High-alert macro regime: inflation pressure, uncertainty, and VIX are raising procurement risk."
      : score >= 50
          ? "Elevated macro pressure: inflation and geopolitical flow are keeping buyer risk elevated."
          : score >= 35
            ? "Watch regime: mixed macro signals with manageable pressure."
            : "Contained macro backdrop: uncertainty and volatility are currently stable.";

  return {
    score: Math.round(score * 10) / 10,
    level,
    regime,
    headline,
    components: {
      uncertainty_score: Math.round(uncertaintyScore * 10) / 10,
      uncertainty_value: Math.round(uncertaintyValue),
      vix_score: Math.round(vixScore * 10) / 10,
      vix_value:
        context?.vix !== null && context?.vix !== undefined
          ? Math.round(context.vix * 10) / 10
          : null,
      oil_score: Math.round(oilScore * 10) / 10,
      oil_change_5d:
        context?.oilChange5d !== null && context?.oilChange5d !== undefined
          ? Math.round(context.oilChange5d * 10_000) / 10_000
          : null,
      inflation_score: Math.round(inflationScore * 10) / 10,
      inflation_value:
        context?.inflationExpectation !== null &&
        context?.inflationExpectation !== undefined
          ? Math.round(context.inflationExpectation * 100) / 100
          : null,
      iran_war_news_score: Math.round(iranWarNewsScore * 10) / 10,
      iran_war_news_count: iranWarNewsCount,
      macro_news_score: Math.round(macroNewsScore * 10) / 10,
      macro_news_count: macroNewsCount,
      legislation_count: legislationCount,
      legislation_adj: Math.round(legislationAdj * 10) / 10,
      specialist_signal: specialistSignal,
      specialist_adj: Math.round(specialistAdj * 10) / 10,
    },
  };
}
