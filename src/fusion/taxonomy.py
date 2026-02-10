"""
CBI-V15 Crystal Ball Taxonomy
========================
Canonical constants for the 15-driver system (10 economic + 5 neural).
This is the single source of truth for driver IDs, schemas, and naming rules.

LOCKED — DO NOT MODIFY WITHOUT EXPLICIT APPROVAL.
"""

from typing import Literal

# =============================================================================
# DRIVER TAXONOMY (16 TOTAL: 11 Economic + 5 Neural)
# =============================================================================

# Economic Drivers (11)
ECONOMIC_DRIVERS: tuple[str, ...] = (
    "crush",
    "china",
    "fx",
    "fed",
    "tariff",
    "energy",
    "biofuel",
    "palm",
    "volatility",
    "substitutes",
    "trump_effect",
)

# Specialist alias (for backward compatibility with Big-8/10 naming)
SPECIALISTS: tuple[str, ...] = ECONOMIC_DRIVERS

# Neural Drivers (5)
NEURAL_DRIVERS: tuple[str, ...] = (
    "neural_trend",
    "neural_regime",
    "neural_flow",
    "neural_sentiment",
    "neural_residual",
)

# All Drivers (16)
ALL_DRIVERS: tuple[str, ...] = ECONOMIC_DRIVERS + NEURAL_DRIVERS

# Type hints
EconomicDriverId = Literal[
    "crush",
    "china",
    "fx",
    "fed",
    "tariff",
    "energy",
    "biofuel",
    "palm",
    "volatility",
    "substitutes",
    "trump_effect",
]
NeuralDriverId = Literal[
    "neural_trend",
    "neural_regime",
    "neural_flow",
    "neural_sentiment",
    "neural_residual",
]
DriverId = Literal[
    "crush",
    "china",
    "fx",
    "fed",
    "tariff",
    "energy",
    "biofuel",
    "palm",
    "volatility",
    "substitutes",
    "trump_effect",
    "neural_trend",
    "neural_regime",
    "neural_flow",
    "neural_sentiment",
    "neural_residual",
]

# =============================================================================
# SCHEMA TAXONOMY (13 SCHEMAS - Institutional Architecture)
# =============================================================================

# Landing schemas: append-only source data
LANDING_SCHEMAS: tuple[str, ...] = ("mkt", "econ", "alt", "pos", "supply")

# Derived schemas: computed from landing
DERIVED_SCHEMAS: tuple[str, ...] = ("features", "training")

# Output schemas: model artifacts and predictions
OUTPUT_SCHEMAS: tuple[str, ...] = ("model", "forecasts", "analytics")

# Governance schemas: operations and metadata
GOVERNANCE_SCHEMAS: tuple[str, ...] = ("metadata", "ops")

# All schemas (canonical list)
SCHEMAS: tuple[str, ...] = (
    LANDING_SCHEMAS + DERIVED_SCHEMAS + OUTPUT_SCHEMAS + GOVERNANCE_SCHEMAS
)

# BANNED schemas - fail hard if detected in new code
BANNED_SCHEMAS: tuple[str, ...] = (
    "raw",
    "gold",
    "silver",
    "bronze",
    "monitoring",
    "specialist",
    "weather",
)

SchemaName = Literal[
    "mkt",
    "econ",
    "alt",
    "pos",
    "supply",  # Landing
    "features",
    "training",  # Derived
    "model",
    "forecasts",
    "analytics",  # Output
    "metadata",
    "ops",  # Governance
]

# =============================================================================
# TIME GRANULARITY
# =============================================================================

TIME_GRAINS: tuple[str, ...] = ("1h", "1d", "1w")

TimeGrain = Literal["1h", "1d", "1w"]

# =============================================================================
# DRIVER METADATA
# =============================================================================

