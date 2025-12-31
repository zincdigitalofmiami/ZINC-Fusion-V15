#!/usr/bin/env python3
"""
News Ingestion & Classification Pipeline
=========================================
Fetches news from Yahoo Finance, Polygon, and ScrapeCreators (analyst feeds),
classifies articles into specialist buckets with advanced scoring.

Features:
- Specialist bucket classification (crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes)
- Half-life decay scoring (short/medium/long)
- Cross-asset boost logic (oil + biofuel = double bullish)
- Source quality weighting
- Analyst feed monitoring via ScrapeCreators

Usage:
    python scripts/ingest_news.py
    python scripts/ingest_news.py --dry-run
    python scripts/ingest_news.py --source yahoo
"""

import os
import sys
import re
import logging
import argparse
import hashlib
import unicodedata
import math
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
SCRAPECREATORS_API_KEY = os.getenv("SCRAPECREATORS_API_KEY")

if not DATABASE_URL:
    logger.error("DATABASE_URL not set")
    sys.exit(1)

# =============================================================================
# SOURCE QUALITY WEIGHTS
# =============================================================================

SOURCE_QUALITY = {
    # Official government sources (highest weight)
    "ustr": 1.0,
    "usda": 1.0,
    "epa": 1.0,
    "fed": 1.0,
    "eu commission": 1.0,
    "wto": 1.0,
    "conab": 1.0,
    "mapa": 1.0,
    "ndrc": 1.0,
    "mpob": 1.0,

    # Major wire services
    "reuters": 0.9,
    "bloomberg": 0.9,
    "dow jones": 0.9,

    # Industry specialists
    "agricensus": 0.85,
    "oil world": 0.85,
    "farmdoc": 0.85,
    "farm policy news": 0.85,
    "dtn": 0.8,
    "agrimoney": 0.8,

    # Analysts (via ScrapeCreators)
    "karen braun": 0.85,
    "arlan suderman": 0.85,
    "scott irwin": 0.9,
    "michael cordonnier": 0.85,
    "javier blas": 0.85,

    # General financial news
    "yahoo": 0.6,
    "polygon": 0.6,
    "cnbc": 0.6,
    "marketwatch": 0.6,

    # Default
    "unknown": 0.5,
}

# Specificity modifiers
SPECIFICITY_HIGH = ["decree", "enacted", "law passed", "ruling", "approved", "signed"]
SPECIFICITY_LOW = ["proposal", "draft", "discussing", "considering", "may", "might"]

# =============================================================================
# HALF-LIFE CONFIGURATION (in hours)
# =============================================================================

HALF_LIFE_HOURS = {
    "short": 24,      # 1 day - strikes, chokepoints
    "medium": 168,    # 1 week - mandates, policy
    "long": 720,      # 30 days - legislation
}

# =============================================================================
# CLASSIFICATION RULES WITH HALF-LIFE
# =============================================================================

