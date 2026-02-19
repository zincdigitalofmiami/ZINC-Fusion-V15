#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    ZINC-FUSION AI COMPUTE LAYER                              ║
║                         Agent Pool Framework                                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  PURPOSE: Real-time AI intelligence ON TOP of trained L0-L3 model outputs    ║
║                                                                              ║
║  PHILOSOPHY:                                                                 ║
║    - Heavy forecasts → Trained models (TimeSeriesPredictor, TabularPredictor)║
║    - Soft intelligence → AI Compute Agents (Claude, on-demand)               ║
║                                                                              ║
║  AGENTS IN POOL:                                                             ║
║    1. SentimentScorer - News analysis with ZL market expertise               ║
║    2. CorrelationAnalyst - Compute & explain correlations (coming)           ║
║    3. FactorAttributor - "What's driving this signal?" (coming)              ║
║    4. OverlayNarrator - Chart overlay descriptions like Grok (coming)        ║
║    5. ScenarioModeler - What-if analysis (coming)                            ║
║                                                                              ║
║  MARKET INTELLIGENCE EMBEDDED:                                               ║
║    - Correlations: USD/BRL(-0.65), USD/ARS(-0.72), VIX(-0.45), Palm(+0.68)  ║
║    - SHAP weights: Biofuel(+0.12), SouthAm supply(-0.09), FX(-0.07)         ║
║    - Current context: ZL~50¢, Fed 3.75%, VIX~15, RVO+50% proposed           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path

from dotenv import load_dotenv

import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("/tmp/zinc_ai_compute.log")],
)
logger = logging.getLogger("ZINC-AI-Compute")

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


# =============================================================================
# MARKET INTELLIGENCE - The Brain
# =============================================================================

MARKET_INTELLIGENCE = """
## SOYBEAN OIL (ZL) MARKET INTELLIGENCE - January 2026

### CURRENT MARKET SNAPSHOT
- ZL1 Futures: ~50 cents/lb (MAR 2026 contract)
- Crush Margins: $1.46/bu, PV 44.6%, record US crush (2.55B bu forecast)
- Fed Funds: 3.75% (projected 3.25% by end 2026)
- VIX: ~15 (low volatility, supportive for commodities)
- USD/BRL: 5.4 (strong BRL helps US competitiveness)

### CORRELATION MATRIX (Historical r-values, 2021-2026)
| Factor | Correlation | Interpretation |
|--------|-------------|----------------|
| USD/BRL | -0.65 | Weaker BRL → Brazil exports more → Bearish US ZL |
| USD/ARS | -0.72 | Weaker ARS → Argentina exports more → Bearish US ZL |
| USD/CNY | -0.58 | Stronger CNY → China imports more → Bullish demand |
| VIX | -0.45 | High volatility → Risk-off → Bearish commodities |
| Fed Rates | -0.38 | Higher rates → Stronger USD → Bearish exports |
| Palm Oil | +0.68 | Positive substitution correlation (leader) |
| Canola | +0.62 | Positive substitution correlation |
| Corn | +0.50 | Positive correlation via ethanol/biodiesel |
| Brazil/Argentina Production | -0.70 | Competition effect on US prices |

### SHAP FEATURE IMPORTANCE (What Drives ZL Prices)
| Factor | Weight | Direction |
|--------|--------|-----------|
| Biofuel Legislation | +0.12 | TOP POSITIVE - RFS, LCFS, 45Z credits |
| South American Supply | -0.09 | TOP NEGATIVE - Competition from Brazil/Argentina |
| FX Movements | -0.07 | USD strength hurts exports |
| VIX/Volatility | -0.05 | Risk sentiment |

### KEY POLICY DRIVERS
- EPA RVO 2026: 5.61B gal proposed (+50% from 2024) - MAJOR BULLISH
- 45Z Credit: 32¢/gal for soy-based biodiesel - BULLISH
- Trump Tariffs: Risk of China retaliation (-10-15% price risk)
- Brazil Harvest: Record 177.1M tons projected - BEARISH pressure

### SUPPLY/DEMAND DYNAMICS
**BULLISH Signals:**
- South American drought/weather problems (supply shock)
- China buying commitments (8-12M tons)
- EPA mandate increases
- Renewable diesel capacity expansion
- Crush margin expansion
- Low VIX environment
- Fed rate cuts

**BEARISH Signals:**
- Record Brazil/Argentina harvests (competition)
- Cheap crude oil (kills biodiesel economics)
- Strong USD (hurts export competitiveness)
- China tariff retaliation
- High VIX spikes
- Weak crush margins

### INVERSION RULES (FinBERT Gets These Wrong!)
When FinBERT sees "fell/drop/decline" it says BEARISH. But:
- "Argentina production FELL 35%" = Supply shock = BULLISH for ZL
- "Crop conditions FELL to 55%" = Drought stress = BULLISH for ZL
- "Crude prices FELL to $12" = Cheap energy = BEARISH for biodiesel ✓
- "China imports FELL" = Demand destruction = BEARISH ✓
- "Corn stocks FELL to 80 days" = Tight supply = BULLISH for grains

### SPECIALIST ROUTING
| Specialist | Triggers On |
|------------|-------------|
| crush | US processing, crush margins, meal/oil demand, basis levels |
| china | Chinese imports, policy, stockpiling, trade relations |
| fx | USD/BRL/ARS/CNY movements, currency volatility |
| fed | Interest rates, FOMC, monetary policy, inflation |
| tariff | Trade policy, duties, retaliation, Section 301 |
| energy | Crude, diesel, logistics, shipping rates |
| biofuel | RFS, LCFS, 45Z, biodiesel mandates, renewable diesel, SAF |
| palm | Palm supply, MPOB, Indonesia/Malaysia policy |
| volatility | VIX, market stress, risk sentiment, positioning |
| substitutes | Canola, sunflower, rapeseed dynamics |
| trump_effect | Executive orders, policy announcements, trade rhetoric |
"""


