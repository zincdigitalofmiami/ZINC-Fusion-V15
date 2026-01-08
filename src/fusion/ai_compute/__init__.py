"""
ZINC-Fusion AI Compute Layer
============================

Real-time AI intelligence ON TOP of trained L0-L3 model outputs.

Agents:
    - SentimentScorerAgent: News analysis with ZL market expertise
    - CorrelationAnalyst: (coming) Compute & explain correlations
    - FactorAttributor: (coming) "What's driving this signal?"
    - OverlayNarrator: (coming) Chart overlay descriptions
    - ScenarioModeler: (coming) What-if analysis
"""

from .agent_pool import (
    BaseAgent,
    SentimentScorerAgent,
    MARKET_INTELLIGENCE,
    run_ai_scoring,
    get_connection,
    fetch_articles_for_scoring,
    update_article_with_ai_score,
    refresh_specialist_training,
)

__all__ = [
    "BaseAgent",
    "SentimentScorerAgent", 
    "MARKET_INTELLIGENCE",
    "run_ai_scoring",
    "get_connection",
    "fetch_articles_for_scoring",
    "update_article_with_ai_score",
    "refresh_specialist_training",
]
