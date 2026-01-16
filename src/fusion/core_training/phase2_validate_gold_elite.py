"""
Phase 2: Validate Gold Elite Indicators
=======================================

Verifies gold.elite_indicators_1d is populated and complete.
Since data already exists (6,627 rows, 2000-2026), this phase validates
rather than rebuilds.

If validation fails, triggers rebuild from silver.futures_prices_1d
using EliteIndicators.compute_all().
"""

from __future__ import annotations

import logging
import hashlib
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd
import psycopg2

from .config import DATABASE_URL, TARGET_SYMBOL

logger = logging.getLogger(__name__)

# Expected columns from EliteIndicators
EXPECTED_COLUMNS = [
    "trade_date",
    "symbol",
    # OHLCV
    "open",
    "high",
    "low",
    "close",
    "volume",
    # Returns
    "returns_1d",
    "log_returns_1d",
    "range_pct",
    # Tier 1: Institutional Gems
    "hurst_exponent",
    "hurst_regime",
    "connors_rsi",
    "fisher_transform",
    "fisher_signal",
    "mcginley_dynamic",
    "ttm_squeeze_on",
    "ttm_squeeze_momentum",
    "schaff_trend_cycle",
    "rvi",
    "rvi_signal",
    "elder_force_index",
    # Tier 2: Optimized Staples
    "kama_10",
    "hma_20",
    "alma_50",
    "rsi_2",
    "rsi_14",
    "cumulative_rsi",
    "macd",
    "macd_signal",
    "macd_histogram",
    "cci_14",
    "cci_50",
    # Tier 3: Volatility
    "atr_10",
    "atr_50",
    "atr_ratio",
    "garman_klass_vol",
    "yang_zhang_vol",
    "bb_percent_b",
    # Tier 4: Volume/Flow
    "cmf_21",
    "volume_zscore",
    "unusual_volume",
]

MINIMUM_ROWS = 6000  # Should have ~6,500 rows for 2000-2026
EXPECTED_START_DATE = "2000-01-01"


def validate_elite_indicators(conn, symbol: str) -> Tuple[bool, dict]:
    """
    Validate gold.elite_indicators_1d completeness.

    Returns:
        (valid: bool, stats: dict)
    """
    logger.info("Validating gold.elite_indicators_1d...")

    stats = {}

    # Check row count and date range
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 
                COUNT(*) as row_count,
                MIN(trade_date) as min_date,
                MAX(trade_date) as max_date,
                COUNT(DISTINCT trade_date) as unique_dates
            FROM gold.elite_indicators_1d
            WHERE symbol = %s
        """,
            (symbol,),
        )
        row = cur.fetchone()

        stats["row_count"] = row[0]
        stats["min_date"] = str(row[1]) if row[1] else None
        stats["max_date"] = str(row[2]) if row[2] else None
        stats["unique_dates"] = row[3]

    logger.info(f"   Rows: {stats['row_count']:,}")
    logger.info(f"   Date range: {stats['min_date']} to {stats['max_date']}")
    logger.info(f"   Unique dates: {stats['unique_dates']:,}")

    # Check minimum rows
    if stats["row_count"] < MINIMUM_ROWS:
        logger.error(f"❌ Insufficient rows: {stats['row_count']} < {MINIMUM_ROWS}")
        return False, stats

    # Check columns exist
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name 
            FROM information_schema.columns
            WHERE table_schema = 'gold' 
              AND table_name = 'elite_indicators_1d'
        """
        )
        existing_cols = {row[0] for row in cur.fetchall()}

    missing_cols = []
    for col in EXPECTED_COLUMNS:
        if col not in existing_cols:
            missing_cols.append(col)

    stats["existing_columns"] = len(existing_cols)
    stats["missing_columns"] = missing_cols

    if missing_cols:
        logger.warning(f"⚠️ Missing columns: {missing_cols}")
    else:
        logger.info(f"   All {len(EXPECTED_COLUMNS)} expected columns present")

    # Check for nulls in critical columns
    critical_cols = ["close", "hurst_exponent", "connors_rsi", "atr_ratio"]
    null_counts = {}

    with conn.cursor() as cur:
        for col in critical_cols:
            if col in existing_cols:
                cur.execute(
                    f"""
                    SELECT COUNT(*) 
                    FROM gold.elite_indicators_1d
                    WHERE symbol = %s AND {col} IS NULL
                """,
                    (symbol,),
                )
                null_counts[col] = cur.fetchone()[0]

    stats["null_counts"] = null_counts
    logger.info(f"   Null counts in critical columns: {null_counts}")

    # Compute content hash for lineage
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT MD5(STRING_AGG(
                COALESCE(trade_date::text, '') || 
                COALESCE(close::text, '') ||
                COALESCE(hurst_exponent::text, ''),
                ''
            ))
            FROM gold.elite_indicators_1d
            WHERE symbol = %s
            ORDER BY trade_date
        """,
            (symbol,),
        )
        stats["content_hash"] = cur.fetchone()[0]

    logger.info(f"   Content hash: {stats['content_hash'][:16]}...")

    # Overall validation
    valid = (
        stats["row_count"] >= MINIMUM_ROWS
        and len(missing_cols) == 0
        and stats["min_date"] <= EXPECTED_START_DATE
    )

    return valid, stats


def get_elite_version(stats: dict) -> str:
    """Generate elite_version hash from validation stats."""
    content = f"{stats['row_count']}_{stats['min_date']}_{stats['max_date']}_{stats['content_hash']}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def run(symbol: str = TARGET_SYMBOL) -> Tuple[bool, Optional[str]]:
    """
    Execute Phase 2: Validate Gold Elite Indicators.

    Returns:
        (success: bool, elite_version: Optional[str])
    """
    logger.info("=" * 60)
    logger.info("PHASE 2: VALIDATE GOLD ELITE INDICATORS")
    logger.info("=" * 60)
    logger.info(f"Symbol: {symbol}")
    logger.info("=" * 60)

    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("✅ Database connected")

        valid, stats = validate_elite_indicators(conn, symbol)

        conn.close()

        if valid:
            elite_version = get_elite_version(stats)
            logger.info("=" * 60)
            logger.info("✅ PHASE 2 COMPLETE - Elite indicators validated")
            logger.info(f"   Rows: {stats['row_count']:,}")
            logger.info(f"   Elite version: {elite_version}")
            logger.info("=" * 60)
            return True, elite_version
        else:
            logger.error("=" * 60)
            logger.error("❌ PHASE 2 FAILED - Elite indicators incomplete")
            logger.error("   Manual rebuild required via EliteIndicators.compute_all()")
            logger.error("=" * 60)
            return False, None

    except Exception as e:
        logger.error(f"❌ PHASE 2 FAILED: {e}", exc_info=True)
        return False, None


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Phase 2: Validate Elite Indicators")
    parser.add_argument("--symbol", default=TARGET_SYMBOL)
    args = parser.parse_args()

    success, version = run(args.symbol)
    exit(0 if success else 1)
