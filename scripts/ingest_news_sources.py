#!/usr/bin/env python3
"""
ZINC-FUSION News Ingestion Pipeline (Server Scheduled Job)
============================================================
Pulls real news from 25+ agricultural, trade, and policy sources.
Routes to appropriate Big-11 specialist buckets via rule-based classifier.

DEPLOYMENT: Server cron job - NOT for local Mac execution.

Schedule (recommended):
    - P0 Critical: Every 2 hours (6 AM - 10 PM ET)
    - P1 High: Every 4 hours
    - P2 Medium: Every 6 hours
    - Full sweep: Daily at 5 AM ET

Cron examples:
    # P0 sources every 2 hours during market hours
    0 6,8,10,12,14,16,18,20,22 * * * python scripts/ingest_news_sources.py --mode quick

    # Full sweep daily at 5 AM ET
    0 5 * * * python scripts/ingest_news_sources.py --mode full --days 7

Environment Variables Required:
    DATABASE_URL - Prisma Postgres connection string
    SCRAPECREATORS_API_KEY - For Twitter/Truth Social (optional)

Sources by Specialist (Big-11):
    crush: Farm Policy, FarmDoc, Reuters, USDA, AgWeb, Agrimoney, DTN, etc.
    china: Reuters China, MOFCOM, Agrimoney China
    fx: ECB, FRED FX commentary
    fed: Federal Reserve News, FOMC Speeches
    tariff: White House, USTR, Federal Register
    energy: EIA Today in Energy, EIA Petroleum
    biofuel: EPA News, Biodiesel Magazine
    palm: MPOB Malaysia, GAPKI Indonesia, Palm Oil Today, RSPO, TradingEcon
    volatility: CBOE Insights
    substitutes: Canola Council, Oilseed & Grain, NSA, ICE Canola, TradingEcon (canola/sunflower/rapeseed)
    trump_effect: Truth Social, Executive Orders, Federal Register, Politico

Usage:
    python scripts/ingest_news_sources.py --mode full     # All sources
    python scripts/ingest_news_sources.py --mode quick    # P0 only (fast)
    python scripts/ingest_news_sources.py --mode p1       # P0 + P1
    python scripts/ingest_news_sources.py --days 30       # Last 30 days
    python scripts/ingest_news_sources.py --dry-run       # Preview only
    python scripts/ingest_news_sources.py --specialist crush  # Single specialist
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import feedparser
import psycopg2
import requests
from bs4 import BeautifulSoup

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.fusion.api.news_sentiment import classify_article

# =============================================================================
# LOGGING CONFIGURATION (Server-friendly)
# =============================================================================

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler(
            LOG_DIR / f"news_ingest_{datetime.now().strftime('%Y%m%d')}.log"
        ),
    ],
)
logger = logging.getLogger(__name__)

# =============================================================================
# BIG-11 SPECIALIST NEWS SOURCES
# =============================================================================

NEWS_SOURCES = [
    # =========================================================================
    # SPECIALIST 1: CRUSH (Soybean Complex Fundamentals)
    # =========================================================================
    {
        "name": "Farm Policy News",
        "source_id": "farm_policy_news",
        "priority": 0,
        "type": "rss",
        "url": "https://farmpolicynews.illinois.edu/feed/",
        "specialist": "crush",
    },
    {
        "name": "FarmDoc Daily",
        "source_id": "farmdoc_daily",
        "priority": 0,
        "type": "rss",
        "url": "https://farmdocdaily.illinois.edu/feed",
        "specialist": "crush",
    },
    {
        "name": "Reuters Commodities",
        "source_id": "reuters_commodities",
        "priority": 0,
        "type": "rss",
        "url": "https://www.reutersagency.com/feed/?best-topics=commodities&post_type=best",
        "specialist": "crush",
    },
    {
        "name": "USDA Press Releases",
        "source_id": "usda_press",
        "priority": 0,
        "type": "rss",
        "url": "https://www.usda.gov/rss/latest-releases.xml",
        "specialist": "crush",
    },
    {
        "name": "DTN Progressive Farmer",
        "source_id": "dtn_progressive",
        "priority": 0,
        "type": "scrape",
        "url": "https://www.dtnpf.com/agriculture/web/ag/home",
        "specialist": "crush",
    },
    {
        "name": "Soybean & Corn Advisor",
        "source_id": "soybean_corn_advisor",
        "priority": 0,
        "type": "scrape",
        "url": "https://www.soybeansandcorn.com",
        "specialist": "crush",
    },
    {
        "name": "Agrimoney Grains",
        "source_id": "agrimoney_grains",
        "priority": 1,
        "type": "rss",
        "url": "https://www.agrimoney.com/rss/grains-oilseeds",
        "specialist": "crush",
    },
    {
        "name": "AgWeb Soybeans",
        "source_id": "agweb_soybeans",
        "priority": 1,
        "type": "rss",
        "url": "https://www.agweb.com/rss/news/crops/soybeans",
        "specialist": "crush",
    },
    {
        "name": "Farm Progress",
        "source_id": "farm_progress",
        "priority": 1,
        "type": "rss",
        "url": "https://www.farmprogress.com/rss.xml",
        "specialist": "crush",
    },
    {
        "name": "Agriculture.com",
        "source_id": "agriculture_com",
        "priority": 2,
        "type": "rss",
        "url": "https://www.agriculture.com/rss/news/crops",
        "specialist": "crush",
    },
    {
        "name": "World Grain",
        "source_id": "world_grain",
        "priority": 2,
        "type": "rss",
        "url": "https://www.world-grain.com/rss",
        "specialist": "crush",
    },
    # =========================================================================
    # SPECIALIST 2: CHINA (Trade Flows)
    # =========================================================================
    {
        "name": "Reuters China",
        "source_id": "reuters_china",
        "priority": 1,
        "type": "rss",
        "url": "https://www.reutersagency.com/feed/?best-regions=asia&post_type=best",
        "specialist": "china",
    },
    {
        "name": "Agrimoney China",
        "source_id": "agrimoney_china",
        "priority": 1,
        "type": "scrape",
        "url": "https://www.agrimoney.com/news/china/",
        "specialist": "china",
    },
    {
        "name": "MOFCOM Trade News",
        "source_id": "mofcom",
        "priority": 2,
        "type": "scrape",
        "url": "http://english.mofcom.gov.cn/",
        "specialist": "china",
    },
    # =========================================================================
    # SPECIALIST 3: FX (Currency Competitiveness)
    # =========================================================================
    {
        "name": "ECB Press Releases",
        "source_id": "ecb_press",
        "priority": 2,
        "type": "scrape",
        "url": "https://www.ecb.europa.eu/press/pr/html/index.en.html",
        "specialist": "fx",
    },
    # =========================================================================
    # SPECIALIST 4: FED (Monetary Policy)
    # =========================================================================
    {
        "name": "Federal Reserve News",
        "source_id": "fed_news",
        "priority": 1,
        "type": "rss",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "specialist": "fed",
    },
    {
        "name": "Federal Reserve Speeches",
        "source_id": "fed_speeches",
        "priority": 2,
        "type": "scrape",
        "url": "https://www.federalreserve.gov/newsevents/speeches.htm",
        "specialist": "fed",
    },
    # =========================================================================
    # SPECIALIST 5: TARIFF (Trade Policy)
    # =========================================================================
    {
        "name": "White House Briefing",
        "source_id": "whitehouse_briefing",
        "priority": 1,
        "type": "rss",
        "url": "https://www.whitehouse.gov/briefing-room/statements-releases/feed/",
        "specialist": "tariff",
    },
    {
        "name": "USTR Press",
        "source_id": "ustr_press",
        "priority": 1,
        "type": "scrape",
        "url": "https://ustr.gov/about-us/policy-offices/press-office/press-releases",
        "specialist": "tariff",
    },
    {
        "name": "Federal Register Tariffs",
        "source_id": "federal_register_tariffs",
        "priority": 2,
        "type": "api",
        "url": "https://www.federalregister.gov/api/v1/documents.json?conditions[term]=tariff&conditions[type][]=RULE&per_page=20",
        "specialist": "tariff",
    },
    # =========================================================================
    # SPECIALIST 6: ENERGY (Crude Oil & Energy Complex)
    # =========================================================================
    {
        "name": "EIA Today in Energy",
        "source_id": "eia_today",
        "priority": 1,
        "type": "rss",
        "url": "https://www.eia.gov/rss/todayinenergy.xml",
        "specialist": "energy",
    },
    {
        "name": "EIA Petroleum News",
        "source_id": "eia_petroleum",
        "priority": 2,
        "type": "rss",
        "url": "https://www.eia.gov/rss/petroleum.xml",
        "specialist": "energy",
    },
    # =========================================================================
    # SPECIALIST 7: BIOFUEL (Biodiesel & Renewable Fuel)
    # =========================================================================
    {
        "name": "EPA News Releases",
        "source_id": "epa_news",
        "priority": 1,
        "type": "rss",
        "url": "https://www.epa.gov/newsreleases/search/rss",
        "specialist": "biofuel",
    },
    {
        "name": "Biodiesel Magazine",
        "source_id": "biodiesel_mag",
        "priority": 2,
        "type": "rss",
        "url": "http://www.biodieselmagazine.com/rss/",
        "specialist": "biofuel",
    },
    # =========================================================================
    # SPECIALIST 8: PALM (Palm Oil Substitution)
    # =========================================================================
    {
        "name": "MPOB Malaysia",
        "source_id": "mpob_news",
        "priority": 1,
        "type": "scrape",
        "url": "https://www.mpob.gov.my/",
        "specialist": "palm",
    },
    {
        "name": "GAPKI Indonesia",
        "source_id": "gapki",
        "priority": 1,
        "type": "scrape",
        "url": "https://gapki.id/en/news/",
        "specialist": "palm",
    },
    {
        "name": "Palm Oil Today",
        "source_id": "palm_oil_today",
        "priority": 2,
        "type": "scrape",
        "url": "https://www.palmoiltoday.net/",
        "specialist": "palm",
    },
    {
        "name": "RSPO News",
        "source_id": "rspo_news",
        "priority": 2,
        "type": "scrape",
        "url": "https://rspo.org/news-and-events/",
        "specialist": "palm",
    },
    {
        "name": "TradingEcon Palm Oil",
        "source_id": "tradingec_palm",
        "priority": 2,
        "type": "scrape",
        "url": "https://tradingeconomics.com/commodity/palm-oil",
        "specialist": "palm",
    },
    # =========================================================================
    # SPECIALIST 9: VOLATILITY (Financial Stress)
    # =========================================================================
    {
        "name": "CBOE Insights",
        "source_id": "cboe_insights",
        "priority": 2,
        "type": "scrape",
        "url": "https://www.cboe.com/insights/",
        "specialist": "volatility",
    },
    # =========================================================================
    # SPECIALIST 10: SUBSTITUTES (Vegetable Oil Competition)
    # Covers: Canola, Sunflower, Rapeseed, other veg oils
    # =========================================================================
    {
        "name": "Canola Council News",
        "source_id": "canola_council",
        "priority": 1,
        "type": "scrape",
        "url": "https://www.canolacouncil.org/news/",
        "specialist": "substitutes",
    },
    {
        "name": "Oilseed & Grain News",
        "source_id": "oilseed_grain",
        "priority": 1,
        "type": "scrape",
        "url": "https://www.oilseedandgrain.com/",
        "specialist": "substitutes",
    },
    {
        "name": "National Sunflower Association",
        "source_id": "sunflower_nsa",
        "priority": 2,
        "type": "scrape",
        "url": "https://www.sunflowernsa.com/",
        "specialist": "substitutes",
    },
    {
        "name": "ICE Canola Futures",
        "source_id": "ice_canola",
        "priority": 2,
        "type": "scrape",
        "url": "https://www.theice.com/products/251/Canola-Futures",
        "specialist": "substitutes",
    },
    {
        "name": "TradingEcon Canola",
        "source_id": "tradingec_canola",
        "priority": 2,
        "type": "scrape",
        "url": "https://tradingeconomics.com/commodity/canola",
        "specialist": "substitutes",
    },
    {
        "name": "TradingEcon Sunflower Oil",
        "source_id": "tradingec_sunflower",
        "priority": 2,
        "type": "scrape",
        "url": "https://tradingeconomics.com/commodity/sunflower-oil",
        "specialist": "substitutes",
    },
    {
        "name": "TradingEcon Rapeseed",
        "source_id": "tradingec_rapeseed",
        "priority": 2,
        "type": "scrape",
        "url": "https://tradingeconomics.com/commodity/rapeseed",
        "specialist": "substitutes",
    },
    # =========================================================================
    # SPECIALIST 11: TRUMP EFFECT (Political & Policy Volatility)
    # =========================================================================
    {
        "name": "White House Executive Orders",
        "source_id": "whitehouse_eo",
        "priority": 1,
        "type": "scrape",
        "url": "https://www.whitehouse.gov/presidential-actions/",
        "specialist": "trump_effect",
    },
    {
        "name": "Federal Register Executive Orders",
        "source_id": "federal_register_eo",
        "priority": 1,
        "type": "api",
        "url": "https://www.federalregister.gov/api/v1/documents.json?conditions[presidential_document_type][]=executive_order&per_page=20",
        "specialist": "trump_effect",
    },
    {
        "name": "Politico Trade",
        "source_id": "politico_trade",
        "priority": 2,
        "type": "scrape",
        "url": "https://www.politico.com/trade",
        "specialist": "trump_effect",
    },
    # Truth Social via ScrapeCreators - requires API key
    {
        "name": "Truth Social Trump",
        "source_id": "truth_social",
        "priority": 1,
        "type": "scrapecreators",
        "url": "https://api.scrapecreators.com/v1/truthsocial/user/realDonaldTrump/posts",
        "specialist": "trump_effect",
        "requires_api_key": True,
    },
]

# Analyst Twitter feeds via ScrapeCreators
ANALYST_FEEDS = [
    {"handle": "kannbwx", "name": "Karen Braun", "specialist": "crush"},
    {"handle": "ArlanFF101", "name": "Arlan Suderman", "specialist": "crush"},
    {"handle": "ScottIrwinUIUC", "name": "Scott Irwin", "specialist": "biofuel"},
    {"handle": "SoybeanCorn", "name": "Dr. Michael Cordonnier", "specialist": "crush"},
    {"handle": "JavierBlas", "name": "Javier Blas", "specialist": "energy"},
]

# Request headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    return psycopg2.connect(database_url)


def article_exists(conn, article_hash: str) -> bool:
    """Check if article already exists by content hash across all news tables."""
    with conn.cursor() as cur:
        # Check across all alt news tables (union for dedup)
        cur.execute(
            """
            SELECT 1 FROM (
                SELECT row_hash FROM alt.policy_news_event WHERE row_hash = %s
                UNION ALL
                SELECT row_hash FROM alt.executive_actions_event WHERE row_hash = %s
                UNION ALL
                SELECT row_hash FROM alt.econ_news_event WHERE row_hash = %s
                UNION ALL
                SELECT row_hash FROM alt.profarmer_news_event WHERE row_hash = %s
            ) combined LIMIT 1
        """,
            (article_hash, article_hash, article_hash, article_hash),
        )
        return cur.fetchone() is not None


def insert_article(conn, article: Dict[str, Any]) -> bool:
    """Insert article into appropriate alt news table based on source type."""
    try:
        # Convert bucket_name to specialist_tags array
        bucket = article.get("bucket_name")
        specialist_tags = [bucket] if bucket else []

        # Route to appropriate table based on source
        source = article.get("source", "").lower()

        # Determine target table
        if "whitehouse" in source or "executive" in source:
            table = "alt.executive_actions_event"
        elif any(x in source for x in ["profarmer", "farmdoc", "agweb", "dtn"]):
            table = "alt.profarmer_news_event"
        elif any(x in source for x in ["fred", "ecb", "bloomberg", "wsj"]):
            table = "alt.econ_news_event"
        else:
            # Default: policy/trade news
            table = "alt.policy_news_event"

        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {table}
                (event_date, published_at, headline, content, source, specialist_tags, zl_sentiment,
                 row_hash, url, ingested_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
                (
                    article["event_date"],
                    article["published_at"],
                    article["headline"][:500] if article["headline"] else None,
                    article["content"][:10000] if article["content"] else None,
                    article["source"],
                    specialist_tags,
                    article.get("zl_sentiment"),
                    article["content_hash"],
                    article.get("url"),
                ),
            )
            logger.info(f"Inserted article to {table}")
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Failed to insert article: {e}")
        return False


def ensure_schema(conn):
    """Verify required columns exist across all alt news tables (no implicit DDL)."""
    # Core columns required across all news tables (removing is_trump_related - field was removed)
    required = {
        "event_date",
        "headline",
        "source",
        "specialist_tags",
        "row_hash",
        "ingested_at",
    }

    tables = ["policy_news", "executive_actions", "econ_news", "profarmer_news"]

    with conn.cursor() as cur:
        for table in tables:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'alt' AND table_name = %s
                """,
                (table,),
            )
            cols = {r[0] for r in cur.fetchall()}

            missing = sorted(required - cols)
            if missing:
                raise SystemExit(
                    f"alt.{table} missing required columns: "
                    + ", ".join(missing)
                    + ". Schema changes require explicit approval."
                )


