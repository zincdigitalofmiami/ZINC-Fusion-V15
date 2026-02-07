#!/usr/bin/env python3
"""
Farmdoc Historical Backfill - Scrapes ALL articles from archive pages

Categories:
- RINs (biofuel, energy) - https://farmdocdaily.illinois.edu/category/areas/biofuels/rins
- Ag Policy (tariff, crush, trump_effect) - https://farmdocdaily.illinois.edu/category/areas/agricultural-policy
- Biofuels general - https://farmdocdaily.illinois.edu/category/areas/biofuels

Run: .venv/bin/python scripts/backfill_farmdoc_historical.py
"""

import os
import re
import hashlib
import json
import time
from datetime import datetime
from typing import Optional, List, Dict
import requests
from bs4 import BeautifulSoup
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    from dotenv import load_dotenv
    load_dotenv()
    DATABASE_URL = os.environ.get("DATABASE_URL")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CATEGORIES = [
    {
        "name": "farmdoc_rins",
        "base_url": "https://farmdocdaily.illinois.edu/category/areas/biofuels/rins",
        "tags": ["biofuel", "energy"],
    },
    {
        "name": "farmdoc_ag_policy",
        "base_url": "https://farmdocdaily.illinois.edu/category/areas/agricultural-policy",
        "tags": ["tariff", "crush", "trump_effect"],
    },
    {
        "name": "farmdoc_biofuels",
        "base_url": "https://farmdocdaily.illinois.edu/category/areas/biofuels",
        "tags": ["biofuel", "energy", "crush"],
    },
]


def compute_row_hash(url: str, pub_date: str) -> str:
    return hashlib.sha256(f"{url}|{pub_date}".encode()).hexdigest()


