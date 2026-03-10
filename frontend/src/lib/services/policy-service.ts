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
import {
  resolveTrumpEffectSnapshot,
  TRUMP_EFFECT_DEFAULT_TTL_DAYS,
  TRUMP_EFFECT_LIVE_MAX_AGE_DAYS,
} from "@/lib/services/trump-effect-source";

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

function isFiniteMetricValue(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function hasValidTrumpMetricContract(row: TrumpEffectMetric): boolean {
  return [
    row.velocity,
    row.acceleration,
    row.score,
    row.neural_signal,
    row.neural_confidence,
    row.epu_7d,
  ].every(isFiniteMetricValue);
}

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
        NULLIF(features->>'action_velocity', '')::float8 as velocity,
        NULLIF(features->>'action_acceleration', '')::float8 as acceleration,
        NULLIF(features->>'weighted_action_score', '')::float8 as score,
        NULLIF(features->>'neural_signal', '')::float8 as neural_signal,
        NULLIF(features->>'neural_confidence', '')::float8 as neural_confidence,
        NULLIF(features->>'epu_7d', '')::float8 as epu_7d
      FROM training.specialist_features_trump_effect
      ORDER BY as_of_date DESC
      LIMIT $1
    `;
    const rows = await query<TrumpEffectMetric>(sql, [days]).catch(() => []);
    const now = Date.now();

    const withinTtl = rows
      .map((row) => {
        const date = new Date(row.date);
        const parsedMs = date.getTime();
        const staleDays = Number.isFinite(parsedMs)
          ? Math.max(0, Math.floor((now - parsedMs) / 86_400_000))
          : TRUMP_EFFECT_DEFAULT_TTL_DAYS + 1;
        const dateIso = Number.isFinite(parsedMs)
          ? date.toISOString().split("T")[0]
          : new Date(now).toISOString().split("T")[0];
        return {
          ...row,
          date: dateIso,
          staleDays,
          source:
            staleDays <= TRUMP_EFFECT_LIVE_MAX_AGE_DAYS
              ? ("feature_payload" as const)
              : staleDays <= TRUMP_EFFECT_DEFAULT_TTL_DAYS
                ? ("last_known" as const)
                : ("unavailable" as const),
          reasonCode:
            staleDays > TRUMP_EFFECT_DEFAULT_TTL_DAYS
              ? ("STALE_EXPIRED" as const)
              : undefined,
        };
      })
      // Contract guard: malformed feature rows must not bypass snapshot fallback.
      .filter(
        (row) =>
          row.source !== "unavailable" && hasValidTrumpMetricContract(row),
      );

    if (withinTtl.length > 0) {
      return withinTtl;
    }

    const snapshot = await resolveTrumpEffectSnapshot(query, {
      ttlDays: TRUMP_EFFECT_DEFAULT_TTL_DAYS,
    });
    if (snapshot.meta.source === "unavailable") {
      return [];
    }

    return [
      {
        date:
          snapshot.meta.asOf ??
          new Date().toISOString().split("T")[0],
        velocity: snapshot.values.action_velocity,
        acceleration: snapshot.values.action_acceleration,
        score: snapshot.values.weighted_action_score,
        neural_signal: snapshot.values.neural_signal,
        neural_confidence: snapshot.values.neural_confidence,
        epu_7d: snapshot.values.epu_7d,
        source: snapshot.meta.source,
        staleDays: snapshot.meta.staleDays,
        reasonCode: snapshot.meta.reasonCode ?? undefined,
      },
    ];
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
    // Fetch all 5 components for calculateTariffThreat() in parallel
    // Also fetch freshness dates for transparency
    const [
      dailyTpu,
      monthlyTpu,
      emvData,
      specialistData,
      legisCount,
      newsCount,
    ] = await Promise.all([
      query<{ val: number; dt: string }>(`
        SELECT value::float8 as val, event_date::text as dt FROM econ.vol_indices_1d
        WHERE series_id = 'USEPUINDXD' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      query<{ val: number }>(`
        SELECT value::float8 as val FROM econ.vol_indices_1d
        WHERE series_id = 'USEPUINDXM' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      query<{ val: number; dt: string }>(`
        SELECT value::float8 as val, event_date::text as dt FROM econ.vol_indices_1d
        WHERE series_id = 'EMVTRADEPOLEMV' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      query<{ signal: number; dt: string }>(`
        SELECT NULLIF(features->>'neural_signal', '')::float8 as signal, as_of_date::text as dt
        FROM training.specialist_features_trump_effect
        WHERE NULLIF(features->>'neural_signal', '') ~ '^-?[0-9]+(\\.[0-9]+)?$'
        ORDER BY as_of_date DESC LIMIT 1
      `),
      // Legislation velocity: trade/tariff + biofuel/EPA/energy policy
      query<{ count: number }>(`
        SELECT COUNT(*)::int as count FROM alt.legislation_1d
        WHERE event_date >= CURRENT_DATE - INTERVAL '14 days'
        AND (title ILIKE '%trade%' OR title ILIKE '%tariff%' OR title ILIKE '%import%' OR title ILIKE '%export%'
         OR title ILIKE '%biofuel%' OR title ILIKE '%biodiesel%' OR title ILIKE '%renewable fuel%'
         OR title ILIKE '%renewable diesel%' OR title ILIKE '%soybean%' OR title ILIKE '%vegetable oil%'
         OR title ILIKE '%ethanol%' OR title ILIKE '%clean fuel%')
      `),
      // News velocity: BOTH ProFarmer + Google News (policy_news_event)
      // ProFarmer has been dead since Feb 14 2026; Google News RSS fills the gap.
      // Broadened keywords: trade/tariff + biofuel/EPA/RFS + sanctions/geopolitical
      query<{ count: number }>(`
        SELECT COUNT(*)::int as count FROM (
          SELECT headline FROM alt.profarmer_news_event
          WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
          AND (headline ILIKE '%tariff%' OR headline ILIKE '%trade war%' OR headline ILIKE '%retaliatory%'
           OR (headline ILIKE '%soy%' AND headline ILIKE '%duty%')
           OR (headline ILIKE '%china%' AND headline ILIKE '%tariff%')
           OR headline ILIKE '%rfs%' OR headline ILIKE '%biodiesel%' OR headline ILIKE '%renewable diesel%'
           OR headline ILIKE '%sanctions%' OR headline ILIKE '%crude oil%'
           OR headline ILIKE '%biofuel%' OR headline ILIKE '%epa%')
          UNION ALL
          SELECT headline FROM alt.policy_news_event
          WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
          AND (headline ILIKE '%tariff%' OR headline ILIKE '%trade war%' OR headline ILIKE '%retaliatory%'
           OR (headline ILIKE '%soy%' AND (headline ILIKE '%duty%' OR headline ILIKE '%oil%'))
           OR (headline ILIKE '%china%' AND (headline ILIKE '%tariff%' OR headline ILIKE '%trade%'))
           OR headline ILIKE '%rfs%' OR headline ILIKE '%biodiesel%' OR headline ILIKE '%renewable diesel%'
           OR headline ILIKE '%sanctions%' OR headline ILIKE '%crude oil%'
           OR headline ILIKE '%biofuel%' OR headline ILIKE '%epa%'
           OR headline ILIKE '%ethanol%' OR headline ILIKE '%import duty%')
        ) combined
      `),
    ]);

    // Resolve inputs with fallbacks
    const tpu = dailyTpu[0]?.val ?? monthlyTpu[0]?.val ?? 100;
    const emv = emvData[0]?.val ?? null;
    const specialistSignal = specialistData[0]?.signal ?? null;
    const lCount = legisCount[0]?.count ?? 0;
    const nCount = newsCount[0]?.count ?? 0;

    // Full 5-component tariff threat scoring (matches policy_pressure.py)
    const threat = calculateTariffThreat(
      tpu,
      emv,
      lCount,
      nCount,
      specialistSignal,
    );

    return {
      score: threat.score,
      label: threat.level as RegimeState["label"],
      headline: threat.headline,
      components: {
        tpu,
        emv: emv ?? 0,
        legis_velocity: lCount,
        news_velocity: nCount,
      },
      tariff_components: threat.components,
      freshness: {
        tpu_date: dailyTpu[0]?.dt ?? null,
        emv_date: emvData[0]?.dt ?? null,
        specialist_date: specialistData[0]?.dt ?? null,
      },
    };
  }
}

