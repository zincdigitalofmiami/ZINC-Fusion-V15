"""Fusion configuration.

This repository uses Prisma Postgres as the production database.
All training, inference, and operations use Prisma Postgres.
Frontend deployed on Vercel (Next.js + Inngest).

Environment Variables:
    DATABASE_URL         - Direct Prisma Postgres connection string
    FUSION_MODEL_DIR     - Path to model directory (default: models)
    HISTORICAL_DATA_PATH - Path to historical parquet files (for initial ingestion)
"""

import os
from pathlib import Path

# =============================================================================
# CANONICAL ENVIRONMENT VARIABLES
# =============================================================================

# Prisma Postgres direct connection (REQUIRED for psycopg2/sqlalchemy paths)
DATABASE_URL = os.environ.get("DATABASE_URL")

# Model directory
FUSION_MODEL_DIR = os.environ.get("FUSION_MODEL_DIR", "models")

# Historical data path (for ingestion scripts)
# Default to None - must be explicitly set for ingestion
HISTORICAL_DATA_PATH = os.environ.get("HISTORICAL_DATA_PATH")


# =============================================================================
# PATH HELPERS
# =============================================================================


def get_database_url() -> str:
    """Get Prisma Postgres connection URL."""
    if not DATABASE_URL:
        # Try loading from .env file
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        if env_path.exists():
            candidates: dict[str, str] = {}
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    if key == "DATABASE_URL":
                        candidates[key] = value.strip().strip('"').strip("'")
            for key in ("DATABASE_URL",):
                if candidates.get(key):
                    url = candidates[key]
                    if url.startswith("prisma+postgres://"):
                        raise ValueError(
                            "Direct postgres:// URL required. Set DATABASE_URL."
                        )
                    return url
        raise ValueError(
            "Database URL not set. Set DATABASE_URL in environment or .env file."
        )
    if DATABASE_URL.startswith("prisma+postgres://"):
        raise ValueError(
            "Direct postgres:// URL required. Set DATABASE_URL."
        )
    return DATABASE_URL


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
# SCHEMAS (Institutional Architecture - 13 schemas)
# =============================================================================

# Landing schemas: append-only source data
LANDING_SCHEMAS = ["mkt", "econ", "alt", "pos", "supply"]

# Derived schemas: computed from landing
DERIVED_SCHEMAS = ["features", "training"]

# Output schemas: model artifacts and predictions
OUTPUT_SCHEMAS = ["model", "forecasts", "analytics"]

# Governance schemas: operations
GOVERNANCE_SCHEMAS = ["ops"]

# Domain schemas
DOMAIN_SCHEMAS = ["vegas"]

# All schemas (canonical list)
SCHEMAS = (
    LANDING_SCHEMAS
    + DERIVED_SCHEMAS
    + OUTPUT_SCHEMAS
    + GOVERNANCE_SCHEMAS
    + DOMAIN_SCHEMAS
)

# BANNED schemas - fail hard if detected in new code
BANNED_SCHEMAS = [
    "raw",
    "gold",
    "silver",
    "bronze",
    "monitoring",
    "specialist",
    "weather",
]


# =============================================================================
# DRIVERS (Canonical - Use taxonomy.py for source of truth)
# =============================================================================

# Re-export from canonical source (fusion.taxonomy) for backward compatibility.
# Do NOT maintain a separate list here — taxonomy.py is the single source of truth.
from fusion.taxonomy import ALL_DRIVERS, ECONOMIC_DRIVERS, NEURAL_DRIVERS  # noqa: E402, F401, I001


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
