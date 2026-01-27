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
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional
import hashlib

from dotenv import load_dotenv

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

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
# SIGNAL GENERATION
# =============================================================================

def generate_signals_for_bucket(
    bucket: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    strict_mode: bool = False,
) -> List[Dict]:
    """
    Generate signals for a single specialist bucket.

    EACH SPECIALIST LOADS ITS OWN DATA via data_loaders.py.
    No shared matrix - each bucket queries exactly what it needs.

    Returns list of signal dictionaries ready for database insertion.
    """
    from fusion.specialists import get_generator, SignalOutput
    from fusion.specialists.data_loaders import load_specialist_data

    try:
        # LOAD THIS SPECIALIST'S OWN DATA
        logger.info(f"   Loading {bucket}-specific data...")
        specialist_data = load_specialist_data(bucket, start_date, end_date)
        logger.info(f"   {bucket} data: {len(specialist_data)} rows, {len(specialist_data.columns)} columns")
        
        # Get the generator and run
        generator = get_generator(bucket)
        signals = generator.generate(specialist_data, start_date, end_date)

        # Convert to dicts for insertion
        return [sig.to_dict() for sig in signals]

    except ValueError as e:
        if strict_mode:
            logger.error(f"Strict mode: {bucket} failed validation: {e}")
            raise
        logger.warning(f"Skipping {bucket}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error generating {bucket} signals: {e}")
        import traceback
        logger.error(traceback.format_exc())
        if strict_mode:
            raise
        return []


def generate_all_signals(
    buckets: List[str],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    strict_mode: bool = False,
) -> Dict[str, List[Dict]]:
    """
    Generate signals for all specified buckets.

    Each bucket loads its OWN data independently.

    Returns dict mapping bucket name to list of signal dicts.
    """
    all_signals = {}

    for bucket in buckets:
        logger.info(f"Generating signals for {bucket}...")
        signals = generate_signals_for_bucket(bucket, start_date, end_date, strict_mode=strict_mode)
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
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: fail immediately on missing features or validation errors.",
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
    strict_mode = args.strict
    os.environ["STRICT_DATA"] = "true" if strict_mode else "false"
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Strict mode: {strict_mode}")

    # Connect to database
    conn = get_connection()

    try:
        # Generate signals - EACH specialist loads its own data
        signals = generate_all_signals(buckets, start_date, end_date, strict_mode=strict_mode)

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
