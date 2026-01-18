# DEPRECATED: This script builds legacy medallion tables (silver/gold).
# The v2 architecture uses features.* tables directly.
# See: mkt.options_1d, features.options_1d, features.weather_1d
# TODO: Remove after 2026-03-01 if no issues.

#!/usr/bin/env python3
"""
Build Options Silver and Gold Tables
=====================================

Transforms raw.options_greeks_1d → silver.options_agg_1d → gold.options_features_1d

Flow:
1. Silver: Aggregate options by underlying/date (ATM IV, skew, term structure)
2. Gold: Create derived features (z-scores, regime indicators)

Also processes raw.etf_prices_1d → silver.etf_prices_1d for correlation features.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Get database connection."""
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def ensure_silver_tables(conn):
    """Create silver tables if they don't exist."""
    cur = conn.cursor()

    # Silver options aggregated by underlying/date
    cur.execute("""
        CREATE TABLE IF NOT EXISTS silver.options_agg_1d (
            id SERIAL PRIMARY KEY,
            event_date DATE NOT NULL,
            underlying VARCHAR(20) NOT NULL,
            iv_atm DOUBLE PRECISION,
            iv_25d_call DOUBLE PRECISION,
            iv_25d_put DOUBLE PRECISION,
            iv_skew DOUBLE PRECISION,
            term_structure_slope DOUBLE PRECISION,
            avg_delta_call DOUBLE PRECISION,
            avg_delta_put DOUBLE PRECISION,
            total_volume BIGINT,
            total_oi BIGINT,
            put_call_ratio_vol DOUBLE PRECISION,
            strike_count INT,
            expiration_count INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(event_date, underlying)
        )
    """)

    # Silver ETF prices (cleaned, with returns)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS silver.etf_prices_1d (
            id SERIAL PRIMARY KEY,
            event_date DATE NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            open DOUBLE PRECISION,
            high DOUBLE PRECISION,
            low DOUBLE PRECISION,
            close DOUBLE PRECISION,
            volume BIGINT,
            return_1d DOUBLE PRECISION,
            return_5d DOUBLE PRECISION,
            return_21d DOUBLE PRECISION,
            volatility_21d DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(event_date, symbol)
        )
    """)

    # Indexes
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_silver_options_agg_date
        ON silver.options_agg_1d(event_date)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_silver_etf_prices_date
        ON silver.etf_prices_1d(event_date, symbol)
    """)

    conn.commit()
    cur.close()
    print("Ensured silver tables exist")


