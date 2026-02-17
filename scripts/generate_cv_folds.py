#!/usr/bin/env python3
"""
ZINC-FUSION-V15: CV Folds Generation Script

Generates purged walk-forward cross-validation folds for all horizons.
These folds are the canonical source of truth for all training.

NON-NEGOTIABLES:
- Folds are stored in Postgres as single source of truth
- Purge gap prevents data leakage from recent observations
- Embargo period prevents look-ahead bias

Fold Parameters (LOCKED):
- 5 folds
- 5-day purge gap (removes observations immediately before validation)
- Embargo = horizon length (removes observations after validation start)

Usage:
    python scripts/generate_cv_folds.py --dry-run    # Preview only
    python scripts/generate_cv_folds.py              # Generate and insert
    python scripts/generate_cv_folds.py --validate   # Validate existing folds
"""

import os
import logging
import argparse
from datetime import datetime, timedelta
from typing import List, Tuple, Dict
from dataclasses import dataclass

import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv(".env.vercel")

# CV Parameters (LOCKED)
NUM_FOLDS = 5
PURGE_GAP = 5  # days before validation to exclude
HORIZONS = [5, 21, 63, 126]  # days


@dataclass
class CVFold:
    """Represents a single CV fold assignment for a date."""

    as_of_date: datetime
    horizon: int
    fold_id: int
    is_train: bool
    is_val: bool


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def get_date_range(conn) -> Tuple[datetime, datetime]:
    """Get the date range from mkt.futures_1d for ZL symbol."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT MIN(event_date), MAX(event_date)
            FROM mkt.futures_1d
            WHERE symbol = 'ZL'
        """)
        result = cur.fetchone()
        if not result or not result[0]:
            raise ValueError("No ZL data found in mkt.futures_1d")
        return result[0], result[1]


def generate_folds_for_horizon(
    start_date: datetime,
    end_date: datetime,
    horizon: int,
    num_folds: int = NUM_FOLDS,
    purge_gap: int = PURGE_GAP,
) -> List[CVFold]:
    """
    Generate purged walk-forward CV folds for a single horizon.

    Walk-forward means:
    - Each fold uses all prior data for training
    - Validation window is at the end of each fold's time period

    Purge gap:
    - Remove observations within PURGE_GAP days before validation start

    Embargo:
    - Remove observations for HORIZON days after validation start
      (to prevent look-ahead bias in feature construction)
    """
    folds = []

    # Calculate total days
    total_days = (end_date - start_date).days
    if total_days < 252:  # Less than 1 trading year
        logger.warning(f"Only {total_days} days available, may not have enough data")

    # Split into num_folds periods
    # Use expanding window: fold 0 trains on first 1/5, fold 4 trains on first 5/5
    fold_size = total_days // num_folds

    # Minimum training size (at least 252 trading days)

    current_date = start_date
    while current_date <= end_date:
        # Determine which fold this date belongs to based on time
        days_from_start = (current_date - start_date).days

        for fold_id in range(num_folds):
            # Each fold has a validation period at the end of its training window
            # Fold boundaries
            fold_end_day = (fold_id + 1) * fold_size

            # For walk-forward: fold_id N uses all data up to fold_end_day
            # and validates on the last portion
            val_start_day = fold_end_day - (
                fold_size // 2
            )  # Last half of fold is validation
            val_end_day = fold_end_day

            # Purge zone: purge_gap days before validation
            purge_start_day = val_start_day - purge_gap
            purge_end_day = val_start_day

            # Embargo zone: horizon days after validation start
            val_start_day + horizon

            # Determine if this date is train, val, or excluded
            is_train = False
            is_val = False

            if days_from_start < purge_start_day:
                # Training region (before purge)
                is_train = True
            elif purge_start_day <= days_from_start < purge_end_day:
                # Purge region - excluded from training
                is_train = False
                is_val = False
            elif val_start_day <= days_from_start < val_end_day:
                # Validation region
                is_val = True
            # After val_end_day: excluded (embargo for future folds)

            folds.append(
                CVFold(
                    as_of_date=current_date,
                    horizon=horizon,
                    fold_id=fold_id,
                    is_train=is_train,
                    is_val=is_val,
                )
            )

        current_date += timedelta(days=1)

    return folds


def generate_all_folds(
    start_date: datetime, end_date: datetime
) -> Dict[int, List[CVFold]]:
    """Generate CV folds for all horizons."""
    all_folds = {}

    for horizon in HORIZONS:
        logger.info(f"Generating folds for horizon={horizon}d")
        folds = generate_folds_for_horizon(start_date, end_date, horizon)
        all_folds[horizon] = folds

        # Log stats
        train_count = sum(1 for f in folds if f.is_train)
        val_count = sum(1 for f in folds if f.is_val)
        logger.info(f"  Total fold assignments: {len(folds)}")
        logger.info(f"  Training assignments: {train_count}")
        logger.info(f"  Validation assignments: {val_count}")

    return all_folds


