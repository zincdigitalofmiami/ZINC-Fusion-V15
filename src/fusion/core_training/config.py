"""
Core Training Package - Shared Configuration
=============================================

LOCKED: 2026-01-15
All parameters frozen. Changes require explicit approval.

ACTUAL MODEL: DirectTabular (AutoGluon) for ALL horizons.
No Chronos. No GA-VMD-LSTM. Just DirectTabular.
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

    # Feature count guardrails - NO LIMITS
    # 2026-01-23: ALL DATA GOES IN, NO FILTERING
    MIN_FEATURES: int = 1
    MAX_FEATURES: int = 9999
    TARGET_FEATURES: int = 350

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

    # FRED series to include - ALL 150 SERIES FROM DATABASE
    # NO FILTERING - include everything we have
    FRED_MACRO_SERIES: List[str] = field(
        default_factory=lambda: [
            "ANFCI", "APU000074714", "B235RC1Q027SBEA", "BAMLC0A0CM", "BAMLH0A0HYM2",
            "BOGMBASE", "BOPGSTB", "BUSLOANS", "CCSA", "CHNCPIALLMINMEI",
            "CHNGDPNQDSMEI", "CHNMAINLANDTPU", "CHNPRINTO01IXPYM", "CLVMNACSCAB1GQEA19",
            "CPIAUCSL", "CPILFESL", "DCOILBRENTEU", "DCOILWTICO", "DDFUELUSGULF",
            "DEXARS", "DEXBZUS", "DEXCAUS", "DEXCHUS", "DEXHKUS", "DEXINUS",
            "DEXJPUS", "DEXKOUS", "DEXMAUS", "DEXMXUS", "DEXNOUS", "DEXSFUS",
            "DEXSIUS", "DEXSZUS", "DEXTAUS", "DEXTHUS", "DEXUSAL", "DEXUSEU",
            "DEXUSUK", "DFEDTARL", "DFEDTARU", "DFF", "DFII10", "DFII20",
            "DFII30", "DFII5", "DFII7", "DGASUSGULF", "DGS1", "DGS10", "DGS1MO",
            "DGS2", "DGS20", "DGS30", "DGS3MO", "DGS5", "DGS6MO", "DGS7",
            "DHHNGSP", "DHOILNYH", "DJFUELUSGULF", "DPRIME", "DPROPANEMBTX",
            "DRCCLACBS", "DTWEXAFEGS", "DTWEXBGS", "DTWEXEMEGS", "DXY",
            "EMVTRADEPOLEMV", "EPUTRADE", "EXPCH", "EXPGS", "FEDFUNDS",
            "FRGSHPUSM649NCIS", "GASDESW", "GASREGW", "GDP", "GDPC1", "GVZCLS",
            "HOUST", "ICSA", "IMPCH", "IMPGS", "INDPRO", "IR3TIB01CNM156N",
            "LVXRNSA", "M2SL", "MANEMP", "MORTGAGE30US", "MYAGM2CNM189N",
            "NASDAQCOM", "NFCI", "NYFED_BGCR", "NYFED_EFFR", "NYFED_OBFR",
            "NYFED_SOFR", "NYFED_TGCR", "OVXCLS", "PAYEMS", "PBARLUSDM", "PCE",
            "PCEPI", "PCEPILFE", "PCOPPUSDM", "PCU311224311224", "PCU32411032411012",
            "PERMIT", "PMAIZMTUSDM", "PNGASEUUSDM", "POLVOILUSDM", "PPIACO",
            "PPIFGS", "PPIFIS", "PPOILUSDM", "PRICENPQUSDM", "PROILUSDM",
            "PSOILUSDM", "PSOYBUSDM", "PSUGAISAUSDM", "PSUNOUSDM", "PWHEAMTUSDM",
            "RRPONTSYD", "RSXFS", "SOFR", "SP500", "STLFSI", "STLFSI4",
            "T10Y2Y", "T10Y3M", "T10YIE", "T20YIEM", "T30YIEM", "T5YIE",
            "T5YIFR", "TEDRATE", "TOTRESNS", "UMCSENT", "UNRATE", "USEPUINDXD",
            "USEPUINDXM", "VIXCLS", "VXGSCLS", "VXVCLS", "WALCL", "WPU01830161",
            "WPU01830171", "WPU057303", "WPU06140341", "WRESBAL", "XTEXVA01CNM667S",
            "XTIMVA01CNM667S",
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
    Training configuration for Core models.

    REALITY: DirectTabular for ALL horizons.
    No Chronos. No GA-VMD-LSTM. Just DirectTabular.
    """

    # Validation
    num_val_windows: int = 4

    # All features are OBSERVED (not known)
    covariate_type: str = "observed"

    # Predictor settings
    eval_metric: str = "WQL"  # Weighted Quantile Loss
    presets: str = "best_quality"
    time_limit: int = 3600  # 1 hour per horizon

    # Window starts (None = use all available data)
    tactical_window_start: Optional[str] = None
    strategic_window_start: Optional[str] = None

    # THE ONLY MODEL WE USE
    models: List[str] = field(
        default_factory=lambda: ["DirectTabular"]
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
