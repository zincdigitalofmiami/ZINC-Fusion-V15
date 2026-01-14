#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Prisma → MLflow Sync
=====================================

Syncs Prisma Postgres data to MLflow for unified experiment tracking:
- Model Registry → MLflow Registered Models
- Training Runs → MLflow Runs with metrics
- Data Sources → MLflow Datasets (metadata)
- Feature Tables → MLflow Dataset profiles

Usage:
    python scripts/sync_prisma_to_mlflow.py --all
    python scripts/sync_prisma_to_mlflow.py --models
    python scripts/sync_prisma_to_mlflow.py --runs
    python scripts/sync_prisma_to_mlflow.py --datasets
"""

import os
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import mlflow
from mlflow.tracking import MlflowClient
import psycopg2
from psycopg2.extras import RealDictCursor

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")

# Prisma database URL (parse from env)
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Experiment naming
EXPERIMENT_PREFIX = "zinc-fusion"


def get_prisma_connection():
    """Get connection to Prisma Postgres database."""
    # Parse DATABASE_URL or use direct connection
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

    # Fallback to local MLflow postgres (for testing)
    return psycopg2.connect(
        host="localhost",
        port=5432,
        database="mlflow",
        user="mlflow",
        password="mlflow",
        cursor_factory=RealDictCursor
    )


def get_mlflow_client() -> MlflowClient:
    """Get configured MLflow client."""
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    return MlflowClient(MLFLOW_TRACKING_URI)


# =============================================================================
# SYNC MODEL REGISTRY
# =============================================================================

def sync_model_registry(client: MlflowClient, conn) -> Dict[str, Any]:
    """
    Sync model.model_registry → MLflow Registered Models.

    Creates:
    - Registered model per model_id
    - Version per Prisma version
    - Tags with all metadata
    """
    results = {"synced": 0, "skipped": 0, "errors": []}

    with conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM model.model_registry
            ORDER BY model_type, horizon, trained_at
        """)
        models = cur.fetchall()

    print(f"\n📦 Syncing {len(models)} models to MLflow Registry...")

    for model in models:
        model_name = model["model_id"]

        try:
            # Create or get registered model
            try:
                client.create_registered_model(
                    name=model_name,
                    description=model.get("notes") or f"{model['model_name']} - {model['model_type']}"
                )
                print(f"  ✅ Created registered model: {model_name}")
            except Exception:
                # Already exists
                pass

            # Set model tags
            tags = {
                "model_type": model["model_type"],
                "model_name": model["model_name"],
                "horizon": str(model.get("horizon") or ""),
                "status": model["status"],
                "is_champion": str(model.get("is_champion", False)),
                "best_model": model.get("best_model") or "",
                "training_mode": model.get("training_mode") or "",
                "mase": str(model.get("mase") or ""),
                "models_trained": str(model.get("models_trained") or ""),
                "trained_at": str(model.get("trained_at") or ""),
                "source": "prisma_sync"
            }

            for key, value in tags.items():
                if value:
                    try:
                        client.set_registered_model_tag(model_name, key, value)
                    except Exception:
                        pass

            results["synced"] += 1

        except Exception as e:
            results["errors"].append(f"{model_name}: {str(e)}")
            print(f"  ❌ Error syncing {model_name}: {e}")

    return results


# =============================================================================
# SYNC TRAINING RUNS
# =============================================================================

