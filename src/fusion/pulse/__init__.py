# ZINC-FUSION-V15 Pulse Engine
"""
Pulse Engine - AI-generated market intelligence for training features.

Modules:
- engine: Orchestrates Intel Drop generation across 11 domains
- schema: Data models and JSON schemas
- validators: Pulse validation and parsing
- compute: Quant computation utilities
- retrieval: External data source fetching
- extractors: Feature extraction from pulses
- storage: Prisma PostgreSQL persistence
"""

from .engine import PulseEngine
from .schema import PulseSchema, IntelDrop, HorizonForecast
from .validators import validate_pulse, PulseValidationError
from .compute import (
    linear_regression,
    correlation,
    zscore,
    percentile_rank,
    compute_quant_payload,
    compute_driver_weights,
)
from .retrieval import (
    RetrievalLayer,
    RetrievalResult,
    SourceStatus,
    fetch_domain_sync,
    DOMAIN_PRIORITY_SOURCES,
    FRED_SERIES,
)
from .extractors import (
    ExtractedFeatures,
    extract_all_features,
    features_to_training_row,
    parse_narrative_sentiment,
)
from .storage import (
    insert_intel_drop,
    insert_intel_drop_rows,
    get_latest_intel_drops,
    get_domain_history,
    get_consensus_view,
)

__all__ = [
    # Engine
    "PulseEngine",
    # Schema
    "PulseSchema",
    "IntelDrop",
    "HorizonForecast",
    # Validators
    "validate_pulse",
    "PulseValidationError",
    # Compute
    "linear_regression",
    "correlation",
    "zscore",
    "percentile_rank",
    "compute_quant_payload",
    "compute_driver_weights",
    # Retrieval
    "RetrievalLayer",
    "RetrievalResult",
    "SourceStatus",
    "fetch_domain_sync",
    "DOMAIN_PRIORITY_SOURCES",
    "FRED_SERIES",
    # Extractors
    "ExtractedFeatures",
    "extract_all_features",
    "features_to_training_row",
    "parse_narrative_sentiment",
    # Storage
    "insert_intel_drop",
    "insert_intel_drop_rows",
    "get_latest_intel_drops",
    "get_domain_history",
    "get_consensus_view",
]

DOMAINS = [
    "CRUSH",
    "CHINA",
    "FX",
    "FED",
    "TARIFF",
    "ENERGY",
    "BIOFUEL",
    "PALM",
    "VOLATILITY",
    "SUBSTITUTES",
    "TRUMP_EFFECT",
]

HORIZONS = ["1W", "1M", "3M", "6M"]
