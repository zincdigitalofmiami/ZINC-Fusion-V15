#!/usr/bin/env python3
"""
Import Barchart Options/Greeks CSV files into mkt.options_greeks_1d

CSV files are in data/Barchart/ with patterns:
- *-volatility-greeks-*.csv (Greeks data: IV, Delta, Gamma, Theta, Vega)
- *-options-*.csv (OHLCV options data)
"""

import os
import re
import csv
import hashlib
from datetime import datetime
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).parent.parent / "data" / "Barchart"


def compute_row_hash(underlying: str, event_date: str, expiration: str, strike: float, option_type: str) -> str:
    """Compute deterministic hash for idempotency."""
    key = f"{underlying}|{event_date}|{expiration}|{strike}|{option_type}"
    return hashlib.sha256(key.encode()).hexdigest()


def parse_filename(filename: str) -> dict:
    """Extract underlying and expiration from filename."""
    # zlh26-volatility-greeks-exp-02_20_26-show-all-01-16-2026.csv
    # $vix-volatility-greeks-exp-2026-01-21-monthly-near-the-money-01-16-2026.csv

    name = filename.lower()
    result = {"underlying": None, "expiration": None, "event_date": None}

    # Extract underlying
    if name.startswith("zlh"):
        result["underlying"] = "ZL"
    elif name.startswith("$vix") or name.startswith("vix"):
        result["underlying"] = "VIX"
    elif name.startswith("cper"):
        result["underlying"] = "CPER"
    elif name.startswith("zsh"):
        result["underlying"] = "ZS"
    elif name.startswith("zmh"):
        result["underlying"] = "ZM"
    elif name.startswith("clh"):
        result["underlying"] = "CL"

    # Extract expiration date
    # Pattern 1: exp-02_20_26 (MM_DD_YY)
    exp_match = re.search(r'exp-(\d{2})_(\d{2})_(\d{2})', name)
    if exp_match:
        month, day, year = exp_match.groups()
        result["expiration"] = f"20{year}-{month}-{day}"

    # Pattern 2: exp-2026-01-21 (YYYY-MM-DD)
    exp_match2 = re.search(r'exp-(\d{4})-(\d{2})-(\d{2})', name)
    if exp_match2:
        year, month, day = exp_match2.groups()
        result["expiration"] = f"{year}-{month}-{day}"

    # Extract event date from end of filename: 01-16-2026.csv
    date_match = re.search(r'(\d{2})-(\d{2})-(\d{4})\.csv$', name)
    if date_match:
        month, day, year = date_match.groups()
        result["event_date"] = f"{year}-{month}-{day}"

    return result


