#!/usr/bin/env python3
"""
ZL Price Fetcher - Scheduled Job
Fetches current ZL price from Yahoo and writes to analytics.intraday_prices.
Runs every 15 minutes via cron or Inngest.
"""

import logging
import os
from datetime import datetime, timezone

import psycopg2
import yfinance as yf

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SYMBOL = "ZL"
YAHOO_TICKER = "ZL=F"


def get_previous_close(conn) -> float | None:
    """Get previous daily close for change calculation."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT close FROM raw.market_futures_1d 
            WHERE symbol = 'ZL' 
            ORDER BY event_date DESC 
            LIMIT 1
        """
        )
        row = cur.fetchone()
        return float(row[0]) if row else None


def fetch_zl_price() -> dict | None:
    """Fetch current ZL price from Yahoo."""
    try:
        ticker = yf.Ticker(YAHOO_TICKER)
        info = ticker.info

        price = info.get("regularMarketPrice") or info.get("previousClose")
        if not price:
            logger.error("Could not get price from Yahoo")
            return None

        return {
            "price": float(price),
            "open": float(info.get("regularMarketOpen") or price),
            "high": float(info.get("regularMarketDayHigh") or price),
            "low": float(info.get("regularMarketDayLow") or price),
            "volume": int(info.get("regularMarketVolume") or 0),
            "market_state": info.get("marketState", "UNKNOWN"),
        }
    except Exception as e:
        logger.error(f"Yahoo fetch failed: {e}")
        return None


def upsert_price(conn, data: dict, previous_close: float | None):
    """Insert or update price in analytics.intraday_prices."""
    now = datetime.now(timezone.utc)

    # Calculate change
    change = None
    change_pct = None
    if previous_close:
        change = data["price"] - previous_close
        change_pct = (change / previous_close) * 100

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO analytics.intraday_prices
                (symbol, timestamp, open, high, low, close, volume,
                 previous_close, change, change_percent, day_high, day_low,
                 source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, timestamp)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                previous_close = EXCLUDED.previous_close,
                change = EXCLUDED.change,
                change_percent = EXCLUDED.change_percent,
                day_high = EXCLUDED.day_high,
                day_low = EXCLUDED.day_low,
                created_at = EXCLUDED.created_at
        """,
            (
                SYMBOL,
                now,
                data["open"],
                data["high"],
                data["low"],
                data["price"],
                data["volume"],
                previous_close,
                change,
                change_pct,
                data["high"],
                data["low"],
                "yahoo",
                now,
            ),
        )
    conn.commit()
    logger.info(f"Wrote ZL=${data['price']:.4f} to DB")


def main():
    logger.info("ZL PRICE FETCHER")
    logger.info("=" * 60)

    # Fetch price
    data = fetch_zl_price()
    if not data:
        logger.error("Failed to fetch price")
        return 1

    logger.info(f"Price: ${data['price']:.4f}")
    logger.info(f"Market: {data['market_state']}")

    # Write to DB
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return 1

    conn = psycopg2.connect(database_url)
    try:
        previous_close = get_previous_close(conn)
        if previous_close:
            change_pct = ((data["price"] - previous_close) / previous_close) * 100
            logger.info(f"Change: {change_pct:+.2f}%")

        upsert_price(conn, data, previous_close)
    finally:
        conn.close()

    logger.info("=" * 60)
    logger.info("COMPLETE")
    return 0


if __name__ == "__main__":
    exit(main())
