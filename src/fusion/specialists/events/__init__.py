"""Event-driven specialist generators split by domain."""

from .biofuel import BiofuelSignalGenerator
from .tariff import TariffSignalGenerator
from .trump_effect import TrumpEffectSignalGenerator

__all__ = [
    "BiofuelSignalGenerator",
    "TariffSignalGenerator",
    "TrumpEffectSignalGenerator",
]