def parse_farmdoc_date(date_str: str) -> Optional[datetime]:
    """Parse date from farmdoc format: 'January 15, 2024' or similar."""
    if not date_str:
        return None

    # Clean up the string
    date_str = date_str.strip()

    formats = [
        "%B %d, %Y",      # January 15, 2024
        "%b %d, %Y",      # Jan 15, 2024
        "%Y-%m-%d",       # 2024-01-15
        "%m/%d/%Y",       # 01/15/2024
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None


def get_page_articles(url: str) -> List[Dict]:
    """Scrape articles from a single page."""
    articles = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find article entries - farmdoc uses article tags or specific divs
        # Pattern 1: article elements
        for article in soup.find_all("article"):
            try:
                # Title and link
                title_elem = article.find("h2") or article.find("h3") or article.find("a", class_="entry-title")
                if not title_elem:
                    continue

                link_elem = title_elem.find("a") if title_elem.name != "a" else title_elem
                if not link_elem or not link_elem.get("href"):
                    continue

                title = link_elem.get_text(strip=True)
                link = link_elem["href"]

                # Date
                date_elem = article.find("time") or article.find(class_=re.compile(r"date|posted|published", re.I))
                date_str = ""
                if date_elem:
                    date_str = date_elem.get("datetime", "") or date_elem.get_text(strip=True)

                # Extract from URL if needed (farmdoc URLs have dates: /2024/01/15/article-name)
                if not date_str:
                    url_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", link)
                    if url_match:
                        date_str = f"{url_match.group(1)}-{url_match.group(2)}-{url_match.group(3)}"

                # Excerpt/summary
                excerpt_elem = article.find(class_=re.compile(r"excerpt|summary|content", re.I))
                excerpt = excerpt_elem.get_text(strip=True)[:2000] if excerpt_elem else ""

                # Author
                author_elem = article.find(class_=re.compile(r"author", re.I))
                author = author_elem.get_text(strip=True) if author_elem else ""

                articles.append({
                    "title": title,
                    "link": link,
                    "date_str": date_str,
                    "excerpt": excerpt,
                    "author": author,
                })

            except Exception as e:
                continue

        # Pattern 2: If no articles found, try generic entry pattern
        if not articles:
            for entry in soup.find_all(class_=re.compile(r"post|entry|article", re.I)):
                try:
                    link_elem = entry.find("a", href=re.compile(r"farmdocdaily\.illinois\.edu/\d{4}/"))
                    if not link_elem:
                        continue

                    title = link_elem.get_text(strip=True)
                    link = link_elem["href"]

                    # Extract date from URL
                    url_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", link)
                    date_str = f"{url_match.group(1)}-{url_match.group(2)}-{url_match.group(3)}" if url_match else ""

                    if title and link and date_str:
                        articles.append({
                            "title": title,
                            "link": link,
                            "date_str": date_str,
                            "excerpt": "",
                            "author": "",
                        })
                except:
                    continue

    except Exception as e:
        print(f"  Error fetching {url}: {e}")

    return articles


def get_all_pages(base_url: str, max_pages: int = 50) -> List[Dict]:
    """Scrape all paginated pages for a category."""
    all_articles = []
    seen_links = set()

    for page_num in range(1, max_pages + 1):
        if page_num == 1:
            url = base_url
        else:
            url = f"{base_url}/page/{page_num}"

        print(f"  Page {page_num}: {url}")
        articles = get_page_articles(url)

        if not articles:
            print(f"  No articles found, stopping pagination")
            break

        new_count = 0
        for article in articles:
            if article["link"] not in seen_links:
                seen_links.add(article["link"])
                all_articles.append(article)
                new_count += 1

        print(f"    Found {len(articles)} articles, {new_count} new")

        if new_count == 0:
            print(f"  All duplicates, stopping")
            break

        # Rate limit
        time.sleep(0.5)

    return all_articles


def backfill_category(conn, category: Dict) -> Dict:
    """Backfill all articles for a category."""
    name = category["name"]
    base_url = category["base_url"]
    tags = category["tags"]

    print(f"\n{'='*60}")
    print(f"CATEGORY: {name}")
    print(f"URL: {base_url}")
    print(f"{'='*60}")

    articles = get_all_pages(base_url)
    print(f"\nTotal articles found: {len(articles)}")

    inserted = 0
    skipped = 0
    errors = 0

    cur = conn.cursor()

    for article in articles:
        try:
            title = article["title"][:500]
            link = article["link"]
            date_str = article["date_str"]
            excerpt = article["excerpt"]
            author = article["author"][:200] if article["author"] else None

            if not link or not date_str:
                errors += 1
                continue

            # Parse date
            parsed_date = parse_farmdoc_date(date_str)
            if not parsed_date:
                # Try URL extraction
                url_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", link)
                if url_match:
                    parsed_date = datetime(
                        int(url_match.group(1)),
                        int(url_match.group(2)),
                        int(url_match.group(3))
                    )

            if not parsed_date:
                errors += 1
                continue

            event_date = parsed_date.strftime("%Y-%m-%d")
            row_hash = compute_row_hash(link, event_date)

            # Check duplicate
            cur.execute("SELECT 1 FROM alt.news_1d WHERE row_hash = %s LIMIT 1", (row_hash,))
            if cur.fetchone():
                skipped += 1
                continue

            # Insert
            cur.execute("""
                INSERT INTO alt.news_1d (
                    event_date, headline, content, url, published_at, author,
                    source, raw_payload, row_hash, specialist_tags
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                event_date,
                title,
                excerpt if excerpt else None,
                link,
                parsed_date,
                author,
                name,
                json.dumps(article),
                row_hash,
                tags,
            ))
            inserted += 1

        except Exception as e:
            print(f"  Error inserting article: {e}")
            errors += 1

    conn.commit()
    cur.close()

    print(f"\nResults for {name}:")
    print(f"  Inserted: {inserted}")
    print(f"  Skipped (dupe): {skipped}")
    print(f"  Errors: {errors}")

    return {"name": name, "inserted": inserted, "skipped": skipped, "errors": errors}


def main():
    print("=" * 60)
    print("FARMDOC HISTORICAL BACKFILL")
    print("=" * 60)

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        return

    conn = psycopg2.connect(DATABASE_URL)

    results = []
    for category in CATEGORIES:
        try:
            result = backfill_category(conn, category)
            results.append(result)
        except Exception as e:
            print(f"ERROR with {category['name']}: {e}")
            results.append({"name": category["name"], "error": str(e)})

    conn.close()

    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    total_inserted = sum(r.get("inserted", 0) for r in results)
    total_skipped = sum(r.get("skipped", 0) for r in results)
    total_errors = sum(r.get("errors", 0) for r in results)

    print(f"Total inserted: {total_inserted}")
    print(f"Total skipped: {total_skipped}")
    print(f"Total errors: {total_errors}")

    for r in results:
        if "error" in r:
            print(f"  {r['name']}: ERROR - {r['error']}")
        else:
            print(f"  {r['name']}: inserted={r['inserted']}, skipped={r['skipped']}")


if __name__ == "__main__":
    main()
