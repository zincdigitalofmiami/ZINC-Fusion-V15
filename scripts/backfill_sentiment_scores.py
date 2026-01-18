#!/usr/bin/env python3
"""
ZINC-FUSION Sentiment Scoring Backfill
======================================
Scores all news articles and populates `features.news_sentiment_1d`.

Fixes:
1. sentiment_score column (100% NULL → scored)
2. China bucket contamination (adds is_zl_relevant filter)

Run: python scripts/backfill_sentiment_scores.py
"""

import os
import sys
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional
from decimal import Decimal

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.fusion.api.news_sentiment import classify_article

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def get_connection():
    """Get database connection from .env"""
    env_path = Path(__file__).parent.parent / ".env"
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
# CANONICAL BIG-11 BUCKET MAPPING
# =============================================================================

BUCKET_CANONICAL_MAP = {
    # Direct matches
    "crush": "crush",
    "china": "china", 
    "fx": "fx",
    "fed": "fed",
    "tariff": "tariff",
    "energy": "energy",
    "biofuel": "biofuel",
    "palm": "palm",
    "volatility": "volatility",
    "substitutes": "substitutes",
    "trump_effect": "trump_effect",
    
    # Legacy bucket mappings
    "China Relations": "china",
    "Tariff Updates": "tariff",
    "Political Changes": "fed",  # Policy/political → fed
    "Biofuel Mandates": "biofuel",
    "Logistics/Chokepoints": "energy",  # Supply chain → energy
    "ESG/Deforestation": "palm",  # ESG mostly affects palm
    "Labor Actions": "crush",  # Labor affects domestic crush
    "Fertilizer/Energy": "energy",
    "Animal Disease": "crush",  # Feed demand → crush
    "US Regulatory Filings": "fed",
    "Legislation Changes": "fed",
}

# ZL-relevant keywords for filtering noisy buckets
ZL_RELEVANT_KEYWORDS = [
    "soybean", "soy oil", "soyoil", "vegetable oil", "edible oil",
    "crush", "crushing", "oilseed", "bean", "meal", "biodiesel",
    "biofuel", "rfs", "lcfs", "palm", "canola", "sunflower",
    "rapeseed", "commodity", "futures", "cbot", "zl", "zm", "zs",
    "agriculture", "crop", "harvest", "planting", "yield",
    "export", "import", "tariff", "trade", "china", "brazil",
    "argentina", "usda", "wasde", "conab", "mpob",
    "trump", "biden", "executive order", "policy",
]

# Keywords that indicate NON-relevant articles
ZL_IRRELEVANT_KEYWORDS = [
    "celebrity", "singer", "actor", "movie", "film", "music",
    "sports", "football", "basketball", "soccer", "cricket",
    "crime", "murder", "robbery", "missing person",
    "restaurant", "recipe", "cooking show",
    "school", "university admission", "exam results",
    "real estate", "housing prices", "apartment",
]

def is_zl_relevant(title: str, content: str) -> bool:
    """Check if article is relevant to ZL/soybean oil markets."""
    text = f"{title} {content}".lower()
    
    # Check for irrelevant keywords first
    for kw in ZL_IRRELEVANT_KEYWORDS:
        if kw in text:
            # But allow if also has relevant keywords
            has_relevant = any(rel in text for rel in ZL_RELEVANT_KEYWORDS[:20])
            if not has_relevant:
                return False
    
    # Check for relevant keywords
    relevant_count = sum(1 for kw in ZL_RELEVANT_KEYWORDS if kw in text)
    return relevant_count >= 1

def get_canonical_bucket(raw_bucket: str) -> Optional[str]:
    """Map raw bucket to canonical Big-11."""
    if not raw_bucket:
        return None
    
    raw_lower = raw_bucket.lower().strip()
    
    # Direct match
    if raw_lower in BUCKET_CANONICAL_MAP:
        return BUCKET_CANONICAL_MAP[raw_lower]
    
    # Fuzzy match
    for key, canonical in BUCKET_CANONICAL_MAP.items():
        if key.lower() in raw_lower or raw_lower in key.lower():
            return canonical
    
    return None

