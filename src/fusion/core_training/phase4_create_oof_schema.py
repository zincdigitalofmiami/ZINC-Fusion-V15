"""
Phase 4: Create OOF Schema
===========================

Defines and creates the training.oof_core_1d table for out-of-fold predictions.

OOF Discipline (LOCKED):
- One row per (trade_date, horizon_days, window_id)
- MUST stamp window_id + cutoff_date for every prediction
- Schema immutable after creation
- run_hash REQUIRED for lineage
- Column names: p30, p50, p70 (stable for L1 interface)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Tuple

import psycopg2

from .config import (
    DATABASE_URL,
    OOF_COLUMNS,
    OOF_COLUMN_NAMES,
    OOF_TABLE_NAME,
    HORIZONS,
)

logger = logging.getLogger(__name__)


# DDL for OOF table - columns match config.OOF_COLUMNS exactly
OOF_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS training.oof_core_1d (
    -- Primary identifiers
    trade_date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL DEFAULT 'ZL',
    horizon_days INTEGER NOT NULL,
    window_id INTEGER NOT NULL,
    cutoff_date DATE NOT NULL,

    -- Quantile predictions (names stable for L1 interface)
    p30 DOUBLE PRECISION NOT NULL,
    p50 DOUBLE PRECISION NOT NULL,
    p70 DOUBLE PRECISION NOT NULL,

    -- Actuals for evaluation
    target_value DOUBLE PRECISION,

    -- Model lineage (REQUIRED)
    trained_at TIMESTAMP NOT NULL DEFAULT NOW(),
    run_hash VARCHAR(64) NOT NULL,

    -- Matrix lineage
    matrix_version VARCHAR(64),

    -- Governance
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, symbol, horizon_days, window_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_oof_core_horizon 
    ON training.oof_core_1d (horizon_days);
    
CREATE INDEX IF NOT EXISTS idx_oof_core_window 
    ON training.oof_core_1d (window_id, cutoff_date);
    
CREATE INDEX IF NOT EXISTS idx_oof_core_run_hash 
    ON training.oof_core_1d (run_hash);

-- Constraint: window_id must be positive
ALTER TABLE training.oof_core_1d
    ADD CONSTRAINT chk_window_id_positive CHECK (window_id > 0);
    
-- Constraint: horizon must be valid
ALTER TABLE training.oof_core_1d
    ADD CONSTRAINT chk_horizon_valid CHECK (horizon_days IN (5, 21, 63, 126));
    
-- Constraint: quantiles must be ordered (monotonic)
ALTER TABLE training.oof_core_1d
    ADD CONSTRAINT chk_quantile_monotonic CHECK (p30 <= p50 AND p50 <= p70);
"""

# View for easy analysis
OOF_VIEW_DDL = """
CREATE OR REPLACE VIEW training.v_oof_core_summary AS
SELECT 
    horizon_days,
    window_id,
    cutoff_date,
    run_hash,
    COUNT(*) as row_count,
    MIN(trade_date) as min_date,
    MAX(trade_date) as max_date,
    AVG(target_value - p50) as mean_error,
    STDDEV(target_value - p50) as std_error,
    -- Coverage metrics (what % of actuals fall within quantiles)
    AVG(CASE WHEN target_value BETWEEN p30 AND p70 THEN 1.0 ELSE 0.0 END) as coverage_30_70
FROM training.oof_core_1d
WHERE target_value IS NOT NULL
GROUP BY horizon_days, window_id, cutoff_date, run_hash
ORDER BY horizon_days, window_id;
"""


def check_existing_table(conn) -> Tuple[bool, int]:
    """Check if OOF table exists and get row count."""
    # Parse canonical table name from config
    schema, table = OOF_TABLE_NAME.split(".")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name = %s
            )
        """,
            (schema, table),
        )
        exists = cur.fetchone()[0]

        if exists:
            cur.execute(f"SELECT COUNT(*) FROM {OOF_TABLE_NAME}")
            row_count = cur.fetchone()[0]
            return True, row_count

        return False, 0


def create_oof_table(conn) -> bool:
    """Create OOF table with constraints."""
    logger.info("Creating training.oof_core_1d table...")

    with conn.cursor() as cur:
        # Split DDL into individual statements
        statements = [s.strip() for s in OOF_TABLE_DDL.split(";") if s.strip()]

        for stmt in statements:
            try:
                cur.execute(stmt)
            except psycopg2.errors.DuplicateObject as e:
                # Constraint already exists - ignore
                conn.rollback()
                continue
            except Exception as e:
                logger.error(f"Failed to execute: {stmt[:100]}...")
                raise

    conn.commit()
    logger.info("✅ OOF table created")
    return True


def create_oof_view(conn) -> bool:
    """Create summary view for OOF analysis."""
    logger.info("Creating training.v_oof_core_summary view...")

    with conn.cursor() as cur:
        cur.execute(OOF_VIEW_DDL)

    conn.commit()
    logger.info("✅ OOF summary view created")
    return True


def validate_schema(conn) -> bool:
    """Validate OOF table has required columns matching config."""
    logger.info("Validating OOF schema against config.OOF_COLUMN_NAMES...")

    schema, table = OOF_TABLE_NAME.split(".")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
        """,
            (schema, table),
        )
        columns = cur.fetchall()

    existing_cols = {row[0] for row in columns}
    required_cols = set(OOF_COLUMN_NAMES)

    missing = required_cols - existing_cols
    if missing:
        logger.error(f"❌ Missing columns: {missing}")
        return False

    logger.info(f"✅ All {len(required_cols)} required columns present")
    return True


def run() -> Tuple[bool, bool]:
    """
    Execute Phase 4: Create OOF Schema.

    Returns:
        (success: bool, table_created: bool)
    """
    logger.info("=" * 60)
    logger.info("PHASE 4: CREATE OOF SCHEMA")
    logger.info("=" * 60)
    logger.info(f"Target table: {OOF_TABLE_NAME}")
    logger.info(f"Horizons: {HORIZONS}")
    logger.info("Quantile columns: p30, p50, p70")
    logger.info("=" * 60)

    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("✅ Database connected")

        # Check existing state
        exists, row_count = check_existing_table(conn)

        if exists:
            logger.info(f"Table already exists with {row_count:,} rows")

            # Validate schema anyway
            if validate_schema(conn):
                logger.info("=" * 60)
                logger.info("✅ PHASE 4 COMPLETE - OOF schema validated")
                logger.info("=" * 60)
                conn.close()
                return True, False
            else:
                logger.error("Schema validation failed - manual intervention required")
                conn.close()
                return False, False

        # Create table
        create_oof_table(conn)

        # Create view
        create_oof_view(conn)

        # Validate
        if validate_schema(conn):
            logger.info("=" * 60)
            logger.info("✅ PHASE 4 COMPLETE - OOF schema created")
            logger.info("=" * 60)
            conn.close()
            return True, True
        else:
            conn.close()
            return False, False

    except Exception as e:
        logger.error(f"❌ PHASE 4 FAILED: {e}", exc_info=True)
        return False, False


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    success, created = run()
    if success:
        print(f"Table {'created' if created else 'validated'}")
    exit(0 if success else 1)
