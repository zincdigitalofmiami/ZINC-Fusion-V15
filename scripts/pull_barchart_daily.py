#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Barchart Daily Price Pull

Fetches latest futures prices from Barchart for symbols not on Yahoo.
Run daily after market close or manually when needed.

Usage:
    python scripts/pull_barchart_daily.py
    python scripts/pull_barchart_daily.py --symbols RS,CC,KC

Note: CPO (Crude Palm Oil) is NOT available on Barchart - it's traded on
Bursa Malaysia and requires Trading Economics API or similar paid source.
"""

import argparse
import os
import sys
from datetime import datetime

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Default symbols to pull (Barchart continuous contract notation)
DEFAULT_SYMBOLS = {
    "RS*0": "RS",   # Canola (not on Yahoo)
    "CC*0": "CC",   # Cocoa
    "KC*0": "KC",   # Coffee
    "SB*0": "SB",   # Sugar
    "CT*0": "CT",   # Cotton
    "OJ*0": "OJ",   # Orange Juice
    "LBR*0": "LBR", # Lumber
}


def get_barchart_session():
    """Bootstrap a Barchart session with CSRF token."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    })

    # Fetch seed page to get cookies
    seed_res = session.get("https://www.barchart.com/futures/quotes/RS*0/overview")
    if not seed_res.ok:
        raise Exception(f"Barchart seed page failed: {seed_res.status_code}")

    xsrf = session.cookies.get("XSRF-TOKEN")
    if not xsrf:
        raise Exception("No XSRF token found in Barchart response")

    return session, xsrf


def fetch_quotes(session, xsrf, symbols):
    """Fetch quotes from Barchart API."""
    res = session.get(
        "https://www.barchart.com/proxies/core-api/v1/quotes/get",
        params={
            "symbols": ",".join(symbols),
            "fields": "symbol,lastPrice,open,high,low,volume,tradeTime,previousClose",
            "raw": "1"
        },
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "X-XSRF-TOKEN": requests.utils.unquote(xsrf),
            "Accept": "application/json"
        }
    )

    if not res.ok:
        raise Exception(f"Barchart API failed: {res.status_code}")

    return res.json().get("data", [])


def parse_num(val):
    """Parse Barchart number format (handles commas, 's' suffix)."""
    if not val:
        return 0
    s = str(val).replace("s", "").replace(",", "").strip()
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return 0


def main():
    parser = argparse.ArgumentParser(description="Pull Barchart daily prices")
    parser.add_argument("--symbols", help="Comma-separated symbols (default: all)")
    parser.add_argument("--date", help="Override event date (YYYY-MM-DD)")
    args = parser.parse_args()

    print("=" * 60)
    print("ZINC-FUSION-V15: BARCHART DAILY PRICE PULL")
    print("=" * 60)
    print(f"Time: {datetime.now()}")
    print()

    # Parse symbols
    if args.symbols:
        selected = [s.strip().upper() for s in args.symbols.split(",")]
        symbols = {f"{s}*0": s for s in selected if s}
    else:
        symbols = DEFAULT_SYMBOLS

    print(f"Symbols: {list(symbols.values())}")
    print()

    # Get session
    print("Initializing Barchart session...")
    session, xsrf = get_barchart_session()
    print("  OK")

    # Fetch quotes
    print("Fetching quotes...")
    quotes = fetch_quotes(session, xsrf, list(symbols.keys()))
    print(f"  Got {len(quotes)} quotes")
    print()

    # Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    event_date = args.date or datetime.now().strftime("%Y-%m-%d")
    print(f"Event date: {event_date}")
    print()

    # Process quotes
    print("Updating database:")
    updated = 0
    for q in quotes:
        bc_symbol = q.get("symbol", "")

        # Find matching DB symbol
        db_symbol = None
        for bc_key, db_key in symbols.items():
            if bc_symbol.startswith(db_key):
                db_symbol = db_key
                break

        if not db_symbol:
            continue

        price = parse_num(q.get("lastPrice"))
        if price == 0:
            print(f"  {db_symbol}: No price, skipping")
            continue

        open_price = parse_num(q.get("open")) or price
        high_price = parse_num(q.get("high")) or price
        low_price = parse_num(q.get("low")) or price
        volume = int(parse_num(q.get("volume")))

        cur.execute("""
            INSERT INTO mkt.futures_1d
            (event_date, symbol, open, high, low, close, volume, source, ingested_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'barchart_api', NOW())
            ON CONFLICT (event_date, symbol) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                close = EXCLUDED.close, volume = EXCLUDED.volume,
                source = EXCLUDED.source, ingested_at = NOW()
        """, (event_date, db_symbol, open_price, high_price, low_price, price, volume))

        print(f"  {db_symbol}: {price}")
        updated += 1

    conn.commit()
    print()
    print(f"Updated {updated} symbols")

    # Show status
    print()
    print("Current data status:")
    for sym in symbols.values():
        cur.execute("SELECT MAX(event_date) FROM mkt.futures_1d WHERE symbol = %s", (sym,))
        row = cur.fetchone()
        print(f"  {sym}: last={row[0]}")

    conn.close()
    print()
    print("=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
