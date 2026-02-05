#!/usr/bin/env python3
"""Fix ALL ADX indicators (adx, adx_neg, adx_pos) for ALL symbols using Ray."""

import os
import sys

sys.path.insert(0, "src")

import psycopg2
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# Get DATABASE_URL before Ray init (workers need it passed explicitly)
DATABASE_URL = os.getenv("DATABASE_URL")
print(f"DATABASE_URL loaded: {DATABASE_URL[:50]}...")

# Ray setup
os.environ["RAY_DEDUP_LOGS"] = "0"
import ray

try:
    ray.init(address="auto", ignore_reinit_error=True)
    print(f"Connected to Ray cluster: {ray.cluster_resources()}")
except:
    ray.init(num_cpus=12, ignore_reinit_error=True)
    print(f"Started local Ray: {ray.cluster_resources()}")


def get_conn(db_url):
    return psycopg2.connect(db_url)


def calculate_adx(df, period=14):
    """Calculate ADX, +DI, -DI using standard formula."""
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    n = len(df)
    if n < period + 1:
        return None, None, None

    # True Range
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])
        )

    # +DM and -DM
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        plus_dm[i] = up_move if up_move > down_move and up_move > 0 else 0
        minus_dm[i] = down_move if down_move > up_move and down_move > 0 else 0

    # Smoothed TR, +DM, -DM (Wilder's smoothing)
    atr = np.zeros(n)
    smooth_plus_dm = np.zeros(n)
    smooth_minus_dm = np.zeros(n)

    # First smoothed value = sum of first 'period' values
    atr[period] = np.sum(tr[1 : period + 1])
    smooth_plus_dm[period] = np.sum(plus_dm[1 : period + 1])
    smooth_minus_dm[period] = np.sum(minus_dm[1 : period + 1])

    # Subsequent values use Wilder's smoothing
    for i in range(period + 1, n):
        atr[i] = atr[i - 1] - (atr[i - 1] / period) + tr[i]
        smooth_plus_dm[i] = (
            smooth_plus_dm[i - 1] - (smooth_plus_dm[i - 1] / period) + plus_dm[i]
        )
        smooth_minus_dm[i] = (
            smooth_minus_dm[i - 1] - (smooth_minus_dm[i - 1] / period) + minus_dm[i]
        )

    # +DI and -DI
    plus_di = np.zeros(n)
    minus_di = np.zeros(n)
    for i in range(period, n):
        if atr[i] != 0:
            plus_di[i] = 100 * smooth_plus_dm[i] / atr[i]
            minus_di[i] = 100 * smooth_minus_dm[i] / atr[i]

    # DX and ADX
    dx = np.zeros(n)
    for i in range(period, n):
        denom = plus_di[i] + minus_di[i]
        if denom != 0:
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / denom

    # ADX = smoothed DX
    adx = np.zeros(n)
    # First ADX = average of first 'period' DX values
    start_idx = 2 * period
    if start_idx < n:
        adx[start_idx] = np.mean(dx[period : start_idx + 1])
        for i in range(start_idx + 1, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return adx, plus_di, minus_di


@ray.remote(num_cpus=1)
def process_symbol(symbol, db_url):
    """Calculate and update ADX for a single symbol."""
    conn = get_conn(db_url)
    try:
        cur = conn.cursor()

        # Get all data for symbol using raw cursor (avoid pandas warning)
        cur.execute(
            f"""
            SELECT event_date, high, low, close 
            FROM mkt.futures_1d 
            WHERE symbol = %s 
            ORDER BY event_date
        """,
            (symbol,),
        )
        rows = cur.fetchall()

        if len(rows) < 30:
            return symbol, 0, "insufficient data"

        df = pd.DataFrame(rows, columns=["event_date", "high", "low", "close"])

        # Calculate ADX
        adx, plus_di, minus_di = calculate_adx(df)
        if adx is None:
            return symbol, 0, "calc failed"

        # Build update data (using event_date + symbol as composite key)
        # Convert numpy types to Python native types for PostgreSQL
        updates = []
        for i in range(len(df)):
            if adx[i] > 0 or plus_di[i] > 0 or minus_di[i] > 0:
                updates.append(
                    (
                        float(round(adx[i], 4)) if adx[i] > 0 else None,
                        float(round(plus_di[i], 4)) if plus_di[i] > 0 else None,
                        float(round(minus_di[i], 4)) if minus_di[i] > 0 else None,
                        df.iloc[i]["event_date"],
                        symbol,
                    )
                )

        if not updates:
            return symbol, 0, "no valid values"

        # Batch update using composite key
        cur.executemany(
            """
            UPDATE mkt.futures_1d 
            SET adx = %s, adx_pos = %s, adx_neg = %s
            WHERE event_date = %s AND symbol = %s
        """,
            updates,
        )
        conn.commit()
        cur.close()

        return symbol, len(updates), "success"
    except Exception as e:
        return symbol, 0, str(e)[:100]
    finally:
        conn.close()


def main():
    conn = get_conn(DATABASE_URL)
    cur = conn.cursor()

    # Get all symbols
    cur.execute("SELECT DISTINCT symbol FROM mkt.futures_1d ORDER BY symbol")
    symbols = [r[0] for r in cur.fetchall()]
    conn.close()

    print(f"\nProcessing {len(symbols)} symbols with Ray...")

    # Submit all tasks - pass DATABASE_URL to each worker
    futures = [process_symbol.remote(s, DATABASE_URL) for s in symbols]

    # Collect results
    results = ray.get(futures)

    total_updated = 0
    failed = []
    for symbol, count, status in results:
        if status == "success":
            total_updated += count
            print(f"  ✓ {symbol}: {count:,} rows updated")
        else:
            failed.append((symbol, status))
            print(f"  ✗ {symbol}: {status}")

    print(f"\n=== COMPLETE ===")
    print(f"Total rows updated: {total_updated:,}")
    print(f"Failed symbols: {len(failed)}")

    # Verify
    conn = get_conn(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM mkt.futures_1d")
    total = cur.fetchone()[0]
    for col in ["adx", "adx_neg", "adx_pos"]:
        cur.execute(f"SELECT COUNT(*) FROM mkt.futures_1d WHERE {col} IS NULL")
        nulls = cur.fetchone()[0]
        pct = (1 - nulls / total) * 100
        print(f"  {col}: {pct:.1f}% populated")
    conn.close()


if __name__ == "__main__":
    main()
