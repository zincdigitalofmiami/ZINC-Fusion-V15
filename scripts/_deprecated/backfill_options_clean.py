#!/usr/bin/env python3
"""
Clean Options Backfill with Full Greeks

Fetches options data from Databento and writes to mkt.options_1d with:
- Proper strike price handling (respects Databento's display_factor)
- IV and delta from Databento statistics (stat_type 14, 15)
- Gamma, theta, vega, rho calculated via Black-76

Usage:
    python scripts/backfill_options_clean.py --underlying ZL --start 2024-01-01
    python scripts/backfill_options_clean.py --underlying ZL --days 30
    python scripts/backfill_options_clean.py --all --start 2020-01-01
"""

import os
import sys
import argparse
import hashlib
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
import math

import databento as db
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv
from scipy.stats import norm

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
load_dotenv(PROJECT_ROOT / ".env")

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# =============================================================================
# OPTIONS CONFIGURATION
# =============================================================================
OPTIONS_CONFIG = [
    # Ag - Soy Complex (priority)
    {"underlying": "ZL", "name": "Soybean Oil", "parent": "OZL.OPT", "tick_size": 0.01},
    {"underlying": "ZS", "name": "Soybeans", "parent": "OZS.OPT", "tick_size": 0.25},
    {"underlying": "ZM", "name": "Soybean Meal", "parent": "OZM.OPT", "tick_size": 0.1},

    # Ag - Grains
    {"underlying": "ZC", "name": "Corn", "parent": "OZC.OPT", "tick_size": 0.25},
    {"underlying": "ZW", "name": "Wheat", "parent": "OZW.OPT", "tick_size": 0.25},
    {"underlying": "KE", "name": "KC HRW Wheat", "parent": "OKE.OPT", "tick_size": 0.25},

    # Energy
    {"underlying": "CL", "name": "Crude Oil", "parent": "LO.OPT", "tick_size": 0.01},
    {"underlying": "NG", "name": "Natural Gas", "parent": "ON.OPT", "tick_size": 0.001},
    {"underlying": "HO", "name": "Heating Oil", "parent": "OH.OPT", "tick_size": 0.0001},
    {"underlying": "RB", "name": "RBOB Gasoline", "parent": "OB.OPT", "tick_size": 0.0001},

    # Metals
    {"underlying": "GC", "name": "Gold", "parent": "OG.OPT", "tick_size": 0.1},
    {"underlying": "SI", "name": "Silver", "parent": "SO.OPT", "tick_size": 0.005},
    {"underlying": "HG", "name": "Copper", "parent": "HXE.OPT", "tick_size": 0.0005},

    # Equity Index
    {"underlying": "ES", "name": "E-mini S&P 500", "parent": "ES.OPT", "tick_size": 0.25},
    {"underlying": "NQ", "name": "E-mini Nasdaq", "parent": "NQ.OPT", "tick_size": 0.25},

    # Treasuries
    {"underlying": "ZB", "name": "30-Year Treasury", "parent": "OZB.OPT", "tick_size": 1/64},
    {"underlying": "ZN", "name": "10-Year Treasury", "parent": "OZN.OPT", "tick_size": 1/64},
    {"underlying": "ZF", "name": "5-Year Treasury", "parent": "OZF.OPT", "tick_size": 1/64},

    # FX
    {"underlying": "6E", "name": "EUR/USD", "parent": "EUU.OPT", "tick_size": 0.0001},
    {"underlying": "6J", "name": "USD/JPY", "parent": "JPU.OPT", "tick_size": 0.0000005},
    {"underlying": "6B", "name": "GBP/USD", "parent": "GBU.OPT", "tick_size": 0.0001},
    {"underlying": "6A", "name": "AUD/USD", "parent": "ADU.OPT", "tick_size": 0.0001},
    {"underlying": "6C", "name": "USD/CAD", "parent": "CAU.OPT", "tick_size": 0.0001},
]

DATASET = "GLBX.MDP3"
RISK_FREE_RATE = 0.045  # Current approx risk-free rate

# =============================================================================
# BLACK-76 GREEKS CALCULATOR
# =============================================================================

