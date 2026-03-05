/**
 * Energy Stress Scoring Service
 *
 * Tracks crude oil (CL) price movements and OVX (oil volatility) to detect
 * energy supply shocks that affect soybean oil via the biofuel channel.
 *
 * Causal chain: Iran war → Hormuz shutdown → crude supply shock →
 * higher energy prices → biofuel economics shift → more soy oil diverted
 * to renewable diesel → ZL prices UP → BAD for Chris (buyer).
 *
 * Pure functions — no DB access, no side effects.
 */

// =============================================================================
// THRESHOLDS
// =============================================================================

const CL_CHANGE_5D = {
  SMALL: 0.02,    // 2% — normal noise
  MODERATE: 0.04, // 4% — notable move
  LARGE: 0.07,    // 7% — supply shock territory
  EXTREME: 0.12,  // 12%+ — crisis (war, embargo)
};

const CL_CHANGE_20D = {
  SMALL: 0.05,    // 5% — trending
  LARGE: 0.10,    // 10% — sustained move
  EXTREME: 0.20,  // 20%+ — structural shift
};

const OVX_THRESHOLDS = {
  LOW: 25,
  NORMAL: 35,
  ELEVATED: 50,
  HIGH: 70,
};

const ENERGY_NEWS_THRESHOLDS = {
  BACKGROUND: 2,
  ELEVATED: 5,
  CRISIS: 10,
};

// =============================================================================
// TYPES
// =============================================================================

export interface EnergyComponents {
  cl_price: number | null;
  cl_change_5d: number | null;
  cl_change_20d: number | null;
  ovx_value: number | null;
  energy_news_count: number;
  cl_level_score: number;
  cl_momentum_adj: number;
  ovx_adj: number;
  news_adj: number;
}

export interface EnergyResult {
  score: number;
  level: string;
  regime: string;
  headline: string;
  components: EnergyComponents;
}

// =============================================================================
// SCORER
// =============================================================================

export function calculateEnergyStress(
  clPrice: number | null,
  clChange5d: number | null,
  clChange20d: number | null,
  ovx: number | null,
  energyNewsCount: number,
): EnergyResult {
  // Default: no data → score 50 (neutral, not zero)
  if (clPrice === null && clChange5d === null && ovx === null) {
    return {
      score: 50,
      level: "No Data",
      regime: "unknown",
      headline: "Energy data unavailable",
      components: {
        cl_price: null, cl_change_5d: null, cl_change_20d: null,
        ovx_value: null, energy_news_count: energyNewsCount,
        cl_level_score: 0, cl_momentum_adj: 0, ovx_adj: 0, news_adj: 0,
      },
    };
  }

  // --- CL 5-day momentum score (primary signal) ---
  let clLevelScore = 40; // base: neutral
  const abs5d = Math.abs(clChange5d ?? 0);
  const sign5d = (clChange5d ?? 0) >= 0 ? 1 : -1;

  if (abs5d >= CL_CHANGE_5D.EXTREME) {
    clLevelScore = sign5d > 0 ? 90 : 15; // crude surging = huge ZL risk; crashing = ZL relief
  } else if (abs5d >= CL_CHANGE_5D.LARGE) {
    clLevelScore = sign5d > 0 ? 78 : 22;
  } else if (abs5d >= CL_CHANGE_5D.MODERATE) {
    clLevelScore = sign5d > 0 ? 65 : 30;
  } else if (abs5d >= CL_CHANGE_5D.SMALL) {
    clLevelScore = sign5d > 0 ? 55 : 38;
  }

  // --- CL 20-day trend adjustment ---
  let clMomentumAdj = 0;
  if (clChange20d !== null) {
    const abs20d = Math.abs(clChange20d);
    const sign20d = clChange20d >= 0 ? 1 : -1;
    if (abs20d >= CL_CHANGE_20D.EXTREME) {
      clMomentumAdj = sign20d > 0 ? 12 : -8;
    } else if (abs20d >= CL_CHANGE_20D.LARGE) {
      clMomentumAdj = sign20d > 0 ? 7 : -5;
    } else if (abs20d >= CL_CHANGE_20D.SMALL) {
      clMomentumAdj = sign20d > 0 ? 3 : -2;
    }
  }

  // --- OVX adjustment ---
  let ovxAdj = 0;
  if (ovx !== null) {
    if (ovx >= OVX_THRESHOLDS.HIGH) ovxAdj = 10;
    else if (ovx >= OVX_THRESHOLDS.ELEVATED) ovxAdj = 6;
    else if (ovx >= OVX_THRESHOLDS.NORMAL) ovxAdj = 2;
    else if (ovx < OVX_THRESHOLDS.LOW) ovxAdj = -3;
  }

  // --- Energy news velocity adjustment ---
  let newsAdj = 0;
  if (energyNewsCount >= ENERGY_NEWS_THRESHOLDS.CRISIS) newsAdj = 8;
  else if (energyNewsCount >= ENERGY_NEWS_THRESHOLDS.ELEVATED) newsAdj = 4;
  else if (energyNewsCount >= ENERGY_NEWS_THRESHOLDS.BACKGROUND) newsAdj = 1;

  // --- Final score ---
  const raw = clLevelScore + clMomentumAdj + ovxAdj + newsAdj;
  const score = Math.max(0, Math.min(100, Math.round(raw)));

  // --- Level classification ---
  let level: string;
  let regime: string;
  if (score >= 80) {
    level = "Crisis";
    regime = "energy_crisis";
  } else if (score >= 65) {
    level = "Supply Shock";
    regime = "supply_shock";
  } else if (score >= 50) {
    level = "Elevated";
    regime = "elevated";
  } else if (score >= 35) {
    level = "Normal";
    regime = "normal";
  } else {
    level = "Low Risk";
    regime = "low_risk";
  }

  // --- Headline ---
  const pctStr = clChange5d !== null ? `${(clChange5d * 100).toFixed(1)}%` : "?%";
  let headline: string;
  if (score >= 80) {
    headline = `ENERGY CRISIS — Crude oil ${sign5d > 0 ? "+" : ""}${pctStr} in 5 days. Supply disruption driving biofuel costs higher.`;
  } else if (score >= 65) {
    headline = `Oil supply shock — CL ${sign5d > 0 ? "+" : ""}${pctStr} (5d). Energy costs rising, biofuel margins pressured.`;
  } else if (score >= 50) {
    headline = `Energy markets elevated — crude ${sign5d > 0 ? "+" : ""}${pctStr} (5d). Watch for biofuel demand impact.`;
  } else if (score >= 35) {
    headline = `Energy markets normal. Crude oil steady — no supply disruption.`;
  } else {
    headline = `Energy tailwind — falling crude eases biofuel cost pressure on soy oil.`;
  }

  return {
    score,
    level,
    regime,
    headline,
    components: {
      cl_price: clPrice,
      cl_change_5d: clChange5d,
      cl_change_20d: clChange20d,
      ovx_value: ovx,
      energy_news_count: energyNewsCount,
      cl_level_score: clLevelScore,
      cl_momentum_adj: clMomentumAdj,
      ovx_adj: ovxAdj,
      news_adj: newsAdj,
    },
  };
}
