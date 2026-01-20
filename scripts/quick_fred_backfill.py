#!/usr/bin/env python3
"""
Quick FRED backfill script - pulls data back to 2000 for all Big-11 series.
"""

import argparse
import hashlib
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Dict

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
import requests

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# FRED API
FRED_API_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES_API_BASE = "https://api.stlouisfed.org/fred/series"
FRED_API_KEY = os.getenv("FRED_API_KEY")

# All Big-11 specialist FRED series
FRED_SERIES = {
    # FED SPECIALIST - Interest Rates, Yields, Monetary Policy
    "DFF": "Fed Funds Effective Rate (Daily)",
    "FEDFUNDS": "Federal Funds Effective Rate",
    "DFEDTARL": "Fed Funds Target Range - Lower Limit",
    "DFEDTARU": "Fed Funds Target Range - Upper Limit",
    "DGS1MO": "1-Month Treasury",
    "DGS3MO": "3-Month Treasury",
    "DGS6MO": "6-Month Treasury",
    "DGS1": "1-Year Treasury",
    "DGS2": "2-Year Treasury",
    "DGS5": "5-Year Treasury",
    "DGS7": "7-Year Treasury",
    "DGS10": "10-Year Treasury",
    "DGS20": "20-Year Treasury",
    "DGS30": "30-Year Treasury",
    "T10Y2Y": "10Y-2Y Spread (Yield Curve)",
    "T10Y3M": "10Y-3M Spread",
    "T10YIE": "10Y Breakeven Inflation",
    "SOFR": "SOFR Rate",
    "DPRIME": "Prime Rate",
    "MORTGAGE30US": "30-Year Mortgage Rate",
    "WALCL": "Fed Total Assets",
    "WRESBAL": "Reserve Balances",
    "RRPONTSYD": "Reverse Repo",
    "BOGMBASE": "Monetary Base: Total",
    "M2SL": "M2 Money Stock",
    "TOTRESNS": "Total Reserves",
    "BUSLOANS": "Commercial & Industrial Loans",
    "DRCCLACBS": "Credit Card Delinquency Rate",

    # FX SPECIALIST - Currency
    "DEXBZUS": "USD/BRL (Brazil)",
    "DEXCHUS": "USD/CNY (China)",
    "DEXUSEU": "USD/EUR",
    "DEXUSUK": "USD/GBP",
    "DEXJPUS": "USD/JPY",
    "DEXCAUS": "USD/CAD",
    "DEXMXUS": "USD/MXN",
    "DEXKOUS": "USD/KRW (Korea)",
    "DEXINUS": "USD/INR (India)",
    "DEXMAUS": "USD/MYR (Malaysia)",
    "DEXSFUS": "USD/SGD (Singapore)",
    "DEXTHUS": "USD/THB (Thailand)",
    "DEXHKUS": "USD/HKD (Hong Kong)",
    "DEXTAUS": "USD/TWD (Taiwan)",
    "DEXUSAL": "USD/AUD",
    "DEXNOUS": "USD/NOK",
    "DEXSZUS": "USD/CHF",
    "DEXSIUS": "USD/SEK",
    "DTWEXBGS": "Trade-Weighted USD (Broad)",
    "DTWEXAFEGS": "USD vs Advanced FX",
    "DTWEXEMEGS": "USD vs EM FX",

    # ENERGY SPECIALIST
    "DCOILWTICO": "WTI Crude Oil",
    "DCOILBRENTEU": "Brent Crude Oil",
    "DHHNGSP": "Henry Hub Natural Gas",
    "DHOILNYH": "Heating Oil Prices (NY Harbor)",
    "PNGASEUUSDM": "Natural Gas Price, EU",
    "DDFUELUSGULF": "Diesel Gulf Coast",
    "DGASUSGULF": "Gasoline Gulf Coast",
    "DJFUELUSGULF": "Jet Fuel Gulf Coast",
    "DPROPANEMBTX": "Propane Prices: Mont Belvieu, Texas",
    "WPU057303": "PPI Diesel Fuel",
    "PCU32411032411012": "PPI Motor Gasoline",

    # BIOFUEL SPECIALIST
    "APU000074714": "Gasoline CPI (Unleaded Regular)",
    "GASREGW": "US Regular Gas Price",
    "GASDESW": "US Diesel Price",
    "WPU06140341": "PPI Ethanol",

    # CRUSH SPECIALIST - Soybean complex from FRED
    "PSOILUSDM": "Soybean Oil Price (World Bank)",
    "PSOYBUSDM": "Soybeans Price (World Bank)",
    "PCU311224311224": "PPI Soybean Oil Processing",
    "PBARLUSDM": "Barley Price",
    "PWHEAMTUSDM": "Wheat Price",
    "PMAIZMTUSDM": "Global price of Corn",

    # PALM SPECIALIST
    "PPOILUSDM": "Global price of Palm Oil",
    "PROILUSDM": "Global price of Rapeseed Oil (proxy for palm kernel)",

    # VOLATILITY SPECIALIST
    "SP500": "S&P 500 Index",
    "NASDAQCOM": "NASDAQ Composite Index",
    "VIXCLS": "VIX Index",
    "OVXCLS": "Crude Oil Volatility Index",
    "GVZCLS": "Gold Volatility Index",
    "STLFSI": "St. Louis Financial Stress Index",
    "STLFSI4": "St. Louis Financial Stress",
    "TEDRATE": "TED Spread",
    "NFCI": "Chicago Fed Financial Conditions",
    "BAMLH0A0HYM2": "High Yield OAS",
    "BAMLC0A0CM": "Corporate OAS",

    # TRUMP EFFECT / POLICY SPECIALIST
    "USEPUINDXD": "US Policy Uncertainty (Daily)",
    "USEPUINDXM": "US Policy Uncertainty (Monthly)",
    "EPUTRADE": "Trade Policy Uncertainty",
    "EMVTRADEPOLEMV": "Trade Policy Volatility",
    "CHNMAINLANDTPU": "China Trade Policy Uncertainty",
    "B235RC1Q027SBEA": "Customs Duties (Tariff Receipts)",
    "IMPCH": "US Imports from China",

    # CHINA SPECIALIST
    "CHNCPIALLMINMEI": "China CPI (Total)",
    "CHNPRINTO01IXPYM": "China Industrial Production",
    "CHNGDPNQDSMEI": "China Real GDP",
    "IR3TIB01CNM156N": "China Interbank Rate (3M)",
    "MYAGM2CNM189N": "China M2",
    "XTEXVA01CNM667S": "China Exports Value",
    "XTIMVA01CNM667S": "China Imports Value",

    # Macro indicators
    "ICSA": "Initial Jobless Claims (Weekly)",
    "CCSA": "Continued Claims (Weekly)",
    "CPIAUCSL": "CPI All Urban",
    "CPILFESL": "Core CPI",
    "PCEPI": "PCE Price Index",
    "PCEPILFE": "Core PCE",
    "UNRATE": "Unemployment Rate",
    "PAYEMS": "Nonfarm Payrolls",
    "MANEMP": "Manufacturing Employment",
    "RSXFS": "Retail Sales",
    "GDP": "Gross Domestic Product",
    "GDPC1": "Real Gross Domestic Product",
    "PCE": "Personal Consumption Expenditures",
    "HOUST": "Housing Starts",
    "PERMIT": "Housing Permits",
    "PPIACO": "PPI All Commodities",
    "PPIFGS": "PPI Finished Goods",
    "BOPGSTB": "Trade Balance: Goods & Services",
    "EXPGS": "Exports of Goods & Services",
    "IMPGS": "Imports of Goods & Services",
    "PCOPPUSDM": "Copper Price (Global)",
    "PRICENPQUSDM": "Rice Price (Global)",
    "PSUNOUSDM": "Sunflower Oil Price (Global)",
    "WPU01830161": "PPI Farm Products: Sunflower",
    "WPU01830171": "PPI Farm Products: Canola",
    "INDPRO": "Industrial Production",
    "UMCSENT": "Consumer Sentiment",
    "FRGSHPUSM649NCIS": "Cass Freight Index",
}

