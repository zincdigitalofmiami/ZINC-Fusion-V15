"""
Core Training Package - Shared Configuration
=============================================

LOCKED: 2026-01-15
All parameters frozen. Changes require explicit approval.
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict
from pathlib import Path

# =============================================================================
# DATABASE
# =============================================================================

DATABASE_URL = os.getenv("DATABASE_URL")

# =============================================================================
# SYMBOLS & HORIZONS
# =============================================================================

TARGET_SYMBOL = "ZL"
HORIZONS = [5, 21, 63, 126]
QUANTILES = [0.3, 0.5, 0.7]

# Tactical vs Strategic split
TACTICAL_HORIZONS = [5, 21]
STRATEGIC_HORIZONS = [63, 126]

# =============================================================================
# OPTIONS CONFIGURATION (PHASE 1)
# =============================================================================


@dataclass
class OptionsConfig:
    """LOCKED: OI-weighted, 30-day roll threshold."""

    weighting: str = "oi"  # open interest weighted
    roll_threshold_days: int = 30
    normalize_greeks: bool = True
    risk_free_rate_series: str = "DGS3MO"  # 3-month treasury


OPTIONS_CONFIG = OptionsConfig()

# =============================================================================
# FEATURE MATRIX CONFIGURATION (PHASE 3)
# =============================================================================


@dataclass
class FeatureMatrixConfig:
    """LOCKED: Blanket inclusion with curation rules."""

    # Feature count guardrails (HARD FAIL, not smoke alarm)
    MIN_FEATURES: int = 120
    MAX_FEATURES: int = 350
    TARGET_FEATURES: int = 213

    # Normalization
    NORMALIZE_METHOD: str = "zscore"
    FIT_ON_TRAINING_ONLY: bool = True

    # Null/constant column thresholds
    MAX_NULL_RATIO: float = 0.30  # >30% null = drop column
    MIN_VARIANCE_RATIO: float = 1e-8  # Constant if variance < this

    # Weather aggregation regions (NOT station-level)
    WEATHER_REGIONS: List[str] = field(
        default_factory=lambda: [
            "us_midwest",  # IA/IL/IN/MN
            "brazil_south",  # RS/PR
            "brazil_central",  # MT/MS/GO
            "argentina_pampas",  # BA/SF/CO
        ]
    )

    # Weather features per region (7 per region = 28 total)
    WEATHER_FEATURES: List[str] = field(
        default_factory=lambda: [
            "temp_anomaly_mean",
            "temp_volatility",
            "precip_anomaly_mean",
            "precip_volatility",
            "persistence",  # rolling mean reversion speed
            "stress_upper",  # upper tail
            "stress_lower",  # lower tail
        ]
    )

    # FRED series to include (TAGGED macro/financial only)
    FRED_MACRO_SERIES: List[str] = field(
        default_factory=lambda: [
            # Rates
            "FEDFUNDS",
            "DGS1MO",
            "DGS3MO",
            "DGS2",
            "DGS5",
            "DGS10",
            "DGS30",
            # Spreads
            "T10Y2Y",
            "T10Y3M",
            # Credit
            "DAAA",
            "DBAA",
            "BAMLH0A0HYM2",
            "BAMLC0A0CM",
            # Volatility
            "VIXCLS",
            # Dollar
            "DTWEXBGS",
            "DTWEXAFEGS",
            "DTWEXEMEGS",
        ]
    )

    # Energy symbols (for cross-commodity features)
    ENERGY_SYMBOLS: List[str] = field(default_factory=lambda: ["CL", "NG", "HO", "RB"])

    # Substitute symbols (competitive products)
    SUBSTITUTE_SYMBOLS: List[str] = field(
        default_factory=lambda: ["ZS", "ZM", "ZC", "ZW", "CPO", "GC", "SI"]
    )


FEATURE_MATRIX_CONFIG = FeatureMatrixConfig()

# =============================================================================
# OOF SCHEMA (PHASE 4)
# =============================================================================

# CANONICAL: Single table with horizon_days column (not per-horizon tables)
OOF_TABLE_NAME = "training.oof_core_zl_1d"

# Column definitions: (name, sql_type, description)
OOF_COLUMNS = [
    ("trade_date", "DATE NOT NULL", "Date forecasting FROM"),
    ("horizon_days", "INTEGER NOT NULL", "Forecast horizon (5/21/63/126)"),
    ("window_id", "INTEGER NOT NULL", "AutoGluon validation window index"),
    ("cutoff_date", "DATE NOT NULL", "Last date in training window"),
    ("core_p30", "DOUBLE PRECISION NOT NULL", "30th percentile forecast"),
    ("core_p50", "DOUBLE PRECISION NOT NULL", "50th percentile (median)"),
    ("core_p70", "DOUBLE PRECISION NOT NULL", "70th percentile forecast"),
    ("target_value", "DOUBLE PRECISION", "Realized return at horizon"),
    ("trained_at", "TIMESTAMP NOT NULL", "Training timestamp"),
    ("core_run_hash", "VARCHAR(64) NOT NULL", "Hash of matrix + config"),
    ("matrix_version", "VARCHAR(64)", "Hash of core_matrix_curated"),
    ("options_version", "VARCHAR(64)", "Hash of options_features"),
]

# Column names only (for validation)
OOF_COLUMN_NAMES = [col[0] for col in OOF_COLUMNS]

# L1 Interface Contract
L1_CONTRACT = {
    "core_columns": 12,  # 4 horizons × 3 quantiles
    "specialist_columns": 132,  # 11 specialists × 4 horizons × 3 quantiles
    "total_l1_inputs": 144,
    "naming_pattern": "{model}_{horizon}_p{quantile}",
    "loss": "quantile_pinball",
}

# =============================================================================
# TRAINING CONFIGURATION (PHASE 6)
# =============================================================================


@dataclass
class TrainingConfig:
    """LOCKED: TimeSeriesPredictor with expanding windows."""

    # Validation
    num_val_windows: int = 3

    # All features are OBSERVED (not known)
    covariate_type: str = "observed"

    # Tactical config (5d, 21d)
    tactical_window_years: int = 7
    tactical_models: List[str] = field(
        default_factory=lambda: [
            "Chronos-Bolt",
            "DirectTabular",
            "ETS",
            "Theta",
            "SeasonalNaive",
        ]
    )

    # Strategic config (63d, 126d)
    strategic_window_start: str = "2000-01-01"
    strategic_models: List[str] = field(
        default_factory=lambda: [
            "Chronos-2-LoRA",
            "DirectTabular",
            "ETS",
            "Theta",
            "SeasonalNaive",
        ]
    )

    # Chronos-2 LoRA fine-tuning
    chronos2_lora_config: Dict = field(
        default_factory=lambda: {
            "fine_tune": True,
            "fine_tune_mode": "lora",
            "fine_tune_lr": 1e-4,
            "fine_tune_steps": 1500,
            "fine_tune_batch_size": 32,
            "context_length": 512,
        }
    )


TRAINING_CONFIG = TrainingConfig()

# =============================================================================
# PATHS
# =============================================================================

PACKAGE_ROOT = Path(__file__).parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models" / "core_v2"
SCALERS_DIR = PROJECT_ROOT / "models" / "core_v2" / "scalers"

# =============================================================================
# VALIDATION
# =============================================================================


def validate_config():
    """Validate configuration on import."""
    if not DATABASE_URL:
        raise EnvironmentError("DATABASE_URL not set")

    # Ensure model dirs exist
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    SCALERS_DIR.mkdir(parents=True, exist_ok=True)

    return True
