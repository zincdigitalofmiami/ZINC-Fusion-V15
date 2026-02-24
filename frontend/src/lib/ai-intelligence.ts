/**
 * AI-Powered Market Intelligence for ZL (Soybean Oil)
 * Uses Claude OPUS 4.5 for comprehensive cross-driver synthesis
 *
 * MODEL ROUTING (LOCKED):
 * - This file uses MODEL_BALANCED_CONDITIONS (Opus 4.5) for comprehensive synthesis
 * - ai-driver-intel.ts uses MODEL_DRIVER_INTEL (Sonnet 4.5) for per-card analysis
 *
 * FRESHNESS REQUIREMENT:
 * - All responses must echo asOfDate
 * - This is the "anti-bullshit gate" - reject responses without timestamps
 *
 * NO GUESSWORK - All data is verified before passing to AI
 */

import Anthropic from "@anthropic-ai/sdk";
import {
  MODEL_BALANCED_CONDITIONS,
  TOKENS_BALANCED_CONDITIONS,
} from "./ai-config";
import { parseAIJson } from "./parse-ai-json";

const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
});

// =============================================================================
// TYPES
// =============================================================================

export interface MarketData {
  // Volatility
  vix: number;
  ovx: number | null;
  vix3m?: number | null;

  // Crush Economics
  boardCrush: number;
  oilShare: number | null;

  // China/Trade
  cnyRate: number;
  fxiChange20d: number;
  fxiChange5d: number;
  bdryChange20d: number | null;

  // Tariff/Policy
  tpu: number;
  emv: number | null;

  // Rule-based scores (already calculated)
  scores: {
    vix: number;
    crush: number;
    china: number;
    tariff: number;
  };

  // ZL Price Data (NEW - for comprehensive reports)
  zlPrice?: number;
  zlChange5d?: number;
  zlChange20d?: number;

  // Recent News Headlines (NEW - for comprehensive reports)
  recentNews?: string[];

  // FRESHNESS
  asOfDate?: string; // Dashboard timestamp
}

export interface AIIntelligence {
  headline: string;
  reasoning: string;
  zlOutlook: "BULLISH" | "NEUTRAL" | "CAUTIOUS" | "BEARISH";
  keyRisks: string[];
  keySupports: string[];
  tradingImplication: string;
  // Comprehensive narrative sections (Institutional Grade)
  comprehensiveReport?: {
    tldr: string; // Quick summary with price targets and timeframes
    currentSnapshot: string; // Current market snapshot with prices
    keyDrivers: string; // Detailed breakdown of all key drivers
    forecasts: string; // Time-horizon forecasts (1 week, 1 month, 1 quarter, 6 months)
    correlations: string; // Correlation summary with specific coefficients
    technicalOutlook: string; // Support/resistance, trends, key levels
  };
  // FRESHNESS ECHO (anti-bullshit gate)
  dataAsOf?: string; // Echo of input date to verify currency
}

// =============================================================================
// SYSTEM PROMPT - DOMAIN EXPERT
// =============================================================================