SERIES_TAGS: Dict[str, list[str]] = {}


def _add_tags(series_ids: list[str], tags: list[str]) -> None:
    for series_id in series_ids:
        SERIES_TAGS[series_id] = tags


_add_tags(
    [
        "DFF",
        "FEDFUNDS",
        "DFEDTARL",
        "DFEDTARU",
        "DGS1MO",
        "DGS3MO",
        "DGS6MO",
        "DGS1",
        "DGS2",
        "DGS5",
        "DGS7",
        "DGS10",
        "DGS20",
        "DGS30",
        "T10Y2Y",
        "T10Y3M",
        "T10YIE",
        "SOFR",
        "DPRIME",
        "MORTGAGE30US",
        "WALCL",
        "WRESBAL",
        "RRPONTSYD",
        "BOGMBASE",
        "M2SL",
        "TOTRESNS",
        "BUSLOANS",
        "DRCCLACBS",
        "CPIAUCSL",
        "CPILFESL",
        "PCEPI",
        "PCEPILFE",
        "PCE",
        "PPIACO",
        "PPIFGS",
        "UNRATE",
        "PAYEMS",
        "MANEMP",
        "RSXFS",
        "GDP",
        "GDPC1",
        "HOUST",
        "PERMIT",
        "ICSA",
        "CCSA",
    ],
    ["fed"],
)

