#!/usr/bin/env python3
"""
News Ingestion Pipeline
========================
Fetches news from Yahoo Finance (primary) and Polygon (backup)
for soybean oil and related commodities.

Runs every 4 hours via Railway cron.

Usage:
    python scripts/ingest_news.py
    python scripts/ingest_news.py --dry-run
    python scripts/ingest_news.py --source yahoo
    python scripts/ingest_news.py --source polygon
"""

import os
import sys
import logging
import argparse
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import requests
import psycopg2
from psycopg2.extras import execute_batch
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

# News search terms for soybean oil context
SEARCH_TERMS = [
    "soybean oil",
    "soy oil",
    "vegetable oil",
    "ZL futures",
    "CBOT soybean",
    "palm oil",
    "biodiesel",
    "renewable diesel",
    "China soybean",
    "Argentina soy",
    "Brazil soybean",
    "crush margin",
    "USDA WASDE",
]

# Yahoo Finance RSS feeds for commodities
YAHOO_RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ZL=F&region=US&lang=en-US",  # ZL futures
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ZS=F&region=US&lang=en-US",  # ZS futures
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ZM=F&region=US&lang=en-US",  # ZM futures
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=CL=F&region=US&lang=en-US",  # Crude
]


class NewsIngester:
    """Ingest news from multiple sources into Prisma."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.pg = psycopg2.connect(DATABASE_URL)
        self._ensure_table()
        logger.info("Connected to Prisma Postgres")

    def _ensure_table(self):
        """Create news table if it doesn't exist."""
        cur = self.pg.cursor()
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
                sentiment VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_news_published ON raw_news_articles(published_at);
            CREATE INDEX IF NOT EXISTS idx_news_source ON raw_news_articles(source);
        """)
        self.pg.commit()
        cur.close()

    def _generate_article_id(self, title: str, url: str) -> str:
        """Generate unique article ID from title and URL."""
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

                    # Parse date
                    published_at = None
                    if pub_date:
                        try:
                            # Yahoo RSS format: "Mon, 30 Dec 2024 15:30:00 +0000"
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
                        'symbols': self._extract_symbols(title + ' ' + description),
                    })

                logger.info(f"  Yahoo RSS: fetched {len(articles)} articles")

            except Exception as e:
                logger.warning(f"  Yahoo RSS error for {feed_url}: {e}")
                continue

        return articles

    def fetch_polygon_news(self) -> List[Dict[str, Any]]:
        """Fetch news from Polygon.io API."""
        if not POLYGON_API_KEY:
            logger.warning("POLYGON_API_KEY not set, skipping Polygon news")
            return []

        articles = []
        tickers = ["ZL", "ZS", "ZM", "CL"]

        for ticker in tickers:
            try:
                url = f"https://api.polygon.io/v2/reference/news"
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

                logger.info(f"  Polygon: fetched {len(data.get('results', []))} articles for {ticker}")

            except Exception as e:
                logger.warning(f"  Polygon error for {ticker}: {e}")
                continue

        return articles

    def _extract_symbols(self, text: str) -> List[str]:
        """Extract commodity symbols from text."""
        symbols = []
        text_upper = text.upper()

        symbol_map = {
            'ZL': ['SOYBEAN OIL', 'SOY OIL', 'ZL'],
            'ZS': ['SOYBEAN', 'SOYBEANS', 'ZS'],
            'ZM': ['SOYBEAN MEAL', 'SOY MEAL', 'ZM'],
            'CL': ['CRUDE OIL', 'WTI', 'CL'],
        }

        for symbol, keywords in symbol_map.items():
            for kw in keywords:
                if kw in text_upper:
                    symbols.append(symbol)
                    break

        return list(set(symbols))

    def store_articles(self, articles: List[Dict[str, Any]]) -> int:
        """Store articles in Prisma database."""
        if not articles:
            return 0

        if self.dry_run:
            logger.info(f"[DRY RUN] Would store {len(articles)} articles")
            return 0

        cur = self.pg.cursor()
        stored = 0

        for article in articles:
            try:
                article_id = self._generate_article_id(
                    article.get('title', ''),
                    article.get('url', '')
                )

                cur.execute("""
                    INSERT INTO raw_news_articles (
                        article_id, title, summary, source, author, url,
                        published_at, symbols, keywords
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (article_id) DO NOTHING
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

                if cur.rowcount > 0:
                    stored += 1

            except Exception as e:
                logger.error(f"Error storing article: {e}")
                continue

        self.pg.commit()
        cur.close()

        return stored

    def run(self, source: str = "all"):
        """Run news ingestion."""
        logger.info("=" * 60)
        logger.info("NEWS INGESTION")
        logger.info(f"Time: {datetime.now().isoformat()}")
        logger.info(f"Source: {source}")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info("=" * 60)

        all_articles = []

        # Fetch from Yahoo (primary)
        if source in ["all", "yahoo"]:
            logger.info("\nFetching from Yahoo Finance...")
            yahoo_articles = self.fetch_yahoo_rss()
            all_articles.extend(yahoo_articles)
            logger.info(f"  Total from Yahoo: {len(yahoo_articles)}")

        # Fetch from Polygon (backup)
        if source in ["all", "polygon"]:
            logger.info("\nFetching from Polygon...")
            polygon_articles = self.fetch_polygon_news()
            all_articles.extend(polygon_articles)
            logger.info(f"  Total from Polygon: {len(polygon_articles)}")

        # Dedupe by title
        seen_titles = set()
        unique_articles = []
        for article in all_articles:
            title = article.get('title', '').lower().strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_articles.append(article)

        logger.info(f"\nTotal unique articles: {len(unique_articles)}")

        # Store
        stored = self.store_articles(unique_articles)

        logger.info("\n" + "=" * 60)
        logger.info("NEWS INGESTION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Articles fetched: {len(all_articles)}")
        logger.info(f"Unique articles: {len(unique_articles)}")
        logger.info(f"New articles stored: {stored}")

        self.pg.close()


def main():
    parser = argparse.ArgumentParser(description="Ingest news articles")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    parser.add_argument("--source", choices=["all", "yahoo", "polygon"],
                        default="all", help="News source to use")
    args = parser.parse_args()

    ingester = NewsIngester(dry_run=args.dry_run)
    ingester.run(source=args.source)


if __name__ == "__main__":
    main()