def black76_greeks(
    F: float,      # Futures price
    K: float,      # Strike price
    T: float,      # Time to expiry in years
    r: float,      # Risk-free rate
    sigma: float,  # Implied volatility
    option_type: str  # 'C' or 'P'
) -> dict:
    """
    Calculate full Greeks using Black-76 model for futures options.

    Returns: {delta, gamma, theta, vega, rho}
    """
    if T <= 0 or sigma <= 0 or F <= 0 or K <= 0:
        return {"delta": None, "gamma": None, "theta": None, "vega": None, "rho": None}

    sqrt_T = math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma**2 * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    # Discount factor
    df = math.exp(-r * T)

    # Standard normal PDF and CDF
    n_d1 = norm.pdf(d1)
    N_d1 = norm.cdf(d1)
    N_d2 = norm.cdf(d2)
    N_neg_d1 = norm.cdf(-d1)
    N_neg_d2 = norm.cdf(-d2)

    if option_type.upper() in ('C', 'CALL'):
        delta = df * N_d1
        rho = T * df * F * N_d1 / 100  # Per 1% rate move
    else:  # Put
        delta = -df * N_neg_d1
        rho = -T * df * F * N_neg_d1 / 100

    # Gamma (same for calls and puts)
    gamma = df * n_d1 / (F * sigma * sqrt_T)

    # Vega (same for calls and puts) - per 1% vol move
    vega = F * df * n_d1 * sqrt_T / 100

    # Theta (per day)
    theta_common = -df * F * n_d1 * sigma / (2 * sqrt_T)
    if option_type.upper() in ('C', 'CALL'):
        theta = (theta_common - r * df * F * N_d1 + r * df * K * N_d2) / 365
    else:
        theta = (theta_common + r * df * F * N_neg_d1 - r * df * K * N_neg_d2) / 365

    return {
        "delta": round(delta, 6),
        "gamma": round(gamma, 8),
        "theta": round(theta, 6),
        "vega": round(vega, 6),
        "rho": round(rho, 6),
    }


# =============================================================================
# DATABENTO DATA FETCHING
# =============================================================================

def get_databento_client() -> db.Historical:
    if not DATABENTO_API_KEY:
        raise ValueError("DATABENTO_API_KEY not set")
    return db.Historical(key=DATABENTO_API_KEY)


def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)


def compute_row_hash(underlying: str, event_date: date, expiration: date,
                     strike: float, option_type: str) -> str:
    key = f"{underlying}|{event_date}|{expiration}|{strike}|{option_type}"
    return hashlib.sha256(key.encode()).hexdigest()


def fetch_definitions(client: db.Historical, parent: str, start: date, end: date) -> dict:
    """Fetch option definitions to map instrument_id -> contract details."""
    print(f"    Fetching definitions for {parent}...")
    try:
        data = client.timeseries.get_range(
            dataset=DATASET,
            schema="definition",
            symbols=[parent],
            stype_in="parent",
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
        )
        df = data.to_df()
        if df.empty:
            return {}

        definitions = {}
        for _, row in df.iterrows():
            inst_id = str(row.get("instrument_id", row.get("id", "")))
            if not inst_id:
                continue

            # Get strike - DIVIDE by display_factor for proper scaling
            raw_strike = row.get("strike_price")
            display_factor = row.get("display_factor", 0.001)

            # Skip if no strike or NaN
            if pd.isna(raw_strike) or raw_strike == 0:
                continue
            if pd.isna(display_factor) or display_factor == 0:
                display_factor = 0.001

            strike = float(raw_strike) / float(display_factor)

            # Skip invalid strikes
            if strike <= 0 or strike > 100000:
                continue

            definitions[inst_id] = {
                "strike": strike,
                "expiration": pd.to_datetime(row.get("expiration", row.get("expiry"))).date() if row.get("expiration") or row.get("expiry") else None,
                "option_type": "C" if str(row.get("instrument_class", "")).upper() in ("C", "CALL") else "P",
                "display_factor": display_factor,
            }

        print(f"    Found {len(definitions)} option definitions")
        return definitions
    except Exception as e:
        print(f"    Definition fetch error: {e}")
        return {}


def fetch_ohlcv(client: db.Historical, parent: str, start: date, end: date, definitions: dict) -> pd.DataFrame:
    """Fetch OHLCV bars for options."""
    print(f"    Fetching OHLCV for {parent}...")
    try:
        data = client.timeseries.get_range(
            dataset=DATASET,
            schema="ohlcv-1d",
            symbols=[parent],
            stype_in="parent",
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
        )
        df = data.to_df()
        if df.empty:
            return pd.DataFrame()

        print(f"    Got {len(df)} OHLCV bars")
        return df
    except Exception as e:
        print(f"    OHLCV fetch error: {e}")
        return pd.DataFrame()


def fetch_statistics(client: db.Historical, parent: str, start: date, end: date) -> pd.DataFrame:
    """Fetch statistics including IV (stat_type=14) and delta (stat_type=15)."""
    print(f"    Fetching statistics for {parent}...")
    try:
        data = client.timeseries.get_range(
            dataset=DATASET,
            schema="statistics",
            symbols=[parent],
            stype_in="parent",
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
        )
        df = data.to_df()
        if df.empty:
            return pd.DataFrame()

        print(f"    Got {len(df)} statistics records")
        return df
    except Exception as e:
        print(f"    Statistics fetch error: {e}")
        return pd.DataFrame()


