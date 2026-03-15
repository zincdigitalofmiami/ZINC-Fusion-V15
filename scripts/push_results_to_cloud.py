#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Push Training Results to Cloud

This script pushes training outputs (OOF predictions, forecasts, metrics)
from local training runs back to Prisma Cloud for dashboard consumption.

Architecture:
    Training (local) → model.*, analytics.* tables → Dashboard reads from cloud

Usage:
    python scripts/push_results_to_cloud.py --table model.oof_predictions --file results/oof.parquet
    python scripts/push_results_to_cloud.py --all-results
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Local results directory
LOCAL_RESULTS_DIR = Path(__file__).parent.parent / "data" / "results"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}


def validate_cloud_database_url(database_url: str) -> str:
    if database_url.startswith("prisma+postgres://"):
        raise ValueError(
            "CLOUD_DATABASE_URL must be direct postgres:// or postgresql:// for psycopg2"
        )
    parsed = urlparse(database_url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("CLOUD_DATABASE_URL must include a host")
    if host in LOCAL_HOSTS:
        raise ValueError(
            f"CLOUD_DATABASE_URL must point to cloud for this push, got local host {host!r}"
        )
    return database_url


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("CLOUD_DATABASE_URL")
    if not database_url:
        raise ValueError("CLOUD_DATABASE_URL not found in environment")
    return psycopg2.connect(validate_cloud_database_url(database_url))


def push_dataframe_to_table(
    conn, df: pd.DataFrame, schema: str, table: str, mode: str = "append"
) -> int:
    """Push a DataFrame to a Postgres table.

    Args:
        conn: Postgres connection
        df: DataFrame to push
        schema: Target schema
        table: Target table
        mode: 'append' or 'replace'

    Returns:
        Number of rows inserted
    """
    if mode == "replace":
        with conn.cursor() as cur:
            cur.execute(f'TRUNCATE "{schema}"."{table}"')
            conn.commit()

    # Get column names
    columns = list(df.columns)
    placeholders = ", ".join(["%s"] * len(columns))
    column_names = ", ".join([f'"{c}"' for c in columns])

    insert_query = f"""
        INSERT INTO "{schema}"."{table}" ({column_names})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING
    """

    # Convert DataFrame to list of tuples
    values = [tuple(row) for row in df.itertuples(index=False, name=None)]

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, values, page_size=1000)
        conn.commit()

    return len(values)


def push_oof_predictions(conn, file_path: Path) -> dict:
    """Push OOF predictions to model.oof_predictions."""
    df = pd.read_parquet(file_path)

    # Ensure required columns exist
    required = ["as_of_date", "horizon_days", "p10", "p50", "p90"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    rows = push_dataframe_to_table(conn, df, "model", "oof_predictions", mode="append")

    return {"table": "model.oof_predictions", "rows_pushed": rows}


def push_forecasts(conn, file_path: Path) -> dict:
    """Push forecast quantiles to forecasts.forecast_quantiles."""
    df = pd.read_parquet(file_path)

    rows = push_dataframe_to_table(
        conn, df, "forecasts", "forecast_quantiles", mode="append"
    )

    return {"table": "forecasts.forecast_quantiles", "rows_pushed": rows}


def push_driver_scores(conn, file_path: Path) -> dict:
    """Push driver scores to analytics.driver_scores."""
    df = pd.read_parquet(file_path)

    rows = push_dataframe_to_table(
        conn, df, "analytics", "driver_scores", mode="append"
    )

    return {"table": "analytics.driver_scores", "rows_pushed": rows}


def push_market_posture(conn, file_path: Path) -> dict:
    """Push market posture to analytics.market_posture."""
    df = pd.read_parquet(file_path)

    rows = push_dataframe_to_table(
        conn, df, "analytics", "market_posture", mode="append"
    )

    return {"table": "analytics.market_posture", "rows_pushed": rows}


# Mapping of result types to push functions
RESULT_HANDLERS = {
    "oof_predictions": push_oof_predictions,
    "forecasts": push_forecasts,
    "driver_scores": push_driver_scores,
    "market_posture": push_market_posture,
}


def main():
    parser = argparse.ArgumentParser(
        description="Push training results to Prisma Cloud"
    )
    parser.add_argument(
        "--table", type=str, help="Target table (e.g., model.oof_predictions)"
    )
    parser.add_argument("--file", type=str, help="Local parquet file to push")
    parser.add_argument(
        "--all-results",
        action="store_true",
        help="Push all results from data/results directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be pushed without pushing",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: Push Results to Cloud")
    logger.info("=" * 60)

    # Connect to cloud
    try:
        conn = get_postgres_connection()
        logger.info("✅ Connected to Prisma Cloud")
    except Exception as e:
        logger.error(f"❌ Failed to connect: {e}")
        sys.exit(1)

    results = []

    if args.all_results:
        # Push all results from local directory
        if not LOCAL_RESULTS_DIR.exists():
            logger.error(f"Results directory not found: {LOCAL_RESULTS_DIR}")
            sys.exit(1)

        for file_path in LOCAL_RESULTS_DIR.glob("*.parquet"):
            result_type = file_path.stem
            if result_type in RESULT_HANDLERS:
                logger.info(f"\n📤 Pushing {result_type}...")
                if args.dry_run:
                    df = pd.read_parquet(file_path)
                    logger.info(f"  Would push {len(df):,} rows")
                    results.append(
                        {"type": result_type, "rows": len(df), "status": "dry_run"}
                    )
                else:
                    try:
                        result = RESULT_HANDLERS[result_type](conn, file_path)
                        results.append(result)
                        logger.info(f"  ✅ Pushed {result['rows_pushed']:,} rows")
                    except Exception as e:
                        logger.error(f"  ❌ Failed: {e}")
                        results.append(
                            {"type": result_type, "status": "error", "error": str(e)}
                        )

    elif args.table and args.file:
        # Push single file to specific table
        file_path = Path(args.file)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            sys.exit(1)

        schema, table = args.table.split(".")

        logger.info(f"\n📤 Pushing {file_path} → {args.table}")
        if args.dry_run:
            df = pd.read_parquet(file_path)
            logger.info(f"  Would push {len(df):,} rows")
        else:
            df = pd.read_parquet(file_path)
            rows = push_dataframe_to_table(conn, df, schema, table)
            logger.info(f"  ✅ Pushed {rows:,} rows")
            results.append({"table": args.table, "rows_pushed": rows})

    else:
        parser.print_help()
        sys.exit(1)

    conn.close()

    # Summary
    if results:
        logger.info("\n" + "=" * 60)
        logger.info("PUSH SUMMARY")
        logger.info("=" * 60)
        for r in results:
            status_icon = "✅" if r.get("status") != "error" else "❌"
            rows = r.get("rows_pushed", r.get("rows", 0))
            name = r.get("table", r.get("type", "unknown"))
            logger.info(f"{status_icon} {name}: {rows:,} rows")


if __name__ == "__main__":
    main()
