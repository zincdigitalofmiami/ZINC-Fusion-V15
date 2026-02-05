#!/usr/bin/env python3
"""
Backfill FX spot rates from FRED into mkt.fx_1d.

Pulls all major currency pairs from 2010-01-01 to 2026-02-02.
Uses canonical no-slash naming (EURUSD, GBPUSD, etc.)

Usage:
    .venv/bin/python scripts/backfill_fx_spot_FRED.py
"""

import os
import ssl
import sys
from datetime import date, datetime
from typing import Optional

# Fix SSL certificate issues on macOS
import certifi

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

try:
    from fredapi import Fred
except ImportError:
    print("ERROR: fredapi not installed. Run: pip install fredapi")
    sys.exit(1)

DATABASE_URL = os.environ.get("DATABASE_URL")
FRED_API_KEY = os.environ.get("FRED_API_KEY")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)
if not FRED_API_KEY:
    print("ERROR: FRED_API_KEY not set")
    sys.exit(1)

# FRED series -> canonical pair name
# Note: FRED quotes vary (some USD/X, some X/USD)
FRED_FX_SERIES = {
    "DEXUSEU": "EURUSD",  # EUR/USD (inverted in FRED as USD per EUR)
    "DEXUSUK": "GBPUSD",  # GBP/USD
    "DEXUSAL": "AUDUSD",  # AUD/USD
    "DEXJPUS": "USDJPY",  # USD/JPY
    "DEXCAUS": "USDCAD",  # USD/CAD
    "DEXCHUS": "USDCNY",  # USD/CNY
    "DEXBZUS": "USDBRL",  # USD/BRL
    "DEXMXUS": "USDMXN",  # USD/MXN
    "DEXKOUS": "USDKRW",  # USD/KRW
    "DEXSFUS": "USDSGD",  # USD/SGD (Singapore)
    "DEXSZUS": "USDCHF",  # USD/CHF (Switzerland)
    "DEXNOUS": "USDNOK",  # USD/NOK (Norway)
    "DEXSDUS": "USDSEK",  # USD/SEK (Sweden)
    "DEXINUS": "USDINR",  # USD/INR (India)
    "DEXTAUS": "USDTWD",  # USD/TWD (Taiwan)
    "DEXHKUS": "USDHKD",  # USD/HKD (Hong Kong)
    "DEXMAUS": "USDMYR",  # USD/MYR (Malaysia)
    "DEXTHUS": "USDTHB",  # USD/THB (Thailand)
    "DTWEXBGS": "DXY_BROAD",  # Trade-weighted USD broad
    "DTWEXAFEGS": "DXY_AFE",  # Trade-weighted USD AFE
    "DTWEXEMEGS": "DXY_EME",  # Trade-weighted USD EME
}

START_DATE = date(2010, 1, 1)
END_DATE = date(2026, 2, 2)


def fetch_fred_series(fred: Fred, series_id: str) -> Optional[pd.Series]:
    """Fetch a single FRED series."""
    try:
        data = fred.get_series(
            series_id,
            observation_start=START_DATE,
            observation_end=END_DATE,
        )
        return data.dropna()
    except Exception as e:
        print(f"  WARNING: Failed to fetch {series_id}: {e}")
        return None


def upsert_fx_rates(conn, pair: str, rates: list[tuple]):
    """Upsert FX rates into mkt.fx_1d."""
    if not rates:
        return 0

    cur = conn.cursor()

    # Use ON CONFLICT to upsert
    execute_values(
        cur,
        """
        INSERT INTO mkt.fx_1d (pair, event_date, rate, source, ingested_at)
        VALUES %s
        ON CONFLICT (pair, event_date) DO UPDATE SET
            rate = EXCLUDED.rate,
            source = EXCLUDED.source,
            ingested_at = NOW()
        """,
        rates,
        template="(%s, %s, %s, %s, NOW())",
        page_size=1000,
    )

    conn.commit()
    return len(rates)


def main():
    print("=" * 70)
    print("FX Spot Rate Backfill from FRED")
    print(f"Date range: {START_DATE} to {END_DATE}")
    print("=" * 70)

    fred = Fred(api_key=FRED_API_KEY)
    conn = psycopg2.connect(DATABASE_URL)

    total_rows = 0

    for series_id, pair in FRED_FX_SERIES.items():
        print(f"\n[{pair}] Fetching {series_id}...")

        data = fetch_fred_series(fred, series_id)
        if data is None or len(data) == 0:
            print(f"  SKIP: No data")
            continue

        # Build records
        rates = []
        for dt, value in data.items():
            if pd.notna(value):
                rates.append((pair, dt.date(), float(value), "FRED"))

        # Upsert
        count = upsert_fx_rates(conn, pair, rates)
        total_rows += count
        print(
            f"  OK: {count} rows ({data.index.min().date()} to {data.index.max().date()})"
        )

    conn.close()

    print("\n" + "=" * 70)
    print(f"DONE: {total_rows:,} total rows upserted")
    print("=" * 70)


if __name__ == "__main__":
    main()
