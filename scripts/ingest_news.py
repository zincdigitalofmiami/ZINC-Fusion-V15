#!/usr/bin/env python3
"""
News Ingestion & Classification Pipeline
=========================================
Fetches news from Yahoo Finance (primary) and Polygon (backup),
classifies articles into specialist buckets, and stores to Prisma.

Specialist Buckets:
- crush: US soybean crushing, NOPA, domestic processing
- china: China demand, imports, policy, Sinograin, COFCO
- fx: Currency moves, BRL, ARS, CNY, USD
- fed: Fed policy, rates, monetary policy
- tariff: Trade disputes, tariffs, quotas, WTO
- energy: Oil prices, natural gas, energy costs
- biofuel: RFS, biodiesel mandates, RINs, SAF, LCFS
- palm: Palm oil, Indonesia, Malaysia, MPOB
- volatility: VIX, market stress, risk-off
- substitutes: Sunflower, rapeseed, other veg oils

Usage:
    python scripts/ingest_news.py
    python scripts/ingest_news.py --dry-run
"""

import os
import sys
import re
import logging
import argparse
import hashlib
import unicodedata
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import requests
import psycopg2
from psycopg2.extras import execute_batch, Json
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    logger.error("DATABASE_URL not set")
    sys.exit(1)

# =============================================================================
# SPECIALIST BUCKET CLASSIFICATION RULES
# =============================================================================

# Map news categories to specialist buckets
CATEGORY_TO_BUCKET = {
    "china_demand_levers": "china",
    "argentina_policy_fx": "fx",
    "brazil_policy_infra": "substitutes",  # Brazil soy competes
    "us_policy": "tariff",
    "biofuels_policy": "biofuel",
    "palm_oil_geopolitics": "palm",
    "black_sea_vegoils": "substitutes",
    "global_chokepoints_freight": "energy",  # Freight/logistics
    "fertilizer_energy_sanctions": "energy",
    "animal_disease_shocks": "crush",  # Affects meal demand
    "trade_disputes_quotas": "tariff",
    "esg_deforestation_rules": "palm",
    "labor_civil_unrest": "crush",
    "cyber_infrastructure_surprises": "volatility",
    "regulatory_approvals": "tariff",
    "macro_fx": "fx",
}

