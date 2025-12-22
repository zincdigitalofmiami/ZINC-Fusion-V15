"""
ZINC FUSION V15 - Dagster Definitions
=====================================
Production-grade ML pipeline with full training lineage.

Pipeline Flow:
  📊 Data Sources → 🔧 Features → 🎯 Core Training → 📦 OOF → 🎒 Bagging → 🔗 Join → 🧠 L1 Meta → 🔮 L2 Fusion → 🎲 L3 Risk → 📈 Forecasts
"""

from dagster import (
    Definitions,
    ScheduleDefinition,
    define_asset_job,
    load_assets_from_modules,
    AssetSelection,
)

# Resources
from .defs.resources import DuckDBResource, DataValidationResource

# Training Pipeline Assets - Full ML Pipeline with proper lineage
from .defs import training_pipeline_assets

# Legacy schema creation
from .defs.zinc_fusion_assets import (
    create_schemas,
    create_raw_tables,
    create_feature_tables,
    create_training_tables,
    create_forecast_tables,
)

# =============================================================================
# LOAD ALL ASSETS
# =============================================================================

# Training pipeline assets (full ML pipeline)
training_assets = load_assets_from_modules([training_pipeline_assets])

# Legacy infrastructure assets
legacy_assets = [
    create_schemas,
    create_raw_tables,
    create_feature_tables,
    create_training_tables,
    create_forecast_tables,
]

all_assets = training_assets + legacy_assets

# =============================================================================
# JOBS
# =============================================================================

# Full training pipeline job
full_training_pipeline = define_asset_job(
    name="full_training_pipeline",
    selection=AssetSelection.groups(
        "data_sources",
        "features",
        "core_training",
        "oof_extraction",
        "bagging_ensemble",
        "join_stack",
        "meta_learner",
        "fusion_engine",
        "risk_engine",
        "forecasts",
    ),
    description="🚀 Complete ML Pipeline: Data → Features → Training → OOF → Bagging → Meta → Fusion → Risk → Forecasts",
)

# Core training job (just specialists)
core_training_job = define_asset_job(
    name="core_training_job",
    selection=AssetSelection.groups("core_training"),
    description="🎯 Train all 10 Big-10 specialist models",
)

# Meta-learning job
meta_learning_job = define_asset_job(
    name="meta_learning_job",
    selection=AssetSelection.groups("meta_learner", "fusion_engine", "risk_engine"),
    description="🧠 L1 Meta → L2 Fusion → L3 Risk pipeline",
)

# Forecast generation job
forecast_job = define_asset_job(
    name="forecast_job",
    selection=AssetSelection.groups("forecasts"),
    description="📈 Generate production forecasts",
)

# =============================================================================
# SCHEDULES
# =============================================================================

# Daily training refresh (6 AM Eastern = 11:00 UTC)
daily_training_schedule = ScheduleDefinition(
    job=full_training_pipeline,
    cron_schedule="0 11 * * *",  # 6 AM Eastern
    name="daily_training_refresh",
    description="Daily full pipeline refresh at 6 AM Eastern",
)

# =============================================================================
# RESOURCES
# =============================================================================

resources = {
    "duckdb_resource": DuckDBResource(
        database_path="/Volumes/Satechi Hub/ZINC-FUSION-V15/data/zinc_fusion_v15.db"
    ),
}

# =============================================================================
# DEFINITIONS
# =============================================================================

defs = Definitions(
    assets=all_assets,
    jobs=[
        full_training_pipeline,
        core_training_job,
        meta_learning_job,
        forecast_job,
    ],
    schedules=[daily_training_schedule],
    resources=resources,
)
