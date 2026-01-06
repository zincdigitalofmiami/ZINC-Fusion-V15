#!/usr/bin/env python3
"""
COMPREHENSIVE DATA INGESTION - Prisma Postgres
===============================================
Ingests all archive and Downloads data with proper routing:
- raw.fred_observations_1d - FRED/economic/quant data
- raw.market_futures_1d - OHLCV futures data
- training.specialist_*_1d - Specialist bucket data

Routes data to correct tables with proper metadata.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import re
import glob

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_batch

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_connection():
    """Get PostgreSQL connection."""
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not url:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(url)


def parse_num(val):
    """Parse numeric value safely."""
    if pd.isna(val) or val == "" or val == '""':
        return None
    if isinstance(val, (int, float)):
        return float(val) if not np.isnan(val) else None
    try:
        return float(str(val).replace(",", "").replace('"', "").strip())
    except:
        return None


def parse_date_flex(date_str):
    """Parse date in various formats."""
    if pd.isna(date_str):
        return None

    formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%b %d, %Y"]
    for fmt in formats:
        try:
            return pd.to_datetime(date_str, format=fmt)
        except:
            continue

    try:
        return pd.to_datetime(date_str, errors="coerce")
    except:
        return None


# =============================================================================
# RAW.FRED_OBSERVATIONS_1D - Economic/Quant Data
# =============================================================================

def ingest_fred_series(conn, filepath: Path, series_id: str, date_col: str, value_col: str, source: str = "CSV") -> int:
    """Ingest single series to fred_observations_1d."""
    try:
        df = pd.read_csv(filepath)

        if date_col not in df.columns or value_col not in df.columns:
            print(f"    Missing columns: {date_col}, {value_col}")
            return 0

        # Parse dates
        if df[date_col].dtype in ['int64', 'float64'] and df[date_col].abs().max() > 1e8:
            df["as_of_date"] = pd.to_datetime(df[date_col], unit='s', errors='coerce')
        else:
            df["as_of_date"] = df[date_col].apply(parse_date_flex)

        df["value"] = df[value_col].apply(parse_num)
        df = df.dropna(subset=["as_of_date", "value"])

        if df.empty:
            return 0

        records = [(series_id, row["as_of_date"], row["value"], source) for _, row in df.iterrows()]

        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO "raw"."fred_observations_1d" (series_id, as_of_date, value, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (series_id, as_of_date) DO NOTHING
                """,
                records,
                page_size=1000
            )
            inserted = cur.rowcount

        conn.commit()
        return inserted
    except Exception as e:
        print(f"    Error: {e}")
        conn.rollback()
        return 0


