"""
ZINC Fusion V15: Specialist Signal Generators (v3 Architecture)
================================================================

This module implements the compact signal architecture where each specialist
emits 1-2 values per date that become Core model input features.

Architecture Shift:
- v2: 44 specialist models (11 buckets × 4 horizons) producing forecasts
- v3: 11 signal generators producing compact signals fed to Core

Signal Contract:
- Each specialist outputs signal_1 (primary) and signal_2 (secondary)
- Signals are horizon-agnostic; Core owns all horizon forecasting
- No decision semantics (no buy/sell outputs)
- Signals stored in training.specialist_signals_1d

Specialist Buckets (Big-11):
- crush: Margin z-score + momentum (GradientBoosting)
- china: Demand outlook score (GPR/GBM)
- fx: FX pressure index (ARDL/GBM)
- fed: Rates regime + change (Ridge/ARDL)
- tariff: Tariff risk score (Tree/Rules)
- energy: Energy spillover score (VAR/GBM)
- biofuel: Policy pressure score (NLP+EMA)
- palm: Substitution pressure (ECM)
- volatility: Regime level + change (GARCH)
- substitutes: Substitution pressure (RandomForest)
- trump_effect: Intensity + uncertainty (Event study)
"""

from fusion.specialists.base import (
    BaseSignalGenerator,
    SignalConfig,
    SignalOutput,
    SPECIALIST_BUCKETS,
    MODEL_TYPES,
)

# Group A: GBM/RF-based
from fusion.specialists.xgb_signals import (
    CrushSignalGenerator,
    SubstitutesSignalGenerator,
    ChinaSignalGenerator,
)

# Group A: GARCH-based
from fusion.specialists.garch_signals import VolatilitySignalGenerator

# Group B: Econometric models
from fusion.specialists.ardl_signals import FxSignalGenerator, FedSignalGenerator
from fusion.specialists.var_signals import EnergySignalGenerator
from fusion.specialists.ecm_signals import PalmSignalGenerator

# Group C: Event-based
from fusion.specialists.event_signals import (
    TariffSignalGenerator,
    BiofuelSignalGenerator,
    TrumpEffectSignalGenerator,
)


# Registry mapping bucket names to generator classes
SIGNAL_GENERATORS = {
    "crush": CrushSignalGenerator,
    "china": ChinaSignalGenerator,
    "fx": FxSignalGenerator,
    "fed": FedSignalGenerator,
    "tariff": TariffSignalGenerator,
    "energy": EnergySignalGenerator,
    "biofuel": BiofuelSignalGenerator,
    "palm": PalmSignalGenerator,
    "volatility": VolatilitySignalGenerator,
    "substitutes": SubstitutesSignalGenerator,
    "trump_effect": TrumpEffectSignalGenerator,
}


def get_generator(bucket: str) -> BaseSignalGenerator:
    """Factory function to get signal generator for a bucket."""
    if bucket not in SIGNAL_GENERATORS:
        raise ValueError(
            f"Unknown bucket: {bucket}. Valid: {list(SIGNAL_GENERATORS.keys())}"
        )
    return SIGNAL_GENERATORS[bucket]()


__all__ = [
    # Base classes
    "BaseSignalGenerator",
    "SignalConfig",
    "SignalOutput",
    "SPECIALIST_BUCKETS",
    "MODEL_TYPES",
    # Generator classes
    "CrushSignalGenerator",
    "ChinaSignalGenerator",
    "FxSignalGenerator",
    "FedSignalGenerator",
    "TariffSignalGenerator",
    "EnergySignalGenerator",
    "BiofuelSignalGenerator",
    "PalmSignalGenerator",
    "VolatilitySignalGenerator",
    "SubstitutesSignalGenerator",
    "TrumpEffectSignalGenerator",
    # Registry
    "SIGNAL_GENERATORS",
    "get_generator",
]
