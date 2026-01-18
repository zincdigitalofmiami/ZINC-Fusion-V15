#!/usr/bin/env python3
"""
Ingest FRED economic release dates as events.

Maps major releases to specialist buckets:
- CPI, PPI, Employment → fed
- Industrial Production, Petroleum → energy  
- Trade, Import/Export → tariff + china
- GDP, Retail Sales, Housing → fed
"""
import os
import requests
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

BASE_URL = "https://api.stlouisfed.org/fred"

# Major releases to track (release_id: (name, specialist))
TRACKED_RELEASES = {
    10: ("Consumer Price Index", "fed"),
    46: ("Producer Price Index", "fed"),
    50: ("Employment Situation", "fed"),
    13: ("Industrial Production", "energy"),
    51: ("US International Trade", "tariff"),
    53: ("Gross Domestic Product", "fed"),
    114: ("Petroleum Weekly", "energy"),
    133: ("Housing Starts", "fed"),
    149: ("FOMC Meeting", "fed"),
    227: ("Advance Monthly Retail Sales", "fed"),
}

def get_release_dates(release_id, months_back=12, months_forward=3):
    """Get release dates for a specific release."""
    start_date = (datetime.now() - timedelta(days=months_back*30)).strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=months_forward*30)).strftime("%Y-%m-%d")
    
    params = {
        "release_id": release_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "realtime_start": start_date,
        "realtime_end": end_date,
        "limit": 1000,
    }
    
    response = requests.get(f"{BASE_URL}/release/dates", params=params)
    if response.status_code == 200:
        return response.json().get("release_dates", [])
    else:
        print(f"  ❌ Error fetching release {release_id}: {response.status_code}")
        return []

def insert_release_events():
    """Insert FRED release dates as events."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    total_inserted = 0
    total_skipped = 0
    
    for release_id, (name, specialist) in TRACKED_RELEASES.items():
        print(f"\nProcessing: {name} (ID: {release_id}) → {specialist}")
        
        dates = get_release_dates(release_id)
        print(f"  Found {len(dates)} release dates")
        
        for date_info in dates:
            release_date_str = date_info.get("date")
            if not release_date_str:
                continue
            
            try:
                release_date = datetime.strptime(release_date_str, "%Y-%m-%d").date()
            except:
                continue
            
            # Create headline
            headline = f"FRED: {name} Release"
            
            # Check if exists
            cur.execute(
                """
                SELECT 1 FROM raw.news_articles_event 
                WHERE source = 'fred_release_calendar' 
                AND headline = %s 
                AND event_date = %s
                """,
                (headline, release_date)
            )
            
            if cur.fetchone():
                total_skipped += 1
                continue
            
            # Insert as event
            cur.execute(
                """
                INSERT INTO raw.news_articles_event
                (headline, source, source_url, published_at, event_date, 
                 bucket_name, specialist_tags, sentiment_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    headline,
                    "fred_release_calendar",
                    f"https://fred.stlouisfed.org/release/{release_id}",
                    datetime.combine(release_date, datetime.min.time()),
                    release_date,
                    specialist,
                    [specialist, "economic_release"],
                    0.0,  # Neutral sentiment (event flag, not news)
                )
            )
            total_inserted += 1
        
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"\n{'='*80}")
    print(f"✅ Inserted {total_inserted} release events")
    print(f"⏭️  Skipped {total_skipped} duplicates")

if __name__ == "__main__":
    insert_release_events()
