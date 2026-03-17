export type FearGreedNarrativePayload = {
  score?: number | null;
  zone?: string | null;
  label?: string | null;
};

export type TrumpEffectNarrativePayload = {
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
  corroboration_score?: number | null;
  corroboration_band?: string | null;
  supporting_policy_items_7d?: number | null;
  market_news_items_7d?: number | null;
  regulatory_follow_through_7d?: number | null;
  procurement_signal?: string | null;
  procurement_label?: string | null;
};

export type VolatilityNarrativePayload = {
  vix?: number | null;
  ovx?: number | null;
  realized_21d?: number | null;
};

export interface SentimentNarratives {
  fearGreedNarrative: string | null;
  trumpEffectNarrative: string | null;
  volatilityNarrative: string | null;
}

function toNum(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

function formatMove(value: number, windowLabel: string): string {
  const magnitude = `${Math.abs(value).toFixed(2)}%`;
  if (value > 0) return `rose ${magnitude} in ${windowLabel}`;
  if (value < 0) return `fell ${magnitude} in ${windowLabel}`;
  return `was unchanged (${magnitude}) in ${windowLabel}`;
}

export function buildFearGreedNarrative(
  input?: FearGreedNarrativePayload,
): string | null {
  if (!input) return null;
  const score = toNum(input.score);
  if (score === null) return null;

  const bias =
    score >= 70
      ? "risk appetite is elevated"
      : score <= 35
        ? "risk aversion is elevated"
        : "signals are balanced";

  const zoneLabel = input.label || input.zone || "current zone";
  return `Fear & Greed is ${Math.round(score)} (${zoneLabel}); ${bias}. Use this with price and positioning, not as a standalone timing signal.`;
}

export function buildTrumpNarrative(
  input?: TrumpEffectNarrativePayload,
): string | null {
  if (!input) return null;

  const title = input.title || "Impact on Soybean Oil Futures";
  const response7d = toNum(input.zl_return_7d_pct);
  const response1d = toNum(input.zl_response_1d_pct);
  const actions = toNum(input.total_actions_7d);
  const eos = toNum(input.executive_orders_7d);
  const otherActions = toNum(input.other_actions_7d);
  const velocity = toNum(input.action_velocity);
  const score = toNum(input.weighted_action_score);
  const corroborationScore = toNum(input.corroboration_score);
  const band = (input.corroboration_band || "").toLowerCase();
  const procurementLabel = input.procurement_label;
  const responseSignal = input.response_signal;
  const supportingItems = toNum(input.supporting_policy_items_7d);
  const marketItems = toNum(input.market_news_items_7d);
  const regulatoryItems = toNum(input.regulatory_follow_through_7d);

  const activityText =
    actions === null
      ? "policy activity unavailable"
      : `${Math.round(actions)} actions this week (${Math.round(eos ?? 0)} executive, ${Math.round(otherActions ?? Math.max(0, actions - (eos ?? 0)))} other)`;
  const scoreText =
    score === null
      ? "policy pressure unavailable"
      : `weighted pressure ${score.toFixed(1)}`;
  const corroborationText =
    corroborationScore === null
      ? "corroboration unavailable"
      : `corroboration ${corroborationScore}/100 (${band || "unknown"})`;
  const responseText =
    response7d === null
      ? "ZL response unavailable"
      : `ZL ${formatMove(response7d, "the 7d policy window")}${response1d == null ? "" : ` and ${formatMove(response1d, "1d")}`} (${responseSignal || "unknown"})`;
  const velocityText = velocity === null ? "" : `, velocity ${velocity.toFixed(1)}/day`;
  const detailTail =
    corroborationScore === null
      ? ""
      : ` with policy=${Math.round(supportingItems ?? 0)}, market=${Math.round(marketItems ?? 0)}, regulatory=${Math.round(regulatoryItems ?? 0)}`;

  return `You are looking at ${title}: ${activityText}${velocityText}; ${scoreText}; ${corroborationText}${detailTail}; ${responseText}. Use this with price and positioning to confirm whether policy flow is real enough to change procurement timing${procurementLabel ? ` (${procurementLabel})` : ""}, not as a standalone trigger.`;
}

export function buildVolatilityNarrative(
  input?: VolatilityNarrativePayload,
): string | null {
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

  return `You are looking at the volatility stack: ${vixState}; ${ovxState}; ${realizedState}. Use this with price action and positioning to size urgency and coverage pace, not as a standalone timing signal.`;
}

export function buildSentimentNarratives(input: {
  fearGreed?: FearGreedNarrativePayload;
  trumpEffect?: TrumpEffectNarrativePayload;
  volatility?: VolatilityNarrativePayload;
}): SentimentNarratives {
  return {
    fearGreedNarrative: buildFearGreedNarrative(input.fearGreed),
    trumpEffectNarrative: buildTrumpNarrative(input.trumpEffect),
    volatilityNarrative: buildVolatilityNarrative(input.volatility),
  };
}