# =============================================================================
# ARTICLE FETCHING
# =============================================================================


def compute_hash(headline: str, content: str, source: str) -> str:
    """Compute unique hash for article deduplication."""
    text = f"{headline or ''}{content or ''}{source or ''}"
    return hashlib.sha256(text.encode()).hexdigest()[:64]


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats."""
    if not date_str:
        return None

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%d %B %Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    return None


def is_trump_related(text: str) -> bool:
    """Check if article mentions Trump or related keywords."""
    patterns = [
        r"\btrump\b",
        r"\btruth\s*social\b",
        r"\bmar-?a-?lago\b",
        r"\bmaga\b",
        r"\bexecutive\s*order\b",
    ]
    combined = "|".join(patterns)
    return bool(re.search(combined, text.lower()))


def process_article(
    headline: str,
    content: str,
    source: Dict,
    url: str = None,
    pub_date: datetime = None,
) -> Dict[str, Any]:
    """Process and classify a single article."""
    # Classify using rule-based system
    article_data = {
        "title": headline,
        "body": content,
        "source": source["source_id"],
    }
    classification = classify_article(article_data)

    # Determine specialist - use classification bucket or default
    bucket = (
        classification["alert_buckets"][0] if classification["alert_buckets"] else None
    )

    # Check for Trump-related content
    trump_related = is_trump_related(f"{headline} {content}")

    # If Trump-related and not already routed to trump_effect, route there
    if trump_related and source["specialist"] != "trump_effect":
        bucket = "trump_effect"

    published_at = pub_date or datetime.now()

    return {
        "event_date": published_at.date(),
        "published_at": published_at,
        "headline": headline,
        "content": content[:10000] if content else None,
        "source": source["source_id"],
        "bucket_name": bucket or source["specialist"],
        "zl_sentiment": classification["impact_score"],
        "is_trump_related": trump_related,
        "content_hash": compute_hash(headline, content, source["source_id"]),
        "url": url,
    }


def fetch_rss_feed(source: Dict[str, Any], days_back: int = 30) -> List[Dict[str, Any]]:
    """Fetch articles from RSS feed."""
    articles = []
    cutoff = datetime.now() - timedelta(days=days_back)

    try:
        feed = feedparser.parse(source["url"], request_headers=HEADERS)

        if feed.bozo and not feed.entries:
            logger.warning(
                f"  RSS parse failed: {source['name']} - {getattr(feed, 'bozo_exception', 'Unknown')}"
            )
            return []

        for entry in feed.entries:
            # Parse date
            pub_date = None
            for date_field in ["published", "updated", "created"]:
                if hasattr(entry, date_field):
                    pub_date = parse_date(getattr(entry, date_field))
                    if pub_date:
                        break

            if not pub_date:
                pub_date = datetime.now()

            # Skip old articles
            try:
                if pub_date.replace(tzinfo=None) < cutoff:
                    continue
            except:
                pass

            # Extract content
            headline = entry.get("title", "")
            content = ""
            if hasattr(entry, "summary"):
                content = entry.summary
            elif hasattr(entry, "content"):
                content = entry.content[0].value if entry.content else ""

            # Clean HTML
            if content:
                soup = BeautifulSoup(content, "html.parser")
                content = soup.get_text(separator=" ", strip=True)

            if not headline:
                continue

            articles.append(
                process_article(
                    headline=headline,
                    content=content,
                    source=source,
                    url=entry.get("link"),
                    pub_date=pub_date,
                )
            )

        return articles

    except Exception as e:
        logger.error(f"  Error fetching RSS {source['name']}: {e}")
        return []


def fetch_api_source(
    source: Dict[str, Any], days_back: int = 30
) -> List[Dict[str, Any]]:
    """Fetch articles from JSON API (e.g., Federal Register)."""
    articles = []

    try:
        response = requests.get(source["url"], headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Handle Federal Register API format
        results = data.get("results", data.get("documents", []))

        for item in results:
            headline = item.get("title", "")
            content = item.get("abstract", item.get("body", ""))
            pub_date = parse_date(item.get("publication_date", ""))
            url = item.get("html_url", item.get("url", ""))

            if not headline:
                continue

            articles.append(
                process_article(
                    headline=headline,
                    content=content,
                    source=source,
                    url=url,
                    pub_date=pub_date,
                )
            )

        return articles

    except Exception as e:
        logger.error(f"  Error fetching API {source['name']}: {e}")
        return []


def fetch_scrape_source(
    source: Dict[str, Any], days_back: int = 30
) -> List[Dict[str, Any]]:
    """Scrape articles from website."""
    articles = []

    try:
        response = requests.get(source["url"], headers=HEADERS, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Generic article extraction
        article_elements = soup.find_all(
            ["article", "div", "li"],
            class_=re.compile(r"(article|post|news|item|entry|story)", re.I),
        )

        for elem in article_elements[:25]:  # Limit per scrape
            # Find headline
            headline_elem = elem.find(["h1", "h2", "h3", "h4", "a"])
            headline = headline_elem.get_text(strip=True) if headline_elem else ""

            if not headline or len(headline) < 10:
                continue

            # Find content/summary
            content_elem = elem.find(
                ["p", "div", "span"],
                class_=re.compile(r"(content|summary|excerpt|desc|text)", re.I),
            )
            content = content_elem.get_text(strip=True) if content_elem else ""

            # Find link
            link_elem = elem.find("a", href=True)
            url = urljoin(source["url"], link_elem["href"]) if link_elem else None

            articles.append(
                process_article(
                    headline=headline,
                    content=content,
                    source=source,
                    url=url,
                    pub_date=datetime.now(),
                )
            )

        return articles

    except Exception as e:
        logger.error(f"  Error scraping {source['name']}: {e}")
        return []


def fetch_scrapecreators(
    source: Dict[str, Any], days_back: int = 7
) -> List[Dict[str, Any]]:
    """Fetch from ScrapeCreators API (Twitter/Truth Social)."""
    api_key = os.getenv("SCRAPECREATORS_API_KEY")
    if not api_key:
        logger.debug(f"  Skipping {source['name']} - no SCRAPECREATORS_API_KEY")
        return []

    articles = []
    try:
        headers = {**HEADERS, "Authorization": f"Bearer {api_key}"}
        response = requests.get(source["url"], headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        posts = data.get("posts", data.get("data", []))
        for post in posts[:50]:
            content = post.get("content", post.get("text", ""))
            pub_date = parse_date(post.get("created_at", ""))

            if not content:
                continue

            # Use first 100 chars as headline
            headline = content[:100] + "..." if len(content) > 100 else content

            articles.append(
                process_article(
                    headline=headline,
                    content=content,
                    source=source,
                    url=post.get("url"),
                    pub_date=pub_date,
                )
            )

        return articles

    except Exception as e:
        logger.error(f"  Error fetching ScrapeCreators {source['name']}: {e}")
        return []


# =============================================================================
# MAIN INGESTION
# =============================================================================


def ingest_news(
    mode: str = "full",
    days_back: int = 30,
    dry_run: bool = False,
    specialist_filter: str = None,
) -> Dict[str, Any]:
    """
    Ingest news from configured sources.

    Args:
        mode: 'full' (all), 'quick' (P0), 'p1' (P0+P1)
        days_back: Days of history to fetch
        dry_run: Preview without inserting
        specialist_filter: Only fetch for this specialist

    Returns:
        Stats dict with counts
    """
    # Filter sources
    sources = NEWS_SOURCES.copy()

    if mode == "quick":
        sources = [s for s in sources if s["priority"] == 0]
    elif mode == "p1":
        sources = [s for s in sources if s["priority"] <= 1]

    if specialist_filter:
        sources = [s for s in sources if s["specialist"] == specialist_filter]

    logger.info("=" * 60)
    logger.info("NEWS INGESTION PIPELINE")
    logger.info("=" * 60)
    logger.info(f"Mode: {mode}")
    logger.info(f"Sources: {len(sources)}")
    logger.info(f"Days back: {days_back}")
    logger.info(f"Dry run: {dry_run}")
    logger.info(f"Specialist filter: {specialist_filter or 'ALL'}")
    logger.info("")

    stats = {
        "run_time": datetime.now().isoformat(),
        "mode": mode,
        "total_fetched": 0,
        "total_inserted": 0,
        "total_duplicates": 0,
        "by_source": {},
        "by_specialist": {},
        "errors": [],
    }

    conn = None
    if not dry_run:
        conn = get_postgres_connection()
        ensure_schema(conn)

    try:
        for source in sources:
            specialist = source["specialist"]
            logger.info(f"[P{source['priority']}] [{specialist}] {source['name']}...")

            # Skip sources requiring API keys we don't have
            if source.get("requires_api_key"):
                key_name = "SCRAPECREATORS_API_KEY"
                if not os.getenv(key_name):
                    logger.info(f"   Skipped (no {key_name})")
                    continue

            # Fetch articles based on type
            if source["type"] == "rss":
                articles = fetch_rss_feed(source, days_back)
            elif source["type"] == "api":
                articles = fetch_api_source(source, days_back)
            elif source["type"] == "scrapecreators":
                articles = fetch_scrapecreators(source, days_back)
            else:
                articles = fetch_scrape_source(source, days_back)

            source_stats = {"fetched": len(articles), "inserted": 0, "duplicates": 0}

            if not dry_run and conn:
                for article in articles:
                    if article_exists(conn, article["content_hash"]):
                        source_stats["duplicates"] += 1
                    elif insert_article(conn, article):
                        source_stats["inserted"] += 1
                        conn.commit()

            stats["total_fetched"] += source_stats["fetched"]
            stats["total_inserted"] += source_stats["inserted"]
            stats["total_duplicates"] += source_stats["duplicates"]
            stats["by_source"][source["source_id"]] = source_stats

            # Track by specialist
            if specialist not in stats["by_specialist"]:
                stats["by_specialist"][specialist] = {"fetched": 0, "inserted": 0}
            stats["by_specialist"][specialist]["fetched"] += source_stats["fetched"]
            stats["by_specialist"][specialist]["inserted"] += source_stats["inserted"]

            logger.info(
                f"   Fetched: {source_stats['fetched']}, Inserted: {source_stats['inserted']}, Dups: {source_stats['duplicates']}"
            )

            # Rate limiting
            time.sleep(1.5)

    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        stats["errors"].append(str(e))
    finally:
        if conn:
            conn.close()

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total fetched: {stats['total_fetched']}")
    logger.info(f"Total inserted: {stats['total_inserted']}")
    logger.info(f"Total duplicates: {stats['total_duplicates']}")
    logger.info("")
    logger.info("By Specialist:")
    for spec, counts in sorted(stats["by_specialist"].items()):
        logger.info(
            f"   {spec}: {counts['inserted']} new / {counts['fetched']} fetched"
        )

    # Write stats to JSON for monitoring
    stats_file = LOG_DIR / f"news_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(stats_file, "w") as f:
        json.dump(stats, f, indent=2)
    logger.info(f"\nStats saved to: {stats_file}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Ingest news from agricultural and policy sources (Server Job)"
    )
    parser.add_argument(
        "--mode",
        choices=["quick", "p1", "full"],
        default="full",
        help="quick=P0 only (fast), p1=P0+P1, full=all sources",
    )
    parser.add_argument(
        "--days", type=int, default=30, help="Days of history to fetch (default: 30)"
    )
    parser.add_argument(
        "--specialist",
        type=str,
        default=None,
        help="Only fetch for this specialist (e.g., 'crush', 'trump_effect')",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting"
    )

    args = parser.parse_args()

    try:
        stats = ingest_news(
            mode=args.mode,
            days_back=args.days,
            dry_run=args.dry_run,
            specialist_filter=args.specialist,
        )
        return 0 if stats["total_inserted"] > 0 or args.dry_run else 1
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
