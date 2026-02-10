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
// SCORING CONSTANTS (Matched to Market Drivers)
// ===========================================
const TPU = { CALM: 40, NORMAL: 100, ELEVATED: 200, HIGH: 400, EXTREME: 700 };

// ===========================================
// PURE SCORING FUNCTIONS
// ===========================================

export function scoreTpu(tpu: number): { score: number; regime: string } {
  if (tpu < TPU.CALM) return { score: 15, regime: "trade_calm" };
  if (tpu < TPU.NORMAL) {
    const score = 15 + ((tpu - TPU.CALM) / (TPU.NORMAL - TPU.CALM)) * 25;
    return { score, regime: "normal_uncertainty" };
  }
  if (tpu < TPU.ELEVATED) {
    const score = 40 + ((tpu - TPU.NORMAL) / (TPU.ELEVATED - TPU.NORMAL)) * 20;
    return { score, regime: "tariff_threats" };
  }
  if (tpu < TPU.HIGH) {
    const score = 60 + ((tpu - TPU.ELEVATED) / (TPU.HIGH - TPU.ELEVATED)) * 20;
    return { score, regime: "tariff_war" };
  }
  if (tpu < TPU.EXTREME) {
    const score = 80 + ((tpu - TPU.HIGH) / (TPU.EXTREME - TPU.HIGH)) * 12;
    return { score, regime: "extreme_disruption" };
  }
  return { score: 95, regime: "extreme_disruption" };
}

export function scoreEmv(emv: number | null): { score: number; adj: number } {
  if (emv === null) return { score: 50, adj: 0 };
  if (emv > 400) return { score: 80, adj: 10 };
  if (emv > 200) return { score: 60, adj: 5 };
  if (emv < 50) return { score: 30, adj: -5 };
  return { score: 50, adj: 0 };
}

export function scoreLegislationVelocity(count: number): number {
  if (count >= 10) return 15;
  if (count >= 5) return 8;
  if (count >= 2) return 3;
  if (count === 0) return -3;
  return 0;
}

export function scoreNewsVelocity(count: number): number {
  if (count >= 10) return 25;
  if (count >= 5) return 15;
  if (count >= 2) return 8;
  if (count >= 1) return 3;
  return -5;
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
       FROM econ.rates_1d
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
    const [tpuRow, emvRow, legisCount, newsCount] = await Promise.all([
      query<{ val: number }>(`
        SELECT value::float8 as val FROM econ.vol_indices_1d
        WHERE series_id = 'USEPUINDXM' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      query<{ val: number }>(`
        SELECT value::float8 as val FROM econ.vol_indices_1d
        WHERE series_id = 'EMVTRADEPOLEMV' AND value IS NOT NULL
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

    const tpu = tpuRow[0]?.val ?? 0;
    const emv = emvRow[0]?.val ?? null;
    const lCount = legisCount[0]?.count ?? 0;
    const nCount = newsCount[0]?.count ?? 0;

    // 2. Score Components
    const { score: tpuScore } = scoreTpu(tpu);
    const { score: emvScore } = scoreEmv(emv);
    const legisAdj = scoreLegislationVelocity(lCount);
    const newsAdj = scoreNewsVelocity(nCount);

    const specialistAdj = 0;

    const rawScore =
      tpuScore * 0.35 +
      emvScore * 0.2 +
      (50 + legisAdj) * 0.1 +
      (50 + specialistAdj) * 0.15 +
      (50 + newsAdj) * 0.2;

    const score = Math.max(0, Math.min(100, rawScore));

    let label: RegimeState["label"] = "Minimal";
    if (score >= 80) label = "Active War";
    else if (score >= 65) label = "Retaliation Risk";
    else if (score >= 50) label = "Elevated";
    else if (score >= 35) label = "Background Noise";

    return {
      score,
      label,
      components: {
        tpu,
        emv: emv ?? 0,
        legis_velocity: lCount,
        news_velocity: nCount,
      },
    };
  }
}