_add_tags(
    [
        "DEXBZUS",
        "DEXUSEU",
        "DEXUSUK",
        "DEXJPUS",
        "DEXCAUS",
        "DEXMXUS",
        "DEXKOUS",
        "DEXINUS",
        "DEXSFUS",
        "DEXTHUS",
        "DEXHKUS",
        "DEXTAUS",
        "DEXUSAL",
        "DEXNOUS",
        "DEXSZUS",
        "DEXSIUS",
        "DTWEXBGS",
        "DTWEXAFEGS",
        "DTWEXEMEGS",
    ],
    ["fx"],
)
SERIES_TAGS["DEXCHUS"] = ["fx", "china"]
SERIES_TAGS["DEXMAUS"] = ["fx", "palm"]

_add_tags(
    [
        "DCOILWTICO",
        "DCOILBRENTEU",
        "DHHNGSP",
        "DHOILNYH",
        "PNGASEUUSDM",
        "DJFUELUSGULF",
        "DPROPANEMBTX",
    ],
    ["energy"],
)
SERIES_TAGS["DDFUELUSGULF"] = ["energy", "biofuel"]
SERIES_TAGS["DGASUSGULF"] = ["energy", "biofuel"]
SERIES_TAGS["WPU057303"] = ["energy", "biofuel"]
SERIES_TAGS["PCU32411032411012"] = ["energy", "biofuel"]

SERIES_TAGS["APU000074714"] = ["biofuel", "energy"]
SERIES_TAGS["GASREGW"] = ["biofuel", "energy"]
SERIES_TAGS["GASDESW"] = ["biofuel", "energy"]
SERIES_TAGS["WPU06140341"] = ["biofuel"]

_add_tags(["PSOILUSDM", "PSOYBUSDM", "PCU311224311224"], ["crush"])
SERIES_TAGS["PMAIZMTUSDM"] = ["crush", "substitutes"]
SERIES_TAGS["PWHEAMTUSDM"] = ["substitutes"]
SERIES_TAGS["PBARLUSDM"] = ["substitutes"]
SERIES_TAGS["PSUNOUSDM"] = ["substitutes"]
SERIES_TAGS["PRICENPQUSDM"] = ["substitutes"]
SERIES_TAGS["PCOPPUSDM"] = ["substitutes"]
SERIES_TAGS["WPU01830161"] = ["substitutes"]
SERIES_TAGS["WPU01830171"] = ["substitutes"]