CLASSIFICATION_RULES = {
    "china_demand_levers": {
        "bucket": "china",
        "half_life": "medium",
        "keywords": ["sinograin", "cofco", "ndrc soybean", "state reserves",
                     "crush margins", "dalian", "china import", "chinese demand",
                     "china soybean", "china vegoil"],
        "bullish": ["reserve stockpiles rebuild", "import quota boost",
                    "crush margin subsidies", "china buying"],
        "bearish": ["biosecurity import slowdowns", "tighter import licenses",
                    "state reserve releases", "china demand weak"],
    },
    "argentina_policy_fx": {
        "bucket": "fx",
        "half_life": "medium",
        "keywords": ["sojadolar", "retenciones", "rosario strike", "ciara-cec",
                     "puerto san lorenzo", "argentina soy", "argentina export"],
        "bullish": ["export taxes up", "soy dollar ends", "port blockades",
                    "trucker strikes", "argentina strike"],
        "bearish": ["export tax cuts", "fx incentives", "imf liberalization"],
    },
    "brazil_policy_infra": {
        "bucket": "substitutes",
        "half_life": "medium",
        "keywords": ["conab", "mapa", "santos", "arco norte", "ferrograo",
                     "ibama embargo", "br-163", "brazil soy", "paranagua"],
        "bullish": ["export licensing hiccups", "environmental enforcement",
                    "barge bottlenecks", "rail bottlenecks"],
        "bearish": ["logistics upgrades", "port privatizations", "brl strengthening"],
    },
    "us_policy": {
        "bucket": "tariff",
        "half_life": "long",
        "keywords": ["ustr", "rfs volumes", "jones act", "usace mississippi",
                     "ilwu", "stb rail", "us soybean", "farm bill"],
        "bullish": ["higher china tariffs", "retaliation risk", "rail strikes",
                    "port strikes", "mississippi draft limits"],
        "bearish": ["export credit guarantees", "grain inspection streamlining",
                    "lower rfs volumes"],
    },
    "biofuels_policy": {
        "bucket": "biofuel",
        "half_life": "medium",
        "keywords": ["b40 indonesia", "renovabio", "cbio", "lcfs", "saf",
                     "epa rvo", "biodiesel", "renewable diesel", "rin price",
                     "blending mandate", "45z", "b35", "rfs"],
        "bullish": ["b35", "b40", "biodiesel blend hikes", "lcfs credit",
                    "saf mandate", "45z credit", "rin rally"],
        "bearish": ["iluc", "weaker lcfs credit", "cap on crop-based",
                    "rin crash", "biofuel cap"],
    },
    "palm_oil_geopolitics": {
        "bucket": "palm",
        "half_life": "medium",
        "keywords": ["cpo export levy", "dmo", "mpob", "india edible oil duty",
                     "palm oil", "indonesia palm", "malaysia palm", "cpo price"],
        "bullish": ["export levies", "export bans", "labor shortages",
                    "esg import hurdles", "palm restriction"],
        "bearish": ["levy cuts", "export liberalization", "bumper output",
                    "india import duty cuts", "palm surplus"],
    },
    "black_sea_vegoils": {
        "bucket": "substitutes",
        "half_life": "short",
        "keywords": ["black sea corridor", "danube ports", "sunflower oil export",
                     "marine insurance", "ukraine grain", "odessa"],
        "bullish": ["corridor disruptions", "port strikes", "sanctions russian",
                    "shipping risk"],
        "bearish": ["corridor re-opening", "insured shipping", "sunflower floods market"],
    },
    "global_chokepoints": {
        "bucket": "energy",
        "half_life": "short",
        "keywords": ["panama canal transit", "bab el-mandeb", "houthi",
                     "war risk premiums", "red sea", "suez", "freight rates"],
        "bullish": ["red sea risk", "suez risk", "panama canal cuts",
                    "south china sea tension", "war risk"],
        "bearish": ["reroute subsidies", "canal rainfall recovery",
                    "naval escorts restore"],
    },
    "fertilizer_energy": {
        "bucket": "energy",
        "half_life": "medium",
        "keywords": ["belarus potash", "cf industries", "ammonia pipeline",
                     "urea tender", "fertilizer price", "natgas", "natural gas"],
        "bullish": ["sanctions", "plant outages", "potash restrictions",
                    "natgas spikes", "fertilizer shortage"],
        "bearish": ["sanction carve-outs", "new supply", "cheap gas",
                    "fertilizer surplus"],
    },
    "animal_disease": {
        "bucket": "crush",
        "half_life": "short",
        "keywords": ["asf china", "avian influenza", "hog herd", "moa china",
                     "african swine fever", "bird flu", "poultry disease"],
        "bullish": ["herd rebuild", "hog herd rebuild", "restocking"],
        "bearish": ["asf outbreak", "avian influenza outbreak", "culling",
                    "disease spread"],
    },
    "trade_disputes": {
        "bucket": "tariff",
        "half_life": "long",
        "keywords": ["antidumping soybean", "wto panel", "trq soybeans",
                     "sps measures", "trade dispute", "cvd", "countervailing"],
        "bullish": ["antidumping", "cvd duties", "new quotas", "sps barriers"],
        "bearish": ["bilateral deals", "tariff-rate quotas", "purchase commitments"],
    },
    "esg_deforestation": {
        "bucket": "palm",
        "half_life": "long",
        "keywords": ["eudr soy", "traceability polygon", "due diligence regulation",
                     "deforestation", "sustainability certification"],
        "bullish": ["strict traceability", "shipment delays", "cargo rejections",
                    "eudr enforcement"],
        "bearish": ["phased enforcement", "exemptions", "eudr delay"],
    },
    "labor_unrest": {
        "bucket": "crush",
        "half_life": "short",
        "keywords": ["port strike santos", "rosario piquete", "gulf export elevators",
                     "blockade", "trucker protest", "farmer blockade"],
        "bullish": ["port strikes", "trucker protests", "farmer blockades",
                    "labor action"],
        "bearish": ["strike settlements", "throughput guarantees", "strike ends"],
    },
    "cyber_infrastructure": {
        "bucket": "volatility",
        "half_life": "short",
        "keywords": ["ransomware port", "terminal outage", "customs it failure",
                     "ais spoofing", "cyber attack", "system outage"],
        "bullish": ["ransomware", "terminal outage", "customs failure",
                    "cyber attack"],
        "bearish": [],
    },
    "regulatory_approvals": {
        "bucket": "tariff",
        "half_life": "long",
        "keywords": ["soy trait approval", "glyphosate ban", "ctnbio",
                     "gmo approval", "herbicide ban"],
        "bullish": ["glyphosate ban", "delayed trait approvals", "withdrawals"],
        "bearish": ["rapid approvals", "alternative herbicide programs"],
    },
    "us_crush": {
        "bucket": "crush",
        "half_life": "medium",
        "keywords": ["nopa", "crush report", "soybean crush", "crush capacity",
                     "crush margins", "soy meal", "soybean meal", "crush rate"],
        "bullish": ["crush margins up", "strong crush demand", "capacity expansion",
                    "record crush"],
        "bearish": ["crush margins down", "weak meal demand", "plant closures",
                    "crush slowdown"],
    },
    "fed_monetary": {
        "bucket": "fed",
        "half_life": "medium",
        "keywords": ["federal reserve", "fomc", "interest rate", "powell",
                     "monetary policy", "rate hike", "rate cut", "fed funds"],
        "bullish": ["rate cut", "dovish", "pause", "fed pivot"],
        "bearish": ["rate hike", "hawkish", "tightening", "higher for longer"],
    },
    "fx_currency": {
        "bucket": "fx",
        "half_life": "short",
        "keywords": ["usd index", "dollar index", "dxy", "brl usd", "ars usd",
                     "cny usd", "yuan", "real", "peso", "currency"],
        "bullish": ["dollar weakness", "brl strength", "ars strength", "dxy down"],
        "bearish": ["dollar strength", "em selloff", "currency crisis", "dxy up"],
    },
    "energy_oil": {
        "bucket": "energy",
        "half_life": "short",
        "keywords": ["crude oil", "wti", "brent", "opec", "oil price",
                     "gasoline", "diesel", "energy prices"],
        "bullish": ["oil rally", "opec cut", "supply disruption", "oil surge"],
        "bearish": ["oil crash", "demand destruction", "oversupply", "oil plunge"],
    },
    "volatility_risk": {
        "bucket": "volatility",
        "half_life": "short",
        "keywords": ["vix", "volatility", "risk off", "flight to safety",
                     "market crash", "selloff", "panic", "fear index"],
        "bullish": ["vix spike", "risk off", "panic selling", "volatility surge"],
        "bearish": ["calm markets", "low vol", "risk on", "vix crush"],
    },
}

