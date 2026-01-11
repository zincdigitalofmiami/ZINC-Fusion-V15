"""
ZINC-FUSION-V15 Data Freshness Monitor

Checks raw.* tables for stale data based on expected update frequency.
Alerts when tables haven't received new data within their expected window.

Usage:
    python -m src.fusion.validators.freshness_monitor
    
Exit codes:
    0 = All tables fresh
    1 = Stale tables detected

Reference: Docs/BRONZE_NAMING_CONTRACT_LOCKED.md (cadence suffixes)
"""

import os
import sys
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


# =============================================================================
# FRESHNESS THRESHOLDS BY CADENCE
# =============================================================================

# Expected maximum age (hours) before a table is considered stale
# Based on cadence suffix from BRONZE_NAMING_CONTRACT_LOCKED.md
FRESHNESS_THRESHOLDS: Dict[str, int] = {
    "_1h": 2,       # Hourly data: stale after 2 hours
    "_1d": 36,      # Daily data: stale after 36 hours (allow weekends)
    "_1w": 192,     # Weekly data: stale after 8 days (192 hours)
    "_1m": 768,     # Monthly data: stale after 32 days (768 hours)
    "_event": 168,  # Event data: stale after 7 days (no events is suspicious)
    "_static": None,  # Static/reference data: no freshness requirement
}

# Tables that are expected to be empty or have special handling
EXEMPT_TABLES: List[str] = [
    # Add tables here that shouldn't be checked
]


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TableFreshness:
    """Freshness status for a single table."""
    table_name: str
    cadence: str
    row_count: int
    latest_knowledge_time: Optional[datetime]
    age_hours: Optional[float]
    threshold_hours: Optional[int]
    is_stale: bool
    is_empty: bool
    

# =============================================================================
# FRESHNESS MONITOR
# =============================================================================

class FreshnessMonitor:
    """Monitors data freshness across raw.* tables."""
    
    def __init__(self, connection_string: str):
        self.conn = psycopg2.connect(connection_string)
        self.results: List[TableFreshness] = []
        
    def close(self):
        if self.conn:
            self.conn.close()
            
    def _get_cadence(self, table_name: str) -> str:
        """Extract cadence suffix from table name."""
        for suffix in FRESHNESS_THRESHOLDS.keys():
            if table_name.endswith(suffix):
                return suffix
        return "_unknown"
    
    def _get_raw_tables(self) -> List[str]:
        """Get all tables in the raw schema."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'raw' 
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            return [row[0] for row in cur.fetchall()]
    
    def _check_table_freshness(self, table_name: str) -> TableFreshness:
        """Check freshness of a single table."""
        cadence = self._get_cadence(table_name)
        threshold = FRESHNESS_THRESHOLDS.get(cadence)
        
        with self.conn.cursor() as cur:
            # Get row count and latest knowledge_time
            cur.execute(f"""
                SELECT 
                    COUNT(*) as row_count,
                    MAX(knowledge_time) as latest_kt
                FROM raw.{table_name}
            """)
            row = cur.fetchone()
            row_count = row[0] or 0
            latest_kt = row[1]
            
        # Calculate age
        age_hours = None
        if latest_kt:
            age = datetime.now(latest_kt.tzinfo) - latest_kt
            age_hours = age.total_seconds() / 3600
            
        # Determine staleness
        is_empty = row_count == 0
        is_stale = False
        
        if table_name in EXEMPT_TABLES:
            is_stale = False
        elif threshold is None:
            # Static tables have no freshness requirement
            is_stale = False
        elif is_empty:
            # Empty tables are considered stale (unless exempt)
            is_stale = True
        elif age_hours is not None and age_hours > threshold:
            is_stale = True
            
        return TableFreshness(
            table_name=table_name,
            cadence=cadence,
            row_count=row_count,
            latest_knowledge_time=latest_kt,
            age_hours=age_hours,
            threshold_hours=threshold,
            is_stale=is_stale,
            is_empty=is_empty,
        )
    
    def check_all(self) -> bool:
        """Check freshness of all raw.* tables."""
        tables = self._get_raw_tables()
        
        print(f"\n{'='*70}")
        print(f"DATA FRESHNESS MONITOR")
        print(f"{'='*70}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"Tables to check: {len(tables)}")
        print(f"{'='*70}\n")
        
        for table in tables:
            try:
                result = self._check_table_freshness(table)
                self.results.append(result)
            except Exception as e:
                print(f"ERROR checking {table}: {e}")
                
        stale_count = sum(1 for r in self.results if r.is_stale)
        return stale_count == 0
    
    def print_report(self):
        """Print freshness report."""
        stale = [r for r in self.results if r.is_stale]
        fresh = [r for r in self.results if not r.is_stale]
        empty = [r for r in self.results if r.is_empty]
        
        print(f"\n{'='*70}")
        print(f"FRESHNESS REPORT")
        print(f"{'='*70}")
        print(f"Total tables:    {len(self.results)}")
        print(f"Fresh:           {len(fresh)}")
        print(f"Stale:           {len(stale)}")
        print(f"Empty:           {len(empty)}")
        print(f"{'='*70}\n")
        
        if stale:
            print("❌ STALE TABLES:\n")
            print(f"{'Table':<45} {'Cadence':<10} {'Age (h)':<10} {'Threshold':<10}")
            print("-" * 75)
            for r in sorted(stale, key=lambda x: x.age_hours or float('inf'), reverse=True):
                age_str = f"{r.age_hours:.1f}" if r.age_hours else "EMPTY"
                thresh_str = str(r.threshold_hours) if r.threshold_hours else "N/A"
                print(f"{r.table_name:<45} {r.cadence:<10} {age_str:<10} {thresh_str:<10}")
            print()
            
        # Show summary of fresh tables by cadence
        print("✅ FRESH TABLES SUMMARY:\n")
        cadence_counts: Dict[str, int] = {}
        for r in fresh:
            cadence_counts[r.cadence] = cadence_counts.get(r.cadence, 0) + 1
        for cadence, count in sorted(cadence_counts.items()):
            print(f"  {cadence}: {count} tables")
        print()
        
        # Show most recent updates
        print("📊 MOST RECENT UPDATES:\n")
        recent = sorted(
            [r for r in self.results if r.latest_knowledge_time],
            key=lambda x: x.latest_knowledge_time,
            reverse=True
        )[:10]
        
        print(f"{'Table':<45} {'Last Update':<25} {'Age (h)':<10}")
        print("-" * 80)
        for r in recent:
            kt_str = r.latest_knowledge_time.strftime("%Y-%m-%d %H:%M:%S") if r.latest_knowledge_time else "Never"
            age_str = f"{r.age_hours:.1f}" if r.age_hours else "N/A"
            print(f"{r.table_name:<45} {kt_str:<25} {age_str:<10}")
        print()
        
        if stale:
            print("❌ Stale data detected. Investigate before training.\n")
        else:
            print("✅ All tables are fresh!\n")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run freshness monitoring."""
    conn_string = os.environ.get(
        "DATABASE_URL",
        os.environ.get("POSTGRES_URL")
    )
    
    if not conn_string:
        print("ERROR: DATABASE_URL or POSTGRES_URL environment variable required")
        sys.exit(1)
    
    monitor = FreshnessMonitor(conn_string)
    
    try:
        all_fresh = monitor.check_all()
        monitor.print_report()
        sys.exit(0 if all_fresh else 1)
        
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
