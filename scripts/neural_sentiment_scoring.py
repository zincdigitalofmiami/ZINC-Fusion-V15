#!/usr/bin/env python3
"""
ZINC-FUSION Neural Sentiment Stack
===================================
Dual-neural sentiment scoring: FinBERT + Claude Sonnet 4.5

Architecture:
  Layer 1: FinBERT (ProsusAI/finbert) - Financial domain NLP
  Layer 2: Claude Sonnet 4.5 - Contextual ZL market impact analysis
  Fusion: Weighted ensemble with confidence weighting

This creates institutional-grade sentiment scoring for soybean oil news.

Usage:
    python scripts/neural_sentiment_scoring.py --mode full
    python scripts/neural_sentiment_scoring.py --mode finbert-only
    python scripts/neural_sentiment_scoring.py --mode test --limit 10
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

# Transformers for FinBERT
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("WARNING: transformers not available, FinBERT disabled")

# Anthropic for Claude
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("WARNING: anthropic not available, Claude scoring disabled")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def get_connection():
    """Get database connection from .env"""
    env_path = PROJECT_ROOT / ".env"
    database_url = None
    
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    database_url = line.split("=", 1)[1].strip().strip('"')
                    break
    
    if not database_url:
        database_url = os.environ.get("DATABASE_URL")
    
    if not database_url:
        raise ValueError("DATABASE_URL not found")
    
    return psycopg2.connect(database_url)


def get_anthropic_key():
    """Get Anthropic API key from .env"""
    env_path = PROJECT_ROOT / ".env"
    
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.startswith("ANTHROPIC_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
    
    return os.environ.get("ANTHROPIC_API_KEY")


# =============================================================================
# FINBERT SCORER
# =============================================================================

class FinBERTScorer:
    """Financial sentiment scoring using ProsusAI/finbert"""
    
    MODEL_NAME = "ProsusAI/finbert"
    
    def __init__(self):
        if not TRANSFORMERS_AVAILABLE:
            raise RuntimeError("transformers library not installed")
        
        logger.info(f"Loading FinBERT model: {self.MODEL_NAME}")
        self.tokenizer = AutoTokenizer.from_pretrained(self.MODEL_NAME)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.MODEL_NAME)
        
        # Use MPS (Metal) on Mac if available
        if torch.backends.mps.is_available():
            self.device = torch.device("mps")
            logger.info("Using MPS (Apple Metal) acceleration")
        elif torch.cuda.is_available():
            self.device = torch.device("cuda")
            logger.info("Using CUDA acceleration")
        else:
            self.device = torch.device("cpu")
            logger.info("Using CPU")
        
        self.model.to(self.device)
        self.model.eval()
        
        # Label mapping: 0=positive, 1=negative, 2=neutral
        self.labels = ["positive", "negative", "neutral"]
        logger.info("FinBERT loaded successfully")
    
    def score_text(self, text: str) -> Dict[str, Any]:
        """Score a single text, return sentiment dict"""
        if not text or len(text.strip()) < 10:
            return {
                "finbert_label": "neutral",
                "finbert_score": 0.0,
                "finbert_confidence": 0.0,
                "finbert_probs": {"positive": 0.33, "negative": 0.33, "neutral": 0.34}
            }
        
        # Truncate to max length
        text = text[:512]
        
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=1)[0].cpu().numpy()
        
        # Get label and confidence
        label_idx = probs.argmax()
        label = self.labels[label_idx]
        confidence = float(probs[label_idx])
        
        # Convert to score: positive=+1, negative=-1, neutral=0
        pos_prob = float(probs[0])
        neg_prob = float(probs[1])
        score = (pos_prob - neg_prob)  # Range: -1 to +1
        
        return {
            "finbert_label": label,
            "finbert_score": round(score, 4),
            "finbert_confidence": round(confidence, 4),
            "finbert_probs": {
                "positive": round(pos_prob, 4),
                "negative": round(neg_prob, 4),
                "neutral": round(float(probs[2]), 4)
            }
        }
    
    def score_batch(self, texts: List[str], batch_size: int = 16) -> List[Dict]:
        """Score multiple texts in batches for efficiency"""
        results = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_results = [self.score_text(t) for t in batch]
            results.extend(batch_results)
            
            if (i + batch_size) % 500 == 0:
                logger.info(f"FinBERT processed {min(i + batch_size, len(texts))}/{len(texts)}")
        
        return results


# =============================================================================
# CLAUDE SENTIMENT INTELLIGENCE ENGINE
# =============================================================================
#
# This is the brain of ZINC-Fusion's news analysis pipeline.
# Claude provides contextual, ZL-specific market impact analysis that 
# domain-agnostic models like FinBERT cannot deliver.
#
# Key capabilities:
#   - Soybean oil market dynamics understanding
#   - Procurement decision intelligence (buy today or wait?)
#   - Factor decomposition for dashboard visualization
#   - Multi-specialist routing intelligence
#   - Anti-hallucination guardrails
#
# =============================================================================

# The Big 11 Specialist Factor Taxonomy
# Each specialist has specific factors that drive its signal
SPECIALIST_FACTORS = {
    "crush": [
        "crush_margins", "processing_capacity", "meal_demand", "domestic_demand",
        "soybean_supply", "plant_operations", "labor_issues", "basis_levels"
    ],
    "china": [
        "import_policy", "stockpile_activity", "demand_signals", "buying_pace",
        "trade_relations", "economic_growth", "hog_herd_rebuild", "food_security"
    ],
    "fx": [
        "dollar_strength", "brl_movement", "ars_movement", "currency_volatility",
        "em_currencies", "trade_weighted_dollar"
    ],
    "fed": [
        "interest_rates", "monetary_policy", "inflation_outlook", "fomc_signals",
        "economic_data", "recession_risk", "liquidity_conditions"
    ],
    "tariff": [
        "trade_policy", "import_duties", "export_restrictions", "retaliatory_tariffs",
        "trade_negotiations", "wto_rulings", "bilateral_deals", "section_301"
    ],
    "energy": [
        "crude_correlation", "diesel_prices", "logistics_costs", "shipping_rates",
        "pipeline_capacity", "refinery_operations", "fuel_demand"
    ],
    "biofuel": [
        "rfs_volumes", "lcfs_credits", "biodiesel_mandates", "saf_demand",
        "blending_requirements", "renewable_diesel", "epa_policy", "45z_credits"
    ],
    "palm": [
        "palm_supply", "mpob_stocks", "indonesia_policy", "malaysia_output",
        "export_levies", "substitution_dynamics", "sustainability_rules"
    ],
    "volatility": [
        "market_stress", "risk_sentiment", "options_activity", "spec_positioning",
        "liquidity_conditions", "correlation_shifts", "vix_levels"
    ],
    "substitutes": [
        "canola_supply", "sunflower_availability", "rapeseed_dynamics",
        "substitute_pricing", "cross_commodity_spreads", "demand_switching"
    ],
    "trump_effect": [
        "executive_orders", "policy_announcements", "trade_rhetoric", "tariff_threats",
        "deregulation", "energy_policy", "ag_policy", "truth_social_posts"
    ]
}

CLAUDE_SYSTEM_PROMPT = """You are the Sentiment Intelligence Engine for ZINC-Fusion-V15, an institutional-grade soybean oil (ZL) futures forecasting system.

