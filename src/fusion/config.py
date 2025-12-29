"""Fusion configuration.

This repository is DuckDB-first; orchestration (Dagster) and model frameworks
(AutoGluon/MLflow) have been removed.

Environment Variables:
    FUSION_DB_PATH    - Path to DuckDB database (default: data/fusion.db)
    FUSION_MODEL_DIR  - Path to model directory (default: models)
"""

import os
from pathlib import Path


# =============================================================================
# CANONICAL ENVIRONMENT VARIABLES
# =============================================================================

# Database path (relative to project root)
FUSION_DB_PATH = os.environ.get("FUSION_DB_PATH", "data/fusion.db")

# Model directory
FUSION_MODEL_DIR = os.environ.get("FUSION_MODEL_DIR", "models")


# =============================================================================
# PATH HELPERS
# =============================================================================


def get_db_path() -> Path:
    """Get absolute path to DuckDB database."""
    return Path(FUSION_DB_PATH).resolve()


def get_model_dir() -> Path:
    """Get absolute path to model directory."""
    return Path(FUSION_MODEL_DIR).resolve()


# =============================================================================
# SCHEMAS (Canonical - Medallion Architecture)
# =============================================================================

# Schema Architecture (Medallion)
SCHEMAS = [
    "raw",  # Bronze: Raw ingestion
    "silver",  # Silver: Validated, cleansed
    "gold",  # Gold: Business aggregates
    "features",  # Feature engineering
    "training",  # Model training (specialists, oof, meta)
    "forecasts",  # Predictions
    "monitoring",  # Performance tracking
    "specialist",  # Specialist metadata
    "weather",  # Weather data source
    "metadata",  # System metadata
    "archive",  # Legacy tables
]


# =============================================================================
# DRIVERS (Canonical - Use taxonomy.py for source of truth)
# =============================================================================

# NOTE: These are maintained for backward compatibility
# The canonical source is fusion.taxonomy.ECONOMIC_DRIVERS and fusion.taxonomy.NEURAL_DRIVERS

ECONOMIC_DRIVERS = [
    "crush",
    "china",
    "fx",
    "fed",
    "tariff",
    "energy",  # SEPARATE from biofuel
    "biofuel",  # SEPARATE from energy
    "palm",  # Normalized (not palm_oil)
    "volatility",
    "substitutes",
]

NEURAL_DRIVERS = [
    "neural_trend",
    "neural_regime",
    "neural_flow",
    "neural_sentiment",
    "neural_residual",
]

ALL_DRIVERS = ECONOMIC_DRIVERS + NEURAL_DRIVERS


# =============================================================================
# GRAIN SUFFIXES
# =============================================================================

GRAIN_SUFFIXES = ["_1h", "_1d", "_1w"]


# =============================================================================
# BANNED NAMES (Do not use these)
# =============================================================================

BANNED_PATTERNS = [
    "zinc_fusion",
    "zinc_fusion_v15",
    "fusion_v15",
    "ohlc",
    "ohlcv",
    "staging_",
    "big10_",  # outside archive
    "_v1",
    "_v2",
    "_latest",
    "_legacy",
    "/Volumes/",
]
