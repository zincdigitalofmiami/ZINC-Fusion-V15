#!/usr/bin/env python3
"""
Backfill FOMC statements, minutes, press conferences, and Beige Book
into alt.econ_news_event from the Federal Reserve website.

SOURCES (all free, no API key):
  1. FOMC Statements: federalreserve.gov/monetarypolicy/fomccalendars.htm
  2. FOMC Minutes: Same page, linked PDFs/HTML
  3. Fed Speeches: federalreserve.gov/newsevents/speeches.htm
  4. Beige Book: federalreserve.gov/monetarypolicy/beige-book-default.htm
  5. Fed Press RSS: federalreserve.gov/feeds/press_all.xml (recent only)

Historical depth:
  - FOMC statements: 1994-present (HTML)
  - FOMC minutes: 1993-present (PDF/HTML)
  - Beige Book: 1996-present (HTML)
  - Speeches: 2006-present (HTML)

Strategy:
  - Scrape the Fed's historical calendar pages year by year
  - Extract statement text, meeting dates, vote outcomes
  - Store in alt.econ_news_event with specialist_tags=['fed']

Usage:
    .venv/bin/python scripts/backfill_fomc_history.py
    .venv/bin/python scripts/backfill_fomc_history.py --years 5
    .venv/bin/python scripts/backfill_fomc_history.py --dry-run
    .venv/bin/python scripts/backfill_fomc_history.py --source statements
    .venv/bin/python scripts/backfill_fomc_history.py --source beige-book
"""

import argparse
import hashlib
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import psycopg2
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    env_local = Path(__file__).parent.parent / "frontend" / ".env.local"
    if env_local.exists():
        for line in env_local.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                DATABASE_URL = line.split("=", 1)[1].strip().strip('"')
                break

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found")
    sys.exit(1)

HEADERS = {
    "User-Agent": "ZincFusion/1.0 (commodity-research; contact: admin@zincdigital.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

FED_BASE = "https://www.federalreserve.gov"


def compute_hash(headline: str, content: str, source: str) -> str:
    text = f"{headline or ''}{content or ''}{source or ''}"
    return hashlib.sha256(text.encode()).hexdigest()[:64]


def article_exists(conn, row_hash: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM alt.econ_news_event WHERE row_hash = %s LIMIT 1",
            (row_hash,),
        )
        return cur.fetchone() is not None


def insert_fomc_article(conn, article: dict) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO alt.econ_news_event
                (event_date, published_at, headline, content, source,
                 specialist_tags, zl_sentiment, row_hash, url, ingested_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    article["event_date"],
                    article["published_at"],
                    article["headline"][:500],
                    article["content"][:10000] if article["content"] else None,
                    article["source"],
                    article["tags"],
                    None,  # Sentiment scored later by pipeline
                    article["row_hash"],
                    article["url"],
                ),
            )
        return True
    except Exception:
        conn.rollback()
        return False


# =============================================================================
# FOMC STATEMENTS (1994-present)
# =============================================================================


