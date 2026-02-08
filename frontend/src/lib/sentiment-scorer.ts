/**
 * Keyword-based ZL (soybean oil) sentiment scorer.
 *
 * Used when the `zl_sentiment` column is NULL (which is ~99% of rows).
 * Scans headline + summary text for domain-relevant keywords and returns
 * a sentiment classification.
 *
 * Context: ZL is the CME soybean oil futures contract. This system supports
 * bulk procurement decisions — "bullish" means prices likely rising (lock now),
 * "bearish" means prices likely falling (delay procurement).
 */

// ── Keyword banks ──

const BULLISH_PATTERNS: [RegExp, number][] = [
  // Direct market direction
  [/\b(bullish|rally|rallied|rallies|surge[ds]?|soar[sed]?|jump[sed]?)\b/i, 2],
  [/\b(rise[sd]?|rising|gain[sed]?|higher|upside|strong|strengthen)\b/i, 1],
  [/\b(boost[sed]?|expand[sed]?|growth|support[sed]?|lift[sed]?)\b/i, 1],
  // Supply tightness (bullish for price)
  [/\b(tight supply|shortage|drought|crop damage|weather concern)\b/i, 2],
  [/\b(supply disruption|export ban|supply crunch|low stocks)\b/i, 2],
  [/\b(below expectations|disappointing crop|yield concern)\b/i, 1.5],
  // Biofuel demand (bullish for soy oil)
  [/\b(biofuel mandate|biodiesel|renewable diesel|blending)\b/i, 1.5],
  [/\b(sustainable aviation fuel|saf|rin price|lcfs)\b/i, 1.5],
  [/\b(renewable fuel standard|rfs|rvo increase)\b/i, 1.5],
  // Demand growth
  [/\b(demand growth|import increase|consumption|buying)\b/i, 1],
  [/\b(crush margin|crush spread|record crush)\b/i, 1],
  [/\b(record export|strong export|export pace)\b/i, 1.5],
];

const BEARISH_PATTERNS: [RegExp, number][] = [
  // Direct market direction
  [/\b(bearish|decline[sd]?|declining|slump[sed]?|plunge[sd]?)\b/i, 2],
  [/\b(drop[ps]?|dropped|fall[sed]?|falling|lower[sed]?|weak[ened]*)\b/i, 1],
  [/\b(sell[- ]?off|pressure[sd]?|downside|retreat[sed]?)\b/i, 1.5],
  // Supply abundance (bearish for price)
  [/\b(surplus|oversupply|bumper crop|record production|abundant)\b/i, 2],
  [/\b(good weather|favorable condition|above expectations)\b/i, 1],
  [/\b(ample supply|large stocks|inventory build|stock build)\b/i, 1.5],
  // Policy risk (bearish for demand)
  [/\b(waiver|epa waiver|exemption|rollback)\b/i, 1.5],
  [/\b(cut mandate|reduce mandate|lower rvo)\b/i, 2],
  // Trade disruption (bearish)
  [/\b(trade war|retaliatory tariff|sanction[sed]?)\b/i, 1.5],
  [/\b(recession|slowdown|contraction|demand destruction)\b/i, 1.5],
  // Substitution risk (bearish for ZL specifically)
  [/\b(palm oil cheaper|canola substitute|switch.*palm)\b/i, 1],
  [/\b(uncertainty|unpredictable|volatile|risk|concern)\b/i, 0.5],
];

export type Sentiment = "bullish" | "bearish" | "neutral";

export interface SentimentScore {
  sentiment: Sentiment;
  confidence: number; // 0–1
  bullScore: number;
  bearScore: number;
}

/**
 * Score a headline (and optional summary/content) for ZL sentiment.
 * Returns sentiment classification + confidence.
 */
export function scoreZlSentiment(
  headline: string | null,
  summary?: string | null,
): SentimentScore {
  const text = [headline, summary].filter(Boolean).join(" ").toLowerCase();

  if (!text || text.length < 5) {
    return { sentiment: "neutral", confidence: 0, bullScore: 0, bearScore: 0 };
  }

  let bullScore = 0;
  let bearScore = 0;

  for (const [pattern, weight] of BULLISH_PATTERNS) {
    const matches = text.match(pattern);
    if (matches) bullScore += weight;
  }

  for (const [pattern, weight] of BEARISH_PATTERNS) {
    const matches = text.match(pattern);
    if (matches) bearScore += weight;
  }

  // Require a minimum score to classify (avoid noise)
  const total = bullScore + bearScore;
  if (total < 0.8) {
    return { sentiment: "neutral", confidence: 0, bullScore, bearScore };
  }

  const netScore = bullScore - bearScore;
  const confidence = Math.min(1, Math.abs(netScore) / 4);

  let sentiment: Sentiment = "neutral";
  if (netScore > 0.3) sentiment = "bullish";
  else if (netScore < -0.3) sentiment = "bearish";

  return { sentiment, confidence, bullScore, bearScore };
}

/**
 * Given a pre-existing zl_sentiment string (from DB), parse it.
 * Falls back to keyword scoring if the DB value is null/empty.
 */
export function classifySentiment(
  zlSentiment: string | null,
  headline: string | null,
  summary?: string | null,
): Sentiment {
  // If the DB has an explicit sentiment, use it
  if (zlSentiment) {
    const s = zlSentiment.toLowerCase();
    if (s.includes("bull") || s.includes("positive")) return "bullish";
    if (s.includes("bear") || s.includes("negative")) return "bearish";
    return "neutral";
  }

  // Otherwise, derive from keywords
  return scoreZlSentiment(headline, summary).sentiment;
}
