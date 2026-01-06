#!/usr/bin/env python3
"""
ZINC-FUSION Data Worker - Comprehensive Data Ingestion
=======================================================
Handles all scheduled data ingestion for the Big-11 specialists:

DAILY:
- FRED economic indicators (rates, FX, inflation, etc.)
- EPA RIN prices (D4 biodiesel RINs)

WEEKLY:
- CFTC COT positioning (Tuesday release)
- USDA Export Sales (Thursday release)

MONTHLY:
- USDA WASDE supply/demand (12th of month)

DEPLOYMENT: Railway cron job with multiple schedules.

Usage:
    python scripts/ingest_all_sources.py --mode daily
    python scripts/ingest_all_sources.py --mode weekly
    python scripts/ingest_all_sources.py --mode monthly
    python scripts/ingest_all_sources.py --mode all --dry-run
    python scripts/ingest_all_sources.py --source fred --backfill --start-date 2020-01-01
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Load environment variables from .env file (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required in Railway (env vars set directly)

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
import requests

# =============================================================================
# LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE
# =============================================================================

def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


# =============================================================================
# FRED API (Daily economic data)
# =============================================================================

FRED_API_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Comprehensive FRED series for Big-11 specialists
# Organized by specialist bucket for clarity
FRED_SERIES = {
    # =========================================================================
    # FED SPECIALIST - Interest Rates, Yields, Monetary Policy
    # =========================================================================
    # Fed Funds
    "DFF": "Fed Funds Effective Rate (Daily)",
    "FEDFUNDS": "Fed Funds Rate (Monthly)",
    "DFEDTARL": "Fed Funds Target Lower",
    "DFEDTARU": "Fed Funds Target Upper",
    # Treasury Yields - Full Curve
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
    # Yield Spreads
    "T10Y2Y": "10Y-2Y Spread (Yield Curve)",
    "T10Y3M": "10Y-3M Spread",
    "T10YIE": "10Y Breakeven Inflation",
    "TEDRATE": "TED Spread",
    # Other Rates
    "SOFR": "SOFR Rate",
    "DPRIME": "Prime Rate",
    "MORTGAGE30US": "30-Year Mortgage Rate",
    # Fed Balance Sheet
    "WALCL": "Fed Total Assets",
    "WRESBAL": "Reserve Balances",
    "RRPONTSYD": "Reverse Repo",
    "TOTRESNS": "Total Reserves",
    "BOGMBASE": "Monetary Base",
    "M2SL": "M2 Money Stock",
    # Employment
    "PAYEMS": "Nonfarm Payrolls",
    "UNRATE": "Unemployment Rate",
    "MANEMP": "Manufacturing Employment",
    "ICSA": "Initial Jobless Claims (Weekly)",
    "CCSA": "Continued Claims (Weekly)",
    # Inflation
    "CPIAUCSL": "CPI All Urban",
    "CPILFESL": "Core CPI",
    "PCEPI": "PCE Price Index",
    "PCEPILFE": "Core PCE",
    "PPIACO": "PPI All Commodities",
    # GDP & Output
    "GDP": "Nominal GDP",
    "GDPC1": "Real GDP",
    "INDPRO": "Industrial Production",
    # Consumer
    "PCE": "Personal Consumption",
    "RSXFS": "Retail Sales",
    "UMCSENT": "Consumer Sentiment",
    # Housing
    "HOUST": "Housing Starts",
    "PERMIT": "Building Permits",
    # Credit
    "BUSLOANS": "Business Loans",
    "DRCCLACBS": "Credit Card Delinquency",

    # =========================================================================
    # FX SPECIALIST - Exchange Rates
    # =========================================================================
    # Major Pairs
    "DEXBZUS": "USD/BRL (Brazil)",
    "DEXCHUS": "USD/CNY (China)",
    "DEXUSEU": "USD/EUR",
    "DEXUSUK": "USD/GBP",
    "DEXJPUS": "USD/JPY",
    "DEXCAUS": "USD/CAD",
    "DEXMXUS": "USD/MXN",
    # Asian Currencies
    "DEXKOUS": "USD/KRW (Korea)",
    "DEXINUS": "USD/INR (India)",
    "DEXMAUS": "USD/MYR (Malaysia)",
    "DEXSFUS": "USD/SGD (Singapore)",
    "DEXTHUS": "USD/THB (Thailand)",
    "DEXHKUS": "USD/HKD (Hong Kong)",
    "DEXTAUS": "USD/TWD (Taiwan)",
    # Other
    "DEXUSAL": "USD/AUD",
    "DEXNOUS": "USD/NOK",
    "DEXSZUS": "USD/CHF",
    "DEXSIUS": "USD/SEK",
    # Trade-Weighted Indices
    "DTWEXBGS": "Trade-Weighted USD (Broad)",
    "DTWEXAFEGS": "USD vs Advanced FX",
    "DTWEXEMEGS": "USD vs EM FX",

    # =========================================================================
    # ENERGY SPECIALIST - Oil, Gas, Fuels
    # =========================================================================
    "DCOILWTICO": "WTI Crude Oil",
    "DCOILBRENTEU": "Brent Crude Oil",
    "DHHNGSP": "Henry Hub Natural Gas",
    "DHOILNYH": "Heating Oil NY Harbor",
    "DDFUELUSGULF": "Diesel Fuel Gulf",
    "GASREGW": "Regular Gasoline (Weekly)",
    "GASDESW": "Diesel (Weekly)",

    # =========================================================================
    # CRUSH SPECIALIST - Soybean Complex & Commodities
    # =========================================================================
    "PSOILUSDM": "Soybean Oil Price",
    "PSOYBUSDM": "Soybeans Price",
    "PMAIZMTUSDM": "Corn Price",
    "PWHEAMTUSDM": "Wheat Price",
    "PPOILUSDM": "Palm Oil Price",
    "PSUNOUSDM": "Sunflower Oil Price",
    "PRICENPQUSDM": "Rice Price",
    "PROILUSDM": "Rapeseed Oil Price",
    "PCOPPUSDM": "Copper Price",
    "PNGASEUUSDM": "EU Natural Gas Price",
    # PPI for Oils
    "WPU01830161": "PPI Soybean Oil",
    "WPU01830171": "PPI Vegetable Oils",
    "WPU057303": "PPI Fats & Oils",
    "WPU06140341": "PPI Biodiesel",
    "PCU311224311224": "PPI Soybean Processing",

    # =========================================================================
    # VOLATILITY SPECIALIST - VIX, Stress, Credit
    # =========================================================================
    "VIXCLS": "VIX Index",
    "OVXCLS": "Oil VIX (OVX)",
    "STLFSI4": "St. Louis Financial Stress",
    "NFCI": "National Financial Conditions",
    "BAMLH0A0HYM2": "High Yield OAS",
    "BAMLC0A0CM": "Corporate Bond OAS",
    "SP500": "S&P 500",

    # =========================================================================
    # TRUMP EFFECT SPECIALIST - Policy Uncertainty, Trade
    # =========================================================================
    "USEPUINDXD": "US Policy Uncertainty (Daily)",
    "USEPUINDXM": "US Policy Uncertainty (Monthly)",
    "EPUTRADE": "Trade Policy Uncertainty",
    "EMVTRADEPOLEMV": "Equity Volatility: Trade Policy",
    "CHNMAINLANDTPU": "China Trade Policy Uncertainty",
    "B235RC1Q027SBEA": "Customs Duties (Tariff Receipts)",
    "IMPCH": "US Imports from China",

    # =========================================================================
    # CHINA SPECIALIST - China Economic Data
    # =========================================================================
    "CHNCPIALLMINMEI": "China CPI",
    "CHNGDPNQDSMEI": "China GDP",
    "IR3TIB01CNM156N": "China Interbank Rate",
    "XTEXVA01CNM667S": "China Exports",
    "XTIMVA01CNM667S": "China Imports",

    # =========================================================================
    # TRADE - Imports/Exports
    # =========================================================================
    "BOPGSTB": "Trade Balance",
    "EXPGS": "Exports of Goods & Services",
    "IMPGS": "Imports of Goods & Services",
}


def fetch_fred_series(series_id: str, api_key: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Fetch a single FRED series."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date,
    }

    try:
        response = requests.get(FRED_API_BASE, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "observations" not in data:
            return None

        df = pd.DataFrame(data["observations"])
        if len(df) == 0:
            return None

        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["series_id"] = series_id

        return df[["date", "series_id", "value"]].dropna()

    except Exception as e:
        logger.error(f"Failed to fetch FRED {series_id}: {e}")
        return None


def ingest_fred(conn, api_key: str, start_date: str, end_date: str, dry_run: bool = False) -> Dict[str, Any]:
    """Ingest all FRED series."""
    stats = {"source": "fred", "rows_inserted": 0, "series_fetched": 0, "errors": []}

    logger.info(f"Fetching FRED data: {start_date} to {end_date}")

    for series_id, description in FRED_SERIES.items():
        logger.info(f"  {series_id}: {description}")

        df = fetch_fred_series(series_id, api_key, start_date, end_date)

        if df is not None and len(df) > 0:
            stats["series_fetched"] += 1
            logger.info(f"    Got {len(df)} observations")

            if not dry_run:
                rows = upsert_fred_observations(conn, df)
                stats["rows_inserted"] += rows
        else:
            stats["errors"].append(f"No data for {series_id}")

        time.sleep(0.5)  # Rate limiting

    return stats


def upsert_fred_observations(conn, df: pd.DataFrame) -> int:
    """Upsert FRED observations to database."""
    insert_query = """
        INSERT INTO raw.fred_observations_1d (as_of_date, series_id, value, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (as_of_date, series_id)
        DO UPDATE SET value = EXCLUDED.value, ingested_at = EXCLUDED.ingested_at
    """

    batch = [
        (row["date"].date(), row["series_id"], row["value"], "fred_api", datetime.now())
        for _, row in df.iterrows()
    ]

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


# =============================================================================
# EPA RIN PRICES (Daily biofuel data)
# =============================================================================

EPA_RIN_URL = "https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information"


def fetch_epa_rin_prices(start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    Fetch EPA RIN prices.
    Note: EPA doesn't have a public API, so this uses web scraping or OPIS.
    For now, we'll use a simplified approach with available data.
    """
    # EPA RIN data requires either:
    # 1. OPIS API key (paid subscription ~$2000/yr)
    # 2. Web scraping from EPA EMTS (requires registration)
    # 3. Manual CSV download

    # Check if OPIS API key is available
    opis_key = os.getenv("OPIS_API_KEY")
    if opis_key:
        return fetch_opis_rin_prices(opis_key, start_date, end_date)

    logger.warning("No OPIS_API_KEY found - EPA RIN ingestion requires OPIS subscription")
    return None


def fetch_opis_rin_prices(api_key: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Fetch RIN prices from OPIS API."""
    # OPIS API endpoint (placeholder - actual endpoint requires subscription)
    logger.info("OPIS API integration not yet implemented")
    return None


def ingest_epa_rin(conn, start_date: str, end_date: str, dry_run: bool = False) -> Dict[str, Any]:
    """Ingest EPA RIN prices."""
    stats = {"source": "epa_rin", "rows_inserted": 0, "errors": []}

    logger.info(f"Fetching EPA RIN data: {start_date} to {end_date}")

    df = fetch_epa_rin_prices(start_date, end_date)

    if df is not None and len(df) > 0:
        logger.info(f"  Got {len(df)} RIN price records")
        if not dry_run:
            rows = upsert_epa_rin(conn, df)
            stats["rows_inserted"] = rows
    else:
        stats["errors"].append("No RIN data available (need OPIS_API_KEY)")

    return stats


def upsert_epa_rin(conn, df: pd.DataFrame) -> int:
    """Upsert EPA RIN prices to database."""
    insert_query = """
        INSERT INTO raw.epa_rin_prices_1d (as_of_date, rin_type, price, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (as_of_date, rin_type)
        DO UPDATE SET price = EXCLUDED.price, ingested_at = EXCLUDED.ingested_at
    """

    batch = [
        (row["date"], row["rin_type"], row["price"], "opis", datetime.now())
        for _, row in df.iterrows()
    ]

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


# =============================================================================
# CFTC COT (Weekly positioning data)
# =============================================================================

CFTC_CURRENT_URL = "https://www.cftc.gov/dea/newcot/deafut.txt"

# Contract codes for commodities we track
CFTC_CONTRACTS = {
    "007601": "ZL",   # Soybean Oil
    "005602": "ZS",   # Soybeans
    "026603": "ZM",   # Soybean Meal
    "002602": "ZC",   # Corn
    "067651": "CL",   # Crude Oil
}


def fetch_cftc_cot_current() -> Optional[pd.DataFrame]:
    """Fetch current week's CFTC COT data."""
    try:
        response = requests.get(CFTC_CURRENT_URL, timeout=60)
        response.raise_for_status()

        # Parse the comma-separated format (no headers)
        from io import StringIO
        df = pd.read_csv(StringIO(response.text), header=None, low_memory=False)

        # CFTC format columns (positional):
        # 0=Market Name, 1=Date YYMMDD, 2=Date YYYY-MM-DD, 3=Contract Code, ...
        # 7=Open Interest, 8=Prod Long, 9=Prod Short, 10=Swap Long, 11=Swap Short, 12=Swap Spread
        # 13=MMoney Long, 14=MMoney Short, 15=MMoney Spread, ...

        # Extract contract code (column 3) and filter
        df["contract_code"] = df.iloc[:, 3].astype(str).str.strip()
        df = df[df["contract_code"].isin(CFTC_CONTRACTS.keys())].copy()

        if len(df) == 0:
            logger.warning("No matching CFTC contracts found")
            return None

        # Map to our symbol names
        df["symbol"] = df["contract_code"].map(CFTC_CONTRACTS)

        # Extract key columns
        df["report_date"] = pd.to_datetime(df.iloc[:, 2], errors="coerce")
        df["Open_Interest_All"] = pd.to_numeric(df.iloc[:, 7], errors="coerce")
        df["Prod_Merc_Positions_Long_All"] = pd.to_numeric(df.iloc[:, 8], errors="coerce")
        df["Prod_Merc_Positions_Short_All"] = pd.to_numeric(df.iloc[:, 9], errors="coerce")
        df["M_Money_Positions_Long_All"] = pd.to_numeric(df.iloc[:, 13], errors="coerce")
        df["M_Money_Positions_Short_All"] = pd.to_numeric(df.iloc[:, 14], errors="coerce")

        logger.info(f"  Found {len(df)} COT records for: {df['symbol'].unique().tolist()}")
        return df

    except Exception as e:
        logger.error(f"Failed to fetch CFTC COT: {e}")
        import traceback
        traceback.print_exc()
        return None


def ingest_cftc_cot(conn, dry_run: bool = False) -> Dict[str, Any]:
    """Ingest current CFTC COT data."""
    stats = {"source": "cftc_cot", "rows_inserted": 0, "errors": []}

    logger.info("Fetching CFTC COT data (current week)")

    df = fetch_cftc_cot_current()

    if df is not None and len(df) > 0:
        logger.info(f"  Got {len(df)} COT records")
        logger.info(f"  Symbols: {df['symbol'].unique().tolist()}")

        if not dry_run:
            rows = upsert_cftc_cot(conn, df)
            stats["rows_inserted"] = rows
    else:
        stats["errors"].append("No CFTC data available")

    return stats


def upsert_cftc_cot(conn, df: pd.DataFrame) -> int:
    """Upsert CFTC COT data to database."""
    insert_query = """
        INSERT INTO raw.cftc_cot_1w
        (report_date, symbol, open_interest,
         prod_merc_long, prod_merc_short, prod_merc_net,
         managed_money_long, managed_money_short, managed_money_net,
         managed_money_net_pct_oi, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (report_date, symbol)
        DO UPDATE SET
            open_interest = EXCLUDED.open_interest,
            managed_money_net = EXCLUDED.managed_money_net,
            managed_money_net_pct_oi = EXCLUDED.managed_money_net_pct_oi,
            ingested_at = EXCLUDED.ingested_at
    """

    batch = []
    for _, row in df.iterrows():
        oi = row.get("Open_Interest_All", 0) or 0
        mm_long = row.get("M_Money_Positions_Long_All", 0) or 0
        mm_short = row.get("M_Money_Positions_Short_All", 0) or 0
        mm_net = mm_long - mm_short
        mm_pct = (mm_net / oi * 100) if oi > 0 else 0

        pm_long = row.get("Prod_Merc_Positions_Long_All", 0) or 0
        pm_short = row.get("Prod_Merc_Positions_Short_All", 0) or 0
        pm_net = pm_long - pm_short

        batch.append((
            row["report_date"].date(),
            row["symbol"],
            int(oi),
            int(pm_long), int(pm_short), int(pm_net),
            int(mm_long), int(mm_short), int(mm_net),
            float(mm_pct),
            "cftc_weekly",
            datetime.now()
        ))

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=100)
    conn.commit()

    return len(batch)


# =============================================================================
# USDA EXPORT SALES (Weekly)
# =============================================================================

USDA_EXPORT_SALES_URL = "https://apps.fas.usda.gov/export-sales/soybean.htm"


def fetch_usda_export_sales() -> Optional[pd.DataFrame]:
    """
    Fetch USDA FAS Export Sales data.
    Note: Requires web scraping from FAS website.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        }
        response = requests.get(USDA_EXPORT_SALES_URL, headers=headers, timeout=30)
        response.raise_for_status()

        # Parse HTML table - simplified version
        # Full implementation would use BeautifulSoup
        logger.info("USDA Export Sales parsing - checking data availability")

        # For now, return None - need to implement proper HTML parsing
        return None

    except Exception as e:
        logger.error(f"Failed to fetch USDA Export Sales: {e}")
        return None


def ingest_usda_export_sales(conn, dry_run: bool = False) -> Dict[str, Any]:
    """Ingest USDA Export Sales data."""
    stats = {"source": "usda_export_sales", "rows_inserted": 0, "errors": []}

    logger.info("Fetching USDA Export Sales data")

    df = fetch_usda_export_sales()

    if df is not None and len(df) > 0:
        logger.info(f"  Got {len(df)} export sales records")
        if not dry_run:
            rows = upsert_usda_export_sales(conn, df)
            stats["rows_inserted"] = rows
    else:
        stats["errors"].append("USDA Export Sales scraping not yet implemented")

    return stats


def upsert_usda_export_sales(conn, df: pd.DataFrame) -> int:
    """Upsert USDA Export Sales to database."""
    # Implementation would go here
    return 0


# =============================================================================
# USDA WASDE (Monthly)
# =============================================================================

def fetch_usda_wasde() -> Optional[pd.DataFrame]:
    """
    Fetch USDA WASDE data.
    Note: Requires USDA PSD API key or manual download.
    """
    psd_key = os.getenv("USDA_PSD_API_KEY")
    if psd_key:
        return fetch_usda_psd_wasde(psd_key)

    logger.warning("No USDA_PSD_API_KEY found - WASDE ingestion requires PSD API key")
    return None


def fetch_usda_psd_wasde(api_key: str) -> Optional[pd.DataFrame]:
    """Fetch WASDE data from USDA PSD API."""
    # USDA PSD API endpoint
    logger.info("USDA PSD API integration not yet implemented")
    return None


def ingest_usda_wasde(conn, dry_run: bool = False) -> Dict[str, Any]:
    """Ingest USDA WASDE data."""
    stats = {"source": "usda_wasde", "rows_inserted": 0, "errors": []}

    logger.info("Fetching USDA WASDE data")

    df = fetch_usda_wasde()

    if df is not None and len(df) > 0:
        logger.info(f"  Got {len(df)} WASDE records")
        if not dry_run:
            # rows = upsert_usda_wasde(conn, df)
            # stats["rows_inserted"] = rows
            pass
    else:
        stats["errors"].append("WASDE requires USDA_PSD_API_KEY")

    return stats


# =============================================================================
# USDA NASS (Crop Progress, Condition, Crush)
# =============================================================================

NASS_API_BASE = "https://quickstats.nass.usda.gov/api/api_GET"


def fetch_usda_nass(api_key: str, params: Dict, start_year: int, end_year: int) -> Optional[pd.DataFrame]:
    """Fetch data from USDA NASS Quick Stats API."""
    query_params = {
        "key": api_key,
        "year__GE": str(start_year),
        "year__LE": str(end_year),
        "format": "JSON",
        **params
    }

    try:
        response = requests.get(NASS_API_BASE, params=query_params, timeout=60)

        if response.status_code == 401:
            logger.error("Invalid USDA NASS API key")
            return None

        response.raise_for_status()
        data = response.json()

        if "data" not in data:
            return None

        return pd.DataFrame(data["data"])

    except Exception as e:
        logger.error(f"NASS API error: {e}")
        return None


def ingest_usda_nass(conn, api_key: str, dry_run: bool = False) -> Dict[str, Any]:
    """Ingest USDA NASS data (crop progress, condition, crush)."""
    stats = {"source": "usda_nass", "rows_inserted": 0, "categories": [], "errors": []}

    current_year = datetime.now().year

    # Crop Progress
    logger.info("Fetching USDA NASS Crop Progress...")
    df = fetch_usda_nass(api_key, {
        "source_desc": "SURVEY",
        "commodity_desc": "SOYBEANS",
        "statisticcat_desc": "PROGRESS",
        "freq_desc": "WEEKLY",
    }, current_year - 1, current_year)

    if df is not None and len(df) > 0:
        logger.info(f"  Got {len(df)} crop progress records")
        stats["categories"].append("crop_progress")
        # Upsert logic would go here

    # Crop Condition
    logger.info("Fetching USDA NASS Crop Condition...")
    df = fetch_usda_nass(api_key, {
        "source_desc": "SURVEY",
        "commodity_desc": "SOYBEANS",
        "statisticcat_desc": "CONDITION",
        "freq_desc": "WEEKLY",
    }, current_year - 1, current_year)

    if df is not None and len(df) > 0:
        logger.info(f"  Got {len(df)} crop condition records")
        stats["categories"].append("crop_condition")

    return stats


# =============================================================================
# MAIN ORCHESTRATION
# =============================================================================

def run_daily_ingestion(conn, dry_run: bool = False) -> List[Dict]:
    """Run daily data ingestion."""
    results = []

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")  # Get last week

    # FRED
    fred_key = os.getenv("FRED_API_KEY")
    if fred_key:
        results.append(ingest_fred(conn, fred_key, yesterday, today, dry_run))
    else:
        logger.warning("FRED_API_KEY not found - skipping FRED ingestion")
        results.append({"source": "fred", "errors": ["No FRED_API_KEY"]})

    # EPA RIN
    results.append(ingest_epa_rin(conn, yesterday, today, dry_run))

    return results


def run_weekly_ingestion(conn, dry_run: bool = False) -> List[Dict]:
    """Run weekly data ingestion."""
    results = []

    # CFTC COT
    results.append(ingest_cftc_cot(conn, dry_run))

    # USDA Export Sales
    results.append(ingest_usda_export_sales(conn, dry_run))

    # USDA NASS
    nass_key = os.getenv("USDA_NASS_API_KEY")
    if nass_key:
        results.append(ingest_usda_nass(conn, nass_key, dry_run))
    else:
        logger.warning("USDA_NASS_API_KEY not found - skipping NASS ingestion")

    return results


def run_monthly_ingestion(conn, dry_run: bool = False) -> List[Dict]:
    """Run monthly data ingestion."""
    results = []

    # USDA WASDE
    results.append(ingest_usda_wasde(conn, dry_run))

    return results


def main():
    parser = argparse.ArgumentParser(description="ZINC-FUSION Data Ingestion Worker")
    parser.add_argument("--mode", choices=["daily", "weekly", "monthly", "all"],
                       default="daily", help="Ingestion mode")
    parser.add_argument("--source", type=str, help="Specific source to ingest")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    parser.add_argument("--backfill", action="store_true", help="Run historical backfill")
    parser.add_argument("--start-date", type=str, help="Backfill start date (YYYY-MM-DD)")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ZINC-FUSION DATA WORKER")
    logger.info("=" * 60)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("")

    conn = None
    if not args.dry_run:
        conn = get_postgres_connection()

    try:
        all_results = []

        if args.mode in ["daily", "all"]:
            logger.info("--- DAILY INGESTION ---")
            all_results.extend(run_daily_ingestion(conn, args.dry_run))

        if args.mode in ["weekly", "all"]:
            logger.info("--- WEEKLY INGESTION ---")
            all_results.extend(run_weekly_ingestion(conn, args.dry_run))

        if args.mode in ["monthly", "all"]:
            logger.info("--- MONTHLY INGESTION ---")
            all_results.extend(run_monthly_ingestion(conn, args.dry_run))

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("INGESTION SUMMARY")
        logger.info("=" * 60)

        total_rows = 0
        for result in all_results:
            source = result.get("source", "unknown")
            rows = result.get("rows_inserted", 0)
            errors = result.get("errors", [])

            status = "OK" if not errors else f"WARN ({len(errors)} errors)"
            logger.info(f"  {source:20s}: {rows:>6,} rows  [{status}]")
            total_rows += rows

            for err in errors[:3]:  # Show first 3 errors
                logger.warning(f"    - {err}")

        logger.info("")
        logger.info(f"Total rows inserted: {total_rows:,}")

        return 0 if total_rows > 0 or args.dry_run else 1

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
