#!/usr/bin/env python3
"""
Databento FX Options Backfill - Using Explicit Product Codes

Fetches FX options OHLCV from Databento GLBX.MDP3 using the actual
CME product codes (not wildcards).

Writes to: mkt.options_1d

@author Agent3
@date 2026-01-30
"""

import os
import sys
import argparse
import re
import hashlib
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

import databento as db
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
load_dotenv(PROJECT_ROOT / ".env")

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Fix postgres:// to postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DATASET = "GLBX.MDP3"

# =============================================================================
# FX OPTIONS PRODUCT CODES (From Databento Catalog)
# Each product code maps to an underlying FX future
# =============================================================================

FX_OPTIONS_PRODUCTS = {
    # EUR/USD Weekly Options (underlying: 6E)
    "TU2": {"underlying": "6E", "name": "EUR/USD Weekly Tuesday - Week 2"},
    "3EU": {"underlying": "6E", "name": "EUR/USD Weekly Friday - Week 3"},
    "MO2": {"underlying": "6E", "name": "EUR/USD Weekly Monday - Week 2"},
    "MO4": {"underlying": "6E", "name": "EUR/USD Weekly Monday - Week 4"},
    "WE2": {"underlying": "6E", "name": "EUR/USD Weekly Wednesday - Week 2"},

    # JPY/USD Weekly Options (underlying: 6J)
    "MJ1": {"underlying": "6J", "name": "JPY/USD Weekly Monday - Week 1"},
    "5JY": {"underlying": "6J", "name": "JPY/USD Weekly Friday - Week 5"},
    "WJ3": {"underlying": "6J", "name": "JPY/USD Weekly Wednesday - Week 3"},
    "WJ2": {"underlying": "6J", "name": "JPY/USD Weekly Wednesday - Week 2"},
    "3JY": {"underlying": "6J", "name": "JPY/USD Weekly Friday - Week 3"},
    "SJ5": {"underlying": "6J", "name": "JPY/USD Weekly Thursday - Week 5"},

    # GBP/USD Weekly Options (underlying: 6B)
    "MB2": {"underlying": "6B", "name": "GBP/USD Weekly Monday - Week 2"},
    "3BP": {"underlying": "6B", "name": "GBP/USD Weekly Friday - Week 3"},
    "2BP": {"underlying": "6B", "name": "GBP/USD Weekly Friday - Week 2"},
    "SB1": {"underlying": "6B", "name": "GBP/USD Weekly Thursday - Week 1"},
    "TG1": {"underlying": "6B", "name": "GBP/USD Weekly Tuesday - Week 1"},

    # AUD/USD Weekly Options (underlying: 6A)
    "WA1": {"underlying": "6A", "name": "AUD/USD Weekly Wednesday - Week 1"},
    "WA2": {"underlying": "6A", "name": "AUD/USD Weekly Wednesday - Week 2"},
    "SA1": {"underlying": "6A", "name": "AUD/USD Weekly Thursday - Week 1"},
    "MA1": {"underlying": "6A", "name": "AUD/USD Weekly Monday - Week 1"},
    "2AD": {"underlying": "6A", "name": "AUD/USD Weekly Friday - Week 2"},
    "TA2": {"underlying": "6A", "name": "AUD/USD Weekly Tuesday - Week 2"},

    # CAD/USD Weekly Options (underlying: 6C)
    "WD2": {"underlying": "6C", "name": "CAD/USD Weekly Wednesday - Week 2"},
    "WD3": {"underlying": "6C", "name": "CAD/USD Weekly Wednesday - Week 3"},
    "TL1": {"underlying": "6C", "name": "CAD/USD Weekly Tuesday - Week 1"},

    # CHF/USD Weekly Options (underlying: 6S)
    "4SF": {"underlying": "6S", "name": "CHF/USD Weekly Friday - Week 4"},
    "5SF": {"underlying": "6S", "name": "CHF/USD Weekly Friday - Week 5"},
    "2SF": {"underlying": "6S", "name": "CHF/USD Weekly Friday - Week 2"},

    # MXN/USD Monthly (underlying: 6M)
    "6M": {"underlying": "6M", "name": "MXN/USD Monthly Options"},
}