## YOUR ROLE
You analyze news articles to determine their impact on soybean oil prices. Your analysis feeds directly into:
1. The L0 Specialist models (10 domain experts + trump_effect)
2. Dashboard visualizations showing factor breakdowns
3. Procurement decision intelligence for "Should I buy oil today or wait?"

## CORE PRINCIPLES

### Anti-Hallucination Rules
- ONLY score based on information explicitly stated in the article
- If the article doesn't mention soybean oil or related factors, mark as NOT RELEVANT
- Never infer market impact that isn't supported by the text
- When uncertain, reduce confidence score, don't guess direction
- "I don't know" is better than fabrication

### Confidence Calibration
- 0.9-1.0: Direct, explicit ZL price impact stated or obvious immediate market effect
- 0.7-0.8: Clear causal chain to ZL (e.g., "China increases soybean imports" → bullish)
- 0.5-0.6: Indirect relationship requiring inference (e.g., "drought in Argentina")
- 0.3-0.4: Weak or speculative connection
- 0.0-0.2: Minimal relevance or unable to determine impact

### Impact Scoring (-1.0 to +1.0)
- +0.7 to +1.0: Major bullish catalyst (supply shock, demand surge, policy support)
- +0.3 to +0.6: Moderate bullish (tightening supply, steady demand growth)
- +0.1 to +0.2: Slight bullish lean
- -0.1 to +0.1: Neutral / No clear direction
- -0.2 to -0.1: Slight bearish lean
- -0.6 to -0.3: Moderate bearish (supply growth, demand weakness)
- -1.0 to -0.7: Major bearish catalyst (supply glut, demand collapse, policy reversal)