# =============================================================================
# BASE AGENT CLASS
# =============================================================================


class BaseAgent(ABC):
    """Base class for all AI Compute Agents"""

    name: str = "base_agent"
    description: str = "Base agent class"

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model
        self.total_tokens = 0
        self.calls = 0
        self.errors = 0

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent"""
        pass

    @abstractmethod
    def process(self, input_data: dict) -> dict:
        """Process input and return results"""
        pass

    def get_stats(self) -> dict:
        return {
            "agent": self.name,
            "model": self.model,
            "calls": self.calls,
            "errors": self.errors,
            "total_tokens": self.total_tokens,
        }


# =============================================================================
# AGENT #1: SENTIMENT SCORER
# =============================================================================

SENTIMENT_SCORER_PROMPT = f"""You are the Sentiment Intelligence Engine for ZINC-Fusion-V15, an institutional-grade soybean oil (ZL) futures forecasting system.

{MARKET_INTELLIGENCE}

## YOUR MISSION
Analyze news articles and determine their impact on soybean oil prices with institutional-grade precision. Your analysis powers:
1. The 11 Specialist models (Crush, China, FX, Fed, Tariff, Energy, Biofuel, Palm, Volatility, Substitutes, Trump Effect)
2. Dashboard visualizations showing factor breakdowns
3. Procurement decision intelligence: "Should I buy oil today or wait?"

## ANTI-HALLUCINATION RULES
- ONLY score based on information EXPLICITLY stated in the article
- If the article doesn't mention ZL-relevant factors, mark is_zl_relevant=false
- When uncertain, REDUCE confidence, don't guess direction
- "I don't know" is better than fabrication

## INVERSION AWARENESS
Remember: FinBERT sees "fell/drop/decline" and says BEARISH. YOU must understand context:
- Production/supply falls → BULLISH (supply shock!)
- Demand/imports falls → BEARISH (demand destruction)
- Prices/margins falls → Context-dependent
- Crop conditions fall → BULLISH (weather stress = tight supply)

## SCORING GUIDELINES

### Impact Score (-1.0 to +1.0)
- +0.7 to +1.0: Major bullish catalyst (supply shock, demand surge, policy support)
- +0.3 to +0.6: Moderate bullish (tightening supply, steady demand growth)
- -0.1 to +0.1: Neutral / No clear direction
- -0.3 to -0.6: Moderate bearish (supply growth, demand weakness)
- -0.7 to -1.0: Major bearish catalyst (supply glut, demand collapse)

### Confidence (0.0 to 1.0)
- 0.9-1.0: Direct, explicit ZL price impact or obvious immediate effect
- 0.7-0.8: Clear causal chain to ZL prices
- 0.5-0.6: Indirect relationship requiring inference
- 0.3-0.4: Weak or speculative connection
- 0.0-0.2: Minimal relevance

### Time Horizon
- immediate: Days (breaking news, price moves)
- short_term: 1-4 weeks (weather, positioning)
- medium_term: 1-3 months (policy, seasonal)
- structural: 6+ months (trade deals, mandates)

