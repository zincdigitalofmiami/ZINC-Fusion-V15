#!/usr/bin/env python3
"""
Barchart News Scraper - Uses Playwright to scrape news with your login session.

This script:
1. Opens a browser with your Barchart session (saves cookies for reuse)
2. Navigates to search pages (china, trump, tariff, soybean, etc.)
3. Paginates through historical articles
4. Extracts headline, date, content
5. Runs FinBERT sentiment analysis
6. Inserts to alt.news_1d

Usage:
    # First run - will open browser for you to login manually
    python scripts/scrape_barchart_news.py --login

    # After login, scrape with saved session
    python scripts/scrape_barchart_news.py --keywords "china,trump,tariff"

    # Scrape all specialist keywords
    python scripts/scrape_barchart_news.py --all

    # Limit pages per keyword
    python scripts/scrape_barchart_news.py --keywords "china" --max-pages 50
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
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
from playwright.sync_api import sync_playwright, Page, Browser
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
COOKIES_PATH = PROJECT_ROOT / ".barchart_cookies.json"

# ============================================================
# Specialist Tagging - Uses shared module
# ============================================================

import sys
from pathlib import Path

# Add src to path if running as script
_src_path = Path(__file__).parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from fusion.tagging import classify_specialists

# Default keywords to scrape for full backfill
DEFAULT_KEYWORDS = [
    "soybean oil",
    "soybeans",
    "china soybean",
    "trump tariff",
    "tariff",
    "biofuel",
    "biodiesel",
    "palm oil",
    "FOMC",
    "VIX",
]


def get_specialist_for_keyword(keyword: str) -> str:
    """Map a keyword to its specialist bucket (uses shared classifier)."""
    tags = classify_specialists(keyword)
    return tags[0] if tags else "general"


def load_finbert():
    """Load FinBERT model for sentiment analysis."""
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        log.info("Loading FinBERT model...")
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        log.info(f"Using device: {device}")

        tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        model.to(device)
        model.eval()

        return tokenizer, model, device
    except Exception as e:
        log.warning(f"Could not load FinBERT: {e}")
        return None, None, None


def analyze_sentiment(text: str, tokenizer, model, device) -> float:
    """Analyze sentiment using FinBERT. Returns score from -1 (negative) to +1 (positive)."""
    if tokenizer is None or model is None:
        return 0.0

    try:
        import torch

        # Truncate to max length
        text = text[:512]

        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.softmax(outputs.logits, dim=1)

        # FinBERT classes: 0=positive, 1=negative, 2=neutral
        pos, neg, neu = probs[0].tolist()

        # Convert to -1 to +1 scale
        sentiment = pos - neg
        return round(sentiment, 4)
    except Exception as e:
        log.warning(f"Sentiment analysis failed: {e}")
        return 0.0


def save_cookies(page: Page):
    """Save browser cookies for session persistence."""
    cookies = page.context.cookies()
    with open(COOKIES_PATH, "w") as f:
        json.dump(cookies, f)
    log.info(f"Cookies saved to {COOKIES_PATH}")


def load_cookies(context):
    """Load saved cookies into browser context."""
    if COOKIES_PATH.exists():
        with open(COOKIES_PATH, "r") as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        log.info(f"Loaded {len(cookies)} cookies from {COOKIES_PATH}")
        return True
    return False


def login_interactive(playwright):
    """Open browser for manual login, then save cookies."""
    log.info("Opening browser for manual login...")
    log.info("Please log in to Barchart, then press Enter in this terminal when done.")

    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    page.goto("https://www.barchart.com/login")

    input("\n>>> Press Enter after you've logged in to Barchart... ")

    save_cookies(page)
    browser.close()
    log.info("Login complete! You can now run scraping commands.")


def parse_article_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats from Barchart."""
    if not date_str:
        return None

    date_str = date_str.strip()

    # Try various formats
    formats = [
        "%b %d, %Y",  # Jan 15, 2026
        "%B %d, %Y",  # January 15, 2026
        "%a %b %d, %Y",  # Fri Dec 26, 2025
        "%A %B %d, %Y",  # Friday December 26, 2025
        "%m/%d/%Y",  # 01/15/2026
        "%Y-%m-%d",  # 2026-01-15
        "%b %d, %Y %I:%M%p",  # Jan 15, 2026 2:30PM
        "%B %d, %Y %I:%M%p",  # January 15, 2026 2:30PM
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Handle "Thu Jan 15, 2:50PM CST" format (no year)
    match = re.match(r"(\w+) (\w+) (\d+), (\d+):(\d+)(AM|PM) \w+", date_str)
    if match:
        day_name, month_str, day, hour, minute, ampm = match.groups()
        try:
            month_map = {
                "Jan": 1,
                "Feb": 2,
                "Mar": 3,
                "Apr": 4,
                "May": 5,
                "Jun": 6,
                "Jul": 7,
                "Aug": 8,
                "Sep": 9,
                "Oct": 10,
                "Nov": 11,
                "Dec": 12,
            }
            month = month_map.get(month_str, 1)
            hour = int(hour)
            if ampm == "PM" and hour != 12:
                hour += 12
            elif ampm == "AM" and hour == 12:
                hour = 0
            return datetime(datetime.now().year, month, int(day), hour, int(minute))
        except:
            pass

    # Handle relative dates like "2 hours ago", "Yesterday"
    if "ago" in date_str.lower():
        return datetime.now()
    if "yesterday" in date_str.lower():
        return datetime.now() - timedelta(days=1)

    log.warning(f"Could not parse date: {date_str}")
    return None


def scrape_search_page(page: Page, keyword: str, max_pages: int = 100) -> list[dict]:
    """Scrape news articles from a Barchart search page."""
    articles = []
    keyword_slug = keyword.replace(" ", "+")
    base_url = f"https://www.barchart.com/news/search/any/{keyword_slug}"

    log.info(f"Scraping keyword: '{keyword}' from {base_url}")

    for page_num in range(1, max_pages + 1):
        url = f"{base_url}?page={page_num}" if page_num > 1 else base_url

        try:
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)  # Wait for JS to render

            # Check if we're still logged in
            if "login" in page.url.lower():
                log.error("Session expired! Run with --login to re-authenticate.")
                break

            # Method 1: Extract from data-feed-items JSON attribute
            feed_element = page.query_selector("[data-feed-items]")
            if feed_element:
                feed_json = feed_element.get_attribute("data-feed-items")
                if feed_json:
                    try:
                        feed_items = json.loads(feed_json)
                        page_articles = 0
                        for item in feed_items:
                            headline = item.get("title", "")
                            news_id = item.get("id", "")
                            slug = item.get("slug", "")
                            source_name = item.get("feedName", "barchart")
                            published_str = item.get("published", "")

                            # Parse the date
                            published_at = parse_article_date(published_str)

                            # Build URL
                            article_url = (
                                f"https://www.barchart.com/story/news/{news_id}/{slug}"
                                if news_id
                                else None
                            )

                            if headline and published_at:
                                articles.append(
                                    {
                                        "headline": headline,
                                        "source_url": article_url,
                                        "published_at": published_at,
                                        "source": f"barchart_scrape_{keyword.replace(' ', '_')}",
                                        "keyword": keyword,
                                        "feed_name": source_name,
                                    }
                                )
                                page_articles += 1

                        log.info(
                            f"  Page {page_num}: {page_articles} articles (total: {len(articles)})"
                        )

                        if page_articles == 0:
                            log.info(f"No more articles on page {page_num}, stopping")
                            break
                        continue
                    except json.JSONDecodeError:
                        pass

            # Method 2: Fallback to DOM scraping
            story_elements = page.query_selector_all(".story.clearfix")
            if not story_elements:
                log.info(f"No more articles found on page {page_num}")
                break

            page_articles = 0
            for el in story_elements:
                try:
                    # Extract headline and link
                    link_el = el.query_selector("a.story-link")
                    if not link_el:
                        continue
                    headline = link_el.inner_text().strip()
                    link = link_el.get_attribute("href")
                    if link and not link.startswith("http"):
                        link = f"https://www.barchart.com{link}"

                    # Extract date from story-meta
                    meta_el = el.query_selector(".story-meta")
                    if meta_el:
                        meta_text = meta_el.inner_text().strip()
                        # Format: "Associated Press - 1 hour ago" or "Barchart - Thu Jan 15, 10:44AM CST"
                        parts = meta_text.split(" - ", 1)
                        source_name = parts[0].strip() if len(parts) > 1 else "barchart"
                        date_str = parts[-1].strip()
                        published_at = parse_article_date(date_str)
                    else:
                        source_name = "barchart"
                        published_at = None

                    if headline and published_at:
                        articles.append(
                            {
                                "headline": headline,
                                "source_url": link,
                                "published_at": published_at,
                                "source": f"barchart_scrape_{keyword.replace(' ', '_')}",
                                "keyword": keyword,
                                "feed_name": source_name,
                            }
                        )
                        page_articles += 1
                except Exception:
                    continue

            log.info(
                f"  Page {page_num}: {page_articles} articles (total: {len(articles)})"
            )

            if page_articles == 0:
                break

        except Exception as e:
            log.error(f"Error on page {page_num}: {e}")
            break

    return articles


