#!/usr/bin/env python3
"""
Ingest Barchart CSV files into mkt.futures_1d.

These CSV files were downloaded from Barchart Premier and contain historical
futures data back to 1980 for key symbols.

Usage:
    # Ingest all CSV files
    python scripts/ingest_barchart_csv.py --all

    # Ingest specific file
    python scripts/ingest_barchart_csv.py --file "data/Barchart/filename.csv"

    # Dry run
    python scripts/ingest_barchart_csv.py --all --dry-run
"""

import argparse
import csv
import hashlib
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
BARCHART_DIR = PROJECT_ROOT / "data" / "Barchart"


def parse_barchart_date(date_str: str) -> datetime:
    """Parse Barchart date formats."""
    formats = [
        "%m/%d/%Y",  # 01/15/2026
        "%Y-%m-%d",  # 2026-01-15
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    raise ValueError(f"Could not parse date: {date_str}")


def ingest_csv_file(filepath: Path, dry_run: bool = False) -> dict:
    """
    Ingest a single Barchart CSV file.

    Expected CSV format:
    Symbol,Time,Last,Change,...
    ZL,01/02/1980,30.75,0.00,...
    """
    log.info(f"Processing {filepath.name}...")

    stats = {
        "file": filepath.name,
        "rows_read": 0,
        "rows_inserted": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "symbols": set(),
        "date_range": {"earliest": None, "latest": None},
    }

    # Read CSV
    rows_to_insert = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)

        for row in reader:
            stats["rows_read"] += 1

            try:
                # Extract fields (case-insensitive column matching)
                symbol = row.get("Symbol") or row.get("symbol") or row.get("SYMBOL")
                date_str = (
                    row.get("Time")
                    or row.get("Date")
                    or row.get("time")
                    or row.get("date")
                )

                # Price fields
                open_price = row.get("Open") or row.get("open")
                high_price = row.get("High") or row.get("high")
                low_price = row.get("Low") or row.get("low")
                close_price = (
                    row.get("Latest")
                    or row.get("Last")
                    or row.get("Close")
                    or row.get("last")
                    or row.get("close")
                )
                volume = row.get("Volume") or row.get("volume") or "0"

                if not symbol or not date_str:
                    continue

                # Clean symbol (remove futures month codes if present)
                symbol = symbol.strip().upper()
                stats["symbols"].add(symbol)

                # Parse date
                event_date = parse_barchart_date(date_str.strip())

                # Track date range
                if (
                    stats["date_range"]["earliest"] is None
                    or event_date < stats["date_range"]["earliest"]
                ):
                    stats["date_range"]["earliest"] = event_date
                if (
                    stats["date_range"]["latest"] is None
                    or event_date > stats["date_range"]["latest"]
                ):
                    stats["date_range"]["latest"] = event_date

                # Convert prices (handle empty strings)
                try:
                    open_val = float(open_price) if open_price else None
                    high_val = float(high_price) if high_price else None
                    low_val = float(low_price) if low_price else None
                    close_val = float(close_price) if close_price else None
                    volume_val = int(float(volume.replace(",", ""))) if volume else 0
                except (ValueError, AttributeError):
                    log.warning(
                        f"Skipping row with bad price data: {symbol} {date_str}"
                    )
                    stats["rows_skipped"] += 1
                    continue

                # Must have at least close price
                if close_val is None:
                    stats["rows_skipped"] += 1
                    continue

                rows_to_insert.append(
                    {
                        "symbol": symbol,
                        "event_date": event_date,
                        "open": open_val,
                        "high": high_val,
                        "low": low_val,
                        "close": close_val,
                        "volume": volume_val,
                        "source": "barchart_csv",
                    }
                )

            except Exception as e:
                log.warning(f"Error processing row: {e}")
                stats["rows_skipped"] += 1
                continue

    if dry_run:
        log.info(f"  [DRY RUN] Would insert {len(rows_to_insert)} rows")
        return stats

    # Insert to database
    if not rows_to_insert:
        log.warning("  No valid rows to insert")
        return stats

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    for row_data in rows_to_insert:
        try:
            # Upsert (INSERT...ON CONFLICT UPDATE)
            cur.execute(
                """
                INSERT INTO mkt.futures_1d 
                (symbol, event_date, open, high, low, close, volume, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, event_date) 
                DO UPDATE SET
                    open = COALESCE(EXCLUDED.open, mkt.futures_1d.open),
                    high = COALESCE(EXCLUDED.high, mkt.futures_1d.high),
                    low = COALESCE(EXCLUDED.low, mkt.futures_1d.low),
                    close = COALESCE(EXCLUDED.close, mkt.futures_1d.close),
                    volume = COALESCE(EXCLUDED.volume, mkt.futures_1d.volume),
                    source = CASE 
                        WHEN mkt.futures_1d.source = 'yahoo_finance' 
                        THEN 'yahoo_finance'  -- Keep yahoo as primary
                        ELSE EXCLUDED.source 
                    END
                WHERE mkt.futures_1d.close IS NULL OR EXCLUDED.close IS NOT NULL
            """,
                (
                    row_data["symbol"],
                    row_data["event_date"],
                    row_data["open"],
                    row_data["high"],
                    row_data["low"],
                    row_data["close"],
                    row_data["volume"],
                    row_data["source"],
                ),
            )

            if cur.rowcount > 0:
                stats["rows_inserted"] += 1
            else:
                stats["rows_updated"] += 1

        except Exception as e:
            log.warning(
                f"Insert error for {row_data['symbol']} {row_data['event_date']}: {e}"
            )
            stats["rows_skipped"] += 1
            continue

    conn.commit()
    cur.close()
    conn.close()

    log.info(
        f"  Inserted: {stats['rows_inserted']}, Updated: {stats['rows_updated']}, Skipped: {stats['rows_skipped']}"
    )
    log.info(f"  Symbols: {', '.join(sorted(stats['symbols']))}")
    log.info(
        f"  Date range: {stats['date_range']['earliest'].date()} to {stats['date_range']['latest'].date()}"
    )

    return stats


