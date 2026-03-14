import { classifySentiment, type Sentiment } from "@/lib/sentiment-scorer";

export interface SentimentStats {
  total: number;
  bullish: number;
  bearish: number;
  neutral: number;
}

export function resolveZlSentiment(
  zlSentiment: string | null | undefined,
  headline: string | null | undefined,
  summary?: string | null,
): Sentiment {
  const explicit = zlSentiment?.trim().toLowerCase();
  if (explicit === "bullish" || explicit === "bearish" || explicit === "neutral") {
    return explicit;
  }

  return classifySentiment(headline ?? "", summary ?? "");
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