DRIVER_DESCRIPTIONS: dict[str, str] = {
    # Economic
    "crush": "Soybean crush margins and processing economics",
    "china": "China import demand, trade flow behavior",
    "fx": "Foreign exchange impacts on global oil pricing",
    "fed": "Rates, liquidity, and monetary policy transmission",
    "tariff": "Tariffs, trade policy, and regulatory friction",
    "energy": "Crude, diesel, and energy complex spillover",
    "biofuel": "RFS, SAF, biodiesel incentives and demand",
    "palm": "Palm oil supply, pricing, and substitution effects",
    "volatility": "Market stress, convexity, regime shifts",
    "substitutes": "Cross-oil substitution (canola, UCO, etc.)",
    "trump_effect": "Trump/policy regime dynamics, trade war, EPA waivers, tweet volatility",
    # Neural
    "neural_trend": "Learned price trend and momentum structure",
    "neural_regime": "Latent market regime classification",
    "neural_flow": "Learned flow/pressure from multi-asset inputs",
    "neural_sentiment": "Neural aggregation of news + narrative tone",
    "neural_residual": "Unexplained residual pressure after economics",
}

DRIVER_TYPES: dict[str, str] = {
    **{d: "economic" for d in ECONOMIC_DRIVERS},
    **{d: "neural" for d in NEURAL_DRIVERS},
}

# =============================================================================
# NAMING RULES (ENFORCED)
# =============================================================================

# Banned patterns in table names
BANNED_PATTERNS: tuple[str, ...] = (
    "_v1",
    "_v2",
    "_v3",
    "_v4",
    "_new",
    "_legacy",
    "_latest",
    "_old",
    "ohlcv",
    "ohlc",
)

# Valid table suffixes
VALID_SUFFIXES: tuple[str, ...] = ("_1h", "_1d", "_1w")


def validate_table_name(table_name: str) -> bool:
    """Check if table name follows canonical naming rules."""
    lower_name = table_name.lower()
    for banned in BANNED_PATTERNS:
        if banned in lower_name:
            return False
    return True


def validate_driver_id(driver_id: str) -> bool:
    """Check if driver_id is in canonical list."""
    return driver_id in ALL_DRIVERS


# =============================================================================
# HORIZONS (AutoGluon ML Standards)
# =============================================================================

FORECAST_HORIZONS: tuple[str, ...] = ("1W", "1M", "3M", "6M")

HorizonId = Literal["1W", "1M", "3M", "6M"]

# Horizon steps (trading days)
HORIZON_STEPS: dict[str, int] = {
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
}

# Target column naming convention (AutoGluon standard)
TARGET_COLUMNS: dict[int, str] = {
    5: "target_return_5d",
    21: "target_return_21d",
    63: "target_return_63d",
    126: "target_return_126d",
}

# Quantile regression standards
QUANTILE_LEVELS: tuple[float, ...] = (0.1, 0.5, 0.9)
QUANTILE_COLUMNS: tuple[str, ...] = ("p10", "p50", "p90")

# =============================================================================
# SYMBOLS
# =============================================================================

PRIMARY_SYMBOL: str = "ZL"  # Soybean Oil

RELATED_SYMBOLS: tuple[str, ...] = (
    "ZS",  # Soybeans
    "ZM",  # Soymeal
    "ZC",  # Corn
    "CL",  # Crude Oil
    "HO",  # Heating Oil
    "CPO",  # Crude Palm Oil
)

# =============================================================================
# NEURAL → DRIVER OWNERSHIP MAP (EXPLAINABILITY WIRING)
# =============================================================================
# This defines which neural signals can contribute to which economic drivers.
# Without this, explanations drift and become "black box".
#
# Rules:
# - Each neural driver MUST map to at least one economic driver
# - Neural drivers cannot contribute to unmapped economic drivers
# - contribution_cap limits maximum attribution (0.0-1.0)
# - SHAP aggregation uses this for deterministic roll-up
#
# LOCKED — Changes require explicit approval and audit trail.

