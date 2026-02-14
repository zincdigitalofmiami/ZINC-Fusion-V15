/**
 * China Tension Scoring Service
 *
 * Matches china_tension.py exactly.
 * Pure functions — no DB access, no side effects.
 */

// =============================================================================
// DOMAIN-SPECIFIC THRESHOLDS
// =============================================================================

// CNY/USD Rate
const CNY = { STRONG: 7.0, NORMAL: 7.15, WEAK: 7.3, STRESS: 7.45, CRISIS: 7.6 };

// Shipping (BDRY) 20d change thresholds - DISABLED: ETF data quality issues
const SHIP = { COLLAPSE: -0.25, WEAK: -0.1, STABLE: 0.1, STRONG: 0.2 };

// =============================================================================
// TYPES
// =============================================================================

export interface ChinaComponents {
  fxi_score: number;
  fxi_change_20d: number;
  fxi_change_5d: number;
  cny_score: number;
  cny_rate: number;
  cny_change_20d: number | null;
  ship_score: number;
  bdry_change_20d: number | null;
  soy_china_news_count: number;
  news_score: number;
  specialist_signal: number | null;
  specialist_score: number;
}

// =============================================================================
// HELPER SCORERS
// =============================================================================

function scoreFxiPerformance(
  change20d: number,
  change5d: number,
): { score: number; desc: string } {
  let base: number, desc: string;
  if (change20d <= -0.15) {
    base = 90;
    desc = "China equities in freefall";
  } else if (change20d <= -0.1) {
    base = 80;
    desc = "China equities severely weak";
  } else if (change20d <= -0.05) {
    base = 65;
    desc = "China equities under pressure";
  } else if (change20d <= -0.02) {
    base = 55;
    desc = "China equities soft";
  } else if (change20d <= 0.02) {
    base = 45;
    desc = "China equities stable";
  } else if (change20d <= 0.05) {
    base = 35;
    desc = "China equities firming";
  } else if (change20d <= 0.1) {
    base = 25;
    desc = "China equities rallying";
  } else {
    base = 20;
    desc = "China equities surging";
  }

  // Short-term momentum modifier
  if (change5d < -0.05) {
    base = Math.min(100, base + 10);
    desc += " (accelerating weakness)";
  } else if (change5d > 0.05) {
    base = Math.max(0, base - 5);
    desc += " (near-term bounce)";
  }

  return { score: base, desc };
}

function scoreCnyLevel(
  rate: number,
  change20d: number | null,
): { score: number; desc: string } {
  let levelScore: number, levelDesc: string;
  if (rate < CNY.STRONG) {
    levelScore = 25;
    levelDesc = "Yuan strong";
  } else if (rate < CNY.NORMAL) {
    levelScore = 35;
    levelDesc = "Yuan stable";
  } else if (rate < CNY.WEAK) {
    levelScore = 50;
    levelDesc = "Yuan slightly weak";
  } else if (rate < CNY.STRESS) {
    levelScore = 65;
    levelDesc = "Yuan weak";
  } else if (rate < CNY.CRISIS) {
    levelScore = 80;
    levelDesc = "Yuan under pressure";
  } else {
    levelScore = 90;
    levelDesc = "Yuan crisis level";
  }

  // Rate of change modifier
  let rocAdj = 0,
    rocDesc = "";
  if (change20d !== null) {
    if (change20d >= 0.02) {
      rocAdj = 15;
      rocDesc = ", devaluing rapidly";
    } else if (change20d >= 0.01) {
      rocAdj = 8;
      rocDesc = ", weakening";
    } else if (change20d <= -0.02) {
      rocAdj = -15;
      rocDesc = ", strengthening rapidly";
    } else if (change20d <= -0.01) {
      rocAdj = -8;
      rocDesc = ", firming";
    }
  }

  return {
    score: Math.max(0, Math.min(100, levelScore + rocAdj)),
    desc: levelDesc + rocDesc,
  };
}

function scoreShipping(change20d: number | null): {
  score: number;
  desc: string;
} {
  if (change20d === null) return { score: 50, desc: "No shipping data" };
  if (change20d <= SHIP.COLLAPSE)
    return { score: 85, desc: "Shipping rates collapsed" };
  if (change20d <= SHIP.WEAK) return { score: 70, desc: "Shipping rates weak" };
  if (change20d <= SHIP.STABLE)
    return { score: 45, desc: "Shipping rates stable" };
  if (change20d <= SHIP.STRONG)
    return { score: 30, desc: "Shipping rates firm" };
  return { score: 25, desc: "Shipping rates surging" };
}