# Agriculture Options (bonus - from screenshots)
AG_OPTIONS_PRODUCTS = {
    # Wheat Weekly Options
    "1WC": {"underlying": "ZW", "name": "Wheat Wednesday Weekly - Week 1"},
    "1WB": {"underlying": "ZW", "name": "Wheat Tuesday Weekly - Week 1"},
    "1WA": {"underlying": "ZW", "name": "Wheat Monday Weekly - Week 1"},
    "1WD": {"underlying": "ZW", "name": "Wheat Thursday Weekly - Week 1"},
    "2WA": {"underlying": "ZW", "name": "Wheat Monday Weekly - Week 2"},

    # Soybean Weekly Options
    "1SD": {"underlying": "ZS", "name": "Soybean Thursday Weekly - Week 1"},
    "1SA": {"underlying": "ZS", "name": "Soybean Monday Weekly - Week 1"},

    # Soybean Oil Weekly Options
    "ZL5": {"underlying": "ZL", "name": "Soybean Oil Friday Weekly - Week 5"},

    # KC HRW Wheat Weekly
    "OE1": {"underlying": "KE", "name": "KC HRW Wheat Friday Weekly - Week 1"},
    "OE5": {"underlying": "KE", "name": "KC HRW Wheat Friday Weekly - Week 5"},

    # Corn Weekly
    "CN5": {"underlying": "ZC", "name": "New Crop Corn Weekly - Week 5"},

    # Other Agriculture
    "LBR": {"underlying": "LBS", "name": "Lumber Options"},
    "GDK": {"underlying": "DC", "name": "Class IV Milk Options"},
}

# Combined for full catalog
ALL_OPTIONS_PRODUCTS = {**FX_OPTIONS_PRODUCTS, **AG_OPTIONS_PRODUCTS}


def get_databento_client() -> db.Historical:
    """Get Databento client."""
    if not DATABENTO_API_KEY:
        raise ValueError("DATABENTO_API_KEY not set in .env")
    return db.Historical(key=DATABENTO_API_KEY)


