/**
 * Crush Pressure Scoring Service
 *
 * Matches crush_pressure.py exactly.
 * Pure functions — no DB access, no side effects.
 */

// =============================================================================
// DOMAIN-SPECIFIC THRESHOLDS
// =============================================================================

// Board Crush (USD/bushel)
const CRUSH = {
  DANGER: 0.75,
  SEVERE: 1.0,
  TIGHT: 1.25,
  NEUTRAL: 1.5,
  HEALTHY: 1.75,
  STRONG: 2.0,
  EXCEPTIONAL: 2.5,
};

// Oil Share Thresholds
const OIL_SHARE = {
  VERY_LOW: 0.42,
  LOW: 0.45,
  NEUTRAL_LOW: 0.47,
  NEUTRAL_HIGH: 0.49,
  HIGH: 0.51,
  VERY_HIGH: 0.54,
};

// =============================================================================
// TYPES
// =============================================================================

export interface CrushComponents {
  board_crush_score: number;
  board_crush_value: number;
  oil_share_value: number | null;
  oil_share_level_adj: number;
  oil_share_5d_change: number | null;
  oil_share_trend_adj: number;
  specialist_signal: number | null;
  specialist_adj: number;
}

// =============================================================================
// HELPER SCORERS
// =============================================================================

function scoreBoardCrush(crush: number): { score: number; regime: string } {
  if (crush < CRUSH.DANGER) {
    const score = 95 + Math.min(5, (CRUSH.DANGER - crush) * 20);
    return { score: Math.min(100, score), regime: "margin_collapse" };
  }
  if (crush < CRUSH.SEVERE) {
    const pct = (crush - CRUSH.DANGER) / (CRUSH.SEVERE - CRUSH.DANGER);
    return { score: 85 - pct * 10, regime: "severe_stress" };
  }
  if (crush < CRUSH.TIGHT) {
    const pct = (crush - CRUSH.SEVERE) / (CRUSH.TIGHT - CRUSH.SEVERE);
    return { score: 70 - pct * 15, regime: "tight_margins" };
  }
  if (crush < CRUSH.NEUTRAL) {
    const pct = (crush - CRUSH.TIGHT) / (CRUSH.NEUTRAL - CRUSH.TIGHT);
    return { score: 55 - pct * 10, regime: "tight_margins" };
  }
  if (crush < CRUSH.HEALTHY) {
    const pct = (crush - CRUSH.NEUTRAL) / (CRUSH.HEALTHY - CRUSH.NEUTRAL);
    return { score: 45 - pct * 15, regime: "healthy_margins" };
  }
  if (crush < CRUSH.STRONG) {
    const pct = (crush - CRUSH.HEALTHY) / (CRUSH.STRONG - CRUSH.HEALTHY);
    return { score: 30 - pct * 10, regime: "strong_margins" };
  }
  const excess = crush - CRUSH.STRONG;
  return {
    score: Math.max(5, 20 - Math.min(15, excess * 15)),
    regime: "exceptional_margins",
  };
}

function scoreOilShareLevel(share: number | null): {
  adj: number;
  desc: string;
} {
  if (share === null) return { adj: 0, desc: "No oil share data" };
  if (share < OIL_SHARE.VERY_LOW)
    return { adj: 20, desc: "Oil severely undervalued (meal driving crush)" };
  if (share < OIL_SHARE.LOW)
    return { adj: 12, desc: "Oil weak relative to meal" };
  if (share < OIL_SHARE.NEUTRAL_LOW)
    return { adj: 5, desc: "Oil slightly below average" };
  if (share < OIL_SHARE.NEUTRAL_HIGH)
    return { adj: 0, desc: "Oil share in normal range" };
  if (share < OIL_SHARE.HIGH)
    return { adj: -5, desc: "Oil slightly above average" };
  if (share < OIL_SHARE.VERY_HIGH)
    return { adj: -10, desc: "Oil commanding premium" };
  return { adj: -15, desc: "Oil share extremely elevated" };
}

function scoreOilShareTrend(change5d: number | null): {
  adj: number;
  desc: string;
} {
  if (change5d === null) return { adj: 0, desc: "No trend data" };
  if (change5d < -0.02) return { adj: 15, desc: "Oil share falling sharply" };
  if (change5d < -0.005) return { adj: 8, desc: "Oil share declining" };
  if (change5d > 0.02) return { adj: -12, desc: "Oil share surging" };
  if (change5d > 0.005) return { adj: -6, desc: "Oil share rising" };
  return { adj: 0, desc: "Oil share stable" };
}

// =============================================================================
// MAIN CALCULATOR
// =============================================================================

export function calculateCrushPressure(
  crush: number,
  oilShare: number | null,
  oilShare5dAgo: number | null,
  specialistSignal: number | null,
): {
  score: number;
  level: string;
  regime: string;
  headline: string;
  components: CrushComponents;
} {
  // Component 1: Board Crush Level (45%)
  const { score: crushScore, regime } = scoreBoardCrush(crush);

  // Component 2: Oil Share Level (20%)
  const { adj: oilShareAdj } = scoreOilShareLevel(oilShare);

  // Component 3: Oil Share Trend (20%)
  let oilShareChange: number | null = null;
  if (oilShare !== null && oilShare5dAgo !== null && oilShare5dAgo > 0) {
    oilShareChange = (oilShare - oilShare5dAgo) / oilShare5dAgo;
  }
  const { adj: trendAdj } = scoreOilShareTrend(oilShareChange);

  // Component 4: Specialist Signal (15%)
  let specialistAdj = 0;
  if (specialistSignal !== null) {
    specialistAdj = -specialistSignal * 20 * 0.5; // Negative signal = bearish = more pressure
  }

  // Composite Score
  let score = crushScore;
  score += (oilShareAdj * 0.2) / 0.45;
  score += (trendAdj * 0.2) / 0.45;
  score += (specialistAdj * 0.15) / 0.45;
  score = Math.max(0, Math.min(100, score));

  // Level classification - ACTIONABLE LABELS
  let level: string;
  if (score >= 80) level = "Plant Idling";
  else if (score >= 65) level = "Margin Squeeze";
  else if (score >= 55) level = "Tight";
  else if (score >= 45) level = "Neutral";
  else if (score >= 30) level = "Healthy";
  else level = "Max Utilization";

  // Headlines with board crush context (<USD 1 crisis, USD 1.50 neutral, >USD 2 strong)
  const headline =
    score >= 75
      ? "ZL Mixed - Crush Plants Idling (<USD 1.00/bu margins)"
      : score >= 55
        ? "ZL Cautious - Processor Margins Tight (USD 1.00-1.50/bu)"
        : score >= 40
          ? "ZL Neutral - Crush Economics Balanced (~USD 1.50/bu)"
          : score >= 25
            ? "ZL Supportive - Healthy Crush (USD 1.75+/bu)"
            : "ZL Watch Supply - Max Crush at USD 2+/bu";

  return {
    score: Math.round(score * 10) / 10,
    level,
    regime,
    headline,
    components: {
      board_crush_score: Math.round(crushScore * 10) / 10,
      board_crush_value: Math.round(crush * 100) / 100,
      oil_share_value: oilShare ? Math.round(oilShare * 1000) / 10 : null, // As percentage
      oil_share_level_adj: Math.round(oilShareAdj * 10) / 10,
      oil_share_5d_change: oilShareChange
        ? Math.round(oilShareChange * 1000) / 10
        : null, // As percentage
      oil_share_trend_adj: Math.round(trendAdj * 10) / 10,
      specialist_signal: specialistSignal,
      specialist_adj: Math.round(specialistAdj * 10) / 10,
    },
  };
}
