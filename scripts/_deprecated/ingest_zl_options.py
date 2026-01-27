#!/usr/bin/env python3
"""
ZL (Soybean Oil) Futures Options Ingestion from Barchart
========================================================

Scrapes ZL futures options data from Barchart Premier using saved session.

Data extracted:
- Strike price, expiration, put/call type
- Last price, bid, ask
- Volume, open interest
- Implied volatility, Delta, Gamma, Theta, Vega

Tables Written:
- raw.options_futures_1d: Contract-level daily data

Usage:
    # First ensure you have a Barchart session
    python scripts/scrape_barchart_news.py --login

    # Ingest ZL options for all available expirations
    python scripts/ingest_zl_options.py --all

    # Ingest specific month
    python scripts/ingest_zl_options.py --month ZLH26

    # Dry run
    python scripts/ingest_zl_options.py --all --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
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

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
COOKIES_PATH = PROJECT_ROOT / ".barchart_cookies.json"
DATABASE_URL = os.getenv("DATABASE_URL")

# ZL contract months (standard soybean oil futures months)
# F=Jan, G=Feb, H=Mar, J=Apr, K=May, M=Jun, N=Jul, Q=Aug, U=Sep, V=Oct, X=Nov, Z=Dec
ZL_MONTHS = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]


def get_available_months() -> List[str]:
    """Get ZL contract months for current + next year."""
    now = datetime.now()
    current_year = now.year % 100  # 26 for 2026
    next_year = (current_year + 1) % 100

    months = []
    for year in [current_year, next_year]:
        for month_code in ZL_MONTHS:
            months.append(f"ZL{month_code}{year}")

    return months


def parse_expiration_date(contract: str) -> Optional[datetime]:
    """Parse expiration date from contract code like ZLH26."""
    match = re.match(r"ZL([A-Z])(\d{2})", contract)
    if not match:
        return None

    month_code = match.group(1)
    year = int(match.group(2)) + 2000

    month_map = {
        "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
        "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12
    }

    month = month_map.get(month_code, 1)

    # Options typically expire mid-month
    return datetime(year, month, 15)


def parse_strike_price(strike_str: str) -> Optional[float]:
    """Parse strike price from string."""
    if not strike_str:
        return None
    try:
        clean = strike_str.replace(",", "").strip()
        return float(clean)
    except ValueError:
        return None


def parse_price(price_str: str) -> Optional[float]:
    """Parse price from string, handling various formats."""
    if not price_str or price_str in ["-", "N/A", "--"]:
        return None
    try:
        clean = price_str.replace(",", "").replace("s", "").strip()
        return float(clean)
    except ValueError:
        return None


def parse_volume(vol_str: str) -> Optional[int]:
    """Parse volume from string."""
    if not vol_str or vol_str in ["-", "N/A", "--"]:
        return None
    try:
        clean = vol_str.replace(",", "").strip()
        return int(float(clean))
    except ValueError:
        return None


def parse_iv(iv_str: str) -> Optional[float]:
    """Parse implied volatility from string (e.g., '25.70%')."""
    if not iv_str or iv_str in ["-", "N/A", "--"]:
        return None
    try:
        clean = iv_str.replace("%", "").strip()
        return float(clean) / 100  # Convert to decimal
    except ValueError:
        return None


def parse_greek(greek_str: str) -> Optional[float]:
    """Parse Greek value from string."""
    if not greek_str or greek_str in ["-", "N/A", "--"]:
        return None
    try:
        return float(greek_str.strip())
    except ValueError:
        return None


def scrape_options_page(page, contract: str, option_type: str = "all") -> List[Dict]:
    """
    Scrape options data from a Barchart options page.

    Args:
        page: Playwright page object
        contract: Contract code like ZLH26
        option_type: 'calls', 'puts', or 'all'
    """
    options_data = []

    # Build URL
    base_url = f"https://www.barchart.com/futures/quotes/{contract}/options"
    params = "?view=stacked&moneyness=allStrikes"  # Get all strikes

    url = f"{base_url}{params}"
    logger.info(f"Fetching: {url}")

    try:
        page.goto(url, timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(3)  # Wait for JS rendering

        # Check if we're logged in
        if "login" in page.url.lower():
            logger.error("Session expired! Run scrape_barchart_news.py --login")
            return []

        # Try to extract data from the options table
        # Method 1: Look for data-ng-init or similar Angular data attributes
        tables = page.query_selector_all("table.bc-table-scrollable-inner, .options-chain table, table")

        for table in tables:
            rows = table.query_selector_all("tbody tr")

            for row in rows:
                cells = row.query_selector_all("td")

                if len(cells) < 8:
                    continue

                # The options table typically has:
                # Strike | Last | Chg | Bid | Ask | Vol | OI | IV
                # for both calls and puts

                try:
                    # Try to identify row type from classes or data attributes
                    row_class = row.get_attribute("class") or ""

                    # Extract cell values
                    cell_texts = [c.inner_text().strip() for c in cells]

                    # Skip header rows
                    if any(x in cell_texts[0].lower() for x in ["strike", "calls", "puts"]):
                        continue

                    # Parse based on table structure
                    # Stacked view: Strike | Call Last | Call Bid | Call Ask | Call Vol | Call OI | Call IV | Put Last | ...

                    if len(cell_texts) >= 14:
                        # Stacked view with calls and puts
                        strike = parse_strike_price(cell_texts[0])

                        if strike:
                            # Call option
                            call_data = {
                                "strike": strike,
                                "option_type": "call",
                                "last": parse_price(cell_texts[1]),
                                "bid": parse_price(cell_texts[2]),
                                "ask": parse_price(cell_texts[3]),
                                "volume": parse_volume(cell_texts[4]),
                                "open_interest": parse_volume(cell_texts[5]),
                                "iv": parse_iv(cell_texts[6]),
                            }
                            options_data.append(call_data)

                            # Put option
                            put_data = {
                                "strike": strike,
                                "option_type": "put",
                                "last": parse_price(cell_texts[7]),
                                "bid": parse_price(cell_texts[8]),
                                "ask": parse_price(cell_texts[9]),
                                "volume": parse_volume(cell_texts[10]),
                                "open_interest": parse_volume(cell_texts[11]),
                                "iv": parse_iv(cell_texts[12]),
                            }
                            options_data.append(put_data)

                except Exception as e:
                    logger.debug(f"Error parsing row: {e}")
                    continue

        # Method 2: Try extracting from data attributes (Angular/Vue data binding)
        if not options_data:
            # Look for data-feed-items or similar
            data_element = page.query_selector("[data-template-data], [data-ng-init], [ng-init]")
            if data_element:
                data_attr = data_element.get_attribute("data-template-data") or \
                           data_element.get_attribute("data-ng-init") or \
                           data_element.get_attribute("ng-init")

                if data_attr:
                    # Try to parse JSON from the attribute
                    try:
                        # Extract JSON from ng-init format
                        json_match = re.search(r'\{.*\}', data_attr)
                        if json_match:
                            data = json.loads(json_match.group())
                            logger.info(f"Found data in attribute: {len(data)} items")
                    except json.JSONDecodeError:
                        pass

        # Method 3: Check for download button and get CSV
        download_btn = page.query_selector("a[href*='download'], button:has-text('Download')")
        if download_btn and not options_data:
            logger.info("Found download button - manual CSV download recommended")

        logger.info(f"Scraped {len(options_data)} options records for {contract}")

    except Exception as e:
        logger.error(f"Error scraping {contract}: {e}")

    return options_data


def scrape_options_via_download(page, contract: str) -> List[Dict]:
    """
    Alternative method: Trigger CSV download and parse it.
    """
    # Navigate to options overview with all strikes
    url = f"https://www.barchart.com/futures/quotes/{contract}/options?view=stacked&moneyness=allStrikes"

    try:
        page.goto(url, timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(3)

        # Check login
        if "login" in page.url.lower():
            logger.error("Session expired!")
            return []

        # Look for download functionality
        # Barchart typically has a download icon/button

        # Try clicking the download button
        download_selectors = [
            "a.download-csv",
            "button[data-action='download']",
            ".toolbar-download",
            "[title*='Download']",
            "[aria-label*='Download']",
        ]

        for selector in download_selectors:
            btn = page.query_selector(selector)
            if btn:
                logger.info(f"Found download button: {selector}")
                # Note: Would need to handle download in headless mode
                break

        return []

    except Exception as e:
        logger.error(f"Error in download method: {e}")
        return []


def write_options_to_db(records: List[Dict], contract: str, event_date: datetime, dry_run: bool = False) -> int:
    """Write options data to raw.options_futures_1d."""
    if not records:
        return 0

    if dry_run:
        logger.info(f"[DRY RUN] Would insert {len(records)} records for {contract}")
        return len(records)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    expiration = parse_expiration_date(contract)
    inserted = 0

    for rec in records:
        try:
            # Create symbol: ZLH26 C4500 or ZLH26 P4500
            strike_str = f"{int(rec['strike'])}" if rec['strike'] else "0"
            option_type_char = "C" if rec['option_type'] == "call" else "P"
            symbol = f"{contract} {option_type_char}{strike_str}"

            # Generate row hash
            hash_input = f"{symbol}|{event_date.date()}"
            row_hash = hashlib.md5(hash_input.encode()).hexdigest()

            cur.execute("""
                INSERT INTO raw.options_futures_1d (
                    symbol, event_date, strike, option_type, expiration,
                    close, volume, open_interest, source, row_hash,
                    specialist_tags
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, event_date)
                DO UPDATE SET
                    close = COALESCE(EXCLUDED.close, raw.options_futures_1d.close),
                    volume = COALESCE(EXCLUDED.volume, raw.options_futures_1d.volume),
                    open_interest = COALESCE(EXCLUDED.open_interest, raw.options_futures_1d.open_interest)
            """, (
                symbol,
                event_date.date(),
                rec['strike'],
                rec['option_type'].upper(),
                expiration,
                rec.get('last'),
                rec.get('volume'),
                rec.get('open_interest'),
                'barchart_options',
                row_hash,
                ['volatility']  # Tag for volatility specialist
            ))
            inserted += 1

        except Exception as e:
            logger.warning(f"Insert error for {contract}: {e}")
            continue

    conn.commit()
    cur.close()
    conn.close()

    return inserted


def main():
    raise SystemExit(
        "Barchart options ingestion is disabled in production. Existing data is retained."
    )
    parser = argparse.ArgumentParser(description="Ingest ZL options from Barchart")
    parser.add_argument("--all", action="store_true", help="Ingest all available months")
    parser.add_argument("--month", type=str, help="Specific month code (e.g., ZLH26)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless")
    args = parser.parse_args()

    if not args.all and not args.month:
        parser.print_help()
        sys.exit(1)

    # Check for saved session
    if not COOKIES_PATH.exists():
        logger.error("No Barchart session found! Run: python scripts/scrape_barchart_news.py --login")
        sys.exit(1)

    # Determine contracts to process
    if args.month:
        contracts = [args.month.upper()]
    else:
        contracts = get_available_months()[:6]  # Focus on nearest 6 months

    logger.info("=" * 60)
    logger.info("ZL OPTIONS INGESTION FROM BARCHART")
    logger.info("=" * 60)
    logger.info(f"Contracts: {contracts}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 60)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

        # Load cookies
        with open(COOKIES_PATH, "r") as f:
            cookies = json.load(f)
        context.add_cookies(cookies)

        page = context.new_page()

        # Test session
        page.goto("https://www.barchart.com")
        time.sleep(2)

        event_date = datetime.now()
        total_records = 0

        for contract in contracts:
            logger.info(f"\n{'='*40}")
            logger.info(f"Processing {contract}")
            logger.info(f"{'='*40}")

            options_data = scrape_options_page(page, contract)

            if options_data:
                count = write_options_to_db(
                    options_data,
                    contract,
                    event_date,
                    dry_run=args.dry_run
                )
                total_records += count
                logger.info(f"  Wrote {count} records for {contract}")
            else:
                logger.warning(f"  No data scraped for {contract}")

            # Rate limiting
            time.sleep(2)

        browser.close()

    logger.info(f"\n{'='*60}")
    logger.info(f"COMPLETE: {total_records} total records")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