# Yahoo Finance RSS feeds
YAHOO_RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ZL=F&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ZS=F&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ZM=F&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=CL=F&region=US&lang=en-US",
]

# Analyst handles for ScrapeCreators
ANALYST_HANDLES = [
    {"handle": "kannbwx", "name": "Karen Braun", "focus": "Reuters commodities"},
    {"handle": "ArlanFF101", "name": "Arlan Suderman", "focus": "StoneX economist"},
    {"handle": "ScottIrwinUIUC", "name": "Scott Irwin", "focus": "UIUC ag economics"},
    {"handle": "SoybeanCorn", "name": "Michael Cordonnier", "focus": "South America"},
    {"handle": "JavierBlas", "name": "Javier Blas", "focus": "Bloomberg commodities"},
]


def normalize_text(text: str) -> str:
    """Normalize text for matching."""
    if not text:
        return ""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()
    return f" {cleaned} "


def get_source_quality(source: str, text: str) -> float:
    """Calculate source quality weight."""
    source_lower = source.lower() if source else ""
    text_lower = text.lower() if text else ""

    # Check for known sources
    for src, weight in SOURCE_QUALITY.items():
        if src in source_lower or src in text_lower:
            return weight

    return SOURCE_QUALITY["unknown"]


def get_specificity_modifier(text: str) -> float:
    """Get specificity modifier based on language."""
    text_lower = text.lower()

    for term in SPECIFICITY_HIGH:
        if term in text_lower:
            return 0.2  # Boost for specific/official language

    for term in SPECIFICITY_LOW:
        if term in text_lower:
            return -0.1  # Penalty for vague language

    return 0.0


