import { scoreZlSentiment } from "@/lib/sentiment-scorer";

const DAY_MS = 24 * 60 * 60 * 1000;
const SQRT_252 = Math.sqrt(252);

type ConfirmationBand = "low" | "mixed" | "strong";
type ResponseSignal = "muted" | "active" | "elevated";
type BuyerSignal =
  | "limited_confirmation"
  | "watchlist"
  | "rising_buyer_risk"
  | "confirmed_pressure";

export interface TrumpFeatureRow {
  as_of_date: string;
  latest_any_as_of: string;
  selection_mode: "latest_valid" | "latest_fallback";
  weighted_action_score: number | null;
  action_velocity: number | null;
  action_acceleration: number | null;
  total_actions_7d: number | null;
  total_actions_30d: number | null;
  eo_count_7d: number | null;
}

export interface ExecutiveActionRow {
  event_date: string;
  document_type: string | null;
  zl_sentiment: string | null;
  headline: string | null;
  content: string | null;
}

export interface ConfirmationInputs {
  independent_policy_items_7d: number | null;
  market_news_items_7d: number | null;
  regulatory_follow_through_7d: number | null;
}

export interface ZlResponseInputs {
  close_anchor: number | null;
  close_prev_1d: number | null;
  close_prev_5d: number | null;
  close_start_7d: number | null;
  realized_vol_21d: number | null;
  anchor_price_date: string | null;
}

interface TrumpZlResponse {
  anchor_price_date: string | null;
  anchor_window_start_date: string | null;
  zl_return_7d_pct: number | null;
  zl_response_1d_pct: number | null;
  zl_response_5d_pct: number | null;
  realized_vol_21d_pct: number | null;
  response_signal: ResponseSignal | null;
  abnormal_move_ratio: number | null;
}

interface TrumpPolicyActivity {
  executive_orders_7d: number | null;
  total_presidential_actions_7d: number | null;
  other_presidential_actions_7d: number | null;
  action_velocity: number | null;
  action_acceleration: number | null;
  weighted_action_score: number | null;
  avg_sentiment_7d: number | null;
  avg_sentiment_30d: number | null;
}

interface TrumpConfirmation {
  independent_policy_items_7d: number;
  market_news_items_7d: number;
  regulatory_follow_through_7d: number;
  confirmation_score: number;
  confirmation_band: ConfirmationBand;
}

interface TrumpBuyerMeaning {
  procurement_signal: BuyerSignal;
  label: string;
  rationale: string;
}

export interface TrumpEffectPayload {
  title: "Policy Impact on ZL";
  policy_window: {
    anchor_date: string;
    start_date_7d: string | null;
    selected_feature_mode: "latest_valid" | "latest_fallback";
  };
  zl_response: TrumpZlResponse;
  policy_activity: TrumpPolicyActivity;
  independent_confirmation: TrumpConfirmation;
  buyer_meaning: TrumpBuyerMeaning;

  // Legacy fields retained for compatibility with existing consumers.
  weighted_action_score: number | null;
  action_velocity: number | null;
  action_acceleration: number | null;
  total_actions_7d: number | null;
  total_actions_30d: number | null;
  eo_count_7d: number | null;
  other_actions_7d: number | null;
  avg_sentiment_7d: number | null;
  avg_sentiment_30d: number | null;
}

function parseDateOnly(value: string): Date | null {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Date(
    Date.UTC(
      parsed.getUTCFullYear(),
      parsed.getUTCMonth(),
      parsed.getUTCDate(),
      0,
      0,
      0,
      0,
    ),
  );
}

function formatDateOnly(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function sentimentToNumeric(row: ExecutiveActionRow): number {
  const explicit = row.zl_sentiment?.toLowerCase();
  if (explicit === "bullish") return 1;
  if (explicit === "bearish") return -1;
  if (explicit === "neutral") return 0;

  const inferred = scoreZlSentiment(row.headline, row.content).sentiment;
  if (inferred === "bullish") return 1;
  if (inferred === "bearish") return -1;
  return 0;
}

function averageOrNull(sum: number, count: number): number | null {
  return count > 0 ? sum / count : null;
}

function toRounded(value: number, digits: number): number {
  return Number(value.toFixed(digits));
}

function roundOrNull(value: number | null, digits: number): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  return toRounded(value, digits);
}

function percentChange(current: number | null, previous: number | null): number | null {
  if (current == null || previous == null || previous === 0) return null;
  return ((current - previous) / previous) * 100;
}

function normalizeActionType(documentType: string | null): string | null {
  const key = documentType?.toLowerCase().trim();
  if (!key) return null;
  if (key === "executive order") return "executive_order";
  if (key === "presidential memorandum") return "presidential_memorandum";
  if (key === "nomination appointment") return "nomination_appointment";
  if (key === "presidential document") return "presidential_document";
  return key;
}

function scoreWeightForDocType(documentType: string | null): number {
  const key = normalizeActionType(documentType);
  if (key === "executive_order") return 3.0;
  if (key === "presidential_memorandum" || key === "memorandum") return 2.5;
  if (key === "presidential_document") return 2.0;
  if (key === "proclamation") return 1.5;
  if (key === "nomination_appointment" || key === "nomination") return 1.0;
  return 0;
}

