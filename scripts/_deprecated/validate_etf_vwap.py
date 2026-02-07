#!/usr/bin/env python3
"""
ETF VWAP Validation Script

Validates VWAP data quality in mkt.etf_1d:
1. Non-null coverage by symbol
2. Date range coverage
3. VWAP sanity checks (vs close price)
4. Sample spot-checks

Usage:
    python scripts/validate_etf_vwap.py
    python scripts/validate_etf_vwap.py --symbols FXI,GLD,SPY

@author: Claude (ZINC-FUSION-V15)
@date: 2026-02-03
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from typing import List, Optional

import psycopg2

try:
    from tabulate import tabulate

    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

ETF_SYMBOLS = [
    "FXI",
    "KWEB",
    "MCHI",  # China
    "GLD",
    "SLV",  # Metals
    "BDRY",
    "SBLK",  # Shipping
    "XLE",
    "XOP",
    "USO",
    "UNG",
    "OIH",  # Energy
    "TLT",
    "IEF",  # Treasuries
    "SPY",
    "QQQ",  # Broad Market
    "DBA",
    "SOYB",
    "CORN",
    "WEAT",  # Ag
    "UUP",  # Dollar
    "ICLN",
    "TAN",
    "LIT",  # Green Energy
]


def get_db_connection():
    """Get database connection."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)


def validate_vwap_coverage(symbols: Optional[List[str]] = None):
    """Validate VWAP coverage across symbols."""
    if symbols is None:
        symbols = ETF_SYMBOLS

    conn = get_db_connection()
    cur = conn.cursor()

    logger.info("=" * 70)
    logger.info("ETF VWAP COVERAGE VALIDATION")
    logger.info("=" * 70)

    try:
        # Per-symbol coverage
        cur.execute(
            """
            SELECT
                symbol,
                COUNT(*) as total_rows,
                COUNT(vwap) as vwap_rows,
                ROUND(100.0 * COUNT(vwap) / NULLIF(COUNT(*), 0), 1) as vwap_pct,
                MIN(event_date) FILTER (WHERE vwap IS NOT NULL) as vwap_min_date,
                MAX(event_date) FILTER (WHERE vwap IS NOT NULL) as vwap_max_date,
                ROUND(AVG(vwap)::numeric, 2) as avg_vwap,
                ROUND(MIN(vwap)::numeric, 2) as min_vwap,
                ROUND(MAX(vwap)::numeric, 2) as max_vwap
            FROM mkt.etf_1d
            WHERE symbol = ANY(%s)
            GROUP BY symbol
            ORDER BY symbol
            """,
            (symbols,),
        )

        rows = cur.fetchall()

        if not rows:
            logger.warning("No data found in mkt.etf_1d")
            return

        table_data = []
        for row in rows:
            (
                symbol,
                total,
                vwap_count,
                vwap_pct,
                min_date,
                max_date,
                avg,
                min_v,
                max_v,
            ) = row
            table_data.append(
                [
                    symbol,
                    f"{total:,}",
                    f"{vwap_count:,}",
                    f"{vwap_pct}%",
                    min_date or "NULL",
                    max_date or "NULL",
                    f"${avg}" if avg else "NULL",
                    f"${min_v}" if min_v else "NULL",
                    f"${max_v}" if max_v else "NULL",
                ]
            )

        headers = [
            "Symbol",
            "Total Rows",
            "VWAP Rows",
            "Coverage %",
            "Min Date",
            "Max Date",
            "Avg VWAP",
            "Min VWAP",
            "Max VWAP",
        ]
        if HAS_TABULATE:
            print("\n" + tabulate(table_data, headers=headers, tablefmt="grid"))
        else:
            # Fallback to simple print
            print("\n" + " | ".join(headers))
            print("-" * 120)
            for row in table_data:
                print(" | ".join(str(cell) for cell in row))

        # Overall summary
        total_rows_all = sum(r[1] for r in rows)
        total_vwap_all = sum(r[2] for r in rows)
        overall_pct = (
            100.0 * total_vwap_all / total_rows_all if total_rows_all > 0 else 0
        )

        logger.info(f"\nOVERALL SUMMARY:")
        logger.info(f"  Total ETF rows: {total_rows_all:,}")
        logger.info(f"  Rows with VWAP: {total_vwap_all:,}")
        logger.info(f"  Overall coverage: {overall_pct:.1f}%")

        # Flag symbols with low coverage
        low_coverage = [r for r in rows if (r[3] or 0) < 90]
        if low_coverage:
            logger.warning(f"\n⚠️  Symbols with <90% VWAP coverage:")
            for row in low_coverage:
                logger.warning(f"  {row[0]}: {row[3]}% ({row[2]:,}/{row[1]:,} rows)")

    finally:
        cur.close()
        conn.close()


