#!/usr/bin/env python3
"""
Comprehensive ingestion script for all CSV data in Downloads folder.
Handles multiple formats: TradingView, CME, FRED direct downloads.

Routes data to v2 schema tables:
- FRED data → econ.* tables via FRED_SERIES_ROUTING
- Futures data → mkt.futures_1d
"""

import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

# Load environment
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.fusion.db.fred_routing import get_fred_schema_table


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    if database_url.startswith("prisma+postgres://"):
        raise ValueError(
            "DATABASE_URL must be a direct postgres:// or postgresql:// URL"
        )
    return psycopg2.connect(database_url)


def parse_unix_timestamp(ts):
    """Parse unix timestamp (seconds since epoch) to datetime."""
    try:
        return pd.to_datetime(ts, unit="s")
    except:
        return pd.NaT


def parse_date_flexible(date_str):
    """Parse dates in various formats."""
    if pd.isna(date_str):
        return pd.NaT

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
    ]

    for fmt in formats:
        try:
            return pd.to_datetime(date_str, format=fmt)
        except:
            continue

    return pd.to_datetime(date_str, errors="coerce")


# ============================================================================
# INGEST FUNCTIONS
# ============================================================================


def ingest_fred_file(
    conn, filepath: Path, series_id: str, date_col: str, value_col: str
) -> int:
    """Ingest FRED-style CSV into fred_observations_1d."""
    try:
        df = pd.read_csv(filepath)

        if date_col not in df.columns or value_col not in df.columns:
            print(f"    Missing columns: need {date_col}, {value_col}")
            return 0

        # Handle unix timestamps
        if (
            df[date_col].dtype in ["int64", "float64"]
            and df[date_col].abs().max() > 1e8
        ):
            df["as_of_date"] = df[date_col].apply(parse_unix_timestamp)
        else:
            df["as_of_date"] = pd.to_datetime(df[date_col], errors="coerce")

        df["value"] = pd.to_numeric(df[value_col], errors="coerce")
        df = df.dropna(subset=["as_of_date", "value"])

        if df.empty:
            return 0

        # Route to correct econ.* table based on series_id
        schema, table = get_fred_schema_table(series_id)
        qualified_table = f'"{schema}"."{table}"'

        records = [
            (series_id, row["as_of_date"], row["value"], "FRED")
            for _, row in df.iterrows()
        ]

        with conn.cursor() as cur:
            execute_batch(
                cur,
                f"""
                INSERT INTO {qualified_table}
                (series_id, event_date, value, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (series_id, event_date) DO NOTHING
                """,
                records,
                page_size=500,
            )
            inserted = cur.rowcount

        conn.commit()
        print(f"    Routed to: {qualified_table}")
        return inserted

    except Exception as e:
        print(f"    Error: {e}")
        conn.rollback()
        return 0


