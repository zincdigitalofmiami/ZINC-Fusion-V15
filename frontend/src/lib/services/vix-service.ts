/**
 * VIX Stress Scoring Service
 *
 * Matches volatility_pressure.py exactly.
 * Pure functions — no DB access, no side effects.
 */

// =============================================================================
// DOMAIN-SPECIFIC THRESHOLDS
// =============================================================================

// VIX Level Thresholds
const VIX = {
  COMPLACENT: 12,
  LOW: 15,
  NORMAL: 20,
  ELEVATED: 25,
  HIGH: 30,
  EXTREME: 40,
};

// VIX Term Structure (VIX/VIX3M ratio)
const TERM = {
  HEALTHY_CONTANGO: 0.85,
  NORMAL_CONTANGO: 0.92,
  FLAT: 1.0,
  BACKWARDATION: 1.05,
  SEVERE: 1.15,
};

// OVX (Oil Volatility) - biodiesel link
const OVX = { LOW: 25, NORMAL: 35, ELEVATED: 50, HIGH: 70 };

// VIX-ZL Correlation Thresholds (KEY SOY METRIC)
const VIX_ZL_CORR = { HIGH: 0.5, MODERATE: 0.3, LOW: 0.1, NEGATIVE: -0.1 };

// =============================================================================
// TYPES
// =============================================================================

export interface VixComponents {
  vix_level_score: number;
  vix_value: number;
  vix3m_value: number | null;
  vix_ratio: number | null;
  term_structure_adj: number;
  ovx_value: number | null;
  ovx_adj: number;
  realized_zl_vol: number | null;
  realized_vol_adj: number;
  vix_zl_correlation: number | null; // KEY SOY METRIC
  vix_zl_adj: number;
  hedge_article_count: number;
  hedge_adj: number;
  specialist_signal: number | null;
  specialist_adj: number;
}

// =============================================================================
// HELPER SCORERS
// =============================================================================

function scoreVixLevel(vix: number): { score: number; regime: string } {
  if (vix < VIX.COMPLACENT) return { score: 20, regime: "complacent" };
  if (vix < VIX.LOW) {
    const pct = (vix - VIX.COMPLACENT) / (VIX.LOW - VIX.COMPLACENT);
    return { score: 15 + pct * 10, regime: "low_vol" };
  }
  if (vix < VIX.NORMAL) {
    const pct = (vix - VIX.LOW) / (VIX.NORMAL - VIX.LOW);
    return { score: 25 + pct * 20, regime: "normal" };
  }
  if (vix < VIX.ELEVATED) {
    const pct = (vix - VIX.NORMAL) / (VIX.ELEVATED - VIX.NORMAL);
    return { score: 45 + pct * 15, regime: "elevated" };
  }
  if (vix < VIX.HIGH) {
    const pct = (vix - VIX.ELEVATED) / (VIX.HIGH - VIX.ELEVATED);
    return { score: 60 + pct * 15, regime: "high_vol" };
  }
  if (vix < VIX.EXTREME) {
    const pct = (vix - VIX.HIGH) / (VIX.EXTREME - VIX.HIGH);
    return { score: 75 + pct * 15, regime: "fear" };
  }
  const excess = Math.min(20, vix - VIX.EXTREME);
  return { score: Math.min(100, 90 + excess / 2), regime: "extreme_fear" };
}

function scoreTermStructure(
  vix: number,
  vix3m: number | null,
): { adj: number; desc: string } {
  if (!vix3m || vix3m === 0) return { adj: 0, desc: "No term structure data" };
  const ratio = vix / vix3m;
  if (ratio < TERM.HEALTHY_CONTANGO)
    return { adj: -15, desc: "Steep contango - very orderly" };
  if (ratio < TERM.NORMAL_CONTANGO) return { adj: -8, desc: "Normal contango" };
  if (ratio < TERM.FLAT) return { adj: -3, desc: "Mild contango" };
  if (ratio < TERM.BACKWARDATION)
    return { adj: 5, desc: "Flat to slight backwardation" };
  if (ratio < TERM.SEVERE)
    return { adj: 15, desc: "Backwardation - near-term stress" };
  return { adj: 25, desc: "Severe backwardation - panic mode" };
}

function scoreOvx(ovx: number | null): { adj: number; desc: string } {
  if (ovx === null) return { adj: 0, desc: "No OVX data" };
  if (ovx < OVX.LOW) return { adj: -5, desc: "Calm energy markets" };
  if (ovx < OVX.NORMAL) return { adj: 0, desc: "Normal oil volatility" };
  if (ovx < OVX.ELEVATED) {
    const pct = (ovx - OVX.NORMAL) / (OVX.ELEVATED - OVX.NORMAL);
    return { adj: pct * 12, desc: "Elevated oil volatility" };
  }
  if (ovx < OVX.HIGH) {
    const pct = (ovx - OVX.ELEVATED) / (OVX.HIGH - OVX.ELEVATED);
    return { adj: 12 + pct * 10, desc: "High oil volatility" };
  }
  return { adj: 25, desc: "Extreme oil volatility" };
}