def validate_vwap_sanity():
    """Validate VWAP sanity (should be close to daily close price)."""
    logger.info("\n" + "=" * 70)
    logger.info("VWAP SANITY CHECKS")
    logger.info("=" * 70)

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Check VWAP vs close price deviation
        cur.execute(
            """
            SELECT
                symbol,
                COUNT(*) as vwap_count,
                ROUND(AVG(ABS(vwap - close) / close * 100)::numeric, 2) as avg_deviation_pct,
                ROUND(MAX(ABS(vwap - close) / close * 100)::numeric, 2) as max_deviation_pct,
                COUNT(*) FILTER (WHERE ABS(vwap - close) / close > 0.05) as outlier_count
            FROM mkt.etf_1d
            WHERE vwap IS NOT NULL AND close IS NOT NULL AND close > 0
            GROUP BY symbol
            ORDER BY avg_deviation_pct DESC
            LIMIT 20
            """
        )

        rows = cur.fetchall()

        if rows:
            table_data = []
            for symbol, count, avg_dev, max_dev, outliers in rows:
                table_data.append(
                    [
                        symbol,
                        f"{count:,}",
                        f"{avg_dev}%",
                        f"{max_dev}%",
                        outliers,
                    ]
                )

            headers = [
                "Symbol",
                "VWAP Rows",
                "Avg Dev %",
                "Max Dev %",
                "Outliers (>5%)",
            ]
            if HAS_TABULATE:
                print("\n" + tabulate(table_data, headers=headers, tablefmt="grid"))
            else:
                print("\n" + " | ".join(headers))
                print("-" * 80)
                for row in table_data:
                    print(" | ".join(str(cell) for cell in row))

            logger.info(
                "\nVWAP typically deviates 0.1-1% from close price (daily average)."
            )
            logger.info("Deviations >5% may indicate data quality issues.")

    finally:
        cur.close()
        conn.close()


def show_sample_data(symbol: str = "FXI", limit: int = 10):
    """Show sample VWAP data for visual inspection."""
    logger.info(f"\n" + "=" * 70)
    logger.info(f"SAMPLE DATA: {symbol} (Latest {limit} rows with VWAP)")
    logger.info("=" * 70)

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                event_date,
                close,
                vwap,
                ROUND((ABS(vwap - close) / close * 100)::numeric, 2) as deviation_pct,
                volume
            FROM mkt.etf_1d
            WHERE symbol = %s AND vwap IS NOT NULL
            ORDER BY event_date DESC
            LIMIT %s
            """,
            (symbol, limit),
        )

        rows = cur.fetchall()

        if rows:
            table_data = []
            for date, close, vwap, dev, vol in rows:
                table_data.append(
                    [
                        date,
                        f"${close:.2f}",
                        f"${vwap:.2f}",
                        f"{dev}%",
                        f"{vol:,}",
                    ]
                )

            headers = ["Date", "Close", "VWAP", "Deviation %", "Volume"]
            if HAS_TABULATE:
                print("\n" + tabulate(table_data, headers=headers, tablefmt="grid"))
            else:
                print("\n" + " | ".join(headers))
                print("-" * 80)
                for row in table_data:
                    print(" | ".join(str(cell) for cell in row))
        else:
            logger.warning(f"No VWAP data found for {symbol}")

    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Validate ETF VWAP Data")
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of symbols to validate (default: all)",
    )
    parser.add_argument(
        "--sample",
        type=str,
        default="FXI",
        help="Symbol to show sample data for (default: FXI)",
    )

    args = parser.parse_args()

    # Parse symbols
    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]

    # Run validations
    validate_vwap_coverage(symbols)
    validate_vwap_sanity()
    show_sample_data(args.sample)

    logger.info("\n" + "=" * 70)
    logger.info("✓ VALIDATION COMPLETE")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
