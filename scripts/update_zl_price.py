#!/usr/bin/env python3
"""
ZL Price Ticker - Lightweight 15-minute price updates
======================================================
Fetches only ZL (soybean oil) futures price for chart updates.
Designed to run every 15 minutes via Railway cron.

Usage:
    python scripts/update_zl_price.py
    python scripts/update_zl_price.py --dry-run
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from typing import Optional

import requests
import psycopg2
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if not POLYGON_API_KEY:
    logger.error("POLYGON_API_KEY not set")
    sys.exit(1)

if not DATABASE_URL:
    logger.error("DATABASE_URL not set")
    sys.exit(1)


def get_zl_price() -> Optional[dict]:
    """Fetch current ZL futures price from Polygon."""
    url = "https://api.polygon.io/v2/aggs/ticker/ZL/prev"
    params = {"apiKey": POLYGON_API_KEY}

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("results"):
            result = data["results"][0]
            return {
                "symbol": "ZL",
                "open": result.get("o"),
                "high": result.get("h"),
                "low": result.get("l"),
                "close": result.get("c"),
                "volume": result.get("v"),
                "vwap": result.get("vw"),
                "timestamp": result.get("t"),
            }
    except Exception as e:
        logger.error(f"API error: {e}")

    return None


def update_price(price_data: dict, dry_run: bool = False) -> bool:
    """Update ZL price in Prisma database."""
    if dry_run:
        logger.info(f"[DRY RUN] Would update ZL: ${price_data['close']:.4f}")
        return True

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        today = datetime.now().date()

        # Upsert into raw_market_futures
        cur.execute("""
            INSERT INTO raw_market_futures
                (symbol, as_of_date, open, high, low, close, volume, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (symbol, as_of_date) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                created_at = NOW()
        """, (
            price_data["symbol"],
            today,
            price_data["open"],
            price_data["high"],
            price_data["low"],
            price_data["close"],
            price_data["volume"],
        ))

        conn.commit()
        cur.close()
        conn.close()

        logger.info(f"Updated ZL: ${price_data['close']:.4f} (OHLC: {price_data['open']:.2f}/{price_data['high']:.2f}/{price_data['low']:.2f}/{price_data['close']:.2f})")
        return True

    except Exception as e:
        logger.error(f"Database error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Update ZL price")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    args = parser.parse_args()

    logger.info("="*50)
    logger.info("ZL PRICE UPDATE")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info("="*50)

    price = get_zl_price()

    if price:
        success = update_price(price, dry_run=args.dry_run)
        if success:
            logger.info("Price update complete")
        else:
            logger.error("Price update failed")
            sys.exit(1)
    else:
        logger.error("Could not fetch ZL price")
        sys.exit(1)


if __name__ == "__main__":
    main()