function scoreVixZlCorrelation(corr: number | null): {
  adj: number;
  desc: string;
} {
  if (corr === null) return { adj: 0, desc: "No VIX-ZL correlation data" };
  if (corr >= VIX_ZL_CORR.HIGH) {
    const adj = 15 + Math.min(10, (corr - VIX_ZL_CORR.HIGH) * 40);
    return {
      adj,
      desc: `High VIX-ZL transmission (${corr.toFixed(2)}) - risk-off hitting soy`,
    };
  }
  if (corr >= VIX_ZL_CORR.MODERATE) {
    const pct =
      (corr - VIX_ZL_CORR.MODERATE) / (VIX_ZL_CORR.HIGH - VIX_ZL_CORR.MODERATE);
    return {
      adj: 5 + pct * 10,
      desc: `Moderate VIX-ZL correlation (${corr.toFixed(2)})`,
    };
  }
  if (corr >= VIX_ZL_CORR.LOW) {
    return {
      adj: 0,
      desc: `Low VIX-ZL correlation (${corr.toFixed(2)}) - fundamentals driving`,
    };
  }
  if (corr >= VIX_ZL_CORR.NEGATIVE) {
    return {
      adj: -5,
      desc: `Minimal VIX-ZL link (${corr.toFixed(2)}) - ZL independent`,
    };
  }
  return {
    adj: -10,
    desc: `Negative VIX-ZL (${corr.toFixed(2)}) - ZL acting as hedge`,
  };
}

function scoreHedgeSentiment(count: number): { adj: number; desc: string } {
  if (count >= 15)
    return {
      adj: 18,
      desc: `Heavy hedge focus (${count} articles) - farmer stress elevated`,
    };
  if (count >= 8)
    return { adj: 12, desc: `Elevated hedge discussion (${count} articles)` };
  if (count >= 4)
    return { adj: 5, desc: `Normal hedge coverage (${count} articles)` };
  if (count >= 1)
    return { adj: 0, desc: `Light hedge mentions (${count} articles)` };
  return { adj: -3, desc: "No hedge discussion - calm or complacent" };
}

// =============================================================================
// MAIN CALCULATOR
// =============================================================================

export function calculateVixStress(
  vix: number,
  vix3m: number | null,
  ovx: number | null,
  realizedVol: number | null,
  vixZlCorr: number | null,
  hedgeCount: number,
  specialistSignal: number | null,
): {
  score: number;
  level: string;
  regime: string;
  headline: string;
  components: VixComponents;
} {
  // Component 1: VIX Level (30%)
  const { score: vixScore, regime } = scoreVixLevel(vix);

  // Component 2: Term Structure (15%)
  const { adj: termAdj } = scoreTermStructure(vix, vix3m);

  // Component 3: OVX (10%)
  const { adj: ovxAdj } = scoreOvx(ovx);

  // Component 4: Realized Vol (10%)
  let rvAdj = 0;
  if (realizedVol !== null) {
    if (realizedVol < 0.18) rvAdj = -5;
    else if (realizedVol < 0.28) rvAdj = 0;
    else if (realizedVol < 0.38) rvAdj = 8;
    else if (realizedVol < 0.5) rvAdj = 15;
    else rvAdj = 20;
  }

  // Component 5: VIX-ZL Correlation (15%) - KEY SOY METRIC
  const { adj: vixZlAdj } = scoreVixZlCorrelation(vixZlCorr);

  // Component 6: ProFarmer Hedge Sentiment (10%)
  const { adj: hedgeAdj } = scoreHedgeSentiment(hedgeCount);

  // Component 7: Specialist Signal (10%)
  let specialistAdj = 0;
  if (specialistSignal !== null) {
    specialistAdj = specialistSignal * 10 * 0.5; // Apply with 0.5 confidence
  }

  // Composite Score (weighted)
  let score = vixScore;
  score += termAdj * (15 / 30);
  score += ovxAdj * (10 / 30);
  score += rvAdj * (10 / 30);
  score += vixZlAdj * (15 / 30); // KEY SOY METRIC - heavily weighted
  score += hedgeAdj * (10 / 30);
  score += specialistAdj * (10 / 30);
  score = Math.max(0, Math.min(100, score));

  // Level classification - ACTIONABLE LABELS
  let level: string;
  if (score >= 80) level = "Gap Risk";
  else if (score >= 65) level = "Fund Exit";
  else if (score >= 50) level = "Spread Widening";
  else if (score >= 35) level = "Normal";
  else if (score >= 20) level = "Calm";
  else level = "Compressing";

  // Soy-centric headlines with VIX-ZL correlation context (r = 0.4-0.6 typical)
  const headline =
    score >= 80
      ? "ZL Gap Risk - VIX Panic Mode (0.5+ correlation)"
      : score >= 65
        ? "Fund Liquidation - VIX Selling ZL (0.4+ correlation)"
        : score >= 50
          ? "VIX Elevated - Watch ZL Spread Blowouts"
          : score >= 35
            ? "Normal VIX - ZL Trading on Fundamentals"
            : "Low VIX - Stable ZL, Fundamentals-Driven";

  return {
    score: Math.round(score * 10) / 10,
    level,
    regime,
    headline,
    components: {
      vix_level_score: Math.round(vixScore * 10) / 10,
      vix_value: Math.round(vix * 10) / 10,
      vix3m_value: vix3m ? Math.round(vix3m * 10) / 10 : null,
      vix_ratio: vix3m ? Math.round((vix / vix3m) * 1000) / 1000 : null,
      term_structure_adj: Math.round(termAdj * 10) / 10,
      ovx_value: ovx ? Math.round(ovx * 10) / 10 : null,
      ovx_adj: Math.round(ovxAdj * 10) / 10,
      realized_zl_vol: realizedVol ? Math.round(realizedVol * 1000) / 10 : null, // As percentage
      realized_vol_adj: Math.round(rvAdj * 10) / 10,
      vix_zl_correlation: vixZlCorr
        ? Math.round(vixZlCorr * 1000) / 1000
        : null,
      vix_zl_adj: Math.round(vixZlAdj * 10) / 10,
      hedge_article_count: hedgeCount,
      hedge_adj: Math.round(hedgeAdj * 10) / 10,
      specialist_signal: specialistSignal,
      specialist_adj: Math.round(specialistAdj * 10) / 10,
    },
  };
}
