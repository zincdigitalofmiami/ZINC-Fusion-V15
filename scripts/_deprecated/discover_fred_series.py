#!/usr/bin/env python3
"""
Ingest key FRED series from Federal Reserve categories.

Categories to pull:
- Interest rates (category 46) → fed specialist
- Yield curve data → fed specialist  
- Commodities (category 32217) → crush/energy/palm specialists
- Soybeans/beans → crush specialist
"""
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
FRED_API_KEY = os.getenv("FRED_API_KEY")
BASE_URL = "https://api.stlouisfed.org/fred"

# Key series to ingest (series_id: (name, specialist))
TARGET_SERIES = {
    # Soybeans / Crush
    "WPU01830131": ("PPI: Soybean Meal", "crush"),
    "WPU01830111": ("PPI: Soybeans", "crush"),
    "WPU01830121": ("PPI: Soybean Oil", "crush"),
    
    # Interest Rates / Fed
    "DFF": ("Federal Funds Rate", "fed"),
    "SOFR": ("Secured Overnight Financing Rate", "fed"),
    "DGS10": ("10-Year Treasury Constant Maturity Rate", "fed"),
    "DGS2": ("2-Year Treasury Constant Maturity Rate", "fed"),
    "DGS5": ("5-Year Treasury Constant Maturity Rate", "fed"),
    "T10Y2Y": ("10-Year Treasury Minus 2-Year (Yield Spread)", "fed"),
    "T10Y3M": ("10-Year Treasury Minus 3-Month (Yield Spread)", "fed"),
    
    # Additional Fed indicators
    "UNRATE": ("Unemployment Rate", "fed"),
    "CPILFESL": ("Core CPI (ex Food & Energy)", "fed"),
    "PCEPILFE": ("Core PCE Price Index", "fed"),
    "M2SL": ("M2 Money Supply", "fed"),
    
    # Energy
    "DCOILWTICO": ("WTI Crude Oil Price", "energy"),
    "DCOILBRENTEU": ("Brent Crude Oil Price", "energy"),
    "DHHNGSP": ("Henry Hub Natural Gas Spot Price", "energy"),
    "GASREGW": ("US Regular Gasoline Prices", "energy"),
    "DPROPANEMBTX": ("Propane Prices", "energy"),
    
    # FX
    "DEXCHUS": ("China/US Exchange Rate", "fx"),
    "DEXBZUS": ("Brazil/US Exchange Rate", "fx"),
    "DEXUSAL": ("US Dollar Index", "fx"),
    
    # China Trade
    "XTIMVA01CNM659S": ("China Imports", "china"),
    "XTEXVA01CNM659S": ("China Exports", "china"),
    
    # Tariffs
    "B235RC1Q027SBEA": ("Customs Duties (Tariff Receipts)", "tariff"),
    
    # Trump Effect / Policy Uncertainty
    "USEPUINDXD": ("US Economic Policy Uncertainty Index (Daily)", "trump_effect"),
    "USEPUINDXM": ("US Economic Policy Uncertainty Index (Monthly)", "trump_effect"),
    "EPUTRADE": ("Trade Policy Uncertainty Index", "trump_effect"),
    "CHNMAINLANDTPU": ("China Trade Policy Uncertainty", "trump_effect"),
}

def get_category_series(category_id, tag=None, limit=100):
    """Get series from a FRED category with optional tag filter."""
    params = {
        "category_id": category_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "limit": limit,
        "order_by": "popularity",
        "sort_order": "desc",
    }
    
    if tag:
        params["tag_names"] = tag
    
    response = requests.get(f"{BASE_URL}/category/series", params=params)
    if response.status_code == 200:
        return response.json().get("seriess", [])
    return []

def check_series_exists(series_id):
    """Check if series exists in FRED."""
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
    }
    
    response = requests.get(f"{BASE_URL}/series", params=params)
    return response.status_code == 200

def main():
    print("FRED Series Discovery for ZINC-FUSION Specialists")
    print("=" * 80)
    
    # Check target series availability
    print("\n1. Checking TARGET_SERIES availability:")
    print("-" * 80)
    
    available = []
    missing = []
    
    for series_id, (name, specialist) in TARGET_SERIES.items():
        exists = check_series_exists(series_id)
        status = "✅" if exists else "❌"
        print(f"{status} {series_id:20} | {specialist:15} | {name}")
        
        if exists:
            available.append((series_id, name, specialist))
        else:
            missing.append(series_id)
    
    print(f"\n✅ Available: {len(available)}")
    print(f"❌ Missing: {len(missing)}")
    if missing:
        print(f"   Missing series: {', '.join(missing)}")
    
    # Discover additional commodity series
    print("\n2. Discovering Commodities Category (32217):")
    print("-" * 80)
    
    commodity_series = get_category_series(32217, limit=50)
    print(f"Found {len(commodity_series)} commodity series")
    
    relevant_commodities = []
    for series in commodity_series[:20]:  # Show top 20
        series_id = series.get("id", "")
        title = series.get("title", "")
        
        # Filter for relevant commodities
        keywords = ["soy", "oil", "palm", "corn", "wheat", "crude", "gas", "diesel", "biodiesel"]
        if any(kw in title.lower() for kw in keywords):
            print(f"  {series_id:20} | {title[:60]}")
            
            # Auto-map to specialist
            specialist = None
            if "soy" in title.lower():
                specialist = "crush"
            elif "crude" in title.lower() or "oil" in title.lower():
                specialist = "energy"
            elif "palm" in title.lower():
                specialist = "palm"
            
            if specialist:
                relevant_commodities.append((series_id, title, specialist))
    
    # Discover beans tag series
    print("\n3. Discovering 'beans' tagged series:")
    print("-" * 80)
    
    params = {
        "tag_names": "beans",
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "limit": 30,
        "order_by": "popularity",
        "sort_order": "desc",
    }
    
    response = requests.get(f"{BASE_URL}/tags/series", params=params)
    if response.status_code == 200:
        beans_series = response.json().get("seriess", [])
        print(f"Found {len(beans_series)} beans-tagged series")
        
        for series in beans_series[:15]:
            series_id = series.get("id", "")
            title = series.get("title", "")
            print(f"  {series_id:20} | {title[:60]}")
    
    # Output ingestion script
    print("\n" + "=" * 80)
    print("\n✅ Next Steps:")
    print("  1. Run: python scripts/ingest_fred_series.py (to pull observations)")
    print("  2. Add newly discovered series to TARGET_SERIES dict")
    print("  3. Update src/fusion/ingestion/router.py with new mappings")
    
    # Write discovered series to file
    with open("data/fred_discovered_series.txt", "w") as f:
        f.write("# FRED Series Discovered for ZINC-FUSION\n\n")
        f.write("## Target Series (Already Mapped)\n")
        for series_id, name, specialist in available:
            f.write(f"{series_id},{name},{specialist}\n")
        
        f.write("\n## Commodities Category\n")
        for series_id, title, specialist in relevant_commodities:
            f.write(f"{series_id},{title},{specialist}\n")
    
    print(f"\n📝 Discovery results written to: data/fred_discovered_series.txt")

if __name__ == "__main__":
    main()
