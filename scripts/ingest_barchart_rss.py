#!/usr/bin/env python3
"""
Barchart RSS News Feed Ingestion with FinBERT Sentiment & Specialist Tagging

Ingests FREE RSS news feeds from Barchart into alt.news_1d.
Uses ProsusAI/finbert for financial sentiment analysis.
Tags articles to Big 11 specialists based on content.

FEEDS BY SPECIALIST:
- crush:       grain (RSS)
- china:       china (search)
- fx:          fx (financials)
- fed:         interest_rates, financials
- tariff:      tariff, legislative (search)
- energy:      energy (RSS)
- biofuel:     (covered by energy)
- palm:        (covered by commodities)
- volatility:  options_news, vix (search)
- substitutes: softs (RSS)
- trump_effect: trump (search)

Core Feeds (RSS):
- commodities:     https://www.barchart.com/news/rss/commodities
- grain:           https://www.barchart.com/news/rss/commodities/grain
- softs:           https://www.barchart.com/news/rss/commodities/softs
- energy:          https://www.barchart.com/news/rss/commodities/energy
- metals:          https://www.barchart.com/news/rss/commodities/metals

Financial Feeds (RSS):
- financials:      https://www.barchart.com/news/rss/financials
- interest_rates:  https://www.barchart.com/news/rss/financials/interest-rates
- fx:              https://www.barchart.com/news/rss/financials/fx
- etfs:            https://www.barchart.com/news/rss/etfs

Options/Volatility Feeds:
- options_news:    https://www.barchart.com/news/rss/options-news
- vix:             https://www.barchart.com/news/rss/search/any/vix

Search Feeds (by topic):
- china:           https://www.barchart.com/news/rss/search/any/china
- trump:           https://www.barchart.com/news/rss/search/any/trump
- tariff:          https://www.barchart.com/news/rss/search/any/tariff
- legislative:     https://www.barchart.com/news/rss/search/any/legislative
- lobbying:        https://www.barchart.com/news/rss/search/any/lobbying

Usage:
    python scripts/ingest_barchart_rss.py                      # All feeds
    python scripts/ingest_barchart_rss.py --feeds grain        # Just grain
    python scripts/ingest_barchart_rss.py --feeds china trump  # China + Trump
    python scripts/ingest_barchart_rss.py --dry-run            # Test without DB
    python scripts/ingest_barchart_rss.py --no-sentiment       # Skip FinBERT (faster)
"""

import argparse
import hashlib
import logging
import os
import ssl
import certifi
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional, Tuple

import feedparser
import psycopg2
from psycopg2.extras import execute_values

