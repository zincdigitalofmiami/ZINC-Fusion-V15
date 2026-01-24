#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Specialist Signal Generation Orchestrator

Generates compact signals (1-2 values per date) from all 11 specialists
and writes them to training.specialist_signals_1d.

This replaces the old 44-model architecture with 11 signal generators
that feed into the Core training matrix.

Usage:
    python scripts/generate_specialist_signals.py
    python scripts/generate_specialist_signals.py --bucket crush --start-date 2020-01-01
    python scripts/generate_specialist_signals.py --bucket all --dry-run
    python scripts/generate_specialist_signals.py --backfill --start-date 2015-01-01

@author Claude (ZINC-FUSION-V15)
@version 1.0.0
@date 2026-01-21
"""

import os
import sys
import logging
import argparse
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import hashlib

import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv(PROJECT_ROOT / ".env")


# =============================================================================
# CONSTANTS
# =============================================================================

SPECIALISTS = [
    "crush", "china", "fx", "fed", "tariff",
    "energy", "biofuel", "palm", "volatility",
    "substitutes", "trump_effect",
]


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def get_connection():
    """Get database connection from DATABASE_URL."""
    import psycopg2
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    return psycopg2.connect(database_url)


# =============================================================================
# DATA LOADING
# =============================================================================

def load_training_matrix(
    conn,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """
    Load training matrix from database.

    Returns DataFrame with trade_date as index and all feature columns.
    """
    query = """
    SELECT *
    FROM training.matrix_1d
    WHERE symbol = 'ZL'
    """
    params = []

    if start_date:
        query += " AND trade_date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND trade_date <= %s"
        params.append(end_date)

    query += " ORDER BY trade_date"

    df = pd.read_sql(query, conn, params=params if params else None)

    if df.empty:
        raise ValueError("No data found in training.matrix_1d")

    # Set trade_date as index
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date")

    logger.info(f"Loaded {len(df)} rows from training.matrix_1d ({df.index.min()} to {df.index.max()})")
    return df


def load_supplemental_data(conn, df: pd.DataFrame) -> pd.DataFrame:
    """
    Load supplemental data that may not be in the training matrix.

    Includes:
    - Related futures (ZS, ZM, CL, HO, etc.)
    - FX pairs
    - Commodity prices (CPO, HG, etc.)
    """
    start_date = df.index.min().date()
    end_date = df.index.max().date()

    # Load related futures
    futures_query = """
    SELECT event_date as trade_date, symbol, close, volume, open_interest
    FROM mkt.futures_1d
    WHERE event_date >= %s AND event_date <= %s
      AND symbol IN ('ZS', 'ZM', 'CL', 'HO', 'RB', 'NG', 'HG', 'RS', 'DX', 'BDRY', 'SBLK')
    ORDER BY event_date, symbol
    """
    futures_df = pd.read_sql(futures_query, conn, params=[start_date, end_date])

    if not futures_df.empty:
        futures_df["trade_date"] = pd.to_datetime(futures_df["trade_date"])
        futures_pivot = futures_df.pivot(
            index="trade_date",
            columns="symbol",
            values="close"
        )
        futures_pivot.columns = [f"{col.lower()}_close" for col in futures_pivot.columns]

        # Merge into main dataframe (rsuffix for overlapping columns)
        df = df.join(futures_pivot, how="left", rsuffix="_supp")
        logger.info(f"Added {len(futures_pivot.columns)} supplemental futures columns")

    # Load CPO (palm oil) if available
    cpo_query = """
    SELECT event_date as trade_date, close as cpo_close
    FROM mkt.futures_1d
    WHERE event_date >= %s AND event_date <= %s
      AND symbol = 'CPO'
    ORDER BY event_date
    """
    try:
        cpo_df = pd.read_sql(cpo_query, conn, params=[start_date, end_date])
        if not cpo_df.empty:
            cpo_df["trade_date"] = pd.to_datetime(cpo_df["trade_date"])
            cpo_df = cpo_df.set_index("trade_date")
            df = df.join(cpo_df, how="left")
            logger.info("Added CPO (palm oil) data")
    except Exception as e:
        logger.warning(f"Could not load CPO data: {e}")

    # Load RIN prices for biofuel specialist (NEW - 2026-01-21)
    rin_query = """
    SELECT event_date as trade_date, rin_type, price
    FROM supply.epa_rin_1d
    WHERE event_date >= %s AND event_date <= %s
    ORDER BY event_date, rin_type
    """
    try:
        rin_df = pd.read_sql(rin_query, conn, params=[start_date, end_date])
        if not rin_df.empty:
            rin_df["trade_date"] = pd.to_datetime(rin_df["trade_date"])
            # Pivot RIN types to columns
            rin_pivot = rin_df.pivot(
                index="trade_date",
                columns="rin_type",
                values="price"
            )
            # Rename columns to match expected names
            rin_pivot.columns = [f"rin_{col.lower()}_price" for col in rin_pivot.columns]
            df = df.join(rin_pivot, how="left")
            logger.info(f"Added {len(rin_pivot.columns)} RIN price columns: {list(rin_pivot.columns)}")
    except Exception as e:
        logger.warning(f"Could not load RIN prices: {e}")

    # Load WASDE fundamentals for crush specialist (NEW - 2026-01-21)
    wasde_query = """
    SELECT
        event_date as trade_date,
        commodity,
        metric,
        value
    FROM supply.usda_wasde_1m
    WHERE event_date >= %s AND event_date <= %s
      AND commodity IN ('Soybean Oil', 'Soybeans', 'Soybean Meal')
      AND country = 'United States'
    ORDER BY event_date
    """
    try:
        wasde_df = pd.read_sql(wasde_query, conn, params=[start_date, end_date])
        if not wasde_df.empty:
            wasde_df["trade_date"] = pd.to_datetime(wasde_df["trade_date"])
            # Create key from commodity + metric
            wasde_df["key"] = wasde_df["commodity"].str.replace(" ", "_").str.lower() + "_" + \
                             wasde_df["metric"].str.replace(" ", "_").str.lower()
            # Pivot to wide format
            wasde_pivot = wasde_df.pivot(
                index="trade_date",
                columns="key",
                values="value"
            )
            wasde_pivot.columns = [f"wasde_{col}" for col in wasde_pivot.columns]
            df = df.join(wasde_pivot, how="left")
            logger.info(f"Added {len(wasde_pivot.columns)} WASDE columns")
    except Exception as e:
        logger.warning(f"Could not load WASDE data: {e}")

    # Load FRED commodity proxies for sunflower/rapeseed (econ.commodities_1d)
    commodities_query = """
    SELECT event_date as trade_date, series_id, value
    FROM econ.commodities_1d
    WHERE event_date >= %s AND event_date <= %s
      AND series_id IN ('PROILUSDM', 'PSUNOUSDM')
    ORDER BY event_date, series_id
    """
    try:
        comm_df = pd.read_sql(commodities_query, conn, params=[start_date, end_date])
        if not comm_df.empty:
            comm_df["trade_date"] = pd.to_datetime(comm_df["trade_date"])
            comm_pivot = comm_df.pivot(
                index="trade_date",
                columns="series_id",
                values="value"
            )
            # Map FRED series IDs to expected column names
            rename_map = {
                "PROILUSDM": "rapeseed_close",
                "PSUNOUSDM": "sunflower_close",
            }
            comm_pivot = comm_pivot.rename(columns=rename_map)
            df = df.join(comm_pivot, how="left")
            logger.info(f"Added FRED commodity columns: {list(comm_pivot.columns)}")
    except Exception as e:
        logger.warning(f"Could not load FRED commodity proxies: {e}")

    # Fallback: alias rapeseed_close to rs_close if missing or empty
    if "rapeseed_close" not in df.columns or df["rapeseed_close"].isna().all():
        if "rs_close" in df.columns:
            df["rapeseed_close"] = df["rs_close"]
            logger.info("Aliased rapeseed_close from rs_close (no rapeseed series found)")
        else:
            logger.warning("rapeseed_close missing and rs_close not available; alias skipped")

    return df


# =============================================================================
# SIGNAL GENERATION
# =============================================================================

def generate_signals_for_bucket(
    bucket: str,
    data: pd.DataFrame,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict]:
    """
    Generate signals for a single specialist bucket.

    Returns list of signal dictionaries ready for database insertion.
    """
    from fusion.specialists import get_generator, SignalOutput

    try:
        generator = get_generator(bucket)
        signals = generator.generate(data, start_date, end_date)

        # Convert to dicts for insertion
        return [sig.to_dict() for sig in signals]

    except ValueError as e:
        logger.warning(f"Skipping {bucket}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error generating {bucket} signals: {e}")
        return []


def generate_all_signals(
    data: pd.DataFrame,
    buckets: List[str],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Dict[str, List[Dict]]:
    """
    Generate signals for all specified buckets.

    Returns dict mapping bucket name to list of signal dicts.
    """
    all_signals = {}

    for bucket in buckets:
        logger.info(f"Generating signals for {bucket}...")
        signals = generate_signals_for_bucket(bucket, data, start_date, end_date)
        all_signals[bucket] = signals
        logger.info(f"  {bucket}: {len(signals)} signals generated")

    return all_signals


# =============================================================================
# DATABASE WRITING
# =============================================================================

def write_signals_to_db(
    conn,
    signals: Dict[str, List[Dict]],
    run_hash: str,
    dry_run: bool = False,
) -> int:
    """
    Write signals to training.specialist_signals_1d.

    Uses UPSERT to handle re-runs cleanly.

    Returns number of signals written.
    """
    from psycopg2.extras import execute_values

    total_written = 0

    upsert_query = """
    INSERT INTO training.specialist_signals_1d
        (as_of_date, bucket, signal_1, signal_2, confidence, model_type, run_hash)
    VALUES %s
    ON CONFLICT (as_of_date, bucket)
    DO UPDATE SET
        signal_1 = EXCLUDED.signal_1,
        signal_2 = EXCLUDED.signal_2,
        confidence = EXCLUDED.confidence,
        model_type = EXCLUDED.model_type,
        run_hash = EXCLUDED.run_hash,
        created_at = NOW()
    """

    for bucket, bucket_signals in signals.items():
        if not bucket_signals:
            continue

        # Prepare values
        values = [
            (
                sig["as_of_date"],
                sig["bucket"],
                sig["signal_1"],
                sig.get("signal_2"),
                sig.get("confidence"),
                sig["model_type"],
                run_hash,
            )
            for sig in bucket_signals
        ]

        if dry_run:
            logger.info(f"  [DRY RUN] Would write {len(values)} {bucket} signals")
        else:
            try:
                with conn.cursor() as cur:
                    execute_values(cur, upsert_query, values)
                conn.commit()
                logger.info(f"  Wrote {len(values)} {bucket} signals")
                total_written += len(values)
            except Exception as e:
                conn.rollback()
                logger.error(f"  Failed to write {bucket} signals: {e}")

    return total_written


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate specialist signals for v3 architecture"
    )
    parser.add_argument(
        "--bucket",
        choices=SPECIALISTS + ["all"],
        default="all",
        help="Specialist bucket to generate (default: all)",
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill mode: generate signals for all available history",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to database, just show what would be done",
    )
    args = parser.parse_args()

    # Determine buckets to process
    buckets = SPECIALISTS if args.bucket == "all" else [args.bucket]

    # Determine date range
    start_date = args.start_date
    end_date = args.end_date or date.today()

    if args.backfill and not start_date:
        start_date = date(2015, 1, 1)
        logger.info(f"Backfill mode: starting from {start_date}")

    # Generate run hash
    run_hash = hashlib.sha256(
        f"{datetime.now().isoformat()}:{','.join(buckets)}".encode()
    ).hexdigest()[:16]

    logger.info(f"Run hash: {run_hash}")
    logger.info(f"Buckets: {buckets}")
    logger.info(f"Date range: {start_date or 'earliest'} to {end_date}")
    logger.info(f"Dry run: {args.dry_run}")

    # Connect and load data
    conn = get_connection()

    try:
        # Load training matrix
        data = load_training_matrix(conn, start_date, end_date)

        # Add supplemental data
        data = load_supplemental_data(conn, data)

        # Generate signals
        signals = generate_all_signals(data, buckets, start_date, end_date)

        # Write to database
        total = sum(len(sigs) for sigs in signals.values())
        logger.info(f"Total signals generated: {total}")

        if total > 0:
            written = write_signals_to_db(conn, signals, run_hash, args.dry_run)
            logger.info(f"Total signals written: {written}")

    finally:
        conn.close()

    logger.info("Signal generation complete.")


if __name__ == "__main__":
    main()