def calculate_half_life_decay(published_at: datetime, half_life_type: str) -> float:
    """Calculate decay factor based on article age and half-life."""
    if not published_at:
        return 1.0

    hours_old = (datetime.now() - published_at).total_seconds() / 3600
    half_life_hours = HALF_LIFE_HOURS.get(half_life_type, HALF_LIFE_HOURS["medium"])

    # Exponential decay: 0.5^(t/half_life)
    decay = math.pow(0.5, hours_old / half_life_hours)
    return max(0.1, decay)  # Floor at 0.1


def check_cross_asset_boost(categories: List[Dict]) -> float:
    """Check for cross-asset signal amplification."""
    buckets_hit = set(c["bucket"] for c in categories)
    directions = [c["direction"] for c in categories]

    boost = 0.0

    # Oil + Biofuel = double signal for soy oil
    if "energy" in buckets_hit and "biofuel" in buckets_hit:
        if directions.count("bullish") >= 2:
            boost += 0.3
        elif directions.count("bearish") >= 2:
            boost -= 0.3

    # China + Tariff = amplified trade signal
    if "china" in buckets_hit and "tariff" in buckets_hit:
        if "bullish" in directions:
            boost += 0.2
        if "bearish" in directions:
            boost -= 0.2

    # Palm + Substitutes = veg oil competition signal
    if "palm" in buckets_hit and "substitutes" in buckets_hit:
        boost += 0.15  # Competition news is generally bullish for soy oil

    return boost


