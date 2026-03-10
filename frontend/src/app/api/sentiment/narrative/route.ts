import { NextResponse } from "next/server";
import { generateText } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { MODEL_DRIVER_INTEL } from "@/lib/ai-config";

export const dynamic = "force-dynamic";

type FearGreedPayload = {
  score?: number | null;
  zone?: string | null;
  label?: string | null;
};

type TrumpEffectPayload = {
  title?: string | null;
  zl_return_7d_pct?: number | null;
  zl_response_1d_pct?: number | null;
  zl_response_5d_pct?: number | null;
  response_signal?: string | null;
  weighted_action_score?: number | null;
  total_actions_7d?: number | null;
  executive_orders_7d?: number | null;
  other_actions_7d?: number | null;
  action_velocity?: number | null;
  confirmation_score?: number | null;
  confirmation_band?: string | null;
  independent_policy_items_7d?: number | null;
  market_news_items_7d?: number | null;
  regulatory_follow_through_7d?: number | null;
  buyer_signal?: string | null;
  buyer_label?: string | null;
};

type VolatilityPayload = {
  vix?: number | null;
  ovx?: number | null;
  realized_21d?: number | null;
};

type NarrativeRequest = {
  fearGreed?: FearGreedPayload;
  trumpEffect?: TrumpEffectPayload;
  volatility?: VolatilityPayload;
};

