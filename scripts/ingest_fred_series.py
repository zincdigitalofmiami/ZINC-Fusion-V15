#!/usr/bin/env python3
"""
Ingest FRED series observations for ZINC-FUSION specialists.

Pulls historical observations for all TARGET_SERIES and inserts
into raw.fred_observations_1d table.
"""
import os
import requests
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv
import time

load_dotenv()
FRED_API_KEY = os.getenv("FRED_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
BASE_URL = "https://api.stlouisfed.org/fred"

# Target series (from discover_fred_series.py)
TARGET_SERIES = {
    # Soybeans / Crush
    "WPU01830131": ("PPI: Soybean Meal", "crush"),
    "WPU01830111": ("PPI: Soybeans", "crush"),
    "WPU01830121": ("PPI: Soybean Oil", "crush"),
    "PSOYBUSDM": ("Global Price: Soybeans", "crush"),
    "PSOILUSDM": ("Global Price: Soybean Oil", "crush"),
    "PSMEAUSDM": ("Global Price: Soybean Meal", "crush"),
    
    # Interest Rates / Fed
    "DFF": ("Federal Funds Rate", "fed"),
    "SOFR": ("Secured Overnight Financing Rate", "fed"),
    "DGS10": ("10-Year Treasury Rate", "fed"),
    "DGS2": ("2-Year Treasury Rate", "fed"),
    "DGS5": ("5-Year Treasury Rate", "fed"),
    "T10Y2Y": ("10Y-2Y Yield Spread", "fed"),
    "T10Y3M": ("10Y-3M Yield Spread", "fed"),
    
    # Fed Indicators
    "UNRATE": ("Unemployment Rate", "fed"),
    "CPILFESL": ("Core CPI", "fed"),
    "PCEPILFE": ("Core PCE", "fed"),
    "M2SL": ("M2 Money Supply", "fed"),
    
    # Energy
    "DCOILWTICO": ("WTI Crude Oil", "energy"),
    "DCOILBRENTEU": ("Brent Crude Oil", "energy"),
    "DHHNGSP": ("Natural Gas Spot", "energy"),
    "GASREGW": ("Gasoline Prices", "energy"),
    "DPROPANEMBTX": ("Propane Prices", "energy"),
    
    # FX
    "DEXCHUS": ("CNY/USD", "fx"),
    "DEXBZUS": ("BRL/USD", "fx"),
    "DEXUSAL": ("USD Index", "fx"),
    
    # China
    "XTIMVA01CNM659S": ("China Imports", "china"),
    "XTEXVA01CNM659S": ("China Exports", "china"),
    
    # Tariff
    "B235RC1Q027SBEA": ("Customs Duties", "tariff"),
    
    # Trump Effect / Uncertainty
    "USEPUINDXD": ("EPU Daily", "trump_effect"),
    "USEPUINDXM": ("EPU Monthly", "trump_effect"),
    "EPUTRADE": ("Trade Policy Uncertainty", "trump_effect"),
    "CHNMAINLANDTPU": ("China TPU", "trump_effect"),
}

def get_observations(series_id, start_date="1990-01-01"):
    """Get observations for a series."""
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "limit": 100000,  # Max allowed
    }
    
    response = requests.get(f"{BASE_URL}/series/observations", params=params)
    if response.status_code == 200:
        return response.json().get("observations", [])
    else:
        print(f"  ❌ API Error {response.status_code}: {response.text[:100]}")
        return []

def ingest_series(series_id, name, specialist):
    """Ingest observations for a single series."""
    print(f"\n{series_id} ({specialist}): {name}")
    print("  Fetching observations...")
    
    observations = get_observations(series_id)
    
    if not observations:
        print("  ⚠️  No observations returned")
        return 0, 0
    
    print(f"  Found {len(observations)} observations")
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    inserted = 0
    skipped = 0
    
    for obs in observations:
        date_str = obs.get("date")
        value_str = obs.get("value")
        
        # Skip missing/invalid values
        if not date_str or value_str == ".":
            continue
        
        try:
            obs_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            value = float(value_str)
        except (ValueError, TypeError):
            continue
        
        # Upsert
        try:
            cur.execute(
                """
                INSERT INTO raw.fred_observations_1d 
                (series_id, observation_date, value)
                VALUES (%s, %s, %s)
                ON CONFLICT (series_id, observation_date) 
                DO UPDATE SET value = EXCLUDED.value
                """,
                (series_id, obs_date, value)
            )
            inserted += 1
        except Exception as e:
            skipped += 1
            continue
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"  ✅ Inserted/Updated: {inserted} | Skipped: {skipped}")
    return inserted, skipped

def main():
    print("FRED Series Ingestion for ZINC-FUSION")
    print("=" * 80)
    
    total_inserted = 0
    total_skipped = 0
    success_count = 0
    
    for i, (series_id, (name, specialist)) in enumerate(TARGET_SERIES.items(), 1):
        print(f"\n[{i}/{len(TARGET_SERIES)}]", end=" ")
        
        try:
            inserted, skipped = ingest_series(series_id, name, specialist)
            total_inserted += inserted
            total_skipped += skipped
            success_count += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        # Rate limit: 120 requests/minute
        if i % 10 == 0:
            print("\n  ⏸️  Rate limit pause (5 seconds)...")
            time.sleep(5)
    
    print("\n" + "=" * 80)
    print(f"\n✅ Complete:")
    print(f"  Series processed: {success_count}/{len(TARGET_SERIES)}")
    print(f"  Observations inserted/updated: {total_inserted:,}")
    print(f"  Observations skipped: {total_skipped:,}")

if __name__ == "__main__":
    main()