## OUTPUT FORMAT
Return ONLY valid JSON:
{{
    "is_zl_relevant": true|false,
    "sentiment": "bullish"|"bearish"|"neutral",
    "impact_score": <float -1.0 to +1.0>,
    "confidence": <float 0.0 to 1.0>,
    "time_horizon": "immediate"|"short_term"|"medium_term"|"structural",
    "affected_specialists": ["specialist1", "specialist2"],
    "factor_breakdown": {{
        "specialist_name": {{
            "factor_name": <weight 0.0 to 1.0>
        }}
    }},
    "correlation_note": "<which correlations from the matrix are relevant, e.g. 'USD/BRL r=-0.65 applies here'>",
    "finbert_correction": "<if FinBERT would get this wrong, explain why, else null>",
    "reasoning": "<1-2 sentence explanation grounded in article>",
    "key_quote": "<relevant quote or null>",
    "overlay_narrative": "<dashboard overlay text like: 'Bullish pressure from South American drought; r=-0.70 with Brazil production supports 2-4% upside over 1-month horizon'>"
}}

Be decisive. Be grounded. Understand the market. Power the intelligence."""


class SentimentScorerAgent(BaseAgent):
    """
    Agent #1: Sentiment Scorer

    Analyzes news articles with ZL market expertise.
    Corrects FinBERT's commodity-blind scoring.
    Provides factor breakdowns for dashboard visualization.
    """

    name = "sentiment_scorer"
    description = "News sentiment analysis with soybean oil market expertise"

    def __init__(self, api_key: str = None):
        super().__init__(model="claude-sonnet-4-20250514")

        if api_key:
            self.api_key = api_key
        else:
            self.api_key = self._load_api_key()

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required")

        try:
            import anthropic

            self.client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            raise RuntimeError("anthropic package not installed")

        logger.info(f"SentimentScorerAgent initialized with {self.model}")

    def _load_api_key(self) -> str:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        return os.environ.get("ANTHROPIC_API_KEY")

    def get_system_prompt(self) -> str:
        return SENTIMENT_SCORER_PROMPT

    def process(self, input_data: dict) -> dict:
        headline = input_data.get("headline", "")
        content = input_data.get("content", "")
        source = input_data.get("source", "")
        finbert_score = input_data.get("finbert_score", 0)
        finbert_label = input_data.get("finbert_label", "neutral")

        user_msg = f"""Analyze this article for soybean oil (ZL) market impact:

HEADLINE: {headline}
SOURCE: {source}
FINBERT SCORE: {finbert_score:.4f} ({finbert_label})

CONTENT: {(content or "")[:1000]}

Remember: FinBERT scored this as {finbert_label} ({finbert_score:.4f}).
Check if this is correct given commodity market dynamics, or if FinBERT misunderstood.

Return your JSON analysis:"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=800,
                system=self.get_system_prompt(),
                messages=[{"role": "user", "content": user_msg}],
            )

            self.calls += 1
            self.total_tokens += (
                response.usage.input_tokens + response.usage.output_tokens
            )

            text = response.content[0].text.strip()

            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            result = json.loads(text)
            result["_tokens"] = (
                response.usage.input_tokens + response.usage.output_tokens
            )
            return result

        except json.JSONDecodeError as e:
            self.errors += 1
            logger.warning(f"JSON parse error: {e}")
            return self._default_result(f"JSON error: {str(e)[:50]}")
        except Exception as e:
            self.errors += 1
            logger.warning(f"Agent error: {e}")
            return self._default_result(f"Error: {str(e)[:50]}")

    def _default_result(self, error: str) -> dict:
        return {
            "is_zl_relevant": False,
            "sentiment": "neutral",
            "impact_score": 0.0,
            "confidence": 0.0,
            "time_horizon": "unknown",
            "affected_specialists": [],
            "factor_breakdown": {},
            "reasoning": error,
            "overlay_narrative": None,
            "_error": True,
        }


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================


def get_connection():
    env_path = PROJECT_ROOT / ".env"
    database_url = None

    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    database_url = line.split("=", 1)[1].strip().strip('"')
                    break

    if not database_url:
        raise ValueError("DATABASE_URL not found")

    return psycopg2.connect(database_url)


def fetch_articles_for_scoring(
    conn, limit: int = None, priority: str = "high_signal"
) -> list[dict]:
    """
    DEPRECATED: The old monolithic news + sentiment tables no longer exist.
    News was split into alt.policy_news_event, alt.executive_actions_event, alt.econ_news_event, alt.profarmer_news_event.
    Sentiment scoring tables were removed from the features schema.

    Returns empty list until proper migration is implemented.
    """
    import logging

    logging.warning(
        "fetch_articles_for_scoring: Old monolithic news/sentiment tables "
        "no longer exist. News data split into 4 domain-specific alt tables. "
        "Returning empty list until migration implemented."
    )
    return []