def import_greeks_csv(filepath: Path, conn) -> dict:
    """Import a volatility-greeks CSV file."""
    filename = filepath.name
    meta = parse_filename(filename)

    if not meta["underlying"] or not meta["expiration"] or not meta["event_date"]:
        print(f"  SKIP: Could not parse filename: {filename}")
        return {"inserted": 0, "skipped": 0, "errors": 1}

    underlying = meta["underlying"]
    expiration = meta["expiration"]
    event_date = meta["event_date"]

    inserted = 0
    skipped = 0
    errors = 0

    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        cur = conn.cursor()

        for row in reader:
            try:
                strike = float(row.get("Strike", 0))
                option_type = "C" if row.get("Type", "").lower() == "call" else "P"

                # Parse IV (may have % sign)
                iv_str = row.get("IV", "0").replace("%", "").strip()
                iv = float(iv_str) / 100 if iv_str else None

                # Parse IV Skew
                skew_str = row.get("IV Skew", "0").replace("%", "").strip()
                iv_skew = float(skew_str) / 100 if skew_str else None

                last_price = float(row.get("Latest", 0)) if row.get("Latest") else None
                delta = float(row.get("Delta", 0)) if row.get("Delta") else None
                gamma = float(row.get("Gamma", 0)) if row.get("Gamma") else None
                theta = float(row.get("Theta", 0)) if row.get("Theta") else None
                vega = float(row.get("Vega", 0)) if row.get("Vega") else None

                row_hash = compute_row_hash(underlying, event_date, expiration, strike, option_type)

                # Check if exists
                cur.execute(
                    "SELECT 1 FROM mkt.options_greeks_1d WHERE row_hash = %s LIMIT 1",
                    (row_hash,)
                )
                if cur.fetchone():
                    skipped += 1
                    continue

                # Assign specialist tags based on underlying
                tags = []
                if underlying in ("ZL", "ZS", "ZM"):
                    tags = ["crush", "volatility"]
                elif underlying == "CL":
                    tags = ["energy", "volatility"]
                elif underlying == "VIX":
                    tags = ["volatility"]

                cur.execute(
                    """INSERT INTO mkt.options_greeks_1d
                       (underlying, event_date, expiration, strike, option_type,
                        last_price, implied_volatility, delta, gamma, theta, vega,
                        iv_skew, source, row_hash, specialist_tags)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (underlying, event_date, expiration, strike, option_type,
                     last_price, iv, delta, gamma, theta, vega,
                     iv_skew, "barchart_csv", row_hash, tags)
                )
                inserted += 1

            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"  ERROR: {e} in row {row}")

        conn.commit()
        cur.close()

    return {"inserted": inserted, "skipped": skipped, "errors": errors}


def import_options_ohlcv_csv(filepath: Path, conn) -> dict:
    """Import an options OHLCV CSV file into mkt.options_1d."""
    filename = filepath.name
    meta = parse_filename(filename)

    if not meta["underlying"] or not meta["expiration"] or not meta["event_date"]:
        print(f"  SKIP: Could not parse filename: {filename}")
        return {"inserted": 0, "skipped": 0, "errors": 1}

    underlying = meta["underlying"]
    expiration = meta["expiration"]
    event_date = meta["event_date"]

    inserted = 0
    skipped = 0
    errors = 0

    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        cur = conn.cursor()

        for row in reader:
            try:
                # Strike may have C/P suffix like "48.000C"
                strike_raw = row.get("Strike", "0")
                option_type = "C" if "C" in strike_raw.upper() or row.get("Type", "").lower() == "call" else "P"
                strike = float(re.sub(r'[CP]', '', strike_raw, flags=re.IGNORECASE))

                open_price = float(row.get("Open", 0)) if row.get("Open") else None
                high_price = float(row.get("High", 0)) if row.get("High") else None
                low_price = float(row.get("Low", 0)) if row.get("Low") else None
                close_price = float(row.get("Latest", 0)) if row.get("Latest") else None
                volume = int(float(row.get("Volume", 0))) if row.get("Volume") else None
                open_interest = int(float(row.get("Open Int", 0))) if row.get("Open Int") else None

                row_hash = compute_row_hash(underlying, event_date, expiration, strike, option_type)

                # Check if exists
                cur.execute(
                    "SELECT 1 FROM mkt.options_1d WHERE row_hash = %s LIMIT 1",
                    (row_hash,)
                )
                if cur.fetchone():
                    skipped += 1
                    continue

                cur.execute(
                    """INSERT INTO mkt.options_1d
                       (underlying, event_date, expiration, strike, option_type,
                        open, high, low, close, volume, open_interest, source, row_hash)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (underlying, event_date, expiration, strike, option_type,
                     open_price, high_price, low_price, close_price, volume, open_interest,
                     "barchart_csv", row_hash)
                )
                inserted += 1

            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"  ERROR: {e} in row {row}")

        conn.commit()
        cur.close()

    return {"inserted": inserted, "skipped": skipped, "errors": errors}


def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    total_inserted = 0
    total_skipped = 0
    total_errors = 0

    # Process Greeks CSVs
    print("\n=== Importing Greeks CSVs ===")
    greeks_files = list(DATA_DIR.glob("*greeks*.csv"))
    print(f"Found {len(greeks_files)} greeks files")

    for filepath in sorted(greeks_files):
        print(f"\nProcessing: {filepath.name}")
        result = import_greeks_csv(filepath, conn)
        print(f"  Inserted: {result['inserted']}, Skipped: {result['skipped']}, Errors: {result['errors']}")
        total_inserted += result["inserted"]
        total_skipped += result["skipped"]
        total_errors += result["errors"]

    # Process Options OHLCV CSVs
    print("\n=== Importing Options OHLCV CSVs ===")
    options_files = [f for f in DATA_DIR.glob("*options*.csv") if "greeks" not in f.name.lower()]
    print(f"Found {len(options_files)} options OHLCV files")

    for filepath in sorted(options_files):
        print(f"\nProcessing: {filepath.name}")
        result = import_options_ohlcv_csv(filepath, conn)
        print(f"  Inserted: {result['inserted']}, Skipped: {result['skipped']}, Errors: {result['errors']}")
        total_inserted += result["inserted"]
        total_skipped += result["skipped"]
        total_errors += result["errors"]

    conn.close()

    print(f"\n=== TOTAL ===")
    print(f"Inserted: {total_inserted}")
    print(f"Skipped: {total_skipped}")
    print(f"Errors: {total_errors}")


if __name__ == "__main__":
    main()
