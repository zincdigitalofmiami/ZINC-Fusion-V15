#!/usr/bin/env python3
"""
Backfill 5 years of Federal Register documents into alt.legislation_1d.

The Inngest daily job (federal-register.ts) only fetches the last 7 days.
This script fetches the full 5-year archive from the Federal Register API,
applying the same tag-assignment and deduplication logic.

SOURCE: https://www.federalregister.gov/api/v1/
  - No API key required (public API)
  - Rate limit: ~1000 requests/hour
  - Returns: title, abstract, publication_date, html_url, type, agencies

Document types:
  - RULE (Final rules)
  - PRORULE (Proposed rules)
  - NOTICE (Notices)
  - PRESDOCU (Presidential documents)

Usage:
    .venv/bin/python scripts/backfill_federal_register.py
    .venv/bin/python scripts/backfill_federal_register.py --years 3
    .venv/bin/python scripts/backfill_federal_register.py --dry-run
"""

import argparse
import hashlib
import os
import re
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

FEDERAL_REGISTER_BASE = "https://www.federalregister.gov/api/v1/documents.json"
DOC_TYPES = ["RULE", "PRORULE", "NOTICE", "PRESDOCU"]

# Tag assignment rules — mirrors federal-register.ts TAG_RULES
TAG_RULES = [
    (re.compile(r"section[\s_-]?301", re.I), ["tariff"]),
    (re.compile(r"section[\s_-]?232", re.I), ["tariff"]),
    (re.compile(r"tariff[\s_-]?(rate|schedule|exclusion|list)", re.I), ["tariff"]),
    (re.compile(r"anti[\s_-]?dumping", re.I), ["tariff"]),
    (re.compile(r"countervailing[\s_-]?dut", re.I), ["tariff"]),
    (
        re.compile(r"trade[\s_-]?(deal|agreement|negotiation)", re.I),
        ["tariff", "trump_effect"],
    ),
    (re.compile(r"usmca|nafta", re.I), ["tariff", "trump_effect"]),
    (re.compile(r"\bchina\b|\bprc\b|chinese", re.I), ["china", "tariff"]),
    (re.compile(r"cofco|sinograin", re.I), ["china"]),
    (re.compile(r"executive[\s_-]?order", re.I), ["trump_effect"]),
    (
        re.compile(
            r"presidential[\s_-]?(action|memorandum|proclamation|determination)", re.I
        ),
        ["trump_effect"],
    ),
    (re.compile(r"doge|government[\s_-]?efficiency", re.I), ["trump_effect"]),
    (
        re.compile(
            r"immigration|ice[\s_-]enforcement|deportation|visa|border[\s_-]?(security|control)",
            re.I,
        ),
        ["trump_effect"],
    ),
    (re.compile(r"renewable[\s_-]?fuel[\s_-]?standard|rfs", re.I), ["biofuel"]),
    (
        re.compile(r"\brin\b|renewable[\s_-]?identification[\s_-]?number", re.I),
        ["biofuel"],
    ),
    (re.compile(r"biodiesel|renewable[\s_-]?diesel", re.I), ["biofuel"]),
    (re.compile(r"\b45z\b|section[\s_-]?45z", re.I), ["biofuel"]),
    (re.compile(r"clean[\s_-]?fuel[\s_-]?production[\s_-]?credit", re.I), ["biofuel"]),
    (
        re.compile(r"sustainable[\s_-]?aviation[\s_-]?fuel|saf[\s_-]?credit", re.I),
        ["biofuel"],
    ),
    (re.compile(r"lcfs|low[\s_-]?carbon[\s_-]?fuel[\s_-]?standard", re.I), ["biofuel"]),
    (re.compile(r"clean[\s_-]?fuel", re.I), ["biofuel"]),
    (re.compile(r"epa.*fuel|fuel.*epa", re.I), ["biofuel"]),
    (re.compile(r"blending[\s_-]?mandate|blender", re.I), ["biofuel"]),
    (re.compile(r"petroleum|crude[\s_-]?oil|refiner", re.I), ["energy"]),
    (re.compile(r"natural[\s_-]?gas|lng", re.I), ["energy"]),
    (re.compile(r"opec|oil[\s_-]?export", re.I), ["energy"]),
    (re.compile(r"soybean|soy[\s_-]?oil|soy[\s_-]?meal", re.I), ["crush"]),
    (re.compile(r"usda|department[\s_-]?of[\s_-]?agriculture", re.I), ["crush"]),
    (re.compile(r"grain|corn|wheat", re.I), ["crush", "substitutes"]),
    (re.compile(r"federal[\s_-]?reserve|fomc|monetary[\s_-]?policy", re.I), ["fed"]),
    (re.compile(r"interest[\s_-]?rate|treasury[\s_-]?yield", re.I), ["fed"]),
    (re.compile(r"sanctions|ofac|export[\s_-]?control", re.I), ["tariff", "china"]),
]


def assign_tags(
    title: str, abstract: str, doc_type: str, agencies: list[str]
) -> list[str]:
    """Assign specialist tags — mirrors TypeScript assignTags()."""
    content = f"{title} {abstract} {' '.join(agencies)}".lower()
    tags = set()

    if doc_type == "PRESDOCU":
        tags.add("trump_effect")

    for pattern, rule_tags in TAG_RULES:
        if pattern.search(content):
            tags.update(rule_tags)

    return list(tags) if tags else ["general"]


