#!/usr/bin/env python3
"""
Google News RSS Feed Ingestion for Specialist Data Enrichment.

Fetches recent headlines from Google News RSS for each specialist bucket,
tags them with specialist_tags, and inserts into alt.policy_news_event.

Usage:
    python scripts/ingest_google_news.py                    # All specialists
    python scripts/ingest_google_news.py --bucket crush     # Single specialist
    python scripts/ingest_google_news.py --dry-run          # Preview without inserting

This fills the news gap left by ProFarmer being dead since Feb 14, 2026.
Google News RSS is free, no API key needed, returns ~100 articles per query.
"""

import argparse
import hashlib
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import psycopg2
import psycopg2.extras
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Google News search queries per specialist bucket
# Each bucket maps to a list of search queries. Multiple queries per bucket
# ensure broad coverage. Google News RSS returns ~20-100 articles per query.
# ---------------------------------------------------------------------------

SPECIALIST_QUERIES: dict[str, list[str]] = {
    "crush": [
        "soybean crush margin",
        "soybean oil processing plant",
        "soy crush capacity expansion",
    ],
    "china": [
        "China soybean imports",
        "China soybean oil trade",
        "China US trade tariff agriculture",
    ],
    "substitutes": [
        "palm oil price global",
        "canola rapeseed oil market",
        "vegetable oil substitute demand",
    ],
    "fx": [
        "US dollar index DXY currency",
        "emerging market currency devaluation",
        "Brazilian real Chinese yuan exchange rate",
    ],
    "fed": [
        "Federal Reserve interest rate decision",
        "FOMC meeting minutes monetary policy",
        "US inflation economic outlook Fed",
    ],
    "tariff": [
        "US tariff trade war agriculture",
        "agricultural trade policy sanctions",
        "Trump tariff soybean oil",
    ],
    "energy": [
        "crude oil price OPEC supply",
        "renewable fuel standard mandate",
        "energy commodities market outlook",
    ],
    "biofuel": [
        "biodiesel renewable diesel production",
        "RIN credit price EPA biofuel",
        "sustainable aviation fuel SAF soybean oil",
    ],
    "palm": [
        "palm oil production Malaysia Indonesia",
        "MPOB palm oil stocks exports",
        "palm oil export ban Indonesia",
    ],
    "volatility": [
        "commodity market volatility VIX",
        "soybean oil futures volatility",
        "agricultural commodity risk",
    ],
    "trump_effect": [
        "Trump executive order trade",
        "Trump tariff policy 2026",
        "Trump administration trade agriculture energy",
    ],
}

# All valid specialist buckets (Big-11)
ALL_BUCKETS = list(SPECIALIST_QUERIES.keys())

GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search"
USER_AGENT = "Mozilla/5.0 (ZINC-Fusion/1.0)"
SOURCE_NAME = "google_news"


# ---------------------------------------------------------------------------
# RSS Parsing
# ---------------------------------------------------------------------------


def fetch_google_news_rss(query: str, max_articles: int = 50) -> list[dict[str, Any]]:
    """Fetch and parse Google News RSS for a search query."""
    url = f"{GOOGLE_NEWS_RSS_BASE}?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch RSS for '{query}': {e}")
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        logger.warning(f"Failed to parse RSS XML for '{query}': {e}")
        return []

    articles = []
    channel = root.find("channel")
    if channel is None:
        return []

    for item in channel.findall("item")[:max_articles]:
        title_el = item.find("title")
        link_el = item.find("link")
        pubdate_el = item.find("pubDate")
        source_el = item.find("source")

        if title_el is None or title_el.text is None:
            continue

        headline = title_el.text.strip()
        url_val = link_el.text.strip() if link_el is not None and link_el.text else None
        pub_source = (
            source_el.text.strip()
            if source_el is not None and source_el.text
            else "Google News"
        )

        # Parse pubDate (RFC 2822 format: "Sat, 01 Mar 2026 14:30:00 GMT")
        published_at = None
        event_date = None
        if pubdate_el is not None and pubdate_el.text:
            try:
                from email.utils import parsedate_to_datetime

                published_at = parsedate_to_datetime(pubdate_el.text)
                event_date = published_at.date()
            except Exception:
                event_date = datetime.now(timezone.utc).date()
                published_at = datetime.now(timezone.utc)
        else:
            event_date = datetime.now(timezone.utc).date()
            published_at = datetime.now(timezone.utc)

        articles.append(
            {
                "headline": headline,
                "url": url_val,
                "published_at": published_at,
                "event_date": event_date,
                "pub_source": pub_source,
            }
        )

    return articles


# ---------------------------------------------------------------------------
# Specialist tagging
# ---------------------------------------------------------------------------

# Keywords that indicate relevance to each specialist
# An article matched by query X gets bucket X, but may also match others
CROSS_TAG_KEYWORDS: dict[str, list[str]] = {
    "crush": ["crush", "soybean oil", "soy oil", "processing", "soy meal"],
    "china": ["china", "chinese", "beijing", "xi jinping"],
    "substitutes": ["palm oil", "canola", "rapeseed", "sunflower", "olive oil"],
    "fx": ["dollar", "currency", "forex", "exchange rate", "yuan", "real"],
    "fed": ["federal reserve", "fomc", "interest rate", "monetary policy", "inflation"],
    "tariff": ["tariff", "trade war", "sanctions", "import duty", "trade policy"],
    "energy": ["crude oil", "opec", "petroleum", "natural gas", "energy"],
    "biofuel": ["biodiesel", "renewable diesel", "rin", "biofuel", "ethanol", "saf"],
    "palm": ["palm oil", "mpob", "indonesia", "malaysia palm"],
    "volatility": ["volatility", "vix", "risk", "market crash", "sell-off"],
    "trump_effect": ["trump", "executive order", "presidential", "white house"],
}