def classify_article(title: str, summary: str, source: str = "",
                     published_at: datetime = None) -> Dict[str, Any]:
    """
    Classify article with full scoring pipeline.

    Returns:
        {
            "buckets": ["china", "tariff"],
            "direction": "bullish",
            "raw_impact": 0.65,
            "decayed_impact": 0.52,
            "source_quality": 0.85,
            "specificity_mod": 0.1,
            "cross_asset_boost": 0.2,
            "final_score": 0.72,
            "categories": [...]
        }
    """
    text = normalize_text(f"{title} {summary}")
    full_text = f"{title} {summary}"

    matches = []
    buckets_hit = set()
    total_raw_impact = 0.0

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

        # Determine direction and base impact
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
        half_life = rules.get("half_life", "medium")
        buckets_hit.add(bucket)
        total_raw_impact += impact

        matches.append({
            "category": category,
            "bucket": bucket,
            "half_life": half_life,
            "direction": direction,
            "impact": round(impact, 3),
            "keyword_hits": keyword_hits,
            "bullish_hits": bullish_hits,
            "bearish_hits": bearish_hits,
        })

    # Calculate modifiers
    source_quality = get_source_quality(source, full_text)
    specificity_mod = get_specificity_modifier(full_text)
    cross_asset_boost = check_cross_asset_boost(matches)

    # Calculate half-life decay (use shortest half-life if multiple categories)
    decay_factor = 1.0
    if matches and published_at:
        half_lives = [m.get("half_life", "medium") for m in matches]
        # Use shortest half-life for decay
        if "short" in half_lives:
            decay_factor = calculate_half_life_decay(published_at, "short")
        elif "medium" in half_lives:
            decay_factor = calculate_half_life_decay(published_at, "medium")
        else:
            decay_factor = calculate_half_life_decay(published_at, "long")

    # Calculate final score
    decayed_impact = total_raw_impact * decay_factor
    adjusted_impact = decayed_impact * source_quality * (1 + specificity_mod)
    final_score = adjusted_impact + cross_asset_boost

    # Overall direction
    if final_score > 0.1:
        overall_direction = "bullish"
    elif final_score < -0.1:
        overall_direction = "bearish"
    else:
        overall_direction = "neutral"

    return {
        "buckets": sorted(buckets_hit),
        "direction": overall_direction,
        "raw_impact": round(total_raw_impact, 3),
        "decayed_impact": round(decayed_impact, 3),
        "decay_factor": round(decay_factor, 3),
        "source_quality": round(source_quality, 3),
        "specificity_mod": round(specificity_mod, 3),
        "cross_asset_boost": round(cross_asset_boost, 3),
        "final_score": round(final_score, 4),
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

        # Parsed/classified news with full scoring
        cur.execute("""
            CREATE TABLE IF NOT EXISTS parsed_news (
                id SERIAL PRIMARY KEY,
                article_id VARCHAR(64) REFERENCES raw_news_articles(article_id),
                buckets TEXT[] NOT NULL,
                direction VARCHAR(20),
                raw_impact FLOAT,
                decayed_impact FLOAT,
                decay_factor FLOAT,
                source_quality FLOAT,
                cross_asset_boost FLOAT,
                final_score FLOAT,
                classification JSONB,
                processed_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(article_id)
            );
            CREATE INDEX IF NOT EXISTS idx_parsed_buckets ON parsed_news USING GIN(buckets);
            CREATE INDEX IF NOT EXISTS idx_parsed_direction ON parsed_news(direction);
            CREATE INDEX IF NOT EXISTS idx_parsed_score ON parsed_news(final_score);
        """)

        # News sentiment by bucket (daily aggregates)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS news_sentiment_daily (
                id SERIAL PRIMARY KEY,
                as_of_date DATE NOT NULL,
                bucket VARCHAR(50) NOT NULL,
                article_count INT,
                bullish_count INT,
                bearish_count INT,
                neutral_count INT,
                avg_raw_impact FLOAT,
                avg_decayed_impact FLOAT,
                avg_source_quality FLOAT,
                net_sentiment FLOAT,
                weighted_score FLOAT,
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

                    # Detect source from publisher
                    publisher = item.get("publisher", {})
                    source = publisher.get("name", "polygon") if publisher else "polygon"

                    articles.append({
                        'title': item.get('title', ''),
                        'summary': item.get('description', ''),
                        'url': item.get('article_url', ''),
                        'source': source,
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

    def fetch_scrapecreators_analysts(self) -> List[Dict[str, Any]]:
        """Fetch analyst tweets via ScrapeCreators API."""
        if not SCRAPECREATORS_API_KEY:
            logger.info("  ScrapeCreators: API key not set, skipping analysts")
            return []

        articles = []
        base_url = "https://api.scrapecreators.com/v1/twitter/user/tweets"

        for analyst in ANALYST_HANDLES:
            try:
                params = {
                    "username": analyst["handle"],
                    "limit": 10,
                }
                headers = {
                    "Authorization": f"Bearer {SCRAPECREATORS_API_KEY}",
                }

                resp = requests.get(base_url, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
                data = resp.json()

                for tweet in data.get("tweets", []):
                    created_at = None
                    if tweet.get("created_at"):
                        try:
                            created_at = datetime.fromisoformat(
                                tweet["created_at"].replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                        except ValueError:
                            created_at = datetime.now()

                    articles.append({
                        'title': tweet.get('text', '')[:200],
                        'summary': tweet.get('text', ''),
                        'url': f"https://twitter.com/{analyst['handle']}/status/{tweet.get('id', '')}",
                        'source': analyst["name"],
                        'author': analyst["name"],
                        'published_at': created_at,
                        'symbols': [],
                        'keywords': [],
                    })

                logger.info(f"    {analyst['name']}: {len(data.get('tweets', []))} tweets")

            except Exception as e:
                logger.warning(f"  ScrapeCreators error for {analyst['handle']}: {e}")
                continue

        logger.info(f"  ScrapeCreators: fetched {len(articles)} analyst posts")
        return articles

    def store_and_classify(self, articles: List[Dict[str, Any]]) -> Dict[str, int]:
        """Store raw articles and classify with full scoring."""
        if not articles:
            return {"raw": 0, "classified": 0}

        if self.dry_run:
            for article in articles[:5]:
                result = classify_article(
                    article.get('title', ''),
                    article.get('summary', ''),
                    article.get('source', ''),
                    article.get('published_at')
                )
                logger.info(f"  [DRY RUN] {article.get('title', '')[:50]}...")
                logger.info(f"    Buckets: {result['buckets']}")
                logger.info(f"    Direction: {result['direction']}, Score: {result['final_score']}")
                logger.info(f"    Source Quality: {result['source_quality']}, Decay: {result['decay_factor']}")
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

                    # Classify with full scoring
                    classification = classify_article(
                        article.get('title', ''),
                        article.get('summary', ''),
                        article.get('source', ''),
                        article.get('published_at')
                    )

                    # Store classification
                    if classification['buckets']:
                        cur.execute("""
                            INSERT INTO parsed_news (
                                article_id, buckets, direction, raw_impact,
                                decayed_impact, decay_factor, source_quality,
                                cross_asset_boost, final_score, classification
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (article_id) DO UPDATE SET
                                buckets = EXCLUDED.buckets,
                                direction = EXCLUDED.direction,
                                raw_impact = EXCLUDED.raw_impact,
                                decayed_impact = EXCLUDED.decayed_impact,
                                decay_factor = EXCLUDED.decay_factor,
                                source_quality = EXCLUDED.source_quality,
                                cross_asset_boost = EXCLUDED.cross_asset_boost,
                                final_score = EXCLUDED.final_score,
                                classification = EXCLUDED.classification,
                                processed_at = NOW()
                        """, (
                            article_id,
                            classification['buckets'],
                            classification['direction'],
                            classification['raw_impact'],
                            classification['decayed_impact'],
                            classification['decay_factor'],
                            classification['source_quality'],
                            classification['cross_asset_boost'],
                            classification['final_score'],
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
        """Aggregate daily sentiment by bucket with weighted scoring."""
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
                p.raw_impact,
                p.decayed_impact,
                p.source_quality,
                p.final_score
            FROM parsed_news p
            JOIN raw_news_articles r ON p.article_id = r.article_id
            WHERE r.published_at::date = %s
        """, [today])

        bucket_stats = {}
        for row in cur.fetchall():
            bucket, direction, raw_impact, decayed_impact, source_quality, final_score = row
            if bucket not in bucket_stats:
                bucket_stats[bucket] = {
                    "count": 0, "bullish": 0, "bearish": 0, "neutral": 0,
                    "total_raw": 0.0, "total_decayed": 0.0,
                    "total_source_quality": 0.0, "total_weighted": 0.0
                }
            bucket_stats[bucket]["count"] += 1
            bucket_stats[bucket][direction] = bucket_stats[bucket].get(direction, 0) + 1
            bucket_stats[bucket]["total_raw"] += raw_impact or 0
            bucket_stats[bucket]["total_decayed"] += decayed_impact or 0
            bucket_stats[bucket]["total_source_quality"] += source_quality or 0
            bucket_stats[bucket]["total_weighted"] += final_score or 0

        # Store aggregates
        for bucket, stats in bucket_stats.items():
            count = stats["count"]
            avg_raw = stats["total_raw"] / count if count > 0 else 0
            avg_decayed = stats["total_decayed"] / count if count > 0 else 0
            avg_source = stats["total_source_quality"] / count if count > 0 else 0
            net_sentiment = (stats["bullish"] - stats["bearish"]) / count if count > 0 else 0
            weighted_score = stats["total_weighted"] / count if count > 0 else 0

            cur.execute("""
                INSERT INTO news_sentiment_daily (
                    as_of_date, bucket, article_count, bullish_count,
                    bearish_count, neutral_count, avg_raw_impact,
                    avg_decayed_impact, avg_source_quality, net_sentiment,
                    weighted_score
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (as_of_date, bucket) DO UPDATE SET
                    article_count = EXCLUDED.article_count,
                    bullish_count = EXCLUDED.bullish_count,
                    bearish_count = EXCLUDED.bearish_count,
                    neutral_count = EXCLUDED.neutral_count,
                    avg_raw_impact = EXCLUDED.avg_raw_impact,
                    avg_decayed_impact = EXCLUDED.avg_decayed_impact,
                    avg_source_quality = EXCLUDED.avg_source_quality,
                    net_sentiment = EXCLUDED.net_sentiment,
                    weighted_score = EXCLUDED.weighted_score,
                    created_at = NOW()
            """, (
                today, bucket, count, stats["bullish"],
                stats["bearish"], stats["neutral"], avg_raw,
                avg_decayed, avg_source, net_sentiment, weighted_score
            ))

        self.pg.commit()
        cur.close()
        logger.info(f"  Updated sentiment for {len(bucket_stats)} buckets")

    def run(self, source: str = "all"):
        """Run news ingestion and classification."""
        logger.info("=" * 60)
        logger.info("NEWS INGESTION & CLASSIFICATION (Full Pipeline)")
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

        if source in ["all", "analysts"]:
            logger.info("\nFetching from ScrapeCreators (analysts)...")
            all_articles.extend(self.fetch_scrapecreators_analysts())

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
        logger.info("\nStoring and classifying with full scoring...")
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
    parser.add_argument("--source", choices=["all", "yahoo", "polygon", "analysts"],
                        default="all")
    args = parser.parse_args()

    ingester = NewsIngester(dry_run=args.dry_run)
    ingester.run(source=args.source)


if __name__ == "__main__":
    main()