def build_silver_options(conn) -> int:
    """
    Build silver.options_agg_1d from raw.options_greeks_1d.

    Aggregates options by underlying/date to create summary metrics.
    """
    print("\n" + "=" * 60)
    print("BUILDING silver.options_agg_1d")
    print("=" * 60)

    cur = conn.cursor()

    # Get raw options data
    cur.execute("""
        SELECT
            event_date,
            underlying,
            strike,
            option_type,
            last_price,
            implied_volatility,
            delta,
            expiration
        FROM raw.options_greeks_1d
        WHERE implied_volatility IS NOT NULL
        ORDER BY event_date, underlying, strike
    """)

    rows = cur.fetchall()
    if not rows:
        print("   No raw options data found")
        return 0

    df = pd.DataFrame(rows, columns=[
        'event_date', 'underlying', 'strike', 'option_type',
        'last_price', 'iv', 'delta', 'expiration'
    ])

    print(f"   Loaded {len(df):,} raw options records")

    # Group by date and underlying
    results = []
    for (event_date, underlying), group in df.groupby(['event_date', 'underlying']):
        calls = group[group['option_type'] == 'CALL']
        puts = group[group['option_type'] == 'PUT']

        # ATM IV (closest to 50 delta)
        atm_call = calls.iloc[(calls['delta'].abs() - 0.5).abs().argsort()[:1]] if len(calls) > 0 else None
        atm_put = puts.iloc[(puts['delta'].abs() - 0.5).abs().argsort()[:1]] if len(puts) > 0 else None

        iv_atm = None
        if atm_call is not None and len(atm_call) > 0 and atm_put is not None and len(atm_put) > 0:
            iv_atm = (atm_call['iv'].values[0] + atm_put['iv'].values[0]) / 2
        elif atm_call is not None and len(atm_call) > 0:
            iv_atm = atm_call['iv'].values[0]

        # 25 delta wings for skew
        call_25d = calls[(calls['delta'] > 0.2) & (calls['delta'] < 0.3)]
        put_25d = puts[(puts['delta'] < -0.2) & (puts['delta'] > -0.3)]

        iv_25d_call = call_25d['iv'].mean() if len(call_25d) > 0 else None
        iv_25d_put = put_25d['iv'].mean() if len(put_25d) > 0 else None

        # Skew = put IV - call IV at 25 delta
        iv_skew = None
        if iv_25d_call and iv_25d_put:
            iv_skew = iv_25d_put - iv_25d_call

        # Term structure slope (if multiple expirations)
        expirations = group['expiration'].dropna().unique()
        term_slope = None
        if len(expirations) > 1:
            exp_ivs = []
            for exp in sorted(expirations):
                exp_data = group[group['expiration'] == exp]
                if len(exp_data) > 0:
                    exp_ivs.append((exp, exp_data['iv'].mean()))
            if len(exp_ivs) > 1:
                # Simple slope: (far IV - near IV) / days
                days_diff = (exp_ivs[-1][0] - exp_ivs[0][0]).days
                if days_diff > 0:
                    term_slope = (exp_ivs[-1][1] - exp_ivs[0][1]) / days_diff * 30  # Normalize to monthly

        results.append({
            'event_date': event_date,
            'underlying': underlying,
            'iv_atm': iv_atm,
            'iv_25d_call': iv_25d_call,
            'iv_25d_put': iv_25d_put,
            'iv_skew': iv_skew,
            'term_structure_slope': term_slope,
            'avg_delta_call': calls['delta'].mean() if len(calls) > 0 else None,
            'avg_delta_put': puts['delta'].mean() if len(puts) > 0 else None,
            'total_volume': None,  # Not in our Greeks data
            'total_oi': None,
            'put_call_ratio_vol': None,
            'strike_count': len(group),
            'expiration_count': len(expirations),
        })

    # Helper to convert numpy types to Python natives
    def to_python(val):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        if hasattr(val, 'item'):
            return val.item()
        return val

    # Insert into silver
    if results:
        values = [
            (
                r['event_date'], r['underlying'], to_python(r['iv_atm']), to_python(r['iv_25d_call']),
                to_python(r['iv_25d_put']), to_python(r['iv_skew']), to_python(r['term_structure_slope']),
                to_python(r['avg_delta_call']), to_python(r['avg_delta_put']), to_python(r['total_volume']),
                to_python(r['total_oi']), to_python(r['put_call_ratio_vol']), r['strike_count'],
                r['expiration_count']
            )
            for r in results
        ]

        execute_values(
            cur,
            """
            INSERT INTO silver.options_agg_1d (
                event_date, underlying, iv_atm, iv_25d_call, iv_25d_put,
                iv_skew, term_structure_slope, avg_delta_call, avg_delta_put,
                total_volume, total_oi, put_call_ratio_vol, strike_count,
                expiration_count
            ) VALUES %s
            ON CONFLICT (event_date, underlying) DO UPDATE SET
                iv_atm = EXCLUDED.iv_atm,
                iv_25d_call = EXCLUDED.iv_25d_call,
                iv_25d_put = EXCLUDED.iv_25d_put,
                iv_skew = EXCLUDED.iv_skew,
                term_structure_slope = EXCLUDED.term_structure_slope,
                avg_delta_call = EXCLUDED.avg_delta_call,
                avg_delta_put = EXCLUDED.avg_delta_put,
                strike_count = EXCLUDED.strike_count,
                expiration_count = EXCLUDED.expiration_count
            """,
            values,
            page_size=500
        )
        conn.commit()

    print(f"   Wrote {len(results)} silver options records")
    return len(results)


def build_silver_etf(conn) -> int:
    """
    Build silver.etf_prices_1d from raw.etf_prices_1d.

    Adds returns and rolling volatility.
    """
    print("\n" + "=" * 60)
    print("BUILDING silver.etf_prices_1d")
    print("=" * 60)

    cur = conn.cursor()

    # Get raw ETF data
    cur.execute("""
        SELECT symbol, event_date, open, high, low, close, volume
        FROM raw.etf_prices_1d
        ORDER BY symbol, event_date
    """)

    rows = cur.fetchall()
    if not rows:
        print("   No raw ETF data found")
        return 0

    df = pd.DataFrame(rows, columns=['symbol', 'event_date', 'open', 'high', 'low', 'close', 'volume'])
    print(f"   Loaded {len(df):,} raw ETF records for {df['symbol'].nunique()} symbols")

    # Calculate returns per symbol
    results = []
    for symbol, group in df.groupby('symbol'):
        group = group.sort_values('event_date').copy()

        # Returns
        group['return_1d'] = group['close'].pct_change()
        group['return_5d'] = group['close'].pct_change(5)
        group['return_21d'] = group['close'].pct_change(21)

        # Rolling volatility (21-day)
        group['volatility_21d'] = group['return_1d'].rolling(21).std() * np.sqrt(252)

        for _, row in group.iterrows():
            results.append({
                'event_date': row['event_date'],
                'symbol': symbol,
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume'],
                'return_1d': row['return_1d'] if pd.notna(row['return_1d']) else None,
                'return_5d': row['return_5d'] if pd.notna(row['return_5d']) else None,
                'return_21d': row['return_21d'] if pd.notna(row['return_21d']) else None,
                'volatility_21d': row['volatility_21d'] if pd.notna(row['volatility_21d']) else None,
            })

    # Batch insert
    if results:
        values = [
            (
                r['event_date'], r['symbol'], r['open'], r['high'], r['low'],
                r['close'], r['volume'], r['return_1d'], r['return_5d'],
                r['return_21d'], r['volatility_21d']
            )
            for r in results
        ]

        execute_values(
            cur,
            """
            INSERT INTO silver.etf_prices_1d (
                event_date, symbol, open, high, low, close, volume,
                return_1d, return_5d, return_21d, volatility_21d
            ) VALUES %s
            ON CONFLICT (event_date, symbol) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                return_1d = EXCLUDED.return_1d,
                return_5d = EXCLUDED.return_5d,
                return_21d = EXCLUDED.return_21d,
                volatility_21d = EXCLUDED.volatility_21d
            """,
            values,
            page_size=1000
        )
        conn.commit()

    print(f"   Wrote {len(results)} silver ETF records")
    return len(results)


