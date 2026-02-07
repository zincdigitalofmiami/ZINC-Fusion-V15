#!/usr/bin/env python3
"""
Backfill ZL correlations for mkt.fx_1d table.

Calculates 30d, 60d, 90d rolling correlations between each FX pair's
daily returns and ZL (soybean oil) daily returns.

Usage:
    .venv/bin/python scripts/backfill_fx_correlations.py
"""

import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)


def get_zl_returns(conn) -> pd.Series:
    """Fetch ZL daily close prices and compute returns."""
    query = """
    SELECT event_date, close
    FROM mkt.futures_1d
    WHERE symbol = 'ZL' AND close IS NOT NULL
    ORDER BY event_date
    """
    df = pd.read_sql(query, conn, parse_dates=["event_date"])
    df = df.set_index("event_date")
    df["return"] = df["close"].pct_change()
    return df["return"].dropna()


def get_fx_rates(conn) -> pd.DataFrame:
    """Fetch all FX pairs and pivot to wide format."""
    query = """
    SELECT pair, event_date, rate
    FROM mkt.fx_1d
    WHERE rate IS NOT NULL
    ORDER BY pair, event_date
    """
    df = pd.read_sql(query, conn, parse_dates=["event_date"])
    # Pivot to wide: rows=dates, cols=pairs
    pivot = df.pivot(index="event_date", columns="pair", values="rate")
    return pivot


def compute_fx_returns(fx_rates: pd.DataFrame) -> pd.DataFrame:
    """Compute daily returns for each FX pair."""
    return fx_rates.pct_change()


def compute_rolling_correlations(
    zl_returns: pd.Series, fx_returns: pd.DataFrame, windows: list[int]
) -> dict[int, pd.DataFrame]:
    """
    Compute rolling correlations between ZL returns and each FX pair.
    Returns dict: window -> DataFrame(dates x pairs) of correlations.
    """
    results = {}
    for window in windows:
        corr_df = pd.DataFrame(index=fx_returns.index)
        for pair in fx_returns.columns:
            fx_ret = fx_returns[pair]
            # Align on common dates
            aligned = pd.concat([zl_returns, fx_ret], axis=1, join="inner")
            aligned.columns = ["zl", "fx"]
            # Rolling correlation
            rolling_corr = (
                aligned["zl"].rolling(window, min_periods=window).corr(aligned["fx"])
            )
            # Reindex to original fx_returns index
            corr_df[pair] = rolling_corr.reindex(fx_returns.index)
        results[window] = corr_df
    return results


def update_correlations(conn, pair: str, updates: list[tuple]):
    """
    Batch update correlations for a single FX pair.
    updates: list of (event_date, corr_30, corr_60, corr_90)
    """
    if not updates:
        return 0

    cur = conn.cursor()
    # Use a temp table approach for efficiency
    cur.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS fx_corr_updates (
            event_date DATE,
            zl_corr_30d DOUBLE PRECISION,
            zl_corr_60d DOUBLE PRECISION,
            zl_corr_90d DOUBLE PRECISION
        ) ON COMMIT DELETE ROWS
    """
    )

    execute_values(
        cur,
        "INSERT INTO fx_corr_updates (event_date, zl_corr_30d, zl_corr_60d, zl_corr_90d) VALUES %s",
        updates,
        page_size=1000,
    )

    cur.execute(
        """
        UPDATE mkt.fx_1d f
        SET 
            zl_corr_30d = u.zl_corr_30d,
            zl_corr_60d = u.zl_corr_60d,
            zl_corr_90d = u.zl_corr_90d
        FROM fx_corr_updates u
        WHERE f.pair = %s AND f.event_date = u.event_date
    """,
        (pair,),
    )

    updated = cur.rowcount
    conn.commit()
    return updated


def main():
    print("=" * 60)
    print("FX Correlation Backfill")
    print("=" * 60)

    conn = psycopg2.connect(DATABASE_URL)

    # 1. Get ZL returns
    print("\n[1/4] Fetching ZL returns...")
    zl_returns = get_zl_returns(conn)
    print(
        f"      ZL returns: {len(zl_returns)} days ({zl_returns.index.min()} to {zl_returns.index.max()})"
    )

    # 2. Get FX rates
    print("\n[2/4] Fetching FX rates...")
    fx_rates = get_fx_rates(conn)
    print(f"      FX pairs: {len(fx_rates.columns)}")
    print(f"      Date range: {fx_rates.index.min()} to {fx_rates.index.max()}")

    # 3. Compute returns
    print("\n[3/4] Computing FX returns...")
    fx_returns = compute_fx_returns(fx_rates)

    # 4. Compute rolling correlations
    windows = [30, 60, 90]
    print(f"\n[4/4] Computing rolling correlations (windows: {windows})...")
    corr_results = compute_rolling_correlations(zl_returns, fx_returns, windows)

    # 5. Update database
    print("\n" + "=" * 60)
    print("Updating database...")
    print("=" * 60)

    total_updated = 0
    pairs = fx_rates.columns.tolist()

    for i, pair in enumerate(pairs, 1):
        # Build update list for this pair
        updates = []
        for dt in fx_returns.index:
            c30_raw = corr_results[30].loc[dt, pair]
            c60_raw = corr_results[60].loc[dt, pair]
            c90_raw = corr_results[90].loc[dt, pair]

            # Convert numpy floats to Python floats, handle NaN
            c30 = float(c30_raw) if pd.notna(c30_raw) else None
            c60 = float(c60_raw) if pd.notna(c60_raw) else None
            c90 = float(c90_raw) if pd.notna(c90_raw) else None

            # Only update if at least one correlation is valid
            if c30 is not None or c60 is not None or c90 is not None:
                updates.append((dt.date(), c30, c60, c90))

        updated = update_correlations(conn, pair, updates)
        total_updated += updated
        print(f"  [{i:2}/{len(pairs)}] {pair:12} -> {updated:6} rows updated")

    conn.close()

    print("\n" + "=" * 60)
    print(f"DONE: {total_updated:,} total rows updated")
    print("=" * 60)


if __name__ == "__main__":
    main()