def scrape_fomc_statements(start_year: int, end_year: int) -> list[dict]:
    """Scrape FOMC statements from the Fed's historical calendar pages."""
    articles = []

    for year in range(start_year, end_year + 1):
        print(f"  [FOMC Statements] {year} ... ", end="", flush=True)

        # The Fed uses different URL patterns for recent vs historical
        if year >= 2017:
            url = f"{FED_BASE}/monetarypolicy/fomccalendars.htm"
        else:
            url = f"{FED_BASE}/monetarypolicy/fomchistorical{year}.htm"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 404:
                print("NOT FOUND")
                continue
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Find all statement links
            statement_links = []
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                text = a_tag.get_text(strip=True).lower()
                if "statement" in text and (
                    "monetarypolicy" in href or "newsevents" in href
                ):
                    full_url = href if href.startswith("http") else f"{FED_BASE}{href}"
                    statement_links.append(full_url)

            # Deduplicate
            statement_links = list(set(statement_links))
            count = 0

            for stmt_url in statement_links:
                try:
                    stmt_resp = requests.get(stmt_url, headers=HEADERS, timeout=30)
                    if stmt_resp.status_code != 200:
                        continue

                    stmt_soup = BeautifulSoup(stmt_resp.text, "html.parser")

                    # Extract date from URL or page content
                    date_match = re.search(r"(\d{4})(\d{2})(\d{2})", stmt_url)
                    if date_match:
                        event_date = datetime(
                            int(date_match.group(1)),
                            int(date_match.group(2)),
                            int(date_match.group(3)),
                        )
                    else:
                        event_date = datetime(year, 1, 1)

                    # Extract title
                    title_elem = stmt_soup.find("h3", class_="title")
                    if not title_elem:
                        title_elem = stmt_soup.find("title")
                    headline = (
                        title_elem.get_text(strip=True)
                        if title_elem
                        else f"FOMC Statement {event_date.strftime('%Y-%m-%d')}"
                    )

                    # Extract statement body
                    article_elem = stmt_soup.find(
                        "div", {"id": re.compile(r"article|content")}
                    )
                    if not article_elem:
                        article_elem = stmt_soup.find("div", class_="col-xs-12")
                    content = (
                        article_elem.get_text(separator=" ", strip=True)
                        if article_elem
                        else ""
                    )

                    if not content or len(content) < 100:
                        continue

                    row_hash = compute_hash(headline, content, "fomc_statement")
                    articles.append(
                        {
                            "event_date": event_date.date(),
                            "published_at": event_date,
                            "headline": headline,
                            "content": content,
                            "source": "fomc_statement",
                            "tags": ["fed"],
                            "row_hash": row_hash,
                            "url": stmt_url,
                        }
                    )
                    count += 1
                    time.sleep(0.5)

                except Exception:
                    continue

            print(f"{count} statements")

        except Exception as e:
            print(f"ERROR: {e}")

        time.sleep(1.0)

    return articles


# =============================================================================
# BEIGE BOOK (1996-present)
# =============================================================================


def scrape_beige_book(start_year: int, end_year: int) -> list[dict]:
    """Scrape Beige Book summaries from the Fed website."""
    articles = []

    for year in range(start_year, end_year + 1):
        print(f"  [Beige Book] {year} ... ", end="", flush=True)

        # Beige Book archive URL
        url = f"{FED_BASE}/monetarypolicy/beige-book-archive.htm"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Find Beige Book links for this year
            bb_links = []
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                text = a_tag.get_text(strip=True)
                if str(year) in href and (
                    "beige" in href.lower() or "beige" in text.lower()
                ):
                    full_url = href if href.startswith("http") else f"{FED_BASE}{href}"
                    bb_links.append((full_url, text))

            count = 0
            for bb_url, link_text in bb_links:
                try:
                    bb_resp = requests.get(bb_url, headers=HEADERS, timeout=30)
                    if bb_resp.status_code != 200:
                        continue

                    bb_soup = BeautifulSoup(bb_resp.text, "html.parser")

                    # Extract date
                    date_match = re.search(r"(\d{4})(\d{2})(\d{2})", bb_url)
                    if date_match:
                        event_date = datetime(
                            int(date_match.group(1)),
                            int(date_match.group(2)),
                            int(date_match.group(3)),
                        )
                    else:
                        # Try to extract from link text
                        event_date = datetime(year, 1, 1)

                    headline = f"Beige Book Summary - {link_text.strip()}"

                    # Get the national summary section
                    content_elem = bb_soup.find("div", {"id": "national-summary"})
                    if not content_elem:
                        content_elem = bb_soup.find(
                            "div", class_=re.compile(r"col-xs-12|article")
                        )
                    content = (
                        content_elem.get_text(separator=" ", strip=True)
                        if content_elem
                        else ""
                    )

                    if not content or len(content) < 100:
                        continue

                    row_hash = compute_hash(headline, content, "beige_book")
                    articles.append(
                        {
                            "event_date": event_date.date(),
                            "published_at": event_date,
                            "headline": headline,
                            "content": content,
                            "source": "beige_book",
                            "tags": ["fed"],
                            "row_hash": row_hash,
                            "url": bb_url,
                        }
                    )
                    count += 1
                    time.sleep(0.5)

                except Exception:
                    continue

            print(f"{count} reports")

        except Exception as e:
            print(f"ERROR: {e}")

        time.sleep(1.0)

    return articles