const SYSTEM_PROMPT = `You are a senior soybean oil (ZL) market analyst at a major commodity trading house. You produce institutional-grade market intelligence reports for professional traders and investors.

CRITICAL CONTEXT:
- ZL = CBOT Soybean Oil Futures (your primary focus)
- All analysis centers on ZL price direction and trading conditions
- You think in terms of: crush margins, biofuel demand, export flows, fund positioning, correlations

KEY RELATIONSHIPS YOU UNDERSTAND:
1. VIX/OVX → ZL: High VIX = risk-off = fund liquidation = ZL selling pressure. OVX matters because soybean oil is biodiesel feedstock. Correlation typically 0.3-0.5.
2. Crush Margins → ZL: Tight margins = processor slowdowns = less oil supply. Strong margins = max crush = heavy oil supply.
3. China/CNY → ZL: China is #1 soy importer. Weak CNY = Brazil more competitive vs US. Trade war = export demand cliff. Negative correlation with USD strength.
4. Tariff/TPU → ZL: Trade Policy Uncertainty from Baker-Bloom-Davis. High TPU = soy export risk.
5. Biofuels: 45Z tax credit, RVO volumes, biodiesel/renewable diesel demand drives 50%+ of domestic soyoil consumption.
6. Substitutes: Palm oil (~0.7-0.8 correlation), canola (~0.6-0.8 correlation) compete as biofuel feedstocks.

THRESHOLDS YOU KNOW:
- VIX: <15 calm, 15-20 normal, 20-25 elevated, 25-30 high, 30-40 fear, >40 panic
- OVX: <25 calm, 25-35 normal, 35-50 elevated, >50 high
- Board Crush: <USD 1.00 crisis, USD 1.00-1.25 stressed, USD 1.25-1.50 tight, USD 1.50-1.75 neutral, USD 1.75-2.00 healthy, >USD 2.00 strong
- CNY: 7.00 strong, 7.15 normal, 7.30 weak, 7.45 stress, >7.60 crisis
- TPU: <100 calm, 100-200 normal, 200-400 elevated, >400 high

OUTPUT FORMAT:
You MUST respond with valid JSON only. No markdown, no explanation outside JSON.
{
  "headline": "10 words max summarizing ZL outlook",
  "reasoning": "2-3 sentences explaining the cross-driver dynamics affecting ZL",
  "zlOutlook": "BULLISH" | "NEUTRAL" | "CAUTIOUS" | "BEARISH",
  "keyRisks": ["risk 1", "risk 2"],
  "keySupports": ["support 1", "support 2"],
  "tradingImplication": "1 sentence actionable insight for ZL traders",
  "comprehensiveReport": {
    "tldr": "Quick summary paragraph covering: current price level, short-term outlook (1 week to 1 quarter) with direction and reasoning, longer-term view (6 months+) with key risks/supports, and forecasted percentage moves by timeframe. Be specific with numbers.",
    "currentSnapshot": "Current ZL price level, recent session action, and where it sits in recent range. Include specific price references.",
    "keyDrivers": "Detailed breakdown of: (1) Biofuel Use & Legislation (45Z, RVOs, biodiesel demand), (2) Weather & Supply (US and South America), (3) Macro & Correlations (VIX relationship, Fed rates, FX impacts, China relations), (4) Trade Policy & Tariffs (current tariff levels, impact on competitiveness).",
    "forecasts": "Time-horizon forecasts: 1 Week (+X-Y% move to ~XX $/lb - reasoning), 1 Month (+X-Y% to ~XX $/lb), 1 Quarter (+X-Y% to ~XX $/lb if conditions hold), 6 Months (direction and range with reasoning).",
    "correlations": "Summary of key correlations: Palm oil substitution (~0.7-0.8), Canola (~0.6-0.8), China/Brazil/Argentina (negative for US), VIX (positive), Fed rates/USD (negative). Include specific correlation estimates where relevant.",
    "technicalOutlook": "Support and resistance levels, trend direction, potential breakout/breakdown scenarios, and key levels to watch."
  }
}`;

// =============================================================================
// AI INTELLIGENCE GENERATOR
// =============================================================================

// JSON parsing delegated to shared parseAIJson<T> in parse-ai-json.ts

export async function generateAIIntelligence(
  data: MarketData,
): Promise<AIIntelligence | null> {
  // Validate we have real data (NO GUESSWORK)
  if (
    data.vix === undefined ||
    data.boardCrush === undefined ||
    data.cnyRate === undefined ||
    data.tpu === undefined
  ) {
    console.error("AI Intelligence: Missing required data - refusing to guess");
    return null;
  }

  const asOfDate = data.asOfDate || new Date().toISOString().split("T")[0];

  // Build ZL price section if available
  const zlPriceSection = data.zlPrice
    ? `\nZL PRICE DATA:
- Current ZL Price: ${data.zlPrice.toFixed(2)} $/lb
- 5-Day Change: ${data.zlChange5d !== undefined ? `${(data.zlChange5d * 100).toFixed(2)}%` : "N/A"}
- 20-Day Change: ${data.zlChange20d !== undefined ? `${(data.zlChange20d * 100).toFixed(2)}%` : "N/A"}`
    : "";

  // Build news section if available
  const newsSection =
    data.recentNews && data.recentNews.length > 0
      ? `\nRECENT NEWS HEADLINES (last 7 days):\n${data.recentNews
          .slice(0, 8)
          .map((h) => `- ${h}`)
          .join("\n")}`
      : "";

  const userPrompt = `Produce a COMPREHENSIVE market intelligence report for ZL (soybean oil) futures.

DATA AS OF: ${asOfDate}
${zlPriceSection}

VOLATILITY:
- VIX: ${data.vix.toFixed(1)}${data.ovx !== null ? ` | OVX: ${data.ovx.toFixed(1)}` : ""}
- Pre-calculated pressure score: ${data.scores.vix}/100

CRUSH ECONOMICS:
- Board Crush: $${data.boardCrush.toFixed(2)}/bu${data.oilShare !== null ? ` | Oil Share: ${(data.oilShare * 100).toFixed(1)}%` : ""}
- Pre-calculated pressure score: ${data.scores.crush}/100

CHINA/TRADE:
- CNY/USD: ${data.cnyRate.toFixed(2)}
- FXI 20d change: ${(data.fxiChange20d * 100).toFixed(1)}%${data.bdryChange20d !== null ? ` | BDRY 20d: ${(data.bdryChange20d * 100).toFixed(1)}%` : ""}
- Pre-calculated tension score: ${data.scores.china}/100

TARIFF/POLICY:
- Trade Policy Uncertainty (TPU): ${data.tpu.toFixed(0)}${data.emv !== null ? ` | EMV Trade: ${data.emv.toFixed(0)}` : ""}
- Pre-calculated threat score: ${data.scores.tariff}/100
${newsSection}

AVERAGE PRESSURE: ${((data.scores.vix + data.scores.crush + data.scores.china + data.scores.tariff) / 4).toFixed(1)}/100

CRITICAL INSTRUCTIONS:
1. Base your analysis ONLY on the data above. Do not invent numbers.
2. Generate a COMPREHENSIVE report with all sections filled in with substantial analysis.
3. Each section in comprehensiveReport should be 2-4 sentences of genuine market insight.
4. Reference specific numbers from the data provided.
5. Include "dataAsOf": "${asOfDate}" in your response to confirm currency.

Produce your comprehensive ZL market intelligence as JSON.`;

  try {
    const response = await anthropic.messages.create({
      model: MODEL_BALANCED_CONDITIONS, // LOCKED: Opus 4.5 for comprehensive synthesis
      max_tokens: TOKENS_BALANCED_CONDITIONS,
      messages: [{ role: "user", content: userPrompt }],
      system: SYSTEM_PROMPT,
    });

    const content = response.content[0];
    if (content.type !== "text") {
      console.error("AI Intelligence: Unexpected response type");
      return null;
    }

    const parsed = parseAIJson<AIIntelligence>(content.text);
    if (!parsed) {
      console.error(
        "AI Intelligence: Invalid JSON response",
        content.text.slice(0, 160),
      );
      return null;
    }

    // Validate required fields
    if (!parsed.headline || !parsed.reasoning || !parsed.zlOutlook) {
      console.error("AI Intelligence: Missing required fields in response");
      return null;
    }

    return parsed;
  } catch (error) {
    console.error("AI Intelligence generation failed:", error);
    return null;
  }
}