def sync_training_runs(client: MlflowClient, conn) -> Dict[str, Any]:
    """
    Sync ops.training_runs → MLflow Experiments & Runs.

    Creates:
    - Experiment per model_type/specialist
    - Run per training run with metrics
    """
    results = {"synced": 0, "skipped": 0, "errors": []}

    with conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM ops.training_runs
            ORDER BY started_at DESC
        """)
        runs = cur.fetchall()

    print(f"\n🏃 Syncing {len(runs)} training runs to MLflow...")

    for run in runs:
        # Determine experiment name
        if run.get("specialist_name"):
            exp_name = f"{EXPERIMENT_PREFIX}/specialist/{run['specialist_name']}"
        else:
            exp_name = f"{EXPERIMENT_PREFIX}/{run['model_type']}"

        if run.get("horizon"):
            exp_name += f"/h{run['horizon']}d"

        try:
            # Create or get experiment
            experiment = client.get_experiment_by_name(exp_name)
            if not experiment:
                exp_id = client.create_experiment(
                    name=exp_name,
                    tags={"model_type": run["model_type"]}
                )
                print(f"  📁 Created experiment: {exp_name}")
            else:
                exp_id = experiment.experiment_id

            # Check if run already synced (by run_id tag)
            existing_runs = client.search_runs(
                experiment_ids=[exp_id],
                filter_string=f"tags.prisma_run_id = '{run['run_id']}'"
            )

            if existing_runs:
                results["skipped"] += 1
                continue

            # Create MLflow run
            mlflow_run = client.create_run(
                experiment_id=exp_id,
                run_name=run["run_name"],
                start_time=int(run["started_at"].timestamp() * 1000) if run.get("started_at") else None,
                tags={
                    "prisma_run_id": run["run_id"],
                    "model_type": run["model_type"],
                    "specialist_name": run.get("specialist_name") or "",
                    "horizon": str(run.get("horizon") or ""),
                    "training_mode": run.get("training_mode") or "",
                    "status": run["status"],
                    "source": "prisma_sync"
                }
            )

            run_id = mlflow_run.info.run_id

            # Log metrics
            if run.get("mase"):
                client.log_metric(run_id, "mase", float(run["mase"]))

            if run.get("duration_seconds"):
                client.log_metric(run_id, "training_time_seconds", float(run["duration_seconds"]))

            # Log metrics from JSON
            metrics = run.get("metrics") or {}
            if isinstance(metrics, dict):
                for key, value in metrics.items():
                    if isinstance(value, (int, float)):
                        client.log_metric(run_id, key, value)

            # Log parameters
            if run.get("hyperparameters"):
                params = run["hyperparameters"]
                if isinstance(params, dict):
                    for key, value in params.items():
                        client.log_param(run_id, key, str(value))

            # End run if completed
            if run["status"] == "completed" and run.get("completed_at"):
                client.set_terminated(
                    run_id,
                    status="FINISHED",
                    end_time=int(run["completed_at"].timestamp() * 1000)
                )
            elif run["status"] == "failed":
                client.set_terminated(run_id, status="FAILED")

            results["synced"] += 1
            print(f"  ✅ Synced run: {run['run_name']}")

        except Exception as e:
            results["errors"].append(f"{run['run_name']}: {str(e)}")
            print(f"  ❌ Error syncing {run['run_name']}: {e}")

    return results


# =============================================================================
# SYNC DATA SOURCES AS DATASETS
# =============================================================================

def sync_data_sources(client: MlflowClient, conn) -> Dict[str, Any]:
    """
    Sync ops.data_source_registry → MLflow Datasets.

    Registers each data source as an MLflow dataset with metadata.
    """
    results = {"synced": 0, "skipped": 0, "errors": []}

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM ops.data_source_registry ORDER BY source_id")
        sources = cur.fetchall()

    print(f"\n📊 Syncing {len(sources)} data sources to MLflow...")

    # Create a datasets experiment
    exp_name = f"{EXPERIMENT_PREFIX}/datasets/sources"
    experiment = client.get_experiment_by_name(exp_name)
    if not experiment:
        exp_id = client.create_experiment(
            name=exp_name,
            tags={"type": "data_sources"}
        )
        print(f"  📁 Created experiment: {exp_name}")
    else:
        exp_id = experiment.experiment_id

    for source in sources:
        source_id = source["source_id"]

        try:
            # Check if already synced
            existing = client.search_runs(
                experiment_ids=[exp_id],
                filter_string=f"tags.source_id = '{source_id}'"
            )

            if existing:
                results["skipped"] += 1
                continue

            # Create run for this data source
            mlflow_run = client.create_run(
                experiment_id=exp_id,
                run_name=f"datasource-{source_id}",
                tags={
                    "source_id": source_id,
                    "source_name": source["source_name"],
                    "target_table": source["target_table"],
                    "target_schema": source["target_schema"],
                    "api_provider": source.get("api_provider") or "",
                    "update_frequency": source.get("update_frequency") or "",
                    "is_active": str(source.get("is_active", False)),
                    "requires_subscription": str(source.get("requires_subscription", False)),
                    "type": "data_source",
                    "source": "prisma_sync"
                }
            )

            run_id = mlflow_run.info.run_id

            # Log parameters (metadata)
            params = {
                "description": source.get("description") or "",
                "api_endpoint": source.get("api_endpoint") or "",
                "response_format": source.get("response_format") or "",
                "date_column": source.get("date_column") or "",
                "entity_column": source.get("entity_column") or "",
                "typical_lag_hours": str(source.get("typical_lag_hours") or ""),
                "ingestion_script": source.get("ingestion_script") or "",
                "notes": source.get("notes") or ""
            }

            for key, value in params.items():
                if value:
                    client.log_param(run_id, key, value[:500])  # Truncate long values

            client.set_terminated(run_id, status="FINISHED")

            results["synced"] += 1
            print(f"  ✅ Synced data source: {source_id}")

        except Exception as e:
            results["errors"].append(f"{source_id}: {str(e)}")
            print(f"  ❌ Error syncing {source_id}: {e}")

    return results


# =============================================================================
# SYNC FEATURE TABLES
# =============================================================================

def sync_feature_tables(client: MlflowClient, conn) -> Dict[str, Any]:
    """
    Sync feature table metadata → MLflow.

    Creates dataset cards for each specialist feature table.
    """
    results = {"synced": 0, "skipped": 0, "errors": []}

    # Get row counts for feature tables
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                schemaname as schema_name,
                relname as table_name,
                n_live_tup as row_count
            FROM pg_stat_user_tables
            WHERE schemaname IN ('training', 'silver', 'gold')
            AND n_live_tup > 0
            ORDER BY n_live_tup DESC
        """)
        tables = cur.fetchall()

    print(f"\n📋 Syncing {len(tables)} feature tables to MLflow...")

    # Create features experiment
    exp_name = f"{EXPERIMENT_PREFIX}/datasets/features"
    experiment = client.get_experiment_by_name(exp_name)
    if not experiment:
        exp_id = client.create_experiment(
            name=exp_name,
            tags={"type": "feature_tables"}
        )
        print(f"  📁 Created experiment: {exp_name}")
    else:
        exp_id = experiment.experiment_id

    for table in tables:
        table_key = f"{table['schema_name']}.{table['table_name']}"

        try:
            # Check if already synced
            existing = client.search_runs(
                experiment_ids=[exp_id],
                filter_string=f"tags.table_key = '{table_key}'"
            )

            if existing:
                # Update row count metric
                run_id = existing[0].info.run_id
                client.log_metric(run_id, "row_count", int(table["row_count"]))
                results["skipped"] += 1
                continue

            # Get column info
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    LIMIT 50
                """, (table["schema_name"], table["table_name"]))
                columns = cur.fetchall()

            # Create run for this table
            mlflow_run = client.create_run(
                experiment_id=exp_id,
                run_name=f"table-{table['table_name']}",
                tags={
                    "table_key": table_key,
                    "schema_name": table["schema_name"],
                    "table_name": table["table_name"],
                    "column_count": str(len(columns)),
                    "type": "feature_table",
                    "source": "prisma_sync"
                }
            )

            run_id = mlflow_run.info.run_id

            # Log metrics
            client.log_metric(run_id, "row_count", int(table["row_count"]))
            client.log_metric(run_id, "column_count", len(columns))

            # Log column schema as param
            schema_str = json.dumps([
                {"name": c["column_name"], "type": c["data_type"]}
                for c in columns
            ])
            client.log_param(run_id, "schema", schema_str[:500])

            client.set_terminated(run_id, status="FINISHED")

            results["synced"] += 1
            print(f"  ✅ Synced table: {table_key} ({table['row_count']:,} rows)")

        except Exception as e:
            results["errors"].append(f"{table_key}: {str(e)}")
            print(f"  ❌ Error syncing {table_key}: {e}")

    return results


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Sync Prisma data to MLflow")
    parser.add_argument("--all", action="store_true", help="Sync everything")
    parser.add_argument("--models", action="store_true", help="Sync model registry")
    parser.add_argument("--runs", action="store_true", help="Sync training runs")
    parser.add_argument("--datasets", action="store_true", help="Sync data sources")
    parser.add_argument("--features", action="store_true", help="Sync feature tables")

    args = parser.parse_args()

    # Default to --all if no flags
    if not any([args.all, args.models, args.runs, args.datasets, args.features]):
        args.all = True

    print("=" * 60)
    print("🔄 ZINC-FUSION: Prisma → MLflow Sync")
    print("=" * 60)
    print(f"\nMLflow URI: {MLFLOW_TRACKING_URI}")

    # Test MLflow connection
    try:
        client = get_mlflow_client()
        client.search_experiments()
        print("✅ MLflow connection OK")
    except Exception as e:
        print(f"❌ MLflow connection failed: {e}")
        print("\nMake sure MLflow is running: ./scripts/start-mlflow.sh")
        return

    # Test Prisma connection
    try:
        conn = get_prisma_connection()
        print("✅ Prisma database connection OK")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\nSet DATABASE_URL environment variable")
        return

    results = {}

    try:
        if args.all or args.models:
            results["models"] = sync_model_registry(client, conn)

        if args.all or args.runs:
            results["runs"] = sync_training_runs(client, conn)

        if args.all or args.datasets:
            results["datasets"] = sync_data_sources(client, conn)

        if args.all or args.features:
            results["features"] = sync_feature_tables(client, conn)

    finally:
        conn.close()

    # Summary
    print("\n" + "=" * 60)
    print("📊 SYNC SUMMARY")
    print("=" * 60)

    total_synced = 0
    total_skipped = 0
    total_errors = 0

    for category, res in results.items():
        print(f"\n{category.upper()}:")
        print(f"  Synced: {res['synced']}")
        print(f"  Skipped: {res['skipped']}")
        print(f"  Errors: {len(res['errors'])}")

        total_synced += res['synced']
        total_skipped += res['skipped']
        total_errors += len(res['errors'])

        if res['errors']:
            print("  Error details:")
            for err in res['errors'][:5]:
                print(f"    - {err}")

    print(f"\n{'=' * 60}")
    print(f"TOTAL: {total_synced} synced, {total_skipped} skipped, {total_errors} errors")
    print(f"\n🎉 View results at: {MLFLOW_TRACKING_URI}")


if __name__ == "__main__":
    main()
