"""
ZINC-FUSION-V15 Schema Contract Validator

Validates that all raw.* tables comply with the Bronze v2.0 contract.
Run this BEFORE every training run to prevent schema drift.

Usage:
    python -m src.fusion.validators.schema_contract
    
Exit codes:
    0 = All tables compliant
    1 = Contract violations detected

Reference: Docs/BRONZE_NAMING_CONTRACT_LOCKED.md
"""

import os
import sys
import re
from typing import Dict, List, Tuple, Set
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


# =============================================================================
# BRONZE CONTRACT DEFINITIONS
# =============================================================================

# Required Bronze columns (12 total)
BRONZE_COLUMNS: Set[str] = {
    "knowledge_time",
    "revision_no",
    "supersedes_id",
    "is_preliminary",
    "validation_status",
    "quality_score",
    "anomaly_flags",
    "source_url",
    "raw_payload",
    "ingestion_batch_id",
    "row_hash",
    "specialist_tags",
}

# Valid cadence suffixes (LOCKED - per BRONZE_NAMING_CONTRACT_LOCKED.md)
VALID_SUFFIXES: Set[str] = {
    "_1h",      # Hourly
    "_1d",      # Daily
    "_1w",      # Weekly
    "_1m",      # Monthly
    "_event",   # Irregular/event-time
    "_static",  # Reference/dimension data
}

# Forbidden patterns in table names
FORBIDDEN_PATTERNS: List[str] = [
    "_1y",       # No yearly cadence
    "_archive",  # Storage intent
    "_backup",   # Storage intent
    "_old",      # Storage intent
    "_tmp",      # Storage intent
    "_bronze",   # Processing stage
    "_silver",   # Processing stage
    "_gold",     # Processing stage
    "_daily",    # Use _1d instead
    "_weekly",   # Use _1w instead
    "_hourly",   # Use _1h instead
]


# =============================================================================
# VALIDATOR CLASS
# =============================================================================

class SchemaContractValidator:
    """Validates Bronze contract compliance for raw.* tables."""
    
    def __init__(self, connection_string: str):
        self.conn = psycopg2.connect(connection_string)
        self.violations: List[Dict] = []
        self.warnings: List[Dict] = []
        self.tables_checked: int = 0
        self.tables_compliant: int = 0
        
    def close(self):
        if self.conn:
            self.conn.close()
            
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
    
    def _get_table_columns(self, table_name: str) -> Set[str]:
        """Get column names for a table."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'raw' 
                  AND table_name = %s
            """, (table_name,))
            return {row[0] for row in cur.fetchall()}
    
    def _validate_naming(self, table_name: str) -> bool:
        """Validate table name follows naming contract."""
        valid = True
        
        # Check for valid suffix
        has_valid_suffix = any(table_name.endswith(suffix) for suffix in VALID_SUFFIXES)
        if not has_valid_suffix:
            self.violations.append({
                "table": table_name,
                "type": "NAMING",
                "message": f"Missing valid cadence suffix. Must end with one of: {VALID_SUFFIXES}",
            })
            valid = False
        
        # Check for forbidden patterns
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in table_name:
                self.violations.append({
                    "table": table_name,
                    "type": "NAMING",
                    "message": f"Contains forbidden pattern '{pattern}'",
                })
                valid = False
                
        # Check naming grammar: raw.<provider>_<dataset>_<cadence>
        # Should have at least 2 underscores (provider_dataset_cadence)
        parts = table_name.split("_")
        if len(parts) < 3:
            self.warnings.append({
                "table": table_name,
                "type": "NAMING",
                "message": "Name may not follow <provider>_<dataset>_<cadence> grammar",
            })
            
        return valid
    
    def _validate_bronze_columns(self, table_name: str) -> bool:
        """Validate table has all required Bronze columns."""
        columns = self._get_table_columns(table_name)
        missing = BRONZE_COLUMNS - columns
        
        if missing:
            self.violations.append({
                "table": table_name,
                "type": "SCHEMA",
                "message": f"Missing Bronze columns: {sorted(missing)}",
            })
            return False
            
        return True
    
    def _validate_row_hash_index(self, table_name: str) -> bool:
        """Validate row_hash column has an index for idempotency checks."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) 
                FROM pg_indexes 
                WHERE schemaname = 'raw' 
                  AND tablename = %s 
                  AND indexdef LIKE '%%row_hash%%'
            """, (table_name,))
            count = cur.fetchone()[0]
            
        if count == 0:
            self.warnings.append({
                "table": table_name,
                "type": "INDEX",
                "message": "No index on row_hash column (recommended for idempotency)",
            })
            return False
            
        return True
    
    def validate_table(self, table_name: str) -> bool:
        """Run all validations on a single table."""
        self.tables_checked += 1
        
        naming_ok = self._validate_naming(table_name)
        schema_ok = self._validate_bronze_columns(table_name)
        self._validate_row_hash_index(table_name)  # Warning only
        
        if naming_ok and schema_ok:
            self.tables_compliant += 1
            return True
        return False
    
    def validate_all(self) -> bool:
        """Validate all raw.* tables."""
        tables = self._get_raw_tables()
        
        if not tables:
            print("WARNING: No tables found in raw schema")
            return True
            
        print(f"\n{'='*60}")
        print(f"BRONZE CONTRACT VALIDATION")
        print(f"{'='*60}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"Tables to check: {len(tables)}")
        print(f"{'='*60}\n")
        
        for table in tables:
            self.validate_table(table)
            
        return len(self.violations) == 0
    
    def print_report(self):
        """Print validation report."""
        print(f"\n{'='*60}")
        print(f"VALIDATION REPORT")
        print(f"{'='*60}")
        print(f"Tables checked:    {self.tables_checked}")
        print(f"Tables compliant:  {self.tables_compliant}")
        print(f"Violations:        {len(self.violations)}")
        print(f"Warnings:          {len(self.warnings)}")
        print(f"{'='*60}\n")
        
        if self.violations:
            print("❌ VIOLATIONS (must fix):\n")
            for v in self.violations:
                print(f"  [{v['type']}] {v['table']}")
                print(f"    → {v['message']}\n")
                
        if self.warnings:
            print("⚠️  WARNINGS (recommended):\n")
            for w in self.warnings:
                print(f"  [{w['type']}] {w['table']}")
                print(f"    → {w['message']}\n")
                
        if not self.violations and not self.warnings:
            print("✅ All tables are Bronze contract compliant!\n")
        elif not self.violations:
            print("✅ No violations. Warnings are non-blocking.\n")
        else:
            print("❌ Contract violations detected. Fix before training.\n")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run schema contract validation."""
    # Get connection string from environment or use default
    conn_string = os.environ.get(
        "DATABASE_URL",
        os.environ.get("POSTGRES_URL")
    )
    
    if not conn_string:
        print("ERROR: DATABASE_URL or POSTGRES_URL environment variable required")
        sys.exit(1)
    
    validator = SchemaContractValidator(conn_string)
    
    try:
        all_valid = validator.validate_all()
        validator.print_report()
        
        # Exit with appropriate code
        sys.exit(0 if all_valid else 1)
        
    finally:
        validator.close()


if __name__ == "__main__":
    main()
