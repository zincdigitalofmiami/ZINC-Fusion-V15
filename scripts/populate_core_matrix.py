#!/usr/bin/env python3
"""
Populate training.matrix_1d with targets and features.

This script computes:
- target_5d, target_21d, target_63d, target_126d (ZL close price at t+H trading days)
- Core features (returns, volatility, crush spread, calendar features)

SoT v2 Contract:
- Targets are ZL CLOSE PRICES at future trading days (not returns)
- Horizons H ∈ {5, 21, 63, 126} are TRADING DAYS, not calendar days
- Point-in-time correct: no future data leakage

Usage:
    python scripts/populate_core_matrix.py --start 2000-01-01 --dry-run
    python scripts/populate_core_matrix.py --start 2000-01-01 --execute
"""

import os
import sys
import argparse
from datetime import datetime

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Configuration
# =============================================================================

HORIZONS = [5, 21, 63, 126]
SYMBOL = "ZL"

# Calendar features
WASDE_DAYS = list(range(7, 15))  # 7th-14th of month
FOMC_MONTHS = [1, 3, 5, 6, 7, 9, 11, 12]  # FOMC meeting months
EXPIRY_WEEK = 3  # 3rd week of month


def get_connection():
    """Get database connection from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL not found in environment")
    return psycopg2.connect(database_url)


def load_zl_prices(conn, start_date: str) -> pd.DataFrame:
    """Load ZL daily prices from mkt.futures_1d."""
    query = """
        SELECT
            event_date::date as as_of_date,
            close as zl_close,
            open as zl_open,
            high as zl_high,
            low as zl_low,
            volume as zl_volume
        FROM mkt.futures_1d
        WHERE symbol = %s
          AND event_date >= %s
        ORDER BY event_date
    """
    df = pd.read_sql(query, conn, params=[SYMBOL, start_date])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    return df


def load_related_prices(conn, start_date: str) -> pd.DataFrame:
    """Load ZS and ZM prices for crush spread calculation."""
    query = """
        SELECT
            event_date::date as as_of_date,
            symbol,
            close
        FROM mkt.futures_1d
        WHERE symbol IN ('ZS', 'ZM')
          AND event_date >= %s
        ORDER BY event_date
    """
    df = pd.read_sql(query, conn, params=[start_date])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])

    # Pivot to wide format
    pivot = df.pivot(index="as_of_date", columns="symbol", values="close")
    pivot.columns = [f"{col.lower()}_close" for col in pivot.columns]
    return pivot.reset_index()


def compute_targets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute forward targets using TRADING DAY leads.

    target_Hd = ZL close price at t+H trading days

    This is NOT a calendar day lead - it's the actual close price
    H trading sessions into the future.
    """
    df = df.copy()

    for h in HORIZONS:
        # Shift backwards to get future price (negative shift = future value)
        df[f"target_{h}d"] = df["zl_close"].shift(-h)

    return df