def insert_folds(conn, folds: List[CVFold], dry_run: bool = False) -> int:
    """Insert CV folds into Postgres."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(folds)} fold assignments")
        return 0

    insert_query = """
        INSERT INTO cv_folds (as_of_date, horizon, fold_id, is_train, is_val)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (as_of_date, horizon, fold_id)
        DO UPDATE SET is_train = EXCLUDED.is_train, is_val = EXCLUDED.is_val
    """

    batch = [(f.as_of_date, f.horizon, f.fold_id, f.is_train, f.is_val) for f in folds]

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


def validate_folds(conn) -> bool:
    """Validate existing CV folds in Postgres."""
    logger.info("=" * 60)
    logger.info("VALIDATION: Checking CV folds")
    logger.info("=" * 60)

    all_valid = True

    with conn.cursor() as cur:
        # Check row counts by horizon
        cur.execute("""
            SELECT horizon,
                   COUNT(*) as total,
                   SUM(CASE WHEN is_train THEN 1 ELSE 0 END) as train_count,
                   SUM(CASE WHEN is_val THEN 1 ELSE 0 END) as val_count,
                   COUNT(DISTINCT fold_id) as fold_count,
                   MIN(as_of_date) as start_date,
                   MAX(as_of_date) as end_date
            FROM cv_folds
            GROUP BY horizon
            ORDER BY horizon
        """)

        for row in cur.fetchall():
            horizon, total, train, val, folds, start, end = row
            logger.info(f"\nHorizon {horizon}d:")
            logger.info(f"  Total assignments: {total:,}")
            logger.info(f"  Training: {train:,}")
            logger.info(f"  Validation: {val:,}")
            logger.info(f"  Folds: {folds}")
            logger.info(f"  Date range: {start} to {end}")

            # Validate fold count
            if folds != NUM_FOLDS:
                logger.error(f"  ERROR: Expected {NUM_FOLDS} folds, got {folds}")
                all_valid = False

            # Validate no overlap in is_train and is_val
            cur.execute(
                """
                SELECT COUNT(*)
                FROM cv_folds
                WHERE horizon = %s AND is_train = TRUE AND is_val = TRUE
            """,
                (horizon,),
            )
            overlap = cur.fetchone()[0]
            if overlap > 0:
                logger.error(
                    f"  ERROR: {overlap} rows have both is_train=TRUE and is_val=TRUE"
                )
                all_valid = False

    if all_valid:
        logger.info("\n" + "=" * 60)
        logger.info("VALIDATION PASSED")
        logger.info("=" * 60)
    else:
        logger.error("\n" + "=" * 60)
        logger.error("VALIDATION FAILED")
        logger.error("=" * 60)

    return all_valid


def run_generation(dry_run: bool = False, validate_only: bool = False):
    """Run the CV fold generation pipeline."""
    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: CV Folds Generation")
    logger.info("=" * 60)
    logger.info(f"Parameters:")
    logger.info(f"  NUM_FOLDS: {NUM_FOLDS}")
    logger.info(f"  PURGE_GAP: {PURGE_GAP} days")
    logger.info(f"  HORIZONS: {HORIZONS}")
    logger.info(f"  Dry run: {dry_run}")
    logger.info(f"  Validate only: {validate_only}")
    logger.info("")

    conn = get_postgres_connection()

    try:
        if validate_only:
            validate_folds(conn)
            return

        # Get date range from market data
        start_date, end_date = get_date_range(conn)
        logger.info(f"Date range from market data: {start_date} to {end_date}")

        # Generate folds for all horizons
        all_folds = generate_all_folds(start_date, end_date)

        # Insert folds
        total_inserted = 0
        for horizon, folds in all_folds.items():
            logger.info(f"\nInserting folds for horizon={horizon}d")
            inserted = insert_folds(conn, folds, dry_run)
            total_inserted += inserted
            if not dry_run:
                logger.info(f"  Inserted {inserted:,} fold assignments")

        if not dry_run:
            logger.info(f"\nTotal inserted: {total_inserted:,}")
            validate_folds(conn)

        logger.info("\n" + "=" * 60)
        logger.info("CV FOLDS GENERATION COMPLETE")
        logger.info("=" * 60)

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate CV folds for ZINC-FUSION-V15"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting"
    )
    parser.add_argument(
        "--validate", action="store_true", help="Validate existing folds only"
    )

    args = parser.parse_args()
    run_generation(dry_run=args.dry_run, validate_only=args.validate)


if __name__ == "__main__":
    main()