function toNum(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

// =============================================================================
// STATIC FALLBACK TEMPLATES (used when AI is unavailable)
// =============================================================================

function buildFearGreedNarrative(input?: FearGreedPayload): string | null {
  if (!input) return null;
  const score = toNum(input.score);
  if (score === null) return null;

  const bias =
    score >= 70
      ? "risk appetite is elevated"
      : score <= 35
        ? "the market is trading defensively"
        : "positioning is balanced";

  const zoneLabel = input.label || input.zone || "current zone";
  return `Fear & Greed is ${Math.round(score)} (${zoneLabel}); ${bias}. Use this as context with price and positioning, not as a standalone timing signal.`;
}

function buildTrumpNarrative(input?: TrumpEffectPayload): string | null {
  if (!input) return null;

  const title = input.title || "Policy Impact on ZL";
  const response7d = toNum(input.zl_return_7d_pct);
  const response1d = toNum(input.zl_response_1d_pct);
  const actions = toNum(input.total_actions_7d);
  const eos = toNum(input.executive_orders_7d);
  const otherActions = toNum(input.other_actions_7d);
  const velocity = toNum(input.action_velocity);
  const score = toNum(input.weighted_action_score);
  const confirmationScore = toNum(input.confirmation_score);
  const band = (input.confirmation_band || "").toLowerCase();
  const buyerLabel = input.buyer_label;
  const responseSignal = input.response_signal;

  const activityText =
    actions === null
      ? "Policy activity is unavailable"
      : `${Math.round(actions)} presidential actions this week (${Math.round(eos ?? 0)} executive orders, ${Math.round(otherActions ?? Math.max(0, actions - (eos ?? 0)))} other actions)`;
  const scoreText =
    score === null
      ? "weighted policy pressure is unavailable"
      : `weighted policy pressure is ${score.toFixed(1)}`;
  const confirmationText =
    confirmationScore === null
      ? "independent confirmation is unavailable"
      : `independent confirmation is ${confirmationScore}/100 (${band || "unknown"})`;
  const responseText =
    response7d === null
      ? "ZL response is unavailable"
      : `ZL moved ${response7d > 0 ? "+" : ""}${response7d.toFixed(2)}% over the policy window${response1d == null ? "" : ` and ${response1d > 0 ? "+" : ""}${response1d.toFixed(2)}% over 1d`} (${responseSignal || "unknown"} response)`;
  const velocityText = velocity === null ? "" : ` velocity ${velocity.toFixed(1)}/day`;
  const buyerText = buyerLabel ? ` Buyer meaning: ${buyerLabel}.` : "";

  return `${title}: ${activityText}${velocityText}; ${scoreText}; ${confirmationText}; ${responseText}.${buyerText}`;
}

function buildVolatilityNarrative(input?: VolatilityPayload): string | null {
  if (!input) return null;
  const vix = toNum(input.vix);
  const ovx = toNum(input.ovx);
  const realized = toNum(input.realized_21d);

  if (vix === null && ovx === null && realized === null) return null;

  const vixState =
    vix === null
      ? "VIX unavailable"
      : vix >= 30
        ? `VIX ${vix.toFixed(1)} (high stress)`
        : vix >= 20
          ? `VIX ${vix.toFixed(1)} (elevated)`
          : `VIX ${vix.toFixed(1)} (contained)`;
  const ovxState =
    ovx === null
      ? "OVX unavailable"
      : ovx >= 45
        ? `OVX ${ovx.toFixed(1)} (energy risk elevated)`
        : `OVX ${ovx.toFixed(1)} (energy risk moderate)`;
  const realizedState =
    realized === null
      ? "realized volatility unavailable"
      : `21d realized ${realized.toFixed(1)}%`;

  return `${vixState}; ${ovxState}; ${realizedState}. Expect wider intraday ranges when all three remain elevated together.`;
}

// =============================================================================
// AI NARRATIVE GENERATION (Vercel AI SDK + Claude Sonnet 4.5)
// =============================================================================

async function generateAINarratives(payload: NarrativeRequest): Promise<{
  fearGreedNarrative: string | null;
  trumpEffectNarrative: string | null;
  volatilityNarrative: string | null;
} | null> {
  if (!process.env.ANTHROPIC_API_KEY) return null;

  // Build context from available data
  const dataPoints: string[] = [];

  if (payload.fearGreed) {
    const fg = payload.fearGreed;
    dataPoints.push(`Fear & Greed Index: ${fg.score ?? 'N/A'} (Zone: ${fg.label || fg.zone || 'unknown'})`);
  }

  if (payload.trumpEffect) {
    const te = payload.trumpEffect;
    dataPoints.push(
      `Policy Impact on ZL: weighted_action_score=${te.weighted_action_score ?? 'N/A'}, ` +
      `actions_7d=${te.total_actions_7d ?? 'N/A'}, ` +
      `EOs_7d=${te.executive_orders_7d ?? 'N/A'}, ` +
      `other_actions_7d=${te.other_actions_7d ?? 'N/A'}, ` +
      `confirmation_score=${te.confirmation_score ?? 'N/A'}, ` +
      `confirmation_band=${te.confirmation_band ?? 'N/A'}, ` +
      `zl_return_7d_pct=${te.zl_return_7d_pct ?? 'N/A'}, ` +
      `zl_response_1d_pct=${te.zl_response_1d_pct ?? 'N/A'}, ` +
      `response_signal=${te.response_signal ?? 'N/A'}, ` +
      `buyer_label=${te.buyer_label ?? 'N/A'}`
    );
  }

  if (payload.volatility) {
    const vol = payload.volatility;
    dataPoints.push(
      `Volatility: VIX=${vol.vix ?? 'N/A'}, OVX=${vol.ovx ?? 'N/A'}, realized_21d=${vol.realized_21d ?? 'N/A'}%`
    );
  }

  if (dataPoints.length === 0) return null;

  try {
    const { text } = await generateText({
      model: anthropic(MODEL_DRIVER_INTEL),
      maxOutputTokens: 600,
      system: `You are a commodity procurement analyst for a US soybean oil buyer. Write concise, actionable intelligence narratives. No preamble, no hedging. Speak directly to a procurement buyer who needs to decide when to buy.

Return EXACTLY a JSON object with these keys (use null if no data for that section):
- fearGreedNarrative: 1-2 sentences on market sentiment and what it means for timing
- trumpEffectNarrative: 1-2 sentences that clearly separate policy activity, independent confirmation, and actual ZL response for procurement risk
- volatilityNarrative: 1-2 sentences on vol regime and what it means for coverage decisions

Be specific. Use the numbers. Tell them what to DO, not what might happen.`,
      prompt: `Current market data:\n${dataPoints.join('\n')}\n\nGenerate procurement intelligence narratives.`,
    });

    // Parse JSON response
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) return null;
    const parsed = JSON.parse(jsonMatch[0]);
    return {
      fearGreedNarrative: parsed.fearGreedNarrative || null,
      trumpEffectNarrative: parsed.trumpEffectNarrative || null,
      volatilityNarrative: parsed.volatilityNarrative || null,
    };
  } catch (e) {
    console.error("[narrative] AI generation failed, using static fallback:", e);
    return null;
  }
}

// =============================================================================
// HANDLER
// =============================================================================

export async function POST(request: Request) {
  let payload: NarrativeRequest = {};
  try {
    payload = (await request.json()) as NarrativeRequest;
  } catch {
    // Keep empty payload; return null narratives instead of failing the page.
  }

  // Try AI narratives first, fall back to static templates
  const aiNarratives = await generateAINarratives(payload);

  if (aiNarratives) {
    return NextResponse.json({
      fearGreedNarrative: aiNarratives.fearGreedNarrative ?? buildFearGreedNarrative(payload.fearGreed),
      trumpEffectNarrative: aiNarratives.trumpEffectNarrative ?? buildTrumpNarrative(payload.trumpEffect),
      volatilityNarrative: aiNarratives.volatilityNarrative ?? buildVolatilityNarrative(payload.volatility),
      source: 'ai',
    });
  }

  // Static fallback
  return NextResponse.json({
    fearGreedNarrative: buildFearGreedNarrative(payload.fearGreed),
    trumpEffectNarrative: buildTrumpNarrative(payload.trumpEffect),
    volatilityNarrative: buildVolatilityNarrative(payload.volatility),
    source: 'static',
  });
}
