import { NextResponse } from "next/server";

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

export async function POST(request: Request) {
  let payload: NarrativeRequest = {};
  try {
    payload = (await request.json()) as NarrativeRequest;
  } catch {
    // Keep empty payload; return null narratives instead of failing the page.
  }

  const fearGreedNarrative = buildFearGreedNarrative(payload.fearGreed);
  const trumpEffectNarrative = buildTrumpNarrative(payload.trumpEffect);
  const volatilityNarrative = buildVolatilityNarrative(payload.volatility);

  return NextResponse.json({
    fearGreedNarrative,
    trumpEffectNarrative,
    volatilityNarrative,
  });
}
