/**
 * Keyword-based ZL (soybean oil) sentiment scorer.
 *
 * Used when the `zl_sentiment` column is NULL (which is ~99% of rows).
 * Scans headline + summary text for domain-relevant keywords and returns
 * a sentiment classification with confidence.
 *
 * Context: ZL is the CME soybean oil futures contract. This system supports
 * bulk procurement decisions — "bullish" means prices likely rising (lock now),
 * "bearish" means prices likely falling (delay procurement).
 *
 * Architecture:
 *   1. Negation window — 4-word lookahead negation detection ("no recession"
 *      flips the match to opposite polarity at reduced weight).
 *   2. Weighted regex patterns with \b word boundaries — grouped by domain.
 *   3. Multi-match accumulation — score = sum(matched weights), net = bull - bear.
 *   4. Confidence = min(1, |net| / maxExpected) tuned to typical headline length.
 *
 * Sources:
 *   - Loughran-McDonald financial sentiment dictionary categories
 *   - ZL/soybean oil domain terminology from USDA, NOPA, EPA, MPOB
 *   - FinVADER/VADER financial extensions for market-direction terms
 */

// ── Negation ──

const NEGATION_RE =
  /\b(no|not|n't|never|neither|nor|hardly|barely|unlikely|fails?\sto|failed?\sto|won't|wouldn't|cannot|can't|don't|doesn't|didn't|isn't|aren't|wasn't|weren't)\b/gi;

/**
 * Build a set of character offsets covered by a negation window.
 * Any match whose start falls inside a negation window has its polarity
 * flipped (bull→bear, bear→bull) at 60% of original weight.
 *
 * Uses both lookahead AND lookbehind windows to handle:
 *   - "no recession" (lookahead: negator before term)
 *   - "rate cut unlikely" (lookbehind: negator after term)
 */
function buildNegationSpans(text: string): Set<number> {
  const spans = new Set<number>();
  let m: RegExpExecArray | null;
  const re = new RegExp(NEGATION_RE.source, "gi");
  while ((m = re.exec(text)) !== null) {
    // Lookbehind: 40 chars before the negator
    const behindStart = Math.max(0, m.index - 40);
    for (let i = behindStart; i < m.index; i++) spans.add(i);
    // Lookahead: 40 chars after the negator
    const aheadStart = m.index + m[0].length;
    const aheadEnd = Math.min(aheadStart + 40, text.length);
    for (let i = aheadStart; i < aheadEnd; i++) spans.add(i);
  }
  return spans;
}

// ── Keyword banks ──
// Each entry: [regex, weight].  Higher weight = stronger signal.
// Weights are calibrated so a single strong signal (~2.0) can classify,
// while weak signals (~0.5) need several co-occurrences.

const BULLISH_PATTERNS: [RegExp, number][] = [
  // ── Direct market direction ──
  [/\b(bullish|rally|rallied|rallies)\b/i, 2.0],
  [/\b(surge[ds]?|soar[sed]?|jump[sed]?|spike[ds]?|skyrocket)\b/i, 2.0],
  [/\b(breakout|new high|all[- ]time high|multi[- ]year high|52[- ]week high)\b/i, 2.0],
  [/\b(rise[sd]?|rising|gain[sed]?|higher|upside)\b/i, 1.0],
  [/\b(strong|strengthen[sed]?|robust|outperform[sed]?)\b/i, 1.0],
  [/\b(boost[sed]?|expand[sed]?|growth|lift[sed]?|advance[sd]?)\b/i, 1.0],
  [/\b(support[sed]?|underpin[ned]?|buoy[sed]?|prop[ped]* up)\b/i, 0.8],
  [/\b(recover[yed]?|rebound[sed]?|bounce[sd]?|comeback)\b/i, 1.5],
  [/\b(upgrade[sd]?|beat[s]? estimate|above consensus)\b/i, 1.5],
  [/\b(gap[ped]* up|limit up|lock limit)\b/i, 2.5],
  [/\b(buy signal|golden cross|accumulation)\b/i, 1.5],
  [/\b(short squeeze|short covering|forced buying)\b/i, 2.0],

  // ── Supply tightness (bullish for price) ──
  [/\b(tight supply|shortage|shortfall|deficit)\b/i, 2.0],
  [/\b(drought|crop damage|crop failure|weather concern|frost)\b/i, 2.0],
  [/\b(flood[sed]?|excessive rain|planting delay[sed]?)\b/i, 1.5],
  [/\b(supply disruption|export ban|supply crunch|low stocks)\b/i, 2.0],
  [/\b(pipeline constraint|logistic[s]? bottleneck)\b/i, 1.5],
  [/\b(below expectations|disappointing crop|yield concern)\b/i, 1.5],
  [/\b(crop condition[s]? deteriorat|poor crop rating)\b/i, 1.5],
  [/\b(stocks[- ]to[- ]use ratio.{0,10}low|tight ending stocks)\b/i, 2.0],

  // ── Biofuel demand (bullish for soybean oil) ──
  [/\b(biofuel mandate|biodiesel|renewable diesel|blending)\b/i, 1.5],
  [/\b(sustainable aviation fuel|saf\b|rin price[s]?|lcfs)\b/i, 1.5],
  [/\b(renewable fuel standard|rfs\b|rvo increase|higher rvo)\b/i, 1.5],
  [/\b(45z tax credit|clean fuel|low carbon fuel)\b/i, 1.5],
  [/\b(b35|b40|blend wall|mandate increase)\b/i, 1.5],

  // ── Demand growth ──
  [/\b(demand growth|import increase|consumption up|buying interest)\b/i, 1.0],
  [/\b(crush margin|crush spread|record crush|nopa crush)\b/i, 1.0],
  [/\b(record export|strong export|export pace|export commitment)\b/i, 1.5],
  [/\b(food inflation|cooking oil demand|edible oil demand)\b/i, 1.0],
  [/\b(china buying|china import|chinese demand|india import)\b/i, 1.5],
  [/\b(restocking|stockpil[eing]+|reserve build)\b/i, 1.0],

  // ── Geopolitical / supply-chain risk ──
  [/\b(port strike|labor strike|trucker strike|blockade)\b/i, 1.5],
  [/\b(red sea|suez|panama canal draft|shipping disruption)\b/i, 1.5],
  [/\b(sanctions? on russia|export restriction)\b/i, 1.0],

  // ── Macro tailwinds for commodities ──
  [/\b(rate cut|easing cycle|dovish|stimulus)\b/i, 1.0],
  [/\b(dollar weak|usd weak|dxy decline|greenback fall)\b/i, 1.0],
  [/\b(inflation hedge|commodity supercycle)\b/i, 0.8],
];

const BEARISH_PATTERNS: [RegExp, number][] = [
  // ── Direct market direction ──
  [/\b(bearish|decline[sd]?|declining|slump[sed]?|plunge[sd]?)\b/i, 2.0],
  [/\b(crash[ed]?|collapse[sd]?|tumble[sd]?|plummet[sed]?)\b/i, 2.5],
  [/\b(drop[ps]?|dropped|fall[s]?|fell|falling)\b/i, 1.0],
  [/\b(lower[sed]?|weak[ened]*|soften[sed]?|ease[sd]?|erode[sd]?)\b/i, 1.0],
  [/\b(sell[- ]?off|selling pressure|downside|retreat[sed]?)\b/i, 1.5],
  [/\b(correction|pullback|reversal|breakdown|bear market)\b/i, 1.5],
  [/\b(downgrade[sd]?|miss[ed]? estimate|below consensus)\b/i, 1.5],
  [/\b(gap[ped]* down|limit down|circuit breaker|trading halt)\b/i, 2.5],
  [/\b(margin call|liquidat[eing]+|forced selling)\b/i, 2.0],
  [/\b(death cross|distribution|capitulat[eing]+)\b/i, 1.5],
  [/\b(new low|multi[- ]year low|52[- ]week low|record low)\b/i, 2.0],

  // ── Supply abundance (bearish for price) ──
  [/\b(surplus|oversupply|glut|bumper crop|record production)\b/i, 2.0],
  [/\b(abundant|ample supply|large stocks|record stocks)\b/i, 1.5],
  [/\b(good weather|favorable condition|ideal growing)\b/i, 1.0],
  [/\b(above expectations|better.than.expected yield|record yield)\b/i, 1.5],
  [/\b(inventory build|stock build|carry.?over.{0,8}high)\b/i, 1.5],
  [/\b(crop condition[s]? improv|good.to.excellent rating)\b/i, 1.0],
  [/\b(harvest pressure|harvest progress ahead|early harvest)\b/i, 1.0],

  // ── Policy risk (bearish for demand) ──
  [/\b(epa waiver|sre|small refinery exemption)\b/i, 1.5],
  [/\b(rollback|cut mandate|reduce mandate|lower rvo)\b/i, 2.0],
  [/\b(deregulat|subsidy cut|incentive removal|credit expir)\b/i, 1.0],

  // ── Trade disruption / demand destruction ──
  [/\b(trade war|retaliatory tariff|counter.?tariff)\b/i, 1.5],
  [/\b(recession|slowdown|contraction|demand destruction)\b/i, 1.5],
  [/\b(default|bankruptcy|insolvency|credit crisis)\b/i, 1.5],
  [/\b(embargo on.{0,15}soy|import ban)\b/i, 2.0],

  // ── Substitution risk (bearish for ZL specifically) ──
  [/\b(palm oil cheaper|canola substitut|switch.{0,10}palm)\b/i, 1.0],
  [/\b(sunflower oil.{0,10}displac|rapeseed.{0,10}replac)\b/i, 1.0],
  [/\b(palm oil export.{0,10}surge|cpo.{0,10}flood)\b/i, 1.0],

  // ── Macro headwinds for commodities ──
  [/\b(rate hike|tightening|hawkish|restrictive)\b/i, 1.0],
  [/\b(dollar strong|usd strong|dxy rise|dxy rally|greenback)\b/i, 1.0],
  [/\b(risk[- ]off|flight to safety|deflationary)\b/i, 0.8],
  [/\b(demand concern|consumption.{0,8}drop|usage.{0,8}decline)\b/i, 1.0],
];

// ── Types ──

export type Sentiment = "bullish" | "bearish" | "neutral";

export interface SentimentScore {
  sentiment: Sentiment;
  confidence: number; // 0–1
  bullScore: number;
  bearScore: number;
}

// ── Scoring engine ──

/** Weight multiplier when a match is negated (flipped to opposite polarity). */
const NEGATION_DAMPING = 0.6;

/**
 * Score a headline (and optional summary/content) for ZL sentiment.
 *
 * Algorithm:
 *   1. Concatenate headline + summary, lowercase.
 *   2. Detect negation spans (4-word window after each negator).
 *   3. For each pattern bank (bull/bear), accumulate weighted score.
 *      - If match falls inside a negation span, flip polarity at 60% weight.
 *   4. Net score  = bullScore − bearScore.
 *   5. Confidence = min(1, |net| / 5)  — calibrated so 5+ points = full certainty.
 *   6. Classification threshold: |net| > 0.5 to avoid noise.
 */
export function scoreZlSentiment(
  headline: string | null,
  summary?: string | null,
): SentimentScore {
  const text = [headline, summary].filter(Boolean).join(" ").toLowerCase();

  if (!text || text.length < 5) {
    return { sentiment: "neutral", confidence: 0, bullScore: 0, bearScore: 0 };
  }

  const negSpans = buildNegationSpans(text);

  let bullScore = 0;
  let bearScore = 0;

  // Helper: scan a pattern bank, respecting negation.
  const scan = (
    patterns: [RegExp, number][],
    onHit: "bull" | "bear",
  ): void => {
    for (const [pattern, weight] of patterns) {
      // Use a fresh regex each time (global flag for multiple matches)
      const re = new RegExp(pattern.source, "gi");
      let m: RegExpExecArray | null;
      while ((m = re.exec(text)) !== null) {
        const negated = negSpans.has(m.index);
        if (negated) {
          // Flip polarity at reduced weight
          if (onHit === "bull") bearScore += weight * NEGATION_DAMPING;
          else bullScore += weight * NEGATION_DAMPING;
        } else {
          if (onHit === "bull") bullScore += weight;
          else bearScore += weight;
        }
        break; // count each pattern once per text (avoid double-counting)
      }
    }
  };

  scan(BULLISH_PATTERNS, "bull");
  scan(BEARISH_PATTERNS, "bear");

  // Require minimum evidence to classify (avoids noise on thin headlines)
  const total = bullScore + bearScore;
  if (total < 0.8) {
    return { sentiment: "neutral", confidence: 0, bullScore, bearScore };
  }

  const netScore = bullScore - bearScore;
  // Confidence: |net| / 5, capped at 1.  5+ net points = full confidence.
  const confidence = Math.min(1, Math.abs(netScore) / 5);

  let sentiment: Sentiment = "neutral";
  if (netScore > 0.5) sentiment = "bullish";
  else if (netScore < -0.5) sentiment = "bearish";

  return { sentiment, confidence, bullScore, bearScore };
}

/**
 * Classify sentiment for a news article using keyword scoring.
 */
export function classifySentiment(
  headline: string | null,
  summary?: string | null,
): Sentiment {
  return scoreZlSentiment(headline, summary).sentiment;
}