NEURAL_DRIVER_OWNERSHIP: dict[str, list[tuple[str, float, str]]] = {
    # neural_driver_id: [(economic_driver_id, contribution_cap, rationale), ...]
    "neural_trend": [
        ("crush", 0.3, "Trend captures crush margin momentum"),
        ("energy", 0.3, "Trend correlates with energy complex direction"),
        ("volatility", 0.4, "Trend changes signal volatility regime"),
    ],
    "neural_regime": [
        ("volatility", 0.5, "Regime directly models market stress states"),
        ("fed", 0.3, "Regime captures rate environment shifts"),
        ("china", 0.2, "Regime reflects demand cycle phases"),
    ],
    "neural_flow": [
        ("crush", 0.4, "Flow captures processor hedging pressure"),
        ("china", 0.3, "Flow reflects trade flow momentum"),
        ("substitutes", 0.3, "Flow shows cross-oil arbitrage pressure"),
    ],
    "neural_sentiment": [
        ("tariff", 0.4, "Sentiment captures policy narrative tone"),
        ("china", 0.3, "Sentiment reflects China trade headlines"),
        ("biofuel", 0.3, "Sentiment tracks RFS/SAF policy buzz"),
    ],
    "neural_residual": [
        # Residual is the "unexplained" bucket — distributes across all
        ("crush", 0.15, "Residual unexplained crush pressure"),
        ("china", 0.15, "Residual unexplained China signal"),
        ("fx", 0.10, "Residual FX noise"),
        ("fed", 0.10, "Residual macro noise"),
        ("tariff", 0.10, "Residual policy noise"),
        ("energy", 0.10, "Residual energy spillover"),
        ("biofuel", 0.10, "Residual biofuel signal"),
        ("palm", 0.10, "Residual palm substitution"),
        ("volatility", 0.05, "Residual vol signal"),
        ("substitutes", 0.05, "Residual cross-oil noise"),
    ],
}


# Validate ownership map sums (contribution caps per neural driver should sum to ~1.0)
def validate_ownership_map() -> dict[str, float]:
    """Validate that each neural driver's contribution caps sum to approximately 1.0."""
    results = {}
    for neural_id, mappings in NEURAL_DRIVER_OWNERSHIP.items():
        total = sum(cap for _, cap, _ in mappings)
        results[neural_id] = total
    return results


def get_allowed_economic_drivers(neural_driver_id: str) -> list[str]:
    """Get list of economic drivers a neural signal can contribute to."""
    if neural_driver_id not in NEURAL_DRIVER_OWNERSHIP:
        return []
    return [econ_id for econ_id, _, _ in NEURAL_DRIVER_OWNERSHIP[neural_driver_id]]


# =============================================================================
# VALIDATION
# =============================================================================


def validate_config_compliance() -> dict[str, bool]:
    """
    Validate that all configurations meet overfitting control requirements.

    Returns:
        Dict of check_name -> passed
    """
    checks = {}

    # Specialist config checks (import from autogluon_config at call time)
    from fusion.autogluon_config import SPECIALIST_CONFIG, DRIFT_THRESHOLDS  # noqa: F401

    cfg = SPECIALIST_CONFIG
    checks["specialist_bag_folds_sufficient"] = cfg.num_bag_folds >= 5
    checks["specialist_stack_levels_limited"] = cfg.num_stack_levels <= 1
    checks["specialist_no_holdout_leakage"] = cfg.holdout_frac is None
    checks["specialist_auto_stack_enabled"] = cfg.auto_stack is True

    # Drift threshold checks
    dt = DRIFT_THRESHOLDS
    checks["drift_psi_hierarchy_valid"] = dt.psi_mild < dt.psi_moderate < dt.psi_severe
    checks["drift_coverage_hierarchy_valid"] = (
        dt.coverage_deviation_mild < dt.coverage_deviation_severe
    )

    return checks


def get_contribution_cap(neural_driver_id: str, economic_driver_id: str) -> float:
    """Get the contribution cap for a neural→economic mapping. Returns 0 if not allowed."""
    if neural_driver_id not in NEURAL_DRIVER_OWNERSHIP:
        return 0.0
    for econ_id, cap, _ in NEURAL_DRIVER_OWNERSHIP[neural_driver_id]:
        if econ_id == economic_driver_id:
            return cap
    return 0.0


# =============================================================================
# AUTOGLUON CONFIG CROSS-REFERENCE
# =============================================================================
# See src/fusion/autogluon_config.py for:
# - SpecialistConfig: Mandatory TabularPredictor settings
# - CoreTimeSeriesConfig: TimeSeriesPredictor settings
# - DriftThresholds: Drift detection and action triggers
# - ArtifactContract: Model registry requirements
#
# Import pattern:
#   from fusion.autogluon_config import (
#       get_specialist_fit_kwargs,
#       diagnose_drift,
#       SPECIALIST_CONFIG,
#       DRIFT_THRESHOLDS,
#   )
