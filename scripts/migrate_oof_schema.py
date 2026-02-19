#!/usr/bin/env python3
"""
One-time migration: Recreate training.oof_core_1d for price predictor schema.

Old schema: p30, p50, p70 (quantile outputs)
New schema: predicted_price (single point forecast)

Safe to drop — old data was from dry runs with wrong config (WQL/returns/quantiles).
"""

import sys

sys.path.insert(0, "src")

from fusion.db.connection import get_write_connection

MIGRATION_SQL = """
-- Drop old quantile-based OOF table
DROP TABLE IF EXISTS training.oof_core_1d;

-- Create new price-predictor OOF table
CREATE TABLE training.oof_core_1d (
    trade_date        DATE NOT NULL,
    symbol            VARCHAR(20) NOT NULL DEFAULT 'ZL',
    horizon_days      INTEGER NOT NULL,
    window_id         INTEGER NOT NULL,
    cutoff_date       DATE NOT NULL,
    predicted_price   DOUBLE PRECISION NOT NULL,
    target_value      DOUBLE PRECISION,
    trained_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    run_hash          VARCHAR(64) NOT NULL,
    matrix_version    VARCHAR(64),
    run_id            UUID NOT NULL,
    PRIMARY KEY (trade_date, symbol, horizon_days, window_id)
);

COMMENT ON TABLE training.oof_core_1d IS 'Core model OOF predictions — single predicted_price per horizon (2026-02-19)';
COMMENT ON COLUMN training.oof_core_1d.predicted_price IS 'Core point forecast: ZL futures contract price';
COMMENT ON COLUMN training.oof_core_1d.target_value IS 'Realized ZL futures contract price at horizon';
"""


def main():
    print("=" * 60)
    print("MIGRATION: training.oof_core_1d → price predictor schema")
    print("=" * 60)

    conn = get_write_connection()
    print("Connected to database")

    with conn.cursor() as cur:
        cur.execute(MIGRATION_SQL)

    conn.commit()
    print(
        "Migration complete: training.oof_core_1d recreated with predicted_price column"
    )

    # Verify
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'training' AND table_name = 'oof_core_1d'
            ORDER BY ordinal_position
        """)
        cols = cur.fetchall()

    print("\nNew table schema:")
    for col_name, col_type in cols:
        print(f"  {col_name}: {col_type}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
