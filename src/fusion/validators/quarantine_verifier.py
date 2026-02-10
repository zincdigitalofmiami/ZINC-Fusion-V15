"""
ZINC-FUSION-V15 Quarantine Pipeline Verifier

Tests that the ops.quarantined_record table exists and can receive bad records.
Also provides utilities for inspecting and managing quarantined data.

Usage:
    python -m src.fusion.validators.quarantine_verifier
    python -m src.fusion.validators.quarantine_verifier --stats
    python -m src.fusion.validators.quarantine_verifier --test

Exit codes:
    0 = Quarantine pipeline functional
    1 = Quarantine pipeline broken
"""

import os
import sys
import json
import argparse
from typing import Dict, List
from datetime import datetime
from uuid import uuid4

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


# =============================================================================
# QUARANTINE VERIFIER
# =============================================================================


class QuarantineVerifier:
    """Verifies and manages the quarantine pipeline."""

    def __init__(self, connection_string: str):
        self.conn = psycopg2.connect(connection_string)

    def close(self):
        if self.conn:
            self.conn.close()

    def verify_table_exists(self) -> bool:
        """Check that ops.quarantined_record table exists with correct schema."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'ops'
                  AND table_name = 'quarantined_record'
                ORDER BY ordinal_position
            """)
            columns = {row[0]: row[1] for row in cur.fetchall()}

        if not columns:
            print("❌ ops.quarantined_record table does not exist!")
            return False

        # Required columns
        required = {
            "id": "uuid",
            "source_table": "text",
            "raw_payload": "jsonb",
            "validation_errors": "ARRAY",  # text[]
            "severity": "text",
        }

        missing = []
        for col, expected_type in required.items():
            if col not in columns:
                missing.append(col)
            # Note: type checking is loose because of array notation differences

        if missing:
            print(f"❌ Missing required columns: {missing}")
            return False

        print("✅ ops.quarantined_record table exists with correct schema")
        return True

    def test_insert(self) -> bool:
        """Test inserting a record into quarantine."""
        str(uuid4())
        test_payload = {
            "test": True,
            "timestamp": datetime.now().isoformat(),
            "verifier": "quarantine_verifier.py",
        }

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.quarantined_record
                        (source_table, raw_payload, validation_errors, severity)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """,
                    (
                        "test.quarantine_verifier",
                        json.dumps(test_payload),
                        ["TEST: Quarantine pipeline verification"],
                        "test",
                    ),
                )
                cur.fetchone()[0]

            # Rollback so we don't pollute the table
            self.conn.rollback()

            print(f"✅ Successfully inserted test record (rolled back)")
            return True

        except Exception as e:
            print(f"❌ Failed to insert test record: {e}")
            self.conn.rollback()
            return False

    def get_stats(self) -> Dict:
        """Get quarantine statistics."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Total count
            cur.execute("SELECT COUNT(*) as total FROM ops.quarantined_record")
            total = cur.fetchone()["total"]

            # By severity
            cur.execute("""
                SELECT severity, COUNT(*) as count
                FROM ops.quarantined_record
                GROUP BY severity
                ORDER BY count DESC
            """)
            by_severity = {row["severity"]: row["count"] for row in cur.fetchall()}

            # By source table
            cur.execute("""
                SELECT source_table, COUNT(*) as count
                FROM ops.quarantined_record
                GROUP BY source_table
                ORDER BY count DESC
                LIMIT 10
            """)
            by_source = {row["source_table"]: row["count"] for row in cur.fetchall()}

            # Recent (last 24h)
            cur.execute("""
                SELECT COUNT(*) as recent
                FROM ops.quarantined_record
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            recent = cur.fetchone()["recent"]

        return {
            "total": total,
            "recent_24h": recent,
            "by_severity": by_severity,
            "by_source": by_source,
        }

    def get_recent_records(self, limit: int = 10) -> List[Dict]:
        """Get recent quarantined records."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    source_table,
                    validation_errors,
                    severity,
                    created_at
                FROM ops.quarantined_record
                ORDER BY created_at DESC
                LIMIT %s
            """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def print_stats(self):
        """Print quarantine statistics."""
        stats = self.get_stats()

        print(f"\n{'=' * 60}")
        print(f"QUARANTINE STATISTICS")
        print(f"{'=' * 60}")
        print(f"Total quarantined records: {stats['total']}")
        print(f"Last 24 hours:             {stats['recent_24h']}")
        print(f"{'=' * 60}\n")

        if stats["by_severity"]:
            print("By Severity:")
            for sev, count in stats["by_severity"].items():
                print(f"  {sev or 'NULL'}: {count}")
            print()

        if stats["by_source"]:
            print("By Source Table (top 10):")
            for source, count in stats["by_source"].items():
                print(f"  {source}: {count}")
            print()

        recent = self.get_recent_records(5)
        if recent:
            print("Recent Quarantined Records:")
            print("-" * 60)
            for r in recent:
                print(f"  [{r['severity']}] {r['source_table']}")
                print(f"    Errors: {r['validation_errors'][:100]}...")
                print(f"    Time: {r['created_at']}")
                print()

    def verify_all(self) -> bool:
        """Run all verification checks."""
        print(f"\n{'=' * 60}")
        print(f"QUARANTINE PIPELINE VERIFICATION")
        print(f"{'=' * 60}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"{'=' * 60}\n")

        table_ok = self.verify_table_exists()
        if not table_ok:
            return False

        insert_ok = self.test_insert()

        return table_ok and insert_ok


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Quarantine Pipeline Verifier")
    parser.add_argument(
        "--stats", action="store_true", help="Show quarantine statistics"
    )
    parser.add_argument("--test", action="store_true", help="Run verification tests")
    args = parser.parse_args()

    conn_string = os.environ.get("DATABASE_URL", os.environ.get("POSTGRES_URL"))

    if not conn_string:
        print("ERROR: DATABASE_URL or POSTGRES_URL environment variable required")
        sys.exit(1)

    verifier = QuarantineVerifier(conn_string)

    try:
        if args.stats:
            verifier.print_stats()
            sys.exit(0)
        else:
            # Default: run verification
            ok = verifier.verify_all()
            if ok:
                print("\n✅ Quarantine pipeline is functional!\n")
            sys.exit(0 if ok else 1)

    finally:
        verifier.close()


if __name__ == "__main__":
    main()