# Fix SSL certificate verification on macOS
ssl._create_default_https_context = lambda: ssl.create_default_context(
    cafile=certifi.where()
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ============================================================
# FinBERT Sentiment Analysis (HuggingFace)
# ============================================================

FINBERT_MODEL = None
FINBERT_TOKENIZER = None


def load_finbert():
    """Load FinBERT model for financial sentiment analysis."""
    global FINBERT_MODEL, FINBERT_TOKENIZER

    if FINBERT_MODEL is not None:
        return True

    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch

        logger.info("🤖 Loading FinBERT sentiment model (ProsusAI/finbert)...")
        FINBERT_TOKENIZER = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        FINBERT_MODEL = AutoModelForSequenceClassification.from_pretrained(
            "ProsusAI/finbert"
        )
        FINBERT_MODEL.eval()

        # Use MPS on Apple Silicon if available
        if torch.backends.mps.is_available():
            FINBERT_MODEL = FINBERT_MODEL.to("mps")
            logger.info("  ✅ FinBERT loaded on Apple MPS (GPU)")
        else:
            logger.info("  ✅ FinBERT loaded on CPU")

        return True
    except Exception as e:
        logger.warning(f"  ⚠️ Could not load FinBERT: {e}")
        return False


def finbert_sentiment(text: str) -> Tuple[float, str]:
    """
    Analyze sentiment using FinBERT.

    Returns:
        (score, label) where score is -1 to +1 and label is positive/negative/neutral
    """
    global FINBERT_MODEL, FINBERT_TOKENIZER

    if FINBERT_MODEL is None:
        return 0.0, "neutral"

    try:
        import torch

        # Truncate to model max length
        inputs = FINBERT_TOKENIZER(
            text[:512], return_tensors="pt", truncation=True, max_length=512
        )

        # Move to same device as model
        if next(FINBERT_MODEL.parameters()).device.type == "mps":
            inputs = {k: v.to("mps") for k, v in inputs.items()}

        with torch.no_grad():
            outputs = FINBERT_MODEL(**inputs)
            probs = torch.softmax(outputs.logits, dim=1)

        # FinBERT labels: positive, negative, neutral
        labels = ["positive", "negative", "neutral"]
        probs_np = probs.cpu().numpy()[0]

        # Convert to score: positive=+1, negative=-1, neutral=0
        # Weighted score: positive_prob - negative_prob
        score = float(probs_np[0] - probs_np[1])
        label = labels[probs_np.argmax()]

        return score, label

    except Exception as e:
        logger.warning(f"  FinBERT error: {e}")
        return 0.0, "neutral"


# ============================================================
# Specialist Tagging (Big 11) - Uses shared module
# ============================================================

# Import from consolidated tagging module (src/fusion/tagging/)
import sys
from pathlib import Path

# Add src to path if running as script
_src_path = Path(__file__).parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from fusion.tagging import classify_specialists

# Alias for backward compatibility
tag_specialists = classify_specialists


# ============================================================
# RSS Feed Configuration
# ============================================================

BARCHART_RSS_FEEDS = {
    # ============================================================
    # CORE COMMODITY FEEDS (RSS) ✅ WORKING
    # ============================================================
    "commodities": {
        "url": "https://www.barchart.com/news/rss/commodities",
        "description": "All Commodities News",
        "tags": ["commodities", "energy", "metals", "agriculture"],
        "specialist": "general",
    },
    "grain": {
        "url": "https://www.barchart.com/news/rss/commodities/grain",
        "description": "Grain & Oilseed News",
        "tags": ["grain", "soybeans", "corn", "wheat", "soybean_oil"],
        "specialist": "crush",
    },
    "softs": {
        "url": "https://www.barchart.com/news/rss/commodities/softs",
        "description": "Soft Commodities (Sugar, Coffee, Cocoa, Cotton)",
        "tags": ["softs", "sugar", "coffee", "cocoa", "cotton"],
        "specialist": "substitutes",
    },
    "energy": {
        "url": "https://www.barchart.com/news/rss/commodities/energy",
        "description": "Energy Commodities (Oil, Gas)",
        "tags": ["energy", "crude_oil", "natural_gas", "biodiesel"],
        "specialist": "energy",
    },
    "metals": {
        "url": "https://www.barchart.com/news/rss/commodities/metals",
        "description": "Metals Commodities",
        "tags": ["metals", "gold", "silver", "copper"],
        "specialist": "general",
    },
    # ============================================================
    # FINANCIAL/MACRO FEEDS (RSS) ✅ WORKING
    # ============================================================
    "financials": {
        "url": "https://www.barchart.com/news/rss/financials",
        "description": "Macro Economic/Financial News",
        "tags": ["macro", "economic", "markets", "financial"],
        "specialist": "fed",
    },
    "interest_rates": {
        "url": "https://www.barchart.com/news/rss/financials/interest-rates",
        "description": "Fed & Interest Rate News",
        "tags": ["fed", "rates", "fomc", "treasury", "bonds"],
        "specialist": "fed",
    },
    "fx": {
        "url": "https://www.barchart.com/news/rss/financials/fx",
        "description": "FX/Currency News",
        "tags": ["fx", "currency", "dollar", "euro", "yuan"],
        "specialist": "fx",
    },
    "etfs": {
        "url": "https://www.barchart.com/news/rss/etfs",
        "description": "ETF News (Neural Hunter)",
        "tags": ["etf", "funds", "flows", "positioning"],
        "specialist": "general",
    },
    # ============================================================
    # OPTIONS & VOLATILITY FEEDS (RSS) ✅ WORKING
    # ============================================================
    "options_news": {
        "url": "https://www.barchart.com/news/rss/options-news",
        "description": "Options Activity News",
        "tags": ["options", "volatility", "iv", "flow"],
        "specialist": "volatility",
    },
    # ============================================================
    # SEARCH FEEDS (Require API - may not work with RSS)
    # These URLs are for reference when API access is available
    # ============================================================
    # "china": {
    #     "url": "https://www.barchart.com/news/search/any/china",
    #     "description": "China News",
    #     "tags": ["china", "beijing", "imports", "demand"],
    #     "specialist": "china",
    #     "requires_api": True,
    # },
    # "trump": {
    #     "url": "https://www.barchart.com/news/search/any/trump",
    #     "description": "Trump Effect News",
    #     "tags": ["trump", "white_house", "policy", "executive_order"],
    #     "specialist": "trump_effect",
    #     "requires_api": True,
    # },
    # "tariff": {
    #     "url": "https://www.barchart.com/news/search/any/tariff",
    #     "description": "Tariff/Trade War News",
    #     "tags": ["tariff", "trade_war", "duties", "trade_policy"],
    #     "specialist": "tariff",
    #     "requires_api": True,
    # },
    # "legislative": {
    #     "url": "https://www.barchart.com/news/search/any/legislative",
    #     "description": "Legislative/Policy News",
    #     "tags": ["legislative", "congress", "bill", "policy"],
    #     "specialist": "tariff",
    #     "requires_api": True,
    # },
    # "lobbying": {
    #     "url": "https://www.barchart.com/news/search/any/lobbying",
    #     "description": "Lobbying/Political News (Neural Hunter)",
    #     "tags": ["lobbying", "political", "influence", "regulation"],
    #     "specialist": "general",
    #     "requires_api": True,
    # },
    # "vix": {
    #     "url": "https://www.barchart.com/news/search/any/vix",
    #     "description": "VIX/Volatility News",
    #     "tags": ["vix", "volatility", "fear", "uncertainty"],
    #     "specialist": "volatility",
    #     "requires_api": True,
    # },
}

# Keywords to identify soybean oil relevance
SOY_OIL_KEYWORDS = [
    "soybean oil",
    "soy oil",
    "bean oil",
    "soyo",
    "soyoil",
    "biodiesel",
    "renewable fuel",
    "rfs",
    "rvo",
    "crush",
    "crushing",
    "crusher",
    "zl",
    "soyb",
]

SOYBEAN_KEYWORDS = [
    "soybean",
    "soybeans",
    "soy",
    "beans",
    "brazil soy",
    "argentina soy",
    "us soy",
]


def calculate_relevance_score(title: str, description: str) -> float:
    """
    Calculate relevance score for ZL/soybean oil.

    Returns:
        float: 0.0 to 1.0 relevance score
    """
    text = f"{title} {description}".lower()
    score = 0.0

    # Direct soy oil mentions (highest weight)
    for kw in SOY_OIL_KEYWORDS:
        if kw in text:
            score += 0.4
            break

    # Soybean mentions (medium weight)
    for kw in SOYBEAN_KEYWORDS:
        if kw in text:
            score += 0.3
            break

    # General ag commodity context (lower weight)
    ag_keywords = ["corn", "wheat", "grain", "usda", "export", "wasde"]
    for kw in ag_keywords:
        if kw in text:
            score += 0.1
            break

    # Energy/biofuel context
    energy_keywords = ["biodiesel", "ethanol", "renewable", "epa", "rin"]
    for kw in energy_keywords:
        if kw in text:
            score += 0.2
            break

    return min(score, 1.0)


def generate_article_id(url: str) -> str:
    """Generate deterministic article ID from URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def parse_pub_date(date_str: str) -> Optional[datetime]:
    """Parse RSS pubDate to datetime."""
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return datetime.now(timezone.utc)


def fetch_feed(feed_name: str, use_sentiment: bool = True) -> list[dict]:
    """
    Fetch and parse RSS feed with FinBERT sentiment.

    Returns:
        List of article dictionaries
    """
    feed_config = BARCHART_RSS_FEEDS.get(feed_name)
    if not feed_config:
        logger.error(f"Unknown feed: {feed_name}")
        return []

    url = feed_config["url"]
    logger.info(f"Fetching {feed_name} feed: {url}")

    feed = feedparser.parse(url)

    if feed.bozo:
        logger.warning(f"Feed parse warning: {feed.bozo_exception}")

    articles = []
    for i, entry in enumerate(feed.entries):
        # Extract fields
        title = entry.get("title", "")
        description = entry.get("description", "")
        link = entry.get("link", "")
        author = entry.get("author", "Barchart")
        pub_date = parse_pub_date(entry.get("published", ""))

        # Calculate relevance
        relevance = calculate_relevance_score(title, description)

        # Tag specialists
        full_text = f"{title} {description}"
        specialists = tag_specialists(full_text)

        # FinBERT sentiment (if enabled)
        sentiment_score = 0.0
        sentiment_label = "neutral"
        if use_sentiment:
            sentiment_score, sentiment_label = finbert_sentiment(full_text)

        # Build article record
        article = {
            "article_id": generate_article_id(link),
            "source": "barchart_rss",
            "source_feed": feed_name,
            "title": title,
            "description": description[:2000] if description else None,
            "url": link,
            "author": author,
            "published_at": pub_date,
            "ingested_at": datetime.now(timezone.utc),
            "relevance_score": relevance,
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "specialists": specialists,
            "tags": feed_config["tags"],
        }
        articles.append(article)

    # Summary
    if use_sentiment:
        avg_sent = (
            sum(a["sentiment_score"] for a in articles) / len(articles)
            if articles
            else 0
        )
        logger.info(
            f"  Fetched {len(articles)} articles (avg sentiment: {avg_sent:+.2f})"
        )
    else:
        logger.info(f"  Fetched {len(articles)} articles from {feed_name}")

    return articles


def ensure_table_exists(conn):
    """Verify alt.news_1d exists (it should already exist)."""
    # Table already exists with established schema - just verify
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'raw' AND table_name = 'news_articles_event'
            )
        """
        )
        exists = cur.fetchone()[0]

    if not exists:
        logger.error("❌ Table alt.news_1d does not exist!")
        raise RuntimeError("Missing required table: alt.news_1d")

    logger.info("✅ Verified alt.news_1d table exists")


