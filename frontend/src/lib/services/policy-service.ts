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
    const [dailyTpu, monthlyTpu, actionMetrics, legisCount, newsCount] =
      await Promise.all([
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
        SELECT signal * 100 as score
        FROM training.specialist_trump_effect_1d
        ORDER BY as_of_date DESC LIMIT 1
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
    // If no data, default to 0 (Minimal)
    const tpu = dailyTpu[0]?.val ?? monthlyTpu[0]?.val ?? 0;

    // Get weighted action score from Python engine
    // If null, we default to a baseline score derived from EPU
    // Mapping EPU 0-300 to roughly 0-100 score if no action score exists
    const pythonActionScore = actionMetrics[0]?.score;
    const fallbackScore = Math.min(100, (tpu / 300) * 100);
    const score = pythonActionScore ?? fallbackScore;

    const lCount = legisCount[0]?.count ?? 0;
    const nCount = newsCount[0]?.count ?? 0;

    // 2. Classify Regime (STRICT PYTHON THRESHOLDS)
    let label: RegimeState["label"] = "Minimal";

    if (tpu >= EPU_THRESHOLDS.HIGH) {
      label = "Active War"; // > 250
    } else if (tpu >= EPU_THRESHOLDS.ELEVATED) {
      label = "Retaliation Risk"; // 175 - 250
    } else if (tpu >= EPU_THRESHOLDS.NORMAL) {
      label = "Elevated"; // 125 - 175
    } else if (tpu >= EPU_THRESHOLDS.LOW) {
      label = "Background Noise"; // 75 - 125
    } else {
      label = "Minimal"; // < 75
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
