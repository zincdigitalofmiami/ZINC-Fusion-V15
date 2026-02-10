// frontend/src/lib/services/policy-service.ts
import { query } from "@/lib/db";
import {
  AgencyActivity,
  ExecutiveEvent,
  LegislationEvent,
  PolicyUncertaintyIndex,
  TariffDeadline,
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
   * Fetches executive actions (EOs, Memorandums)
   */
  static async getExecutiveEvents(limit = 50): Promise<ExecutiveEvent[]> {
    const sql = `
      SELECT
        id, event_date, headline, content, url,
        document_type, zl_sentiment, specialist_tags
      FROM alt.executive_actions
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
      SELECT *
      FROM alt.tariff_deadlines
      WHERE is_active = true
      ORDER BY days_to_expiry ASC
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
   * Aggregates legislation frequency by agency for the Heatmap.
   */
  static async getAgencyHeatmap(): Promise<AgencyActivity[]> {
    const sql = `
      SELECT
        agency,
        COUNT(*)::int as count,
        0 as sentiment_score
      FROM alt.legislation_1d
      WHERE agency IS NOT NULL
      GROUP BY agency
      ORDER BY count DESC
      LIMIT 50
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
        action_velocity as velocity,
        action_acceleration as acceleration,
        weighted_action_score as score
      FROM features.trump_effect_1d
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
   * Fetches Executive Actions joined with ZL price performance
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
      FROM alt.executive_actions e
      LEFT JOIN mkt.futures_1d m
        ON e.event_date = m.event_date AND m.symbol = 'ZL'
      WHERE e.zl_sentiment IS NOT NULL
         OR ABS(m.returns_1d) > 0.015
      ORDER BY e.event_date DESC
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

  static async getRegimeStatus(): Promise<RegimeState> {
    // 1. Fetch raw inputs in parallel
    // Priority: Daily EPU -> Monthly EPU
    // We fetch raw components to perform a transparent, real-time calculation
    const [
      dailyTpu,
      monthlyTpu,
      actionFeatures,
      vixData,
      legisCount,
      newsCount,
    ] = await Promise.all([
      query<{ val: number }>(`
        SELECT value::float8 as val FROM econ.vol_indices_1d
        WHERE series_id = 'USEPUINDXD' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      query<{ val: number }>(`
        SELECT value::float8 as val FROM econ.vol_indices_1d
        WHERE series_id = 'USEPUINDXM' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      query<{ score: number }>(`
        SELECT weighted_action_score::float8 as score
        FROM features.trump_effect_1d
        ORDER BY as_of_date DESC LIMIT 1
      `),
      query<{ val: number }>(`
        SELECT value::float8 as val FROM econ.vol_indices_1d
        WHERE series_id = 'VIXCLS' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      query<{ count: number }>(`
        SELECT COUNT(*)::int as count FROM alt.legislation_1d
        WHERE event_date >= CURRENT_DATE - INTERVAL '14 days'
        AND (title ILIKE '%trade%' OR title ILIKE '%tariff%' OR title ILIKE '%import%' OR title ILIKE '%export%')
      `),
      query<{ count: number }>(`
        SELECT COUNT(*)::int as count FROM alt.profarmer_news
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
        AND (headline ILIKE '%tariff%' OR headline ILIKE '%trade war%' OR headline ILIKE '%retaliatory%'
         OR (headline ILIKE '%soy%' AND headline ILIKE '%duty%')
         OR (headline ILIKE '%china%' AND headline ILIKE '%tariff%'))
      `),
    ]);

    // Determine EPU level (Daily preferred)
    const tpu = dailyTpu[0]?.val ?? monthlyTpu[0]?.val ?? 100; // Default to 100 if missing

    // Get raw inputs for calculation
    const rawActionScore = actionFeatures[0]?.score ?? 0;
    const vix = vixData[0]?.val ?? 15; // Default VIX 15

    // "Real Math" Calculation (Transparent Component Summation)
    // 1. Base Action Score (0-2 scale -> 0-70 points)
    //    1.4 raw score (typical high) -> ~56 points
    const actionPoints = Math.min(70, rawActionScore * 40);

    // 2. EPU Stress (0-300 scale -> 0-30 points)
    //    150 TPU -> 15 points
    const epuPoints = Math.min(30, (tpu / 300) * 30);

    // 3. VIX Stress (0-60 scale -> 0-10 points)
    //    15 VIX -> 2.5 points
    const vixPoints = Math.min(10, (vix / 60) * 10);

    // Total calculation
    const calculatedScore = Math.min(100, actionPoints + epuPoints + vixPoints);

    // Use the calculated score
    const score = calculatedScore;

    const lCount = legisCount[0]?.count ?? 0;
    const nCount = newsCount[0]?.count ?? 0;

    // 2. Classify Regime (Score-Driven + Thresholds)
    let label: RegimeState["label"] = "Minimal";

    // Combined Logic: High Score OR High EPU triggers War state
    if (score >= 80 || tpu >= EPU_THRESHOLDS.HIGH) {
      label = "Active War";
    } else if (score >= 60 || tpu >= EPU_THRESHOLDS.ELEVATED) {
      label = "Retaliation Risk";
    } else if (score >= 40 || tpu >= EPU_THRESHOLDS.NORMAL) {
      label = "Elevated";
    } else if (score >= 20 || tpu >= EPU_THRESHOLDS.LOW) {
      label = "Background Noise";
    } else {
      label = "Minimal";
    }

    return {
      score,
      label,
      components: {
        tpu,
        emv: 0, // No longer primary driver
        legis_velocity: lCount,
        news_velocity: nCount,
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
