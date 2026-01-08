#!/usr/bin/env python3
"""
ZINC-FUSION Sentiment Scoring Backfill
======================================
Scores all news articles and populates silver/training layers.

Fixes:
1. sentiment_score column (100% NULL → scored)
2. training.specialist_trump_effect_1d (empty → populated)
3. China bucket contamination (adds is_zl_relevant filter)

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

def get_canonical_bucket(raw_bucket: str) -> str:
    """Map raw bucket to canonical Big-11."""
    if not raw_bucket:
        return "crush"  # Default
    
    raw_lower = raw_bucket.lower().strip()
    
    # Direct match
    if raw_lower in BUCKET_CANONICAL_MAP:
        return BUCKET_CANONICAL_MAP[raw_lower]
    
    # Fuzzy match
    for key, canonical in BUCKET_CANONICAL_MAP.items():
        if key.lower() in raw_lower or raw_lower in key.lower():
            return canonical
    
    return "crush"  # Default fallback

# =============================================================================
# SCHEMA CREATION
# =============================================================================

SILVER_NEWS_SCHEMA = """
CREATE TABLE IF NOT EXISTS silver.news_scored_1d (
    id SERIAL PRIMARY KEY,
    raw_id INTEGER REFERENCES raw.news_articles_1d(id),
    published_at TIMESTAMP,
    
    -- Original and normalized buckets
    raw_bucket VARCHAR(100),
    canonical_bucket VARCHAR(50),
    
    -- Sentiment scores
    sentiment_score DECIMAL(6,4),  -- -1 to +1 overall impact
    sentiment_direction VARCHAR(20),  -- bullish/bearish/uncertain
    sentiment_confidence DECIMAL(4,3),  -- 0 to 1
    
    -- ZL-specific
    is_zl_relevant BOOLEAN DEFAULT TRUE,
    zl_impact_score DECIMAL(6,4),
    
    -- Multi-bucket routing (article can affect multiple specialists)
    affects_crush BOOLEAN DEFAULT FALSE,
    affects_china BOOLEAN DEFAULT FALSE,
    affects_fx BOOLEAN DEFAULT FALSE,
    affects_fed BOOLEAN DEFAULT FALSE,
    affects_tariff BOOLEAN DEFAULT FALSE,
    affects_energy BOOLEAN DEFAULT FALSE,
    affects_biofuel BOOLEAN DEFAULT FALSE,
    affects_palm BOOLEAN DEFAULT FALSE,
    affects_volatility BOOLEAN DEFAULT FALSE,
    affects_substitutes BOOLEAN DEFAULT FALSE,
    affects_trump_effect BOOLEAN DEFAULT FALSE,
    
    -- Dashboard metadata
    headline VARCHAR(500),
    source VARCHAR(100),
    word_count INTEGER,
    matched_categories JSONB,
    
    -- Processing metadata
    scored_at TIMESTAMP DEFAULT NOW(),
    scoring_model VARCHAR(50) DEFAULT 'rule-based-v1',
    
    UNIQUE(raw_id)
);

