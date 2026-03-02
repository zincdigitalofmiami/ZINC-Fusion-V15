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
  weighted_action_score?: number | null;
  total_actions_7d?: number | null;
  eo_count_7d?: number | null;
  proclamation_count_7d?: number | null;
  avg_sentiment_7d?: number | null;
  action_velocity?: number | null;
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

  const actions = toNum(input.total_actions_7d);
  const score = toNum(input.weighted_action_score);
  const velocity = toNum(input.action_velocity);
  const sentiment = toNum(input.avg_sentiment_7d);

  const actionText =
    actions === null
      ? "Action volume is unavailable"
      : `Policy activity logged ${Math.round(actions)} actions over 7 days`;
  const scoreText =
    score === null
      ? "weighted policy score is unavailable"
      : `weighted policy score is ${score.toFixed(1)}`;
  const sentimentText =
    sentiment === null
      ? "sentiment is neutral/unknown"
      : sentiment > 0.1
        ? "policy tone is supportive"
        : sentiment < -0.1
          ? "policy tone is a headwind"
          : "policy tone is mixed";
  const velocityText =
    velocity === null ? "" : ` Velocity is ${velocity.toFixed(1)}.`;

  return `${actionText}; ${scoreText}, and ${sentimentText}.${velocityText}`;
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
      `Trump Effect: weighted_action_score=${te.weighted_action_score ?? 'N/A'}, ` +
      `actions_7d=${te.total_actions_7d ?? 'N/A'}, ` +
      `EOs_7d=${te.eo_count_7d ?? 'N/A'}, ` +
      `proclamations_7d=${te.proclamation_count_7d ?? 'N/A'}, ` +
      `avg_sentiment_7d=${te.avg_sentiment_7d ?? 'N/A'}, ` +
      `velocity=${te.action_velocity ?? 'N/A'}`
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
- trumpEffectNarrative: 1-2 sentences on policy activity and procurement implications
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
