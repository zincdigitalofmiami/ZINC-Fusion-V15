#!/usr/bin/env python3
"""
Register all ZINC-FUSION models in model.model_registry.

This script pre-registers model definitions with status='pending'.
Actual training will update metrics and change status to 'trained'.

Models:
- 11 Specialist models (domain-specific features)
- 1 Core model (technical/price features)
- 1 Meta ensemble (stacks all specialists + core)

Each model x horizon combination gets its own registry entry.

Usage:
    python scripts/register_models.py --dry-run
    python scripts/register_models.py --execute
"""

import os
import sys
import argparse
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values, Json


# =============================================================================
# Model Definitions
# =============================================================================

MODELS = [
    {
        "model_name": "weather_specialist",
        "model_type": "specialist",
        "notes": "Weather and climate features: ENSO indices, drought monitors, growing degree days, precipitation anomalies",
    },
    {
        "model_name": "macro_specialist",
        "model_type": "specialist",
        "notes": "Macroeconomic features: interest rates, DXY, inflation expectations, yield curve, Fed policy signals",
    },
    {
        "model_name": "seasonal_specialist",
        "model_type": "specialist",
        "notes": "Seasonal patterns: calendar effects, harvest cycles, WASDE release timing, planting/harvest windows",
    },
    {
        "model_name": "sentiment_specialist",
        "model_type": "specialist",
        "notes": "Market sentiment: news sentiment scores, social media signals, analyst positioning",
    },
    {
        "model_name": "cot_specialist",
        "model_type": "specialist",
        "notes": "CFTC COT positioning: managed money, commercials, producers, swap dealers, net positions and changes",
    },
    {
        "model_name": "biodiesel_specialist",
        "model_type": "specialist",
        "notes": "Biofuel fundamentals: RIN prices, biodiesel mandates, EPA RVO policy, renewable diesel capacity",
    },
    {
        "model_name": "supply_specialist",
        "model_type": "specialist",
        "notes": "Supply fundamentals: crush margins, soybean stocks, South American production, oil yield rates",
    },
    {
        "model_name": "demand_specialist",
        "model_type": "specialist",
        "notes": "Demand fundamentals: export pace, domestic usage, China import patterns, crush capacity utilization",
    },
    {
        "model_name": "options_specialist",
        "model_type": "specialist",
        "notes": "Options-derived features: IV skew, term structure slope, put/call ratios, gamma exposure, IV percentile",
    },
    {
        "model_name": "crush_specialist",
        "model_type": "specialist",
        "notes": "Crush complex features: board crush spread, GPM, oil share, ZS/ZM/ZL relationships",
    },
    {
        "model_name": "geopolitical_specialist",
        "model_type": "specialist",
        "notes": "Geopolitical risk features: trade policy signals, tariff impacts, sanctions, supply chain disruptions",
    },
    {
        "model_name": "core_model",
        "model_type": "core",
        "notes": "Core technical features: price action, returns, and volatility",
    },
    {
        "model_name": "meta_ensemble",
        "model_type": "meta",
        "notes": "Meta ensemble: stacks OOF predictions from all specialists + core model for final forecast",
    },
]

HORIZONS = [5, 21, 63, 126]


def get_connection():
    """Get database connection from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL not found in environment")
    return psycopg2.connect(database_url)


def register_models(conn, dry_run: bool = True):
    """Register all models in model.model_registry."""

    # Generate all model x horizon combinations
    registrations = []
    for m in MODELS:
        for h in HORIZONS:
            model_id = f"{m['model_name']}_h{h}_v1"
            registrations.append(
                {
                    "model_id": model_id,
                    "model_name": m["model_name"],
                    "model_type": m["model_type"],
                    "horizon": h,
                    "version": 1,
                    "status": "pending",
                    "notes": m["notes"],
                    "tags": {
                        "registered_by": "pre_training_setup",
                        "sot_version": "v2",
                    },
                }
            )

    if dry_run:
        print("\n[DRY RUN] Would register the following models:\n")
        print(f"{'Model ID':<35} {'Type':<12} {'Horizon':<10} {'Status'}")
        print("-" * 70)
        for r in registrations:
            print(
                f"{r['model_id']:<35} {r['model_type']:<12} {r['horizon']:<10} {r['status']}"
            )
        print(
            f"\nTotal: {len(registrations)} model registrations ({len(MODELS)} models x {len(HORIZONS)} horizons)"
        )
        return

    cursor = conn.cursor()

    # Clear existing registrations (only pending ones to preserve trained models)
    cursor.execute("DELETE FROM model.model_registry WHERE status = 'pending'")

    now = datetime.now(timezone.utc)

    # Prepare values
    values = []
    for r in registrations:
        values.append(
            (
                r["model_id"],
                r["model_name"],
                r["model_type"],
                r["horizon"],
                r["version"],
                now,  # trained_at
                r["status"],
                False,  # is_champion
                Json(r["tags"]),
                r["notes"],
                now,  # created_at
                now,  # updated_at
            )
        )

    insert_sql = """
        INSERT INTO model.model_registry
        (model_id, model_name, model_type, horizon, version, trained_at, status, is_champion, tags, notes, created_at, updated_at)
        VALUES %s
        ON CONFLICT (model_id, version) DO UPDATE SET
            status = EXCLUDED.status,
            tags = EXCLUDED.tags,
            updated_at = EXCLUDED.updated_at
    """

    execute_values(cursor, insert_sql, values, page_size=100)
    conn.commit()

    print(
        f"\n[SUCCESS] Registered {len(registrations)} model entries in model.model_registry"
    )

    # Summary by model type
    cursor.execute("""
        SELECT model_type, COUNT(*), COUNT(DISTINCT model_name)
        FROM model.model_registry
        GROUP BY model_type
        ORDER BY model_type
    """)
    rows = cursor.fetchall()
    print("\nSummary by Type:")
    print(f"{'Type':<12} {'Entries':<10} {'Unique Models'}")
    print("-" * 35)
    for row in rows:
        print(f"{row[0]:<12} {row[1]:<10} {row[2]}")


def main():
    parser = argparse.ArgumentParser(
        description="Register models in model.model_registry"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting"
    )
    parser.add_argument(
        "--execute", action="store_true", help="Actually register models"
    )
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("ERROR: Must specify either --dry-run or --execute")
        sys.exit(1)

    print("=" * 60)
    print("REGISTER MODELS")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")

    conn = get_connection()

    try:
        register_models(conn, dry_run=args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
