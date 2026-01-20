#!/usr/bin/env python3
"""
ZINC-FUSION-V15: DeBERTa Relevance Gate
========================================
Superior zero-shot classification using MoritzLaurer/deberta-v3-large-zeroshot-v2.0

Replaces archaic BART-MNLI which has NO semantic understanding.
DeBERTa-v3-zeroshot-v2.0 is trained on 500+ diverse classification tasks
with Mixtral synthetic data - ACTUALLY understands context.

Usage:
    python scripts/deberta_relevance_gate.py --mode score       # Score unscored articles
    python scripts/deberta_relevance_gate.py --mode rescore     # Rescore all articles
    python scripts/deberta_relevance_gate.py --mode test --limit 20
    python scripts/deberta_relevance_gate.py --mode cleanup     # Remove garbage to archive

Architecture:
    1. DeBERTa relevance gate (is this ZL-related?)
    2. DeBERTa specialist routing (which Big 11 bucket?)
    3. Garbage articles (impact < 0.3) → archive table → purge weekly

Created: January 8, 2026
Author: Claude (AI Architect) for Kirk @ ZINC Digital
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

# Transformers for DeBERTa
try:
    import torch
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("ERROR: transformers not available. Install with: pip install transformers torch")

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
# CONFIGURATION
# =============================================================================

# DeBERTa model - SUPERIOR to BART-MNLI
DEBERTA_MODEL = "MoritzLaurer/deberta-v3-large-zeroshot-v2.0"

# Big 11 Specialists with semantic descriptions
BIG_11_CATEGORIES = {
    "crush": "soybean crushing, crush margins, soybean meal demand, oil share, processing capacity, NOPA crush",
    "china": "China soybean imports, Chinese demand, China trade policy, China stockpiling, Dalian futures",
    "fx": "currency exchange rates, USD BRL, dollar strength, Brazilian real, Argentine peso, forex",
    "fed": "Federal Reserve, interest rates, monetary policy, FOMC, inflation, rate cuts, Treasury yields",
    "tariff": "tariffs, trade war, import duties, Section 301, retaliatory tariffs, trade policy",
    "energy": "crude oil prices, WTI, diesel, heating oil, energy costs, petroleum, crack spreads",
    "biofuel": "biodiesel, renewable diesel, RFS mandate, RIN prices, 45Z credits, EPA biofuel, SAF",
    "palm": "palm oil, Indonesia palm, Malaysia palm, MPOB, palm oil exports, B40 mandate",
    "volatility": "VIX, market volatility, risk sentiment, stock market, financial stress, options",
    "substitutes": "canola oil, sunflower oil, rapeseed, vegetable oil alternatives, oil substitution",
    "trump_effect": "Trump policy, executive orders, Trump tariffs, Truth Social, White House announcements",
}

# Relevance gate categories
RELEVANCE_CATEGORIES = [
    "soybean oil futures trading, ZL commodity, vegetable oil markets, oilseed industry",
    "celebrity news, sports scores, entertainment gossip, local weather, unrelated topics"
]

# Thresholds
RELEVANCE_THRESHOLD = 0.5
GARBAGE_IMPACT_THRESHOLD = 0.2
ARCHIVE_RETENTION_DAYS = 7


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


# =============================================================================
# DEBERTA RELEVANCE GATE
# =============================================================================

class DeBERTaRelevanceGate:
    """Superior zero-shot classification using DeBERTa-v3-zeroshot-v2.0"""
    
    def __init__(self, device: str = None):
        if not TRANSFORMERS_AVAILABLE:
            raise RuntimeError("transformers library not installed")
        
        logger.info(f"Loading DeBERTa model: {DEBERTA_MODEL}")
        
        if device:
            self.device = device
        elif torch.backends.mps.is_available():
            self.device = "mps"
            logger.info("Using MPS (Apple Metal) acceleration")
        elif torch.cuda.is_available():
            self.device = "cuda"
            logger.info("Using CUDA acceleration")
        else:
            self.device = "cpu"
            logger.info("Using CPU")
        
        self.classifier = pipeline(
            "zero-shot-classification",
            model=DEBERTA_MODEL,
            device=0 if self.device == "cuda" else -1 if self.device == "cpu" else self.device
        )
        
        self.relevance_labels = RELEVANCE_CATEGORIES
        self.specialist_labels = list(BIG_11_CATEGORIES.values())
        self.specialist_names = list(BIG_11_CATEGORIES.keys())
        
        logger.info(f"DeBERTa loaded on {self.device}")
        
        self.articles_processed = 0
        self.relevant_count = 0
        self.garbage_count = 0
    
    def check_relevance(self, text: str) -> Tuple[bool, float]:
        """Check if article is relevant to soybean oil markets."""
        if not text or len(text.strip()) < 20:
            return False, 0.0
        
        text = text[:512]
        
        result = self.classifier(
            text,
            candidate_labels=self.relevance_labels,
            hypothesis_template="This text is about {}."
        )
        
        relevant_score = result["scores"][0] if result["labels"][0] == self.relevance_labels[0] else result["scores"][1]
        is_relevant = relevant_score > RELEVANCE_THRESHOLD
        return is_relevant, relevant_score
    
    def route_to_specialist(self, text: str) -> Dict[str, Any]:
        """Route article to appropriate Big 11 specialist(s)."""
        if not text or len(text.strip()) < 20:
            return {"primary_specialist": None, "specialist_scores": {}, "affected_specialists": []}
        
        text = text[:512]
        
        result = self.classifier(
            text,
            candidate_labels=self.specialist_labels,
            hypothesis_template="This text is relevant to {}.",
            multi_label=True
        )
        
        specialist_scores = {}
        for label, score in zip(result["labels"], result["scores"]):
            for name, desc in BIG_11_CATEGORIES.items():
                if desc == label:
                    specialist_scores[name] = round(score, 4)
                    break
        
        affected = [name for name, score in specialist_scores.items() if score > 0.3]
        primary = max(specialist_scores, key=specialist_scores.get) if specialist_scores else None
        
        return {
            "primary_specialist": primary,
            "specialist_scores": specialist_scores,
            "affected_specialists": affected
        }
    
    def score_article(self, headline: str, content: str = None) -> Dict[str, Any]:
        """Full scoring pipeline: relevance gate → specialist routing"""
        text = headline
        if content:
            text = f"{headline}. {content[:300]}"
        
        is_relevant, relevance_score = self.check_relevance(text)
        self.articles_processed += 1
        
        if not is_relevant:
            self.garbage_count += 1
            return {
                "is_zl_relevant": False,
                "relevance_score": round(relevance_score, 4),
                "zl_impact_score": 0.0,
                "canonical_bucket": "0",
                "primary_specialist": None,
                "affected_specialists": [],
                "specialist_scores": {},
                "gate_model": "deberta-v3-zeroshot-v2.0"
            }
        
        self.relevant_count += 1
        routing = self.route_to_specialist(text)
        
        if routing["specialist_scores"]:
            max_score = max(routing["specialist_scores"].values())
            impact_score = max(0.2, min(1.0, max_score))
        else:
            impact_score = 0.3
        
        return {
            "is_zl_relevant": True,
            "relevance_score": round(relevance_score, 4),
            "zl_impact_score": round(impact_score, 4),
            "canonical_bucket": routing["primary_specialist"],
            "primary_specialist": routing["primary_specialist"],
            "affected_specialists": routing["affected_specialists"],
            "specialist_scores": routing["specialist_scores"],
            "gate_model": "deberta-v3-zeroshot-v2.0"
        }
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "articles_processed": self.articles_processed,
            "relevant_count": self.relevant_count,
            "garbage_count": self.garbage_count,
            "relevance_rate": round(self.relevant_count / max(1, self.articles_processed), 3)
        }


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def ensure_archive_table(conn):
    """Create archive table for garbage articles if not exists"""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS archive.news_articles (
                id SERIAL PRIMARY KEY,
                original_id INTEGER,
                headline TEXT,
                content TEXT,
                source VARCHAR(255),
                event_date DATE,
                specialist_tags TEXT[],
                sentiment_score NUMERIC,
                archived_at TIMESTAMP DEFAULT NOW(),
                archive_reason VARCHAR(100)
            );
            CREATE INDEX IF NOT EXISTS idx_archive_date ON archive.news_articles(archived_at);
        """)
        conn.commit()
    logger.info("Archive table ready")


