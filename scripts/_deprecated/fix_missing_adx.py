import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
import numpy as np
import psycopg2
from fusion.db.ray_pool import get_connection, release_connection

DATABASE_URL = os.environ.get("DATABASE_URL")


def fix_adx_for_symbol(symbol):
    """Calculate ADX indicators for a specific symbol."""
    conn = get_connection(DATABASE_URL)
    cur = conn.cursor()

    # Get data for this symbol
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
        print(f"Skipping {symbol}: insufficient data ({len(df)} records)")
        cur.close()
        release_connection(conn)
        return 0

    df["event_date"] = pd.to_datetime(df["event_date"])
    df = df.set_index("event_date")

    # Convert to float64
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(np.float64)
    df["volume"] = df["volume"].fillna(0)

    # Calculate ADX using TA-Lib
    from fusion.features.elite_indicators_v2_INSTITUTIONAL import EliteIndicatorsV2

    calc = EliteIndicatorsV2(df)
    df_with_indicators = calc.calculate_all()

    # Update only ADX-related columns
    updated = 0
    for date, row in df_with_indicators.iterrows():
        # Check if ADX data exists and needs updating
        adx_val = float(row["adx"]) if pd.notna(row.get("adx")) else None
        adx_neg_val = float(row["adx_neg"]) if pd.notna(row.get("adx_neg")) else None
        adx_pos_val = float(row["adx_pos"]) if pd.notna(row.get("adx_pos")) else None

        if any([adx_val is not None, adx_neg_val is not None, adx_pos_val is not None]):
            cur.execute(
                """
                UPDATE mkt.futures_1d
                SET 
                    adx = %s,
                    adx_neg = %s,
                    adx_pos = %s
                WHERE symbol = %s AND event_date = %s
            """,
                (adx_val, adx_neg_val, adx_pos_val, symbol, date.date()),
            )
            updated += cur.rowcount

    conn.commit()
    cur.close()
    release_connection(conn)

    print(f"{symbol}: updated {updated} ADX records")
    return updated


# Symbols that need ADX calculation
symbols_needing_adx = [
    "USDCNY",
    "USDCAD",
    "USDJPY",
    "CT",
    "DJT",
    "EURUSD",
    "FXI",
    "GBPUSD",
    "KWEB",
    "NDX",
    "OJ",
    "AUDUSD",
    "VIX",
    "SPX",
    "USDBRL",
    "VX",
    "BZ",
    "ZM",
    "PL",
    "PA",
    "SI",
    "ZL",
]

print(f"Fixing ADX for {len(symbols_needing_adx)} symbols with missing data...")

total_updated = 0
for symbol in symbols_needing_adx:
    try:
        updated = fix_adx_for_symbol(symbol)
        total_updated += updated
    except Exception as e:
        print(f"ERROR processing {symbol}: {e}")

print(
    f"\\n✅ COMPLETED: Updated {total_updated} ADX records across {len(symbols_needing_adx)} symbols"
)