# =============================================================================
# MAIN PROCESSING
# =============================================================================

def create_schemas(conn):
    """Verify required tables exist (no implicit DDL)."""
    required_tables = [
        ("silver", "news_scored_1d"),
        ("raw", "news_articles_1d"),
    ]

    with conn.cursor() as cur:
        for schema, table in required_tables:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
                """,
                (schema, table),
            )
            if not cur.fetchone():
                raise SystemExit(
                    f"Missing required table: {schema}.{table}. "
                    "Schema creation is blocked by policy; create via Prisma/migration with explicit approval."
                )

def fetch_all_articles(conn) -> List[Dict]:
    """Fetch all articles from raw layer."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                id,
                headline as title,
                content as body,
                source,
                bucket_name,
                published_at,
                is_trump_related
            FROM raw.news_articles_1d
            ORDER BY published_at
        """)
        return [dict(row) for row in cur.fetchall()]

def score_article(article: Dict) -> Dict:
    """Score a single article and prepare for insert."""
    # Run through existing classifier
    result = classify_article({
        "id": article["id"],
        "title": article.get("title") or "",
        "body": article.get("body") or "",
        "source": article.get("source") or "",
        "published_at": article.get("published_at"),
    })
    
    raw_bucket = article.get("bucket_name") or ""
    canonical = get_canonical_bucket(raw_bucket)
    title = article.get("title") or ""
    body = article.get("body") or ""
    
    # Check ZL relevance
    zl_relevant = is_zl_relevant(title, body)
    
    # Determine which specialists this affects
    affects = {
        "crush": False, "china": False, "fx": False, "fed": False,
        "tariff": False, "energy": False, "biofuel": False, "palm": False,
        "volatility": False, "substitutes": False, "trump_effect": False
    }
    
    # Primary bucket
    if canonical and canonical in affects:
        affects[canonical] = True
    
    # Check for trump_effect
    if article.get("is_trump_related") or "trump" in f"{title} {body}".lower():
        affects["trump_effect"] = True
    
    # Cross-bucket detection from matched categories
    for match in result.get("matches", []):
        bucket = match.get("alert_bucket", "")
        mapped = get_canonical_bucket(bucket)
        if mapped and mapped in affects:
            affects[mapped] = True
    
    convictions = [
        float(match.get("conviction"))
        for match in result.get("matches", [])
        if match.get("conviction") is not None
    ]
    sentiment_confidence = max(convictions) if convictions else None
    
    return {
        "raw_id": article["id"],
        "published_at": article.get("published_at"),
        "raw_bucket": raw_bucket,
        "canonical_bucket": canonical,
        "sentiment_score": result.get("impact_score", 0),
        "sentiment_direction": result.get("overall_direction", "uncertain"),
        "sentiment_confidence": sentiment_confidence,
        "is_zl_relevant": zl_relevant,
        "zl_impact_score": result.get("impact_score", 0) if zl_relevant else None,
        "affects_crush": affects["crush"],
        "affects_china": affects["china"],
        "affects_fx": affects["fx"],
        "affects_fed": affects["fed"],
        "affects_tariff": affects["tariff"],
        "affects_energy": affects["energy"],
        "affects_biofuel": affects["biofuel"],
        "affects_palm": affects["palm"],
        "affects_volatility": affects["volatility"],
        "affects_substitutes": affects["substitutes"],
        "affects_trump_effect": affects["trump_effect"],
        "headline": title[:500] if title else None,
        "source": article.get("source"),
        "word_count": len(f"{title} {body}".split()),
        "matched_categories": json.dumps(result.get("matches", [])),
    }

def insert_scored_articles(conn, scored: List[Dict]):
    """Bulk insert scored articles to silver layer."""
    if not scored:
        return
    
    columns = [
        "raw_id", "published_at", "raw_bucket", "canonical_bucket",
        "sentiment_score", "sentiment_direction", "sentiment_confidence",
        "is_zl_relevant", "zl_impact_score",
        "affects_crush", "affects_china", "affects_fx", "affects_fed",
        "affects_tariff", "affects_energy", "affects_biofuel", "affects_palm",
        "affects_volatility", "affects_substitutes", "affects_trump_effect",
        "headline", "source", "word_count", "matched_categories"
    ]
    
    values = [
        tuple(article[col] for col in columns)
        for article in scored
    ]
    
    insert_sql = f"""
        INSERT INTO features.news_sentiment_1d ({', '.join(columns)})
        VALUES %s
        ON CONFLICT (raw_id) DO UPDATE SET
            sentiment_score = EXCLUDED.sentiment_score,
            sentiment_direction = EXCLUDED.sentiment_direction,
            is_zl_relevant = EXCLUDED.is_zl_relevant,
            zl_impact_score = EXCLUDED.zl_impact_score,
            affects_trump_effect = EXCLUDED.affects_trump_effect,
            matched_categories = EXCLUDED.matched_categories,
            scored_at = NOW()
    """
    
    with conn.cursor() as cur:
        execute_values(cur, insert_sql, values, page_size=500)
    conn.commit()

def populate_trump_effect_training(conn):
    """Disabled: training.specialist_trump_effect_1d schema is not managed here."""
    raise SystemExit(
        "Disabled: this script does not populate training.specialist_trump_effect_1d. "
        "Use scripts/refresh_trump_effect_features.py or src/fusion/features/trump_effect.py instead."
    )

def update_raw_sentiment_scores(conn):
    """Backfill sentiment_score column in raw.news_articles_1d."""
    logger.info("Updating raw.news_articles_1d.sentiment_score...")
    
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE raw.news_articles_1d r
            SET sentiment_score = s.sentiment_score,
                zl_sentiment = s.zl_impact_score
            FROM features.news_sentiment_1d s
            WHERE r.id = s.raw_id
        """)
        updated = cur.rowcount
        conn.commit()
    
    logger.info(f"Updated {updated} rows in raw.news_articles_1d")

