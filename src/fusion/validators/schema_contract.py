"""
ZINC-FUSION-V15 Institutional Schema Contract Validator

Validates that all landing tables (mkt/econ/alt/pos/supply) comply with
institutional standards. Run BEFORE every training run to prevent schema drift.

Usage:
    python -m src.fusion.validators.schema_contract

Exit codes:
    0 = All tables compliant
    1 = Contract violations detected

SCHEMA TAXONOMY (12 active + 1 deprecated):
    Landing: mkt, econ, alt, pos, supply
    Derived: features, training
    Output: model, forecasts, analytics
    Governance: metadata, ops
    Deprecated: archive (read-only)
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
# INSTITUTIONAL SCHEMA CONTRACT DEFINITIONS
# =============================================================================

# Landing schemas (append-only source data)
LANDING_SCHEMAS: Set[str] = {"mkt", "econ", "alt", "pos", "supply"}

# Derived schemas (computed from landing)
DERIVED_SCHEMAS: Set[str] = {"features", "training"}

# Output schemas (model results)
OUTPUT_SCHEMAS: Set[str] = {"model", "forecasts", "analytics"}

# Governance schemas (operations/metadata)
GOVERNANCE_SCHEMAS: Set[str] = {"metadata", "ops"}

# All allowed schemas (excludes deprecated 'archive')
ALLOWED_SCHEMAS: Set[str] = (
    LANDING_SCHEMAS | DERIVED_SCHEMAS | OUTPUT_SCHEMAS | GOVERNANCE_SCHEMAS
)

# BANNED legacy schemas - fail hard if detected in new code
BANNED_SCHEMAS: Set[str] = {
    "raw",
    "gold",
    "silver",
    "bronze",
    "monitoring",
    "specialist",
    "weather",
}

# Valid cadence suffixes
VALID_SUFFIXES: Set[str] = {
    "_1h",  # Hourly
    "_1d",  # Daily
    "_1w",  # Weekly
    "_1m",  # Monthly
    "_event",  # Irregular/event-time
    "_static",  # Reference/dimension data
}

# Time column contract
TIME_COLUMNS = {
    "landing": "event_date",  # When event occurred
    "derived": "trade_date",  # Trading day
    "forecasts": ("forecast_date", "target_date"),  # Prediction reference + target
}

# Forbidden patterns in table names
FORBIDDEN_PATTERNS: List[str] = [
    "_1y",  # No yearly cadence
    "_archive",  # Storage intent
    "_backup",  # Storage intent
    "_old",  # Storage intent
    "_tmp",  # Storage intent
    "_bronze",  # Processing stage
    "_silver",  # Processing stage
    "_gold",  # Processing stage
    "_daily",  # Use _1d instead
    "_weekly",  # Use _1w instead
    "_hourly",  # Use _1h instead
]


# =============================================================================
# VALIDATOR CLASS
# =============================================================================


class SchemaContractValidator:
    """Validates institutional schema contract compliance for landing tables."""

    def __init__(self, connection_string: str):
        self.conn = psycopg2.connect(connection_string)
        self.violations: List[Dict] = []
        self.warnings: List[Dict] = []
        self.tables_checked: int = 0
        self.tables_compliant: int = 0

    def close(self):
        if self.conn:
            self.conn.close()

    def _get_landing_tables(self) -> List[Tuple[str, str]]:
        """Get all tables in landing schemas (mkt, econ, alt, pos, supply)."""
        schemas = tuple(LANDING_SCHEMAS)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_schema = ANY(%s)
                  AND table_type = 'BASE TABLE'
                ORDER BY table_schema, table_name
            """,
                (list(schemas),),
            )
            return [(row[0], row[1]) for row in cur.fetchall()]

    def _get_table_columns(self, schema: str, table_name: str) -> Set[str]:
        """Get column names for a table."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
            """,
                (schema, table_name),
            )
            return {row[0] for row in cur.fetchall()}

    def _check_banned_schemas(self) -> None:
        """Check if any banned schemas still have tables."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_schema, COUNT(*) as table_count
                FROM information_schema.tables
                WHERE table_schema = ANY(%s)
                  AND table_type = 'BASE TABLE'
                GROUP BY table_schema
            """,
                (list(BANNED_SCHEMAS),),
            )
            for row in cur.fetchall():
                self.warnings.append(
                    {
                        "schema": row[0],
                        "type": "BANNED_SCHEMA",
                        "message": f"Banned schema '{row[0]}' still has {row[1]} tables. Migrate to institutional schemas.",
                    }
                )

    def _validate_naming(self, table_name: str) -> bool:
        """Validate table name follows naming contract."""
        valid = True

        # Check for valid suffix
        has_valid_suffix = any(table_name.endswith(suffix) for suffix in VALID_SUFFIXES)
        if not has_valid_suffix:
            self.violations.append(
                {
                    "table": table_name,
                    "type": "NAMING",
                    "message": f"Missing valid cadence suffix. Must end with one of: {VALID_SUFFIXES}",
                }
            )
            valid = False

        # Check for forbidden patterns
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in table_name:
                self.violations.append(
                    {
                        "table": table_name,
                        "type": "NAMING",
                        "message": f"Contains forbidden pattern '{pattern}'",
                    }
                )
                valid = False

        # Check naming grammar: {schema}.<provider>_<dataset>_<cadence>
        # Should have at least 2 underscores (provider_dataset_cadence)
        parts = table_name.split("_")
        if len(parts) < 3:
            self.warnings.append(
                {
                    "table": table_name,
                    "type": "NAMING",
                    "message": "Name may not follow <provider>_<dataset>_<cadence> grammar",
                }
            )

        return valid

    def _validate_bronze_columns(self, table_name: str) -> bool:
        """Validate table has all required Bronze columns."""
        columns = self._get_table_columns(table_name)
        missing = BRONZE_COLUMNS - columns

        if missing:
            self.violations.append(
                {
                    "table": table_name,
                    "type": "SCHEMA",
                    "message": f"Missing Bronze columns: {sorted(missing)}",
                }
            )
            return False

        return True

    def _validate_row_hash_index(self, table_name: str) -> bool:
        """Validate row_hash column has an index for idempotency checks."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) 
                FROM pg_indexes 
                WHERE schemaname = 'raw' 
                  AND tablename = %s 
                  AND indexdef LIKE '%%row_hash%%'
            """,
                (table_name,),
            )
            count = cur.fetchone()[0]

        if count == 0:
            self.warnings.append(
                {
                    "table": table_name,
                    "type": "INDEX",
                    "message": "No index on row_hash column (recommended for idempotency)",
                }
            )
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
        """Validate all landing schema tables."""
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
    conn_string = os.environ.get("DATABASE_URL", os.environ.get("POSTGRES_URL"))

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
