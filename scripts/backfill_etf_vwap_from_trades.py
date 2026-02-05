#!/usr/bin/env python3
"""
ETF Daily VWAP Calculation from Databento Trades

Calculates true VWAP (Volume Weighted Average Price) from intraday trade data.
VWAP Formula: sum(price * volume) / sum(volume) per trading day

Databento Schema: trades
- Provides all trade executions with price and size
- Dataset: ARCX.PILLAR (NYSE Arca), XNAS.ITCH (Nasdaq)

This is the CORRECT implementation method per Databento documentation.
Statistics schema does not include VWAP for ETF datasets.

Usage:
    # Backfill all ETFs (full history)
    python scripts/backfill_etf_vwap_from_trades.py

    # Backfill specific symbols
    python scripts/backfill_etf_vwap_from_trades.py --symbols FXI,GLD,SPY

    # Backfill specific date range
    python scripts/backfill_etf_vwap_from_trades.py --start 2024-01-01 --end 2024-12-31

    # Dry run (no database writes)
    python scripts/backfill_etf_vwap_from_trades.py --dry-run

@author: Claude (ZINC-FUSION-V15)
@date: 2026-02-03
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict

import psycopg2
from psycopg2.extras import execute_values
import requests
from requests.auth import HTTPBasicAuth

# Ray for parallel processing (optional)
try:
    import ray

    HAS_RAY = True
except ImportError:
    HAS_RAY = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

DATABENTO_API_KEY = os.environ.get("DATABENTO_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")
DATABENTO_BASE_URL = "https://hist.databento.com/v0/timeseries.get_range"

# ETF Configuration (symbol -> dataset mapping)
ETF_CONFIG = {
    # China Complex
    "FXI": "ARCX.PILLAR",
    "KWEB": "ARCX.PILLAR",
    "MCHI": "ARCX.PILLAR",
    # Precious Metals
    "GLD": "ARCX.PILLAR",
    "SLV": "ARCX.PILLAR",
    # Shipping
    "BDRY": "ARCX.PILLAR",
    "SBLK": "XNAS.ITCH",
    # Energy
    "XLE": "ARCX.PILLAR",
    "XOP": "ARCX.PILLAR",
    "USO": "ARCX.PILLAR",
    "UNG": "ARCX.PILLAR",
    "OIH": "ARCX.PILLAR",
    # Treasuries
    "TLT": "XNAS.ITCH",
    "IEF": "XNAS.ITCH",
    # Broad Market
    "SPY": "ARCX.PILLAR",
    "QQQ": "XNAS.ITCH",
    # Ag Commodities
    "DBA": "ARCX.PILLAR",
    "SOYB": "ARCX.PILLAR",
    "CORN": "ARCX.PILLAR",
    "WEAT": "ARCX.PILLAR",
    # Dollar
    "UUP": "ARCX.PILLAR",
    # Green Energy
    "ICLN": "XNAS.ITCH",
    "TAN": "ARCX.PILLAR",
    "LIT": "ARCX.PILLAR",
}


@dataclass
class DailyVwap:
    """Daily VWAP calculation result."""

    symbol: str
    event_date: datetime
    vwap: float
    trade_count: int
    total_volume: int


# =============================================================================
# DATABENTO API
# =============================================================================


def fetch_databento_trades_csv(
    dataset: str,
    symbol: str,
    start: datetime,
    end: datetime,
) -> str:
    """Fetch trades data from Databento Historical API."""
    if not DATABENTO_API_KEY:
        raise ValueError("DATABENTO_API_KEY not set")

    params = {
        "dataset": dataset,
        "schema": "trades",  # Trade executions
        "symbols": symbol,
        "stype_in": "raw_symbol",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "encoding": "csv",
        "pretty_ts": "true",
        "pretty_px": "true",
    }

    response = requests.post(
        DATABENTO_BASE_URL,
        data=params,
        auth=HTTPBasicAuth(DATABENTO_API_KEY, ""),
        timeout=300,  # Trades can be large files
    )

    if response.status_code != 200:
        raise Exception(f"Databento API error {response.status_code}: {response.text}")

    return response.text


def calculate_vwap_from_trades_csv(csv_text: str, symbol: str) -> List[DailyVwap]:
    """
    Calculate daily VWAP from trades CSV.

    VWAP Formula: sum(price * size) / sum(size) per trading day

    Expected CSV columns:
    - ts_event: Timestamp (nanoseconds or ISO8601)
    - price: Trade price (scaled by 1e-9 for fixed-point)
    - size: Trade size (shares)
    """
    lines = [
        l.strip() for l in csv_text.split("\n") if l.strip() and not l.startswith("#")
    ]

    if len(lines) < 2:
        return []

    header = lines[0].split(",")
    idx_ts = header.index("ts_event") if "ts_event" in header else -1
    idx_price = header.index("price") if "price" in header else -1
    idx_size = header.index("size") if "size" in header else -1

    if idx_ts == -1 or idx_price == -1 or idx_size == -1:
        logger.warning(f"Missing required columns in trades CSV: {header}")
        return []

    # Accumulate trades by date
    daily_data = defaultdict(lambda: {"price_volume": 0.0, "volume": 0, "count": 0})

    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < len(header):
            continue

        # Parse timestamp
        ts_str = parts[idx_ts].strip()
        if not ts_str:
            continue

        try:
            if ts_str.isdigit():
                # Nanosecond timestamp
                ts_ms = int(ts_str) // 1_000_000
                ts = datetime.utcfromtimestamp(ts_ms / 1000.0)
            else:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception as e:
            logger.debug(f"Failed to parse timestamp {ts_str}: {e}")
            continue

        date_str = ts.strftime("%Y-%m-%d")

        # Parse price (fixed-point scaled by 1e-9)
        try:
            price_raw = float(parts[idx_price])
            price = (
                price_raw * 1e-9 if price_raw > 1e6 else price_raw
            )  # Handle both formats
        except ValueError:
            continue

        # Parse size
        try:
            size = int(parts[idx_size])
        except ValueError:
            continue

        if price <= 0 or size <= 0:
            continue

        # Accumulate VWAP components
        daily_data[date_str]["price_volume"] += price * size
        daily_data[date_str]["volume"] += size
        daily_data[date_str]["count"] += 1

    # Calculate VWAP for each day
    results = []
    for date_str, data in daily_data.items():
        if data["volume"] > 0:
            vwap = data["price_volume"] / data["volume"]
            event_date = datetime.strptime(date_str, "%Y-%m-%d")
            results.append(
                DailyVwap(
                    symbol=symbol,
                    event_date=event_date,
                    vwap=vwap,
                    trade_count=data["count"],
                    total_volume=data["volume"],
                )
            )

    results.sort(key=lambda x: x.event_date)
    return results


# =============================================================================
# DATABASE
# =============================================================================


def get_db_connection():
    """Get database connection."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)