## SPECIALIST ROUTING
Identify which of these 11 specialists should receive this article's signal:
- crush: US domestic soybean processing, crush margins, meal/oil demand
- china: Chinese import policy, demand, stockpiling, trade relations
- fx: Currency movements affecting competitiveness (USD, BRL, ARS)
- fed: Monetary policy, interest rates, macro economic conditions
- tariff: Trade policy, import/export duties, trade negotiations
- energy: Crude oil correlation, diesel, logistics, shipping
- biofuel: RFS, LCFS, biodiesel mandates, renewable diesel, SAF
- palm: Palm oil supply, Indonesia/Malaysia policy, substitution
- volatility: Market stress, risk sentiment, positioning
- substitutes: Canola, sunflower, rapeseed dynamics
- trump_effect: Executive orders, policy shifts, trade rhetoric

## FACTOR DECOMPOSITION
For each affected specialist, identify the specific factors driving the signal.
This powers the dashboard "jewelry" - visual factor breakdowns on specialist cards.

Valid factors by specialist:
- crush: crush_margins, processing_capacity, meal_demand, domestic_demand, soybean_supply, plant_operations, labor_issues, basis_levels
- china: import_policy, stockpile_activity, demand_signals, buying_pace, trade_relations, economic_growth, hog_herd_rebuild, food_security
- fx: dollar_strength, brl_movement, ars_movement, currency_volatility, em_currencies, trade_weighted_dollar
- fed: interest_rates, monetary_policy, inflation_outlook, fomc_signals, economic_data, recession_risk, liquidity_conditions
- tariff: trade_policy, import_duties, export_restrictions, retaliatory_tariffs, trade_negotiations, wto_rulings, bilateral_deals, section_301
- energy: crude_correlation, diesel_prices, logistics_costs, shipping_rates, pipeline_capacity, refinery_operations, fuel_demand
- biofuel: rfs_volumes, lcfs_credits, biodiesel_mandates, saf_demand, blending_requirements, renewable_diesel, epa_policy, 45z_credits
- palm: palm_supply, mpob_stocks, indonesia_policy, malaysia_output, export_levies, substitution_dynamics, sustainability_rules
- volatility: market_stress, risk_sentiment, options_activity, spec_positioning, liquidity_conditions, correlation_shifts, vix_levels
- substitutes: canola_supply, sunflower_availability, rapeseed_dynamics, substitute_pricing, cross_commodity_spreads, demand_switching
- trump_effect: executive_orders, policy_announcements, trade_rhetoric, tariff_threats, deregulation, energy_policy, ag_policy, truth_social_posts

## OUTPUT FORMAT
Respond with ONLY valid JSON. No markdown, no explanation outside the JSON.

{
    "is_zl_relevant": true|false,
    "sentiment": "bullish"|"bearish"|"neutral",
    "zl_impact_score": <float -1.0 to +1.0>,
    "confidence": <float 0.0 to 1.0>,
    "time_horizon": "immediate"|"short_term"|"medium_term"|"structural",
    "affected_specialists": ["specialist1", "specialist2"],
    "factor_breakdown": {
        "specialist_name": {
            "factor_name": <weight 0.0 to 1.0>,
            "another_factor": <weight>
        }
    },
    "reasoning": "<1-2 sentence explanation grounded in article text>",
    "key_quote": "<relevant quote from article if applicable, else null>"
}

## EXAMPLES

Article: "USDA raises soybean crush forecast by 15 million bushels citing strong biodiesel demand"
→ is_zl_relevant: true, sentiment: bullish, zl_impact_score: 0.5, confidence: 0.85
→ affected_specialists: ["crush", "biofuel"]
→ factor_breakdown: {"crush": {"crush_margins": 0.6, "processing_capacity": 0.4}, "biofuel": {"biodiesel_mandates": 0.8, "renewable_diesel": 0.2}}

Article: "Hong Kong pop star announces world tour dates"
→ is_zl_relevant: false, sentiment: neutral, zl_impact_score: 0, confidence: 0.95
→ affected_specialists: []
→ factor_breakdown: {}
→ reasoning: "Entertainment news with no connection to agricultural commodities or soybean oil markets"