SERIES_TAGS["PPOILUSDM"] = ["palm"]
SERIES_TAGS["PROILUSDM"] = ["palm", "substitutes"]

_add_tags(
    [
        "SP500",
        "NASDAQCOM",
        "VIXCLS",
        "OVXCLS",
        "GVZCLS",
        "STLFSI",
        "STLFSI4",
        "TEDRATE",
        "NFCI",
        "BAMLH0A0HYM2",
        "BAMLC0A0CM",
    ],
    ["volatility"],
)

SERIES_TAGS["USEPUINDXD"] = ["trump_effect", "volatility"]
SERIES_TAGS["USEPUINDXM"] = ["trump_effect", "volatility"]
SERIES_TAGS["EPUTRADE"] = ["tariff"]
SERIES_TAGS["EMVTRADEPOLEMV"] = ["trump_effect", "volatility"]
SERIES_TAGS["CHNMAINLANDTPU"] = ["trump_effect", "tariff"]
SERIES_TAGS["B235RC1Q027SBEA"] = ["trump_effect", "tariff"]
SERIES_TAGS["IMPCH"] = ["trump_effect", "tariff"]
SERIES_TAGS["BOPGSTB"] = ["tariff"]
SERIES_TAGS["EXPGS"] = ["tariff"]
SERIES_TAGS["IMPGS"] = ["tariff"]

SERIES_TAGS["CHNCPIALLMINMEI"] = ["china"]
SERIES_TAGS["CHNPRINTO01IXPYM"] = ["china"]
SERIES_TAGS["CHNGDPNQDSMEI"] = ["china"]
SERIES_TAGS["IR3TIB01CNM156N"] = ["china"]
SERIES_TAGS["MYAGM2CNM189N"] = ["china"]
SERIES_TAGS["XTEXVA01CNM667S"] = ["china", "tariff"]
SERIES_TAGS["XTIMVA01CNM667S"] = ["china", "tariff"]

SERIES_TAGS["INDPRO"] = ["general"]
SERIES_TAGS["UMCSENT"] = ["general"]
SERIES_TAGS["FRGSHPUSM649NCIS"] = ["general"]


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def js_number_string(value: float) -> str:
    """Mirror JS Number.toString() formatting for row_hash consistency."""
    return format(value, ".15g")


def compute_row_hash(series_id: str, event_date: datetime, value: float) -> str:
    payload = f"{series_id}|{event_date.strftime('%Y-%m-%d')}|{js_number_string(value)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_ingest_run(conn, job_name: str) -> str:
    """Create ops.ingest_run record and return run_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ops.ingest_run (job_name, status, started_at, rows_attempted, rows_inserted, rows_skipped, rows_quarantined)
            VALUES (%s, 'running', NOW(), 0, 0, 0, 0)
            RETURNING id
            """,
            (job_name,),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return str(run_id)


def complete_ingest_run(
    conn,
    run_id: str,
    status: str,
    attempted: int,
    inserted: int,
    skipped: int,
    quarantined: int,
    error_message: str | None = None,
) -> None:
    """Update ops.ingest_run with final counters."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ops.ingest_run
            SET status = %s,
                completed_at = NOW(),
                rows_attempted = %s,
                rows_inserted = %s,
                rows_skipped = %s,
                rows_quarantined = %s,
                error_message = %s
            WHERE id = %s
            """,
            (status, attempted, inserted, skipped, quarantined, error_message, run_id),
        )
    conn.commit()


def load_series_tags(conn) -> Dict[str, list[str]]:
    """Load most recent specialist_tags per series from DB (econ tables)."""
    # In the new schema, FRED data is split across econ.* tables
    # Most series go to econ.rates_1d as the default
    # Just return the in-memory tags since we have them
    return SERIES_TAGS.copy()