# =============================================================================
# FED SPEECHES (2006-present)
# =============================================================================


def scrape_fed_speeches(start_year: int, end_year: int) -> list[dict]:
    """Scrape Fed Governor/Chair speeches."""
    articles = []

    for year in range(start_year, end_year + 1):
        print(f"  [Fed Speeches] {year} ... ", end="", flush=True)

        url = f"{FED_BASE}/newsevents/speech/{year}-speeches.htm"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 404:
                print("NOT FOUND")
                continue
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Find speech entries
            speech_items = soup.find_all("div", class_="row")
            count = 0

            for item in speech_items:
                date_elem = item.find("time")
                link_elem = item.find("a", href=True)

                if not date_elem or not link_elem:
                    continue

                date_str = date_elem.get("datetime", date_elem.get_text(strip=True))
                try:
                    event_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
                except (ValueError, TypeError):
                    continue

                headline = link_elem.get_text(strip=True)
                if not headline or len(headline) < 10:
                    continue

                href = link_elem["href"]
                speech_url = href if href.startswith("http") else f"{FED_BASE}{href}"

                # Get speech content (just the title/summary, not full text for speed)
                speaker_elem = item.find("p", class_="news__speaker")
                speaker = speaker_elem.get_text(strip=True) if speaker_elem else ""
                content = f"{speaker}: {headline}"

                row_hash = compute_hash(headline, content, "fed_speech")
                articles.append(
                    {
                        "event_date": event_date.date(),
                        "published_at": event_date,
                        "headline": f"Fed Speech: {headline}",
                        "content": content,
                        "source": "fed_speech",
                        "tags": ["fed"],
                        "row_hash": row_hash,
                        "url": speech_url,
                    }
                )
                count += 1

            print(f"{count} speeches")

        except Exception as e:
            print(f"ERROR: {e}")

        time.sleep(1.0)

    return articles


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Backfill FOMC/Fed history")
    parser.add_argument(
        "--years", type=int, default=5, help="Years of history (default: 5)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting"
    )
    parser.add_argument(
        "--source",
        choices=["all", "statements", "beige-book", "speeches"],
        default="all",
        help="Which source to scrape",
    )
    args = parser.parse_args()

    end_year = datetime.now().year
    start_year = end_year - args.years

    print("=" * 70)
    print("FOMC / FED HISTORICAL BACKFILL")
    print("=" * 70)
    print(f"  Years: {start_year}-{end_year} ({args.years} years)")
    print(f"  Source: {args.source}")
    print(f"  Dry run: {args.dry_run}")

    all_articles = []

    if args.source in ("all", "statements"):
        articles = scrape_fomc_statements(start_year, end_year)
        all_articles.extend(articles)

    if args.source in ("all", "beige-book"):
        articles = scrape_beige_book(start_year, end_year)
        all_articles.extend(articles)

    if args.source in ("all", "speeches"):
        articles = scrape_fed_speeches(max(start_year, 2006), end_year)
        all_articles.extend(articles)

    print(f"\n  Total articles scraped: {len(all_articles)}")

    if args.dry_run:
        print("\n  DRY RUN — no database changes")
        for a in all_articles[:10]:
            print(f"    [{a['event_date']}] {a['source']}: {a['headline'][:80]}")
        if len(all_articles) > 10:
            print(f"    ... and {len(all_articles) - 10} more")
        return

    # Insert into database
    conn = psycopg2.connect(DATABASE_URL)
    inserted = 0
    skipped = 0

    for article in all_articles:
        if article_exists(conn, article["row_hash"]):
            skipped += 1
            continue
        if insert_fomc_article(conn, article):
            inserted += 1
            conn.commit()

    conn.close()

    print(f"\n  Inserted: {inserted}")
    print(f"  Skipped (duplicates): {skipped}")
    print("=" * 70)


if __name__ == "__main__":
    main()