def ingest_futures_ohlc(conn, filepath: Path, symbol: str) -> int:
    """Ingest futures OHLC CSV into market_futures_1d."""
    try:
        df = pd.read_csv(filepath)

        # Detect date column
        date_col = None
        for col in ["Date", "Time", "time", "date"]:
            if col in df.columns:
                date_col = col
                break

        if not date_col:
            print(f"    No date column found")
            return 0

        # Parse date
        if (
            df[date_col].dtype in ["int64", "float64"]
            and df[date_col].abs().max() > 1e8
        ):
            df["as_of_date"] = df[date_col].apply(parse_unix_timestamp)
        else:
            df["as_of_date"] = df[date_col].apply(parse_date_flexible)

        # Get OHLC columns (case-insensitive)
        col_map = {c.lower(): c for c in df.columns}
        open_col = col_map.get("open")
        high_col = col_map.get("high")
        low_col = col_map.get("low")
        close_col = col_map.get("close") or col_map.get("last")
        volume_col = col_map.get("volume")

        if not close_col:
            print(f"    No close column found")
            return 0

        df["open"] = pd.to_numeric(df[open_col], errors="coerce") if open_col else None
        df["high"] = pd.to_numeric(df[high_col], errors="coerce") if high_col else None
        df["low"] = pd.to_numeric(df[low_col], errors="coerce") if low_col else None
        df["close"] = pd.to_numeric(df[close_col], errors="coerce")

        if volume_col:
            df["volume"] = pd.to_numeric(
                df[volume_col].astype(str).str.replace(",", "").str.replace(" ", ""),
                errors="coerce",
            )
        else:
            df["volume"] = None

        df = df.dropna(subset=["as_of_date", "close"])

        if df.empty:
            return 0

        records = [
            (
                symbol,
                row["as_of_date"],
                row.get("open") if pd.notna(row.get("open")) else None,
                row.get("high") if pd.notna(row.get("high")) else None,
                row.get("low") if pd.notna(row.get("low")) else None,
                row["close"],
                row.get("volume") if pd.notna(row.get("volume")) else None,
                "CSV",
            )
            for _, row in df.iterrows()
        ]

        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO "mkt"."futures_1d"
                (symbol, event_date, open, high, low, close, volume, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_date, symbol) DO NOTHING
                """,
                records,
                page_size=500,
            )
            inserted = cur.rowcount

        conn.commit()
        return inserted

    except Exception as e:
        print(f"    Error: {e}")
        conn.rollback()
        return 0


def ingest_multi_commodity_dataset(conn, filepath: Path) -> int:
    """Ingest multi-commodity dataset (Resources_Dataset, Futures_Resources_Data)."""
    try:
        df = pd.read_csv(filepath)

        if "Date" not in df.columns:
            print(f"    No Date column found")
            return 0

        df["as_of_date"] = df["Date"].apply(parse_date_flexible)
        df = df.dropna(subset=["as_of_date"])

        total_inserted = 0

        # Map column names to symbols
        symbol_map = {
            "CL=F": "CL",
            "BZ=F": "BZ",
            "GC=F": "GC",
            "SI=F": "SI",
            "NG=F": "NG",
            "ZC=F": "ZC",
            "ZW=F": "ZW",
            "ZS=F": "ZS",
            "HG=F": "HG",
            "PL=F": "PL",
            "PA=F": "PA",
        }

        for col_prefix, symbol in symbol_map.items():
            # Look for close/closing_price column
            close_col = None
            volume_col = None
            for col in df.columns:
                if col_prefix in col:
                    if "close" in col.lower() or "closing" in col.lower():
                        close_col = col
                    elif "volume" in col.lower():
                        volume_col = col

            if not close_col:
                continue

            df_sym = df[["as_of_date", close_col]].copy()
            if volume_col:
                df_sym["volume"] = pd.to_numeric(df[volume_col], errors="coerce")
            else:
                df_sym["volume"] = None

            df_sym["close"] = pd.to_numeric(df_sym[close_col], errors="coerce")
            df_sym = df_sym.dropna(subset=["close"])

            if df_sym.empty:
                continue

            records = [
                (
                    symbol,
                    row["as_of_date"],
                    None,
                    None,
                    None,  # open, high, low
                    row["close"],
                    row["volume"] if pd.notna(row.get("volume")) else None,
                    "CSV",
                )
                for _, row in df_sym.iterrows()
            ]

            with conn.cursor() as cur:
                execute_batch(
                    cur,
                    """
                    INSERT INTO "mkt"."futures_1d"
                    (symbol, event_date, open, high, low, close, volume, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_date, symbol) DO NOTHING
                    """,
                    records,
                    page_size=500,
                )
                inserted = cur.rowcount
                total_inserted += inserted
                print(f"      {symbol}: {inserted:,} inserted")

            conn.commit()

        return total_inserted

    except Exception as e:
        print(f"    Error: {e}")
        conn.rollback()
        return 0


def main():
    downloads = Path.home() / "Downloads"

    print("=" * 70)
    print("COMPREHENSIVE DATA INGESTION FROM DOWNLOADS")
    print("=" * 70)
    print()

    conn = get_postgres_connection()

    total_inserted = 0

    # 1. FRED files
    print("=" * 50)
    print("[1] FRED OBSERVATIONS")
    print("=" * 50)

    fred_files = {
        "VIXCLS 2.csv": ("VIXCLS", "observation_date", "VIXCLS"),
        "VXGSCLS 2.csv": ("VXGSCLS", "observation_date", "VXGSCLS"),
        "FRED_FEDFUNDS, 1D 2.csv": ("FEDFUNDS", "time", "close"),
        "FRED_GDP, 1D 2.csv": ("GDP", "time", "close"),
        "FRED_SP500, 1D 2.csv": ("SP500", "time", "close"),
        "FRED_LVXRNSA, 1D 2.csv": ("LVXRNSA", "time", "close"),
    }

    for filename, (series_id, date_col, value_col) in fred_files.items():
        filepath = downloads / filename
        if not filepath.exists():
            continue
        df = pd.read_csv(filepath)
        print(f"  {series_id}: {filename} ({len(df):,} rows)")
        inserted = ingest_fred_file(conn, filepath, series_id, date_col, value_col)
        print(f"    -> Inserted: {inserted:,}")
        total_inserted += inserted

    # 2. Multi-commodity datasets
    print()
    print("=" * 50)
    print("[2] MULTI-COMMODITY DATASETS")
    print("=" * 50)

    multi_files = [
        "Resources_Dataset 2.csv",
        "Futures_Resources_Data 2.csv",
    ]

    for filename in multi_files:
        filepath = downloads / filename
        if not filepath.exists():
            continue
        df = pd.read_csv(filepath)
        print(f"  {filename} ({len(df):,} rows)")
        inserted = ingest_multi_commodity_dataset(conn, filepath)
        print(f"    -> Total inserted: {inserted:,}")
        total_inserted += inserted

    # 3. CME futures files
    print()
    print("=" * 50)
    print("[3] CME FUTURES (ZS/ZL)")
    print("=" * 50)

    # Find all CME files
    cme_patterns = ["CME_SF*.csv", "CME_SH*.csv"]
    for pattern in cme_patterns:
        for filepath in downloads.glob(pattern):
            df = pd.read_csv(filepath)
            # Extract symbol from filename
            symbol = "ZS"  # Soybeans
            print(f"  {symbol}: {filepath.name} ({len(df):,} rows)")
            inserted = ingest_futures_ohlc(conn, filepath, symbol)
            print(f"    -> Inserted: {inserted:,}")
            total_inserted += inserted

    # 4. Other futures (crude, wheat, corn, etc.)
    print()
    print("=" * 50)
    print("[4] OTHER FUTURES")
    print("=" * 50)

    other_futures = {
        "crude 2.csv": "CL",
        "wheat 2.csv": "ZW",
        "corn 2.csv": "ZC",
        "canola 2.csv": "RS",
        "rapeseed 2.csv": "RS",
        "10 Year Note 2.csv": "ZN",
    }

    for filename, symbol in other_futures.items():
        filepath = downloads / filename
        if not filepath.exists():
            continue
        df = pd.read_csv(filepath)
        print(f"  {symbol}: {filename} ({len(df):,} rows)")
        inserted = ingest_futures_ohlc(conn, filepath, symbol)
        print(f"    -> Inserted: {inserted:,}")
        total_inserted += inserted

    conn.close()

    print()
    print("=" * 70)
    print(f"INGESTION COMPLETE: {total_inserted:,} total records inserted")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
