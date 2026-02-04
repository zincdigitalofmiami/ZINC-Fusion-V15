#!/usr/bin/env python3
"""
Databento ETF Historical Backfill (10 Years)

Fetches complete OHLCV + Statistics data from Databento for all ETFs.
Uses Ray for parallel processing across your 22-core cluster.

Datasets:
- ARCX.PILLAR (NYSE Arca) - Most ETFs
- XNAS.ITCH (Nasdaq) - QQQ, TLT, IEF, ICLN, SBLK

ETF Categories for ZL Forecasting:
1. China Complex (FXI, KWEB, MCHI) - Demand signals
2. Precious Metals (GLD, SLV) - Vol/inflation regime
3. Shipping (BDRY, SBLK) - Physical flow signals
4. Energy (XLE, XOP, USO, UNG, OIH) - Biodiesel economics
5. Treasuries (TLT, IEF) - Carry trade cost
6. Broad Market (SPY, QQQ) - Risk regime
7. Ag Commodities (DBA, SOYB, CORN, WEAT) - Sector momentum
8. Dollar (UUP) - FX regime
9. Green Energy (ICLN, TAN, LIT) - Biofuel policy

Usage:
    # Backfill all ETFs (10 years)
    python scripts/backfill_etf_databento.py

    # Backfill specific symbols only
    python scripts/backfill_etf_databento.py --symbols FXI,GLD,SLV,BDRY

    # Backfill specific date range
    python scripts/backfill_etf_databento.py --start 2020-01-01 --end 2024-12-31

    # Dry run (no database writes)
    python scripts/backfill_etf_databento.py --dry-run

@author: Claude (ZINC-FUSION-V15)
@date: 2026-02-03
"""

import os
import sys
import argparse
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
import requests
from requests.auth import HTTPBasicAuth

# Try Ray for parallel processing
try:
    import ray
    HAS_RAY = True
except ImportError:
    HAS_RAY = False
    print("Ray not available - using ThreadPoolExecutor fallback")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

DATABENTO_API_KEY = os.environ.get("DATABENTO_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")
DATABENTO_BASE_URL = "https://hist.databento.com/v0/timeseries.get_range"

# ETF Configuration: symbol -> (dataset, name, specialist_tags)
ETF_CONFIG = {
    # China Complex - CRITICAL
    "FXI": ("ARCX.PILLAR", "iShares China Large-Cap", ["china", "tariff", "trump_effect"]),
    "KWEB": ("ARCX.PILLAR", "KraneShares China Internet", ["china"]),
    "MCHI": ("ARCX.PILLAR", "iShares MSCI China", ["china"]),

    # Precious Metals - Vol regime
    "GLD": ("ARCX.PILLAR", "SPDR Gold", ["volatility", "fed"]),
    "SLV": ("ARCX.PILLAR", "iShares Silver", ["volatility", "energy"]),

    # Shipping - Physical flows
    "BDRY": ("ARCX.PILLAR", "Breakwave Dry Bulk Shipping", ["china", "crush"]),
    "SBLK": ("XNAS.ITCH", "Star Bulk Carriers", ["china", "crush"]),

    # Energy - Biodiesel economics
    "XLE": ("ARCX.PILLAR", "Energy Select Sector SPDR", ["energy", "biofuel"]),
    "XOP": ("ARCX.PILLAR", "SPDR Oil & Gas Exploration", ["energy"]),
    "USO": ("ARCX.PILLAR", "United States Oil Fund", ["energy", "biofuel"]),
    "UNG": ("ARCX.PILLAR", "United States Natural Gas", ["energy", "crush"]),
    "OIH": ("ARCX.PILLAR", "VanEck Oil Services", ["energy"]),

    # Treasuries - Carry trade
    "TLT": ("XNAS.ITCH", "iShares 20+ Year Treasury", ["fed", "volatility"]),
    "IEF": ("XNAS.ITCH", "iShares 7-10 Year Treasury", ["fed"]),

    # Broad Market - Regime
    "SPY": ("ARCX.PILLAR", "SPDR S&P 500", ["volatility", "fed"]),
    "QQQ": ("XNAS.ITCH", "Invesco QQQ (Nasdaq 100)", ["volatility"]),

    # Ag Commodities - Cross-validation
    "DBA": ("ARCX.PILLAR", "Invesco DB Agriculture", ["crush", "substitutes"]),
    "SOYB": ("ARCX.PILLAR", "Teucrium Soybean", ["crush"]),
    "CORN": ("ARCX.PILLAR", "Teucrium Corn", ["crush", "biofuel"]),
    "WEAT": ("ARCX.PILLAR", "Teucrium Wheat", ["crush", "substitutes"]),

    # Dollar - FX regime
    "UUP": ("ARCX.PILLAR", "Invesco DB US Dollar", ["fx", "china"]),

    # Green Energy - Biofuel policy
    "ICLN": ("XNAS.ITCH", "iShares Global Clean Energy", ["biofuel", "energy"]),
    "TAN": ("ARCX.PILLAR", "Invesco Solar", ["biofuel", "energy"]),
    "LIT": ("ARCX.PILLAR", "Global X Lithium & Battery", ["biofuel", "energy"]),
}