def ingest_corn_soybean_stats(conn, downloads: Path) -> int:
    """Ingest USDA corn/soybean stats with ethanol/crush data."""
    print("\n[USDA CORN/SOYBEAN STATS]")
    total = 0

    # Find corn/soybean stats files
    patterns = [
        "corn_stats*.csv",
        "soybean_stats*.csv",
    ]

    for pattern in patterns:
        for filepath in downloads.glob(pattern):
            commodity = "CORN" if "corn" in filepath.name.lower() else "SOYBEAN"
            print(f"  {filepath.name}")

            try:
                df = pd.read_csv(filepath)
                records = []

                for _, row in df.iterrows():
                    year = row.get("Year")
                    if pd.isna(year):
                        continue

                    as_of_date = datetime(int(year), 12, 31)

                    # Map columns to series
                    col_mappings = []

                    if commodity == "CORN":
                        col_mappings = [
                            ("CORN - ACRES PLANTED  -  <b>VALUE</b>", "CORN_ACRES_PLANTED"),
                            ("CORN, GRAIN - ACRES HARVESTED  -  <b>VALUE</b>", "CORN_ACRES_HARVESTED"),
                            ("CORN, GRAIN - PRODUCTION, MEASURED IN BU  -  <b>VALUE</b>", "CORN_PRODUCTION_BU"),
                            ("CORN, GRAIN - PRICE RECEIVED, MEASURED IN $ / BU  -  <b>VALUE</b>", "CORN_PRICE_USD_BU"),
                            ("CORN, FOR ALCOHOL - USAGE, MEASURED IN BU  -  <b>VALUE</b>", "CORN_ETHANOL_USAGE_BU"),
                            ("CORN, FOR BEVERAGE ALCOHOL - USAGE, MEASURED IN BU  -  <b>VALUE</b>", "CORN_BEVERAGE_ALCOHOL_BU"),
                        ]
                    else:
                        col_mappings = [
                            ("SOYBEANS - ACRES PLANTED  -  <b>VALUE</b>", "SOYBEAN_ACRES_PLANTED"),
                            ("SOYBEANS - ACRES HARVESTED  -  <b>VALUE</b>", "SOYBEAN_ACRES_HARVESTED"),
                            ("SOYBEANS - PRODUCTION, MEASURED IN BU  -  <b>VALUE</b>", "SOYBEAN_PRODUCTION_BU"),
                            ("SOYBEANS - PRICE RECEIVED, MEASURED IN $ / BU  -  <b>VALUE</b>", "SOYBEAN_PRICE_USD_BU"),
                            ("SOYBEANS - YIELD, MEASURED IN BU / ACRE  -  <b>VALUE</b>", "SOYBEAN_YIELD_BU_ACRE"),
                            ("SOYBEANS - CRUSHED, MEASURED IN TONS  -  <b>VALUE</b>", "SOYBEAN_CRUSHED_TONS"),
                        ]

                    for col_name, series_id in col_mappings:
                        val = parse_num(row.get(col_name))
                        if val is not None:
                            records.append((series_id, as_of_date, val, "USDA"))

                if records:
                    with conn.cursor() as cur:
                        execute_batch(
                            cur,
                            """
                            INSERT INTO "raw"."fred_observations_1d" (series_id, as_of_date, value, source)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (series_id, as_of_date) DO NOTHING
                            """,
                            records,
                            page_size=500
                        )
                        inserted = cur.rowcount
                        total += inserted
                        print(f"    -> Inserted: {inserted}")
                    conn.commit()

            except Exception as e:
                print(f"    Error: {e}")
                conn.rollback()

    # Also check archive folders
    for archive_dir in downloads.glob("archive*"):
        if archive_dir.is_dir():
            for pattern in ["corn_stats*.csv", "soybean_stats*.csv"]:
                for filepath in archive_dir.glob(pattern):
                    commodity = "CORN" if "corn" in filepath.name.lower() else "SOYBEAN"
                    print(f"  {archive_dir.name}/{filepath.name}")

                    try:
                        df = pd.read_csv(filepath)
                        records = []

                        for _, row in df.iterrows():
                            year = row.get("Year")
                            if pd.isna(year):
                                continue

                            as_of_date = datetime(int(year), 12, 31)

                            if commodity == "CORN":
                                mappings = [
                                    ("CORN - ACRES PLANTED  -  <b>VALUE</b>", "CORN_ACRES_PLANTED"),
                                    ("CORN, GRAIN - PRODUCTION, MEASURED IN BU  -  <b>VALUE</b>", "CORN_PRODUCTION_BU"),
                                    ("CORN, FOR ALCOHOL - USAGE, MEASURED IN BU  -  <b>VALUE</b>", "CORN_ETHANOL_USAGE_BU"),
                                ]
                            else:
                                mappings = [
                                    ("SOYBEANS - PRODUCTION, MEASURED IN BU  -  <b>VALUE</b>", "SOYBEAN_PRODUCTION_BU"),
                                    ("SOYBEANS - CRUSHED, MEASURED IN TONS  -  <b>VALUE</b>", "SOYBEAN_CRUSHED_TONS"),
                                ]

                            for col_name, series_id in mappings:
                                val = parse_num(row.get(col_name))
                                if val is not None:
                                    records.append((series_id, as_of_date, val, "USDA"))

                        if records:
                            with conn.cursor() as cur:
                                execute_batch(
                                    cur,
                                    """
                                    INSERT INTO "raw"."fred_observations_1d" (series_id, as_of_date, value, source)
                                    VALUES (%s, %s, %s, %s)
                                    ON CONFLICT (series_id, as_of_date) DO NOTHING
                                    """,
                                    records,
                                    page_size=500
                                )
                                inserted = cur.rowcount
                                total += inserted
                                print(f"    -> Inserted: {inserted}")
                            conn.commit()
                    except Exception as e:
                        print(f"    Error: {e}")
                        conn.rollback()

    return total