def compute_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Compute lagged returns."""
    df = df.copy()

    # Simple returns
    df["zl_return_1d"] = df["zl_close"].pct_change(1)
    df["zl_return_5d"] = df["zl_close"].pct_change(5)
    df["zl_return_21d"] = df["zl_close"].pct_change(21)

    return df


def compute_volatility(df: pd.DataFrame) -> pd.DataFrame:
    """Compute rolling volatility (annualized)."""
    df = df.copy()

    # Daily returns for vol calculation
    daily_ret = df["zl_close"].pct_change()

    # Rolling std * sqrt(252) for annualized vol
    df["zl_vol_21d"] = daily_ret.rolling(21).std() * np.sqrt(252)
    df["zl_vol_63d"] = daily_ret.rolling(63).std() * np.sqrt(252)

    return df


def compute_crush_spread(df: pd.DataFrame, related: pd.DataFrame) -> pd.DataFrame:
    """
    Compute board crush spread and oil share.

    Board Crush = (ZM * 0.022) + (ZL * 11) - ZS
    Oil Share = ZL price / (ZL + ZM) prices
    """
    df = df.copy()

    # Merge related prices
    df = df.merge(related, on="as_of_date", how="left")

    # Board crush (standard conversion factors)
    # ZM: meal in $/ton, convert to $/bu: * 0.022
    # ZL: oil in cents/lb, convert to $/bu: * 11
    # ZS: soybeans in cents/bu
    if "zm_close" in df.columns and "zs_close" in df.columns:
        df["board_crush"] = (
            (df["zm_close"] * 0.022) + (df["zl_close"] * 11) - df["zs_close"]
        )

        # Oil share of crush value
        total_products = (df["zl_close"] * 11) + (df["zm_close"] * 0.022)
        df["oil_share"] = (df["zl_close"] * 11) / total_products
    else:
        df["board_crush"] = None
        df["oil_share"] = None

    return df


def compute_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute calendar-based features."""
    df = df.copy()

    df["day_of_week"] = df["as_of_date"].dt.dayofweek  # 0=Monday
    df["month"] = df["as_of_date"].dt.month

    # WASDE week: 7th-14th of month
    df["is_wasde_week"] = df["as_of_date"].dt.day.isin(WASDE_DAYS)

    # FOMC week: 3rd week of FOMC months
    df["is_fomc_week"] = (
        (df["month"].isin(FOMC_MONTHS))
        & (df["as_of_date"].dt.day >= 15)
        & (df["as_of_date"].dt.day <= 21)
    )

    # Expiry week: 3rd week of month
    df["is_expiry_week"] = (df["as_of_date"].dt.day >= 15) & (
        df["as_of_date"].dt.day <= 21
    )

    # Quarter end
    df["is_quarter_end"] = (df["month"].isin([3, 6, 9, 12])) & (
        df["as_of_date"].dt.day >= 25
    )

    return df


def compute_regimes(df: pd.DataFrame) -> pd.DataFrame:
    """Compute volatility and trend regimes."""
    df = df.copy()

    # Vol regime based on 21d vol percentile
    if "zl_vol_21d" in df.columns:
        vol_pct = df["zl_vol_21d"].rank(pct=True)
        df["vol_regime"] = pd.cut(
            vol_pct, bins=[0, 0.33, 0.67, 1.0], labels=["low", "normal", "high"]
        ).astype(str)
    else:
        df["vol_regime"] = "normal"

    # Trend regime based on 21d return
    if "zl_return_21d" in df.columns:
        df["trend_regime"] = np.where(
            df["zl_return_21d"] > 0.02,
            "bull",
            np.where(df["zl_return_21d"] < -0.02, "bear", "range"),
        )
    else:
        df["trend_regime"] = "range"

    return df


def compute_staleness(df: pd.DataFrame, conn) -> pd.DataFrame:
    """Compute staleness days for WASDE and COT."""
    df = df.copy()

    # Get latest WASDE dates
    wasde_query = """
        SELECT DISTINCT event_date::date as wasde_date
        FROM supply.usda_wasde_1m
        ORDER BY event_date
    """
    wasde_dates = pd.read_sql(wasde_query, conn)["wasde_date"].tolist()

    # Get latest COT dates
    cot_query = """
        SELECT DISTINCT event_date::date as cot_date
        FROM pos.cftc_1w
        ORDER BY event_date
    """
    cot_dates = pd.read_sql(cot_query, conn)["cot_date"].tolist()

    def days_since_last(date, reference_dates):
        """Calculate days since most recent reference date."""
        past_dates = [d for d in reference_dates if d <= date.date()]
        if not past_dates:
            return None
        return (date.date() - max(past_dates)).days

    df["wasde_staleness_days"] = df["as_of_date"].apply(
        lambda d: days_since_last(d, wasde_dates)
    )
    df["cot_staleness_days"] = df["as_of_date"].apply(
        lambda d: days_since_last(d, cot_dates)
    )

    return df


