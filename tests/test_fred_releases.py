#!/usr/bin/env python3
"""Test FRED release calendar API."""
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
FRED_API_KEY = os.getenv("FRED_API_KEY")

if not FRED_API_KEY:
    print("❌ FRED_API_KEY not found in .env")
    exit(1)

# FRED API base
BASE_URL = "https://api.stlouisfed.org/fred"

print("Testing FRED Release Calendar API")
print("=" * 80)

# Get all releases (use default realtime params)
params = {
    "api_key": FRED_API_KEY,
    "file_type": "json",
}

# Get all releases
response = requests.get(f"{BASE_URL}/releases", params=params)
print(f"\nAPI Response Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    releases = data.get("releases", [])
    
    print(f"Total Releases: {len(releases)}")
    print("\nKey Economic Releases:")
    print("-" * 80)
    
    # Filter for major releases
    major_releases = {
        "Consumer Price Index": "fed",
        "Employment Situation": "fed",
        "Producer Price Index": "fed",
        "FOMC": "fed",
        "Gross Domestic Product": "fed",
        "Industrial Production": "energy",
        "Petroleum": "energy",
        "EIA": "energy",
        "Import": "china",
        "Export": "china",
        "Trade": "tariff",
        "Housing": "fed",
        "Retail Sales": "fed",
    }
    
    for release in releases[:20]:  # Show first 20
        name = release.get("name", "")
        release_id = release.get("id", "")
        link = release.get("link", "")
        
        # Map to specialist
        specialist = None
        for keyword, spec in major_releases.items():
            if keyword.lower() in name.lower():
                specialist = spec
                break
        
        if specialist or len(releases) <= 20:
            print(f"\n{name}")
            print(f"  ID: {release_id}")
            print(f"  Link: {link}")
            if specialist:
                print(f"  Specialist: {specialist}")
    
    print("\n" + "=" * 80)
    print("\nNext: Test release dates API for specific releases")
    
    # Test getting release dates for CPI (release_id=10)
    print("\n" + "-" * 80)
    print("Testing CPI Release Dates (release_id=10):")
    
    dates_params = {
        "release_id": 10,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "limit": 10,
        "sort_order": "desc",
    }
    
    dates_response = requests.get(f"{BASE_URL}/release/dates", params=dates_params)
    if dates_response.status_code == 200:
        dates_data = dates_response.json()
        release_dates = dates_data.get("release_dates", [])
        
        print(f"\nUpcoming/Recent CPI Release Dates:")
        for rd in release_dates[:5]:
            print(f"  {rd.get('date')} - Release ID: {rd.get('release_id')}")
    
else:
    print(f"❌ API Error: {response.text}")

print("\n" + "=" * 80)
print("\n✅ FRED Release Calendar Strategy:")
print("  1. Track ~15 major releases (CPI, NFP, GDP, etc.)")
print("  2. Create event flags for training (days until/since release)")
print("  3. Map each release to specialist bucket")
print("  4. Use as regime-aware features (pre/post-release volatility)")
