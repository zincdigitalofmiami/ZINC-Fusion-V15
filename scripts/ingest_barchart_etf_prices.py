#!/usr/bin/env python3
"""
Barchart ETF/Stock Price CSV Ingestion
======================================

Ingests daily price data from Barchart CSV downloads.

Expected CSV format:
    Symbol,Time,Open,High,Low,Latest,Change,%Change,Volume

Tables Written:
    mkt.etf_1d: Daily ETF/stock price data

Usage:
    python scripts/ingest_barchart_etf_prices.py data/Barchart/daily-historical*.csv
    python scripts/ingest_barchart_etf_prices.py --dry-run data/Barchart/*.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

import psycopg2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")


def parse_price(price_str: str) -> Optional[float]:
    """Parse price from string."""
    if not price_str or price_str in ["-", "N/A", "--", ""]:
        return None
    try:
        clean = price_str.replace(",", "").strip()
        return float(clean)
    except ValueError:
        return None


def parse_volume(vol_str: str) -> Optional[int]:
    """Parse volume from string."""
    if not vol_str or vol_str in ["-", "N/A", "--", ""]:
        return None
    try:
        clean = vol_str.replace(",", "").strip()
        return int(float(clean))
    except ValueError:
        return None


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date from YYYY-MM-DD format."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def determine_specialist_tags(symbol: str) -> List[str]:
    """Determine specialist tags based on symbol."""
    symbol = symbol.upper() if symbol else ""
    tags = []

    # Map symbols to specialists
    if symbol in ["SPY", "QQQ", "IWM", "DIA"]:
        tags.extend(["fed", "volatility"])
    elif symbol in ["XLE", "XOP", "USO", "UNG", "OIH"]:
        tags.extend(["energy", "biofuel"])
    elif symbol in ["FXI", "KWEB", "MCHI", "ASHR"]:
        tags.append("china")
    elif symbol in ["DBA", "CORN", "WEAT", "SOYB"]:
        tags.extend(["crush", "substitutes"])
    elif symbol in ["TAN", "ICLN", "PBW", "QCLN", "LIT"]:
        tags.append("biofuel")
    elif symbol in ["GLD", "SLV", "IAU"]:
        tags.append("fx")
    elif symbol in ["TLT", "IEF", "SHY", "BND"]:
        tags.append("fed")
    elif symbol in ["XLF", "KRE", "KBE"]:
        tags.append("fed")
    elif symbol in ["XME", "PICK"]:
        tags.append("substitutes")
    elif symbol in ["EEM", "VWO", "EFA"]:
        tags.extend(["fx", "china"])
    elif symbol == "UUP":
        tags.append("fx")
    elif symbol == "VXX" or symbol.startswith("VIX"):
        tags.append("volatility")
    elif symbol.endswith(".BI"):  # Baltic indices
        # BDI = dry bulk (China demand), BDTI/BCTI = tankers (energy)
        if symbol in ["BDI.BI", "BCI.BI", "BSI.BI", "BPI.BI", "BHSI.BI"]:
            tags.extend(["china", "substitutes"])  # Dry bulk = commodity shipping
        elif symbol in ["BDTI.BI", "BCTI.BI"]:
            tags.append("energy")  # Tanker rates
        elif symbol in ["BLNG.BI", "BLPG.BI"]:
            tags.extend(["energy", "china"])  # LNG/LPG shipping
        else:
            tags.append("china")  # Default for Baltic

    return tags if tags else ["macro"]


def validate_table_exists(conn) -> None:
    """Validate that mkt.etf_1d exists (Prisma-managed table).

    Raises:
        SystemExit: If table does not exist. Run Prisma migrations first.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_schema = 'mkt' AND table_name = 'etf_1d'
        )
    """
    )
    exists = cur.fetchone()[0]
    cur.close()

    if not exists:
        raise SystemExit(
            "FATAL: mkt.etf_1d table does not exist.\n"
            "This table must be created via Prisma migrations.\n"
            "Run: npx prisma migrate dev"
        )
    logger.info("Validated mkt.etf_1d table exists")


def extract_symbol_from_filename(filename: str) -> Optional[str]:
    """Extract symbol from filename for files without Symbol column.

    Examples:
        bdibi_daily_historical-data-01-16-2026.csv -> BDI.BI
        bctibi_daily_historical-data-01-16-2026.csv -> BCTI.BI
    """
    import re

    # Match pattern like bdibi_, bctibi_, bdtibi_
    match = re.match(r"^([a-z]+)bi_", filename.lower())
    if match:
        base = match.group(1).upper()
        return f"{base}.BI"  # Baltic index format
    return None


def parse_csv_file(filepath: Path) -> List[Dict]:
    """Parse a Barchart price CSV file."""
    records = []

    logger.info(f"Parsing {filepath.name}")

    # Check if this is a single-symbol file (no Symbol column)
    filename_symbol = extract_symbol_from_filename(filepath.name)

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Skip footer rows
            if "Downloaded from" in str(row.get("Symbol", "") or row.get("Time", "")):
                continue

            # Use filename symbol if no Symbol column, otherwise use column
            symbol = (
                row.get("Symbol", "").strip().upper()
                if "Symbol" in row and row.get("Symbol")
                else filename_symbol
            )
            if not symbol:
                continue

            event_date = parse_date(row.get("Time", ""))
            if not event_date:
                continue

            close_price = parse_price(row.get("Latest", ""))
            if close_price is None:
                continue

            specialist_tags = determine_specialist_tags(symbol)

            record = {
                "symbol": symbol,
                "event_date": event_date,
                "open": parse_price(row.get("Open", "")),
                "high": parse_price(row.get("High", "")),
                "low": parse_price(row.get("Low", "")),
                "close": close_price,
                "volume": parse_volume(row.get("Volume", "")),
                "specialist_tags": specialist_tags,
            }

            # Generate row hash
            hash_input = f"{symbol}|{event_date}"
            record["row_hash"] = hashlib.sha256(hash_input.encode()).hexdigest()

            records.append(record)

    # Count unique symbols
    symbols = set(r["symbol"] for r in records)
    logger.info(
        f"  Parsed {len(records)} records for {len(symbols)} symbols: {sorted(symbols)}"
    )

    return records


def write_to_db(records: List[Dict], dry_run: bool = False) -> int:
    """Write price records to database using batch inserts."""
    if not records:
        return 0

    if dry_run:
        symbols = set(r["symbol"] for r in records)
        logger.info(
            f"[DRY RUN] Would insert {len(records)} records for {len(symbols)} symbols"
        )
        return len(records)

    conn = psycopg2.connect(DATABASE_URL)
    validate_table_exists(conn)
    cur = conn.cursor()

    # Prepare data for batch insert
    from psycopg2.extras import execute_values

    values = [
        (
            rec["symbol"],
            rec["event_date"],
            rec["open"],
            rec["high"],
            rec["low"],
            rec["close"],
            rec["volume"],
            rec["row_hash"],
            rec["specialist_tags"],
        )
        for rec in records
    ]

    # Batch insert with ON CONFLICT
    execute_values(
        cur,
        """
        INSERT INTO mkt.etf_1d (
            symbol, event_date, open, high, low, close, volume,
            row_hash, specialist_tags
        ) VALUES %s
        ON CONFLICT (symbol, event_date)
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume
        """,
        values,
        page_size=1000,
    )

    conn.commit()
    cur.close()
    conn.close()

    return len(records)


def main():
    parser = argparse.ArgumentParser(description="Ingest Barchart ETF/stock price CSVs")
    parser.add_argument("files", nargs="+", help="CSV files to ingest")
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't write to database"
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("BARCHART ETF/STOCK PRICE INGESTION")
    logger.info("=" * 60)

    total_records = 0
    total_files = 0
    all_symbols = set()

    for filepath in args.files:
        path = Path(filepath)

        if not path.exists():
            logger.warning(f"File not found: {filepath}")
            continue

        # Skip options files
        if "volatility-greeks" in path.name.lower() or "options" in path.name.lower():
            logger.info(f"Skipping options file: {path.name}")
            continue

        records = parse_csv_file(path)

        if records:
            symbols = set(r["symbol"] for r in records)
            all_symbols.update(symbols)

            count = write_to_db(records, dry_run=args.dry_run)
            total_records += count
            total_files += 1
            logger.info(f"  Wrote {count} records")

    logger.info("=" * 60)
    logger.info(f"COMPLETE: {total_records} records from {total_files} files")
    logger.info(f"Symbols: {sorted(all_symbols)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