def main():
    parser = argparse.ArgumentParser(description="Ingest Barchart CSV files")
    parser.add_argument(
        "--all", action="store_true", help="Ingest all CSV files in data/Barchart/"
    )
    parser.add_argument("--file", type=str, help="Ingest specific CSV file")
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run - don't insert to DB"
    )
    args = parser.parse_args()

    if not args.all and not args.file:
        parser.print_help()
        sys.exit(1)

    # Collect files to process
    files_to_process = []
    if args.all:
        files_to_process = sorted(BARCHART_DIR.glob("*.csv"))
        log.info(f"Found {len(files_to_process)} CSV files")
    elif args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            log.error(f"File not found: {filepath}")
            sys.exit(1)
        files_to_process = [filepath]

    # Process files
    total_stats = {
        "files_processed": 0,
        "total_rows_read": 0,
        "total_rows_inserted": 0,
        "total_rows_updated": 0,
        "total_rows_skipped": 0,
        "all_symbols": set(),
    }

    for filepath in files_to_process:
        try:
            stats = ingest_csv_file(filepath, dry_run=args.dry_run)
            total_stats["files_processed"] += 1
            total_stats["total_rows_read"] += stats["rows_read"]
            total_stats["total_rows_inserted"] += stats["rows_inserted"]
            total_stats["total_rows_updated"] += stats["rows_updated"]
            total_stats["total_rows_skipped"] += stats["rows_skipped"]
            total_stats["all_symbols"].update(stats["symbols"])
        except Exception as e:
            log.error(f"Failed to process {filepath.name}: {e}")
            continue

    # Summary
    log.info("\n" + "=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    log.info(f"Files processed: {total_stats['files_processed']}")
    log.info(f"Total rows read: {total_stats['total_rows_read']}")
    log.info(f"Total inserted: {total_stats['total_rows_inserted']}")
    log.info(f"Total updated: {total_stats['total_rows_updated']}")
    log.info(f"Total skipped: {total_stats['total_rows_skipped']}")
    log.info(f"Unique symbols: {len(total_stats['all_symbols'])}")
    log.info(f"Symbols: {', '.join(sorted(total_stats['all_symbols']))}")
    log.info("✅ Done!")


if __name__ == "__main__":
    main()
