#!/usr/bin/env python3
"""
ZINC-FUSION Social Media Intelligence Scraper
==============================================
Pulls social posts from Twitter/X, Facebook, LinkedIn via ScrapeCreators API.
Routes to Big-11 specialist buckets and stores in raw.news_articles_1d.

DEPLOYMENT: Railway/Server cron job - NOT for local Mac execution.

Schedule (recommended):
    - HIGH_ALPHA (Trump, USTR, China): Every 5 minutes
    - REGULATORY (USDA, EPA, exchanges): Every 15 minutes
    - DISCOVERY (industry, associations): Every 60 minutes

Cron examples:
    # High-alpha every 5 minutes
    */5 * * * * python scripts/scrape_social_intel.py --tier high

    # Regulatory every 15 minutes
    */15 * * * * python scripts/scrape_social_intel.py --tier regulatory

    # Discovery hourly
    0 * * * * python scripts/scrape_social_intel.py --tier discovery

    # Full sweep daily at 4 AM ET
    0 4 * * * python scripts/scrape_social_intel.py --tier all --backfill

Environment Variables Required:
    DATABASE_URL - Prisma Postgres connection string
    SCRAPECREATORS_API_KEY - ScrapeCreators API key (required)

Usage:
    python scripts/scrape_social_intel.py --tier high        # Trump, USTR, China
    python scripts/scrape_social_intel.py --tier regulatory  # Government agencies
    python scripts/scrape_social_intel.py --tier discovery   # Industry & associations
    python scripts/scrape_social_intel.py --tier all         # Everything
    python scripts/scrape_social_intel.py --backfill         # Last 100 tweets each
    python scripts/scrape_social_intel.py --dry-run          # Preview only
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
import requests

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.fusion.api.news_sentiment import classify_article

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / f"social_intel_{datetime.now().strftime('%Y%m%d')}.log"),
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# SCRAPECREATORS API CONFIGURATION
# =============================================================================

SC_BASE_URL = "https://api.scrapecreators.com/v1"

# Request headers template
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# =============================================================================
# SOCIAL HANDLE REGISTRY - Organized by Priority Tier
# =============================================================================

# HIGH_ALPHA: 1-5 minute polling - market-moving sources
HIGH_ALPHA_TWITTER = [
    # Trump Administration & Executive
    {"handle": "realDonaldTrump", "name": "Donald Trump", "specialist": "trump_effect", "priority": 0},
    {"handle": "DonaldJTrumpJr", "name": "Donald Trump Jr", "specialist": "trump_effect", "priority": 0},
    {"handle": "EricTrump", "name": "Eric Trump", "specialist": "trump_effect", "priority": 0},
    {"handle": "POTUS", "name": "POTUS", "specialist": "trump_effect", "priority": 0},
    {"handle": "VP", "name": "Vice President", "specialist": "trump_effect", "priority": 0},
    {"handle": "WhiteHouse", "name": "White House", "specialist": "trump_effect", "priority": 0},
    # Trade Policy
    {"handle": "USTR", "name": "US Trade Representative", "specialist": "tariff", "priority": 0},
    {"handle": "USTreasury", "name": "US Treasury", "specialist": "tariff", "priority": 0},
    {"handle": "SecYellen", "name": "Sec Yellen", "specialist": "tariff", "priority": 0},
    # Immigration/Labor
    {"handle": "ICEgov", "name": "ICE", "specialist": "trump_effect", "priority": 0},
    {"handle": "CBP", "name": "CBP", "specialist": "trump_effect", "priority": 0},
    {"handle": "DHSgov", "name": "DHS", "specialist": "trump_effect", "priority": 0},
    # China State Media & Trade
    {"handle": "MOFCOMChina", "name": "MOFCOM China", "specialist": "china", "priority": 0},
    {"handle": "GACC_China", "name": "China Customs", "specialist": "china", "priority": 0},
    {"handle": "cofcointl", "name": "COFCO", "specialist": "china", "priority": 0},
    {"handle": "sinochem_news", "name": "Sinochem", "specialist": "china", "priority": 0},
    {"handle": "sinograin_china", "name": "Sinograin", "specialist": "china", "priority": 0},
    {"handle": "MFA_China", "name": "China Foreign Ministry", "specialist": "china", "priority": 0},
    {"handle": "ChinaEmbinUS", "name": "China Embassy US", "specialist": "china", "priority": 0},
]

# REGULATORY: 10-30 minute polling - government & exchanges
REGULATORY_TWITTER = [
    # US Agriculture
    {"handle": "USDA", "name": "USDA", "specialist": "crush", "priority": 1},
    {"handle": "SecVilsack", "name": "USDA Secretary", "specialist": "crush", "priority": 1},
    {"handle": "USDA_NASS", "name": "USDA NASS", "specialist": "crush", "priority": 1},
    # Biofuel/Energy Policy
    {"handle": "EPA", "name": "EPA", "specialist": "biofuel", "priority": 1},
    {"handle": "EnergyGov", "name": "Dept of Energy", "specialist": "energy", "priority": 1},
    {"handle": "CleanFuelsDA", "name": "RFA", "specialist": "biofuel", "priority": 1},
    {"handle": "BiodieselNow", "name": "NBB", "specialist": "biofuel", "priority": 1},
    {"handle": "EthanolRFA", "name": "Ethanol RFA", "specialist": "biofuel", "priority": 1},
    {"handle": "CARB", "name": "California ARB", "specialist": "biofuel", "priority": 1},
    # Exchanges
    {"handle": "CMEGroup", "name": "CME Group", "specialist": "volatility", "priority": 1},
    {"handle": "ICE_Markets", "name": "ICE", "specialist": "volatility", "priority": 1},
    {"handle": "nasdaq", "name": "Nasdaq", "specialist": "volatility", "priority": 1},
    {"handle": "CBOTExchange", "name": "CBOT", "specialist": "crush", "priority": 1},
    # Congress Ag Committees
    {"handle": "SenateAg", "name": "Senate Ag Committee", "specialist": "tariff", "priority": 1},
    {"handle": "HouseAg", "name": "House Ag Committee", "specialist": "tariff", "priority": 1},
    {"handle": "ChairmanThompson", "name": "House Ag Chair", "specialist": "tariff", "priority": 1},
    {"handle": "SenBooker", "name": "Sen Booker", "specialist": "tariff", "priority": 1},
    {"handle": "RepAustin", "name": "Rep Austin", "specialist": "tariff", "priority": 1},
    {"handle": "SenJoniErnst", "name": "Sen Joni Ernst", "specialist": "tariff", "priority": 1},
    {"handle": "ChuckGrassley", "name": "Sen Grassley", "specialist": "tariff", "priority": 1},
    {"handle": "SenAmyKlobuchar", "name": "Sen Klobuchar", "specialist": "tariff", "priority": 1},
    {"handle": "SenatorFischer", "name": "Sen Fischer", "specialist": "tariff", "priority": 1},
    {"handle": "RepFeenstra", "name": "Rep Feenstra", "specialist": "tariff", "priority": 1},
    {"handle": "RepCindy_Axne", "name": "Rep Axne", "specialist": "tariff", "priority": 1},
    # Brazil Agriculture
    {"handle": "MinAgricultura", "name": "Brazil Ag Ministry", "specialist": "crush", "priority": 1},
    {"handle": "abioveoficial", "name": "ABIOVE Brazil", "specialist": "crush", "priority": 1},
    {"handle": "AprosojaBrasil", "name": "Aprosoja Brazil", "specialist": "crush", "priority": 1},
    {"handle": "conab_oficial", "name": "CONAB", "specialist": "crush", "priority": 1},
    {"handle": "anpbrasil", "name": "ANP Brazil", "specialist": "biofuel", "priority": 1},
    {"handle": "ubrabio", "name": "UBRABIO", "specialist": "biofuel", "priority": 1},
    # Argentina Agriculture
    {"handle": "CIARA_CEC", "name": "CIARA Argentina", "specialist": "crush", "priority": 1},
    {"handle": "ArgentinaGob", "name": "Argentina Govt", "specialist": "crush", "priority": 1},
    {"handle": "BCRAmercados", "name": "Rosario Exchange", "specialist": "crush", "priority": 1},
    {"handle": "MAGyPArgentina", "name": "Argentina MAGyP", "specialist": "crush", "priority": 1},
    {"handle": "INDEC_Argentina", "name": "INDEC Argentina", "specialist": "crush", "priority": 1},
    {"handle": "CancelleriaArg", "name": "Argentina Foreign", "specialist": "tariff", "priority": 1},
    # Palm Oil
    {"handle": "mpobmalaysia", "name": "MPOB Malaysia", "specialist": "palm", "priority": 1},
    {"handle": "gapki_id", "name": "GAPKI Indonesia", "specialist": "palm", "priority": 1},
    {"handle": "icopalmoil", "name": "ICOPA", "specialist": "palm", "priority": 1},
    # EU Policy
    {"handle": "EU_Commission", "name": "EU Commission", "specialist": "tariff", "priority": 1},
    {"handle": "EU_CouncilEU", "name": "EU Council", "specialist": "tariff", "priority": 1},
    # China State Media
    {"handle": "CCTVNews", "name": "CCTV News", "specialist": "china", "priority": 1},
    {"handle": "XinhuaNews", "name": "Xinhua News", "specialist": "china", "priority": 1},
    {"handle": "PDChina", "name": "People's Daily", "specialist": "china", "priority": 1},
    {"handle": "CGTNOfficial", "name": "CGTN", "specialist": "china", "priority": 1},
    {"handle": "ChinaDaily", "name": "China Daily", "specialist": "china", "priority": 1},
]

# DISCOVERY: 30-60 minute polling - industry & associations
DISCOVERY_TWITTER = [
    # Commodity Majors
    {"handle": "ADMCorp", "name": "ADM", "specialist": "crush", "priority": 2},
    {"handle": "BungeGlobal", "name": "Bunge", "specialist": "crush", "priority": 2},
    {"handle": "Cargill", "name": "Cargill", "specialist": "crush", "priority": 2},
    {"handle": "LouisDreyfus", "name": "Louis Dreyfus", "specialist": "crush", "priority": 2},
    {"handle": "Viterra_Global", "name": "Viterra", "specialist": "crush", "priority": 2},
    {"handle": "OilWorld", "name": "Oil World", "specialist": "crush", "priority": 2},
    {"handle": "FCStoneGlobal", "name": "FCStone", "specialist": "crush", "priority": 2},
    {"handle": "Informa_Agri", "name": "Informa Agri", "specialist": "crush", "priority": 2},
    # US Farm Associations
    {"handle": "FarmBureau", "name": "Farm Bureau", "specialist": "crush", "priority": 2},
    {"handle": "NationalCorn", "name": "National Corn", "specialist": "crush", "priority": 2},
    {"handle": "ASA_Soybeans", "name": "ASA Soybeans", "specialist": "crush", "priority": 2},
    {"handle": "NOPA_News", "name": "NOPA", "specialist": "crush", "priority": 2},
    {"handle": "NationalGrange", "name": "National Grange", "specialist": "crush", "priority": 2},
    {"handle": "NFUnion", "name": "NFU", "specialist": "crush", "priority": 2},
    {"handle": "USGrains", "name": "US Grains Council", "specialist": "crush", "priority": 2},
    {"handle": "USSEC", "name": "US Soybean Export", "specialist": "crush", "priority": 2},
    # Ag Media
    {"handle": "corn_soydigest", "name": "Corn & Soy Digest", "specialist": "crush", "priority": 2},
    {"handle": "SuccessfulFarm", "name": "Successful Farming", "specialist": "crush", "priority": 2},
    {"handle": "FarmProgress", "name": "Farm Progress", "specialist": "crush", "priority": 2},
    {"handle": "AgWeb", "name": "AgWeb", "specialist": "crush", "priority": 2},
    {"handle": "dtnpf", "name": "DTN Progressive Farmer", "specialist": "crush", "priority": 2},
    {"handle": "canalrural", "name": "Canal Rural", "specialist": "crush", "priority": 2},
    {"handle": "noticiasagri", "name": "Noticias Agri", "specialist": "crush", "priority": 2},
    {"handle": "agrolink", "name": "Agrolink", "specialist": "crush", "priority": 2},
    {"handle": "ruralbr", "name": "Rural BR", "specialist": "crush", "priority": 2},
    # Weather
    {"handle": "NOAA", "name": "NOAA", "specialist": "crush", "priority": 2},
    {"handle": "NWS", "name": "NWS", "specialist": "crush", "priority": 2},
    {"handle": "NOAAClimate", "name": "NOAA Climate", "specialist": "crush", "priority": 2},
    {"handle": "WorldWeather", "name": "World Weather", "specialist": "crush", "priority": 2},
    {"handle": "AccuWeather", "name": "AccuWeather", "specialist": "crush", "priority": 2},
    {"handle": "WeatherChannel", "name": "Weather Channel", "specialist": "crush", "priority": 2},
    {"handle": "CommodityWX", "name": "Commodity Weather", "specialist": "crush", "priority": 2},
    {"handle": "DroughtGov", "name": "US Drought Monitor", "specialist": "crush", "priority": 2},
    # Think Tanks
    {"handle": "Heritage", "name": "Heritage Foundation", "specialist": "tariff", "priority": 2},
    {"handle": "AEI", "name": "AEI", "specialist": "tariff", "priority": 2},
    {"handle": "BrookingsInst", "name": "Brookings", "specialist": "tariff", "priority": 2},
    {"handle": "CatoInstitute", "name": "Cato Institute", "specialist": "tariff", "priority": 2},
    {"handle": "EconomicPolicy", "name": "EPI", "specialist": "tariff", "priority": 2},
    {"handle": "taxpolicyctr", "name": "Tax Policy Center", "specialist": "tariff", "priority": 2},
    {"handle": "CropLifeAmerica", "name": "CropLife America", "specialist": "crush", "priority": 2},
    {"handle": "bioenergyassoc", "name": "Bioenergy Assoc", "specialist": "biofuel", "priority": 2},
    {"handle": "GrowthEnergy", "name": "Growth Energy", "specialist": "biofuel", "priority": 2},
    # Financial Media
    {"handle": "CNBC", "name": "CNBC", "specialist": "volatility", "priority": 2},
    {"handle": "BloombergNews", "name": "Bloomberg", "specialist": "volatility", "priority": 2},
    {"handle": "Reuters", "name": "Reuters", "specialist": "volatility", "priority": 2},
    {"handle": "WSJ", "name": "WSJ", "specialist": "volatility", "priority": 2},
    {"handle": "MarketWatch", "name": "MarketWatch", "specialist": "volatility", "priority": 2},
    {"handle": "FT", "name": "Financial Times", "specialist": "volatility", "priority": 2},
    {"handle": "AgFunderNews", "name": "AgFunder", "specialist": "crush", "priority": 2},
    {"handle": "foodandagtech", "name": "Food & Ag Tech", "specialist": "crush", "priority": 2},
    {"handle": "AgriPulse", "name": "Agri-Pulse", "specialist": "crush", "priority": 2},
    {"handle": "FarmFutures", "name": "Farm Futures", "specialist": "crush", "priority": 2},
    {"handle": "ProFarmer", "name": "Pro Farmer", "specialist": "crush", "priority": 2},
    {"handle": "DowJonesAgNews", "name": "DJ Ag News", "specialist": "crush", "priority": 2},
    # Substitutes (Canola, Sunflower)
    {"handle": "CanolaCouncil", "name": "Canola Council", "specialist": "substitutes", "priority": 2},
]

# Commodity analyst Twitter handles
ANALYST_TWITTER = [
    {"handle": "kannbwx", "name": "Karen Braun", "specialist": "crush", "priority": 1},
    {"handle": "ArlanFF101", "name": "Arlan Suderman", "specialist": "crush", "priority": 1},
    {"handle": "ScottIrwinUIUC", "name": "Scott Irwin", "specialist": "biofuel", "priority": 1},
    {"handle": "SoybeanCorn", "name": "Dr. Cordonnier", "specialist": "crush", "priority": 1},
    {"handle": "JavierBlas", "name": "Javier Blas", "specialist": "energy", "priority": 1},
]

# Facebook profiles (institutional only)
FACEBOOK_PROFILES = [
    {"profile": "USDA", "name": "USDA", "specialist": "crush", "priority": 1},
    {"profile": "EPA", "name": "EPA", "specialist": "biofuel", "priority": 1},
    {"profile": "AmericanSoybeanAssociation", "name": "ASA", "specialist": "crush", "priority": 2},
    {"profile": "NationalBiodieselBoard", "name": "NBB", "specialist": "biofuel", "priority": 2},
    {"profile": "CMEGroup", "name": "CME Group", "specialist": "volatility", "priority": 2},
    {"profile": "BungeGlobal", "name": "Bunge", "specialist": "crush", "priority": 2},
    {"profile": "CargillInc", "name": "Cargill", "specialist": "crush", "priority": 2},
    {"profile": "ADM", "name": "ADM", "specialist": "crush", "priority": 2},
]

# LinkedIn profiles (institutional only)
LINKEDIN_PROFILES = [
    {"company": "usda", "name": "USDA", "specialist": "crush", "priority": 2},
    {"company": "epa", "name": "EPA", "specialist": "biofuel", "priority": 2},
    {"company": "adm", "name": "ADM", "specialist": "crush", "priority": 2},
    {"company": "bunge", "name": "Bunge", "specialist": "crush", "priority": 2},
    {"company": "cargill", "name": "Cargill", "specialist": "crush", "priority": 2},
    {"company": "louis-dreyfus-company", "name": "Louis Dreyfus", "specialist": "crush", "priority": 2},
    {"company": "cme-group", "name": "CME Group", "specialist": "volatility", "priority": 2},
    {"company": "ice-intercontinental-exchange", "name": "ICE", "specialist": "volatility", "priority": 2},
]

# Truth Social profiles
TRUTH_SOCIAL_PROFILES = [
    {"handle": "realDonaldTrump", "name": "Donald Trump", "specialist": "trump_effect", "priority": 0},
]

# =============================================================================
# KEYWORD RELEVANCE SCORING
# =============================================================================

HIGH_VALUE_KEYWORDS = [
    # Trade Policy
    "tariff", "section 301", "quota", "TRQ", "retaliation", "sanctions",
    # Biofuel Policy
    "RFS", "RIN", "LCFS", "HVO", "HEFA", "SAF", "B30", "B40", "45z",
    # Palm/CPO
    "CPO", "MPOB", "export levy", "DMO",
    # Labor/Immigration
    "H-2A", "I-9", "raid",
    # China Trade
    "COFCO", "Sinograin", "tender", "auction", "state reserve",
    # Weather/Crop
    "drought", "harvest", "crushing", "basis", "FOB premium",
    # Core Commodities
    "soybean oil", "palm oil", "biodiesel", "renewable diesel",
    # Macro
    "trade war", "china imports", "brazil exports", "argentina production",
]

# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================

def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def compute_hash(content: str, source: str, platform: str) -> str:
    """Compute unique hash for post deduplication."""
    text = f"{content or ''}{source or ''}{platform}"
    return hashlib.sha256(text.encode()).hexdigest()[:64]


def post_exists(conn, content_hash: str) -> bool:
    """Check if post already exists by content hash."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT 1 FROM "raw"."news_articles_1d" WHERE content_hash = %s LIMIT 1',
            (content_hash,)
        )
        return cur.fetchone() is not None