def build_gold_options(conn) -> int:
    """
    Build gold.options_features_1d from silver.options_agg_1d.

    Adds z-scores and combines with VIX term structure.
    """
    print("\n" + "=" * 60)
    print("BUILDING gold.options_features_1d")
    print("=" * 60)

    cur = conn.cursor()

    # Get silver options data with VIX term structure
    cur.execute("""
        SELECT
            event_date,
            underlying,
            iv_atm,
            iv_25d_call,
            iv_25d_put,
            iv_skew,
            term_structure_slope,
            expiration_count
        FROM silver.options_agg_1d
        ORDER BY underlying, event_date
    """)

    rows = cur.fetchall()
    if not rows:
        print("   No silver options data found")
        return 0

    df = pd.DataFrame(rows, columns=[
        'event_date', 'underlying', 'iv_atm', 'iv_25d_call', 'iv_25d_put',
        'iv_skew', 'term_slope', 'expiration_count'
    ])

    print(f"   Loaded {len(df)} silver options records")

    # Calculate z-scores per underlying (rolling 63-day)
    results = []
    for underlying, group in df.groupby('underlying'):
        group = group.sort_values('event_date').copy()

        # Rolling z-scores
        for col in ['iv_atm', 'iv_25d_call', 'iv_25d_put', 'iv_skew']:
            if col in group.columns:
                mean = group[col].rolling(63, min_periods=5).mean()
                std = group[col].rolling(63, min_periods=5).std()
                group[f'{col}_z'] = (group[col] - mean) / std.replace(0, np.nan)

        for _, row in group.iterrows():
            results.append({
                'trade_date': row['event_date'],
                'symbol': underlying,
                'iv_atm': row['iv_atm'],
                'iv_call': row['iv_25d_call'],
                'iv_put': row['iv_25d_put'],
                'skew': row['iv_skew'],
                'iv_atm_z': row.get('iv_atm_z'),
                'iv_call_z': row.get('iv_25d_call_z'),
                'iv_put_z': row.get('iv_25d_put_z'),
                'skew_z': row.get('iv_skew_z'),
            })

    # Insert into gold
    if results:
        values = [
            (
                r['trade_date'], r['symbol'], r['iv_atm'], r['iv_call'], r['iv_put'],
                r['skew'], r['iv_atm_z'], r['iv_call_z'], r['iv_put_z'], r['skew_z'],
                datetime.now()
            )
            for r in results
        ]

        execute_values(
            cur,
            """
            INSERT INTO gold.options_features_1d (
                trade_date, symbol, iv_atm, iv_call, iv_put, skew,
                iv_atm_z, iv_call_z, iv_put_z, skew_z, computed_at
            ) VALUES %s
            ON CONFLICT (trade_date, symbol) DO UPDATE SET
                iv_atm = EXCLUDED.iv_atm,
                iv_call = EXCLUDED.iv_call,
                iv_put = EXCLUDED.iv_put,
                skew = EXCLUDED.skew,
                iv_atm_z = EXCLUDED.iv_atm_z,
                iv_call_z = EXCLUDED.iv_call_z,
                iv_put_z = EXCLUDED.iv_put_z,
                skew_z = EXCLUDED.skew_z,
                computed_at = EXCLUDED.computed_at
            """,
            values,
            page_size=500
        )
        conn.commit()

    print(f"   Wrote {len(results)} gold options features")
    return len(results)


def main():
    print("=" * 60)
    print("OPTIONS & ETF SILVER/GOLD BUILD")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")

    conn = get_connection()

    try:
        ensure_silver_tables(conn)

        # Build silver layers
        silver_options = build_silver_options(conn)
        silver_etf = build_silver_etf(conn)

        # Build gold layer
        gold_options = build_gold_options(conn)

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"   silver.options_agg_1d: {silver_options} records")
        print(f"   silver.etf_prices_1d:  {silver_etf} records")
        print(f"   gold.options_features_1d: {gold_options} records")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