# Classification rules by category
CLASSIFICATION_RULES = {
    "china_demand_levers": {
        "bucket": "china",
        "keywords": ["sinograin", "cofco", "ndrc soybean", "state reserves",
                     "crush margins", "dalian", "china import", "chinese demand"],
        "bullish": ["reserve stockpiles rebuild", "import quota boost",
                    "crush margin subsidies"],
        "bearish": ["biosecurity import slowdowns", "tighter import licenses",
                    "state reserve releases"],
    },
    "biofuels_policy": {
        "bucket": "biofuel",
        "keywords": ["b40 indonesia", "renovabio", "cbio", "lcfs", "saf",
                     "epa rvo", "biodiesel", "renewable diesel", "rin price",
                     "blending mandate", "45z"],
        "bullish": ["b35", "b40", "biodiesel blend hikes", "lcfs", "saf", "45z"],
        "bearish": ["iluc", "weaker lcfs credit prices", "cap on crop-based"],
    },
    "palm_oil_geopolitics": {
        "bucket": "palm",
        "keywords": ["cpo export levy", "dmo", "mpob", "india edible oil duty",
                     "palm oil", "indonesia palm", "malaysia palm"],
        "bullish": ["export levies", "export bans", "labor shortages",
                    "esg import hurdles"],
        "bearish": ["levy cuts", "export liberalization", "bumper output",
                    "india import duty cuts"],
    },
    "us_crush": {
        "bucket": "crush",
        "keywords": ["nopa", "crush report", "soybean crush", "crush capacity",
                     "crush margins", "soy meal", "soybean meal"],
        "bullish": ["crush margins up", "strong crush demand", "capacity expansion"],
        "bearish": ["crush margins down", "weak meal demand", "plant closures"],
    },
    "trade_tariff": {
        "bucket": "tariff",
        "keywords": ["tariff", "trade war", "section 301", "wto", "antidumping",
                     "cvd", "trade dispute", "retaliatory", "ustr"],
        "bullish": ["tariff reduction", "trade deal", "exemption"],
        "bearish": ["new tariffs", "retaliation", "trade escalation"],
    },
    "fed_monetary": {
        "bucket": "fed",
        "keywords": ["federal reserve", "fed", "fomc", "interest rate",
                     "powell", "monetary policy", "rate hike", "rate cut"],
        "bullish": ["rate cut", "dovish", "pause"],
        "bearish": ["rate hike", "hawkish", "tightening"],
    },
    "fx_currency": {
        "bucket": "fx",
        "keywords": ["usd", "dollar", "brl", "real", "ars", "peso", "cny",
                     "yuan", "currency", "exchange rate", "dxy"],
        "bullish": ["dollar weakness", "brl strength", "ars strength"],
        "bearish": ["dollar strength", "em selloff", "currency crisis"],
    },
    "energy_oil": {
        "bucket": "energy",
        "keywords": ["crude oil", "wti", "brent", "opec", "natural gas",
                     "energy prices", "oil price", "gasoline"],
        "bullish": ["oil rally", "opec cut", "supply disruption"],
        "bearish": ["oil crash", "demand destruction", "oversupply"],
    },
    "volatility_risk": {
        "bucket": "volatility",
        "keywords": ["vix", "volatility", "risk off", "flight to safety",
                     "market crash", "selloff", "panic"],
        "bullish": ["vix spike", "risk off"],  # Bullish for hedges
        "bearish": ["calm markets", "low vol"],
    },
    "substitutes_oils": {
        "bucket": "substitutes",
        "keywords": ["sunflower oil", "rapeseed", "canola", "black sea",
                     "ukraine", "argentina soy", "brazil soy"],
        "bullish": ["sunflower shortage", "black sea disruption"],
        "bearish": ["bumper sunflower", "argentina recovery"],
    },
}

# Yahoo Finance RSS feeds
YAHOO_RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ZL=F&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ZS=F&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ZM=F&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=CL=F&region=US&lang=en-US",
]


def normalize_text(text: str) -> str:
    """Normalize text for matching."""
    if not text:
        return ""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()
    return f" {cleaned} "


def classify_article(title: str, summary: str) -> Dict[str, Any]:
    """
    Classify article into specialist buckets.

    Returns:
        {
            "buckets": ["china", "tariff"],  # Matched buckets
            "direction": "bullish",  # Overall direction
            "impact_score": 0.65,  # -1 to +1
            "categories": [  # Detailed matches
                {"category": "china_demand_levers", "bucket": "china", ...}
            ]
        }
    """
    text = normalize_text(f"{title} {summary}")

    matches = []
    buckets_hit = set()
    total_score = 0.0

    for category, rules in CLASSIFICATION_RULES.items():
        # Check keywords
        keyword_hits = []
        for kw in rules.get("keywords", []):
            if normalize_text(kw).strip() in text:
                keyword_hits.append(kw)

        if not keyword_hits:
            continue

        # Check direction
        bullish_hits = []
        for term in rules.get("bullish", []):
            if normalize_text(term).strip() in text:
                bullish_hits.append(term)

        bearish_hits = []
        for term in rules.get("bearish", []):
            if normalize_text(term).strip() in text:
                bearish_hits.append(term)

        # Determine direction
        if bullish_hits and bearish_hits:
            direction = "mixed"
            impact = 0.0
        elif bullish_hits:
            direction = "bullish"
            impact = 0.3 + 0.1 * min(len(bullish_hits), 3)
        elif bearish_hits:
            direction = "bearish"
            impact = -(0.3 + 0.1 * min(len(bearish_hits), 3))
        else:
            direction = "neutral"
            impact = 0.0

        bucket = rules["bucket"]
        buckets_hit.add(bucket)
        total_score += impact

        matches.append({
            "category": category,
            "bucket": bucket,
            "direction": direction,
            "impact": round(impact, 3),
            "keyword_hits": keyword_hits,
            "bullish_hits": bullish_hits,
            "bearish_hits": bearish_hits,
        })

    # Overall direction
    if total_score > 0.1:
        overall_direction = "bullish"
    elif total_score < -0.1:
        overall_direction = "bearish"
    else:
        overall_direction = "neutral"

    return {
        "buckets": sorted(buckets_hit),
        "direction": overall_direction,
        "impact_score": round(total_score, 3),
        "categories": matches,
    }