Be decisive. Be grounded. Power the intelligence."""


class ClaudeSentimentScorer:
    """
    The Sentiment Intelligence Engine - contextual ZL market impact analysis.
    
    Uses Claude Sonnet 4.5 for:
    - ZL-specific market understanding
    - Factor decomposition for dashboard visualization
    - Multi-specialist routing
    - Procurement decision intelligence
    """
    
    MODEL = "claude-sonnet-4-20250514"  # Sonnet 4 - fast, cost-effective, great at structured JSON
    
    def __init__(self, api_key: str = None):
        if not ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic library not installed")
        
        self.api_key = api_key or get_anthropic_key()
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in .env or environment")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.articles_processed = 0
        self.errors = 0
        logger.info(f"Claude Sentiment Intelligence Engine initialized: {self.MODEL}")
    
    def score_article(self, headline: str, content: str = None, source: str = None) -> Dict[str, Any]:
        """
        Score a single article with full factor decomposition.
        
        Returns comprehensive analysis including:
        - Sentiment direction and score
        - Confidence level
        - Affected specialists
        - Factor breakdown for dashboard
        - Reasoning grounded in text
        """
        
        # Build analysis text - headline is most important
        text_parts = [f"HEADLINE: {headline}"]
        if source:
            text_parts.append(f"SOURCE: {source}")
        if content:
            # Truncate content to save tokens but keep substance
            content_clean = content.strip()
            if len(content_clean) > 800:
                content_preview = content_clean[:800] + "..."
            else:
                content_preview = content_clean
            text_parts.append(f"CONTENT: {content_preview}")
        
        user_message = "\n\n".join(text_parts)
        
        try:
            response = self.client.messages.create(
                model=self.MODEL,
                max_tokens=512,
                system=CLAUDE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}]
            )
            
            # Track usage
            self.total_input_tokens += response.usage.input_tokens
            self.total_output_tokens += response.usage.output_tokens
            self.articles_processed += 1
            
            # Parse JSON response
            response_text = response.content[0].text.strip()
            
            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                json_lines = []
                in_json = False
                for line in lines:
                    if line.startswith("```") and not in_json:
                        in_json = True
                        continue
                    elif line.startswith("```") and in_json:
                        break
                    elif in_json:
                        json_lines.append(line)
                response_text = "\n".join(json_lines)
            
            result = json.loads(response_text)
            
            # Validate and normalize the response
            return self._normalize_response(result)
            
        except json.JSONDecodeError as e:
            logger.warning(f"Claude JSON parse error for '{headline[:50]}...': {e}")
            self.errors += 1
            return self._default_result(f"JSON parse error: {str(e)[:50]}")
        except anthropic.APIError as e:
            logger.warning(f"Claude API error: {e}")
            self.errors += 1
            return self._default_result(f"API error: {str(e)[:50]}")
        except Exception as e:
            logger.warning(f"Claude scoring error: {e}")
            self.errors += 1
            return self._default_result(f"Error: {str(e)[:50]}")
    
    def _normalize_response(self, result: Dict) -> Dict[str, Any]:
        """Validate and normalize Claude's response"""
        
        # Ensure all required fields exist with proper types
        normalized = {
            "is_zl_relevant": bool(result.get("is_zl_relevant", False)),
            "claude_sentiment": str(result.get("sentiment", "neutral")).lower(),
            "claude_zl_impact": float(result.get("zl_impact_score", 0)),
            "claude_confidence": float(result.get("confidence", 0.5)),
            "claude_time_horizon": str(result.get("time_horizon", "short_term")),
            "affected_specialists": result.get("affected_specialists", []),
            "factor_breakdown": result.get("factor_breakdown", {}),
            "claude_reasoning": str(result.get("reasoning", "")),
            "key_quote": result.get("key_quote"),
        }
        
        # Clamp values to valid ranges
        normalized["claude_zl_impact"] = max(-1.0, min(1.0, normalized["claude_zl_impact"]))
        normalized["claude_confidence"] = max(0.0, min(1.0, normalized["claude_confidence"]))
        
        # Validate sentiment
        if normalized["claude_sentiment"] not in ["bullish", "bearish", "neutral"]:
            normalized["claude_sentiment"] = "neutral"
        
        # Validate specialists
        valid_specialists = set(SPECIALIST_FACTORS.keys())
        normalized["affected_specialists"] = [
            s for s in normalized["affected_specialists"] 
            if s in valid_specialists
        ]
        
        # Validate factor breakdown
        validated_factors = {}
        for specialist, factors in normalized["factor_breakdown"].items():
            if specialist in valid_specialists and isinstance(factors, dict):
                valid_factor_names = set(SPECIALIST_FACTORS[specialist])
                validated_factors[specialist] = {
                    k: max(0.0, min(1.0, float(v)))
                    for k, v in factors.items()
                    if k in valid_factor_names
                }
        normalized["factor_breakdown"] = validated_factors
        
        return normalized
    
    def _default_result(self, error_msg: str = "") -> Dict[str, Any]:
        """Return default result for error cases"""
        return {
            "is_zl_relevant": False,
            "claude_sentiment": "neutral",
            "claude_zl_impact": 0.0,
            "claude_confidence": 0.0,
            "claude_time_horizon": "unknown",
            "affected_specialists": [],
            "factor_breakdown": {},
            "claude_reasoning": error_msg or "Error processing article",
            "key_quote": None,
        }
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get token usage and cost statistics"""
        # Sonnet 4.5 pricing: $3/M input, $15/M output
        input_cost = (self.total_input_tokens * 3.0) / 1_000_000
        output_cost = (self.total_output_tokens * 15.0) / 1_000_000
        
        return {
            "articles_processed": self.articles_processed,
            "errors": self.errors,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "estimated_cost_usd": round(input_cost + output_cost, 4),
            "avg_tokens_per_article": round(
                (self.total_input_tokens + self.total_output_tokens) / max(1, self.articles_processed), 1
            )
        }


# =============================================================================
# ENSEMBLE FUSION
# =============================================================================

def fuse_neural_scores(
    finbert_result: Dict[str, Any],
    claude_result: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Fuse FinBERT and Claude scores into final ensemble sentiment.
    
    Weighting strategy:
    - FinBERT: General financial sentiment baseline (weight: 0.35)
    - Claude: ZL-specific contextual analysis (weight: 0.65)
    
    Claude gets higher weight because:
    1. It understands soybean oil market dynamics
    2. It provides factor decomposition for dashboards
    3. It routes to correct specialists
    
    The ensemble preserves Claude's rich metadata while incorporating
    FinBERT's domain-trained financial sentiment as a sanity check.
    """
    
    finbert_score = finbert_result.get("finbert_score", 0)
    finbert_conf = finbert_result.get("finbert_confidence", 0.5)
    finbert_label = finbert_result.get("finbert_label", "neutral")
    
    # If Claude result available, do weighted fusion
    if claude_result and claude_result.get("claude_confidence", 0) > 0:
        claude_score = claude_result.get("claude_zl_impact", 0)
        claude_conf = claude_result.get("claude_confidence", 0.5)
        claude_relevant = claude_result.get("is_zl_relevant", False)
        
        # If Claude says not relevant, trust that judgment
        if not claude_relevant:
            return {
                "ensemble_score": 0.0,
                "ensemble_direction": "neutral",
                "ensemble_confidence": claude_conf,
                "is_zl_relevant": False,
                "scoring_method": "finbert+claude",
                "finbert_contribution": finbert_result,
                "claude_contribution": claude_result,
                "affected_specialists": [],
                "factor_breakdown": {},
                "reasoning": claude_result.get("claude_reasoning", "Not relevant to ZL"),
            }
        
        # Confidence-weighted fusion
        # Claude dominates for ZL-specific analysis
        w_finbert = 0.35 * finbert_conf
        w_claude = 0.65 * claude_conf
        
        total_weight = w_finbert + w_claude
        if total_weight > 0:
            final_score = (finbert_score * w_finbert + claude_score * w_claude) / total_weight
        else:
            final_score = claude_score  # Default to Claude if weights are zero
        
        # Confidence is boosted when both agree, reduced when they disagree
        agreement_bonus = 0.1 if (finbert_score * claude_score > 0) else -0.05
        final_confidence = min(0.95, (finbert_conf * 0.4 + claude_conf * 0.6) + agreement_bonus)
        
        # Direction from final score
        if final_score > 0.05:
            direction = "bullish"
        elif final_score < -0.05:
            direction = "bearish"
        else:
            direction = "neutral"
        
        return {
            "ensemble_score": round(final_score, 4),
            "ensemble_direction": direction,
            "ensemble_confidence": round(final_confidence, 4),
            "is_zl_relevant": True,
            "scoring_method": "finbert+claude",
            "finbert_contribution": {
                "score": finbert_score,
                "confidence": finbert_conf,
                "label": finbert_label,
                "weight": round(w_finbert / total_weight if total_weight > 0 else 0, 3)
            },
            "claude_contribution": {
                "score": claude_score,
                "confidence": claude_conf,
                "sentiment": claude_result.get("claude_sentiment"),
                "weight": round(w_claude / total_weight if total_weight > 0 else 0, 3)
            },
            "affected_specialists": claude_result.get("affected_specialists", []),
            "factor_breakdown": claude_result.get("factor_breakdown", {}),
            "time_horizon": claude_result.get("claude_time_horizon", "short_term"),
            "reasoning": claude_result.get("claude_reasoning", ""),
            "key_quote": claude_result.get("key_quote"),
        }
    
    else:
        # FinBERT only fallback
        if finbert_score > 0.15:
            direction = "bullish"
        elif finbert_score < -0.15:
            direction = "bearish"
        else:
            direction = "neutral"
        
        return {
            "ensemble_score": round(finbert_score, 4),
            "ensemble_direction": direction,
            "ensemble_confidence": round(finbert_conf * 0.7, 4),  # Reduced confidence without Claude
            "is_zl_relevant": True,  # Assume relevant if we're scoring it
            "scoring_method": "finbert-only",
            "finbert_contribution": {
                "score": finbert_score,
                "confidence": finbert_conf,
                "label": finbert_label,
                "weight": 1.0
            },
            "claude_contribution": None,
            "affected_specialists": [],
            "factor_breakdown": {},
            "reasoning": f"FinBERT-only score: {finbert_label}",
        }


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def fetch_articles_for_scoring(conn, limit: int = None, only_unscored: bool = True) -> List[Dict]:
    """Fetch articles that need neural scoring"""
    
    where_clause = ""
    if only_unscored:
        # Get articles that don't have neural scores yet
        where_clause = """
            WHERE s.id IS NULL 
               OR s.scoring_model = 'rule-based-v1'
               OR s.scoring_model IS NULL
        """
    
    limit_clause = f"LIMIT {limit}" if limit else ""
    
    query = f"""
        SELECT 
            r.id,
            r.headline,
            r.content,
            r.source,
            r.bucket_name,
            r.published_at,
            r.is_trump_related,
            s.id as silver_id,
            s.scoring_model
        FROM raw.news_articles_1d r
        LEFT JOIN silver.news_scored_1d s ON r.id = s.raw_id
        {where_clause}
        ORDER BY r.published_at DESC
        {limit_clause}
    """
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        return [dict(row) for row in cur.fetchall()]


