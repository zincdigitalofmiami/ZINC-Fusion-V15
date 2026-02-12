#!/usr/bin/env python3
"""
One-time cleanup: convert NaN target_value rows to NULL in training.oof_core_1d.

NaN poisons SQL aggregates (AVG, SUM return NaN if any row is NaN),
while NULL rows are properly skipped. This script fixes existing data.

Run once, then future inserts are protected by the NaN→None guard in train_models.py.

Usage:
    .venv/bin/python scripts/cleanup_oof_nan_target_values.py --dry-run
    .venv/bin/python scripts/cleanup_oof_nan_target_values.py --execute
"""

import argparse

from fusion.db.connection import get_connection


def main():
    parser = argparse.ArgumentParser(
        description="Clean NaN target_value in oof_core_1d"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    parser.add_argument(
        "--execute", action="store_true", help="Actually run the UPDATE"
    )
    args = parser.parse_args()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Count NaN rows (Postgres: 'NaN'::float is a special float value)
            cur.execute("""
                SELECT COUNT(*) FROM training.oof_core_1d
                WHERE target_value = 'NaN'::double precision
            """)
            nan_count = cur.fetchone()[0]
            print(f"Found {nan_count} rows with NaN target_value")

            if nan_count == 0:
                print("Nothing to clean up.")
                return

            if args.execute:
                cur.execute("""
                    UPDATE training.oof_core_1d
                    SET target_value = NULL
                    WHERE target_value = 'NaN'::double precision
                """)
                conn.commit()
                print(f"Updated {nan_count} rows: NaN → NULL")
            else:
                print("Dry run — no changes made. Use --execute to apply.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