def ingest_financial_crisis(conn, downloads: Path) -> int:
    """Ingest financial crisis indicator data with crisis labels."""
    print("\n[FINANCIAL CRISIS DATA]")
    total = 0

    for filepath in downloads.glob("Financial_Crisis*.csv"):
        print(f"  {filepath.name}")

        try:
            df = pd.read_csv(filepath)
            df["as_of_date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["as_of_date"])

            series_map = {
                "Equity_Return": "CRISIS_EQUITY_RETURN",
                "Bond_Yield": "CRISIS_BOND_YIELD",
                "FX_Rate_Change": "CRISIS_FX_CHANGE",
                "Volatility_Index": "CRISIS_VIX",
                "GDP_Growth": "CRISIS_GDP_GROWTH",
                "Inflation": "CRISIS_INFLATION",
                "Crisis_Label": "CRISIS_LABEL",
            }

            records = []
            for _, row in df.iterrows():
                for col, series_id in series_map.items():
                    val = parse_num(row.get(col))
                    if val is not None:
                        records.append((series_id, row["as_of_date"], val, "FinancialCrisis"))

            if records:
                with conn.cursor() as cur:
                    execute_batch(
                        cur,
                        """
                        INSERT INTO "raw"."fred_observations_1d" (series_id, as_of_date, value, source)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (series_id, as_of_date) DO NOTHING
                        """,
                        records,
                        page_size=1000
                    )
                    inserted = cur.rowcount
                    total += inserted
                    print(f"    -> Inserted: {inserted}")
                conn.commit()

        except Exception as e:
            print(f"    Error: {e}")
            conn.rollback()

    return total


def ingest_biofuel_eia(conn, downloads: Path) -> int:
    """Ingest EIA biofuel/ethanol data."""
    print("\n[EIA BIOFUEL DATA]")
    total = 0

    for filepath in downloads.glob("*Biofuel*.csv"):
        print(f"  {filepath.name}")

        try:
            df = pd.read_csv(filepath, skiprows=4)

            # Find year columns
            year_cols = [c for c in df.columns if str(c).isdigit()]

            # Key biofuel series
            series_keys = {
                "EOPRPUS": "EIA_ETHANOL_PRODUCTION",
                "BDPRPUS": "EIA_BIODIESEL_PRODUCTION",
                "RDPRPUS": "EIA_RENEWABLE_DIESEL_PROD",
                "EOTCPUS": "EIA_ETHANOL_CONSUMPTION",
                "BFSUPPLY": "EIA_BIOFUEL_SUPPLY",
            }

            records = []
            for _, row in df.iterrows():
                source_key = str(row.get("source key", ""))
                if source_key not in series_keys:
                    continue

                series_id = series_keys[source_key]

                for year_col in year_cols:
                    try:
                        year = int(year_col)
                        val = parse_num(row.get(year_col))
                        if val is not None:
                            as_of_date = datetime(year, 12, 31)
                            records.append((series_id, as_of_date, val, "EIA"))
                    except:
                        continue

            if records:
                with conn.cursor() as cur:
                    execute_batch(
                        cur,
                        """
                        INSERT INTO "raw"."fred_observations_1d" (series_id, as_of_date, value, source)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (series_id, as_of_date) DO NOTHING
                        """,
                        records,
                        page_size=500
                    )
                    inserted = cur.rowcount
                    total += inserted
                    print(f"    -> Inserted: {inserted}")
                conn.commit()

        except Exception as e:
            print(f"    Error: {e}")
            conn.rollback()

    return total


# =============================================================================
# RAW.MARKET_FUTURES_1D - OHLCV Data
# =============================================================================

def ingest_futures_ohlcv(conn, filepath: Path, symbol: str, source: str = "CSV") -> int:
    """Ingest OHLCV futures data."""
    try:
        df = pd.read_csv(filepath)

        # Detect date column
        date_col = None
        for col in ["Date", "date", "Time", "time"]:
            if col in df.columns:
                date_col = col
                break

        if not date_col:
            return 0

        # Parse dates
        if df[date_col].dtype in ['int64', 'float64'] and df[date_col].abs().max() > 1e8:
            df["as_of_date"] = pd.to_datetime(df[date_col], unit='s', errors='coerce')
        else:
            df["as_of_date"] = df[date_col].apply(parse_date_flex)

        # Detect OHLCV columns (case insensitive)
        col_map = {c.lower(): c for c in df.columns}
        open_col = col_map.get("open")
        high_col = col_map.get("high")
        low_col = col_map.get("low")
        close_col = col_map.get("close") or col_map.get("last") or col_map.get("settle")
        volume_col = col_map.get("volume")

        if not close_col:
            return 0

        df = df.dropna(subset=["as_of_date"])

        records = []
        for _, row in df.iterrows():
            close = parse_num(row.get(close_col))
            if close is None:
                continue

            records.append((
                symbol,
                row["as_of_date"],
                parse_num(row.get(open_col)) if open_col else None,
                parse_num(row.get(high_col)) if high_col else None,
                parse_num(row.get(low_col)) if low_col else None,
                close,
                int(parse_num(row.get(volume_col)) or 0) if volume_col else None,
                source,
            ))

        if not records:
            return 0

        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO "raw"."market_futures_1d"
                (symbol, as_of_date, open, high, low, close, volume, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (as_of_date, symbol) DO NOTHING
                """,
                records,
                page_size=500
            )
            inserted = cur.rowcount

        conn.commit()
        return inserted

    except Exception as e:
        print(f"    Error: {e}")
        conn.rollback()
        return 0


def ingest_cme_archives(conn, downloads: Path) -> int:
    """Ingest CME futures from archive folders."""
    print("\n[CME FUTURES ARCHIVES]")
    total = 0

    # CME_SF = Soybean Futures
    for archive_dir in downloads.glob("archive*"):
        if archive_dir.is_dir():
            for filepath in archive_dir.glob("CME_SF*.csv"):
                inserted = ingest_futures_ohlcv(conn, filepath, "ZS", "CME")
                if inserted > 0:
                    print(f"  ZS: {filepath.name} -> {inserted}")
                    total += inserted

            for filepath in archive_dir.glob("CME_WH*.csv"):
                inserted = ingest_futures_ohlcv(conn, filepath, "ZW", "CME")
                if inserted > 0:
                    print(f"  ZW: {filepath.name} -> {inserted}")
                    total += inserted

            for filepath in archive_dir.glob("ICE_DX*.csv"):
                inserted = ingest_futures_ohlcv(conn, filepath, "DX", "ICE")
                if inserted > 0:
                    print(f"  DX: {filepath.name} -> {inserted}")
                    total += inserted

    # Also direct CME files in Downloads
    for filepath in downloads.glob("CME_SF*.csv"):
        inserted = ingest_futures_ohlcv(conn, filepath, "ZS", "CME")
        if inserted > 0:
            print(f"  ZS: {filepath.name} -> {inserted}")
            total += inserted

    return total


def ingest_tradingview_ohlcv(conn, downloads: Path) -> int:
    """Ingest TradingView OHLCV exports."""
    print("\n[TRADINGVIEW OHLCV]")
    total = 0

    # Map file patterns to symbols
    symbol_patterns = {
        "CBOT_ZL": "ZL",
        "CBOT_ZS": "ZS",
        "CBOT_ZC": "ZC",
        "CBOT_ZW": "ZW",
        "CBOT_ZQ": "ZQ",  # Oats
        "NYMEX_CL": "CL",
        "CAPITALCOM_DXY": "DXY",
        "CBOE_DLY_GVZ": "GVZ",
    }

    for pattern, symbol in symbol_patterns.items():
        for filepath in downloads.glob(f"{pattern}*.csv"):
            inserted = ingest_futures_ohlcv(conn, filepath, symbol, "TradingView")
            if inserted > 0:
                print(f"  {symbol}: {filepath.name} -> {inserted}")
                total += inserted

    return total


def ingest_barchart_historical(conn, downloads: Path) -> int:
    """Ingest Barchart historical price files."""
    print("\n[BARCHART HISTORICAL]")
    total = 0

    # Look for typical barchart patterns
    for filepath in downloads.glob("*_daily_historical*.csv"):
        # Try to determine symbol from filename
        name = filepath.name.lower()
        if "usd" in name:
            # FX pair
            continue  # Handle separately
        elif "zl" in name:
            symbol = "ZL"
        elif "historical-prices" in name:
            # Generic - likely ZL
            symbol = "ZL"
        else:
            continue

        inserted = ingest_futures_ohlcv(conn, filepath, symbol, "Barchart")
        if inserted > 0:
            print(f"  {symbol}: {filepath.name} -> {inserted}")
            total += inserted

    return total


# =============================================================================
# MAIN
# =============================================================================

def main():
    downloads = Path.home() / "Downloads"

    print("=" * 70)
    print("COMPREHENSIVE DATA INGESTION")
    print("=" * 70)
    print(f"Downloads folder: {downloads}")
    print()

    conn = get_connection()

    total = 0

    # 1. USDA Stats (corn/soybean with ethanol/crush)
    total += ingest_corn_soybean_stats(conn, downloads)

    # 2. Financial Crisis Data
    total += ingest_financial_crisis(conn, downloads)

    # 3. EIA Biofuel/Ethanol
    total += ingest_biofuel_eia(conn, downloads)

    # 4. CME Futures Archives
    total += ingest_cme_archives(conn, downloads)

    # 5. TradingView OHLCV
    total += ingest_tradingview_ohlcv(conn, downloads)

    # 6. Barchart Historical
    total += ingest_barchart_historical(conn, downloads)

    conn.close()

    print()
    print("=" * 70)
    print(f"TOTAL RECORDS INSERTED: {total:,}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
