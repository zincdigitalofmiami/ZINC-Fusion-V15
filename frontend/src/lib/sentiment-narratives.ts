export type FearGreedComponentKey =
  | "vix"
  | "oil"
  | "uncertainty"
  | "inflation"
  | "iranWar"
  | "news"
  | "positioning"
  | "sentiment"
  | "zlTrend"
  | "dailyShock"
  | "china"
  | "neural";

export type FearGreedNarrativeComponentPayload = {
  score?: number | null;
  weight?: number | null;
  raw?: number | null;
};

export type FearGreedNarrativePayload = {
  score?: number | null;
  zone?: string | null;
  label?: string | null;
  interpretation?: string | null;
  components?: Partial<
    Record<FearGreedComponentKey, FearGreedNarrativeComponentPayload>
  >;
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

function joinList(values: string[]): string {
  if (values.length === 0) return "macro pressure";
  if (values.length === 1) return values[0];
  if (values.length === 2) return `${values[0]} and ${values[1]}`;
  return `${values[0]}, ${values[1]}, and ${values[2]}`;
}

function normalizeZoneLabel(value: string | null | undefined): string {
  if (!value) return "Current";
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatMove(value: number, windowLabel: string): string {
  const magnitude = `${Math.abs(value).toFixed(2)}%`;
  if (value > 0) return `rose ${magnitude} in ${windowLabel}`;
  if (value < 0) return `fell ${magnitude} in ${windowLabel}`;
  return `was unchanged (${magnitude}) in ${windowLabel}`;
}

const FEAR_GREED_LABELS: Record<FearGreedComponentKey, string> = {
  vix: "VIX stress",
  oil: "oil shock",
  uncertainty: "macro uncertainty",
  inflation: "inflation expectations",
  iranWar: "Iran-war flow",
  news: "macro news velocity",
  positioning: "fund positioning",
  sentiment: "headline sentiment",
  zlTrend: "ZL price trend",
  dailyShock: "daily move shock",
  china: "China trade friction",
  neural: "neural geopolitical signal",
};

export function buildFearGreedNarrative(
  input?: FearGreedNarrativePayload,
): string | null {
  if (!input) return null;
  const score = toNum(input.score);
  if (score === null) return null;

  const componentRows = Object.entries(input.components ?? {})
    .map(([key, value]) => {
      const componentScore = toNum(value?.score);
      if (componentScore === null) return null;
      const componentWeight = toNum(value?.weight) ?? 0.08;
      return {
        key: key as FearGreedComponentKey,
        score: componentScore,
        contribution: (componentScore - 50) * componentWeight,
      };
    })
    .filter((row): row is {
      key: FearGreedComponentKey;
      score: number;
      contribution: number;
    } => row !== null);

  const topDrags = componentRows
    .filter((row) => row.contribution < 0)
    .sort((a, b) => a.contribution - b.contribution)
    .slice(0, 3)
    .map((row) => `${FEAR_GREED_LABELS[row.key]} (${Math.round(row.score)})`);
  const topSupports = componentRows
    .filter((row) => row.contribution > 0)
    .sort((a, b) => b.contribution - a.contribution)
    .slice(0, 2)
    .map((row) => `${FEAR_GREED_LABELS[row.key]} (${Math.round(row.score)})`);

  const dragPhrase = joinList(topDrags);
  const supportPhrase = joinList(topSupports);
  const zoneLabel = input.label || normalizeZoneLabel(input.zone);
  const severeMacro =
    componentRows.some((row) =>
      (row.key === "uncertainty" ||
        row.key === "inflation" ||
        row.key === "iranWar" ||
        row.key === "vix" ||
        row.key === "zlTrend") &&
      row.score <= 30
    );

  const regimeSentence =
    score <= 35
      ? "This is a risk-off regime with concentrated upside price pressure risk for buyers."
      : score <= 58 && severeMacro
        ? "The headline score sits near neutral, but the tape is not balanced because core macro drivers are still stressed."
        : score <= 58
          ? "The regime is mixed and transitionary, so directional conviction should come from confirming market structure."
          : score <= 75
            ? "Risk appetite is elevated, but this still requires confirmation from liquidity and positioning behavior."
            : "Risk appetite appears stretched, so extension risk is high without fresh confirmation.";

  return `Fear & Greed is ${Math.round(score)} (${zoneLabel}). The dominant downside pressures are ${dragPhrase}${topSupports.length > 0 ? `, while ${supportPhrase} are the primary offsets` : ""}. ${regimeSentence} ${input.interpretation ?? "Use this composite as a regime filter paired with price, not as a standalone trigger."}`;
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

  return `You are looking at ${title}. Policy flow currently shows ${activityText}${velocityText}, with ${scoreText} and ${corroborationText}${detailTail}. Market response is ${responseText}, which tells you whether policy pressure is actually transmitting into ZL behavior. Procurement posture is ${procurementLabel ?? "not classified"}${procurementLabel ? ` (${procurementLabel})` : ""}, so treat this as a direct execution-risk signal rather than generic political noise.`;
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

  return `You are looking at the volatility stack: ${vixState}, ${ovxState}, and ${realizedState}. This configuration defines execution risk directly because VIX and OVX determine macro shock sensitivity while realized volatility reflects how much ZL is already moving day to day. When this stack stays elevated, procurement timing errors become more expensive and coverage pacing should tighten. Use this read as a tactical risk budget input paired with price action and liquidity conditions, not as a standalone trigger.`;
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