CREATE INDEX IF NOT EXISTS idx_silver_news_published ON silver.news_scored_1d(published_at);
CREATE INDEX IF NOT EXISTS idx_silver_news_canonical ON silver.news_scored_1d(canonical_bucket);
CREATE INDEX IF NOT EXISTS idx_silver_news_trump ON silver.news_scored_1d(affects_trump_effect) WHERE affects_trump_effect = TRUE;
"""

TRUMP_EFFECT_SCHEMA = """
CREATE TABLE IF NOT EXISTS training.specialist_trump_effect_1d (
    id SERIAL PRIMARY KEY,
    as_of_date DATE NOT NULL,
    
    -- Daily aggregates
    article_count INTEGER DEFAULT 0,
    bullish_count INTEGER DEFAULT 0,
    bearish_count INTEGER DEFAULT 0,
    uncertain_count INTEGER DEFAULT 0,
    
    -- Sentiment metrics
    avg_sentiment DECIMAL(6,4),
    max_sentiment DECIMAL(6,4),
    min_sentiment DECIMAL(6,4),
    sentiment_std DECIMAL(6,4),
    
    -- Derived features
    sentiment_7d_ma DECIMAL(6,4),
    sentiment_momentum DECIMAL(6,4),  -- today vs 7d avg
    
    -- Metadata
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_trump_effect_date ON training.specialist_trump_effect_1d(as_of_date);
"""

# =============================================================================
# MAIN PROCESSING
# =============================================================================

def create_schemas(conn):
    """Create silver and training tables if not exist."""
    with conn.cursor() as cur:
        logger.info("Creating silver.news_scored_1d...")
        cur.execute(SILVER_NEWS_SCHEMA)
        
        logger.info("Creating training.specialist_trump_effect_1d...")
        cur.execute(TRUMP_EFFECT_SCHEMA)
        
        conn.commit()
    logger.info("Schemas created successfully")

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
    affects[canonical] = True
    
    # Check for trump_effect
    if article.get("is_trump_related") or "trump" in f"{title} {body}".lower():
        affects["trump_effect"] = True
    
    # Cross-bucket detection from matched categories
    for match in result.get("matches", []):
        bucket = match.get("alert_bucket", "")
        mapped = get_canonical_bucket(bucket)
        if mapped in affects:
            affects[mapped] = True
    
    return {
        "raw_id": article["id"],
        "published_at": article.get("published_at"),
        "raw_bucket": raw_bucket,
        "canonical_bucket": canonical,
        "sentiment_score": result.get("impact_score", 0),
        "sentiment_direction": result.get("overall_direction", "uncertain"),
        "sentiment_confidence": 0.5,  # Rule-based default
        "is_zl_relevant": zl_relevant,
        "zl_impact_score": result.get("impact_score", 0) if zl_relevant else 0,
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
        INSERT INTO silver.news_scored_1d ({', '.join(columns)})
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
    """Aggregate trump_effect articles into training features."""
    logger.info("Populating training.specialist_trump_effect_1d...")
    
    with conn.cursor() as cur:
        # Aggregate daily from silver layer
        cur.execute("""
            INSERT INTO training.specialist_trump_effect_1d (
                as_of_date, article_count, bullish_count, bearish_count, uncertain_count,
                avg_sentiment, max_sentiment, min_sentiment, sentiment_std
            )
            SELECT 
                DATE(published_at) as as_of_date,
                COUNT(*) as article_count,
                COUNT(*) FILTER (WHERE sentiment_direction = 'bullish') as bullish_count,
                COUNT(*) FILTER (WHERE sentiment_direction = 'bearish') as bearish_count,
                COUNT(*) FILTER (WHERE sentiment_direction = 'uncertain') as uncertain_count,
                AVG(sentiment_score) as avg_sentiment,
                MAX(sentiment_score) as max_sentiment,
                MIN(sentiment_score) as min_sentiment,
                STDDEV(sentiment_score) as sentiment_std
            FROM silver.news_scored_1d
            WHERE affects_trump_effect = TRUE
              AND is_zl_relevant = TRUE
            GROUP BY DATE(published_at)
            ON CONFLICT (as_of_date) DO UPDATE SET
                article_count = EXCLUDED.article_count,
                bullish_count = EXCLUDED.bullish_count,
                bearish_count = EXCLUDED.bearish_count,
                uncertain_count = EXCLUDED.uncertain_count,
                avg_sentiment = EXCLUDED.avg_sentiment,
                max_sentiment = EXCLUDED.max_sentiment,
                min_sentiment = EXCLUDED.min_sentiment,
                sentiment_std = EXCLUDED.sentiment_std,
                updated_at = NOW()
        """)
        
        # Calculate 7-day moving averages
        cur.execute("""
            UPDATE training.specialist_trump_effect_1d t
            SET 
                sentiment_7d_ma = sub.ma_7d,
                sentiment_momentum = t.avg_sentiment - sub.ma_7d
            FROM (
                SELECT 
                    as_of_date,
                    AVG(avg_sentiment) OVER (
                        ORDER BY as_of_date 
                        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                    ) as ma_7d
                FROM training.specialist_trump_effect_1d
            ) sub
            WHERE t.as_of_date = sub.as_of_date
        """)
        
        conn.commit()
    
    # Get count
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM training.specialist_trump_effect_1d")
        count = cur.fetchone()[0]
    
    logger.info(f"Trump effect training table populated: {count} rows")

def update_raw_sentiment_scores(conn):
    """Backfill sentiment_score column in raw.news_articles_1d."""
    logger.info("Updating raw.news_articles_1d.sentiment_score...")
    
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE raw.news_articles_1d r
            SET sentiment_score = s.sentiment_score,
                zl_sentiment = s.zl_impact_score
            FROM silver.news_scored_1d s
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
        logger.info("Inserting to silver.news_scored_1d...")
        insert_scored_articles(conn, scored)
        logger.info(f"Inserted {len(scored)} scored articles")
        
        # 5. Populate trump_effect training table
        populate_trump_effect_training(conn)
        
        # 6. Backfill raw sentiment scores
        update_raw_sentiment_scores(conn)
        
        logger.info("=" * 60)
        logger.info("BACKFILL COMPLETE")
        logger.info("=" * 60)
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