def get_series_min_date(conn, series_id: str):
    """Return earliest event_date for a series (or None if missing)."""
    # Query all econ tables since FRED data is distributed
    econ_tables = [
        "econ.rates_1d", "econ.inflation_1d", "econ.labor_1d",
        "econ.activity_1d", "econ.vol_indices_1d", "econ.commodities_1d",
        "econ.money_1d"
    ]
    with conn.cursor() as cur:
        for table in econ_tables:
            try:
                cur.execute(
                    f"SELECT MIN(event_date) FROM {table} WHERE series_id=%s",
                    (series_id,),
                )
                result = cur.fetchone()[0]
                if result:
                    return result
            except:
                continue
        return None


def validate_series_ids(series_ids: list[str], sleep_seconds: float = 0.25):
    """Validate series IDs against FRED metadata endpoint."""
    invalid = {}
    metadata = {}
    if not FRED_API_KEY:
        return series_ids, invalid

    for series_id in series_ids:
        params = {
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
        }
        try:
            response = requests.get(FRED_SERIES_API_BASE, params=params, timeout=20)
            if response.status_code != 200:
                invalid[series_id] = f"status {response.status_code}"
            else:
                data = response.json()
                if not data.get("seriess"):
                    invalid[series_id] = "empty series"
                else:
                    metadata[series_id] = data["seriess"][0]
        except Exception as exc:
            invalid[series_id] = f"error {exc}"

        time.sleep(sleep_seconds)

    valid = [series_id for series_id in series_ids if series_id not in invalid]
    return valid, invalid, metadata


def fetch_fred_series(
    series_id: str,
    start_date: str = "2000-01-01",
    end_date: str | None = None,
) -> pd.DataFrame:
    """Fetch FRED series from API."""
    if not FRED_API_KEY:
        print(f"  Warning: No FRED_API_KEY, skipping {series_id}")
        return pd.DataFrame()

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date or datetime.now().strftime("%Y-%m-%d"),
    }

    try:
        response = requests.get(FRED_API_BASE, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        observations = data.get("observations", [])
        if not observations:
            return pd.DataFrame()

        df = pd.DataFrame(observations)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["value"])

        return df[["date", "value"]]

    except Exception as e:
        print(f"  Error fetching {series_id}: {e}")
        return pd.DataFrame()


def get_target_econ_table(series_id: str, tags: list[str] | None) -> str:
    """Determine which econ table to insert into based on tags."""
    # Map specialist tags to econ tables
    tag_to_table = {
        "fed": "econ.rates_1d",
        "volatility": "econ.vol_indices_1d",
        "energy": "econ.commodities_1d",
        "crush": "econ.commodities_1d",
        "palm": "econ.commodities_1d",
        "substitutes": "econ.commodities_1d",
        "biofuel": "econ.commodities_1d",
    }

    if tags:
        for tag in tags:
            if tag in tag_to_table:
                return tag_to_table[tag]

    # Default to rates_1d for most FRED series
    return "econ.rates_1d"


def insert_fred_data(
    conn,
    series_id: str,
    df: pd.DataFrame,
    tags: list[str] | None,
    run_id: str,
) -> int:
    """Insert FRED data into appropriate econ.* table."""
    if df.empty:
        return 0

    now = datetime.now(timezone.utc)
    target_table = get_target_econ_table(series_id, tags)

    records = []
    for _, row in df.iterrows():
        event_date = row["date"].to_pydatetime() if hasattr(row["date"], "to_pydatetime") else row["date"]
        value = float(row["value"])
        records.append(
            (
                series_id,
                event_date,
                value,
                "FRED",
                now,
                now,
                compute_row_hash(series_id, event_date, value),
            )
        )

    try:
        with conn.cursor() as cur:
            execute_batch(
                cur,
                f"""
                INSERT INTO {target_table}
                (series_id, event_date, value, source, ingested_at, knowledge_time, row_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (series_id, event_date) DO NOTHING
                """,
                records,
                page_size=500
            )
            inserted = len(records)
        conn.commit()
        return inserted
    except Exception as e:
        print(f"  Error inserting {series_id} to {target_table}: {e}")
        conn.rollback()
        return 0