def get_vwap_date_range(symbol: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Get existing VWAP date coverage for a symbol.
    Returns (min_date, max_date) where VWAP is NOT NULL.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT MIN(event_date), MAX(event_date)
            FROM mkt.etf_1d
            WHERE symbol = %s AND vwap IS NOT NULL
            """,
            (symbol,),
        )
        result = cur.fetchone()
        return (result[0], result[1]) if result else (None, None)
    finally:
        cur.close()
        conn.close()


def update_vwap_values(vwap_data: List[DailyVwap], dry_run: bool = False) -> int:
    """
    Update VWAP values in mkt.etf_1d.
    Only updates existing rows (does not insert new rows).
    """
    if not vwap_data:
        return 0

    if dry_run:
        logger.info(
            f"[DRY RUN] Would update {len(vwap_data)} VWAP values for {vwap_data[0].symbol}"
        )
        return len(vwap_data)

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Prepare update data
        values = [(v.vwap, v.symbol, v.event_date.date()) for v in vwap_data]

        # Batch update using unnest pattern (more efficient than individual UPDATEs)
        cur.execute(
            """
            UPDATE mkt.etf_1d AS e
            SET vwap = v.vwap
            FROM (
                SELECT * FROM UNNEST(
                    %s::float[],
                    %s::varchar[],
                    %s::date[]
                ) AS t(vwap, symbol, event_date)
            ) AS v
            WHERE e.symbol = v.symbol AND e.event_date = v.event_date
            """,
            (
                [v.vwap for v in vwap_data],
                [v.symbol for v in vwap_data],
                [v.event_date.date() for v in vwap_data],
            ),
        )

        updated = cur.rowcount
        conn.commit()
        return updated

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


# =============================================================================
# BACKFILL LOGIC
# =============================================================================


def backfill_symbol_vwap(
    symbol: str,
    start: datetime,
    end: datetime,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Backfill VWAP for a single ETF symbol.

    Returns:
        Dict with status, rows updated, date range, etc.
    """
    if symbol not in ETF_CONFIG:
        return {
            "symbol": symbol,
            "status": "error",
            "error": f"Unknown symbol: {symbol}",
        }

    dataset = ETF_CONFIG[symbol]
    logger.info(
        f"Fetching trades for {symbol} from {dataset} ({start.date()} to {end.date()})..."
    )

    try:
        # Fetch trades data
        trades_csv = fetch_databento_trades_csv(dataset, symbol, start, end)

        # Calculate daily VWAP
        vwap_data = calculate_vwap_from_trades_csv(trades_csv, symbol)

        if not vwap_data:
            logger.warning(f"No trades data returned for {symbol}")
            return {"symbol": symbol, "status": "no_data", "rows": 0}

        # Update database
        updated = update_vwap_values(vwap_data, dry_run=dry_run)

        date_range = (
            f"{vwap_data[0].event_date.date()} to {vwap_data[-1].event_date.date()}"
        )
        total_trades = sum(v.trade_count for v in vwap_data)
        avg_vwap = sum(v.vwap for v in vwap_data) / len(vwap_data)

        logger.info(
            f"✓ {symbol}: {updated} days updated, "
            f"{total_trades:,} trades, avg VWAP ${avg_vwap:.2f}"
        )

        return {
            "symbol": symbol,
            "status": "success",
            "rows": updated,
            "date_range": date_range,
            "total_trades": total_trades,
            "avg_vwap": avg_vwap,
        }

    except Exception as e:
        logger.error(f"✗ {symbol}: {str(e)}")
        return {"symbol": symbol, "status": "error", "error": str(e)}


# Ray-accelerated backfill
if HAS_RAY:

    @ray.remote
    def backfill_symbol_vwap_ray(
        symbol: str,
        start: datetime,
        end: datetime,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        return backfill_symbol_vwap(symbol, start, end, dry_run)


def run_backfill(
    symbols: Optional[List[str]] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    dry_run: bool = False,
    use_ray: bool = True,
) -> List[Dict[str, Any]]:
    """Run ETF VWAP backfill."""
    # Default to all symbols
    if symbols is None:
        symbols = list(ETF_CONFIG.keys())

    # Default date range: last 5 years (trades data is large)
    if end is None:
        end = datetime.now()
    if start is None:
        # Start from earliest ETF data in DB or 5 years ago
        start = end - timedelta(days=365 * 5)

    logger.info(f"=" * 60)
    logger.info(f"ETF VWAP Backfill (from Trades)")
    logger.info(f"Symbols: {len(symbols)}")
    logger.info(f"Date range: {start.date()} to {end.date()}")
    logger.info(f"Dry run: {dry_run}")
    logger.info(f"=" * 60)

    results = []

    if use_ray and HAS_RAY:
        try:
            ray.init(address="auto", ignore_reinit_error=True)
            logger.info(f"Ray cluster: {ray.cluster_resources()}")

            futures = [
                backfill_symbol_vwap_ray.remote(sym, start, end, dry_run)
                for sym in symbols
            ]
            results = ray.get(futures)
        except Exception as e:
            logger.warning(f"Ray failed, falling back to serial: {e}")
            use_ray = False

    if not use_ray or not HAS_RAY:
        # Serial processing
        for sym in symbols:
            result = backfill_symbol_vwap(sym, start, end, dry_run)
            results.append(result)

    # Summary
    success = sum(1 for r in results if r.get("status") == "success")
    errors = sum(1 for r in results if r.get("status") == "error")
    no_data = sum(1 for r in results if r.get("status") == "no_data")
    total_rows = sum(r.get("rows", 0) for r in results)
    total_trades = sum(r.get("total_trades", 0) for r in results)

    logger.info(f"=" * 60)
    logger.info(f"BACKFILL COMPLETE")
    logger.info(f"Success: {success}/{len(symbols)}")
    logger.info(f"Errors: {errors}")
    logger.info(f"No data: {no_data}")
    logger.info(f"Total VWAP rows updated: {total_rows:,}")
    logger.info(f"Total trades processed: {total_trades:,}")
    logger.info(f"=" * 60)

    # Print errors
    for r in results:
        if r.get("status") == "error":
            logger.error(f"  {r['symbol']}: {r.get('error')}")

    return results


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="ETF VWAP Backfill from Databento Trades"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of symbols (default: all)",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD, default: 5 years ago)",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to database",
    )
    parser.add_argument(
        "--no-ray",
        action="store_true",
        help="Disable Ray parallel processing",
    )

    args = parser.parse_args()

    # Parse symbols
    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]

    # Parse dates
    start = None
    end = None
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d")
    if args.end:
        end = datetime.strptime(args.end, "%Y-%m-%d")

    # Run backfill
    run_backfill(
        symbols=symbols,
        start=start,
        end=end,
        dry_run=args.dry_run,
        use_ray=not args.no_ray,
    )


if __name__ == "__main__":
    main()