function computeConfirmation(inputs: ConfirmationInputs | null): TrumpConfirmation {
  const independentPolicy = Math.max(0, inputs?.independent_policy_items_7d ?? 0);
  const marketNews = Math.max(0, inputs?.market_news_items_7d ?? 0);
  const regulatoryFollowThrough = Math.max(
    0,
    inputs?.regulatory_follow_through_7d ?? 0,
  );

  const policyNorm = Math.min(independentPolicy, 8) / 8;
  const marketNorm = Math.min(marketNews, 8) / 8;
  const regulatoryNorm = Math.min(regulatoryFollowThrough, 4) / 4;

  const score = Math.round(
    (policyNorm * 0.45 + marketNorm * 0.35 + regulatoryNorm * 0.20) * 100,
  );

  const band: ConfirmationBand =
    score >= 70 ? "strong" : score >= 40 ? "mixed" : "low";

  return {
    independent_policy_items_7d: independentPolicy,
    market_news_items_7d: marketNews,
    regulatory_follow_through_7d: regulatoryFollowThrough,
    confirmation_score: score,
    confirmation_band: band,
  };
}

function computeResponseSignal(
  zlResponse1dPct: number | null,
  abnormalMoveRatio: number | null,
): ResponseSignal | null {
  if (abnormalMoveRatio != null) {
    if (abnormalMoveRatio >= 1.5) return "elevated";
    if (abnormalMoveRatio >= 0.9) return "active";
    return "muted";
  }

  if (zlResponse1dPct == null) return null;
  const absMove = Math.abs(zlResponse1dPct);
  if (absMove >= 1.2) return "elevated";
  if (absMove >= 0.6) return "active";
  return "muted";
}

function deriveBuyerMeaning(
  activity: TrumpPolicyActivity,
  confirmation: TrumpConfirmation,
  response: TrumpZlResponse,
): TrumpBuyerMeaning {
  const totalActions = activity.total_presidential_actions_7d ?? 0;
  const absReturn7d = Math.abs(response.zl_return_7d_pct ?? 0);
  const responseSignal = response.response_signal;

  if (
    confirmation.confirmation_band === "strong" &&
    (responseSignal === "elevated" || absReturn7d >= 1.0)
  ) {
    return {
      procurement_signal: "confirmed_pressure",
      label: "Confirmed pressure on ZL",
      rationale:
        "Independent coverage is strong and ZL is reacting. Treat near-term procurement risk as rising and consider advancing coverage.",
    };
  }

  if (
    confirmation.confirmation_band === "strong" &&
    totalActions >= 6 &&
    (responseSignal === "active" || absReturn7d >= 0.6)
  ) {
    return {
      procurement_signal: "rising_buyer_risk",
      label: "Rising buyer risk",
      rationale:
        "Policy flow is active and independently corroborated. Pressure is building even if the move is not yet extreme.",
    };
  }

  if (
    confirmation.confirmation_band === "low" &&
    (responseSignal === "muted" || responseSignal == null) &&
    absReturn7d < 0.8
  ) {
    return {
      procurement_signal: "limited_confirmation",
      label: "Limited confirmation / likely noise",
      rationale:
        "Headline activity is not being corroborated and ZL response is muted. Avoid chasing policy headlines without price confirmation.",
    };
  }

  if (totalActions <= 1 && confirmation.confirmation_band === "low") {
    return {
      procurement_signal: "limited_confirmation",
      label: "Low immediate policy pressure",
      rationale:
        "Federal action volume is light and confirmation is weak. Use broader supply-demand signals for timing decisions.",
    };
  }

  return {
    procurement_signal: "watchlist",
    label: "Watchlist: mixed confirmation",
    rationale:
      "Policy activity exists, but confirmation and ZL response are mixed. Keep layered coverage and reassess as new confirmation arrives.",
  };
}

