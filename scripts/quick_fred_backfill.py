#!/usr/bin/env python3
"""
Quick FRED backfill script - pulls data back to 2000 for all Big-11 series.
"""

import argparse
import hashlib
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
import requests

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# FRED API
FRED_API_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = os.getenv("FRED_API_KEY")

# All Big-11 specialist FRED series
FRED_SERIES = {
    # FED SPECIALIST - Interest Rates, Yields, Monetary Policy
    "DFF": "Fed Funds Effective Rate (Daily)",
    "DGS1MO": "1-Month Treasury",
    "DGS3MO": "3-Month Treasury",
    "DGS6MO": "6-Month Treasury",
    "DGS1": "1-Year Treasury",
    "DGS2": "2-Year Treasury",
    "DGS5": "5-Year Treasury",
    "DGS7": "7-Year Treasury",
    "DGS10": "10-Year Treasury",
    "DGS20": "20-Year Treasury",
    "DGS30": "30-Year Treasury",
    "T10Y2Y": "10Y-2Y Spread (Yield Curve)",
    "T10Y3M": "10Y-3M Spread",
    "T10YIE": "10Y Breakeven Inflation",
    "SOFR": "SOFR Rate",
    "DPRIME": "Prime Rate",
    "MORTGAGE30US": "30-Year Mortgage Rate",
    "WALCL": "Fed Total Assets",
    "WRESBAL": "Reserve Balances",
    "RRPONTSYD": "Reverse Repo",

    # FX SPECIALIST - Currency
    "DEXBZUS": "USD/BRL (Brazil)",
    "DEXCHUS": "USD/CNY (China)",
    "DEXUSEU": "USD/EUR",
    "DEXUSUK": "USD/GBP",
    "DEXJPUS": "USD/JPY",
    "DEXCAUS": "USD/CAD",
    "DEXMXUS": "USD/MXN",
    "DEXKOUS": "USD/KRW (Korea)",
    "DEXINUS": "USD/INR (India)",
    "DEXMAUS": "USD/MYR (Malaysia)",
    "DEXSFUS": "USD/SGD (Singapore)",
    "DEXTHUS": "USD/THB (Thailand)",
    "DEXHKUS": "USD/HKD (Hong Kong)",
    "DEXTAUS": "USD/TWD (Taiwan)",
    "DEXUSAL": "USD/AUD",
    "DEXNOUS": "USD/NOK",
    "DEXSZUS": "USD/CHF",
    "DEXSIUS": "USD/SEK",
    "DTWEXBGS": "Trade-Weighted USD (Broad)",
    "DTWEXAFEGS": "USD vs Advanced FX",
    "DTWEXEMEGS": "USD vs EM FX",

    # ENERGY SPECIALIST
    "DCOILWTICO": "WTI Crude Oil",
    "DCOILBRENTEU": "Brent Crude Oil",
    "DHHNGSP": "Henry Hub Natural Gas",
    "DDFUELUSGULF": "Diesel Gulf Coast",
    "DGASUSGULF": "Gasoline Gulf Coast",
    "DJFUELUSGULF": "Jet Fuel Gulf Coast",
    "DPROPANEMBTX": "Propane Prices: Mont Belvieu, Texas",

    # CRUSH SPECIALIST - Soybean complex from FRED
    "PSOILUSDM": "Soybean Oil Price (World Bank)",
    "PSOYBUSDM": "Soybeans Price (World Bank)",
    "PPOILUSDM": "Global price of Palm Oil",
    "PBARLUSDM": "Barley Price",
    "PROILUSDM": "Global price of Rapeseed Oil (proxy for palm kernel)",
    "PWHEAMTUSDM": "Wheat Price",
    "PMAIZMTUSDM": "Global price of Corn",

    # VOLATILITY SPECIALIST
    "VIXCLS": "VIX Index",
    "STLFSI4": "St. Louis Financial Stress",
    "NFCI": "Chicago Fed Financial Conditions",
    "CLVMNACSCAB1GQEA19": "Euro Area Financial Stress",
    "BAMLH0A0HYM2": "High Yield OAS",
    "BAMLC0A0CM": "Corporate OAS",

    # TRUMP EFFECT / POLICY SPECIALIST
    "USEPUINDXD": "US Policy Uncertainty (Daily)",
    "USEPUINDXM": "US Policy Uncertainty (Monthly)",

    # Macro indicators
    "ICSA": "Initial Jobless Claims (Weekly)",
    "CCSA": "Continued Claims (Weekly)",
    "CPIAUCSL": "CPI All Urban",
    "CPILFESL": "Core CPI",
    "PCEPI": "PCE Price Index",
    "PCEPILFE": "Core PCE",
    "UNRATE": "Unemployment Rate",
    "PAYEMS": "Nonfarm Payrolls",
    "INDPRO": "Industrial Production",
    "UMCSENT": "Consumer Sentiment",
}

FALLBACK_TAGS: Dict[str, list[str]] = {
    "DPROPANEMBTX": ["energy"],
    "PMAIZMTUSDM": ["crush", "substitutes"],
    "PROILUSDM": ["palm", "substitutes"],
    "PPOILUSDM": ["palm"],
}


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def js_number_string(value: float) -> str:
    """Mirror JS Number.toString() formatting for row_hash consistency."""
    return format(value, ".15g")


def compute_row_hash(series_id: str, event_date: datetime, value: float) -> str:
    payload = f"{series_id}|{event_date.strftime('%Y-%m-%d')}|{js_number_string(value)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_ingest_run(conn, job_name: str) -> str:
    """Create ops.ingest_run record and return run_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ops.ingest_run (job_name, status, started_at, rows_attempted, rows_inserted, rows_skipped, rows_quarantined)
            VALUES (%s, 'running', NOW(), 0, 0, 0, 0)
            RETURNING id
            """,
            (job_name,),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return str(run_id)


