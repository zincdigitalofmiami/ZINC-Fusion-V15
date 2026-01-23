"""
Core Training Package - Shared Configuration
=============================================

LOCKED: 2026-01-15
All parameters frozen. Changes require explicit approval.

UPDATED: 2026-01-16
- Strategic horizons (63d/126d): GA-VMD-LSTM replaces Chronos-2
- Reference: Nature Scientific Reports 2025 - GA-VMD-LSTM for soybean oil
- 67.5% MAPE reduction vs standalone LSTM on soybean oil
- K=12 modes (GA-optimized for soybean oil specifically)
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load .env file to ensure DATABASE_URL is available
load_dotenv()

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
    # Updated 2026-01-22: Coverage filter removed - all features retained
    # Elite (44) + FRED (77) + FX (5) + Weather (~28) + COT + targets = ~170+ features
    # Expanded MAX to accommodate all features without coverage filtering
    MIN_FEATURES: int = 100
    MAX_FEATURES: int = 300
    TARGET_FEATURES: int = 170

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
            # === RATES (9) ===
            "FEDFUNDS",
            "SOFR",
            "DGS1MO",
            "DGS3MO",
            "DGS2",
            "DGS5",
            "DGS10",
            "DGS20",
            "DGS30",
            # === SPREADS (3) ===
            "T10Y2Y",
            "T10Y3M",
            "T10YIE",  # Breakeven inflation
            # === INFLATION EXPECTATIONS (daily) ===
            "T5YIE",  # 5Y breakeven inflation
            "T5YIFR",  # 5Y-5Y forward inflation expectation
            # === TIPS REAL YIELDS (daily) ===
            "DFII5",  # 5Y TIPS yield
            "DFII7",  # 7Y TIPS yield
            "DFII10",  # 10Y TIPS yield
            "DFII20",  # 20Y TIPS yield
            "DFII30",  # 30Y TIPS yield
            # === CREDIT (4) ===
            "BAMLH0A0HYM2",  # HY spread
            "BAMLC0A0CM",  # IG spread
            "DPRIME",  # Prime rate
            # === VOLATILITY (3) ===
            "VIXCLS",
            "OVXCLS",  # Crude oil vol (2007+)
            "GVZCLS",  # Gold vol (2008+)
            # === DOLLAR INDICES (4) ===
            "DTWEXBGS",  # Broad
            "DTWEXAFEGS",  # AFE (advanced)
            "DTWEXEMEGS",  # EME (emerging)
            "DXY",  # Dollar index
            # === FX RATES (12) ===
            "DEXBZUS",  # BRL
            "DEXCHUS",  # CNY
            "DEXUSEU",  # EUR
            "DEXJPUS",  # JPY
            "DEXMXUS",  # MXN
            "DEXCAUS",  # CAD
            "DEXINUS",  # INR
            "DEXKOUS",  # KRW
            "DEXMAUS",  # MYR (Malaysia - palm oil)
            "DEXSFUS",  # SGD
            "DEXTHUS",  # THB
            "DEXUSAL",  # AUD
            # === ENERGY PRICES (8) ===
            "DCOILWTICO",  # WTI crude
            "DCOILBRENTEU",  # Brent
            "DHOILNYH",  # Heating oil
            "DHHNGSP",  # Natural gas (Henry Hub)
            "DGASUSGULF",  # Gulf gasoline
            "DDFUELUSGULF",  # Diesel Gulf
            "DJFUELUSGULF",  # Jet fuel Gulf
            "DPROPANEMBTX",  # Propane
            # === MACRO INDICATORS (11) ===
            "GDP",
            "GDPC1",
            "INDPRO",
            "PAYEMS",
            "UNRATE",
            "ICSA",  # Initial claims
            "CCSA",  # Continued claims
            "UMCSENT",  # Michigan sentiment
            "PCE",
            "PCEPI",
            "PPIFIS",  # PPI Final Demand (replaced discontinued PPIFGS)
            # === COMMODITY PRICES (7) ===
            "PSOILUSDM",  # Soybean oil price (IMF)
            "PSOYBUSDM",  # Soybean price
            "PMAIZMTUSDM",  # Corn price
            "PWHEAMTUSDM",  # Wheat price
            "PCOPPUSDM",  # Copper price
            "PPOILUSDM",  # Palm oil price
            "PROILUSDM",  # Rapeseed oil
            # === FINANCIAL CONDITIONS (5) ===
            "NFCI",  # Chicago Fed NFCI
            "ANFCI",  # Chicago Fed Adjusted NFCI
            "STLFSI4",  # St Louis FSI
            "M2SL",  # Money supply
            "WALCL",  # Fed balance sheet
            # === POLICY UNCERTAINTY (5) ===
            "USEPUINDXD",  # Daily EPU
            "USEPUINDXM",  # Monthly EPU
            "EPUTRADE",  # Trade policy uncertainty
            "EMVTRADEPOLEMV",  # Trade policy EMV
            "CHNMAINLANDTPU",  # China TPU
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
# UPDATED 2026-01-17: Renamed from oof_core_zl_1d to oof_core_1d
OOF_TABLE_NAME = "training.oof_core_1d"

# Matrix table name (renamed from core_matrix_curated_1d)
MATRIX_TABLE_NAME = "training.matrix_1d"

# Column definitions: (name, sql_type, description)
OOF_COLUMNS = [
    ("trade_date", "DATE NOT NULL", "Date forecasting FROM"),
    ("symbol", "VARCHAR(20) NOT NULL DEFAULT 'ZL'", "Target symbol"),
    ("horizon_days", "INTEGER NOT NULL", "Forecast horizon (5/21/63/126)"),
    ("window_id", "INTEGER NOT NULL", "AutoGluon validation window index"),
    ("cutoff_date", "DATE NOT NULL", "Last date in training window"),
    ("p30", "DOUBLE PRECISION NOT NULL", "30th percentile forecast"),
    ("p50", "DOUBLE PRECISION NOT NULL", "50th percentile (median)"),
    ("p70", "DOUBLE PRECISION NOT NULL", "70th percentile forecast"),
    ("target_value", "DOUBLE PRECISION", "Realized return at horizon"),
    ("trained_at", "TIMESTAMP NOT NULL DEFAULT NOW()", "Training timestamp"),
    ("run_hash", "VARCHAR(64) NOT NULL", "Hash of matrix + config"),
    ("matrix_version", "VARCHAR(64)", "Hash of matrix_1d"),
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
    """
    Training configuration per CORE_TRAINING_SPEC_LOCKED.md

    UPDATED 2026-01-22:
    - Date window mandates REMOVED - use all available data
    - AutoGluon's DirectTabular handles missing values natively
    - Features with different start dates are retained (not filtered)
    - Tactical (5d/21d): Chronos-Bolt + RecursiveTabular
    - Strategic (63d/126d): GA-VMD-LSTM + DirectTabular ensemble
    """

    # Validation
    num_val_windows: int = 4  # Per locked spec

    # All features are OBSERVED (not known)
    covariate_type: str = "observed"

    # Predictor settings
    eval_metric: str = "WQL"  # Weighted Quantile Loss
    presets: str = "medium_quality"
    time_limit: int = 3600  # 1 hour per horizon

    # ==========================================================================
    # TACTICAL CONFIG (5d, 21d) - Short-term operational forecasts
    # ==========================================================================
    # UPDATED 2026-01-22: Removed date window mandate
    # AutoGluon handles missing values natively; use all available data
    # Features with different start dates are retained (not filtered)
    tactical_window_start: Optional[str] = None  # Use all available data
    tactical_models: List[str] = field(
        default_factory=lambda: [
            "Chronos",  # chronos-bolt-small
            "DirectTabular",
            "RecursiveTabular",  # INCLUDED for tactical (autoregressive good for short)
            "AutoETS",
            "Theta",
            "SeasonalNaive",
        ]
    )
    tactical_chronos_config: Dict = field(
        default_factory=lambda: {
            "model_path": "autogluon/chronos-bolt-small",
            # No fine-tuning for Chronos-Bolt
        }
    )

    # ==========================================================================
    # STRATEGIC CONFIG (63d, 126d) - Long-term procurement planning
    # ==========================================================================
    # UPDATED 2026-01-16: GA-VMD-LSTM replaces Chronos-2 for strategic horizons
    # Reference: Nature Scientific Reports 2025 - 67.5% MAPE reduction on soybean oil
    #
    # Architecture:
    # 1. GA-optimized VMD decomposes price into K=12 IMFs (soybean oil optimal)
    # 2. Each IMF gets its own LSTM with frequency-appropriate lookback
    # 3. Ensemble all IMF predictions for final forecast
    #
    # Fallback ensemble: DirectTabular + AutoETS + Theta for robustness
    # UPDATED 2026-01-22: Removed date window mandate - use all available data
    strategic_window_start: Optional[str] = None  # Use all available data
    strategic_models: List[str] = field(
        default_factory=lambda: [
            "GA-VMD-LSTM",  # Primary: Nature 2025 paper, soybean oil optimized
            "DirectTabular",  # Fallback ensemble member
            "AutoETS",  # Fallback ensemble member
            "Theta",  # Fallback ensemble member
            # NO Chronos-2: GA-VMD-LSTM outperforms on soybean oil by 67.5%
            # NO RecursiveTabular: error propagation over long horizons
        ]
    )

    # GA-VMD-LSTM config for 63d (per Nature 2025 paper)
    ga_vmd_lstm_63d_config: Dict = field(
        default_factory=lambda: {
            # VMD Decomposition (GA-optimized for soybean oil)
            "vmd_K": 12,  # Number of IMFs (paper finding: optimal for soy oil)
            "vmd_alpha": 2000,  # Bandwidth constraint
            "vmd_tau": 0.0,  # Noise tolerance
            "optimize_vmd": True,  # Run GA optimization on first fit

            # LSTM per IMF
            "lstm_hidden_units": 64,
            "lstm_num_layers": 2,
            "lstm_dropout": 0.2,
            "lstm_lookback": 30,  # Adjusted per IMF frequency
            "lstm_epochs": 100,
            "lstm_patience": 10,  # Early stopping
            "lstm_batch_size": 32,

            # GA optimization
            "ga_population": 20,
            "ga_generations": 15,
            "ga_mutation_rate": 0.1,

            # Output
            "quantiles": [0.3, 0.5, 0.7],
            "device": "cpu",
        }
    )

    # GA-VMD-LSTM config for 126d (longer horizon adjustments)
    ga_vmd_lstm_126d_config: Dict = field(
        default_factory=lambda: {
            # VMD Decomposition - more modes for longer patterns
            "vmd_K": 14,  # More modes for longer horizon
            "vmd_alpha": 2500,  # Higher bandwidth constraint
            "vmd_tau": 0.0,
            "optimize_vmd": True,

            # LSTM per IMF - longer lookback for strategic
            "lstm_hidden_units": 80,
            "lstm_num_layers": 2,
            "lstm_dropout": 0.25,
            "lstm_lookback": 60,  # Longer context for 126d
            "lstm_epochs": 120,
            "lstm_patience": 15,
            "lstm_batch_size": 16,  # Smaller batch for memory

            # GA optimization
            "ga_population": 20,
            "ga_generations": 20,  # More generations for 126d
            "ga_mutation_rate": 0.1,

            # Output
            "quantiles": [0.3, 0.5, 0.7],
            "device": "cpu",
        }
    )

    # Legacy Chronos-2 configs (kept for reference/fallback)
    chronos2_63d_config: Dict = field(
        default_factory=lambda: {
            "context_length": 1024,
            "batch_size": 16,
            "device": "cpu",
            "fine_tune": True,
            "fine_tune_mode": "lora",
            "fine_tune_lr": 5e-5,
            "fine_tune_steps": 300,
            "fine_tune_batch_size": 4,
            "fine_tune_context_length": 512,
            "fine_tune_lora_config": {"r": 4, "lora_alpha": 8},
        }
    )

    chronos2_126d_config: Dict = field(
        default_factory=lambda: {
            "context_length": 2048,
            "batch_size": 8,
            "device": "cpu",
            "fine_tune": True,
            "fine_tune_mode": "lora",
            "fine_tune_lr": 5e-5,
            "fine_tune_steps": 500,
            "fine_tune_batch_size": 2,
            "fine_tune_context_length": 1024,
            "fine_tune_lora_config": {"r": 8, "lora_alpha": 16},
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
