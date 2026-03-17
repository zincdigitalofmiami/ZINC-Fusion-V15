import { classifySentiment, type Sentiment } from "@/lib/sentiment-scorer";

export interface SentimentStats {
  total: number;
  bullish: number;
  bearish: number;
  neutral: number;
}

export interface ZlSentimentRelevanceInput {
  source: string | null | undefined;
  specialistTags: readonly string[] | null | undefined;
  headline: string | null | undefined;
  summary?: string | null;
}

export interface ZlSentimentResolution {
  sentiment: Sentiment;
  includeInCounts: boolean;
}

const PRIMARY_ZL_LANE_SLUGS = new Set([
  "soybean_oil",
  "soybean_agriculture",
  "biofuel",
]);

const PRIMARY_ZL_LANE_TAGS = new Set([
  "lane_soybean_oil",
  "lane_soybean_agriculture",
  "lane_biofuel",
]);

const PRIMARY_ZL_SPECIALIST_TAGS = new Set([
  "crush",
  "biofuel",
  "substitutes",
  "palm",
]);

const CONTEXT_ZL_LANE_SLUGS = new Set([
  "war_military",
  "legislation",
  "trump_actions",
  "ice_immigration",
]);

const CONTEXT_ZL_LANE_TAGS = new Set([
  "lane_war_military",
  "lane_legislation",
  "lane_trump_actions",
  "lane_ice_immigration",
]);

const CONTEXT_ZL_SPECIALIST_TAGS = new Set(["china", "tariff", "energy"]);

const ZL_TEXT_ANCHOR_RE =
  /\b(soybean oil|soy oil|soybean|soybeans|soy complex|soybean meal|soy meal|oilseed|edible oil|biofuel|biodiesel|renewable diesel|feedstock|rfs|rin|45z|lcfs|crush|palm oil|canola oil|sunflower oil)\b/i;

function parseExplicitSentiment(
  value: string | null | undefined,
): Sentiment | null {
  const explicit = value?.trim().toLowerCase();
  if (explicit === "bullish" || explicit === "bearish" || explicit === "neutral") {
    return explicit;
  }
  return null;
}

function laneSlugFromSource(source: string | null | undefined): string | null {
  if (!source || !source.startsWith("google_news/")) return null;
  const parts = source.split("/");
  if (parts.length < 3) return null;
  const lane = parts[1]?.trim();
  if (!lane) return null;
  return lane;
}

function normalizeTags(
  tags: readonly string[] | null | undefined,
): string[] {
  if (!tags?.length) return [];
  return tags
    .map((tag) => tag.trim().toLowerCase())
    .filter((tag) => tag.length > 0);
}

function hasAnyTag(tags: readonly string[], candidates: ReadonlySet<string>): boolean {
  return tags.some((tag) => candidates.has(tag));
}

function hasZlTextAnchor(
  headline: string | null | undefined,
  summary: string | null | undefined,
): boolean {
  const text = [headline, summary]
    .filter((part): part is string => typeof part === "string" && part.trim().length > 0)
    .join(" ");
  return ZL_TEXT_ANCHOR_RE.test(text);
}

export function isEligibleForZlSentimentFallback(
  input: ZlSentimentRelevanceInput,
): boolean {
  const laneSlug = laneSlugFromSource(input.source)?.toLowerCase() ?? null;
  const tags = normalizeTags(input.specialistTags);

  const hasPrimaryLane =
    (laneSlug != null && PRIMARY_ZL_LANE_SLUGS.has(laneSlug)) ||
    hasAnyTag(tags, PRIMARY_ZL_LANE_TAGS);
  if (hasPrimaryLane) return true;

  const hasPrimarySpecialistTag = hasAnyTag(tags, PRIMARY_ZL_SPECIALIST_TAGS);
  if (hasPrimarySpecialistTag) return true;

  const hasContextLane =
    (laneSlug != null && CONTEXT_ZL_LANE_SLUGS.has(laneSlug)) ||
    hasAnyTag(tags, CONTEXT_ZL_LANE_TAGS);
  const hasContextSpecialistTag = hasAnyTag(tags, CONTEXT_ZL_SPECIALIST_TAGS);

  if (hasContextLane || hasContextSpecialistTag) {
    return hasZlTextAnchor(input.headline, input.summary);
  }

  return hasZlTextAnchor(input.headline, input.summary);
}

export function resolveZlSentiment(
  zlSentiment: string | null | undefined,
  headline: string | null | undefined,
  summary?: string | null,
): Sentiment {
  const explicit = parseExplicitSentiment(zlSentiment);
  if (explicit) {
    return explicit;
  }

  return classifySentiment(headline ?? "", summary ?? "");
}

export function resolveZlSentimentForAggregation(
  zlSentiment: string | null | undefined,
  headline: string | null | undefined,
  summary: string | null | undefined,
  source: string | null | undefined,
  specialistTags: readonly string[] | null | undefined,
): ZlSentimentResolution {
  const explicit = parseExplicitSentiment(zlSentiment);
  if (explicit) {
    return {
      sentiment: explicit,
      includeInCounts: true,
    };
  }

  const eligible = isEligibleForZlSentimentFallback({
    source,
    specialistTags,
    headline,
    summary,
  });
  if (!eligible) {
    return {
      sentiment: "neutral",
      includeInCounts: false,
    };
  }

  return {
    sentiment: classifySentiment(headline ?? "", summary ?? ""),
    includeInCounts: true,
  };
}

export function summarizeSentiments(
  sentiments: readonly Sentiment[],
): SentimentStats {
  const bullish = sentiments.filter((sentiment) => sentiment === "bullish").length;
  const bearish = sentiments.filter((sentiment) => sentiment === "bearish").length;
  const neutral = sentiments.length - bullish - bearish;

  return {
    total: sentiments.length,
    bullish,
    bearish,
    neutral,
  };
}

export function computeNetSentimentScore(stats: SentimentStats): number | null {
  if (stats.total === 0) return null;
  return Math.round(((stats.bullish - stats.bearish) / stats.total) * 100);
}
