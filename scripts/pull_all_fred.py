#!/usr/bin/env python3
"""Pull ALL FRED series for missing specialists into DuckDB."""

import os
import sys
import duckdb
from datetime import datetime

# Check for fredapi
try:
    from fredapi import Fred
except ImportError:
    print("Installing fredapi...")
    os.system("pip install fredapi")
    from fredapi import Fred

# FRED API key - check environment
FRED_API_KEY = os.environ.get("FRED_API_KEY")
if not FRED_API_KEY:
    # Try common locations
    for f in [".env", "../.env", os.path.expanduser("~/.fred_api_key")]:
        try:
            with open(f) as fh:
                for line in fh:
                    if "FRED_API_KEY" in line:
                        FRED_API_KEY = line.split("=")[1].strip().strip("\"'")
                        break
        except:
            pass

if not FRED_API_KEY:
    print("ERROR: FRED_API_KEY not found. Set it in environment or .env file")
    print("Get your key at: https://fred.stlouisfed.org/docs/api/api_key.html")
    sys.exit(1)

print(f"Using FRED API key: {FRED_API_KEY[:8]}...")

# Initialize FRED client
fred = Fred(api_key=FRED_API_KEY)

# ALL series we need for complete specialist coverage
FRED_SERIES = {
    # Trade/Tariff Policy Uncertainty
    "EPUTRADE": "Economic Policy Uncertainty - Trade",
    # Vegetable Oils (Global Prices - Substitutes & Palm)
    "PROILUSDM": "Rapeseed Oil, Global Price $/MT",
    "PSUNOUSDM": "Sunflower Oil, Global Price $/MT",
    "PPOILUSDM": "Palm Oil, Global Price $/MT",
    "PSOILUSDM": "Soybean Oil, Global Price $/MT",
    # PPI Indices for oils
    "WPU01830171": "PPI - Canola Oil",
    "WPU01830161": "PPI - Sunflower Oil",
    # FX - Trade Weighted Dollar
    "DTWEXBGS": "Trade Weighted Dollar Index (Broad)",
    "DTWEXAFEGS": "Trade Weighted Dollar (Advanced Foreign Economies)",
    "DTWEXEMEGS": "Trade Weighted Dollar (Emerging Markets)",
    # FX - Major pairs
    "DEXUSEU": "US/Euro Exchange Rate",
    "DEXCHUS": "China Yuan per USD",
    "DEXBZUS": "Brazil Real per USD",
    "DEXMXUS": "Mexico Peso per USD",
    "DEXCAUS": "Canada Dollar per USD",
    "DEXINUS": "India Rupee per USD",
    "DEXMAUS": "Malaysia Ringgit per USD",
    # Fed/Monetary
    "DFF": "Fed Funds Effective Rate",
    "SOFR": "Secured Overnight Financing Rate",
    "T10Y2Y": "10Y-2Y Treasury Spread",
    "T10Y3M": "10Y-3M Treasury Spread",
    "WALCL": "Fed Balance Sheet",
    # Volatility/Risk
    "VIXCLS": "CBOE VIX",
    "STLFSI4": "St Louis Financial Stress Index",
    "NFCI": "Chicago Fed National Financial Conditions",
    # Energy
    "DCOILWTICO": "WTI Crude Oil",
    "DCOILBRENTEU": "Brent Crude Oil",
    "DHHNGSP": "Henry Hub Natural Gas",
    # Macro
    "CPIAUCSL": "CPI All Urban Consumers",
    "UNRATE": "Unemployment Rate",
    "PAYEMS": "Nonfarm Payrolls",
    "INDPRO": "Industrial Production Index",
    "RSXFS": "Retail Sales",
    # China Economy
    "CHNGDPNQDSMEI": "China GDP",
    "XTEXVA01CNM667S": "China Exports",
    "XTIMVA01CNM667S": "China Imports",
    # Agricultural Commodities
    "PMAIZMTUSDM": "Corn Global Price",
    "PWHEAMTUSDM": "Wheat Global Price",
    "PSOYBUSDM": "Soybeans Global Price",
    "PRICENPQUSDM": "Rice Global Price",
    "PNGASEUUSDM": "Natural Gas EU Price",
}

# Connect to DuckDB
db_path = "data/fusion.db"
print(f"\nConnecting to {db_path}...")
con = duckdb.connect(db_path)

# Ensure schema and table exist
con.execute("CREATE SCHEMA IF NOT EXISTS raw")
con.execute(
    """
    CREATE TABLE IF NOT EXISTS raw.fred_observations_1d (
        as_of_date DATE,
        series_id VARCHAR,
        value DOUBLE,
        PRIMARY KEY (as_of_date, series_id)
    )
"""
)

# Pull each series
success_count = 0
fail_count = 0

for series_id, description in FRED_SERIES.items():
    print(f"\nPulling {series_id}: {description}...")
    try:
        data = fred.get_series(series_id)
        if data is None or len(data) == 0:
            print(f"  ⚠ No data for {series_id}")
            fail_count += 1
            continue

        # Convert to DataFrame
        df = data.reset_index()
        df.columns = ["as_of_date", "value"]
        df["series_id"] = series_id
        df = df[["as_of_date", "series_id", "value"]]
        df = df.dropna()

        print(
            f"  Got {len(df)} observations from {df['as_of_date'].min().date()} to {df['as_of_date'].max().date()}"
        )

        # Delete existing and insert fresh
        con.execute(
            """
            DELETE FROM raw.fred_observations_1d 
            WHERE series_id = ?
        """,
            [series_id],
        )

        con.execute(
            """
            INSERT INTO raw.fred_observations_1d (as_of_date, series_id, value)
            SELECT as_of_date::DATE, series_id, value FROM df
        """
        )

        print(f"  ✓ Loaded {len(df)} rows")
        success_count += 1

    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        fail_count += 1

# Show summary
print("\n" + "=" * 70)
print(f"FRED DATA PULL COMPLETE: {success_count} succeeded, {fail_count} failed")
print("=" * 70)

result = con.execute(
    """
    SELECT 
        series_id,
        COUNT(*) as rows,
        MIN(as_of_date) as first_date,
        MAX(as_of_date) as last_date
    FROM raw.fred_observations_1d
    GROUP BY series_id
    ORDER BY series_id
"""
).fetchdf()

print(result.to_string())

total = con.execute("SELECT COUNT(*) FROM raw.fred_observations_1d").fetchone()[0]
series_count = con.execute(
    "SELECT COUNT(DISTINCT series_id) FROM raw.fred_observations_1d"
).fetchone()[0]
print(f"\nTOTAL: {total:,} observations across {series_count} series")

con.close()
print("\n✓ Done!")