def prepare_final_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Select and order columns for insertion."""
    columns = [
        "as_of_date",
        "target_5d",
        "target_21d",
        "target_63d",
        "target_126d",
        "zl_close",
        "zl_return_1d",
        "zl_return_5d",
        "zl_return_21d",
        "zl_vol_21d",
        "zl_vol_63d",
        "zs_close",
        "zm_close",
        "board_crush",
        "oil_share",
        "day_of_week",
        "month",
        "is_wasde_week",
        "is_fomc_week",
        "is_expiry_week",
        "is_quarter_end",
        "vol_regime",
        "trend_regime",
        "wasde_staleness_days",
        "cot_staleness_days",
    ]

    # Ensure all columns exist
    for col in columns:
        if col not in df.columns:
            df[col] = None

    return df[columns]


def insert_to_database(conn, df: pd.DataFrame, dry_run: bool = True):
    """Insert data into training.matrix_1d."""
    if dry_run:
        print(f"\n[DRY RUN] Would insert {len(df)} rows")
        print(f"Date range: {df['as_of_date'].min()} to {df['as_of_date'].max()}")
        print(f"\nSample rows:")
        print(df.head(3).to_string())
        print(f"\n... and {len(df) - 3} more rows")
        return

    # Clear existing data
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE training.matrix_1d RESTART IDENTITY")

    # Convert DataFrame to records, replacing NaN with None for postgres NULL
    df_clean = df.copy()

    # Replace NaN with None (postgres NULL)
    df_clean = df_clean.where(pd.notnull(df_clean), None)

    # Convert numpy types to python types for psycopg2
    def convert_value(val):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        if isinstance(val, (np.integer, np.int64)):
            return int(val)
        if isinstance(val, (np.floating, np.float64)):
            return float(val)
        if isinstance(val, np.bool_):
            return bool(val)
        if isinstance(val, pd.Timestamp):
            return val.to_pydatetime().date()
        return val

    # Prepare insert
    columns = df_clean.columns.tolist()
    values = [tuple(convert_value(v) for v in row) for row in df_clean.values]

    insert_sql = f"""
        INSERT INTO training.matrix_1d ({", ".join(columns)}, created_at)
        VALUES %s
    """

    # Add created_at timestamp to each row (updated_at is not in Prisma schema)
    from datetime import timezone

    now = datetime.now(timezone.utc)
    values_with_timestamps = [v + (now,) for v in values]

    # Use execute_values for efficient batch insert
    template = "(" + ", ".join(["%s"] * len(columns)) + ", %s)"
    execute_values(
        cursor, insert_sql, values_with_timestamps, template=template, page_size=1000
    )

    conn.commit()
    print(f"\n✅ Inserted {len(df)} rows into training.matrix_1d")


def main():
    parser = argparse.ArgumentParser(description="Populate training.matrix_1d")
    parser.add_argument(
        "--start", default="2000-01-01", help="Start date (default: 2000-01-01)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting"
    )
    parser.add_argument("--execute", action="store_true", help="Actually insert data")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("ERROR: Must specify either --dry-run or --execute")
        sys.exit(1)

    print("=" * 60)
    print("POPULATE CORE MATRIX")
    print("=" * 60)
    print(f"Start date: {args.start}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")

    conn = get_connection()

    try:
        # Load data
        print("\n[1/8] Loading ZL prices...")
        df = load_zl_prices(conn, args.start)
        print(f"      Loaded {len(df)} trading days")

        print("\n[2/8] Loading related prices (ZS, ZM)...")
        related = load_related_prices(conn, args.start)
        print(f"      Loaded {len(related)} days")

        # Compute features
        print("\n[3/8] Computing targets (trading day leads)...")
        df = compute_targets(df)

        print("\n[4/8] Computing returns...")
        df = compute_returns(df)

        print("\n[5/8] Computing volatility...")
        df = compute_volatility(df)

        print("\n[6/8] Computing crush spread...")
        df = compute_crush_spread(df, related)

        print("\n[7/8] Computing calendar features...")
        df = compute_calendar_features(df)
        df = compute_regimes(df)
        df = compute_staleness(df, conn)

        # Prepare and validate
        print("\n[8/8] Preparing final dataframe...")
        df = prepare_final_dataframe(df)

        # Remove rows where targets are NaN (future dates we can't compute)
        max(HORIZONS)
        df_valid = df.dropna(subset=["target_5d"])  # At minimum need 5d target
        print(f"      Valid rows (with targets): {len(df_valid)}")
        print(
            f"      Dropped {len(df) - len(df_valid)} rows (insufficient future data)"
        )

        # Summary stats
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total rows to insert: {len(df_valid)}")
        print(
            f"Date range: {df_valid['as_of_date'].min()} to {df_valid['as_of_date'].max()}"
        )
        print(f"\nTarget coverage:")
        for h in HORIZONS:
            col = f"target_{h}d"
            count = df_valid[col].notna().sum()
            print(f"  {col}: {count} rows ({count / len(df_valid) * 100:.1f}%)")

        # Insert
        insert_to_database(conn, df_valid, dry_run=args.dry_run)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
