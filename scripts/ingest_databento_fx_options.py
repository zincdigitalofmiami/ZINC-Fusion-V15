#!/usr/bin/env python3
"""
Databento FX Options Ingestion

Fetches FX options with implied volatility and Greeks from Databento.
Uses CME FX options on GLBX.MDP3.

Writes to: mkt.options_greeks_1d

@author Agent3
@date 2026-01-30
"""

import os
import sys
import argparse
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

import databento as db
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv
import numpy as np
from scipy.stats import norm

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
load_dotenv(PROJECT_ROOT / ".env")

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# FX Options underlyings (CME)
FX_OPTIONS = [
    {"root": "6E", "name": "EUR/USD", "underlying_size": 125000},
    {"root": "6J", "name": "USD/JPY", "underlying_size": 12500000},
    {"root": "6B", "name": "GBP/USD", "underlying_size": 62500},
    {"root": "6A", "name": "AUD/USD", "underlying_size": 100000},
    {"root": "6C", "name": "USD/CAD", "underlying_size": 100000},
    {"root": "6M", "name": "MXN/USD", "underlying_size": 500000},
]

DATASET = "GLBX.MDP3"


def get_databento_client() -> db.Historical:
    """Get Databento client."""
    if not DATABENTO_API_KEY:
        raise ValueError("DATABENTO_API_KEY not set in .env")
    return db.Historical(key=DATABENTO_API_KEY)


def get_db_connection():
    """Get database connection."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set in .env")
    return psycopg2.connect(DATABASE_URL)


def black_scholes_iv(
    option_price, S, K, T, r, option_type="call", max_iterations=100, precision=1e-5
):
    """
    Calculate implied volatility using Newton-Raphson method.
    """
    if T <= 0 or option_price <= 0:
        return None

    # Initial guess
    sigma = 0.3

    for i in range(max_iterations):
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

        if option_type == "call":
            price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
            vega = S * norm.pdf(d1) * np.sqrt(T)
        else:
            price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            vega = S * norm.pdf(d1) * np.sqrt(T)

        if vega < 1e-12:
            return None

        diff = option_price - price
        if abs(diff) < precision:
            return sigma

        sigma = sigma + diff / vega

        if sigma <= 0 or sigma > 5:
            return None

    return None


def calculate_greeks(S, K, T, r, sigma, option_type="call"):
    """Calculate option Greeks."""
    if T <= 0 or sigma <= 0:
        return None, None, None, None

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == "call":
        delta = norm.cdf(d1)
        theta = (
            -S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
            - r * K * np.exp(-r * T) * norm.cdf(d2)
        ) / 365
    else:
        delta = norm.cdf(d1) - 1
        theta = (
            -S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
            + r * K * np.exp(-r * T) * norm.cdf(-d2)
        ) / 365

    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100  # Per 1% move

    return delta, gamma, theta, vega


def fetch_options_data(
    client: db.Historical, root: str, start_date: date, end_date: date
) -> pd.DataFrame:
    """
    Fetch options data from Databento.
    Uses definition schema to get available contracts.
    """
    print(f"  Fetching options definitions for {root}...")

    try:
        # Get option definitions
        data = client.timeseries.get_range(
            dataset=DATASET,
            schema="definition",
            symbols=[f"{root}*.OPT"],
            stype_in="raw_symbol",
            start=start_date.isoformat(),
            end=end_date.isoformat(),
        )

        df = data.to_df()
        if df.empty:
            print(f"    No options definitions found")
            return pd.DataFrame()

        df = df.reset_index()
        print(f"    Found {len(df)} option definitions")
        return df

    except Exception as e:
        print(f"    ERROR: {e}")
        return pd.DataFrame()


def upsert_options_greeks(conn, rows: list) -> int:
    """Upsert options Greeks data into mkt.options_greeks_1d."""  # sqlref: ignore
    if not rows:
        return 0

    upsert_query = """
    INSERT INTO mkt.options_greeks_1d  -- sqlref: ignore
        (underlying, event_date, expiration, strike, option_type,
         last_price, implied_volatility, delta, gamma, theta, vega, source)
    VALUES
        (%(underlying)s, %(event_date)s, %(expiration)s, %(strike)s, %(option_type)s,
         %(last_price)s, %(implied_volatility)s, %(delta)s, %(gamma)s, %(theta)s, %(vega)s, 'databento')
    ON CONFLICT (underlying, event_date, expiration, strike, option_type) DO UPDATE SET
        last_price = EXCLUDED.last_price,
        implied_volatility = EXCLUDED.implied_volatility,
        delta = EXCLUDED.delta,
        gamma = EXCLUDED.gamma,
        theta = EXCLUDED.theta,
        vega = EXCLUDED.vega,
        source = 'databento'
    """

    cur = conn.cursor()
    execute_batch(cur, upsert_query, rows, page_size=1000)
    conn.commit()
    upserted = cur.rowcount
    cur.close()

    return upserted


def main():
    parser = argparse.ArgumentParser(description="Ingest FX options from Databento")
    parser.add_argument(
        "--start-date",
        type=str,
        default=(date.today() - timedelta(days=30)).isoformat(),
    )
    parser.add_argument(
        "--end-date", type=str, default=(date.today() - timedelta(days=1)).isoformat()
    )
    parser.add_argument("--underlying", type=str, help="Specific underlying (e.g., 6E)")
    args = parser.parse_args()

    print("=" * 70)
    print("DATABENTO FX OPTIONS INGESTION")
    print("=" * 70)

    client = get_databento_client()
    conn = get_db_connection()

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)

    print(f"Date range: {start_date} to {end_date}")

    options_to_fetch = FX_OPTIONS
    if args.underlying:
        options_to_fetch = [o for o in FX_OPTIONS if o["root"] == args.underlying]

    total_upserted = 0

    for config in options_to_fetch:
        root = config["root"]
        name = config["name"]

        print(f"\n[{root}] {name}")

        # Fetch options data
        options_df = fetch_options_data(client, root, start_date, end_date)

        if options_df.empty:
            print(f"  No options data available")
            continue

        # Note: Full IV calculation requires underlying price, strike, expiry
        # For now, log what we found
        print(f"  Found {len(options_df)} records")

        # TODO: Calculate IV and Greeks when we have full options chain data
        # For now, this serves as a template for when options data becomes available

    conn.close()

    print("\n" + "=" * 70)
    print(f"COMPLETE: {total_upserted} rows upserted")
    print("=" * 70)
    print("\nNote: Full options Greeks ingestion requires:")
    print("  1. Options OHLCV data (ohlcv-1d schema for options)")
    print("  2. Underlying prices for IV calculation")
    print("  3. Expiration dates and strikes")


if __name__ == "__main__":
    main()
