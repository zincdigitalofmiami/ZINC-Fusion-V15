#!/usr/bin/env python3
"""
Ingest critical archive data from Downloads folder.
Includes: corn/soybean stats with ethanol, financial crisis events, CME futures.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import re

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    return psycopg2.connect(database_url)


def parse_numeric(value):
    """Parse numeric value, handling commas and empty strings."""
    if pd.isna(value) or value == "" or value == '""':
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace('"', ""))
    except:
        return None


def ingest_corn_stats(conn, filepath: Path) -> int:
    """Ingest USDA corn statistics including ethanol usage."""
    print(f"\n  Processing corn stats: {filepath.name}")

    try:
        df = pd.read_csv(filepath)

        # Build records for usda_statistics table
        records = []

        for _, row in df.iterrows():
            year = row.get("Year")
            if pd.isna(year):
                continue

            # Parse relevant columns (stripping HTML tags from headers)
            acres_planted = parse_numeric(row.get("CORN - ACRES PLANTED  -  <b>VALUE</b>"))
            acres_harvested = parse_numeric(row.get("CORN, GRAIN - ACRES HARVESTED  -  <b>VALUE</b>"))
            production_bu = parse_numeric(row.get("CORN, GRAIN - PRODUCTION, MEASURED IN BU  -  <b>VALUE</b>"))
            production_usd = parse_numeric(row.get("CORN, GRAIN - PRODUCTION, MEASURED IN $  -  <b>VALUE</b>"))
            price_per_bu = parse_numeric(row.get("CORN, GRAIN - PRICE RECEIVED, MEASURED IN $ / BU  -  <b>VALUE</b>"))

            # CRITICAL: Ethanol usage data
            ethanol_usage_bu = parse_numeric(row.get("CORN, FOR ALCOHOL - USAGE, MEASURED IN BU  -  <b>VALUE</b>"))
            beverage_alcohol_bu = parse_numeric(row.get("CORN, FOR BEVERAGE ALCOHOL - USAGE, MEASURED IN BU  -  <b>VALUE</b>"))

            as_of_date = datetime(int(year), 12, 31)

            # Insert corn production stats
            if production_bu:
                records.append((
                    "CORN_PRODUCTION_BU",
                    as_of_date,
                    production_bu,
                    "USDA",
                    "Annual corn grain production in bushels"
                ))

            if acres_planted:
                records.append((
                    "CORN_ACRES_PLANTED",
                    as_of_date,
                    acres_planted,
                    "USDA",
                    "Annual corn acres planted"
                ))

            if acres_harvested:
                records.append((
                    "CORN_ACRES_HARVESTED",
                    as_of_date,
                    acres_harvested,
                    "USDA",
                    "Annual corn grain acres harvested"
                ))

            if price_per_bu:
                records.append((
                    "CORN_PRICE_PER_BU",
                    as_of_date,
                    price_per_bu,
                    "USDA",
                    "Corn price received per bushel"
                ))

            # CRITICAL: Ethanol/alcohol usage
            if ethanol_usage_bu:
                records.append((
                    "CORN_ETHANOL_USAGE_BU",
                    as_of_date,
                    ethanol_usage_bu,
                    "USDA",
                    "Corn used for alcohol/ethanol production in bushels"
                ))

            if beverage_alcohol_bu:
                records.append((
                    "CORN_BEVERAGE_ALCOHOL_BU",
                    as_of_date,
                    beverage_alcohol_bu,
                    "USDA",
                    "Corn used for beverage alcohol production in bushels"
                ))

        if not records:
            return 0

        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO "raw"."fred_observations_1d"
                (series_id, event_date, value, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                [(r[0], r[1], r[2], r[3]) for r in records],
                page_size=500,
            )
            inserted = cur.rowcount

        conn.commit()
        return inserted

    except Exception as e:
        print(f"    Error: {e}")
        conn.rollback()
        return 0


def ingest_soybean_stats(conn, filepath: Path) -> int:
    """Ingest USDA soybean statistics including crushing data."""
    print(f"\n  Processing soybean stats: {filepath.name}")

    try:
        df = pd.read_csv(filepath)

        records = []

        for _, row in df.iterrows():
            year = row.get("Year")
            if pd.isna(year):
                continue

            acres_planted = parse_numeric(row.get("SOYBEANS - ACRES PLANTED  -  <b>VALUE</b>"))
            acres_harvested = parse_numeric(row.get("SOYBEANS - ACRES HARVESTED  -  <b>VALUE</b>"))
            production_bu = parse_numeric(row.get("SOYBEANS - PRODUCTION, MEASURED IN BU  -  <b>VALUE</b>"))
            production_usd = parse_numeric(row.get("SOYBEANS - PRODUCTION, MEASURED IN $  -  <b>VALUE</b>"))
            price_per_bu = parse_numeric(row.get("SOYBEANS - PRICE RECEIVED, MEASURED IN $ / BU  -  <b>VALUE</b>"))
            yield_bu_acre = parse_numeric(row.get("SOYBEANS - YIELD, MEASURED IN BU / ACRE  -  <b>VALUE</b>"))
            crushed_tons = parse_numeric(row.get("SOYBEANS - CRUSHED, MEASURED IN TONS  -  <b>VALUE</b>"))

            as_of_date = datetime(int(year), 12, 31)

            if production_bu:
                records.append((
                    "SOYBEAN_PRODUCTION_BU",
                    as_of_date,
                    production_bu,
                    "USDA",
                ))

            if acres_planted:
                records.append((
                    "SOYBEAN_ACRES_PLANTED",
                    as_of_date,
                    acres_planted,
                    "USDA",
                ))

            if acres_harvested:
                records.append((
                    "SOYBEAN_ACRES_HARVESTED",
                    as_of_date,
                    acres_harvested,
                    "USDA",
                ))

            if price_per_bu:
                records.append((
                    "SOYBEAN_PRICE_PER_BU",
                    as_of_date,
                    price_per_bu,
                    "USDA",
                ))

            if yield_bu_acre:
                records.append((
                    "SOYBEAN_YIELD_BU_ACRE",
                    as_of_date,
                    yield_bu_acre,
                    "USDA",
                ))

            # CRITICAL: Crushing data
            if crushed_tons:
                records.append((
                    "SOYBEAN_CRUSHED_TONS",
                    as_of_date,
                    crushed_tons,
                    "USDA",
                ))

        if not records:
            return 0

        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO "raw"."fred_observations_1d"
                (series_id, event_date, value, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
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


def ingest_financial_crisis(conn, filepath: Path) -> int:
    """Ingest financial crisis indicator data with crisis labels."""
    print(f"\n  Processing financial crisis data: {filepath.name}")

    try:
        df = pd.read_csv(filepath)

        # Parse dates
        df["as_of_date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["as_of_date"])

        records = []

        # Define series to extract
        series_map = {
            "Equity_Return": "CRISIS_EQUITY_RETURN",
            "Bond_Yield": "CRISIS_BOND_YIELD",
            "FX_Rate_Change": "CRISIS_FX_RATE_CHANGE",
            "Volatility_Index": "CRISIS_VOLATILITY_INDEX",
            "GDP_Growth": "CRISIS_GDP_GROWTH",
            "Inflation": "CRISIS_INFLATION",
            "Crisis_Label": "CRISIS_LABEL",
        }

        for _, row in df.iterrows():
            as_of_date = row["as_of_date"]

            for col, series_id in series_map.items():
                value = parse_numeric(row.get(col))
                if value is not None:
                    records.append((
                        series_id,
                        as_of_date,
                        value,
                        "FinancialCrisis",
                    ))

        if not records:
            return 0

        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO "raw"."fred_observations_1d"
                (series_id, event_date, value, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                records,
                page_size=1000,
            )
            inserted = cur.rowcount

        conn.commit()
        return inserted

    except Exception as e:
        print(f"    Error: {e}")
        conn.rollback()
        return 0


def ingest_biofuel_data(conn, filepath: Path) -> int:
    """Ingest EIA biofuel supply and consumption data."""
    print(f"\n  Processing biofuel data: {filepath.name}")

    try:
        df = pd.read_csv(filepath, skiprows=4)  # Skip header rows

        # Find year columns
        year_cols = [c for c in df.columns if c.isdigit() or (isinstance(c, str) and re.match(r'^\d{4}$', c))]

        records = []

        for _, row in df.iterrows():
            source_key = row.get("source key")
            if pd.isna(source_key) or source_key == "":
                continue

            series_name = str(row.get("", row.iloc[0] if len(row) > 0 else ""))

            # Critical biofuel series
            biofuel_series = {
                "EOPRPUS": "EIA_ETHANOL_PRODUCTION",
                "BDPRPUS": "EIA_BIODIESEL_PRODUCTION",
                "RDPRPUS": "EIA_RENEWABLE_DIESEL_PRODUCTION",
                "EOTCPUS": "EIA_ETHANOL_CONSUMPTION",
                "BFSUPPLY": "EIA_BIOFUEL_SUPPLY",
                "BFTCPUS": "EIA_BIOFUEL_CONSUMPTION",
                "EOPSPUS": "EIA_ETHANOL_INVENTORY",
            }

            if source_key not in biofuel_series:
                continue

            series_id = biofuel_series[source_key]

            for year_col in year_cols:
                try:
                    year = int(year_col)
                    value = parse_numeric(row.get(year_col))
                    if value is not None:
                        as_of_date = datetime(year, 12, 31)
                        records.append((series_id, as_of_date, value, "EIA"))
                except:
                    continue

        if not records:
            return 0

        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO "raw"."fred_observations_1d"
                (series_id, event_date, value, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
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


def ingest_cme_futures(conn, folder: Path, symbol: str) -> int:
    """Ingest CME futures data from archive folder."""
    print(f"\n  Processing CME {symbol} futures from: {folder.name}")

    total_inserted = 0

    try:
        csv_files = list(folder.glob("*.csv"))

        for filepath in csv_files:
            df = pd.read_csv(filepath)

            # Detect date column
            date_col = None
            for col in ["Date", "date", "Time", "time"]:
                if col in df.columns:
                    date_col = col
                    break

            if not date_col:
                continue

            df["as_of_date"] = pd.to_datetime(df[date_col], errors="coerce")

            # Get OHLC columns
            col_map = {c.lower(): c for c in df.columns}
            close_col = col_map.get("close") or col_map.get("last") or col_map.get("settle")
            open_col = col_map.get("open")
            high_col = col_map.get("high")
            low_col = col_map.get("low")
            volume_col = col_map.get("volume")

            if not close_col:
                continue

            df = df.dropna(subset=["as_of_date"])

            records = []
            for _, row in df.iterrows():
                close = parse_numeric(row.get(close_col))
                if close is None:
                    continue

                records.append((
                    symbol,
                    row["as_of_date"],
                    parse_numeric(row.get(open_col)) if open_col else None,
                    parse_numeric(row.get(high_col)) if high_col else None,
                    parse_numeric(row.get(low_col)) if low_col else None,
                    close,
                    parse_numeric(row.get(volume_col)) if volume_col else None,
                    "CME",
                ))

            if records:
                with conn.cursor() as cur:
                    execute_batch(
                        cur,
                        """
                        INSERT INTO "raw"."market_futures_1d"
                        (symbol, event_date, open, high, low, close, volume, source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (event_date, symbol) DO NOTHING
                        """,
                        records,
                        page_size=500,
                    )
                    total_inserted += cur.rowcount

                conn.commit()

        return total_inserted

    except Exception as e:
        print(f"    Error: {e}")
        conn.rollback()
        return 0


def main():
    downloads = Path.home() / "Downloads"

    print("=" * 70)
    print("ARCHIVE DATA INGESTION")
    print("Corn/Soybean Stats, Financial Crisis, Biofuels, CME Futures")
    print("=" * 70)

    conn = get_postgres_connection()

    total_inserted = 0

    # 1. Corn and Soybean Stats (with ethanol usage)
    print("\n" + "=" * 50)
    print("[1] USDA CORN & SOYBEAN STATISTICS")
    print("=" * 50)

    for pattern in ["archive (7)*", "archive (7) *"]:
        for folder in downloads.glob(pattern):
            if folder.is_dir():
                corn_file = folder / "corn_stats.csv"
                soy_file = folder / "soybean_stats.csv"

                if corn_file.exists():
                    inserted = ingest_corn_stats(conn, corn_file)
                    print(f"    -> Corn stats inserted: {inserted:,}")
                    total_inserted += inserted

                if soy_file.exists():
                    inserted = ingest_soybean_stats(conn, soy_file)
                    print(f"    -> Soybean stats inserted: {inserted:,}")
                    total_inserted += inserted

    # 2. Financial Crisis Data
    print("\n" + "=" * 50)
    print("[2] FINANCIAL CRISIS INDICATORS")
    print("=" * 50)

    for pattern in ["Financial_Crisis*.csv"]:
        for filepath in downloads.glob(pattern):
            inserted = ingest_financial_crisis(conn, filepath)
            print(f"    -> Financial crisis inserted: {inserted:,}")
            total_inserted += inserted

    # 3. Biofuel/Ethanol Data
    print("\n" + "=" * 50)
    print("[3] EIA BIOFUEL/ETHANOL DATA")
    print("=" * 50)

    for pattern in ["*Biofuel*.csv", "*biofuel*.csv"]:
        for filepath in downloads.glob(pattern):
            inserted = ingest_biofuel_data(conn, filepath)
            print(f"    -> Biofuel data inserted: {inserted:,}")
            total_inserted += inserted

    # 4. CME Futures Archives
    print("\n" + "=" * 50)
    print("[4] CME FUTURES ARCHIVES")
    print("=" * 50)

    # CME_SF = Soybean futures
    for pattern in ["archive (9)*", "archive (9) *"]:
        for folder in downloads.glob(pattern):
            if folder.is_dir():
                inserted = ingest_cme_futures(conn, folder, "ZS")
                print(f"    -> ZS (Soybeans) inserted: {inserted:,}")
                total_inserted += inserted

    # CME_WH = Wheat futures (Soft Red Winter)
    for pattern in ["archive (10)*", "archive (10) *"]:
        for folder in downloads.glob(pattern):
            if folder.is_dir():
                inserted = ingest_cme_futures(conn, folder, "ZW")
                print(f"    -> ZW (Wheat) inserted: {inserted:,}")
                total_inserted += inserted

    # ICE_DX = Dollar Index futures
    for pattern in ["archive (11)*", "archive (11) *"]:
        for folder in downloads.glob(pattern):
            if folder.is_dir():
                inserted = ingest_cme_futures(conn, folder, "DX")
                print(f"    -> DX (Dollar Index) inserted: {inserted:,}")
                total_inserted += inserted

    conn.close()

    print("\n" + "=" * 70)
    print(f"ARCHIVE INGESTION COMPLETE: {total_inserted:,} total records inserted")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
