"""
Core Training Package - Shared Configuration
=============================================

LOCKED: 2026-01-24
Core uses AutoGluon TimeSeries with an explicit Model Zoo allowlist (CPU-only).
No presets, no time limits. Specialists are separate and unchanged.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load .env file so DB URL vars are available during local execution
load_dotenv()

# =============================================================================
# DATABASE
# =============================================================================

DATABASE_URL = (
    os.getenv("DIRECT_DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("DATABASE_URL")
)

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
            "ANFCI",
            "APU000074714",
            "B235RC1Q027SBEA",
            "BAMLC0A0CM",
            "BAMLH0A0HYM2",
            "BOGMBASE",
            "BOPGSTB",
            "BUSLOANS",
            "CCSA",
            "CHNCPIALLMINMEI",
            "CHNGDPNQDSMEI",
            "CHNMAINLANDTPU",
            "CLVMNACSCAB1GQEA19",  # CHNPRINTO01IXPYM removed 2026-01-31 (discontinued)
            "CPIAUCSL",
            "CPILFESL",
            "DCOILBRENTEU",
            "DCOILWTICO",
            "DDFUELUSGULF",
            "DEXARS",
            "DEXBZUS",
            "DEXCAUS",
            "DEXCHUS",
            "DEXHKUS",
            "DEXINUS",
            "DEXJPUS",
            "DEXKOUS",
            "DEXMAUS",
            "DEXMXUS",
            "DEXNOUS",
            "DEXSFUS",
            "DEXSIUS",
            "DEXSZUS",
            "DEXTAUS",
            "DEXTHUS",
            "DEXUSAL",
            "DEXUSEU",
            "DEXUSUK",
            "DFEDTARL",
            "DFEDTARU",
            "DFF",
            "DFII10",
            "DFII20",
            "DFII30",
            "DFII5",
            "DFII7",
            "DGASUSGULF",
            "DGS1",
            "DGS10",
            "DGS1MO",
            "DGS2",
            "DGS20",
            "DGS30",
            "DGS3MO",
            "DGS5",
            "DGS6MO",
            "DGS7",
            "DHHNGSP",
            "DHOILNYH",
            "DJFUELUSGULF",
            "DPRIME",
            "DPROPANEMBTX",
            "DRCCLACBS",
            "DTWEXAFEGS",
            "DTWEXBGS",
            "DTWEXEMEGS",
            "DXY",
            "EMVTRADEPOLEMV",
            "EPUTRADE",
            "EXPCH",
            "EXPGS",
            "FEDFUNDS",
            "FRGSHPUSM649NCIS",
            "GASDESW",
            "GASREGW",
            "GDP",
            "GDPC1",
            "GVZCLS",
            "HOUST",
            "ICSA",
            "IMPCH",
            "IMPGS",
            "INDPRO",
            "IR3TIB01CNM156N",
            "LVXRNSA",
            "M2SL",
            "MANEMP",
            "MORTGAGE30US",
            "MYAGM2CNM189N",
            "NASDAQCOM",
            "NFCI",
            "NYFED_BGCR",
            "NYFED_EFFR",
            "NYFED_OBFR",
            "NYFED_SOFR",
            "NYFED_TGCR",
            "OVXCLS",
            "PAYEMS",
            "PBARLUSDM",
            "PCE",
            "PCEPI",
            "PCEPILFE",
            "PCOPPUSDM",
            "PCU311224311224",
            "PCU32411032411012",
            "PERMIT",
            "PMAIZMTUSDM",
            "PNGASEUUSDM",
            "POLVOILUSDM",
            "PPIACO",
            "PPIFGS",
            "PPIFIS",
            "PPOILUSDM",
            "PRICENPQUSDM",
            "PROILUSDM",
            "PSOILUSDM",
            "PSOYBUSDM",
            "PSUGAISAUSDM",
            "PSUNOUSDM",
            "PWHEAMTUSDM",
            "RRPONTSYD",
            "RSXFS",
            "SOFR",
            "SP500",
            "STLFSI",
            "STLFSI4",
            "T10Y2Y",
            "T10Y3M",
            "T10YIE",
            "T20YIEM",
            "T30YIEM",
            "T5YIE",
            "T5YIFR",
            "TEDRATE",
            "TOTRESNS",
            "UMCSENT",
            "UNRATE",
            "USEPUINDXD",
            "USEPUINDXM",
            "VIXCLS",
            "VXGSCLS",
            "VXVCLS",
            "WALCL",
            "WPU01830161",
            "WPU01830171",
            "WPU057303",
            "WPU06140341",
            "WRESBAL",
            "XTEXVA01CNM667S",
            "XTIMVA01CNM667S",
            # NEW (2026-02-03): Shipping, livestock, VIX term structure
            "BDIY",  # Baltic Dry Index (shipping costs)
            "CATTLENFNCM",  # Cattle on Feed (ZM demand proxy)
            "HOGSANDPIGSNONCM",  # Hogs and Pigs Inventory (ZM demand proxy)
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
    ("run_id", "UUID NOT NULL", "Training run UUID"),
]

# Column names only (for validation)
OOF_COLUMN_NAMES = [col[0] for col in OOF_COLUMNS]

# L1 Interface Contract
L1_CONTRACT = {
    # Core OOF: 4 horizons × 3 quantiles
    "core_columns": 12,
    # Specialist signals (table-level contract; signal columns vary by bucket)
    "specialist_signals_table": "training.specialist_signals_1d",
    "specialist_signal_columns": ["signal_1", "signal_2", "confidence"],
    "specialists": 11,
    "loss": "quantile_pinball",
}

# =============================================================================
# TRAINING CONFIGURATION (PHASE 6)
# =============================================================================


@dataclass
class TrainingConfig:
    """
    Training configuration for Core models.

    UPDATED 2026-01-24: Core uses an explicit AutoGluon Model Zoo allowlist (CPU-only).
    No presets. No time limits.
    """

    # Validation
    num_val_windows: int = 4

    # All features are OBSERVED (not known)
    covariate_type: str = "observed"

    # Predictor settings
    eval_metric: str = "WQL"  # Weighted Quantile Loss
    presets: Optional[str] = None  # Not used (explicit model allowlist)
    time_limit: Optional[int] = None  # Not used (no time limits)

    # Window starts (None = use all available data)
    tactical_window_start: Optional[str] = None
    strategic_window_start: Optional[str] = None


TRAINING_CONFIG = TrainingConfig()

# =============================================================================
# FROZEN MODEL ZOO — single source of truth for allowed models
# =============================================================================
# LOCKED: 2026-02-18
# Only models in this set will be trained. Any model NOT listed here is rejected.
# To add/remove a model, update this set and re-run training.
#
# 2026-02-18: Removed 7 deep learning models (DeepAR, TFT, PatchTST, TiDE,
# WaveNet, DLinear, SimpleFeedForward) — unstable on macOS ARM.
# Restore when training moves to Linux/server.
#
# 2026-02-18: Re-enabled AutoCES (statistical, CPU-safe — was incorrectly
# grouped with deep learning). Added Chronos2 (foundation model, zero-shot
# with native covariate support, inference-only — no training loop).

MODEL_ZOO_FROZEN: frozenset[str] = frozenset(
    {
        # Baselines (5)
        "Naive",
        "SeasonalNaive",
        "Average",
        "SeasonalAverage",
        "Zero",
        # Statistical (10)
        "ETS",
        "AutoETS",
        "AutoARIMA",
        "AutoCES",  # Complex exponential smoothing — CPU-safe
        "Theta",
        "DynamicOptimizedTheta",
        "NPTS",
        "ADIDA",
        "Croston",
        "IMAPA",
        # Tabular TS (3)
        "DirectTabular",
        "PerStepTabular",
        "RecursiveTabular",
        # Foundation / Pretrained (1)
        "Chronos2",  # 120M-param zero-shot, native covariate support
    }
)

# Deep learning models — disabled on macOS ARM, restore on Linux/server
MODEL_ZOO_DEEP_LEARNING: frozenset[str] = frozenset(
    {
        "DeepAR",
        "DLinear",
        "PatchTST",
        "SimpleFeedForward",
        "TemporalFusionTransformer",
        "TiDE",
        "WaveNet",
    }
)

# Pretrained models not yet active (enable after Chronos2 proves stable)
MODEL_ZOO_PRETRAINED: frozenset[str] = frozenset(
    {
        "Chronos",  # Original Chronos (no covariate support)
        "Toto",  # Databricks foundation model
    }
)

# Expected model count: 19 active + WeightedEnsemble = 20 per horizon
MODEL_ZOO_ACTIVE_COUNT = len(MODEL_ZOO_FROZEN)  # 19

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
        raise EnvironmentError(
            "Database URL not set (DIRECT_DATABASE_URL/POSTGRES_URL/DATABASE_URL)"
        )

    # Ensure model dirs exist
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    SCALERS_DIR.mkdir(parents=True, exist_ok=True)

    return True
