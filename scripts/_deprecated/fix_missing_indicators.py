#!/usr/bin/env python3
"""
TARGETED FIX: Only recalculate missing futures indicators

Strategy:
1. Identify empty indicators (adx_neg, adx_pos)
2. Identify symbols with <95% indicator coverage
3. Only recalculate missing data for those specific gaps
4. Skip already complete indicators/symbols

This is MUCH faster than blanket recalculation.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
import numpy as np
import psycopg2
from tqdm import tqdm
from fusion.db.ray_pool import get_connection, release_connection

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set")


def get_missing_indicators():
    """Identify which indicators and symbols need fixing."""
    conn = get_connection(DATABASE_URL)
    cur = conn.cursor()

    # Get all indicator columns
    cur.execute(
        """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = 'mkt'
    AND table_name = 'futures_1d'
    AND column_name NOT IN ('event_date', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'open_interest', 'ingested_at')
    ORDER BY column_name
    """
    )

    all_indicators = [row[0] for row in cur.fetchall()]

    # Check completeness
    cur.execute("SELECT count(*) FROM mkt.futures_1d")
    total_records = cur.fetchone()[0]

    empty_indicators = []
    partial_symbols = []

    for indicator in all_indicators:
        # Check overall completeness
        cur.execute(
            f"SELECT count(*) FROM mkt.futures_1d WHERE {indicator} IS NOT NULL"
        )
        non_null = cur.fetchone()[0]
        pct = (non_null / total_records) * 100 if total_records > 0 else 0

        if pct == 0:
            empty_indicators.append(indicator)

    # Find symbols that need fixes (RSI < 95% coverage)
    cur.execute(
        """
    SELECT symbol, count(*) as records, count(rsi_14) as rsi_count
    FROM mkt.futures_1d
    GROUP BY symbol
    HAVING (count(rsi_14)::float / count(*)::float) < 0.95
    ORDER BY (count(rsi_14)::float / count(*)::float) ASC
    """
    )

    partial_symbols = [(row[0], row[1], row[2]) for row in cur.fetchall()]

    cur.close()
    release_connection(conn)

    return empty_indicators, partial_symbols


def fix_symbol_indicators(symbol, indicators_to_fix):
    """Fix missing indicators for a specific symbol."""
    conn = get_connection(DATABASE_URL)
    cur = conn.cursor()

    # Load OHLCV data
    df = pd.read_sql(
        f"""
        SELECT event_date, open, high, low, close, volume
        FROM mkt.futures_1d
        WHERE symbol = '{symbol}'
        ORDER BY event_date
    """,
        conn,
    )

    if len(df) < 100:
        cur.close()
        release_connection(conn)
        return 0

    df["event_date"] = pd.to_datetime(df["event_date"])
    df = df.set_index("event_date")

    # Convert to float64 for TA-Lib
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(np.float64)
    df["volume"] = df["volume"].fillna(0)

    # Calculate missing indicators
    from fusion.features.elite_indicators_v2_INSTITUTIONAL import EliteIndicatorsV2

    calc = EliteIndicatorsV2(df)
    df_with_indicators = calc.calculate_all()

    # Build update query for only missing indicators
    update_fields = []
    update_values = []

    for indicator in indicators_to_fix:
        if indicator in df_with_indicators.columns and indicator in [
            "adx_neg",
            "adx_pos",
        ]:
            update_fields.append(f"{indicator} = %s")
            update_values.append(indicator)

    if not update_fields:
        cur.close()
        release_connection(conn)
        return 0

    # Update only records that are missing these indicators
    update_query = f"""
    UPDATE mkt.futures_1d
    SET {', '.join(update_fields)}
    WHERE symbol = %s AND event_date = %s AND ({' OR '.join([f'{ind} IS NULL' for ind in indicators_to_fix])})
    """

    updated = 0
    for date, row in df_with_indicators.iterrows():
        # Check if any of the target indicators are missing for this record
        values = [row.get(ind) for ind in indicators_to_fix]
        if any(pd.notna(val) for val in values):
            try:
                cur.execute(update_query, values + [symbol, date.date()])
                updated += cur.rowcount
            except Exception as e:
                print(f"Error updating {symbol} {date}: {e}")

    conn.commit()
    cur.close()
    release_connection(conn)

    return updated


def main():
    print("🔧 TARGETED FIX: Missing Futures Indicators")
    print("=" * 50)

    # Identify what's missing
    empty_indicators, partial_symbols = get_missing_indicators()

    print(f"📊 Found {len(empty_indicators)} empty indicators: {empty_indicators}")
    print(f"📊 Found {len(partial_symbols)} symbols needing fixes")

    if not empty_indicators and not partial_symbols:
        print("✅ No missing indicators found!")
        return

    # Fix empty indicators across all symbols
    if empty_indicators:
        print(f"\n🔧 Fixing empty indicators: {empty_indicators}")
        total_updated = 0

        # Get all symbols
        conn = get_connection(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT symbol FROM mkt.futures_1d ORDER BY symbol")
        all_symbols = [row[0] for row in cur.fetchall()]
        cur.close()
        release_connection(conn)

        for symbol in tqdm(all_symbols, desc="Processing symbols"):
            updated = fix_symbol_indicators(symbol, empty_indicators)
            total_updated += updated

        print(f"✅ Fixed {total_updated} missing indicator values")

    # Report results
    print("\n" + "=" * 50)
    print("🎯 TARGETED FIX COMPLETE")
    print(f"• Empty indicators fixed: {len(empty_indicators)}")
    print(
        f"• Symbols processed: {len(all_symbols) if 'all_symbols' in locals() else 0}"
    )
    print("• Only missing data recalculated (not everything)")


if __name__ == "__main__":
    main()