def update_article_with_ai_score(
    conn, raw_id: int, ai_result: dict, finbert_data: dict
):
    """
    DEPRECATED: The old sentiment table no longer exists.
    News data was split into alt.policy_news_event, alt.executive_actions_event, alt.econ_news_event, alt.profarmer_news_event.
    The features-layer sentiment table was removed during the v2 schema migration.

    Returns without action. Upstream fetch_articles_for_scoring() already returns empty list.
    """
    import logging

    logging.warning(
        "update_article_with_ai_score: Deprecated — old sentiment table no longer exists. "
        "No-op until migration to new news tables is implemented."
    )
    return


def refresh_specialist_training(conn):
    """
    DEPRECATED: The old sentiment table no longer exists (removed during v2 migration).
    Trump effect training signals are now generated via scripts/refresh_trump_effect_features.py
    which reads directly from alt.executive_actions_event and alt.policy_news_event.

    Returns without action.
    """
    logger.warning(
        "refresh_specialist_training: Deprecated — old sentiment table no longer exists. "
        "Use scripts/refresh_trump_effect_features.py instead."
    )
    return


# =============================================================================
# MAIN RUNNER
# =============================================================================


def run_ai_scoring(
    batch_size: int = 100,
    priority: str = "high_signal",
    rate_limit_delay: float = 12.0,  # Free tier: 5 req/min = 12s between calls
    max_articles: int = None,
):
    logger.info("=" * 70)
    logger.info("ZINC-FUSION AI COMPUTE LAYER")
    logger.info("Agent: SentimentScorer | Model: claude-sonnet-4-20250514")
    logger.info(
        f"Priority: {priority} | Batch: {batch_size} | Max: {max_articles or 'all'}"
    )
    logger.info(f"Rate limit delay: {rate_limit_delay}s between calls")
    logger.info("=" * 70)

    conn = get_connection()
    agent = SentimentScorerAgent()

    try:
        articles = fetch_articles_for_scoring(
            conn, limit=max_articles, priority=priority
        )
        logger.info(f"Found {len(articles)} articles to process")

        if not articles:
            logger.info("No articles to score!")
            return

        processed = 0
        start_time = time.time()

        for i, article in enumerate(articles):
            raw_id = article["raw_id"]
            headline = article.get("headline", "")[:80]

            input_data = {
                "headline": article.get("headline", ""),
                "content": article.get("content", ""),
                "source": article.get("source", ""),
                "finbert_score": float(article.get("finbert_score", 0) or 0),
                "finbert_label": article.get("finbert_label", "neutral"),
            }

            result = agent.process(input_data)

            finbert_data = {
                "score": input_data["finbert_score"],
                "label": input_data["finbert_label"],
                "confidence": 0.7,
            }

            update_article_with_ai_score(conn, raw_id, result, finbert_data)
            processed += 1

            sentiment = result.get("sentiment", "?")
            score = result.get("impact_score", 0)
            overlay = (result.get("overlay_narrative") or "")[:70]
            correction = result.get("finbert_correction")

            logger.info(
                f"[{processed}/{len(articles)}] {sentiment:8s} ({score:+.2f}) | {headline}..."
            )
            if overlay:
                logger.info(f"    └─ Overlay: {overlay}...")
            if correction:
                logger.info(f"    └─ FinBERT Fix: {correction[:60]}...")

            if processed % 10 == 0:
                conn.commit()

            time.sleep(rate_limit_delay)

        conn.commit()
        refresh_specialist_training(conn)

        elapsed = time.time() - start_time
        stats = agent.get_stats()

        logger.info("=" * 70)
        logger.info("AI SCORING COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Articles processed: {processed}")
        logger.info(
            f"Time elapsed: {elapsed:.1f}s ({processed / elapsed * 60:.1f} articles/min)"
        )
        logger.info(f"API calls: {stats['calls']} | Errors: {stats['errors']}")
        logger.info(f"Total tokens: {stats['total_tokens']:,}")

        est_cost = (
            stats["total_tokens"] * 0.6 * 3 + stats["total_tokens"] * 0.4 * 15
        ) / 1_000_000
        logger.info(f"Estimated cost: ${est_cost:.4f}")

    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ZINC-Fusion AI Compute Layer")
    parser.add_argument("--batch", type=int, default=100, help="Batch size")
    parser.add_argument(
        "--priority",
        choices=["high_signal", "recent", "trump", "unscored"],
        default="high_signal",
        help="Article priority",
    )
    parser.add_argument("--max", type=int, default=None, help="Max articles to process")
    parser.add_argument(
        "--delay", type=float, default=12.0, help="Delay between API calls (seconds)"
    )

    args = parser.parse_args()

    run_ai_scoring(
        batch_size=args.batch,
        priority=args.priority,
        max_articles=args.max,
        rate_limit_delay=args.delay,
    )