export function buildTrumpEffectPayload(
  featureRow: TrumpFeatureRow | null,
  actions: ExecutiveActionRow[],
  confirmationInputs: ConfirmationInputs | null,
  zlResponseInputs: ZlResponseInputs | null,
): TrumpEffectPayload | null {
  if (!featureRow) return null;

  const anchorDate = parseDateOnly(featureRow.as_of_date);
  if (!anchorDate) {
    return null;
  }

  const start7d = new Date(anchorDate.getTime() - 6 * DAY_MS);
  const start30d = new Date(anchorDate.getTime() - 29 * DAY_MS);
  const previousWeekStart = new Date(anchorDate.getTime() - 13 * DAY_MS);
  const previousWeekEnd = new Date(anchorDate.getTime() - 7 * DAY_MS);

  let eoCount7d = 0;
  let totalActions7d = 0;
  let totalActions30d = 0;
  let weighted7d = 0;
  let previousWeekActions = 0;
  let sentimentSum7d = 0;
  let sentimentCount7d = 0;
  let sentimentSum30d = 0;
  let sentimentCount30d = 0;

  for (const row of actions) {
    const eventDate = parseDateOnly(row.event_date);
    if (!eventDate || eventDate < start30d || eventDate > anchorDate) continue;

    const sentimentValue = sentimentToNumeric(row);
    const docType = normalizeActionType(row.document_type);

    totalActions30d += 1;
    sentimentSum30d += sentimentValue;
    sentimentCount30d += 1;

    if (eventDate >= start7d) {
      totalActions7d += 1;
      sentimentSum7d += sentimentValue;
      sentimentCount7d += 1;
      weighted7d += scoreWeightForDocType(docType);
      if (docType === "executive_order") eoCount7d += 1;
    }

    if (eventDate >= previousWeekStart && eventDate <= previousWeekEnd) {
      previousWeekActions += 1;
    }
  }

  const derivedVelocity = totalActions7d / 7;
  const derivedPreviousVelocity = previousWeekActions / 7;
  const derivedAcceleration = derivedVelocity - derivedPreviousVelocity;
  const derivedWeightedScore = weighted7d / 10.0;

  const selectedEoCount = featureRow.eo_count_7d ?? eoCount7d;
  const selectedTotalActions7d = featureRow.total_actions_7d ?? totalActions7d;
  const selectedTotalActions30d = featureRow.total_actions_30d ?? totalActions30d;
  const selectedVelocity = featureRow.action_velocity ?? derivedVelocity;
  const selectedAcceleration =
    featureRow.action_acceleration ?? derivedAcceleration;
  const selectedWeightedScore =
    featureRow.weighted_action_score ?? derivedWeightedScore;
  const selectedOtherActions7d =
    selectedTotalActions7d != null && selectedEoCount != null
      ? Math.max(0, selectedTotalActions7d - selectedEoCount)
      : null;

  const responseReturn7d = percentChange(
    zlResponseInputs?.close_anchor ?? null,
    zlResponseInputs?.close_start_7d ?? null,
  );
  const responseReturn1d = percentChange(
    zlResponseInputs?.close_anchor ?? null,
    zlResponseInputs?.close_prev_1d ?? null,
  );
  const responseReturn5d = percentChange(
    zlResponseInputs?.close_anchor ?? null,
    zlResponseInputs?.close_prev_5d ?? null,
  );

  const realizedVol = zlResponseInputs?.realized_vol_21d ?? null;
  const dailyVolPct = realizedVol != null ? realizedVol / SQRT_252 : null;
  const abnormalMoveRatio =
    responseReturn1d != null && dailyVolPct != null && dailyVolPct > 0
      ? Math.abs(responseReturn1d) / dailyVolPct
      : null;

  const responseSignal = computeResponseSignal(responseReturn1d, abnormalMoveRatio);

  const zlResponse: TrumpZlResponse = {
    anchor_price_date: zlResponseInputs?.anchor_price_date ?? null,
    anchor_window_start_date: formatDateOnly(start7d),
    zl_return_7d_pct: roundOrNull(responseReturn7d, 2),
    zl_response_1d_pct: roundOrNull(responseReturn1d, 2),
    zl_response_5d_pct: roundOrNull(responseReturn5d, 2),
    realized_vol_21d_pct: roundOrNull(realizedVol, 2),
    response_signal: responseSignal,
    abnormal_move_ratio: roundOrNull(abnormalMoveRatio, 2),
  };

  const policyActivity: TrumpPolicyActivity = {
    executive_orders_7d: selectedEoCount,
    total_presidential_actions_7d: selectedTotalActions7d,
    other_presidential_actions_7d: selectedOtherActions7d,
    action_velocity: roundOrNull(selectedVelocity, 4),
    action_acceleration: roundOrNull(selectedAcceleration, 4),
    weighted_action_score: roundOrNull(selectedWeightedScore, 4),
    avg_sentiment_7d: averageOrNull(sentimentSum7d, sentimentCount7d),
    avg_sentiment_30d: averageOrNull(sentimentSum30d, sentimentCount30d),
  };

  const independentConfirmation = computeConfirmation(confirmationInputs);
  const buyerMeaning = deriveBuyerMeaning(
    policyActivity,
    independentConfirmation,
    zlResponse,
  );

  return {
    title: "Policy Impact on ZL",
    policy_window: {
      anchor_date: featureRow.as_of_date,
      start_date_7d: formatDateOnly(start7d),
      selected_feature_mode: featureRow.selection_mode,
    },
    zl_response: zlResponse,
    policy_activity: policyActivity,
    independent_confirmation: independentConfirmation,
    buyer_meaning: buyerMeaning,

    weighted_action_score: policyActivity.weighted_action_score,
    action_velocity: policyActivity.action_velocity,
    action_acceleration: policyActivity.action_acceleration,
    total_actions_7d: policyActivity.total_presidential_actions_7d,
    total_actions_30d: selectedTotalActions30d,
    eo_count_7d: policyActivity.executive_orders_7d,
    other_actions_7d: policyActivity.other_presidential_actions_7d,
    avg_sentiment_7d: policyActivity.avg_sentiment_7d,
    avg_sentiment_30d: policyActivity.avg_sentiment_30d,
  };
}