def fetch_article_content(page: Page, url: str) -> str:
    """Fetch full article content from URL."""
    try:
        page.goto(url, timeout=20000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)

        # Find article body
        content_el = page.query_selector(
            "article .story-content, .bc-news-body, [class*='article-body'], .story-body"
        )
        if content_el:
            return content_el.inner_text().strip()[:2000]  # Limit length

        return ""
    except Exception as e:
        log.warning(f"Could not fetch content from {url}: {e}")
        return ""


def insert_articles(articles: list[dict], tokenizer, model, device):
    """Insert articles into database with sentiment analysis."""
    if not articles:
        log.info("No articles to insert")
        return

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    inserted = 0
    skipped = 0

    for article in articles:
        try:
            # Generate row hash for deduplication
            hash_input = f"{article['headline']}|{article['published_at'].date()}"
            row_hash = hashlib.md5(hash_input.encode()).hexdigest()

            # Check if exists
            cur.execute(
                "SELECT 1 FROM alt.news_1d WHERE row_hash = %s", (row_hash,)
            )
            if cur.fetchone():
                skipped += 1
                continue

            # Analyze sentiment
            sentiment = analyze_sentiment(article["headline"], tokenizer, model, device)

            # Get specialist bucket
            specialist = get_specialist_for_keyword(article["keyword"])

            # Insert
            cur.execute(
                """
                INSERT INTO alt.news_1d
                (headline, source, url, event_date,
                 sentiment_score, specialist_tags, row_hash, ingested_at, knowledge_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            """,
                (
                    article["headline"],
                    article["source"],
                    article.get("source_url"),
                    article["published_at"].date(),
                    sentiment,
                    [specialist, article["keyword"]],
                    row_hash,
                ),
            )
            inserted += 1

        except Exception as e:
            log.warning(f"Insert error: {e}")
            continue

    conn.commit()
    cur.close()
    conn.close()

    log.info(f"Inserted {inserted} articles, skipped {skipped} duplicates")