def process_options_data(
    underlying: str,
    definitions: dict,
    ohlcv_df: pd.DataFrame,
    stats_df: pd.DataFrame,
) -> list:
    """Process raw Databento data into records for database."""
    records = []

    if ohlcv_df.empty:
        return records

    # Build statistics lookup: (instrument_id, date, stat_type) -> value
    # Note: Databento DataFrames use ts_event as the INDEX, not a column
    stats_lookup = {}
    if not stats_df.empty:
        for idx, row in stats_df.iterrows():
            inst_id = str(row.get("instrument_id", ""))
            event_date = pd.to_datetime(idx).date()
            stat_type = int(row.get("stat_type", 0))

            # Get price value with proper scaling (DIVIDE by display_factor)
            price = row.get("price", 0)
            if price and price != 2147483647:  # INT32_MAX sentinel
                display_factor = definitions.get(inst_id, {}).get("display_factor", 0.001)
                if display_factor and display_factor != 0:
                    value = float(price) / float(display_factor)
                else:
                    value = float(price)
                stats_lookup[(inst_id, event_date, stat_type)] = value

    # Process OHLCV bars
    # Note: Databento DataFrames use ts_event as the INDEX, not a column
    for idx, row in ohlcv_df.iterrows():
        try:
            inst_id = str(row.get("instrument_id", ""))
            if inst_id not in definitions:
                continue

            defn = definitions[inst_id]
            strike = defn["strike"]
            expiration = defn["expiration"]
            option_type = defn["option_type"]
            display_factor = defn.get("display_factor", 0.001)

            if not expiration or strike <= 0:
                continue

            # Event date from index (Databento uses ts_event as DataFrame index)
            event_date = pd.to_datetime(idx).date()

            # OHLCV prices are already in human-readable format from Databento
            def get_price(val):
                if val is not None and val != 2147483647:
                    return float(val)
                return None

            open_price = get_price(row.get("open"))
            high_price = get_price(row.get("high"))
            low_price = get_price(row.get("low"))
            close_price = get_price(row.get("close"))
            volume = int(row.get("volume", 0)) if row.get("volume") else None

            # Get statistics for this contract/date
            iv = stats_lookup.get((inst_id, event_date, 14))  # stat_type 14 = IV
            delta_db = stats_lookup.get((inst_id, event_date, 15))  # stat_type 15 = delta
            open_interest = stats_lookup.get((inst_id, event_date, 9))  # stat_type 9 = OI
            vwap = stats_lookup.get((inst_id, event_date, 13))  # stat_type 13 = VWAP
            settlement = stats_lookup.get((inst_id, event_date, 3))  # stat_type 3 = settlement
            bid = stats_lookup.get((inst_id, event_date, 8))  # stat_type 8 = bid
            ask = stats_lookup.get((inst_id, event_date, 7))  # stat_type 7 = ask
            change = stats_lookup.get((inst_id, event_date, 12))  # stat_type 12 = change

            # Calculate remaining Greeks from IV using Black-76
            greeks = {"delta": None, "gamma": None, "theta": None, "vega": None, "rho": None}
            if iv and iv > 0 and close_price and close_price > 0:
                T = (expiration - event_date).days / 365.0
                if T > 0:
                    # Use close price as futures price approximation
                    greeks = black76_greeks(
                        F=close_price * 100 if underlying == "ZL" else close_price,  # ZL is in cents
                        K=strike * 100 if underlying == "ZL" else strike,
                        T=T,
                        r=RISK_FREE_RATE,
                        sigma=iv,
                        option_type=option_type,
                    )

            # Use Databento delta if available, otherwise calculated
            delta = delta_db if delta_db is not None else greeks.get("delta")

            record = {
                "underlying": underlying,
                "event_date": event_date,
                "expiration": expiration,
                "strike": strike,
                "option_type": option_type,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
                "open_interest": int(open_interest) if open_interest else None,
                "bid": bid,
                "ask": ask,
                "change": change,
                "premium": close_price,  # Premium = close price for options
                "vwap": vwap,
                "settlement": settlement,
                "implied_volatility": iv,
                "delta": delta,
                "gamma": greeks.get("gamma"),
                "theta": greeks.get("theta"),
                "vega": greeks.get("vega"),
                "rho": greeks.get("rho"),
                "row_hash": compute_row_hash(underlying, event_date, expiration, strike, option_type),
            }
            records.append(record)

        except Exception as e:
            continue

    return records