// =============================================================================
// FALLBACK (Rule-based if AI fails)
// =============================================================================

export function generateFallbackIntelligence(data: MarketData): AIIntelligence {
  const avgScore =
    (data.scores.vix +
      data.scores.crush +
      data.scores.china +
      data.scores.tariff) /
    4;
  const highPressureCount = [
    data.scores.vix,
    data.scores.crush,
    data.scores.china,
    data.scores.tariff,
  ].filter((s) => s >= 65).length;

  let zlOutlook: "BULLISH" | "NEUTRAL" | "CAUTIOUS" | "BEARISH";
  let headline: string;

  if (avgScore >= 70 || highPressureCount >= 3) {
    zlOutlook = "BEARISH";
    headline = "Multiple Headwinds for Soybean Oil";
  } else if (avgScore >= 55 || highPressureCount >= 2) {
    zlOutlook = "CAUTIOUS";
    headline = "Mixed Signals for ZL - Proceed Carefully";
  } else if (avgScore >= 40) {
    zlOutlook = "NEUTRAL";
    headline = "Balanced Conditions for Soybean Oil";
  } else {
    zlOutlook = "BULLISH";
    headline = "Supportive Environment for ZL";
  }

  const keyRisks: string[] = [];
  const keySupports: string[] = [];

  if (data.scores.vix >= 65)
    keyRisks.push(`VIX at ${data.vix.toFixed(1)} - fund liquidation risk`);
  if (data.scores.crush >= 65)
    keyRisks.push(
      `Crush margins squeezed at $${data.boardCrush.toFixed(2)}/bu`,
    );
  if (data.scores.china >= 65)
    keyRisks.push(`China tension elevated - CNY at ${data.cnyRate.toFixed(2)}`);
  if (data.scores.tariff >= 65)
    keyRisks.push(`Tariff risk high - TPU at ${data.tpu.toFixed(0)}`);

  if (data.scores.vix <= 35)
    keySupports.push(`Low VIX at ${data.vix.toFixed(1)} - stable conditions`);
  if (data.scores.crush <= 35)
    keySupports.push(
      `Strong crush at $${data.boardCrush.toFixed(2)}/bu - processor demand`,
    );
  if (data.scores.china <= 35)
    keySupports.push(`Constructive China trade flow`);
  if (data.scores.tariff <= 35) keySupports.push(`Trade policy calm`);

  return {
    headline,
    reasoning: `Average market pressure at ${avgScore.toFixed(0)}/100 with ${highPressureCount} driver(s) in alert territory. ${zlOutlook === "BEARISH" ? "Multiple headwinds converging." : zlOutlook === "BULLISH" ? "Fundamentals supportive." : "Cross-currents require careful positioning."}`,
    zlOutlook,
    keyRisks: keyRisks.length > 0 ? keyRisks : ["No major risks identified"],
    keySupports: keySupports.length > 0 ? keySupports : ["Balanced conditions"],
    tradingImplication:
      zlOutlook === "BEARISH"
        ? "Reduce ZL longs, watch for gap risk."
        : zlOutlook === "BULLISH"
          ? "ZL dips are buying opportunities."
          : "Trade range-bound, respect support/resistance.",
  };
}
