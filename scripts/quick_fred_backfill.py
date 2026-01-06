#!/usr/bin/env python3
"""
Quick FRED backfill script - pulls data back to 2000 for all Big-11 series.
"""

import os
import sys
import time
from datetime import datetime
from typing import Dict, List

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
    "DPROPANEUSGULF": "Propane Gulf Coast",

    # CRUSH SPECIALIST - Soybean complex from FRED
    "PSOILUSDM": "Soybean Oil Price (World Bank)",
    "PSOYBUSDM": "Soybeans Price (World Bank)",
    "PMAABORPCSF": "Palm Oil Price (World Bank)",
    "PBARLUSDM": "Barley Price",
    "PMAABORPCPF": "Palm Kernel Oil Price",
    "PWHEAMTUSDM": "Wheat Price",
    "PCORNUSDM": "Corn Price",

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


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


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


def insert_fred_data(conn, series_id: str, df: pd.DataFrame) -> int:
    """Insert FRED data into database."""
    if df.empty:
        return 0

    records = [
        (
            series_id,
            row["date"],
            row["value"],
            "FRED"
        )
        for _, row in df.iterrows()
    ]

    try:
        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO "raw"."fred_observations_1d"
                (series_id, as_of_date, value, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (series_id, as_of_date) DO NOTHING
                """,
                records,
                page_size=500
            )
            inserted = cur.rowcount
        conn.commit()
        return inserted
    except Exception as e:
        print(f"  Error inserting {series_id}: {e}")
        conn.rollback()
        return 0


def main():
    print("=" * 60)
    print("FRED BACKFILL TO 2000")
    print("=" * 60)
    print(f"Series to backfill: {len(FRED_SERIES)}")
    print(f"Start date: 2000-01-01")
    print()

    if not FRED_API_KEY:
        print("ERROR: FRED_API_KEY not set in environment")
        return 1

    conn = get_postgres_connection()

    total_inserted = 0
    total_fetched = 0

    for i, (series_id, description) in enumerate(FRED_SERIES.items(), 1):
        print(f"[{i}/{len(FRED_SERIES)}] {series_id}: {description}")

        df = fetch_fred_series(series_id, "2000-01-01")

        if df.empty:
            print(f"  No data available")
            time.sleep(0.3)
            continue

        fetched = len(df)
        inserted = insert_fred_data(conn, series_id, df)

        print(f"  Fetched: {fetched:,} | Inserted: {inserted:,}")
        total_fetched += fetched
        total_inserted += inserted

        # Rate limit: FRED allows ~120 requests/minute
        time.sleep(0.5)

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