// ===========================================
// EXPORTED HELPER FUNCTIONS (API SUPPORT)
// ===========================================

export function scoreTpu(value: number): { score: number; regime: string } {
  // Normalize 0-300 scale to 0-100
  const score = Math.min(100, (value / 300) * 100);

  let regime = "Minimal";
  if (value >= EPU_THRESHOLDS.HIGH) regime = "Active War";
  else if (value >= EPU_THRESHOLDS.ELEVATED) regime = "Retaliation Risk";
  else if (value >= EPU_THRESHOLDS.NORMAL) regime = "Elevated";
  else if (value >= EPU_THRESHOLDS.LOW) regime = "Background Noise";

  return { score, regime };
}

export function scoreEmv(value: number | null): { score: number } {
  if (value === null) return { score: 0 };
  // EMV tends to align with EPU, use same normalization for consistency
  const score = Math.min(100, (value / 300) * 100);
  return { score };
}

export function scoreLegislationVelocity(count: number): number {
  // Simple heuristic: 0 count -> 0, 10 count -> +20
  return Math.min(20, count * 2);
}

export function scoreNewsVelocity(count: number): number {
  // Simple heuristic: 0 count -> 0, 20 count -> +20
  return Math.min(20, count);
}

// ===========================================
// TARIFF THREAT SCORING (Full Sophistication)
// Matches policy_pressure.py exactly
// ===========================================