def get_db_connection():
    """Get database connection."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set in .env")
    return psycopg2.connect(DATABASE_URL)


def compute_row_hash(row: dict) -> str:
    """Compute hash for idempotency."""
    key = f"{row['underlying']}|{row['event_date']}|{row['expiration']}|{row['strike']}|{row['option_type']}"
    return hashlib.md5(key.encode()).hexdigest()


def parse_option_symbol(symbol: str, product_code: str, underlying: str):
    """
    Parse CME option symbol to extract expiration, strike, and type.

    CME Weekly options format varies by product. Common patterns:
    - {PRODUCT}{MONTH}{YEAR}{C/P}{STRIKE}
    - e.g., MJ1H5C007650 = JPY Monday Week 1, March 2025, Call, strike 0.007650

    Args:
        symbol: Raw symbol from Databento
        product_code: The product code (e.g., MJ1)
        underlying: The underlying future (e.g., 6J)

    Returns: (expiration_date, option_type, strike) or None
    """
    if not symbol:
        return None

    # Clean up
    s = symbol.strip().upper().replace(' ', '')

    # Month code mapping
    month_map = {
        'F': 1, 'G': 2, 'H': 3, 'J': 4, 'K': 5, 'M': 6,
        'N': 7, 'Q': 8, 'U': 9, 'V': 10, 'X': 11, 'Z': 12
    }

    # Try pattern: PRODUCT + MONTH + YEAR + TYPE + STRIKE
    # e.g., MJ1H5C007650 or MJ1H25C007650
    pattern = rf'^{re.escape(product_code)}([FGHJKMNQUVXZ])(\d{{1,2}})([CP])(\d+)'
    match = re.match(pattern, s)

    if match:
        month_code = match.group(1)
        year_code = match.group(2)
        opt_type = 'call' if match.group(3) == 'C' else 'put'
        strike_raw = match.group(4)

        # Convert expiry code to date
        month = month_map.get(month_code, 1)
        year_num = int(year_code)
        year = 2000 + year_num if year_num < 50 else 1900 + year_num

        # Approximate expiry as 3rd Friday of month
        # For weekly options, this is approximate
        expiry = date(year, month, 15)

        # Convert strike based on underlying
        # JPY options: divide by 1,000,000 (strikes like 007650 = 0.007650)
        # Most FX: divide by 10,000 (strikes like 12100 = 1.2100)
        if underlying == '6J':
            strike = float(strike_raw) / 1000000
        elif underlying == '6M':  # MXN
            strike = float(strike_raw) / 100000
        else:
            strike = float(strike_raw) / 10000

        return (expiry, opt_type, strike)

    # Fallback: try generic pattern without product code prefix
    generic_match = re.search(r'([FGHJKMNQUVXZ])(\d{1,2})([CP])(\d+)', s)
    if generic_match:
        month_code = generic_match.group(1)
        year_code = generic_match.group(2)
        opt_type = 'call' if generic_match.group(3) == 'C' else 'put'
        strike_raw = generic_match.group(4)

        month = month_map.get(month_code, 1)
        year_num = int(year_code)
        year = 2000 + year_num if year_num < 50 else 1900 + year_num
        expiry = date(year, month, 15)

        if underlying == '6J':
            strike = float(strike_raw) / 1000000
        elif underlying == '6M':
            strike = float(strike_raw) / 100000
        else:
            strike = float(strike_raw) / 10000

        return (expiry, opt_type, strike)

    return None


def fetch_options_ohlcv(
    client: db.Historical,
    product_code: str,
    start_date: date,
    end_date: date
) -> pd.DataFrame:
    """
    Fetch options OHLCV from Databento using explicit product code.

    Args:
        client: Databento Historical client
        product_code: CME product code (e.g., MJ1, 5JY)
        start_date: Start date for fetch
        end_date: End date for fetch

    Returns: DataFrame with OHLCV data
    """
    print(f"    Fetching OHLCV for {product_code} from {start_date} to {end_date}...")

    try:
        # Use the product code as the symbol
        # Databento accepts product codes directly for options
        data = client.timeseries.get_range(
            dataset=DATASET,
            schema="ohlcv-1d",
            symbols=[product_code],
            stype_in="parent",  # Product code is the parent symbol
            start=start_date.isoformat(),
            end=end_date.isoformat(),
        )

        df = data.to_df()
        if df.empty:
            print(f"      No OHLCV data returned")
            return pd.DataFrame()

        df = df.reset_index()
        print(f"      Received {len(df)} records")
        return df

    except Exception as e:
        err_str = str(e)
        if "not found" in err_str.lower() or "invalid" in err_str.lower():
            print(f"      Product {product_code} not found in Databento - skipping")
        else:
            print(f"      ERROR: {e}")
        return pd.DataFrame()


def upsert_options(conn, rows: list) -> int:
    """Upsert options into mkt.options_1d."""
    if not rows:
        return 0

    upsert_query = """
    INSERT INTO mkt.options_1d
        (underlying, event_date, expiration, strike, option_type,
         open, high, low, close, volume, source, row_hash)
    VALUES
        (%(underlying)s, %(event_date)s, %(expiration)s, %(strike)s, %(option_type)s,
         %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, 'databento', %(row_hash)s)
    ON CONFLICT (underlying, event_date, expiration, strike, option_type) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        source = 'databento',
        row_hash = EXCLUDED.row_hash
    """

    cur = conn.cursor()
    execute_batch(cur, upsert_query, rows, page_size=1000)
    conn.commit()
    cur.close()

    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Backfill FX Options from Databento")
    parser.add_argument("--start-date", type=str, default="2020-01-01",
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str,
                        default=(date.today() - timedelta(days=1)).isoformat(),
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--product", type=str,
                        help="Specific product code (e.g., MJ1, 5JY)")
    parser.add_argument("--fx-only", action="store_true",
                        help="Only FX options (skip agriculture)")
    parser.add_argument("--ag-only", action="store_true",
                        help="Only agriculture options (skip FX)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch but don't write to database")
    args = parser.parse_args()

    print("=" * 70)
    print("DATABENTO FX/AG OPTIONS BACKFILL (Explicit Product Codes)")
    print("=" * 70)

    client = get_databento_client()
    conn = get_db_connection() if not args.dry_run else None

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)

    print(f"Date range: {start_date} to {end_date}")

    # Select which products to fetch
    if args.product:
        # Single product
        if args.product in ALL_OPTIONS_PRODUCTS:
            products = {args.product: ALL_OPTIONS_PRODUCTS[args.product]}
        else:
            print(f"ERROR: Unknown product code '{args.product}'")
            print(f"Available FX: {list(FX_OPTIONS_PRODUCTS.keys())}")
            print(f"Available AG: {list(AG_OPTIONS_PRODUCTS.keys())}")
            return
    elif args.fx_only:
        products = FX_OPTIONS_PRODUCTS
    elif args.ag_only:
        products = AG_OPTIONS_PRODUCTS
    else:
        products = ALL_OPTIONS_PRODUCTS

    print(f"Products to fetch: {len(products)}")

    total_upserted = 0
    products_with_data = 0
    products_without_data = 0

    for product_code, config in products.items():
        underlying = config["underlying"]
        name = config["name"]

        print(f"\n[{product_code}] {name} (underlying: {underlying})")

        # Fetch in yearly chunks to avoid timeout
        current_start = start_date
        product_rows = 0

        while current_start <= end_date:
            chunk_end = min(current_start + timedelta(days=365), end_date)

            df = fetch_options_ohlcv(client, product_code, current_start, chunk_end)

            if df.empty:
                current_start = chunk_end + timedelta(days=1)
                continue

            # Process rows
            rows = []
            for _, row in df.iterrows():
                # Get symbol from the dataframe
                symbol = str(row.get("symbol", "") or row.get("raw_symbol", "") or "")

                # Parse the symbol
                parsed = parse_option_symbol(symbol, product_code, underlying)

                if parsed is None:
                    # If parsing fails, use defaults
                    expiry = None
                    opt_type = 'unknown'
                    strike = 0.0
                else:
                    expiry, opt_type, strike = parsed

                # Get event date
                ts_event = row.get("ts_event")
                if pd.isna(ts_event):
                    continue
                event_date = pd.to_datetime(ts_event).date()

                row_data = {
                    "underlying": underlying,
                    "event_date": event_date,
                    "expiration": expiry,
                    "strike": strike,
                    "option_type": opt_type,
                    "open": float(row["open"]) if pd.notna(row.get("open")) else None,
                    "high": float(row["high"]) if pd.notna(row.get("high")) else None,
                    "low": float(row["low"]) if pd.notna(row.get("low")) else None,
                    "close": float(row["close"]) if pd.notna(row.get("close")) else None,
                    "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
                }
                row_data["row_hash"] = compute_row_hash(row_data)
                rows.append(row_data)

            if rows:
                if args.dry_run:
                    print(f"      [DRY RUN] Would upsert {len(rows)} rows")
                    product_rows += len(rows)
                else:
                    upserted = upsert_options(conn, rows)
                    product_rows += upserted
                    print(f"      Upserted {upserted} rows")

            current_start = chunk_end + timedelta(days=1)

        if product_rows > 0:
            products_with_data += 1
            total_upserted += product_rows
            print(f"  Total for {product_code}: {product_rows} rows")
        else:
            products_without_data += 1

    if conn:
        conn.close()

    print("\n" + "=" * 70)
    print(f"COMPLETE")
    print(f"  Products with data: {products_with_data}")
    print(f"  Products without data: {products_without_data}")
    print(f"  Total rows {'processed' if args.dry_run else 'upserted'}: {total_upserted}")
    print("=" * 70)

    if not args.dry_run and total_upserted > 0:
        print("\nVerify with:")
        print("  SELECT underlying, COUNT(*), MIN(event_date), MAX(event_date)")
        print("  FROM mkt.options_1d WHERE source = 'databento'")
        print("  GROUP BY underlying ORDER BY COUNT(*) DESC;")


if __name__ == "__main__":
    main()
