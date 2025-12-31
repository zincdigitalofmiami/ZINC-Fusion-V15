"""Fusion configuration.

This repository uses Prisma Postgres as the authoritative database.
DuckDB (data/fusion.db) is ARCHIVE ONLY - do not use for training or operations.

Architecture:
    CLOUD (Prisma Postgres)  - Ingestion target, dashboard source, authoritative
    LOCAL (training only)    - Sync from cloud, train, push results back

Environment Variables:
    DATABASE_URL         - Prisma Postgres connection string (REQUIRED)
    FUSION_MODEL_DIR     - Path to model directory (default: models)
    HISTORICAL_DATA_PATH - Path to historical parquet files (for initial ingestion)

Deprecated (archive only):
    FUSION_DB_PATH    - Path to DuckDB archive (default: data/fusion.db)
"""

import os
from pathlib import Path


# =============================================================================
# CANONICAL ENVIRONMENT VARIABLES
# =============================================================================

# Prisma Postgres connection (AUTHORITATIVE)
DATABASE_URL = os.environ.get("DATABASE_URL")

# Model directory
FUSION_MODEL_DIR = os.environ.get("FUSION_MODEL_DIR", "models")

# Historical data path (for ingestion scripts)
# Default to None - must be explicitly set for ingestion
HISTORICAL_DATA_PATH = os.environ.get("HISTORICAL_DATA_PATH")

# DuckDB archive path (READ-ONLY, for historical extraction only)
FUSION_DB_PATH = os.environ.get("FUSION_DB_PATH", "data/fusion.db")


# =============================================================================
# PATH HELPERS
# =============================================================================


def get_database_url() -> str:
    """Get Prisma Postgres connection URL."""
    if not DATABASE_URL:
        # Try loading from .env file
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.startswith("DATABASE_URL="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        raise ValueError("DATABASE_URL not set. Set it in environment or .env file.")
    return DATABASE_URL


def get_db_path() -> Path:
    """Get absolute path to DuckDB archive (READ-ONLY)."""
    return Path(FUSION_DB_PATH).resolve()


def get_model_dir() -> Path:
    """Get absolute path to model directory."""
    return Path(FUSION_MODEL_DIR).resolve()


def get_historical_data_path() -> Path:
    """Get path to historical parquet files for ingestion.

    Must be explicitly set via HISTORICAL_DATA_PATH env var.
    This is only needed for initial ingestion from local files.
    """
    if not HISTORICAL_DATA_PATH:
        raise ValueError(
            "HISTORICAL_DATA_PATH not set. Set it to the directory containing "
            "historical parquet files (e.g., /Volumes/Satechi Hub/Historical Data)"
        )
    return Path(HISTORICAL_DATA_PATH).resolve()


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