def main():
    parser = argparse.ArgumentParser(description="Backfill FRED series into econ.* tables")
    parser.add_argument(
        "--series",
        help="Comma-separated list of FRED series IDs to backfill (default: all in script)",
    )
    parser.add_argument(
        "--start-date",
        default="2000-01-01",
        help="Start date for backfill (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Backfill missing history even if the series already exists in the DB",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip FRED series metadata validation",
    )
    parser.add_argument(
        "--fail-on-invalid",
        action="store_true",
        help="Exit if any FRED series IDs are invalid",
    )
    args = parser.parse_args()

    if args.series:
        series_ids = [s.strip() for s in args.series.split(",") if s.strip()]
    else:
        series_ids = list(FRED_SERIES.keys())

    print("=" * 60)
    print("FRED BACKFILL TO 2000")
    print("=" * 60)
    print(f"Series to backfill: {len(series_ids)}")
    print(f"Start date: {args.start_date}")
    print()

    if not FRED_API_KEY:
        print("ERROR: FRED_API_KEY not set in environment")
        return 1

    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()

    metadata = {}
    if not args.skip_validation:
        print("Validating FRED series IDs...")
        series_ids, invalid, metadata = validate_series_ids(series_ids)
        if invalid:
            print("\nInvalid series IDs detected:")
            for series_id, reason in invalid.items():
                print(f"  - {series_id}: {reason}")
            if args.fail_on_invalid:
                print("ERROR: Invalid series IDs present; aborting.")
                return 1
        print(f"Valid series: {len(series_ids)}")

    conn = get_postgres_connection()
    tags_map = load_series_tags(conn)
    run_id = create_ingest_run(conn, "fred-backfill")

    total_inserted = 0
    total_fetched = 0
    total_attempted = 0
    total_skipped = 0

    for i, series_id in enumerate(series_ids, 1):
        description = FRED_SERIES.get(series_id, "Custom series")
        print(f"[{i}/{len(series_ids)}] {series_id}: {description}")
        total_attempted += 1

        min_date = get_series_min_date(conn, series_id)
        fetch_start = start_date
        meta = metadata.get(series_id)
        if meta and meta.get("observation_start"):
            try:
                obs_start = datetime.strptime(meta["observation_start"], "%Y-%m-%d").date()
                fetch_start = max(fetch_start, obs_start)
            except ValueError:
                pass

        if min_date:
            min_date_val = min_date.date() if hasattr(min_date, "date") else min_date
            if min_date_val <= fetch_start:
                print("  Already has history to start_date, skipping")
                total_skipped += 1
                continue
            end_date = (min_date_val - timedelta(days=1)).isoformat()
        else:
            end_date = None

        if min_date:
            print(f"  Backfilling missing history through {end_date}")
        elif not min_date:
            print("  Series not found in DB, backfilling full history")

        df = fetch_fred_series(series_id, fetch_start.isoformat(), end_date)

        if df.empty:
            print("  No data available")
            total_skipped += 1
            time.sleep(0.3)
            continue

        fetched = len(df)
        tags = tags_map.get(series_id) or SERIES_TAGS.get(series_id)
        inserted = insert_fred_data(conn, series_id, df, tags, run_id)

        print(f"  Fetched: {fetched:,} | Inserted: {inserted:,}")
        total_fetched += fetched
        total_inserted += inserted

        # Rate limit: FRED allows ~120 requests/minute
        time.sleep(0.5)

    complete_ingest_run(
        conn,
        run_id,
        "success",
        total_attempted,
        total_inserted,
        total_skipped,
        0,
    )
    conn.close()

    print()
    print("=" * 60)
    print("BACKFILL COMPLETE")
    print("=" * 60)
    print(f"Total fetched: {total_fetched:,}")
    print(f"Total inserted: {total_inserted:,}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