def compute_specialist_tags(headline: str, primary_bucket: str) -> list[str]:
    """Compute specialist tags for an article based on headline content."""
    tags = {primary_bucket}  # Always include the primary bucket
    headline_lower = headline.lower()

    for bucket, keywords in CROSS_TAG_KEYWORDS.items():
        if bucket == primary_bucket:
            continue
        for kw in keywords:
            if kw in headline_lower:
                tags.add(bucket)
                break

    return sorted(tags)


def compute_row_hash(headline: str, event_date: Any, source: str) -> str:
    """Compute idempotent row hash."""
    parts = f"{headline}|{event_date}|{source}"
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------


def get_db_connection():
    """Get database connection from environment."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        # Try loading from .env file
        env_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
        )
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DATABASE_URL="):
                        db_url = line.split("=", 1)[1].strip('"').strip("'")
                        break

    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    return psycopg2.connect(db_url)


def insert_articles(
    articles: list[dict[str, Any]], dry_run: bool = False
) -> tuple[int, int]:
    """Insert articles into alt.policy_news_event with row_hash dedup."""
    if not articles:
        return 0, 0

    if dry_run:
        for a in articles[:5]:
            logger.info(
                f"  [DRY RUN] {a['event_date']} | {a['specialist_tags']} | "
                f"{a['headline'][:80]}"
            )
        if len(articles) > 5:
            logger.info(f"  ... and {len(articles) - 5} more")
        return len(articles), 0

    conn = get_db_connection()
    cur = conn.cursor()

    inserted = 0
    skipped = 0

    for article in articles:
        row_hash = article["row_hash"]

        # Check if already exists (idempotent)
        cur.execute(
            "SELECT 1 FROM alt.policy_news_event WHERE row_hash = %s", (row_hash,)
        )
        if cur.fetchone():
            skipped += 1
            continue

        try:
            cur.execute(
                """
                INSERT INTO alt.policy_news_event
                    (event_date, published_at, headline, url, source,
                     specialist_tags, row_hash, ingested_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (row_hash) WHERE row_hash IS NOT NULL DO NOTHING
                """,
                (
                    article["event_date"],
                    article["published_at"],
                    article["headline"],
                    article["url"],
                    article["source"],
                    article["specialist_tags"],
                    row_hash,
                ),
            )
            inserted += 1
        except Exception as e:
            logger.warning(f"Insert error: {e}")
            conn.rollback()
            continue

    conn.commit()
    cur.close()
    conn.close()

    return inserted, skipped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def ingest_bucket(bucket: str, dry_run: bool = False) -> tuple[int, int]:
    """Ingest Google News for a single specialist bucket."""
    queries = SPECIALIST_QUERIES.get(bucket, [])
    if not queries:
        logger.warning(f"No queries defined for bucket '{bucket}'")
        return 0, 0

    all_articles: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for query in queries:
        logger.info(f"  Fetching: '{query}'")
        raw = fetch_google_news_rss(query)
        logger.info(f"    Got {len(raw)} articles")

        for article in raw:
            tags = compute_specialist_tags(article["headline"], bucket)
            row_hash = compute_row_hash(
                article["headline"], article["event_date"], article["pub_source"]
            )

            # Deduplicate within this run
            if row_hash in seen_hashes:
                continue
            seen_hashes.add(row_hash)

            all_articles.append(
                {
                    "event_date": article["event_date"],
                    "published_at": article["published_at"],
                    "headline": article["headline"],
                    "url": article["url"],
                    "source": f"{SOURCE_NAME}/{article['pub_source']}",
                    "specialist_tags": tags,
                    "row_hash": row_hash,
                }
            )

    logger.info(f"  Total unique articles for {bucket}: {len(all_articles)}")
    inserted, skipped = insert_articles(all_articles, dry_run=dry_run)
    return inserted, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Google News RSS for specialist data enrichment"
    )
    parser.add_argument(
        "--bucket",
        choices=ALL_BUCKETS + ["all"],
        default="all",
        help="Specialist bucket to ingest (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview articles without inserting into DB",
    )
    args = parser.parse_args()

    buckets = ALL_BUCKETS if args.bucket == "all" else [args.bucket]

    logger.info(f"Google News ingestion starting for {len(buckets)} bucket(s)")
    logger.info(f"Dry run: {args.dry_run}")

    total_inserted = 0
    total_skipped = 0

    for bucket in buckets:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processing: {bucket.upper()}")
        logger.info(f"{'=' * 60}")

        inserted, skipped = ingest_bucket(bucket, dry_run=args.dry_run)
        total_inserted += inserted
        total_skipped += skipped

        logger.info(f"  {bucket}: {inserted} inserted, {skipped} skipped (dedup)")

    logger.info(f"\n{'=' * 60}")
    logger.info(f"TOTAL: {total_inserted} inserted, {total_skipped} skipped")
    logger.info(f"{'=' * 60}")


if __name__ == "__main__":
    main()
