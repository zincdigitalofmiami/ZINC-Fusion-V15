import { NextResponse } from "next/server";
import { query } from "@/lib/db";
import {
  generateAIIntelligence,
  type MarketData,
  type AIIntelligence,
} from "@/lib/ai-intelligence";
import {
  generateDriverIntel,
  generateFallbackDriverIntel,
  type DriverIntel,
} from "@/lib/ai-driver-intel";
import {
  scoreTpu,
  scoreEmv,
  scoreLegislationVelocity,
  scoreNewsVelocity,
} from "@/lib/services/policy-service";

export const dynamic = "force-dynamic";
// Vercel Pro allows up to 300s. The 3 AM cron is the ONLY call that generates
// AI — let it take as long as it needs. Every other request serves from cache.
export const maxDuration = 300;

const CACHE_STALE_WHILE_REVALIDATE_SECONDS = 60 * 60;

// Must match frontend/vercel.json daily cron (3 AM UTC).
const DAILY_REFRESH_UTC_HOUR = 3;
const DAILY_REFRESH_UTC_MINUTE = 0;

// =============================================================================
// DAILY AI CACHE — Anthropic runs ONCE at 3 AM UTC, cached until next 3 AM
// =============================================================================
const AI_REFRESH_UTC_HOUR = 3; // Reset AI cache at 3 AM UTC each day

interface AiCacheEntry {
  dayKey: string;
  aiIntelligence: AIIntelligence | null;
  vixIntel: DriverIntel | null;
  crushIntel: DriverIntel | null;
  chinaIntel: DriverIntel | null;
  tariffIntel: DriverIntel | null;
}

// Module-level singleton — persists across requests within the same serverless
// instance. On Vercel, cold starts get a fresh cache = one AI call, then all
// subsequent requests in that instance reuse it until 5 AM UTC rolls over.
let aiCache: AiCacheEntry | null = null;

/** Returns YYYY-MM-DD for the current "AI day" (resets at 5 AM UTC). */
function getAiDayKey(now = new Date()): string {
  // Before 5 AM UTC → still "yesterday's" AI day
  const d = new Date(now);
  if (d.getUTCHours() < AI_REFRESH_UTC_HOUR) {
    d.setUTCDate(d.getUTCDate() - 1);
  }
  return d.toISOString().slice(0, 10);
}

function getAiCache(): AiCacheEntry | null {
  if (!aiCache) return null;
  if (aiCache.dayKey !== getAiDayKey()) return null; // stale — new day
  return aiCache;
}

function setAiCache(entry: AiCacheEntry): void {
  aiCache = entry;
}

function getDailyRefreshMeta(now = new Date()) {
  const nextRefresh = new Date(
    Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate(),
      DAILY_REFRESH_UTC_HOUR,
      DAILY_REFRESH_UTC_MINUTE,
      0,
      0,
    ),
  );
  if (now >= nextRefresh) nextRefresh.setUTCDate(nextRefresh.getUTCDate() + 1);

  const sMaxAge = Math.max(
    60,
    Math.floor((nextRefresh.getTime() - now.getTime()) / 1000),
  );
  const headers = {
    "Cache-Control": `public, s-maxage=${sMaxAge}, stale-while-revalidate=${CACHE_STALE_WHILE_REVALIDATE_SECONDS}`,
    "X-Narrative-Next-Refresh-Utc": nextRefresh.toISOString(),
  };

  return {
    nextRefreshUtc: nextRefresh.toISOString(),
    headers,
  };
}

// =============================================================================
// DOMAIN-SPECIFIC THRESHOLDS
// Matched exactly to Python pressure calculators
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

// Board Crush ($/bushel)
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

// CNY/USD Rate
const CNY = { STRONG: 7.0, NORMAL: 7.15, WEAK: 7.3, STRESS: 7.45, CRISIS: 7.6 };

// Shipping (BDRY) 20d change thresholds - DISABLED: ETF data quality issues
const SHIP = { COLLAPSE: -0.25, WEAK: -0.1, STABLE: 0.1, STRONG: 0.2 };

// =============================================================================
// VIX STRESS SCORING (Full Sophistication)
// Matches volatility_pressure.py exactly
// =============================================================================