def update_silver_with_neural_scores(conn, article_id: int, ensemble: Dict, 
                                      finbert: Dict, claude: Dict = None):
    """Update silver.news_scored_1d with neural sentiment scores"""
    
    # Build specialist flags from Claude's routing
    affected = set(ensemble.get("affected_specialists", []))
    
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE silver.news_scored_1d
            SET 
                sentiment_score = %s,
                sentiment_direction = %s,
                sentiment_confidence = %s,
                is_zl_relevant = %s,
                zl_impact_score = %s,
                affects_crush = %s,
                affects_china = %s,
                affects_fx = %s,
                affects_fed = %s,
                affects_tariff = %s,
                affects_energy = %s,
                affects_biofuel = %s,
                affects_palm = %s,
                affects_volatility = %s,
                affects_substitutes = %s,
                affects_trump_effect = %s,
                matched_categories = %s,
                scoring_model = %s,
                scored_at = NOW()
            WHERE raw_id = %s
        """, (
            ensemble.get("ensemble_score", 0),
            ensemble.get("ensemble_direction", "neutral"),
            ensemble.get("ensemble_confidence", 0.5),
            ensemble.get("is_zl_relevant", True),
            ensemble.get("ensemble_score", 0),
            "crush" in affected,
            "china" in affected,
            "fx" in affected,
            "fed" in affected,
            "tariff" in affected,
            "energy" in affected,
            "biofuel" in affected,
            "palm" in affected,
            "volatility" in affected,
            "substitutes" in affected,
            "trump_effect" in affected,
            json.dumps({
                "finbert": finbert,
                "claude": claude,
                "ensemble": {
                    "score": ensemble.get("ensemble_score"),
                    "direction": ensemble.get("ensemble_direction"),
                    "confidence": ensemble.get("ensemble_confidence"),
                    "method": ensemble.get("scoring_method"),
                },
                "factor_breakdown": ensemble.get("factor_breakdown", {}),
                "reasoning": ensemble.get("reasoning", ""),
            }),
            ensemble.get("scoring_method", "neural"),
            article_id
        ))


def update_raw_sentiment(conn, article_id: int, score: float):
    """Update raw.news_articles_1d.sentiment_score"""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE raw.news_articles_1d
            SET sentiment_score = %s
            WHERE id = %s
        """, (score, article_id))