def upsert_options(conn, records: list) -> int:
    """Upsert options records to database."""
    if not records:
        return 0

    query = """
    INSERT INTO mkt.options_1d
        (underlying, event_date, expiration, strike, option_type,
         open, high, low, close, volume, open_interest,
         bid, ask, change, premium, vwap, settlement,
         implied_volatility, delta, gamma, theta, vega, rho,
         source, ingested_at, row_hash)
    VALUES
        (%(underlying)s, %(event_date)s, %(expiration)s, %(strike)s, %(option_type)s,
         %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(open_interest)s,
         %(bid)s, %(ask)s, %(change)s, %(premium)s, %(vwap)s, %(settlement)s,
         %(implied_volatility)s, %(delta)s, %(gamma)s, %(theta)s, %(vega)s, %(rho)s,
         'databento', NOW(), %(row_hash)s)
    ON CONFLICT (underlying, event_date, expiration, strike, option_type) DO UPDATE SET
        open = COALESCE(EXCLUDED.open, mkt.options_1d.open),
        high = COALESCE(EXCLUDED.high, mkt.options_1d.high),
        low = COALESCE(EXCLUDED.low, mkt.options_1d.low),
        close = COALESCE(EXCLUDED.close, mkt.options_1d.close),
        volume = COALESCE(EXCLUDED.volume, mkt.options_1d.volume),
        open_interest = COALESCE(EXCLUDED.open_interest, mkt.options_1d.open_interest),
        bid = COALESCE(EXCLUDED.bid, mkt.options_1d.bid),
        ask = COALESCE(EXCLUDED.ask, mkt.options_1d.ask),
        change = COALESCE(EXCLUDED.change, mkt.options_1d.change),
        premium = COALESCE(EXCLUDED.premium, mkt.options_1d.premium),
        vwap = COALESCE(EXCLUDED.vwap, mkt.options_1d.vwap),
        settlement = COALESCE(EXCLUDED.settlement, mkt.options_1d.settlement),
        implied_volatility = COALESCE(EXCLUDED.implied_volatility, mkt.options_1d.implied_volatility),
        delta = COALESCE(EXCLUDED.delta, mkt.options_1d.delta),
        gamma = COALESCE(EXCLUDED.gamma, mkt.options_1d.gamma),
        theta = COALESCE(EXCLUDED.theta, mkt.options_1d.theta),
        vega = COALESCE(EXCLUDED.vega, mkt.options_1d.vega),
        rho = COALESCE(EXCLUDED.rho, mkt.options_1d.rho),
        ingested_at = NOW()
    """

    with conn.cursor() as cur:
        execute_batch(cur, query, records, page_size=1000)
    conn.commit()
    return len(records)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Clean options backfill with full Greeks")
    parser.add_argument("--underlying", type=str, help="Single underlying to backfill (e.g., ZL)")
    parser.add_argument("--all", action="store_true", help="Backfill all underlyings")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD), default yesterday")
    parser.add_argument("--days", type=int, help="Days to backfill from today")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done")
    args = parser.parse_args()

    # Determine date range
    end_date = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)
    if args.days:
        start_date = end_date - timedelta(days=args.days)
    elif args.start:
        start_date = date.fromisoformat(args.start)
    else:
        start_date = end_date - timedelta(days=30)

    print(f"Date range: {start_date} to {end_date}")

    # Select configs
    if args.all:
        configs = OPTIONS_CONFIG
    elif args.underlying:
        configs = [c for c in OPTIONS_CONFIG if c["underlying"] == args.underlying.upper()]
        if not configs:
            print(f"ERROR: Unknown underlying {args.underlying}")
            sys.exit(1)
    else:
        print("ERROR: Specify --underlying or --all")
        sys.exit(1)

    print(f"Underlyings: {[c['underlying'] for c in configs]}")

    if args.dry_run:
        print("DRY RUN - would backfill above underlyings")
        return

    # Initialize clients
    client = get_databento_client()
    conn = get_db_connection()

    total_rows = 0

    for config in configs:
        print(f"\n{'='*60}")
        print(f"[{config['underlying']}] {config['name']}")
        print(f"{'='*60}")

        try:
            # Fetch data
            definitions = fetch_definitions(client, config["parent"], start_date, end_date)
            if not definitions:
                print(f"  No definitions found, skipping")
                continue

            ohlcv_df = fetch_ohlcv(client, config["parent"], start_date, end_date, definitions)
            stats_df = fetch_statistics(client, config["parent"], start_date, end_date)

            # Process
            records = process_options_data(
                config["underlying"],
                definitions,
                ohlcv_df,
                stats_df,
            )

            if records:
                # Check a sample strike for sanity
                sample = records[0]
                print(f"  Sample: strike={sample['strike']}, close={sample['close']}, iv={sample['implied_volatility']}")

                # Upsert
                count = upsert_options(conn, records)
                total_rows += count
                print(f"  Upserted {count} records")
            else:
                print(f"  No records to insert")

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            continue

    conn.close()
    print(f"\n{'='*60}")
    print(f"TOTAL: {total_rows} records upserted")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