def write_articles(conn, articles: list[dict], dry_run: bool = False) -> int:
    """
    Write articles to database using existing schema.

    Returns:
        Number of articles inserted
    """
    if not articles:
        return 0

    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(articles)} articles")
        for a in articles[:5]:
            sent_icon = (
                "📈"
                if a["sentiment_score"] > 0.1
                else ("📉" if a["sentiment_score"] < -0.1 else "➡️")
            )
            logger.info(
                f"    {sent_icon} [{a['sentiment_score']:+.2f}] [{a['relevance_score']:.2f}] {a['title'][:50]}..."
            )
            logger.info(f"       Specialists: {a['specialists']}")
        return 0

    # Use existing table schema: headline, content, source, published_at,
    # source_url, specialist_tags, event_date, sentiment_score, quality_score
    insert_sql = """
    INSERT INTO alt.news_1d 
        (headline, content, source, published_at, source_url, 
         specialist_tags, event_date, sentiment_score, quality_score, raw_payload)
    VALUES %s
    ON CONFLICT DO NOTHING
    """

    values = [
        (
            a["title"][:500],  # headline
            a["description"][:2000] if a["description"] else None,  # content
            f"barchart_rss_{a['source_feed']}",  # source
            a["published_at"],  # published_at
            a["url"],  # source_url
            a["specialists"],  # specialist_tags (tagged to Big 11!)
            (
                a["published_at"].date()
                if a["published_at"]
                else datetime.now(timezone.utc).date()
            ),  # event_date
            a["sentiment_score"],  # sentiment_score from FinBERT
            a["relevance_score"],  # quality_score (relevance as proxy)
            json.dumps(
                {
                    "author": a["author"],
                    "feed": a["source_feed"],
                    "sentiment_label": a.get("sentiment_label", "neutral"),
                    "original_tags": a["tags"],
                }
            ),  # raw_payload
        )
        for a in articles
    ]

    with conn.cursor() as cur:
        execute_values(cur, insert_sql, values)
    conn.commit()

    return len(articles)