def refresh_trump_effect_training(conn):
    """Refresh training.specialist_trump_effect_1d from neural-scored silver data"""
    
    logger.info("Refreshing training.specialist_trump_effect_1d...")
    
    with conn.cursor() as cur:
        # Clear and repopulate
        cur.execute("DELETE FROM training.specialist_trump_effect_1d WHERE symbol = 'ZL'")
        
        cur.execute("""
            INSERT INTO training.specialist_trump_effect_1d (
                as_of_date, symbol, signal, confidence, features, created_at
            )
            SELECT 
                DATE(published_at) as as_of_date,
                'ZL' as symbol,
                AVG(sentiment_score) as signal,
                AVG(sentiment_confidence) as confidence,
                jsonb_build_object(
                    'article_count', COUNT(*),
                    'bullish_count', COUNT(*) FILTER (WHERE sentiment_direction = 'bullish'),
                    'bearish_count', COUNT(*) FILTER (WHERE sentiment_direction = 'bearish'),
                    'neutral_count', COUNT(*) FILTER (WHERE sentiment_direction = 'neutral'),
                    'avg_score', AVG(sentiment_score),
                    'max_score', MAX(sentiment_score),
                    'min_score', MIN(sentiment_score),
                    'scoring_method', MAX(scoring_model)
                ) as features,
                NOW() as created_at
            FROM silver.news_scored_1d
            WHERE affects_trump_effect = TRUE
              AND is_zl_relevant = TRUE
              AND published_at IS NOT NULL
            GROUP BY DATE(published_at)
        """)
        
        inserted = cur.rowcount
        conn.commit()
    
    logger.info(f"Refreshed trump_effect training: {inserted} days")
    return inserted


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_neural_scoring(
    mode: str = "full",
    limit: int = None,
    skip_claude: bool = False,
    skip_finbert: bool = False,
    claude_batch_size: int = 50,
    cost_limit_usd: float = 5.0
):
    """
    Run the neural sentiment scoring pipeline.
    
    Modes:
    - full: Score all articles with FinBERT + Claude
    - finbert-only: Score with FinBERT only (free, fast)
    - claude-only: Score with Claude only (skip FinBERT)
    - test: Score limited articles for testing
    
    Strategy:
    1. Load FinBERT and score ALL articles (fast, free, local)
    2. Use FinBERT scores to prioritize articles for Claude
    3. Score with Claude until cost limit reached
    4. Fuse scores and update database
    """
    
    logger.info("=" * 70)
    logger.info("ZINC-FUSION Neural Sentiment Scoring")
    logger.info(f"Mode: {mode} | Limit: {limit} | Cost limit: ${cost_limit_usd}")
    logger.info("=" * 70)
    
    conn = get_connection()
    
    try:
        # Fetch articles
        logger.info("Fetching articles for scoring...")
        articles = fetch_articles_for_scoring(conn, limit=limit, only_unscored=(mode != "rescore"))
        logger.info(f"Found {len(articles)} articles to process")
        
        if not articles:
            logger.info("No articles to score. Done!")
            return
        
        # Initialize scorers
        finbert_scorer = None
        claude_scorer = None
        
        if not skip_finbert:
            try:
                finbert_scorer = FinBERTScorer()
            except Exception as e:
                logger.warning(f"Could not load FinBERT: {e}")
                if skip_claude:
                    raise RuntimeError("Neither FinBERT nor Claude available!")
        
        if not skip_claude and mode != "finbert-only":
            try:
                claude_scorer = ClaudeSentimentScorer()
            except Exception as e:
                logger.warning(f"Could not initialize Claude: {e}")
        
        # Phase 1: FinBERT scoring (all articles, fast)
        finbert_results = {}
        if finbert_scorer:
            logger.info("\n--- Phase 1: FinBERT Scoring ---")
            texts = [f"{a.get('headline') or ''} {(a.get('content') or '')[:200]}" for a in articles]
            
            start_time = time.time()
            fb_scores = finbert_scorer.score_batch(texts, batch_size=32)
            elapsed = time.time() - start_time
            
            for article, fb_score in zip(articles, fb_scores):
                finbert_results[article["id"]] = fb_score
            
            logger.info(f"FinBERT completed: {len(articles)} articles in {elapsed:.1f}s")
            logger.info(f"  ({len(articles)/elapsed:.1f} articles/sec)")
        
        # Phase 2: Claude scoring (selective, with cost awareness)
        claude_results = {}
        if claude_scorer:
            logger.info("\n--- Phase 2: Claude Sentiment Intelligence ---")
            
            # Prioritize articles: non-neutral FinBERT scores first, then by recency
            def priority_key(article):
                fb = finbert_results.get(article["id"], {})
                fb_score = abs(fb.get("finbert_score", 0))
                # Higher absolute score = higher priority
                # More recent = higher priority (secondary)
                return (-fb_score, article.get("published_at") or datetime.min)
            
            sorted_articles = sorted(articles, key=priority_key)
            
            processed = 0
            batch_start = time.time()
            
            for i, article in enumerate(sorted_articles):
                # Check cost limit
                stats = claude_scorer.get_usage_stats()
                if stats["estimated_cost_usd"] >= cost_limit_usd:
                    logger.warning(f"Cost limit reached (${stats['estimated_cost_usd']:.4f}). Stopping Claude scoring.")
                    break
                
                # Score with Claude
                result = claude_scorer.score_article(
                    headline=article.get("headline", ""),
                    content=article.get("content", ""),
                    source=article.get("source", "")
                )
                claude_results[article["id"]] = result
                processed += 1
                
                # Progress logging
                if processed % claude_batch_size == 0:
                    elapsed = time.time() - batch_start
                    stats = claude_scorer.get_usage_stats()
                    logger.info(f"Claude progress: {processed}/{len(sorted_articles)} | "
                               f"${stats['estimated_cost_usd']:.4f} | "
                               f"{processed/elapsed:.1f} articles/sec")
            
            final_stats = claude_scorer.get_usage_stats()
            logger.info(f"Claude completed: {processed} articles")
            logger.info(f"  Tokens: {final_stats['total_tokens']:,} | Cost: ${final_stats['estimated_cost_usd']:.4f}")
        
        # Phase 3: Fusion and database update
        logger.info("\n--- Phase 3: Ensemble Fusion & Database Update ---")
        
        updated = 0
        for article in articles:
            article_id = article["id"]
            
            finbert = finbert_results.get(article_id, {
                "finbert_score": 0, "finbert_confidence": 0.5, "finbert_label": "neutral"
            })
            claude = claude_results.get(article_id)
            
            # Fuse scores
            ensemble = fuse_neural_scores(finbert, claude)
            
            # Update database
            update_silver_with_neural_scores(conn, article_id, ensemble, finbert, claude)
            update_raw_sentiment(conn, article_id, ensemble.get("ensemble_score", 0))
            updated += 1
            
            if updated % 500 == 0:
                conn.commit()
                logger.info(f"Updated {updated}/{len(articles)} articles...")
        
        conn.commit()
        logger.info(f"Database updated: {updated} articles")
        
        # Phase 4: Refresh training tables
        logger.info("\n--- Phase 4: Refresh Training Tables ---")
        refresh_trump_effect_training(conn)
        
        # Final summary
        logger.info("\n" + "=" * 70)
        logger.info("NEURAL SCORING COMPLETE")
        logger.info("=" * 70)
        
        if finbert_scorer:
            logger.info(f"FinBERT: {len(finbert_results)} articles scored")
        
        if claude_scorer:
            stats = claude_scorer.get_usage_stats()
            logger.info(f"Claude: {stats['articles_processed']} articles scored")
            logger.info(f"  Total tokens: {stats['total_tokens']:,}")
            logger.info(f"  Estimated cost: ${stats['estimated_cost_usd']:.4f}")
            logger.info(f"  Errors: {stats['errors']}")
        
        # Quick quality check
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    scoring_model,
                    COUNT(*) as count,
                    AVG(sentiment_score) as avg_score,
                    COUNT(*) FILTER (WHERE sentiment_direction = 'bullish') as bullish,
                    COUNT(*) FILTER (WHERE sentiment_direction = 'bearish') as bearish
                FROM silver.news_scored_1d
                GROUP BY scoring_model
            """)
            for row in cur.fetchall():
                logger.info(f"  {row[0]}: {row[1]} articles, avg={row[2]:.4f}, "
                           f"bullish={row[3]}, bearish={row[4]}")
        
    finally:
        conn.close()


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="ZINC-FUSION Neural Sentiment Scoring Pipeline"
    )
    parser.add_argument(
        "--mode", 
        choices=["full", "finbert-only", "claude-only", "test", "rescore"],
        default="full",
        help="Scoring mode"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of articles to process"
    )
    parser.add_argument(
        "--cost-limit",
        type=float,
        default=5.0,
        help="Maximum USD to spend on Claude API"
    )
    parser.add_argument(
        "--skip-finbert",
        action="store_true",
        help="Skip FinBERT scoring"
    )
    parser.add_argument(
        "--skip-claude",
        action="store_true", 
        help="Skip Claude scoring"
    )
    
    args = parser.parse_args()
    
    # Mode shortcuts
    if args.mode == "finbert-only":
        args.skip_claude = True
    elif args.mode == "claude-only":
        args.skip_finbert = True
    elif args.mode == "test":
        args.limit = args.limit or 10
    
    run_neural_scoring(
        mode=args.mode,
        limit=args.limit,
        skip_claude=args.skip_claude,
        skip_finbert=args.skip_finbert,
        cost_limit_usd=args.cost_limit
    )


if __name__ == "__main__":
    main()