class NewsIngester:
    """Ingest and classify news into Prisma."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.pg = psycopg2.connect(DATABASE_URL)
        self._ensure_tables()
        logger.info("Connected to Prisma Postgres")

    def _ensure_tables(self):
        """Create news tables if they don't exist."""
        cur = self.pg.cursor()

        # Raw news articles
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raw_news_articles (
                id SERIAL PRIMARY KEY,
                article_id VARCHAR(64) UNIQUE,
                title TEXT NOT NULL,
                summary TEXT,
                source VARCHAR(100),
                author VARCHAR(200),
                url TEXT,
                published_at TIMESTAMP,
                symbols TEXT[],
                keywords TEXT[],
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_news_published ON raw_news_articles(published_at);
            CREATE INDEX IF NOT EXISTS idx_news_source ON raw_news_articles(source);
        """)

        # Parsed/classified news with specialist routing
        cur.execute("""
            CREATE TABLE IF NOT EXISTS parsed_news (
                id SERIAL PRIMARY KEY,
                article_id VARCHAR(64) REFERENCES raw_news_articles(article_id),
                buckets TEXT[] NOT NULL,
                direction VARCHAR(20),
                impact_score FLOAT,
                classification JSONB,
                processed_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(article_id)
            );
            CREATE INDEX IF NOT EXISTS idx_parsed_buckets ON parsed_news USING GIN(buckets);
            CREATE INDEX IF NOT EXISTS idx_parsed_direction ON parsed_news(direction);
            CREATE INDEX IF NOT EXISTS idx_parsed_impact ON parsed_news(impact_score);
        """)

        # News sentiment by bucket (daily aggregates for specialists)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS news_sentiment_daily (
                id SERIAL PRIMARY KEY,
                as_of_date DATE NOT NULL,
                bucket VARCHAR(50) NOT NULL,
                article_count INT,
                bullish_count INT,
                bearish_count INT,
                neutral_count INT,
                avg_impact FLOAT,
                net_sentiment FLOAT,
                top_keywords JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(as_of_date, bucket)
            );
            CREATE INDEX IF NOT EXISTS idx_sentiment_date ON news_sentiment_daily(as_of_date);
            CREATE INDEX IF NOT EXISTS idx_sentiment_bucket ON news_sentiment_daily(bucket);
        """)

        self.pg.commit()
        cur.close()

    def _generate_article_id(self, title: str, url: str) -> str:
        """Generate unique article ID."""
        content = f"{title}:{url}"
        return hashlib.sha256(content.encode()).hexdigest()[:64]

    def fetch_yahoo_rss(self) -> List[Dict[str, Any]]:
        """Fetch news from Yahoo Finance RSS feeds."""
        articles = []

        try:
            import xml.etree.ElementTree as ET
        except ImportError:
            logger.error("xml.etree not available")
            return []

        for feed_url in YAHOO_RSS_FEEDS:
            try:
                resp = requests.get(feed_url, timeout=15)
                resp.raise_for_status()

                root = ET.fromstring(resp.content)
                channel = root.find('channel')

                if channel is None:
                    continue

                for item in channel.findall('item'):
                    title = item.findtext('title', '')
                    link = item.findtext('link', '')
                    description = item.findtext('description', '')
                    pub_date = item.findtext('pubDate', '')

                    if not title:
                        continue

                    published_at = None
                    if pub_date:
                        try:
                            published_at = datetime.strptime(
                                pub_date.replace(' +0000', '').replace(' GMT', ''),
                                '%a, %d %b %Y %H:%M:%S'
                            )
                        except ValueError:
                            published_at = datetime.now()

                    articles.append({
                        'title': title,
                        'summary': description,
                        'url': link,
                        'source': 'yahoo_finance',
                        'published_at': published_at,
                    })

            except Exception as e:
                logger.warning(f"Yahoo RSS error: {e}")
                continue

        logger.info(f"  Yahoo: fetched {len(articles)} articles")
        return articles

    def fetch_polygon_news(self) -> List[Dict[str, Any]]:
        """Fetch news from Polygon.io API."""
        if not POLYGON_API_KEY:
            logger.warning("POLYGON_API_KEY not set, skipping")
            return []

        articles = []
        tickers = ["ZL", "ZS", "ZM", "CL"]

        for ticker in tickers:
            try:
                url = "https://api.polygon.io/v2/reference/news"
                params = {
                    "ticker": ticker,
                    "limit": 20,
                    "order": "desc",
                    "sort": "published_utc",
                    "apiKey": POLYGON_API_KEY,
                }

                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("results", []):
                    published_at = None
                    if item.get("published_utc"):
                        try:
                            published_at = datetime.fromisoformat(
                                item["published_utc"].replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                        except ValueError:
                            published_at = datetime.now()

                    articles.append({
                        'title': item.get('title', ''),
                        'summary': item.get('description', ''),
                        'url': item.get('article_url', ''),
                        'source': 'polygon',
                        'author': item.get('author', ''),
                        'published_at': published_at,
                        'symbols': item.get('tickers', []),
                        'keywords': item.get('keywords', []),
                    })

            except Exception as e:
                logger.warning(f"Polygon error for {ticker}: {e}")
                continue

        logger.info(f"  Polygon: fetched {len(articles)} articles")
        return articles

    def store_and_classify(self, articles: List[Dict[str, Any]]) -> Dict[str, int]:
        """Store raw articles and classify into buckets."""
        if not articles:
            return {"raw": 0, "classified": 0}

        if self.dry_run:
            # Still classify for logging
            for article in articles[:5]:
                result = classify_article(
                    article.get('title', ''),
                    article.get('summary', '')
                )
                logger.info(f"  [DRY RUN] {article.get('title', '')[:50]}...")
                logger.info(f"    Buckets: {result['buckets']}, Direction: {result['direction']}")
            return {"raw": 0, "classified": 0}

        cur = self.pg.cursor()
        raw_stored = 0
        classified = 0

        for article in articles:
            try:
                article_id = self._generate_article_id(
                    article.get('title', ''),
                    article.get('url', '')
                )

                # Insert raw article
                cur.execute("""
                    INSERT INTO raw_news_articles (
                        article_id, title, summary, source, author, url,
                        published_at, symbols, keywords
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (article_id) DO NOTHING
                    RETURNING id
                """, (
                    article_id,
                    article.get('title', '')[:500],
                    article.get('summary', '')[:2000] if article.get('summary') else None,
                    article.get('source', 'unknown'),
                    article.get('author', '')[:200] if article.get('author') else None,
                    article.get('url', ''),
                    article.get('published_at'),
                    article.get('symbols', []),
                    article.get('keywords', []),
                ))

                result = cur.fetchone()
                if result:
                    raw_stored += 1

                    # Classify the article
                    classification = classify_article(
                        article.get('title', ''),
                        article.get('summary', '')
                    )

                    # Store classification
                    if classification['buckets']:
                        cur.execute("""
                            INSERT INTO parsed_news (
                                article_id, buckets, direction, impact_score, classification
                            ) VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (article_id) DO UPDATE SET
                                buckets = EXCLUDED.buckets,
                                direction = EXCLUDED.direction,
                                impact_score = EXCLUDED.impact_score,
                                classification = EXCLUDED.classification,
                                processed_at = NOW()
                        """, (
                            article_id,
                            classification['buckets'],
                            classification['direction'],
                            classification['impact_score'],
                            Json(classification),
                        ))
                        classified += 1

            except Exception as e:
                logger.error(f"Error storing article: {e}")
                continue

        self.pg.commit()
        cur.close()

        return {"raw": raw_stored, "classified": classified}

    def update_daily_sentiment(self):
        """Aggregate daily sentiment by bucket for specialists."""
        if self.dry_run:
            logger.info("[DRY RUN] Would update daily sentiment aggregates")
            return

        cur = self.pg.cursor()
        today = datetime.now().date()

        # Get today's classified articles by bucket
        cur.execute("""
            SELECT
                unnest(p.buckets) as bucket,
                p.direction,
                p.impact_score
            FROM parsed_news p
            JOIN raw_news_articles r ON p.article_id = r.article_id
            WHERE r.published_at::date = %s
        """, [today])

        bucket_stats = {}
        for row in cur.fetchall():
            bucket, direction, impact = row
            if bucket not in bucket_stats:
                bucket_stats[bucket] = {
                    "count": 0, "bullish": 0, "bearish": 0, "neutral": 0,
                    "total_impact": 0.0
                }
            bucket_stats[bucket]["count"] += 1
            bucket_stats[bucket][direction] = bucket_stats[bucket].get(direction, 0) + 1
            bucket_stats[bucket]["total_impact"] += impact or 0

        # Store aggregates
        for bucket, stats in bucket_stats.items():
            avg_impact = stats["total_impact"] / stats["count"] if stats["count"] > 0 else 0
            net_sentiment = (stats["bullish"] - stats["bearish"]) / stats["count"] if stats["count"] > 0 else 0

            cur.execute("""
                INSERT INTO news_sentiment_daily (
                    as_of_date, bucket, article_count, bullish_count,
                    bearish_count, neutral_count, avg_impact, net_sentiment
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (as_of_date, bucket) DO UPDATE SET
                    article_count = EXCLUDED.article_count,
                    bullish_count = EXCLUDED.bullish_count,
                    bearish_count = EXCLUDED.bearish_count,
                    neutral_count = EXCLUDED.neutral_count,
                    avg_impact = EXCLUDED.avg_impact,
                    net_sentiment = EXCLUDED.net_sentiment,
                    created_at = NOW()
            """, (
                today, bucket, stats["count"], stats["bullish"],
                stats["bearish"], stats["neutral"], avg_impact, net_sentiment
            ))

        self.pg.commit()
        cur.close()
        logger.info(f"  Updated sentiment for {len(bucket_stats)} buckets")

    def run(self, source: str = "all"):
        """Run news ingestion and classification."""
        logger.info("=" * 60)
        logger.info("NEWS INGESTION & CLASSIFICATION")
        logger.info(f"Time: {datetime.now().isoformat()}")
        logger.info(f"Source: {source}")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info("=" * 60)

        all_articles = []

        if source in ["all", "yahoo"]:
            logger.info("\nFetching from Yahoo Finance...")
            all_articles.extend(self.fetch_yahoo_rss())

        if source in ["all", "polygon"]:
            logger.info("\nFetching from Polygon...")
            all_articles.extend(self.fetch_polygon_news())

        # Dedupe
        seen_titles = set()
        unique_articles = []
        for article in all_articles:
            title = article.get('title', '').lower().strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_articles.append(article)

        logger.info(f"\nUnique articles: {len(unique_articles)}")

        # Store and classify
        logger.info("\nStoring and classifying...")
        results = self.store_and_classify(unique_articles)

        # Update daily aggregates
        logger.info("\nUpdating daily sentiment aggregates...")
        self.update_daily_sentiment()

        logger.info("\n" + "=" * 60)
        logger.info("COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Raw articles stored: {results['raw']}")
        logger.info(f"Articles classified: {results['classified']}")

        self.pg.close()


def main():
    parser = argparse.ArgumentParser(description="Ingest and classify news")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", choices=["all", "yahoo", "polygon"], default="all")
    args = parser.parse_args()

    ingester = NewsIngester(dry_run=args.dry_run)
    ingester.run(source=args.source)


if __name__ == "__main__":
    main()
