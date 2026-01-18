#!/usr/bin/env python3
"""
Barchart Options Greeks CSV Ingestion
=====================================

Ingests options volatility & greeks data from Barchart CSV downloads.

Expected CSV format (from Barchart "Volatility & Greeks" download):
    Strike,Type,Latest,IV,Delta,Gamma,Theta,Vega,IV Skew,Time

Tables Written:
    mkt.options_greeks_1d: Options Greeks data by strike

Usage:
    # Ingest single file
    python scripts/ingest_barchart_options.py data/Barchart/zlh26-volatility-greeks*.csv

    # Ingest all options files
    python scripts/ingest_barchart_options.py data/Barchart/*volatility-greeks*.csv

    # Dry run
    python scripts/ingest_barchart_options.py --dry-run data/Barchart/*.csv
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
from typing import Optional, List, Dict, Any

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")


def parse_iv(iv_str: str) -> Optional[float]:
    """Parse implied volatility from string (e.g., '25.70%' or '0.00%')."""
    if not iv_str or iv_str in ["-", "N/A", "--", ""]:
        return None
    try:
        clean = iv_str.replace("%", "").strip()
        val = float(clean)
        if val == 0:
            return None  # 0% IV is meaningless
        return val / 100  # Convert to decimal
    except ValueError:
        return None


def parse_greek(greek_str: str) -> Optional[float]:
    """Parse Greek value from string."""
    if not greek_str or greek_str in ["-", "N/A", "--", ""]:
        return None
    try:
        val = float(greek_str.strip())
        # Filter out nonsense values (scientific notation extremes)
        if abs(val) < 1e-10 or abs(val) > 1e10:
            return None
        return val
    except ValueError:
        return None


def parse_price(price_str: str) -> Optional[float]:
    """Parse price from string."""
    if not price_str or price_str in ["-", "N/A", "--", ""]:
        return None
    try:
        clean = price_str.replace(",", "").strip()
        return float(clean)
    except ValueError:
        return None


def parse_strike(strike_str: str) -> Optional[float]:
    """Parse strike price from string."""
    if not strike_str:
        return None
    try:
        clean = strike_str.replace(",", "").strip()
        return float(clean)
    except ValueError:
        return None


def extract_contract_info(filename: str) -> Dict[str, Any]:
    """
    Extract contract info from filename.

    Examples:
        zlh26-volatility-greeks-exp-02_20_26-show-all-01-16-2026.csv
        spy-volatility-greeks-exp-01_17_26-show-all-01-16-2026.csv
        $vix-volatility-greeks-exp-2026-02-18-monthly-near-the-money-01-16-2026.csv
    """
    info = {
        "underlying": None,
        "expiration": None,
        "download_date": None,
    }

    # Handle $vix special case
    if filename.startswith("$vix"):
        info["underlying"] = "VIX"
    else:
        # Extract underlying symbol (first part before dash)
        match = re.match(r"^([a-zA-Z0-9]+)-", filename)
        if match:
            info["underlying"] = match.group(1).upper()

    # Extract expiration date - try YYYY-MM-DD format first (VIX style)
    exp_match = re.search(r"exp-(\d{4})-(\d{2})-(\d{2})", filename)
    if exp_match:
        year, month, day = exp_match.groups()
        try:
            info["expiration"] = datetime(int(year), int(month), int(day)).date()
        except ValueError:
            pass
    else:
        # Try MM_DD_YY format (ZL style)
        exp_match = re.search(r"exp-(\d{2})_(\d{2})_(\d{2})", filename)
        if exp_match:
            month, day, year = exp_match.groups()
            year_full = 2000 + int(year)
            try:
                info["expiration"] = datetime(year_full, int(month), int(day)).date()
            except ValueError:
                pass

    # Extract download date (last date in filename MM-DD-YYYY)
    date_match = re.search(r"(\d{2})-(\d{2})-(\d{4})\.csv$", filename)
    if date_match:
        month, day, year = date_match.groups()
        try:
            info["download_date"] = datetime(int(year), int(month), int(day)).date()
        except ValueError:
            pass

    return info


def determine_specialist_tags(underlying: str) -> List[str]:
    """Determine specialist tags based on underlying."""
    underlying = underlying.upper() if underlying else ""

    tags = ["volatility"]  # All options data tagged for volatility specialist

    # Map underlyings to specialists
    if underlying.startswith("ZL"):
        tags.extend(["crush", "biofuel"])
    elif underlying.startswith("ZS"):
        tags.append("crush")
    elif underlying.startswith("ZM"):
        tags.append("crush")
    elif underlying in ["SPY", "QQQ", "IWM", "ES", "NQ"]:
        tags.append("fed")  # Macro/equity correlation
    elif underlying in ["USO", "XLE", "XOP", "CL"]:
        tags.append("energy")
    elif underlying in ["FXI", "KWEB", "MCHI"]:
        tags.append("china")
    elif underlying in ["DBA", "CORN", "WEAT", "SOYB"]:
        tags.extend(["crush", "substitutes"])
    elif underlying in ["TAN", "ICLN", "PBW", "QCLN"]:
        tags.append("biofuel")
    elif underlying in ["GLD", "SLV", "GC", "SI"]:
        tags.append("fx")  # Precious metals correlate with currency
    elif underlying in ["VIX", "VXX", "UVXY"]:
        tags.append("volatility")
    elif underlying in ["TLT", "ZB", "ZN"]:
        tags.append("fed")
    elif underlying == "DX":
        tags.append("fx")

    return list(set(tags))


def validate_table_exists(conn) -> None:
    """Validate that mkt.options_greeks_1d exists (Prisma-managed table).
    
    Raises:
        SystemExit: If table does not exist. Run Prisma migrations first.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_schema = 'mkt' AND table_name = 'options_greeks_1d'
        )
    """)
    exists = cur.fetchone()[0]
    cur.close()
    
    if not exists:
        raise SystemExit(
            "FATAL: mkt.options_greeks_1d table does not exist.\n"
            "This table must be created via Prisma migrations.\n"
            "Run: npx prisma migrate dev"
        )
    logger.info("Validated mkt.options_greeks_1d table exists")


def parse_csv_file(filepath: Path) -> List[Dict]:
    """Parse a Barchart options Greeks CSV file."""
    records = []

    contract_info = extract_contract_info(filepath.name)
    underlying = contract_info["underlying"]
    expiration = contract_info["expiration"]
    event_date = contract_info["download_date"] or datetime.now().date()

    if not underlying:
        logger.warning(f"Could not extract underlying from filename: {filepath.name}")
        return []

    specialist_tags = determine_specialist_tags(underlying)

    logger.info(f"Parsing {filepath.name}")
    logger.info(f"  Underlying: {underlying}, Expiration: {expiration}, Date: {event_date}")

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Skip footer rows
            if "Downloaded from" in str(row.get("Strike", "")):
                continue

            strike = parse_strike(row.get("Strike", ""))
            if strike is None:
                continue

            option_type = row.get("Type", "").strip().upper()
            if option_type not in ["CALL", "PUT"]:
                continue

            iv = parse_iv(row.get("IV", ""))

            # Skip rows with no meaningful IV
            if iv is None:
                continue

            record = {
                "underlying": underlying,
                "event_date": event_date,
                "expiration": expiration,
                "strike": strike,
                "option_type": option_type,
                "last_price": parse_price(row.get("Latest", "")),
                "implied_volatility": iv,
                "delta": parse_greek(row.get("Delta", "")),
                "gamma": parse_greek(row.get("Gamma", "")),
                "theta": parse_greek(row.get("Theta", "")),
                "vega": parse_greek(row.get("Vega", "")),
                "iv_skew": parse_iv(row.get("IV Skew", "")),
                "specialist_tags": specialist_tags,
            }

            # Generate row hash
            hash_input = f"{underlying}|{event_date}|{expiration}|{strike}|{option_type}"
            record["row_hash"] = hashlib.sha256(hash_input.encode()).hexdigest()

            records.append(record)

    logger.info(f"  Parsed {len(records)} valid options records")
    return records


def write_to_db(records: List[Dict], dry_run: bool = False) -> int:
    """Write options records to database."""
    if not records:
        return 0

    if dry_run:
        logger.info(f"[DRY RUN] Would insert {len(records)} records")
        # Show sample
        for r in records[:3]:
            logger.info(f"  {r['underlying']} {r['strike']} {r['option_type']} IV={r['implied_volatility']:.2%}")
        return len(records)

    conn = psycopg2.connect(DATABASE_URL)
    validate_table_exists(conn)
    cur = conn.cursor()

    inserted = 0
    for rec in records:
        try:
            cur.execute("""
                INSERT INTO mkt.options_greeks_1d (
                    underlying, event_date, expiration, strike, option_type,
                    last_price, implied_volatility, delta, gamma, theta, vega,
                    iv_skew, row_hash, specialist_tags
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (underlying, event_date, expiration, strike, option_type)
                DO UPDATE SET
                    last_price = EXCLUDED.last_price,
                    implied_volatility = EXCLUDED.implied_volatility,
                    delta = EXCLUDED.delta,
                    gamma = EXCLUDED.gamma,
                    theta = EXCLUDED.theta,
                    vega = EXCLUDED.vega,
                    iv_skew = EXCLUDED.iv_skew
            """, (
                rec["underlying"],
                rec["event_date"],
                rec["expiration"],
                rec["strike"],
                rec["option_type"],
                rec["last_price"],
                rec["implied_volatility"],
                rec["delta"],
                rec["gamma"],
                rec["theta"],
                rec["vega"],
                rec["iv_skew"],
                rec["row_hash"],
                rec["specialist_tags"],
            ))
            inserted += 1
        except Exception as e:
            logger.warning(f"Insert error: {e}")
            continue

    conn.commit()
    cur.close()
    conn.close()

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Ingest Barchart options Greeks CSVs")
    parser.add_argument("files", nargs="+", help="CSV files to ingest")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("BARCHART OPTIONS GREEKS INGESTION")
    logger.info("=" * 60)

    total_records = 0
    total_files = 0

    for filepath in args.files:
        path = Path(filepath)

        if not path.exists():
            logger.warning(f"File not found: {filepath}")
            continue

        # Only process volatility-greeks files
        if "volatility-greeks" not in path.name.lower() and "options" not in path.name.lower():
            logger.info(f"Skipping non-options file: {path.name}")
            continue

        records = parse_csv_file(path)

        if records:
            count = write_to_db(records, dry_run=args.dry_run)
            total_records += count
            total_files += 1
            logger.info(f"  Wrote {count} records")

    logger.info("=" * 60)
    logger.info(f"COMPLETE: {total_records} records from {total_files} files")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
