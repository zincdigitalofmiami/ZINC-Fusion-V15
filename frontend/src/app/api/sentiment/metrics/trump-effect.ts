import { scoreZlSentiment } from "@/lib/sentiment-scorer";

const DAY_MS = 24 * 60 * 60 * 1000;

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

export interface TrumpEffectPayload {
  weighted_action_score: number | null;
  action_velocity: number | null;
  action_acceleration: number | null;
  total_actions_7d: number | null;
  total_actions_30d: number | null;
  eo_count_7d: number | null;
  proclamation_count_7d: number | null;
  memorandum_count_7d: number | null;
  nomination_count_7d: number | null;
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
  if (key === "proclamation") return 1.5;
  if (key === "nomination_appointment" || key === "nomination") return 1.0;
  if (key === "presidential_document") return 2.0;
  return 0;
}

export function buildTrumpEffectPayload(
  featureRow: TrumpFeatureRow | null,
  actions: ExecutiveActionRow[],
): TrumpEffectPayload | null {
  if (!featureRow) return null;

  const anchorDate = parseDateOnly(featureRow.as_of_date);
  if (!anchorDate) {
    return {
      weighted_action_score: featureRow.weighted_action_score,
      action_velocity: featureRow.action_velocity,
      action_acceleration: featureRow.action_acceleration,
      total_actions_7d: featureRow.total_actions_7d,
      total_actions_30d: featureRow.total_actions_30d,
      eo_count_7d: featureRow.eo_count_7d,
      proclamation_count_7d: null,
      memorandum_count_7d: null,
      nomination_count_7d: null,
      avg_sentiment_7d: null,
      avg_sentiment_30d: null,
    };
  }

  const start7d = new Date(anchorDate.getTime() - 6 * DAY_MS);
  const start30d = new Date(anchorDate.getTime() - 29 * DAY_MS);

  let proclamationCount7d = 0;
  let memorandumCount7d = 0;
  let nominationCount7d = 0;
  let eoCount7d = 0;
  let totalActions7d = 0;
  let totalActions30d = 0;
  let weighted7d = 0;
  let previousWeekActions = 0;
  let sentimentSum7d = 0;
  let sentimentCount7d = 0;
  let sentimentSum30d = 0;
  let sentimentCount30d = 0;
  const previousWeekStart = new Date(anchorDate.getTime() - 13 * DAY_MS);
  const previousWeekEnd = new Date(anchorDate.getTime() - 7 * DAY_MS);

  for (const row of actions) {
    const eventDate = parseDateOnly(row.event_date);
    if (!eventDate || eventDate < start30d || eventDate > anchorDate) continue;
    totalActions30d += 1;

    const sentimentValue = sentimentToNumeric(row);
    sentimentSum30d += sentimentValue;
    sentimentCount30d += 1;
    const docType = normalizeActionType(row.document_type);

    if (eventDate >= start7d) {
      totalActions7d += 1;
      sentimentSum7d += sentimentValue;
      sentimentCount7d += 1;
      weighted7d += scoreWeightForDocType(docType);

      if (docType === "executive_order") eoCount7d += 1;
      if (docType === "proclamation") proclamationCount7d += 1;
      if (docType === "presidential_memorandum" || docType === "memorandum") {
        memorandumCount7d += 1;
      }
      if (docType === "nomination_appointment" || docType === "nomination") {
        nominationCount7d += 1;
      }
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
  const selectedAcceleration = featureRow.action_acceleration ?? derivedAcceleration;
  const selectedWeightedScore =
    featureRow.weighted_action_score ?? derivedWeightedScore;

  return {
    weighted_action_score: toRounded(selectedWeightedScore, 4),
    action_velocity: toRounded(selectedVelocity, 4),
    action_acceleration: toRounded(selectedAcceleration, 4),
    total_actions_7d: selectedTotalActions7d,
    total_actions_30d: selectedTotalActions30d,
    eo_count_7d: selectedEoCount,
    proclamation_count_7d: proclamationCount7d,
    memorandum_count_7d: memorandumCount7d,
    nomination_count_7d: nominationCount7d,
    avg_sentiment_7d: averageOrNull(sentimentSum7d, sentimentCount7d),
    avg_sentiment_30d: averageOrNull(sentimentSum30d, sentimentCount30d),
  };
}
