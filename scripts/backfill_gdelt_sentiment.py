#!/usr/bin/env python3
"""
Backfill daily news sentiment from GDELT Project into alt.econ_news_event.

GDELT (Global Database of Events, Language, and Tone) provides:
- Daily aggregate sentiment for every country/topic since 2015
- Pre-computed tone scores (positive/negative/polarity)
- Article counts per topic per day
- Free download, no API key required

SOURCE: GDELT GKG (Global Knowledge Graph)
  - Daily files: http://data.gdeltproject.org/gdeltv2/masterfilelist.txt
  - API: https://api.gdeltproject.org/api/v2/doc/doc
  - BigQuery: gdelt-bq.gdeltv2.gkg

STRATEGY:
  Use GDELT DOC API for daily topic sentiment aggregation.
  Query agriculture/commodity themes, aggregate by day, store as
  daily sentiment timeseries in alt.econ_news_event.

  For each Big-11 specialist, we define topic queries and extract:
  - article_count: Number of articles mentioning the topic
  - avg_tone: Average sentiment tone (-10 to +10)
  - positive_pct: % of articles with positive tone
  - negative_pct: % of articles with negative tone

THEMES MAPPED TO BIG-11:
  crush:        soybeans, soybean oil, soybean meal, USDA, crush margin
  china:        China trade, China soybeans, China imports
  fx:           US dollar, exchange rate, currency
  fed:          Federal Reserve, FOMC, interest rates, monetary policy
  tariff:       tariff, trade war, Section 301, trade policy
  energy:       crude oil, petroleum, energy prices, OPEC
  biofuel:      biodiesel, renewable fuel, ethanol, RFS, EPA fuel
  palm:         palm oil, Malaysia, Indonesia palm
  volatility:   market volatility, VIX, financial stress
  substitutes:  canola oil, sunflower oil, rapeseed
  trump_effect: Trump policy, executive order, trade war

Usage:
    .venv/bin/python scripts/backfill_gdelt_sentiment.py
    .venv/bin/python scripts/backfill_gdelt_sentiment.py --years 5
    .venv/bin/python scripts/backfill_gdelt_sentiment.py --specialist crush
    .venv/bin/python scripts/backfill_gdelt_sentiment.py --dry-run
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import psycopg2
import requests

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

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# Big-11 specialist → GDELT search queries
# Each specialist gets 1-3 focused queries that capture its domain
SPECIALIST_QUERIES = {
    "crush": [
        "soybean oil OR soy oil OR soybean meal",
        "soybean crush OR crush margin OR oilseed processing",
        "USDA soybeans OR soybean exports OR soybean production",
    ],
    "china": [
        "China soybeans OR China soybean imports",
        "China trade agriculture OR China food imports",
        "COFCO OR Sinograin OR China grain purchases",
    ],
    "fx": [
        "US dollar exchange rate OR dollar index",
        "Brazilian real currency OR Argentine peso",
        "emerging market currencies",
    ],
    "fed": [
        "Federal Reserve interest rates OR FOMC decision",
        "Fed monetary policy OR Fed rate hike OR Fed rate cut",
        "Federal Reserve inflation OR Fed employment mandate",
    ],
    "tariff": [
        "trade tariff agriculture OR section 301 tariff",
        "US China trade war OR trade policy soybeans",
        "agricultural tariff OR import duties grains",
    ],
    "energy": [
        "crude oil prices OR petroleum markets",
        "OPEC production OR oil supply OR energy prices",
        "diesel fuel prices OR heating oil",
    ],
    "biofuel": [
        "biodiesel renewable fuel OR renewable fuel standard",
        "ethanol production OR biofuel mandate",
        "EPA renewable volume obligation OR RIN credits",
    ],
    "palm": [
        "palm oil Malaysia OR palm oil Indonesia",
        "palm oil exports OR palm oil production",
        "MPOB OR palm oil prices",
    ],
    "volatility": [
        "stock market volatility OR VIX index",
        "financial market stress OR market selloff",
        "commodity market volatility",
    ],
    "substitutes": [
        "canola oil OR rapeseed oil",
        "sunflower oil prices OR vegetable oil competition",
        "olive oil OR coconut oil OR cooking oil prices",
    ],
    "trump_effect": [
        "Trump tariff OR Trump trade policy",
        "executive order trade OR presidential trade action",
        "Trump agriculture policy OR Trump farmer",
    ],
}


def compute_hash(specialist: str, date_str: str, query_idx: int) -> str:
    text = f"gdelt_{specialist}_{date_str}_{query_idx}"
    return hashlib.sha256(text.encode()).hexdigest()[:64]


def fetch_gdelt_day(query: str, date_str: str) -> dict | None:
    """
    Fetch GDELT DOC API for a single query and date.

    Returns aggregate tone data or None on failure.
    The DOC API returns article metadata; we aggregate tone ourselves.
    """
    # GDELT DOC API expects dates as YYYYMMDDHHMMSS
    start_dt = f"{date_str.replace('-', '')}000000"
    end_dt = f"{date_str.replace('-', '')}235959"

    params = {
        "query": query,
        "mode": "timelinetone",
        "startdatetime": start_dt,
        "enddatetime": end_dt,
        "format": "json",
        "maxrecords": "1",
    }

    try:
        resp = requests.get(GDELT_DOC_API, params=params, timeout=30)
        if resp.status_code != 200:
            return None

        data = resp.json()

        # timelinetone returns: { "timeline": [{ "series": [{ "data": [...] }] }] }
        timeline = data.get("timeline", [])
        if not timeline:
            return None

        series_data = timeline[0].get("data", [])
        if not series_data:
            return None

        # Each data point: { "date": "2021-01-15T00:00:00Z", "value": 2.5 }
        # Value is the average tone for that day
        for point in series_data:
            if date_str in str(point.get("date", "")):
                return {
                    "avg_tone": point.get("value", 0),
                    "date": date_str,
                }

        # If exact date not found, return first point
        if series_data:
            return {
                "avg_tone": series_data[0].get("value", 0),
                "date": date_str,
            }

        return None

    except Exception:
        return None


def fetch_gdelt_article_count(query: str, date_str: str) -> int:
    """Fetch article count for a query on a specific date."""
    start_dt = f"{date_str.replace('-', '')}000000"
    end_dt = f"{date_str.replace('-', '')}235959"

    params = {
        "query": query,
        "mode": "timelinevol",
        "startdatetime": start_dt,
        "enddatetime": end_dt,
        "format": "json",
        "maxrecords": "1",
    }

    try:
        resp = requests.get(GDELT_DOC_API, params=params, timeout=30)
        if resp.status_code != 200:
            return 0

        data = resp.json()
        timeline = data.get("timeline", [])
        if not timeline:
            return 0

        series_data = timeline[0].get("data", [])
        total = sum(p.get("value", 0) for p in series_data)
        return int(total)

    except Exception:
        return 0


def article_exists(conn, row_hash: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM alt.econ_news_event WHERE row_hash = %s LIMIT 1",
            (row_hash,),
        )
        return cur.fetchone() is not None


def insert_gdelt_record(conn, record: dict) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO alt.econ_news_event
                (event_date, published_at, headline, content, source,
                 specialist_tags, sentiment_score, row_hash, ingested_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    record["event_date"],
                    record["published_at"],
                    record["headline"],
                    record["content"],
                    record["source"],
                    record["tags"],
                    record["sentiment_score"],
                    record["row_hash"],
                ),
            )
        return True
    except Exception:
        conn.rollback()
        return False


def backfill_specialist(
    conn, specialist: str, start_date: datetime, end_date: datetime, dry_run: bool
) -> dict:
    """Backfill GDELT sentiment for a single specialist."""
    queries = SPECIALIST_QUERIES.get(specialist, [])
    if not queries:
        return {"inserted": 0, "skipped": 0}

    inserted = 0
    skipped = 0

    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")

        for qi, query in enumerate(queries):
            row_hash = compute_hash(specialist, date_str, qi)

            if not dry_run and conn and article_exists(conn, row_hash):
                skipped += 1
                continue

            # Fetch tone data
            tone_data = fetch_gdelt_day(query, date_str)
            article_count = fetch_gdelt_article_count(query, date_str)

            if tone_data is None and article_count == 0:
                continue

            avg_tone = tone_data["avg_tone"] if tone_data else 0
            # Normalize GDELT tone (-10 to +10) to our scale (-1 to +1)
            normalized_sentiment = max(-1.0, min(1.0, avg_tone / 10.0))

            headline = f"GDELT {specialist}: {query[:60]} ({date_str})"
            content = json.dumps(
                {
                    "query": query,
                    "date": date_str,
                    "article_count": article_count,
                    "avg_tone": avg_tone,
                    "normalized_sentiment": normalized_sentiment,
                    "source": "gdelt_doc_api",
                }
            )

            record = {
                "event_date": current.date(),
                "published_at": current,
                "headline": headline,
                "content": content,
                "source": f"gdelt_{specialist}",
                "tags": [specialist],
                "sentiment_score": normalized_sentiment,
                "row_hash": row_hash,
            }

            if dry_run:
                inserted += 1
            elif conn and insert_gdelt_record(conn, record):
                inserted += 1
                conn.commit()

            # GDELT rate limit: ~60 requests/minute
            time.sleep(1.0)

        current += timedelta(days=1)

    return {"inserted": inserted, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser(description="Backfill GDELT daily sentiment")
    parser.add_argument(
        "--years", type=int, default=5, help="Years of history (default: 5)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting"
    )
    parser.add_argument(
        "--specialist",
        default="all",
        help="Single specialist or 'all' (default: all)",
    )
    parser.add_argument(
        "--sample-days",
        type=int,
        default=0,
        help="Only fetch N sample days (for testing)",
    )
    args = parser.parse_args()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.years * 365)

    if args.sample_days > 0:
        start_date = end_date - timedelta(days=args.sample_days)

    specialists = (
        list(SPECIALIST_QUERIES.keys())
        if args.specialist == "all"
        else [args.specialist]
    )

    print("=" * 70)
    print("GDELT DAILY SENTIMENT BACKFILL")
    print("=" * 70)
    print(f"  Date range: {start_date.date()} to {end_date.date()}")
    print(f"  Specialists: {', '.join(specialists)}")
    print(f"  Dry run: {args.dry_run}")
    days = (end_date - start_date).days
    total_queries = sum(len(SPECIALIST_QUERIES.get(s, [])) for s in specialists)
    print(
        f"  Estimated API calls: ~{days * total_queries:,} ({days} days x {total_queries} queries)"
    )
    print(f"  Estimated time: ~{days * total_queries / 60:.0f} minutes")
    print()

    conn = None
    if not args.dry_run:
        conn = psycopg2.connect(DATABASE_URL)

    grand_total = {"inserted": 0, "skipped": 0}

    for specialist in specialists:
        print(f"\n  [{specialist.upper()}]")
        queries = SPECIALIST_QUERIES.get(specialist, [])
        print(f"    Queries: {len(queries)}")
        for q in queries:
            print(f"      - {q[:70]}")

        result = backfill_specialist(
            conn, specialist, start_date, end_date, args.dry_run
        )
        grand_total["inserted"] += result["inserted"]
        grand_total["skipped"] += result["skipped"]
        print(f"    Result: {result['inserted']} inserted, {result['skipped']} skipped")

    if conn:
        conn.close()

    print("\n" + "=" * 70)
    print("BACKFILL COMPLETE")
    print("=" * 70)
    print(f"  Total inserted: {grand_total['inserted']:,}")
    print(f"  Total skipped:  {grand_total['skipped']:,}")
    print()
    print(
        "NOTE: For full 5-year backfill, this takes ~30+ hours due to GDELT rate limits."
    )
    print("Recommended: Run with --specialist <name> to backfill one at a time,")
    print("or use --sample-days 30 to test first.")


if __name__ == "__main__":
    main()
