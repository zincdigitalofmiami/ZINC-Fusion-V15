#!/usr/bin/env python3
"""
One-time migration: Normalize 'databento_historical' → 'databento' in mkt.futures_1d.

This fixes the incremental query gap where jobs looking for source='databento'
miss the 6,500+ historical rows that use 'databento_historical'.

Run with --dry-run first to see what would change.
"""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")


def get_db_connection():
    """Get database connection."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set in .env")
    return psycopg2.connect(DATABASE_URL)


def check_current_state(conn):
    """Show current source distribution."""
    cur = conn.cursor()
    cur.execute("""
        SELECT source, COUNT(*) as cnt, MIN(event_date) as min_date, MAX(event_date) as max_date
        FROM mkt.futures_1d
        WHERE symbol = 'ZL'
        GROUP BY source
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    cur.close()
    
    print("\n=== Current Source Distribution (ZL in mkt.futures_1d) ===")
    print(f"{'Source':<25} {'Count':<10} {'Min Date':<12} {'Max Date':<12}")
    print("-" * 60)
    for row in rows:
        source, cnt, min_date, max_date = row
        print(f"{source or 'NULL':<25} {cnt:<10} {str(min_date):<12} {str(max_date):<12}")
    print()
    
    return rows


def migrate_sources(conn, dry_run=True):
    """Migrate databento_historical → databento."""
    cur = conn.cursor()
    
    # Count affected rows first
    cur.execute("""
        SELECT COUNT(*) FROM mkt.futures_1d WHERE source = 'databento_historical'
    """)
    affected_count = cur.fetchone()[0]
    
    print(f"\nRows to migrate: {affected_count}")
    
    if dry_run:
        print("DRY RUN - no changes made")
        cur.close()
        return 0
    
    if affected_count == 0:
        print("Nothing to migrate")
        cur.close()
        return 0
    
    # Execute migration
    print("Executing migration...")
    cur.execute("""
        UPDATE mkt.futures_1d 
        SET source = 'databento' 
        WHERE source = 'databento_historical'
    """)
    
    updated = cur.rowcount
    conn.commit()
    cur.close()
    
    print(f"✅ Migrated {updated} rows: 'databento_historical' → 'databento'")
    return updated


def main():
    """Main entry point."""
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    
    print("=" * 70)
    print("DATABENTO SOURCE MIGRATION")
    print("=" * 70)
    
    if dry_run:
        print("MODE: DRY RUN (use --execute to apply changes)")
    else:
        print("MODE: EXECUTE (changes will be applied)")
    
    conn = get_db_connection()
    
    # Show current state
    check_current_state(conn)
    
    # Run migration
    if "--execute" in sys.argv:
        updated = migrate_sources(conn, dry_run=False)
    else:
        updated = migrate_sources(conn, dry_run=True)
    
    # Show new state
    if updated > 0:
        check_current_state(conn)
    
    conn.close()
    
    print("\nDone.")


if __name__ == "__main__":
    main()