# =============================================================================
# MAIN
# =============================================================================

def main():
    logger.info("=" * 60)
    logger.info("ZINC-FUSION Sentiment Scoring Backfill")
    logger.info("=" * 60)
    
    conn = get_connection()
    logger.info("Connected to database")
    
    try:
        # 1. Create schemas
        create_schemas(conn)
        
        # 2. Fetch all articles
        logger.info("Fetching articles from raw.news_articles_1d...")
        articles = fetch_all_articles(conn)
        logger.info(f"Found {len(articles)} articles to process")
        
        # 3. Score all articles
        logger.info("Scoring articles...")
        scored = []
        trump_count = 0
        irrelevant_count = 0
        
        for i, article in enumerate(articles):
            result = score_article(article)
            scored.append(result)
            
            if result["affects_trump_effect"]:
                trump_count += 1
            if not result["is_zl_relevant"]:
                irrelevant_count += 1
            
            if (i + 1) % 1000 == 0:
                logger.info(f"Scored {i + 1}/{len(articles)} articles...")
        
        logger.info(f"Scoring complete: {trump_count} trump_effect, {irrelevant_count} marked irrelevant")
        
        # 4. Insert to silver layer
        logger.info("Inserting to features.news_sentiment_1d...")
        insert_scored_articles(conn, scored)
        logger.info(f"Inserted {len(scored)} scored articles")
        
        # 5. Backfill raw sentiment scores
        update_raw_sentiment_scores(conn)
        
        logger.info("=" * 60)
        logger.info("BACKFILL COMPLETE")
        logger.info("=" * 60)
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