function scoreChinaNews(
  count: number,
  total: number,
): { score: number; desc: string } {
  if (total === 0) return { score: 50, desc: "No news data" };
  const concentration = count / total;
  if (count >= 50)
    return {
      score: Math.min(100, 80 + (count - 30) / 2),
      desc: `Heavy China focus (${count} articles)`,
    };
  if (concentration > 0.3)
    return { score: 80, desc: `Heavy China focus (${count} articles)` };
  if (concentration > 0.2)
    return { score: 65, desc: `Elevated China coverage (${count} articles)` };
  if (concentration > 0.1)
    return { score: 50, desc: `Normal China coverage (${count} articles)` };
  return { score: 35, desc: `Light China coverage (${count} articles)` };
}

// =============================================================================
// MAIN CALCULATOR
// =============================================================================

export function calculateChinaTension(
  fxiChange20d: number,
  fxiChange5d: number,
  cnyRate: number,
  cnyChange20d: number | null,
  bdryChange20d: number | null,
  soyChinaNews: number,
  totalNews: number,
  specialistSignal: number | null,
): {
  score: number;
  level: string;
  regime: string;
  headline: string;
  components: ChinaComponents;
} {
  // Component 1: FXI Performance (20%)
  const { score: fxiScore } = scoreFxiPerformance(fxiChange20d, fxiChange5d);

  // Component 2: CNY Level/Trend (25%)
  const { score: cnyScore } = scoreCnyLevel(cnyRate, cnyChange20d);

  // Component 3: Shipping BDRY (30%) - direct trade flow proxy
  const { score: shipScore } = scoreShipping(bdryChange20d);

  // Component 4: Soy China News (15%)
  const { score: newsScore } = scoreChinaNews(soyChinaNews, totalNews);

  // Component 5: Specialist Signal (10%)
  let specialistScore = 50;
  if (specialistSignal !== null) {
    specialistScore = 50 - specialistSignal * 25 * 0.5; // Negative signal = bearish = more tension
    specialistScore = Math.max(0, Math.min(100, specialistScore));
  }

  // Composite Score (SOY-CENTRIC WEIGHTS from Python)
  // Shipping 30%, CNY 25%, FXI 20%, News 15%, Specialist 10%
  const score = Math.max(
    0,
    Math.min(
      100,
      shipScore * 0.3 +
        cnyScore * 0.25 +
        fxiScore * 0.2 +
        newsScore * 0.15 +
        specialistScore * 0.1,
    ),
  );

  // Regime (internal state machine)
  let regime: string;
  if (score >= 75) regime = "crisis";
  else if (score >= 60) regime = "high_tension";
  else if (score >= 45) regime = "elevated";
  else if (score >= 30) regime = "normal";
  else regime = "low_tension";

  // Level - MEANINGFUL LABELS (not vague terms like "Constructive")
  // Note: US faces 13% tariff vs 3% for Brazil/Argentina - structural disadvantage
  let level: string;
  if (score >= 75) level = "Trade Freeze";
  else if (score >= 60) level = "Export Risk";
  else if (score >= 45) level = "Monitor Flows";
  else if (score >= 30)
    level = "Brazil Favored"; // Structural disadvantage always present
  else level = "Brazil Dominates"; // Low tension doesn't mean US competitive

  // Headlines - ACCURATE REALITY (US has 13% tariff disadvantage vs Brazil's 3%)
  // Even "low tension" means Brazil outcompetes US due to tariff structure
  const headline =
    score >= 75
      ? "ZL Bearish - China Export Freeze"
      : score >= 60
        ? "ZL Cautious - Trade War Escalation"
        : score >= 45
          ? "Monitor USDA Export Pace - 13% Tariff Drag"
          : score >= 30
            ? "Brazil Preferred - US Tariff Disadvantage (13% vs 3%)"
            : "China Stable but Brazil Dominates US at 13% Tariff Gap";

  return {
    score: Math.round(score * 10) / 10,
    level,
    regime,
    headline,
    components: {
      fxi_score: Math.round(fxiScore * 10) / 10,
      fxi_change_20d: Math.round(fxiChange20d * 1000) / 10, // As percentage
      fxi_change_5d: Math.round(fxiChange5d * 1000) / 10,
      cny_score: Math.round(cnyScore * 10) / 10,
      cny_rate: Math.round(cnyRate * 100) / 100,
      cny_change_20d: cnyChange20d
        ? Math.round(cnyChange20d * 1000) / 10
        : null,
      ship_score: Math.round(shipScore * 10) / 10,
      bdry_change_20d: bdryChange20d
        ? Math.round(bdryChange20d * 1000) / 10
        : null,
      soy_china_news_count: soyChinaNews,
      news_score: Math.round(newsScore * 10) / 10,
      specialist_signal: specialistSignal,
      specialist_score: Math.round(specialistScore * 10) / 10,
    },
  };
}
