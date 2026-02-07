#!/usr/bin/env python3
"""
Quick News Backfill - RSS Sources
Pulls all available articles from RSS feeds into alt.news_1d

Sources:
- Farmdoc RINs (biofuel, energy)
- Farmdoc Ag Policy (tariff, crush, trump_effect)
- Farm Progress (crush, substitutes)
- CONAB Brazil (crush, china)

Run: .venv/bin/python scripts/backfill_news_sources.py
"""

import os
import hashlib
import json
from datetime import datetime
from typing import Optional
import feedparser
import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    from dotenv import load_dotenv
    load_dotenv()
    DATABASE_URL = os.environ.get("DATABASE_URL")

RSS_SOURCES = [
    {
        "name": "farmdoc_rins",
        "url": "https://farmdocdaily.illinois.edu/category/areas/biofuels/rins/feed",
        "tags": ["biofuel", "energy"],
    },
    {
        "name": "farmdoc_ag_policy",
        "url": "https://farmdocdaily.illinois.edu/category/areas/agricultural-policy/feed",
        "tags": ["tariff", "crush", "trump_effect"],
    },
    {
        "name": "farmprogress",
        "url": "https://www.farmprogress.com/rss.xml",
        "tags": ["crush", "substitutes"],
    },
    {
        "name": "conab_brazil",
        "url": "https://www.conab.gov.br/ultimas-noticias?format=feed&type=rss",
        "tags": ["crush", "china"],
    },
]


def compute_row_hash(url: str, pub_date: str) -> str:
    return hashlib.sha256(f"{url}|{pub_date}".encode()).hexdigest()


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats from RSS feeds."""
    if not date_str:
        return None

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    # Try feedparser's parsed time
    return None


def fetch_rss(url: str) -> list:
    """Fetch and parse RSS feed with proper headers."""
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    return feed.entries


def backfill_source(conn, source: dict) -> dict:
    """Backfill a single RSS source."""
    name = source["name"]
    url = source["url"]
    tags = source["tags"]

    print(f"\n=== {name} ===")
    print(f"URL: {url}")

    entries = fetch_rss(url)
    print(f"Fetched {len(entries)} entries")

    inserted = 0
    skipped = 0
    errors = 0

    cur = conn.cursor()

    for entry in entries:
        try:
            # Extract fields
            title = entry.get("title", "")[:500]
            link = entry.get("link", "")
            content = entry.get("summary", "") or entry.get("description", "")
            pub_date_str = entry.get("published", "") or entry.get("updated", "")
            author = entry.get("author", "")

            if not link:
                errors += 1
                continue

            # Parse date
            parsed_date = parse_date(pub_date_str)
            if not parsed_date:
                # Try feedparser's struct_time
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    parsed_date = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    parsed_date = datetime(*entry.updated_parsed[:6])
                else:
                    parsed_date = datetime.now()

            event_date = parsed_date.strftime("%Y-%m-%d")

            # Compute hash
            row_hash = compute_row_hash(link, pub_date_str or event_date)

            # Check if exists
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
                content[:5000] if content else None,
                link,
                parsed_date,
                author[:200] if author else None,
                name,
                json.dumps(dict(entry)),
                row_hash,
                tags,
            ))
            inserted += 1

        except Exception as e:
            print(f"  Error: {e}")
            errors += 1
            continue

    conn.commit()
    cur.close()

    print(f"  Inserted: {inserted}")
    print(f"  Skipped (dupe): {skipped}")
    print(f"  Errors: {errors}")

    return {"name": name, "inserted": inserted, "skipped": skipped, "errors": errors}


def main():
    print("=" * 60)
    print("NEWS RSS BACKFILL")
    print("=" * 60)

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        return

    conn = psycopg2.connect(DATABASE_URL)

    results = []
    for source in RSS_SOURCES:
        try:
            result = backfill_source(conn, source)
            results.append(result)
        except Exception as e:
            print(f"ERROR with {source['name']}: {e}")
            results.append({"name": source["name"], "error": str(e)})

    conn.close()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total_inserted = sum(r.get("inserted", 0) for r in results)
    total_skipped = sum(r.get("skipped", 0) for r in results)
    print(f"Total inserted: {total_inserted}")
    print(f"Total skipped: {total_skipped}")

    for r in results:
        status = f"inserted={r.get('inserted', 0)}" if 'inserted' in r else f"error={r.get('error', 'unknown')}"
        print(f"  {r['name']}: {status}")


if __name__ == "__main__":
    main()