def compute_row_hash(document_number: str, pub_date: str) -> str:
    """Compute SHA256 hash — mirrors TypeScript computeRowHash()."""
    payload = f"{document_number}|{pub_date}"
    return hashlib.sha256(payload.encode()).hexdigest()


def fetch_month(year: int, month: int) -> list[dict]:
    """Fetch all Federal Register documents for a given month."""
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1}-01-01"
    else:
        end = f"{year}-{month + 1:02d}-01"

    # Subtract 1 day from end to get last day of month
    end_date = datetime.strptime(end, "%Y-%m-%d") - timedelta(days=1)
    end = end_date.strftime("%Y-%m-%d")

    all_docs = []
    page = 1

    while True:
        params = {
            "per_page": "100",
            "page": str(page),
            "order": "oldest",
            "conditions[publication_date][gte]": start,
            "conditions[publication_date][lte]": end,
        }
        for doc_type in DOC_TYPES:
            params["conditions[type][]"] = doc_type

        # Build URL with multiple type params
        url = FEDERAL_REGISTER_BASE + "?"
        url += f"per_page=100&page={page}&order=oldest"
        url += f"&conditions[publication_date][gte]={start}"
        url += f"&conditions[publication_date][lte]={end}"
        for dt in DOC_TYPES:
            url += f"&conditions[type][]={dt}"

        try:
            resp = requests.get(
                url, timeout=30, headers={"User-Agent": "ZincFusion/1.0"}
            )
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            all_docs.extend(results)

            if not data.get("next_page_url"):
                break
            page += 1
            time.sleep(0.15)  # Rate limit
        except Exception as e:
            print(f"    ERROR fetching {year}-{month:02d} page {page}: {e}")
            break

    return all_docs


def main():
    parser = argparse.ArgumentParser(description="Backfill Federal Register (5yr)")
    parser.add_argument(
        "--years", type=int, default=5, help="Years of history (default: 5)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("FEDERAL REGISTER 5-YEAR BACKFILL")
    print("=" * 70)
    print(f"  Years: {args.years}")
    print(f"  Dry run: {args.dry_run}")

    start_date = datetime.now() - timedelta(days=args.years * 365)
    end_date = datetime.now()

    conn = None
    if not args.dry_run:
        conn = psycopg2.connect(DATABASE_URL)

    total_fetched = 0
    total_inserted = 0
    total_skipped = 0
    total_errors = 0

    # Iterate month by month
    current = datetime(start_date.year, start_date.month, 1)
    while current <= end_date:
        year, month = current.year, current.month
        print(f"\n  [{year}-{month:02d}] Fetching ... ", end="", flush=True)

        docs = fetch_month(year, month)
        total_fetched += len(docs)
        print(f"{len(docs)} docs", end="")

        month_inserted = 0
        month_skipped = 0

        if not args.dry_run and conn:
            cur = conn.cursor()
            for doc in docs:
                doc_number = doc.get("document_number", "")
                pub_date = doc.get("publication_date", "")

                if not doc_number or not pub_date:
                    total_errors += 1
                    continue

                row_hash = compute_row_hash(doc_number, pub_date)

                # Check duplicate
                cur.execute(
                    "SELECT 1 FROM alt.legislation_1d WHERE row_hash = %s LIMIT 1",
                    (row_hash,),
                )
                if cur.fetchone():
                    month_skipped += 1
                    continue

                agencies = [a.get("name", "") for a in (doc.get("agencies") or [])]
                tags = assign_tags(
                    doc.get("title", ""),
                    doc.get("abstract", ""),
                    doc.get("type", ""),
                    agencies,
                )

                try:
                    cur.execute(
                        """
                        INSERT INTO alt.legislation_1d (
                            event_date, document_number, document_type, title, agency,
                            source, url, raw_payload, row_hash, specialist_tags
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            pub_date,
                            doc_number,
                            doc.get("type"),
                            doc.get("title", "")[:500],
                            ", ".join(agencies)[:500],
                            "federal_register_api",
                            doc.get("html_url"),
                            None,  # Skip raw_payload for backfill (saves space)
                            row_hash,
                            tags,
                        ),
                    )
                    month_inserted += 1
                except Exception:
                    total_errors += 1
                    conn.rollback()

            conn.commit()

        total_inserted += month_inserted
        total_skipped += month_skipped
        print(f" → {month_inserted} new, {month_skipped} dups")

        # Next month
        if month == 12:
            current = datetime(year + 1, 1, 1)
        else:
            current = datetime(year, month + 1, 1)

        time.sleep(0.2)

    if conn:
        conn.close()

    print("\n" + "=" * 70)
    print("BACKFILL COMPLETE")
    print("=" * 70)
    print(f"  Total fetched:  {total_fetched:,}")
    print(f"  Total inserted: {total_inserted:,}")
    print(f"  Total skipped:  {total_skipped:,}")
    print(f"  Total errors:   {total_errors:,}")


if __name__ == "__main__":
    main()
