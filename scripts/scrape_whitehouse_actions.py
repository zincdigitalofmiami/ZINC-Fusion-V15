#!/usr/bin/env python3
"""
ZINC-FUSION-V15: WhiteHouse Actions Scraper

Scrapes presidential actions from whitehouse.gov and populates
alt.legislation_1d table.

Sources:
- Executive Orders
- Presidential Memoranda
- Proclamations
- Nominations/Appointments

Also pulls from Federal Register Presidential Documents.
"""

import os
import re
import json
import hashlib
import sys
from pathlib import Path
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Add src to path for shared tagging module
_src_path = Path(__file__).parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from fusion.tagging import classify_specialists

DATABASE_URL = os.getenv("DATABASE_URL")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def generate_row_hash(action_date: str, action_type: str, title: str) -> str:
    """Generate unique hash for deduplication."""
    content = f"{action_date}|{action_type}|{title}"
    return hashlib.sha256(content.encode()).hexdigest()


def extract_date_from_url(url: str) -> Optional[str]:
    """Extract date from whitehouse.gov URL pattern: /YYYY/MM/slug/"""
    match = re.search(r'/(\d{4})/(\d{2})/', url)
    if match:
        return f"{match.group(1)}-{match.group(2)}-01"
    return None


def scrape_presidential_actions_page(url: str, action_type: str) -> List[Dict]:
    """Scrape a whitehouse.gov presidential actions page."""
    actions = []
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        html = response.text
        
        # Pattern to match links to individual actions
        # Format: /presidential-actions/YYYY/MM/slug/
        patterns = [
            r'<a[^>]*href="(https://www\.whitehouse\.gov/presidential-actions/\d{4}/\d{2}/[^"]+)"[^>]*>([^<]+)</a>',
            r'<a[^>]*href="(/presidential-actions/\d{4}/\d{2}/[^"]+)"[^>]*>([^<]+)</a>',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                link = match[0]
                title = match[1].strip()
                
                # Make absolute URL
                if link.startswith('/'):
                    link = f"https://www.whitehouse.gov{link}"
                
                # Skip navigation items
                if len(title) < 15 or title in ['Read More', 'View All', 'Read']:
                    continue
                
                # Extract date from URL
                action_date = extract_date_from_url(link)
                if not action_date:
                    continue
                
                actions.append({
                    'action_date': action_date,
                    'action_type': action_type,
                    'title': title,
                    'url': link,
                    'source': 'whitehouse.gov',
                })
        
        print(f"  Found {len(actions)} actions from {url}")
        
    except Exception as e:
        print(f"  Error scraping {url}: {e}")
    
    return actions


def scrape_whitehouse_rss() -> List[Dict]:
    """Scrape whitehouse.gov RSS feed for statements."""
    actions = []
    rss_url = "https://www.whitehouse.gov/briefing-room/statements-releases/feed/"
    
    try:
        response = requests.get(rss_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        # Parse RSS items
        items = re.findall(r'<item>[\s\S]*?</item>', response.text)
        
        for item_xml in items[:50]:  # Last 50 items
            title_match = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>', item_xml)
            link_match = re.search(r'<link>(.*?)</link>', item_xml)
            date_match = re.search(r'<pubDate>(.*?)</pubDate>', item_xml)
            
            if title_match and link_match:
                title = (title_match.group(1) or title_match.group(2) or "").strip()
                link = link_match.group(1) or ""
                
                # Parse date
                action_date = datetime.now().strftime('%Y-%m-%d')
                if date_match:
                    try:
                        pub_date = datetime.strptime(date_match.group(1)[:25], '%a, %d %b %Y %H:%M:%S')
                        action_date = pub_date.strftime('%Y-%m-%d')
                    except:
                        pass
                
                # Classify type
                title_lower = title.lower()
                if 'executive order' in title_lower:
                    action_type = 'executive_order'
                elif 'proclamation' in title_lower:
                    action_type = 'proclamation'
                elif 'memorandum' in title_lower or 'memo' in title_lower:
                    action_type = 'memorandum'
                elif 'nomination' in title_lower or 'appoint' in title_lower:
                    action_type = 'nomination'
                elif 'fact sheet' in title_lower:
                    action_type = 'fact_sheet'
                else:
                    action_type = 'statement'
                
                actions.append({
                    'action_date': action_date,
                    'action_type': action_type,
                    'title': title,
                    'url': link,
                    'source': 'whitehouse_rss',
                })
        
        print(f"  Found {len(actions)} actions from RSS feed")
        
    except Exception as e:
        print(f"  Error scraping RSS: {e}")
    
    return actions


def import_from_federal_register(conn) -> int:
    """Import presidential documents from Federal Register."""
    cur = conn.cursor()
    
    # Get presidential documents not yet in whitehouse_actions_event
    cur.execute("""
        SELECT 
            event_date,
            document_type,
            title,
            source_url,
            abstract
        FROM alt.legislation_1d
        WHERE document_type = 'Presidential Document'
          AND NOT EXISTS (
              SELECT 1 FROM alt.legislation_1d wae
              WHERE wae.title = legislation_federal_register_1d.title
                AND wae.action_date = legislation_federal_register_1d.event_date
          )
        ORDER BY event_date DESC
    """)
    
    fed_reg_docs = cur.fetchall()
    print(f"  Found {len(fed_reg_docs)} Federal Register presidential documents to import")
    
    inserted = 0
    for doc in fed_reg_docs:
        event_date, doc_type, title, source_url, abstract = doc
        
        # Classify action type from title
        title_lower = (title or "").lower()
        if 'executive order' in title_lower:
            action_type = 'executive_order'
        elif 'proclamation' in title_lower:
            action_type = 'proclamation'
        elif 'memorandum' in title_lower:
            action_type = 'memorandum'
        elif 'nomination' in title_lower or 'appoint' in title_lower:
            action_type = 'nomination'
        else:
            action_type = 'presidential_document'
        
        row_hash = generate_row_hash(str(event_date), action_type, title or "")
        
        try:
            cur.execute("""
                INSERT INTO alt.legislation_1d
                (action_date, action_type, title, url, summary, source_url, row_hash, 
                 event_date, scraped_at, validation_status, specialist_tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), 'validated', %s)
                ON CONFLICT (action_date, action_type, title) DO NOTHING
            """, (
                event_date,
                action_type,
                title,
                source_url,
                abstract,
                source_url,
                row_hash,
                event_date,
                ['trump_effect', 'tariff'],
            ))
            inserted += 1
        except Exception as e:
            print(f"  Error inserting Federal Register doc: {e}")
    
    conn.commit()
    return inserted


def main():
    print("\n" + "=" * 70)
    print("ZINC-FUSION-V15: WHITEHOUSE ACTIONS SCRAPER")
    print("=" * 70)
    
    conn = get_connection()
    cur = conn.cursor()
    print("✅ Connected to database")
    
    # Check current state
    cur.execute("SELECT COUNT(*) FROM alt.legislation_1d")
    existing_count = cur.fetchone()[0]
    print(f"📊 Current whitehouse_actions_event rows: {existing_count}")
    
    all_actions = []
    
    # ==========================================================================
    # STEP 1: Import from Federal Register
    # ==========================================================================
    print("\n" + "=" * 60)
    print("STEP 1: Import Presidential Documents from Federal Register")
    print("=" * 60)
    
    fed_reg_count = import_from_federal_register(conn)
    print(f"  ✅ Imported {fed_reg_count} Federal Register documents")
    
    # ==========================================================================
    # STEP 2: Scrape WhiteHouse pages
    # ==========================================================================
    print("\n" + "=" * 60)
    print("STEP 2: Scrape WhiteHouse.gov Pages")
    print("=" * 60)
    
    pages_to_scrape = [
        ("https://www.whitehouse.gov/presidential-actions/executive-orders/", "executive_order"),
        ("https://www.whitehouse.gov/presidential-actions/presidential-memoranda/", "memorandum"),
        ("https://www.whitehouse.gov/presidential-actions/proclamations/", "proclamation"),
        ("https://www.whitehouse.gov/presidential-actions/nominations-appointments/", "nomination"),
    ]
    
    for url, action_type in pages_to_scrape:
        print(f"\n  Scraping {action_type}...")
        actions = scrape_presidential_actions_page(url, action_type)
        all_actions.extend(actions)
    
    # ==========================================================================
    # STEP 3: Scrape RSS Feed
    # ==========================================================================
    print("\n" + "=" * 60)
    print("STEP 3: Scrape WhiteHouse RSS Feed")
    print("=" * 60)
    
    rss_actions = scrape_whitehouse_rss()
    all_actions.extend(rss_actions)
    
    print(f"\n📊 Total actions collected: {len(all_actions)}")
    
    # ==========================================================================
    # STEP 4: Insert into database
    # ==========================================================================
    print("\n" + "=" * 60)
    print("STEP 4: Insert into Database")
    print("=" * 60)
    
    inserted = 0
    skipped = 0
    
    for action in all_actions:
        row_hash = generate_row_hash(
            action['action_date'],
            action['action_type'],
            action['title']
        )
        
        # Check if exists
        cur.execute(
            "SELECT 1 FROM alt.legislation_1d WHERE row_hash = %s",
            (row_hash,)
        )
        if cur.fetchone():
            skipped += 1
            continue
        
        # Determine specialist tags using shared classifier
        specialist_tags = classify_specialists(action['title'])
        # Whitehouse actions always get trump_effect tag
        if 'trump_effect' not in specialist_tags:
            specialist_tags.append('trump_effect')
        # Remove "general" if other tags present
        if len(specialist_tags) > 1 and 'general' in specialist_tags:
            specialist_tags.remove('general')
        
        try:
            cur.execute("""
                INSERT INTO alt.legislation_1d
                (action_date, action_type, title, url, source_url, row_hash, 
                 event_date, scraped_at, validation_status, specialist_tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), 'validated', %s)
                ON CONFLICT (action_date, action_type, title) DO NOTHING
            """, (
                action['action_date'],
                action['action_type'],
                action['title'],
                action.get('url'),
                action.get('url'),
                row_hash,
                action['action_date'],
                specialist_tags,
            ))
            inserted += 1
        except Exception as e:
            print(f"  Error: {e}")
    
    conn.commit()
    
    print(f"\n  Inserted: {inserted}")
    print(f"  Skipped (duplicates): {skipped}")
    
    # ==========================================================================
    # FINAL VERIFICATION
    # ==========================================================================
    print("\n" + "=" * 70)
    print("FINAL VERIFICATION")
    print("=" * 70)
    
    cur.execute("""
        SELECT 
            action_type,
            COUNT(*) as cnt,
            MIN(action_date) as min_date,
            MAX(action_date) as max_date
        FROM alt.legislation_1d
        GROUP BY action_type
        ORDER BY cnt DESC
    """)
    
    print("\n  Actions by type:")
    total = 0
    for row in cur.fetchall():
        print(f"    {row[0]:25} {row[1]:4} rows ({row[2]} to {row[3]})")
        total += row[1]
    
    print(f"\n  Total: {total} actions")
    
    cur.execute("""
        SELECT COUNT(*) FROM alt.legislation_1d
    """)
    final_count = cur.fetchone()[0]
    print(f"\n  Final table count: {final_count}")
    
    cur.close()
    conn.close()
    
    print("\n" + "=" * 70)
    print("🎉 WHITEHOUSE SCRAPER COMPLETE")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