def main():
    parser = argparse.ArgumentParser(description="Ingest Barchart RSS news feeds")
    parser.add_argument(
        "--feeds",
        nargs="+",
        choices=list(BARCHART_RSS_FEEDS.keys()),
        default=list(BARCHART_RSS_FEEDS.keys()),
        help="Feeds to ingest (default: all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing to database"
    )
    parser.add_argument(
        "--show-relevant",
        action="store_true",
        help="Show only ZL-relevant articles (relevance > 0.3)",
    )
    parser.add_argument(
        "--no-sentiment",
        action="store_true",
        help="Skip FinBERT sentiment analysis (faster)",
    )
    args = parser.parse_args()

    use_sentiment = not args.no_sentiment

    logger.info("=" * 60)
    logger.info("BARCHART RSS NEWS INGESTION")
    logger.info("=" * 60)
    logger.info(f"Feeds: {args.feeds}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"FinBERT sentiment: {use_sentiment}")
    logger.info("=" * 60)

    # Load FinBERT if sentiment enabled
    if use_sentiment:
        if not load_finbert():
            logger.warning("Continuing without sentiment analysis")
            use_sentiment = False

    # Connect to database
    database_url = os.getenv("DATABASE_URL")
    if not database_url and not args.dry_run:
        logger.error("DATABASE_URL not set. Use --dry-run or set env var.")
        return 1

    conn = None
    if not args.dry_run:
        conn = psycopg2.connect(database_url)
        ensure_table_exists(conn)

    total_articles = 0
    total_relevant = 0
    sentiment_sum = 0.0

    for feed_name in args.feeds:
        articles = fetch_feed(feed_name, use_sentiment=use_sentiment)

        if args.show_relevant:
            relevant = [a for a in articles if a["relevance_score"] > 0.3]
            logger.info(f"\n📰 {feed_name}: {len(relevant)} ZL-relevant articles:")
            for a in relevant:
                sent_icon = (
                    "📈"
                    if a["sentiment_score"] > 0.1
                    else ("📉" if a["sentiment_score"] < -0.1 else "➡️")
                )
                logger.info(
                    f"  {sent_icon} [{a['sentiment_score']:+.2f}] {a['title'][:60]}..."
                )
                logger.info(f"     → Specialists: {a['specialists']}")
            total_relevant += len(relevant)

        if conn:
            inserted = write_articles(conn, articles, dry_run=args.dry_run)
            logger.info(f"  Inserted/updated {inserted} articles")

        total_articles += len(articles)
        sentiment_sum += sum(a["sentiment_score"] for a in articles)

    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total articles fetched: {total_articles}")
    if total_articles > 0:
        logger.info(f"Average sentiment: {sentiment_sum / total_articles:+.3f}")
    if args.show_relevant:
        logger.info(f"ZL-relevant articles: {total_relevant}")

    if conn:
        # Show recent articles with sentiment
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*), 
                       AVG(sentiment_score)::numeric(5,3),
                       MAX(published_at)::text
                FROM alt.news_1d
                WHERE source LIKE 'barchart_rss%'
            """
            )
            count, avg_sent, latest = cur.fetchone()
            logger.info(f"Total Barchart RSS articles in DB: {count}")
            logger.info(f"DB avg sentiment: {avg_sent}")
            logger.info(f"Latest article: {latest}")
        conn.close()

    logger.info("✅ Done!")
    return 0


if __name__ == "__main__":
    exit(main())