def main():
    raise SystemExit(
        "Barchart scraping is disabled in production. Existing data is retained."
    )
    parser = argparse.ArgumentParser(
        description="Scrape Barchart news with your login session"
    )
    parser.add_argument(
        "--login", action="store_true", help="Open browser for manual login"
    )
    parser.add_argument(
        "--keywords", type=str, help="Comma-separated keywords to scrape"
    )
    parser.add_argument(
        "--all", action="store_true", help="Scrape all default specialist keywords"
    )
    parser.add_argument(
        "--max-pages", type=int, default=50, help="Max pages per keyword (default: 50)"
    )
    parser.add_argument(
        "--fetch-content",
        action="store_true",
        help="Fetch full article content (slower)",
    )
    parser.add_argument(
        "--no-sentiment", action="store_true", help="Skip sentiment analysis"
    )
    args = parser.parse_args()

    with sync_playwright() as playwright:
        # Handle login mode
        if args.login:
            login_interactive(playwright)
            return

        # Check for saved session
        if not COOKIES_PATH.exists():
            log.error("No saved session found! Run with --login first.")
            sys.exit(1)

        # Determine keywords to scrape
        if args.all:
            keywords = DEFAULT_KEYWORDS
        elif args.keywords:
            keywords = [k.strip() for k in args.keywords.split(",")]
        else:
            parser.print_help()
            sys.exit(1)

        # Load FinBERT
        tokenizer, model, device = (None, None, None)
        if not args.no_sentiment:
            tokenizer, model, device = load_finbert()

        # Launch browser with saved session
        log.info("Launching browser with saved session...")
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        load_cookies(context)
        page = context.new_page()

        # Test session
        page.goto("https://www.barchart.com")
        time.sleep(2)

        all_articles = []
        for keyword in keywords:
            articles = scrape_search_page(page, keyword, max_pages=args.max_pages)
            all_articles.extend(articles)
            log.info(f"Keyword '{keyword}': {len(articles)} articles")

        browser.close()

        # Insert to database
        log.info(f"\nTotal articles scraped: {len(all_articles)}")
        insert_articles(all_articles, tokenizer, model, device)

        log.info("✅ Done!")


if __name__ == "__main__":
    main()