export function calculateTariffThreat(
  tpu: number,
  emv: number | null,
  legislationCount: number,
  soyTariffNews: number,
  specialistSignal: number | null,
): {
  score: number;
  level: string;
  regime: string;
  headline: string;
  components: TariffComponents;
} {
  // Component 1: TPU (35%)
  const { score: tpuScore, regime } = scoreTpu(tpu);

  // Component 2: EMV (20%)
  const { score: emvScore } = scoreEmv(emv);

  // Component 3: Legislation Velocity (10%)
  const legisAdj = scoreLegislationVelocity(legislationCount);

  // Component 4: Soy Tariff News (20%)
  const newsAdj = scoreNewsVelocity(soyTariffNews);

  // Component 5: Specialist Signal (15%)
  let specialistAdj = 0;
  if (specialistSignal !== null) {
    specialistAdj = -specialistSignal * 20 * 0.5;
  }

  // Composite Score (SOY-CENTRIC WEIGHTS from Python)
  // TPU 35%, EMV 20%, Legislation 10%, Specialist 15%, Soy News 20%
  const score = Math.max(
    0,
    Math.min(
      100,
      tpuScore * 0.35 +
        emvScore * 0.2 +
        (50 + legisAdj) * 0.1 +
        (50 + specialistAdj) * 0.15 +
        (50 + newsAdj) * 0.2,
    ),
  );

  // Level - ACTIONABLE LABELS
  let level: string;
  if (score >= 80) level = "Active War";
  else if (score >= 65) level = "Retaliation Risk";
  else if (score >= 50) level = "Elevated Noise";
  else if (score >= 35) level = "Background Noise";
  else level = "Minimal Threat";

  // Headlines with TPU context (normal ~100, elevated ~200, crisis 400+)
  const headline =
    score >= 80
      ? "ZL Bearish - Active Tariffs on Soy (TPU 400+)"
      : score >= 65
        ? "ZL Cautious - Retaliatory Tariff Risk (TPU 200+)"
        : score >= 50
          ? "TPU Elevated - Export Sales Pace Uncertain"
          : score >= 35
            ? "TPU Normal Range - Background Trade Noise"
            : "Trade Policy Calm - Supportive for Soy Exports";

  return {
    score: Math.round(score * 10) / 10,
    level,
    regime,
    headline,
    components: {
      tpu_score: Math.round(tpuScore * 10) / 10,
      tpu_value: Math.round(tpu),
      emv_score: Math.round(emvScore * 10) / 10,
      emv_value: emv ? Math.round(emv) : null,
      legislation_count: legislationCount,
      legislation_adj: Math.round(legisAdj * 10) / 10,
      soy_tariff_news_count: soyTariffNews,
      soy_tariff_news_adj: Math.round(newsAdj * 10) / 10,
      specialist_signal: specialistSignal,
      specialist_adj: Math.round(specialistAdj * 10) / 10,
    },
  };
}