def complete_ingest_run(
    conn,
    run_id: str,
    status: str,
    attempted: int,
    inserted: int,
    skipped: int,
    quarantined: int,
    error_message: str | None = None,
) -> None:
    """Update ops.ingest_run with final counters."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ops.ingest_run
            SET status = %s,
                completed_at = NOW(),
                rows_attempted = %s,
                rows_inserted = %s,
                rows_skipped = %s,
                rows_quarantined = %s,
                error_message = %s
            WHERE id = %s
            """,
            (status, attempted, inserted, skipped, quarantined, error_message, run_id),
        )
    conn.commit()


def load_series_tags(conn) -> Dict[str, list[str]]:
    """Load most recent specialist_tags per series from DB."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (series_id) series_id, specialist_tags
            FROM raw.fred_observations_1d
            WHERE specialist_tags IS NOT NULL
            ORDER BY series_id, event_date DESC, knowledge_time DESC
            """
        )
        tags_map: Dict[str, list[str]] = {}
        for series_id, tags in cur.fetchall():
            if tags:
                tags_map[series_id] = list(tags)
        return tags_map


def series_exists(conn, series_id: str) -> bool:
    """Check if series already has any rows."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM raw.fred_observations_1d WHERE series_id=%s LIMIT 1",
            (series_id,),
        )
        return cur.fetchone() is not None


def fetch_fred_series(series_id: str, start_date: str = "2000-01-01") -> pd.DataFrame:
    """Fetch FRED series from API."""
    if not FRED_API_KEY:
        print(f"  Warning: No FRED_API_KEY, skipping {series_id}")
        return pd.DataFrame()

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": datetime.now().strftime("%Y-%m-%d"),
    }

    try:
        response = requests.get(FRED_API_BASE, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        observations = data.get("observations", [])
        if not observations:
            return pd.DataFrame()

        df = pd.DataFrame(observations)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["value"])

        return df[["date", "value"]]

    except Exception as e:
        print(f"  Error fetching {series_id}: {e}")
        return pd.DataFrame()


def insert_fred_data(
    conn,
    series_id: str,
    df: pd.DataFrame,
    tags: list[str] | None,
    run_id: str,
) -> int:
    """Insert FRED data into database."""
    if df.empty:
        return 0

    now = datetime.now(timezone.utc)
    records = []
    for _, row in df.iterrows():
        event_date = row["date"].to_pydatetime() if hasattr(row["date"], "to_pydatetime") else row["date"]
        value = float(row["value"])
        records.append(
            (
                series_id,
                event_date,
                value,
                "fred_api",
                now,
                1,
                False,
                "validated",
                f"https://fred.stlouisfed.org/series/{series_id}",
                run_id,
                compute_row_hash(series_id, event_date, value),
                tags,
            )
        )

    try:
        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO "raw"."fred_observations_1d"
                (series_id, event_date, value, source, knowledge_time, revision_no, is_preliminary, validation_status, source_url, ingestion_batch_id, row_hash, specialist_tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                records,
                page_size=500
            )
            inserted = len(records)
        conn.commit()
        return inserted
    except Exception as e:
        print(f"  Error inserting {series_id}: {e}")
        conn.rollback()
        return 0


def main():
    parser = argparse.ArgumentParser(description="Backfill FRED series into raw.fred_observations_1d")
    parser.add_argument(
        "--series",
        help="Comma-separated list of FRED series IDs to backfill (default: all in script)",
    )
    parser.add_argument(
        "--start-date",
        default="2000-01-01",
        help="Start date for backfill (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Backfill even if the series already exists in the DB",
    )
    args = parser.parse_args()

    if args.series:
        series_ids = [s.strip() for s in args.series.split(",") if s.strip()]
    else:
        series_ids = list(FRED_SERIES.keys())

    print("=" * 60)
    print("FRED BACKFILL TO 2000")
    print("=" * 60)
    print(f"Series to backfill: {len(series_ids)}")
    print(f"Start date: {args.start_date}")
    print()

    if not FRED_API_KEY:
        print("ERROR: FRED_API_KEY not set in environment")
        return 1

    conn = get_postgres_connection()
    tags_map = load_series_tags(conn)
    run_id = create_ingest_run(conn, "fred-backfill")

    total_inserted = 0
    total_fetched = 0
    total_attempted = 0
    total_skipped = 0

    for i, series_id in enumerate(series_ids, 1):
        description = FRED_SERIES.get(series_id, "Custom series")
        print(f"[{i}/{len(series_ids)}] {series_id}: {description}")
        total_attempted += 1

        if not args.force and series_exists(conn, series_id):
            print("  Already in DB, skipping (use --force to override)")
            total_skipped += 1
            continue

        df = fetch_fred_series(series_id, args.start_date)

        if df.empty:
            print(f"  No data available")
            time.sleep(0.3)
            continue

        fetched = len(df)
        tags = tags_map.get(series_id) or FALLBACK_TAGS.get(series_id)
        inserted = insert_fred_data(conn, series_id, df, tags, run_id)

        print(f"  Fetched: {fetched:,} | Inserted: {inserted:,}")
        total_fetched += fetched
        total_inserted += inserted

        # Rate limit: FRED allows ~120 requests/minute
        time.sleep(0.5)

    complete_ingest_run(
        conn,
        run_id,
        "success",
        total_attempted,
        total_inserted,
        total_skipped,
        0,
    )
    conn.close()

    print()
    print("=" * 60)
    print("BACKFILL COMPLETE")
    print("=" * 60)
    print(f"Total fetched: {total_fetched:,}")
    print(f"Total inserted: {total_inserted:,}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