def fetch_articles_for_scoring(conn, limit: int = None, only_unscored: bool = True) -> List[Dict]:
    """Fetch articles needing DeBERTa scoring"""
    where_clause = ""
    if only_unscored:
        where_clause = "WHERE s.id IS NULL OR s.scoring_model IS NULL OR s.scoring_model NOT LIKE '%deberta%'"
    
    limit_clause = f"LIMIT {limit}" if limit else ""
    
    query = f"""
        SELECT r.id, r.headline, r.content, r.source, r.bucket_name, r.published_at, s.id as silver_id
        FROM alt.news_1d r
        LEFT JOIN features.news_sentiment_1d s ON r.id = s.raw_id
        {where_clause}
        ORDER BY r.published_at DESC
        {limit_clause}
    """
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        return [dict(row) for row in cur.fetchall()]


def upsert_silver_score(conn, raw_id: int, result: Dict[str, Any], headline: str, source: str):
    """Insert or update features.news_sentiment_1d with DeBERTa scores"""
    affected = set(result.get("affected_specialists", []))
    
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO features.news_sentiment_1d (
                raw_id, headline, source, 
                is_zl_relevant, zl_impact_score, sentiment_score, sentiment_direction,
                canonical_bucket,
                affects_crush, affects_china, affects_fx, affects_fed, affects_tariff,
                affects_energy, affects_biofuel, affects_palm, affects_volatility,
                affects_substitutes, affects_trump_effect,
                matched_categories, scoring_model, scored_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, NOW()
            )
            ON CONFLICT (raw_id) DO UPDATE SET
                is_zl_relevant = EXCLUDED.is_zl_relevant,
                zl_impact_score = EXCLUDED.zl_impact_score,
                canonical_bucket = EXCLUDED.canonical_bucket,
                affects_crush = EXCLUDED.affects_crush,
                affects_china = EXCLUDED.affects_china,
                affects_fx = EXCLUDED.affects_fx,
                affects_fed = EXCLUDED.affects_fed,
                affects_tariff = EXCLUDED.affects_tariff,
                affects_energy = EXCLUDED.affects_energy,
                affects_biofuel = EXCLUDED.affects_biofuel,
                affects_palm = EXCLUDED.affects_palm,
                affects_volatility = EXCLUDED.affects_volatility,
                affects_substitutes = EXCLUDED.affects_substitutes,
                affects_trump_effect = EXCLUDED.affects_trump_effect,
                matched_categories = EXCLUDED.matched_categories,
                scoring_model = EXCLUDED.scoring_model,
                scored_at = NOW()
        """, (
            raw_id, headline[:500] if headline else None, source,
            result.get("is_zl_relevant", False),
            result.get("zl_impact_score", 0),
            result.get("zl_impact_score", 0),
            "neutral" if abs(result.get("zl_impact_score", 0)) < 0.1 else ("bullish" if result.get("zl_impact_score", 0) > 0 else "bearish"),
            result.get("canonical_bucket", "0"),
            "crush" in affected, "china" in affected, "fx" in affected, "fed" in affected, "tariff" in affected,
            "energy" in affected, "biofuel" in affected, "palm" in affected, "volatility" in affected,
            "substitutes" in affected, "trump_effect" in affected,
            json.dumps({"deberta_gate": {"relevance_score": result.get("relevance_score"), "specialist_scores": result.get("specialist_scores"), "model": result.get("gate_model")}}),
            result.get("gate_model", "deberta-v3-zeroshot-v2.0")
        ))


def get_bucket_distribution(conn) -> List[Dict]:
    """Get current bucket distribution"""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT COALESCE(canonical_bucket, 'unassigned') as bucket, COUNT(*) as count,
                   ROUND(AVG(zl_impact_score)::numeric, 3) as avg_impact
            FROM features.news_sentiment_1d GROUP BY canonical_bucket ORDER BY count DESC
        """)
        return [dict(row) for row in cur.fetchall()]


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_scoring(mode: str = "score", limit: int = None):
    """Run the DeBERTa relevance gate pipeline"""
    logger.info("=" * 70)
    logger.info("ZINC-FUSION DeBERTa Relevance Gate")
    logger.info(f"Mode: {mode} | Limit: {limit}")
    logger.info("=" * 70)
    
    conn = get_connection()
    
    try:
        gate = DeBERTaRelevanceGate()
        only_unscored = mode not in ["rescore", "all"]
        articles = fetch_articles_for_scoring(conn, limit=limit, only_unscored=only_unscored)
        logger.info(f"Found {len(articles)} articles to process")
        
        if not articles:
            logger.info("No articles to score")
            return
        
        start_time = time.time()
        scored = 0
        
        for i, article in enumerate(articles):
            result = gate.score_article(headline=article.get("headline", ""), content=article.get("content", ""))
            upsert_silver_score(conn, raw_id=article["id"], result=result, headline=article.get("headline"), source=article.get("source"))
            scored += 1
            
            if scored % 100 == 0:
                conn.commit()
                elapsed = time.time() - start_time
                logger.info(f"Progress: {scored}/{len(articles)} | {scored/elapsed:.1f} articles/sec")
        
        conn.commit()
        elapsed = time.time() - start_time
        
        stats = gate.get_stats()
        logger.info("\n" + "=" * 70)
        logger.info("SCORING COMPLETE")
        logger.info(f"Processed: {stats['articles_processed']} articles in {elapsed:.1f}s")
        logger.info(f"Relevant: {stats['relevant_count']} ({stats['relevance_rate']*100:.1f}%)")
        logger.info(f"Garbage: {stats['garbage_count']} ({100-stats['relevance_rate']*100:.1f}%)")
        logger.info("=" * 70)
        
        dist = get_bucket_distribution(conn)
        logger.info("\nBucket Distribution:")
        for row in dist:
            logger.info(f"  {row['bucket']}: {row['count']} articles (avg impact: {row['avg_impact']})")
        
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="ZINC-FUSION DeBERTa Relevance Gate")
    parser.add_argument("--mode", choices=["score", "rescore", "test", "cleanup", "status"], default="score")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    
    if args.mode == "test":
        args.limit = args.limit or 20
    
    if args.mode == "status":
        conn = get_connection()
        dist = get_bucket_distribution(conn)
        print("\nCurrent Bucket Distribution:")
        for row in dist:
            print(f"  {row['bucket']}: {row['count']} articles")
        conn.close()
    else:
        run_scoring(mode=args.mode, limit=args.limit)


if __name__ == "__main__":
    main()