def insert_post(conn, post: Dict[str, Any]) -> bool:
    """Insert social post into database."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO "raw"."news_articles_1d"
                (as_of_date, headline, content, source, bucket_name, zl_sentiment,
                 is_trump_related, content_hash, url, ingested_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (content_hash) DO NOTHING
            """, (
                post["as_of_date"],
                post["headline"][:500] if post["headline"] else None,
                post["content"][:10000] if post["content"] else None,
                post["source"],
                post.get("bucket_name"),
                post.get("zl_sentiment"),
                post.get("is_trump_related", False),
                post["content_hash"],
                post.get("url"),
            ))
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Failed to insert post: {e}")
        return False


# =============================================================================
# SCRAPECREATORS API FUNCTIONS
# =============================================================================

def get_api_key() -> Optional[str]:
    """Get ScrapeCreators API key from environment."""
    return os.getenv("SCRAPECREATORS_API_KEY")


def fetch_twitter_user_tweets(handle: str, api_key: str, limit: int = 20) -> List[Dict]:
    """
    Fetch tweets from a Twitter/X user via ScrapeCreators.

    API Endpoint: GET /v1/twitter/user-tweets
    """
    url = f"{SC_BASE_URL}/twitter/user-tweets"
    headers = {**HEADERS, "x-api-key": api_key}
    params = {
        "handle": handle,
        "limit": limit,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("tweets", data.get("data", []))
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.warning(f"Twitter user not found: @{handle}")
        elif e.response.status_code == 429:
            logger.warning(f"Rate limited on @{handle}")
        else:
            logger.error(f"HTTP error fetching @{handle}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching Twitter @{handle}: {e}")
        return []


def fetch_facebook_posts(profile: str, api_key: str, limit: int = 10) -> List[Dict]:
    """
    Fetch posts from a Facebook profile via ScrapeCreators.

    Note: Facebook endpoints may not be available - check API docs.
    """
    # Facebook scraping not currently available in this API tier
    logger.debug(f"Facebook scraping skipped for {profile} - not available in current API")
    return []


def fetch_linkedin_posts(company: str, api_key: str, limit: int = 10) -> List[Dict]:
    """
    Fetch posts from a LinkedIn company via ScrapeCreators.

    Note: LinkedIn endpoints may not be available - check API docs.
    """
    # LinkedIn scraping not currently available in this API tier
    logger.debug(f"LinkedIn scraping skipped for {company} - not available in current API")
    return []


def fetch_truthsocial_posts(handle: str, api_key: str, limit: int = 20) -> List[Dict]:
    """
    Fetch posts from a Truth Social user via ScrapeCreators.

    Note: Truth Social endpoints may not be available - check API docs.
    """
    # Truth Social scraping not currently available in this API tier
    logger.debug(f"Truth Social scraping skipped for {handle} - not available in current API")
    return []


# =============================================================================
# POST PROCESSING
# =============================================================================

def parse_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats from social platforms."""
    if not date_str:
        return None

    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%a %b %d %H:%M:%S %z %Y",  # Twitter format
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    return None


def is_trump_related(text: str) -> bool:
    """Check if post mentions Trump or related keywords."""
    import re
    patterns = [
        r"\btrump\b",
        r"\btruth\s*social\b",
        r"\bmar-?a-?lago\b",
        r"\bmaga\b",
        r"\bexecutive\s*order\b",
    ]
    combined = "|".join(patterns)
    return bool(re.search(combined, text.lower()))


def calculate_relevance_score(text: str) -> float:
    """Calculate relevance score based on keyword matches."""
    text_lower = text.lower()
    score = 0.0
    for keyword in HIGH_VALUE_KEYWORDS:
        if keyword.lower() in text_lower:
            score += 0.1
    return min(1.0, score)


def process_twitter_post(tweet: Dict, source_info: Dict) -> Optional[Dict[str, Any]]:
    """Process a Twitter tweet into standardized format."""
    # ScrapeCreators returns nested structure: tweet.legacy.full_text or tweet.note_tweet
    legacy = tweet.get("legacy", {})
    content = legacy.get("full_text", "")

    # Check for extended note_tweet content
    note_tweet = tweet.get("note_tweet", {})
    note_results = note_tweet.get("note_tweet_results", {}).get("result", {})
    if note_results.get("text"):
        content = note_results["text"]

    if not content:
        # Fallback to direct fields
        content = tweet.get("text", tweet.get("full_text", ""))

    if not content:
        return None

    # Get created_at from legacy
    created_at = legacy.get("created_at", tweet.get("created_at"))
    pub_date = parse_date(created_at) or datetime.now()
    headline = content[:100] + "..." if len(content) > 100 else content

    # Get tweet ID
    tweet_id = tweet.get("rest_id", legacy.get("id_str", tweet.get("id", "")))

    # Classify using rule-based system
    article_data = {
        "title": headline,
        "body": content,
        "source": f"twitter_{source_info['handle']}",
    }
    classification = classify_article(article_data)
    bucket = classification["alert_buckets"][0] if classification["alert_buckets"] else None

    trump_related = is_trump_related(content) or source_info.get("specialist") == "trump_effect"

    return {
        "as_of_date": pub_date.date(),
        "headline": headline,
        "content": content,
        "source": f"twitter_{source_info['handle']}",
        "bucket_name": bucket or source_info["specialist"],
        "zl_sentiment": classification["impact_score"],
        "is_trump_related": trump_related,
        "content_hash": compute_hash(content, source_info['handle'], "twitter"),
        "url": f"https://x.com/{source_info['handle']}/status/{tweet_id}",
    }


def process_facebook_post(post: Dict, source_info: Dict) -> Optional[Dict[str, Any]]:
    """Process a Facebook post into standardized format."""
    content = post.get("message", post.get("text", ""))
    if not content:
        return None

    pub_date = parse_date(post.get("created_time")) or datetime.now()
    headline = content[:100] + "..." if len(content) > 100 else content

    article_data = {
        "title": headline,
        "body": content,
        "source": f"facebook_{source_info['profile']}",
    }
    classification = classify_article(article_data)
    bucket = classification["alert_buckets"][0] if classification["alert_buckets"] else None

    return {
        "as_of_date": pub_date.date(),
        "headline": headline,
        "content": content,
        "source": f"facebook_{source_info['profile']}",
        "bucket_name": bucket or source_info["specialist"],
        "zl_sentiment": classification["impact_score"],
        "is_trump_related": is_trump_related(content),
        "content_hash": compute_hash(content, source_info['profile'], "facebook"),
        "url": post.get("permalink_url", ""),
    }


def process_linkedin_post(post: Dict, source_info: Dict) -> Optional[Dict[str, Any]]:
    """Process a LinkedIn post into standardized format."""
    content = post.get("text", post.get("commentary", ""))
    if not content:
        return None

    pub_date = parse_date(post.get("published_at")) or datetime.now()
    headline = content[:100] + "..." if len(content) > 100 else content

    article_data = {
        "title": headline,
        "body": content,
        "source": f"linkedin_{source_info['company']}",
    }
    classification = classify_article(article_data)
    bucket = classification["alert_buckets"][0] if classification["alert_buckets"] else None

    return {
        "as_of_date": pub_date.date(),
        "headline": headline,
        "content": content,
        "source": f"linkedin_{source_info['company']}",
        "bucket_name": bucket or source_info["specialist"],
        "zl_sentiment": classification["impact_score"],
        "is_trump_related": is_trump_related(content),
        "content_hash": compute_hash(content, source_info['company'], "linkedin"),
        "url": post.get("url", ""),
    }


def process_truthsocial_post(post: Dict, source_info: Dict) -> Optional[Dict[str, Any]]:
    """Process a Truth Social post into standardized format."""
    content = post.get("content", post.get("text", ""))
    if not content:
        return None

    pub_date = parse_date(post.get("created_at")) or datetime.now()
    headline = content[:100] + "..." if len(content) > 100 else content

    article_data = {
        "title": headline,
        "body": content,
        "source": f"truthsocial_{source_info['handle']}",
    }
    classification = classify_article(article_data)
    bucket = classification["alert_buckets"][0] if classification["alert_buckets"] else None

    return {
        "as_of_date": pub_date.date(),
        "headline": headline,
        "content": content,
        "source": f"truthsocial_{source_info['handle']}",
        "bucket_name": bucket or source_info["specialist"],
        "zl_sentiment": classification["impact_score"],
        "is_trump_related": True,  # Truth Social is inherently Trump-related
        "content_hash": compute_hash(content, source_info['handle'], "truthsocial"),
        "url": post.get("url", f"https://truthsocial.com/@{source_info['handle']}/posts/{post.get('id', '')}"),
    }


# =============================================================================
# MAIN SCRAPING FUNCTIONS
# =============================================================================

def scrape_tier(
    tier: str,
    api_key: str,
    conn,
    backfill: bool = False,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Scrape social posts for a specific tier.

    Args:
        tier: 'high', 'regulatory', 'discovery', or 'all'
        api_key: ScrapeCreators API key
        conn: Database connection
        backfill: If True, fetch more posts per source
        dry_run: If True, don't insert to database

    Returns:
        Stats dict with counts
    """
    stats = {
        "tier": tier,
        "run_time": datetime.now().isoformat(),
        "total_fetched": 0,
        "total_inserted": 0,
        "total_duplicates": 0,
        "by_platform": {},
        "by_specialist": {},
        "errors": [],
    }

    limit = 100 if backfill else 20

    # Build handle list based on tier
    twitter_handles = []
    if tier in ("high", "all"):
        twitter_handles.extend(HIGH_ALPHA_TWITTER)
    if tier in ("regulatory", "all"):
        twitter_handles.extend(REGULATORY_TWITTER)
        twitter_handles.extend(ANALYST_TWITTER)
    if tier in ("discovery", "all"):
        twitter_handles.extend(DISCOVERY_TWITTER)

    # Twitter/X
    logger.info(f"Scraping {len(twitter_handles)} Twitter handles...")
    platform_stats = {"fetched": 0, "inserted": 0, "duplicates": 0}

    for source in twitter_handles:
        logger.info(f"  [@{source['handle']}] {source['name']}...")
        tweets = fetch_twitter_user_tweets(source["handle"], api_key, limit)

        for tweet in tweets:
            post = process_twitter_post(tweet, source)
            if not post:
                continue

            platform_stats["fetched"] += 1

            if dry_run:
                continue

            if post_exists(conn, post["content_hash"]):
                platform_stats["duplicates"] += 1
            elif insert_post(conn, post):
                platform_stats["inserted"] += 1
                conn.commit()

        # Rate limiting
        time.sleep(2)

    stats["by_platform"]["twitter"] = platform_stats
    stats["total_fetched"] += platform_stats["fetched"]
    stats["total_inserted"] += platform_stats["inserted"]
    stats["total_duplicates"] += platform_stats["duplicates"]

    # Truth Social (high-alpha only)
    if tier in ("high", "all"):
        logger.info(f"Scraping {len(TRUTH_SOCIAL_PROFILES)} Truth Social profiles...")
        platform_stats = {"fetched": 0, "inserted": 0, "duplicates": 0}

        for source in TRUTH_SOCIAL_PROFILES:
            logger.info(f"  [@{source['handle']}] {source['name']}...")
            posts = fetch_truthsocial_posts(source["handle"], api_key, limit)

            for post_data in posts:
                post = process_truthsocial_post(post_data, source)
                if not post:
                    continue

                platform_stats["fetched"] += 1

                if dry_run:
                    continue

                if post_exists(conn, post["content_hash"]):
                    platform_stats["duplicates"] += 1
                elif insert_post(conn, post):
                    platform_stats["inserted"] += 1
                    conn.commit()

            time.sleep(2)

        stats["by_platform"]["truthsocial"] = platform_stats
        stats["total_fetched"] += platform_stats["fetched"]
        stats["total_inserted"] += platform_stats["inserted"]
        stats["total_duplicates"] += platform_stats["duplicates"]

    # Facebook (regulatory and discovery)
    if tier in ("regulatory", "discovery", "all"):
        fb_profiles = [p for p in FACEBOOK_PROFILES if p["priority"] <= (1 if tier == "regulatory" else 2)]
        logger.info(f"Scraping {len(fb_profiles)} Facebook profiles...")
        platform_stats = {"fetched": 0, "inserted": 0, "duplicates": 0}

        for source in fb_profiles:
            logger.info(f"  [{source['profile']}] {source['name']}...")
            posts = fetch_facebook_posts(source["profile"], api_key, min(limit, 10))

            for post_data in posts:
                post = process_facebook_post(post_data, source)
                if not post:
                    continue

                platform_stats["fetched"] += 1

                if dry_run:
                    continue

                if post_exists(conn, post["content_hash"]):
                    platform_stats["duplicates"] += 1
                elif insert_post(conn, post):
                    platform_stats["inserted"] += 1
                    conn.commit()

            time.sleep(3)

        stats["by_platform"]["facebook"] = platform_stats
        stats["total_fetched"] += platform_stats["fetched"]
        stats["total_inserted"] += platform_stats["inserted"]
        stats["total_duplicates"] += platform_stats["duplicates"]

    # LinkedIn (discovery only)
    if tier in ("discovery", "all"):
        logger.info(f"Scraping {len(LINKEDIN_PROFILES)} LinkedIn profiles...")
        platform_stats = {"fetched": 0, "inserted": 0, "duplicates": 0}

        for source in LINKEDIN_PROFILES:
            logger.info(f"  [{source['company']}] {source['name']}...")
            posts = fetch_linkedin_posts(source["company"], api_key, min(limit, 10))

            for post_data in posts:
                post = process_linkedin_post(post_data, source)
                if not post:
                    continue

                platform_stats["fetched"] += 1

                if dry_run:
                    continue

                if post_exists(conn, post["content_hash"]):
                    platform_stats["duplicates"] += 1
                elif insert_post(conn, post):
                    platform_stats["inserted"] += 1
                    conn.commit()

            time.sleep(3)

        stats["by_platform"]["linkedin"] = platform_stats
        stats["total_fetched"] += platform_stats["fetched"]
        stats["total_inserted"] += platform_stats["inserted"]
        stats["total_duplicates"] += platform_stats["duplicates"]

    return stats


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Scrape social media for commodity intelligence (Server Job)"
    )
    parser.add_argument(
        "--tier",
        choices=["high", "regulatory", "discovery", "all"],
        default="all",
        help="Priority tier to scrape"
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill mode - fetch more posts per source"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without inserting to database"
    )

    args = parser.parse_args()

    # Check API key
    api_key = get_api_key()
    if not api_key:
        logger.error("SCRAPECREATORS_API_KEY not set. Exiting.")
        return 1

    logger.info("=" * 60)
    logger.info("SOCIAL MEDIA INTELLIGENCE SCRAPER")
    logger.info("=" * 60)
    logger.info(f"Tier: {args.tier}")
    logger.info(f"Backfill: {args.backfill}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("")

    conn = None
    if not args.dry_run:
        conn = get_postgres_connection()

    try:
        stats = scrape_tier(
            tier=args.tier,
            api_key=api_key,
            conn=conn,
            backfill=args.backfill,
            dry_run=args.dry_run
        )

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("SCRAPE COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total fetched: {stats['total_fetched']}")
        logger.info(f"Total inserted: {stats['total_inserted']}")
        logger.info(f"Total duplicates: {stats['total_duplicates']}")
        logger.info("")
        logger.info("By Platform:")
        for platform, counts in stats["by_platform"].items():
            logger.info(f"  {platform}: {counts['inserted']} new / {counts['fetched']} fetched")

        # Save stats
        stats_file = LOG_DIR / f"social_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(stats_file, "w") as f:
            json.dump(stats, f, indent=2)
        logger.info(f"\nStats saved to: {stats_file}")

        return 0 if stats["total_inserted"] > 0 or args.dry_run else 1

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