@dataclass
class EtfBar:
    """Single ETF OHLCV bar with optional statistics."""
    symbol: str
    event_date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    opening_price: Optional[float] = None
    closing_price: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    indicative_open: Optional[float] = None
    indicative_close: Optional[float] = None
    vwap: Optional[float] = None
    specialist_tags: List[str] = None

    def row_hash(self) -> str:
        """Compute idempotency hash."""
        date_str = self.event_date.strftime("%Y-%m-%d")
        hash_input = f"{self.symbol}|{date_str}|{self.open}|{self.high}|{self.low}|{self.close}|{self.volume}"
        return hashlib.sha256(hash_input.encode()).hexdigest()


# =============================================================================
# DATABENTO API
# =============================================================================

def fetch_databento_csv(
    dataset: str,
    schema: str,
    symbol: str,
    start: datetime,
    end: datetime,
) -> str:
    """Fetch data from Databento Historical API."""
    if not DATABENTO_API_KEY:
        raise ValueError("DATABENTO_API_KEY not set")

    params = {
        "dataset": dataset,
        "schema": schema,
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
        timeout=120,
    )

    if response.status_code != 200:
        raise Exception(f"Databento API error {response.status_code}: {response.text}")

    return response.text


def parse_ohlcv_csv(csv_text: str) -> pd.DataFrame:
    """Parse Databento OHLCV CSV into DataFrame."""
    lines = [l.strip() for l in csv_text.split("\n") if l.strip() and not l.startswith("#")]
    if len(lines) < 2:
        return pd.DataFrame()

    header = lines[0].split(",")
    data = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) >= len(header):
            data.append(dict(zip(header, parts)))

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    # Parse timestamp
    if "ts_event" in df.columns:
        def parse_ts(val):
            if pd.isna(val):
                return pd.NaT
            val = str(val).strip()
            if val.isdigit():
                # Nanosecond timestamp
                return pd.Timestamp(int(val) // 1_000_000, unit="ms", tz="UTC")
            return pd.Timestamp(val)

        df["ts_event"] = df["ts_event"].apply(parse_ts)
        df = df.dropna(subset=["ts_event"])

    # Parse numeric columns
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def parse_statistics_csv(csv_text: str) -> Dict[str, Dict[str, float]]:
    """Parse Databento statistics CSV into dict by date."""
    lines = [l.strip() for l in csv_text.split("\n") if l.strip() and not l.startswith("#")]
    if len(lines) < 2:
        return {}

    header = lines[0].split(",")
    idx_ts = header.index("ts_event") if "ts_event" in header else -1
    idx_stat = header.index("stat_type") if "stat_type" in header else -1
    idx_price = header.index("price") if "price" in header else -1

    if idx_ts == -1 or idx_stat == -1:
        return {}

    # ETF stat type mapping
    STAT_MAP = {
        1: "opening_price",
        2: "indicative_open",
        3: "closing_price",
        4: "session_low",
        5: "session_high",
        11: "indicative_close",
        13: "vwap",
    }

    result = {}
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < len(header):
            continue

        ts_str = parts[idx_ts].strip()
        if not ts_str:
            continue

        try:
            if ts_str.isdigit():
                ts = pd.Timestamp(int(ts_str) // 1_000_000, unit="ms", tz="UTC")
            else:
                ts = pd.Timestamp(ts_str)
            date_str = ts.strftime("%Y-%m-%d")
        except Exception:
            continue

        stat_type = int(parts[idx_stat]) if parts[idx_stat].isdigit() else 0
        if stat_type not in STAT_MAP:
            continue

        field = STAT_MAP[stat_type]

        if idx_price >= 0:
            try:
                price = float(parts[idx_price]) * 1e-9  # Fixed-point scaling
                if price > 0:
                    if date_str not in result:
                        result[date_str] = {}
                    result[date_str][field] = price
            except ValueError:
                pass

    return result


def fetch_etf_data(
    symbol: str,
    dataset: str,
    start: datetime,
    end: datetime,
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    """Fetch OHLCV + Statistics for an ETF."""
    # Fetch OHLCV
    ohlcv_csv = fetch_databento_csv(dataset, "ohlcv-1d", symbol, start, end)
    ohlcv_df = parse_ohlcv_csv(ohlcv_csv)

    # Fetch Statistics (may not be available)
    stats = {}
    try:
        stats_csv = fetch_databento_csv(dataset, "statistics", symbol, start, end)
        stats = parse_statistics_csv(stats_csv)
    except Exception as e:
        logger.debug(f"No statistics for {symbol}: {e}")

    return ohlcv_df, stats


# =============================================================================
# DATABASE
# =============================================================================

def get_db_connection():
    """Get database connection."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)


def upsert_etf_bars(bars: List[EtfBar], dry_run: bool = False) -> int:
    """Upsert ETF bars to database."""
    if not bars:
        return 0

    if dry_run:
        logger.info(f"[DRY RUN] Would upsert {len(bars)} bars for {bars[0].symbol}")
        return len(bars)

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Prepare data for batch upsert
        values = []
        for bar in bars:
            values.append((
                bar.symbol,
                bar.event_date.date(),
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                "databento",
                bar.row_hash(),
                bar.specialist_tags or [],
                bar.opening_price,
                bar.closing_price,
                bar.session_high,
                bar.session_low,
                bar.indicative_open,
                bar.indicative_close,
                bar.vwap,
            ))

        # Batch upsert
        execute_values(
            cur,
            """
            INSERT INTO mkt.etf_1d (
                symbol, event_date, open, high, low, close, volume,
                source, row_hash, specialist_tags,
                opening_price, closing_price, session_high, session_low,
                indicative_open, indicative_close, vwap
            ) VALUES %s
            ON CONFLICT (symbol, event_date) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                source = EXCLUDED.source,
                row_hash = EXCLUDED.row_hash,
                specialist_tags = EXCLUDED.specialist_tags,
                opening_price = COALESCE(EXCLUDED.opening_price, mkt.etf_1d.opening_price),
                closing_price = COALESCE(EXCLUDED.closing_price, mkt.etf_1d.closing_price),
                session_high = COALESCE(EXCLUDED.session_high, mkt.etf_1d.session_high),
                session_low = COALESCE(EXCLUDED.session_low, mkt.etf_1d.session_low),
                indicative_open = COALESCE(EXCLUDED.indicative_open, mkt.etf_1d.indicative_open),
                indicative_close = COALESCE(EXCLUDED.indicative_close, mkt.etf_1d.indicative_close),
                vwap = COALESCE(EXCLUDED.vwap, mkt.etf_1d.vwap)
            """,
            values,
            page_size=500,
        )

        conn.commit()
        return len(bars)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


# =============================================================================
# BACKFILL LOGIC
# =============================================================================

def backfill_symbol(
    symbol: str,
    start: datetime,
    end: datetime,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Backfill a single ETF symbol."""
    if symbol not in ETF_CONFIG:
        return {"symbol": symbol, "status": "error", "error": f"Unknown symbol: {symbol}"}

    dataset, name, tags = ETF_CONFIG[symbol]
    logger.info(f"Backfilling {symbol} ({name}) from {dataset}...")

    try:
        # Fetch data
        ohlcv_df, stats = fetch_etf_data(symbol, dataset, start, end)

        if ohlcv_df.empty:
            logger.warning(f"No data returned for {symbol}")
            return {"symbol": symbol, "status": "no_data", "rows": 0}

        # Convert to bars
        bars = []
        for _, row in ohlcv_df.iterrows():
            event_date = row["ts_event"].to_pydatetime()
            date_str = event_date.strftime("%Y-%m-%d")
            day_stats = stats.get(date_str, {})

            bar = EtfBar(
                symbol=symbol,
                event_date=event_date,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=int(row.get("volume", 0) or 0),
                opening_price=day_stats.get("opening_price"),
                closing_price=day_stats.get("closing_price"),
                session_high=day_stats.get("session_high"),
                session_low=day_stats.get("session_low"),
                indicative_open=day_stats.get("indicative_open"),
                indicative_close=day_stats.get("indicative_close"),
                vwap=day_stats.get("vwap"),
                specialist_tags=tags,
            )
            bars.append(bar)

        # Upsert to database
        inserted = upsert_etf_bars(bars, dry_run=dry_run)

        date_range = f"{bars[0].event_date.date()} to {bars[-1].event_date.date()}"
        logger.info(f"✓ {symbol}: {inserted} rows ({date_range}), {len(stats)} stats days")

        return {
            "symbol": symbol,
            "status": "success",
            "rows": inserted,
            "stats_days": len(stats),
            "date_range": date_range,
        }
    except Exception as e:
        logger.error(f"✗ {symbol}: {str(e)}")
        return {"symbol": symbol, "status": "error", "error": str(e)}


# Ray-accelerated backfill
if HAS_RAY:
    @ray.remote
    def backfill_symbol_ray(
        symbol: str,
        start: datetime,
        end: datetime,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        return backfill_symbol(symbol, start, end, dry_run)


def run_backfill(
    symbols: Optional[List[str]] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    dry_run: bool = False,
    use_ray: bool = True,
) -> List[Dict[str, Any]]:
    """Run full ETF backfill."""
    # Default to all symbols
    if symbols is None:
        symbols = list(ETF_CONFIG.keys())

    # Default to 10 years
    if end is None:
        end = datetime.now()
    if start is None:
        start = end - timedelta(days=365 * 10)

    logger.info(f"=" * 60)
    logger.info(f"ETF Backfill: {len(symbols)} symbols")
    logger.info(f"Date range: {start.date()} to {end.date()}")
    logger.info(f"Dry run: {dry_run}")
    logger.info(f"=" * 60)

    results = []

    if use_ray and HAS_RAY:
        # Use Ray cluster
        try:
            ray.init(address="auto", ignore_reinit_error=True)
            logger.info(f"Ray cluster: {ray.cluster_resources()}")

            futures = [
                backfill_symbol_ray.remote(sym, start, end, dry_run)
                for sym in symbols
            ]
            results = ray.get(futures)
        except Exception as e:
            logger.warning(f"Ray failed, falling back to serial: {e}")
            use_ray = False

    if not use_ray or not HAS_RAY:
        # Serial fallback with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(backfill_symbol, sym, start, end, dry_run): sym
                for sym in symbols
            }
            for future in as_completed(futures):
                results.append(future.result())

    # Summary
    success = sum(1 for r in results if r.get("status") == "success")
    errors = sum(1 for r in results if r.get("status") == "error")
    no_data = sum(1 for r in results if r.get("status") == "no_data")
    total_rows = sum(r.get("rows", 0) for r in results)

    logger.info(f"=" * 60)
    logger.info(f"BACKFILL COMPLETE")
    logger.info(f"Success: {success}/{len(symbols)}")
    logger.info(f"Errors: {errors}")
    logger.info(f"No data: {no_data}")
    logger.info(f"Total rows: {total_rows:,}")
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
    parser = argparse.ArgumentParser(description="Databento ETF Historical Backfill")
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of symbols (default: all)",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD, default: 10 years ago)",
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