interface VixComponents {
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

function calculateVixStress(
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

// =============================================================================
// CRUSH PRESSURE SCORING (Full Sophistication)
// Matches crush_pressure.py exactly
// =============================================================================

interface CrushComponents {
  board_crush_score: number;
  board_crush_value: number;
  oil_share_value: number | null;
  oil_share_level_adj: number;
  oil_share_5d_change: number | null;
  oil_share_trend_adj: number;
  specialist_signal: number | null;
  specialist_adj: number;
}

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

function calculateCrushPressure(
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

  // Headlines with board crush context (<$1 crisis, $1.50 neutral, >$2 strong)
  const headline =
    score >= 75
      ? "ZL Mixed - Crush Plants Idling (<$1.00/bu margins)"
      : score >= 55
        ? "ZL Cautious - Processor Margins Tight ($1.00-1.50/bu)"
        : score >= 40
          ? "ZL Neutral - Crush Economics Balanced (~$1.50/bu)"
          : score >= 25
            ? "ZL Supportive - Healthy Crush ($1.75+/bu)"
            : "ZL Watch Supply - Max Crush at $2+/bu";

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

// =============================================================================
// CHINA TENSION SCORING (Full Sophistication)
// Matches china_tension.py exactly
// =============================================================================

interface ChinaComponents {
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

function calculateChinaTension(
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

// =============================================================================
// TARIFF THREAT SCORING (Full Sophistication)
// Matches policy_pressure.py exactly
// =============================================================================

interface TariffComponents {
  tpu_score: number;
  tpu_value: number;
  emv_score: number;
  emv_value: number | null;
  legislation_count: number;
  legislation_adj: number;
  soy_tariff_news_count: number;
  soy_tariff_news_adj: number;
  specialist_signal: number | null;
  specialist_adj: number;
}

function calculateTariffThreat(
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

// =============================================================================
// NARRATIVE GENERATOR
// =============================================================================

interface DriverResult {
  score: number;
  level: string;
  regime: string;
  headline: string;
}

function generateMarketIntelligence(
  vix: DriverResult,
  _vixValue: number,
  crush: DriverResult,
  crushValue: number,
  oilShare: number | null,
  china: DriverResult,
  cnyRate: number,
  fxiChange20d: number,
  tariff: DriverResult,
  _tpuValue: number,
): {
  headline: string;
  summary: string;
  drivers: { label: string; outlook: string; detail: string }[];
  zlOutlook: "BULLISH" | "NEUTRAL" | "CAUTIOUS" | "BEARISH";
  zlColor: string;
} {
  const avgScore = (vix.score + crush.score + china.score + tariff.score) / 4;
  const highPressureCount = [
    vix.score,
    crush.score,
    china.score,
    tariff.score,
  ].filter((s) => s >= 65).length;
  const lowPressureCount = [
    vix.score,
    crush.score,
    china.score,
    tariff.score,
  ].filter((s) => s <= 35).length;

  let zlOutlook: "BULLISH" | "NEUTRAL" | "CAUTIOUS" | "BEARISH";
  let zlColor: string;
  let headline: string;

  // VEGAS BUYER LANGUAGE - DIRECT AND ACTIONABLE
  if (avgScore >= 70 || highPressureCount >= 3) {
    zlOutlook = "BEARISH";
    zlColor = "#EF4444";
    headline = "WAIT TO BUY - Multiple Red Flags";
  } else if (avgScore >= 55 || highPressureCount >= 2) {
    zlOutlook = "CAUTIOUS";
    zlColor = "#F97316";
    headline = "CAUTION - Mixed Signals, Keep Powder Dry";
  } else if (avgScore >= 40) {
    zlOutlook = "NEUTRAL";
    zlColor = "#EAB308";
    headline = "NORMAL MARKET - Buy On Schedule";
  } else {
    zlOutlook = "BULLISH";
    zlColor = "#22C55E";
    headline = "GOOD WINDOW - Lock In Coverage";
  }

  // BUILD PLAIN ENGLISH SUMMARY FOR VEGAS BUYERS
  const summaryParts: string[] = [];

  // Lead with the action
  if (avgScore >= 65) {
    summaryParts.push(`Bottom line: HOLD OFF on new purchases.`);
  } else if (avgScore <= 35) {
    summaryParts.push(`Bottom line: Good time to cover your needs.`);
  } else {
    summaryParts.push(`Bottom line: Normal market conditions.`);
  }

  // Volatility - simple
  if (vix.score >= 65) {
    summaryParts.push(`Wall Street is panicking - prices could swing wildly.`);
  } else if (vix.score <= 35) {
    summaryParts.push(`Markets are calm - stable pricing environment.`);
  }

  // Crush - what it means for supply
  if (crush.score >= 65) {
    summaryParts.push(
      `Crushers struggling at $${crushValue.toFixed(2)}/bu margins - supply may tighten.`,
    );
  } else if (crush.score <= 35) {
    summaryParts.push(
      `Crushers making money at $${crushValue.toFixed(2)}/bu - plenty of oil supply.`,
    );
  }

  // China - keep it real
  if (china.score >= 65) {
    summaryParts.push(
      `China trade is frozen - that's hurting overall soybean demand.`,
    );
  } else {
    summaryParts.push(
      `China is buying from Brazil (13% tariff gap vs US) - that's just reality.`,
    );
  }

  // Tariff - cut the noise
  if (tariff.score >= 65) {
    summaryParts.push(`Trade war risk is elevated - stay defensive.`);
  } else if (tariff.score <= 35) {
    summaryParts.push(`Trade policy is quiet - no new threats.`);
  }

  // Final recommendation
  if (highPressureCount >= 2) {
    summaryParts.push(
      `RECOMMENDATION: Wait for better entry. Too many headwinds right now.`,
    );
  } else if (lowPressureCount >= 3) {
    summaryParts.push(
      `RECOMMENDATION: Lock in coverage. Conditions favor buyers.`,
    );
  } else {
    summaryParts.push(
      `RECOMMENDATION: Normal buying on your schedule. Nothing dramatic either way.`,
    );
  }

  const drivers = [
    {
      label: "Markets",
      outlook:
        vix.score >= 65
          ? "PANIC"
          : vix.score >= 50
            ? "NERVOUS"
            : vix.score <= 35
              ? "CALM"
              : "OK",
      detail:
        vix.score >= 65
          ? "Funds selling everything"
          : vix.score <= 35
            ? "Stable, fundamentals-driven"
            : "Normal volatility",
    },
    {
      label: "Crush",
      outlook:
        crush.score >= 65 ? "TIGHT" : crush.score <= 35 ? "FLUSH" : "NORMAL",
      detail: `$${crushValue.toFixed(2)}/bu margins - ${crush.score >= 65 ? "plants slowing" : crush.score <= 35 ? "running full out" : "normal pace"}`,
    },
    {
      label: "China",
      outlook: china.score >= 65 ? "FROZEN" : "BRAZIL WINS",
      detail:
        china.score >= 65
          ? "Trade disrupted"
          : `Brazil preferred at 13% tariff gap`,
    },
    {
      label: "Trade",
      outlook:
        tariff.score >= 65 ? "RISK" : tariff.score <= 35 ? "QUIET" : "NOISE",
      detail:
        tariff.score >= 65
          ? "War risk elevated"
          : tariff.score <= 35
            ? "Policy stable"
            : "Headlines, no action",
    },
  ];

  return {
    headline,
    summary: summaryParts.join(" "),
    drivers,
    zlOutlook,
    zlColor,
  };
}

// =============================================================================
// MAIN API HANDLER - Full Sophistication Queries
// =============================================================================

// The nightly cron (3 AM UTC) is the ONLY request that calls Anthropic.
// No timeout — let it cook. Every daytime request serves from cache.
const AI_TIMEOUT_MS = 120_000; // 2 min safety net, but cron has 300s total

function withTimeout<T>(
  promise: Promise<T>,
  ms: number,
  fallback: T,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  return Promise.race([
    promise.then((v) => {
      clearTimeout(timer);
      return v;
    }),
    new Promise<T>((resolve) => {
      timer = setTimeout(() => resolve(fallback), ms);
    }),
  ]);
}

export async function GET() {
  try {
    // Parallel queries for all data sources
    const [
      vixRows,
      vix3mRows,
      ovxRows,
      realizedVolRows,
      vixZlCorrRows,
      hedgeNewsRows,
      crushRows,
      oilShare5dRows,
      cnyRows,
      cnyChangeRows,
      fxiRows,
      bdryRows,
      soyChinaNewsRows,
      totalNewsRows,
      tpuRows,
      legislationRows,
      soyTariffNewsRows,
      volSignalRows,
      crushSignalRows,
      chinaSignalRows,
      tariffSignalRows,
      zlPriceRows,
      recentNewsRows,
    ] = await Promise.all([
      // === VIX STRESS DATA ===
      query<{ vix: number; event_date: string }>(`
        SELECT value::float8 as vix, event_date::text FROM econ.vol_indices_1d
        WHERE series_id = 'VIXCLS' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      query<{ vix3m: number }>(`
        SELECT value::float8 as vix3m FROM econ.vol_indices_1d
        WHERE series_id = 'VXVCLS' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      query<{ ovx: number }>(`
        SELECT value::float8 as ovx FROM econ.vol_indices_1d
        WHERE series_id = 'OVXCLS' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      // Realized ZL Volatility (63-day annualized)
      query<{ realized_vol: number }>(`
        WITH returns AS (
          SELECT (close - LAG(close) OVER (ORDER BY event_date)) /
                 NULLIF(LAG(close) OVER (ORDER BY event_date), 0) as ret
          FROM analytics.zl_price_1d
          ORDER BY event_date DESC LIMIT 63
        )
        SELECT STDDEV(ret) * SQRT(252) as realized_vol FROM returns WHERE ret IS NOT NULL
      `),
      // VIX-ZL Correlation (KEY SOY METRIC - 20-day rolling)
      query<{ vix_zl_corr: number }>(`
        WITH vix_changes AS (
          SELECT event_date, value - LAG(value) OVER (ORDER BY event_date) as vix_change
          FROM econ.vol_indices_1d WHERE series_id = 'VIXCLS'
          ORDER BY event_date DESC LIMIT 25
        ),
        zl_changes AS (
          SELECT event_date, (close - LAG(close) OVER (ORDER BY event_date)) /
                 NULLIF(LAG(close) OVER (ORDER BY event_date), 0) as zl_ret
          FROM analytics.zl_price_1d ORDER BY event_date DESC LIMIT 25
        )
        SELECT CORR(v.vix_change, z.zl_ret) as vix_zl_corr
        FROM vix_changes v JOIN zl_changes z ON v.event_date = z.event_date
        WHERE v.vix_change IS NOT NULL AND z.zl_ret IS NOT NULL
      `),
      // ProFarmer Hedge Sentiment (7 days)
      query<{ count: number }>(`
        SELECT COUNT(*)::int as count FROM alt.profarmer_news
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
        AND (content ILIKE '%hedge%' OR content ILIKE '%hedging%' OR content ILIKE '%volatility%'
             OR content ILIKE '%options%' OR content ILIKE '%protection%' OR content ILIKE '%risk management%')
      `),

      // === CRUSH PRESSURE DATA ===
      query<{ crush: number; oil_share: number | null; trade_date: string }>(`
        SELECT board_crush::float8 as crush, oil_share::float8 as oil_share, trade_date::text
        FROM analytics.board_crush_1d WHERE board_crush IS NOT NULL
        ORDER BY trade_date DESC LIMIT 1
      `),
      // Oil Share 5 days ago (for trend)
      query<{ oil_share_5d: number }>(`
        SELECT oil_share::float8 as oil_share_5d FROM analytics.board_crush_1d
        WHERE oil_share IS NOT NULL ORDER BY trade_date DESC OFFSET 5 LIMIT 1
      `),

      // === CHINA TENSION DATA ===
      query<{ rate: number; event_date: string }>(`
        SELECT rate::float8 as rate, event_date::text FROM mkt.fx_1d
        WHERE pair IN ('USD/CNY', 'USDCNY') AND rate IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),
      // CNY 20-day change
      query<{ rate_20d: number }>(`
        SELECT rate::float8 as rate_20d FROM mkt.fx_1d
        WHERE pair IN ('USD/CNY', 'USDCNY') AND rate IS NOT NULL
        ORDER BY event_date DESC OFFSET 20 LIMIT 1
      `),
      // FXI - DISABLED: ETF data has reverse-split artifacts
      // Returns neutral defaults (0% change)
      Promise.resolve([{ price: 0, change_20d: 0, change_5d: 0 }]),
      // BDRY - DISABLED: ETF data has quality issues
      // Returns neutral default (0% change)
      Promise.resolve([{ change_20d: 0 }]),
      // Soy China News (ProFarmer)
      query<{ count: number }>(`
        SELECT COUNT(*)::int as count FROM alt.profarmer_news
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
        AND ((headline ILIKE '%china%' AND (headline ILIKE '%soy%' OR headline ILIKE '%bean%' OR headline ILIKE '%export%'))
             OR headline ILIKE '%trade war%' OR headline ILIKE '%tariff%' OR headline ILIKE '%export sales%'
             OR content ILIKE '%china soy%' OR content ILIKE '%soybean export%' OR content ILIKE '%chinese import%')
      `),
      // Total ProFarmer News (for concentration)
      query<{ count: number }>(`
        SELECT COUNT(*)::int as count FROM alt.profarmer_news
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
      `),

      // === TARIFF THREAT DATA ===
      // NOTE: Using USEPUINDXM (main EPU) instead of EPUTRADE - EPUTRADE is stale (Dec 2025)
      query<{ tpu: number; tpu_date: string; emv: number | null }>(`
        SELECT
          (SELECT value FROM econ.vol_indices_1d WHERE series_id = 'USEPUINDXM' AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1)::float8 as tpu,
          (SELECT event_date::text FROM econ.vol_indices_1d WHERE series_id = 'USEPUINDXM' AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1) as tpu_date,
          (SELECT value FROM econ.vol_indices_1d WHERE series_id = 'EMVTRADEPOLEMV' AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1)::float8 as emv
      `),
      // Legislation Velocity (14 days)
      query<{ count: number }>(`
        SELECT COUNT(*)::int as count FROM alt.legislation_1d
        WHERE event_date >= CURRENT_DATE - INTERVAL '14 days'
        AND (title ILIKE '%trade%' OR title ILIKE '%tariff%' OR title ILIKE '%import%' OR title ILIKE '%export%')
      `).catch(() => [{ count: 0 }]), // Table might not exist
      // Soy Tariff News (ProFarmer)
      query<{ count: number }>(`
        SELECT COUNT(*)::int as count FROM alt.profarmer_news
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
        AND (headline ILIKE '%tariff%' OR headline ILIKE '%trade war%' OR headline ILIKE '%retaliatory%'
             OR (headline ILIKE '%soy%' AND headline ILIKE '%duty%')
             OR (headline ILIKE '%china%' AND headline ILIKE '%tariff%')
             OR content ILIKE '%soy tariff%' OR content ILIKE '%soybean tariff%' OR content ILIKE '%25 percent%')
      `),

      // === SPECIALIST SIGNALS ===
      // DISABLED: Data in training.specialist_signals_1d is FAKE/PLACEHOLDER:
      // - volatility: outputs only 0/1/2/3 discrete values (not real GARCH), all recent = 1.0
      // - Real specialist models (GARCH, XGB, ARDL, etc.) have NOT been trained
      // - 82K rows exist but are rule-based script output, not ML model predictions
      // Enable when REAL trained specialist models exist in models/specialists/
      Promise.resolve([] as { signal: number }[]), // volSignal - FAKE (regime labels only)
      Promise.resolve([] as { signal: number }[]), // crushSignal - FAKE (not trained XGB)
      Promise.resolve([] as { signal: number }[]), // chinaSignal - FAKE (not trained GBM)
      Promise.resolve([] as { signal: number }[]), // tariffSignal - FAKE (not trained tree)

      // === ZL PRICE DATA (for comprehensive reports) ===
      query<{ close: number; change_5d: number; change_20d: number }>(`
        WITH zl AS (
          SELECT close, ROW_NUMBER() OVER (ORDER BY event_date DESC) as rn
          FROM analytics.zl_price_1d WHERE close IS NOT NULL LIMIT 21
        )
        SELECT
          (SELECT close FROM zl WHERE rn = 1)::float8 as close,
          CASE WHEN (SELECT close FROM zl WHERE rn = 6) > 0
               THEN ((SELECT close FROM zl WHERE rn = 1) - (SELECT close FROM zl WHERE rn = 6)) / (SELECT close FROM zl WHERE rn = 6)
               ELSE 0 END::float8 as change_5d,
          CASE WHEN (SELECT close FROM zl WHERE rn = 21) > 0
               THEN ((SELECT close FROM zl WHERE rn = 1) - (SELECT close FROM zl WHERE rn = 21)) / (SELECT close FROM zl WHERE rn = 21)
               ELSE 0 END::float8 as change_20d
      `),

      // === RECENT NEWS HEADLINES (for comprehensive reports) ===
      query<{ headline: string }>(`
        SELECT headline FROM alt.profarmer_news
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
        AND headline IS NOT NULL
        ORDER BY event_date DESC
        LIMIT 10
      `).catch(() => [] as { headline: string }[]),
    ]);

    // Extract values — NO FALLBACKS. If primary data is missing, we fail honestly.
    const vixValue = vixRows[0]?.vix ?? null;
    const vixDate = vixRows[0]?.event_date ?? null;
    const vix3mValue = vix3mRows[0]?.vix3m ?? null;
    const ovxValue = ovxRows[0]?.ovx ?? null;
    const realizedVol = realizedVolRows[0]?.realized_vol ?? null;
    const vixZlCorr = vixZlCorrRows[0]?.vix_zl_corr ?? null;
    const hedgeCount = hedgeNewsRows[0]?.count ?? 0;
    const volSignal = volSignalRows[0]?.signal ?? null;

    const crushValue = crushRows[0]?.crush ?? null;
    const crushDate = crushRows[0]?.trade_date ?? null;
    const oilShareValue = crushRows[0]?.oil_share ?? null;
    const oilShare5dAgo = oilShare5dRows[0]?.oil_share_5d ?? null;
    const crushSignal = crushSignalRows[0]?.signal ?? null;

    const cnyRate = cnyRows[0]?.rate ?? null;
    const cnyDate = cnyRows[0]?.event_date ?? null;
    const cnyRate20d = cnyChangeRows[0]?.rate_20d ?? null;
    const cnyChange20d =
      cnyRate20d && cnyRate && cnyRate20d > 0
        ? (cnyRate - cnyRate20d) / cnyRate20d
        : null;
    const fxiChange20d = fxiRows[0]?.change_20d ?? 0;
    const fxiChange5d = fxiRows[0]?.change_5d ?? 0;
    const bdryChange20d = bdryRows[0]?.change_20d ?? null;
    const soyChinaNews = soyChinaNewsRows[0]?.count ?? 0;
    const totalNews = totalNewsRows[0]?.count ?? 1;
    const chinaSignal = chinaSignalRows[0]?.signal ?? null;

    const tpuValue = tpuRows[0]?.tpu ?? null;
    const tpuDate = tpuRows[0]?.tpu_date ?? null;
    const emvValue = tpuRows[0]?.emv ?? null;
    const legislationCount = legislationRows[0]?.count ?? 0;
    const soyTariffNews = soyTariffNewsRows[0]?.count ?? 0;
    const tariffSignal = tariffSignalRows[0]?.signal ?? null;

    // HARD STOP: If any primary driver data is missing, return 503.
    // All 4 drivers are interconnected — partial data produces wrong results.
    const missing: string[] = [];
    if (vixValue === null) missing.push("VIX (econ.vol_indices_1d VIXCLS)");
    if (crushValue === null)
      missing.push("Board Crush (analytics.board_crush_1d)");
    if (cnyRate === null) missing.push("CNY Rate (mkt.fx_1d USD/CNY)");
    if (tpuValue === null) missing.push("TPU (econ.vol_indices_1d USEPUINDXM)");
    if (missing.length > 0) {
      return NextResponse.json(
        {
          error:
            "Missing required market data — all 4 drivers must have live data",
          missing,
          data_quality: {
            vix: { date: vixDate, available: vixValue !== null },
            crush: { date: crushDate, available: crushValue !== null },
            cny: { date: cnyDate, available: cnyRate !== null },
            tpu: { date: tpuDate, available: tpuValue !== null },
          },
        },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }

    // ZL Price Data for comprehensive reports
    const zlPrice = zlPriceRows[0]?.close ?? null;
    const zlChange5d = zlPriceRows[0]?.change_5d ?? null;
    const zlChange20d = zlPriceRows[0]?.change_20d ?? null;

    // Recent news headlines for comprehensive reports
    const recentNews = recentNewsRows?.map((r) => r.headline) ?? [];

    const asOfDate = new Date().toISOString().split("T")[0];

    // Past the 503 guard: all 4 primary values are guaranteed non-null
    const vix = vixValue as number;
    const crush = crushValue as number;
    const cny = cnyRate as number;
    const tpu = tpuValue as number;

    // Data quality tracking
    const today = new Date();
    const daysSince = (dateStr: string | null) => {
      if (!dateStr) return null;
      const d = new Date(dateStr);
      return Math.floor(
        (today.getTime() - d.getTime()) / (1000 * 60 * 60 * 24),
      );
    };
    const dataFreshness = {
      vix: {
        date: vixDate,
        days_old: daysSince(vixDate),
        status:
          daysSince(vixDate) !== null && daysSince(vixDate)! <= 2
            ? "fresh"
            : "stale",
      },
      crush: {
        date: crushDate,
        days_old: daysSince(crushDate),
        status:
          daysSince(crushDate) !== null && daysSince(crushDate)! <= 2
            ? "fresh"
            : "stale",
      },
      cny: {
        date: cnyDate,
        days_old: daysSince(cnyDate),
        status:
          daysSince(cnyDate) !== null && daysSince(cnyDate)! <= 5
            ? "fresh"
            : "stale",
      },
      tpu: {
        date: tpuDate,
        days_old: daysSince(tpuDate),
        status:
          daysSince(tpuDate) !== null && daysSince(tpuDate)! <= 45
            ? "fresh"
            : "stale",
      },
      vix3m: {
        available: vix3mValue !== null,
        note:
          vix3mValue === null
            ? "VXVCLS (VIX 3-month) series not found"
            : "Term structure calc enabled",
      },
      specialist_signals: {
        available: false,
        note: "Specialist models not trained yet. No signal data.",
      },
    };

    // Calculate scores with full sophistication
    const vixResult = calculateVixStress(
      vix,
      vix3mValue,
      ovxValue,
      realizedVol,
      vixZlCorr,
      hedgeCount,
      volSignal,
    );
    const crushResult = calculateCrushPressure(
      crush,
      oilShareValue,
      oilShare5dAgo,
      crushSignal,
    );
    const chinaResult = calculateChinaTension(
      fxiChange20d,
      fxiChange5d,
      cny,
      cnyChange20d,
      bdryChange20d,
      soyChinaNews,
      totalNews,
      chinaSignal,
    );
    const tariffResult = calculateTariffThreat(
      tpu,
      emvValue,
      legislationCount,
      soyTariffNews,
      tariffSignal,
    );

    // Generate narrative
    const ruleBasedIntelligence = generateMarketIntelligence(
      vixResult,
      vix,
      crushResult,
      crush,
      oilShareValue,
      chinaResult,
      cny,
      fxiChange20d,
      tariffResult,
      tpu,
    );

    // Prepare AI data
    const marketData: MarketData = {
      vix,
      ovx: ovxValue,
      boardCrush: crush,
      oilShare: oilShareValue,
      cnyRate: cny,
      fxiChange20d,
      fxiChange5d,
      bdryChange20d,
      tpu,
      emv: emvValue,
      scores: {
        vix: vixResult.score,
        crush: crushResult.score,
        china: chinaResult.score,
        tariff: tariffResult.score,
      },
      // ZL Price Data for comprehensive reports
      zlPrice: zlPrice ?? undefined,
      zlChange5d: zlChange5d ?? undefined,
      zlChange20d: zlChange20d ?? undefined,
      // Recent news for comprehensive reports
      recentNews: recentNews.length > 0 ? recentNews : undefined,
      asOfDate,
    };

    // -----------------------------------------------------------------------
    // DAILY AI CACHE — only call Anthropic ONCE per day, reuse until 5 AM UTC
    // -----------------------------------------------------------------------
    const cached = getAiCache();
    let aiIntelligence: AIIntelligence | null;
    let vixIntel: DriverIntel | null;
    let crushIntel: DriverIntel | null;
    let chinaIntel: DriverIntel | null;
    let tariffIntel: DriverIntel | null;

    if (cached) {
      // Cache hit — skip ALL Anthropic calls
      aiIntelligence = cached.aiIntelligence;
      vixIntel = cached.vixIntel;
      crushIntel = cached.crushIntel;
      chinaIntel = cached.chinaIntel;
      tariffIntel = cached.tariffIntel;
    } else {
      // Cache miss — call AI with timeout, then cache for the rest of the day
      [aiIntelligence, vixIntel, crushIntel, chinaIntel, tariffIntel] =
        await Promise.all([
          withTimeout(
            generateAIIntelligence(marketData).catch(() => null),
            AI_TIMEOUT_MS,
            null,
          ),
          withTimeout(
            generateDriverIntel({
              driverName: "vix",
              score: vixResult.score,
              level: vixResult.level,
              regime: vixResult.regime,
              components: vixResult.components as unknown as Record<
                string,
                number | null
              >,
              asOfDate,
            }).catch(() => null),
            AI_TIMEOUT_MS,
            null,
          ),
          withTimeout(
            generateDriverIntel({
              driverName: "crush",
              score: crushResult.score,
              level: crushResult.level,
              regime: crushResult.regime,
              components: crushResult.components as unknown as Record<
                string,
                number | null
              >,
              asOfDate,
            }).catch(() => null),
            AI_TIMEOUT_MS,
            null,
          ),
          withTimeout(
            generateDriverIntel({
              driverName: "china",
              score: chinaResult.score,
              level: chinaResult.level,
              regime: chinaResult.regime,
              components: chinaResult.components as unknown as Record<
                string,
                number | null
              >,
              asOfDate,
            }).catch(() => null),
            AI_TIMEOUT_MS,
            null,
          ),
          withTimeout(
            generateDriverIntel({
              driverName: "tariff",
              score: tariffResult.score,
              level: tariffResult.level,
              regime: tariffResult.regime,
              components: tariffResult.components as unknown as Record<
                string,
                number | null
              >,
              asOfDate,
            }).catch(() => null),
            AI_TIMEOUT_MS,
            null,
          ),
        ]);

      // Persist to cache — all subsequent requests today skip AI entirely
      setAiCache({
        dayKey: getAiDayKey(),
        aiIntelligence,
        vixIntel,
        crushIntel,
        chinaIntel,
        tariffIntel,
      });
    }

    const intelligence = aiIntelligence
      ? {
          headline: aiIntelligence.headline,
          summary: aiIntelligence.reasoning,
          drivers: [
            ...aiIntelligence.keyRisks.map((r) => ({
              label: "Risk",
              outlook: "PRESSURE" as const,
              detail: r,
            })),
            ...aiIntelligence.keySupports.map((s) => ({
              label: "Support",
              outlook: "SUPPORTIVE" as const,
              detail: s,
            })),
          ],
          zlOutlook: aiIntelligence.zlOutlook,
          zlColor:
            aiIntelligence.zlOutlook === "BEARISH"
              ? "#EF4444"
              : aiIntelligence.zlOutlook === "CAUTIOUS"
                ? "#F97316"
                : aiIntelligence.zlOutlook === "NEUTRAL"
                  ? "#EAB308"
                  : "#22C55E",
          tradingImplication: aiIntelligence.tradingImplication,
          comprehensiveReport: aiIntelligence.comprehensiveReport, // Institutional-grade full report
          aiPowered: true,
        }
      : { ...ruleBasedIntelligence, aiPowered: false };

    // Fallbacks - PASS FULL COMPONENTS for data-rich templates
    const vixWhatsHappening =
      vixIntel ??
      generateFallbackDriverIntel({
        driverName: "vix",
        score: vixResult.score,
        level: vixResult.level,
        regime: vixResult.regime,
        components: vixResult.components as unknown as Record<
          string,
          number | null
        >,
        asOfDate,
      });
    const crushWhatsHappening =
      crushIntel ??
      generateFallbackDriverIntel({
        driverName: "crush",
        score: crushResult.score,
        level: crushResult.level,
        regime: crushResult.regime,
        components: crushResult.components as unknown as Record<
          string,
          number | null
        >,
        asOfDate,
      });
    const chinaWhatsHappening =
      chinaIntel ??
      generateFallbackDriverIntel({
        driverName: "china",
        score: chinaResult.score,
        level: chinaResult.level,
        regime: chinaResult.regime,
        components: chinaResult.components as unknown as Record<
          string,
          number | null
        >,
        asOfDate,
      });
    const tariffWhatsHappening =
      tariffIntel ??
      generateFallbackDriverIntel({
        driverName: "tariff",
        score: tariffResult.score,
        level: tariffResult.level,
        regime: tariffResult.regime,
        components: tariffResult.components as unknown as Record<
          string,
          number | null
        >,
        asOfDate,
      });

    const refreshMeta = getDailyRefreshMeta();

    return NextResponse.json(
      {
        as_of_date: asOfDate,
        narrative_refresh: {
          cadence: "daily",
          next_refresh_utc: refreshMeta.nextRefreshUtc,
          ai_cached: !!cached,
          ai_cache_day: getAiDayKey(),
        },
        drivers: {
          vix_stress: {
            name: "VIX Stress",
            score: vixResult.score,
            level: vixResult.level,
            regime: vixResult.regime,
            headline: vixResult.headline,
            components: vixResult.components,
            whatsHappening: vixWhatsHappening,
            aiPowered: vixIntel !== null,
            dataDate: vixDate, // Source data freshness
          },
          crush_pressure: {
            name: "Crush Pressure",
            score: crushResult.score,
            level: crushResult.level,
            regime: crushResult.regime,
            headline: crushResult.headline,
            components: crushResult.components,
            whatsHappening: crushWhatsHappening,
            aiPowered: crushIntel !== null,
            dataDate: crushDate, // Source data freshness
          },
          china_tension: {
            name: "China Tension",
            score: chinaResult.score,
            level: chinaResult.level,
            regime: chinaResult.regime,
            headline: chinaResult.headline,
            components: chinaResult.components,
            whatsHappening: chinaWhatsHappening,
            aiPowered: chinaIntel !== null,
            dataDate: cnyDate, // Source data freshness
          },
          tariff_threat: {
            name: "Tariff Threat",
            score: tariffResult.score,
            level: tariffResult.level,
            regime: tariffResult.regime,
            headline: tariffResult.headline,
            components: tariffResult.components,
            whatsHappening: tariffWhatsHappening,
            aiPowered: tariffIntel !== null,
            dataDate: tpuDate, // Source data freshness (monthly series)
          },
        },
        summary: {
          average_pressure:
            Math.round(
              ((vixResult.score +
                crushResult.score +
                chinaResult.score +
                tariffResult.score) /
                4) *
                10,
            ) / 10,
          highest_pressure: [
            { name: "VIX Stress", score: vixResult.score },
            { name: "Crush Pressure", score: crushResult.score },
            { name: "China Tension", score: chinaResult.score },
            { name: "Tariff Threat", score: tariffResult.score },
          ].sort((a, b) => b.score - a.score)[0],
          alert_count: [
            vixResult.score,
            crushResult.score,
            chinaResult.score,
            tariffResult.score,
          ].filter((s) => s >= 65).length,
        },
        intelligence,
        data_quality: dataFreshness,
      },
      { headers: refreshMeta.headers },
    );
  } catch (error) {
    console.error("Market drivers query failed:", error);
    return NextResponse.json(
      { error: "Market drivers query failed", details: String(error) },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
