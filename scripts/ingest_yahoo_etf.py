#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Yahoo ETF Daily EOD Ingestion

Ingests daily OHLCV data from Yahoo Finance into mkt.etf_1d.
Uses a safe upsert:
  - Inserts new rows
  - Updates existing Yahoo/Barchart rows (for corrections/replacement)
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from typing import Dict, List, Optional, Tuple

import pandas as pd
import psycopg2
from dotenv import load_dotenv

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    raise SystemExit("yfinance not installed. Run: pip install yfinance")


ETF_SYMBOLS = [
    # Energy
    {"symbol": "XLE", "tags": ["energy", "biofuel"]},
    {"symbol": "XOP", "tags": ["energy"]},
    {"symbol": "USO", "tags": ["energy"]},
    {"symbol": "UNG", "tags": ["energy"]},
    {"symbol": "OIH", "tags": ["energy"]},
    # China
    {"symbol": "FXI", "tags": ["china"]},
    {"symbol": "KWEB", "tags": ["china"]},
    {"symbol": "MCHI", "tags": ["china"]},
    # Agriculture/Commodities
    {"symbol": "DBA", "tags": ["crush", "substitutes"]},
    {"symbol": "CORN", "tags": ["crush", "substitutes"]},
    {"symbol": "WEAT", "tags": ["crush", "substitutes"]},
    {"symbol": "SOYB", "tags": ["crush"]},
    # Biofuel/Clean Energy
    {"symbol": "TAN", "tags": ["biofuel"]},
    {"symbol": "ICLN", "tags": ["biofuel"]},
    {"symbol": "LIT", "tags": ["biofuel"]},
    # Rates/Macro
    {"symbol": "TLT", "tags": ["fed"]},
    {"symbol": "IEF", "tags": ["fed"]},
    {"symbol": "SPY", "tags": ["fed", "volatility"]},
    {"symbol": "QQQ", "tags": ["fed", "volatility"]},
    # Volatility
    {"symbol": "VXX", "tags": ["volatility"]},
    {"symbol": "UVXY", "tags": ["volatility"]},
    # Shipping / freight proxies (China)
    {"symbol": "BDRY", "tags": ["china"]},
    {"symbol": "SBLK", "tags": ["china"]},
    # FX/Metals
    {"symbol": "UUP", "tags": ["fx"]},
    {"symbol": "GLD", "tags": ["fx"]},
    {"symbol": "SLV", "tags": ["fx"]},
    # Palm Oil related
    {"symbol": "PALM", "tags": ["palm", "substitutes"]},
]


def compute_row_hash(symbol: str, event_date: date) -> str:
    return sha256(f"{symbol}|{event_date.isoformat()}".encode("utf-8")).hexdigest()


def download_yahoo_data(
    symbols: List[str], start_date: date, end_date: date
) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    # yfinance end is exclusive, add 1 day
    end_plus = end_date + timedelta(days=1)
    df = yf.download(
        tickers=symbols,
        start=start_date.isoformat(),
        end=end_plus.isoformat(),
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
    )
    return df


def process_df(
    df: pd.DataFrame, tags_map: Dict[str, List[str]]
) -> List[Tuple]:
    rows: List[Tuple] = []
    if df.empty:
        return rows

    # Multiple tickers: columns are (ticker, field)
    if isinstance(df.columns, pd.MultiIndex):
        tickers = sorted({c[0] for c in df.columns})
        for ticker in tickers:
            if ticker not in tags_map:
                continue
            sub = df[ticker].copy()
            rows.extend(_process_ticker_df(ticker, sub, tags_map[ticker]))
    else:
        # Single ticker
        ticker = next(iter(tags_map.keys()))
        rows.extend(_process_ticker_df(ticker, df, tags_map[ticker]))

    return rows


def chunked(items: List[str], size: int) -> List[List[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _process_ticker_df(
    ticker: str, df: pd.DataFrame, tags: List[str]
) -> List[Tuple]:
    rows: List[Tuple] = []
    df = df.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    for idx, row in df.iterrows():
        event_date = idx.date()
        close = row.get("Close")
        if pd.isna(close):
            continue
        row_hash = compute_row_hash(ticker, event_date)
        rows.append(
            (
                ticker,
                event_date,
                float(row.get("Open")) if pd.notna(row.get("Open")) else None,
                float(row.get("High")) if pd.notna(row.get("High")) else None,
                float(row.get("Low")) if pd.notna(row.get("Low")) else None,
                float(close),
                int(row.get("Volume")) if pd.notna(row.get("Volume")) else None,
                "yahoo",
                row_hash,
                tags,
            )
        )
    return rows


def upsert_rows(conn, rows: List[Tuple], dry_run: bool = False) -> Tuple[int, int]:
    if not rows:
        return 0, 0

    if dry_run:
        return 0, 0

    insert_sql = """
        INSERT INTO mkt.etf_1d
            (symbol, event_date, open, high, low, close, volume, source, row_hash, specialist_tags)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, event_date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            source = EXCLUDED.source,
            row_hash = EXCLUDED.row_hash,
            specialist_tags = EXCLUDED.specialist_tags
        WHERE mkt.etf_1d.source IN ('yahoo', 'barchart')
    """

    inserted = 0
    updated = 0
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(insert_sql, row)
            if cur.rowcount == 1:
                inserted += 1
            else:
                updated += 1
    conn.commit()
    return inserted, updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Yahoo ETF daily prices")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--days-back",
        type=int,
        default=365,
        help="Days to look back if start/end not specified",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Optional subset of ETF symbols",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Yahoo download batch size (tickers per request)",
    )
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    args = parser.parse_args()

    load_dotenv()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    # Date range
    today = datetime.now(timezone.utc).date()
    if args.start and args.end:
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end)
    else:
        end_date = today
        start_date = today - timedelta(days=args.days_back)

    symbols = [e["symbol"] for e in ETF_SYMBOLS]
    if args.symbols:
        symbols = [s for s in symbols if s in set(args.symbols)]

    tags_map = {e["symbol"]: e["tags"] for e in ETF_SYMBOLS if e["symbol"] in symbols}

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger("yahoo_etf")

    logger.info("ZINC-FUSION-V15: Yahoo ETF EOD Ingestion")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Symbols: {symbols}")
    if args.dry_run:
        logger.info("*** DRY RUN MODE ***")

    total_inserted = 0
    total_updated = 0
    total_rows = 0

    for batch in chunked(symbols, max(args.batch_size, 1)):
        logger.info(f"Downloading batch: {batch}")
        df = download_yahoo_data(batch, start_date, end_date)
        rows = process_df(df, {k: tags_map[k] for k in batch})
        inserted, updated = upsert_rows(conn, rows, dry_run=args.dry_run)
        total_inserted += inserted
        total_updated += updated
        total_rows += len(rows)

    logger.info(
        f"Inserted: {total_inserted}, Updated: {total_updated}, Rows prepared: {total_rows}"
    )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
