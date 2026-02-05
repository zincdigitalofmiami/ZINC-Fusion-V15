#!/usr/bin/env python3
"""
OPTIMIZED Yang-Zhang and Garman-Klass Volatility (BATCH UPDATES)

Same EXACT academic formulas, but with batch database operations for speed.

Author: ZINC-FUSION-V15
Date: 2026-01-31
"""

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
import os
from tqdm import tqdm


def load_env():
    """Load environment variables from .env file."""
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line and "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip().strip('"').strip("'")


def get_db_connection():
    """Get database connection."""
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL.split("?")[0])


def calculate_volatilities(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """
    Calculate both Yang-Zhang and Garman-Klass volatility.

    EXACT ACADEMIC FORMULAS - NO APPROXIMATIONS.
    """
    o = df["open"].astype(np.float64)
    h = df["high"].astype(np.float64)
    l = df["low"].astype(np.float64)
    c = df["close"].astype(np.float64)
    c_prev = c.shift(1)

    with np.errstate(divide="ignore", invalid="ignore"):
        # ============================================================
        # GARMAN-KLASS VOLATILITY (1980)
        # GK_daily = 0.5 * ln(H/L)² - (2*ln(2) - 1) * ln(C/O)²
        # ============================================================
        log_hl = np.log(h / l)
        log_co = np.log(c / o)
        gk_coefficient = 2 * np.log(2) - 1  # ≈ 0.386
        gk_daily = 0.5 * (log_hl**2) - gk_coefficient * (log_co**2)
        gk_mean = gk_daily.rolling(window).mean()
        df["garman_klass_vol"] = np.sqrt(gk_mean.clip(lower=0)) * np.sqrt(252)

        # ============================================================
        # YANG-ZHANG VOLATILITY (2000)
        # σ² = σ_o² + k*σ_c² + (1-k)*σ_rs²
        # ============================================================
        log_oc = np.log(o / c_prev)  # Overnight
        log_co_intraday = np.log(c / o)  # Intraday

        # Rogers-Satchell
        log_hc = np.log(h / c)
        log_ho = np.log(h / o)
        log_lc = np.log(l / c)
        log_lo = np.log(l / o)
        rs_daily = log_hc * log_ho + log_lc * log_lo

        # k factor
        k = 0.34 / (1.34 + (window + 1) / (window - 1))

        # Variances
        sigma_o_sq = log_oc.rolling(window).var()
        sigma_c_sq = log_co_intraday.rolling(window).var()
        sigma_rs_sq = rs_daily.rolling(window).mean()

        # Yang-Zhang
        yang_zhang_var = sigma_o_sq + k * sigma_c_sq + (1 - k) * sigma_rs_sq
        df["yang_zhang_vol"] = np.sqrt(yang_zhang_var) * np.sqrt(252)

    return df


def main():
    print("\n" + "=" * 70)
    print("YANG-ZHANG & GARMAN-KLASS VOLATILITY - BATCH OPTIMIZED")
    print("=" * 70)
    print("\nUsing EXACT academic formulas with batch database updates\n")

    load_env()
    conn = get_db_connection()

    # Load ALL futures data at once
    print("Loading all futures data...")
    df_all = pd.read_sql(
        """
        SELECT symbol, event_date, open, high, low, close
        FROM mkt.futures_1d
        ORDER BY symbol, event_date
    """,
        conn,
    )

    print(f"Loaded {len(df_all):,} rows")

    # Process by symbol
    symbols = df_all["symbol"].unique()
    print(f"Processing {len(symbols)} symbols...\n")

    all_updates = []

    for symbol in tqdm(symbols, desc="Calculating"):
        df_sym = df_all[df_all["symbol"] == symbol].copy()
        df_sym["event_date"] = pd.to_datetime(df_sym["event_date"])
        df_sym = df_sym.set_index("event_date").sort_index()

        if len(df_sym) < 30:
            continue

        # Calculate volatilities
        df_result = calculate_volatilities(df_sym)

        # Collect valid updates
        for event_date, row in df_result.iterrows():
            if pd.notna(row["yang_zhang_vol"]) and pd.notna(row["garman_klass_vol"]):
                all_updates.append(
                    (
                        float(row["yang_zhang_vol"]),
                        float(row["garman_klass_vol"]),
                        symbol,
                        event_date.date(),
                    )
                )

    print(f"\nPrepared {len(all_updates):,} updates")
    print("Executing batch update...")

    # Batch update
    cursor = conn.cursor()

    batch_size = 5000
    for i in tqdm(range(0, len(all_updates), batch_size), desc="Updating"):
        batch = all_updates[i : i + batch_size]

        # Use executemany for speed
        cursor.executemany(
            """
            UPDATE mkt.futures_1d
            SET yang_zhang_vol = %s,
                garman_klass_vol = %s
            WHERE id = %s
        """,
            batch,
        )
        conn.commit()

    cursor.close()
    conn.close()

    print(f"\n{'='*70}")
    print(f"✅ COMPLETE: {len(all_updates):,} rows updated")
    print("✅ YANG-ZHANG: Exact formula (overnight + intraday + Rogers-Satchell)")
    print("✅ GARMAN-KLASS: Exact formula with (2·ln2-1) coefficient")
    print("✅ Both annualized (×√252)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
