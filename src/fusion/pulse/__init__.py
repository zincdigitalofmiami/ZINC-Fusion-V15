# ZINC-FUSION-V15 Pulse Engine

from .engine import PulseEngine
from .schema import PulseSchema, IntelDrop, HorizonForecast
from .validators import validate_pulse, PulseValidationError

__all__ = [
    'PulseEngine',
    'PulseSchema', 
    'IntelDrop',
    'HorizonForecast',
    'validate_pulse',
    'PulseValidationError'
]

DOMAINS = [
    'CRUSH',
    'CHINA', 
    'FX',
    'FED',
    'TARIFF',
    'ENERGY',
    'BIOFUEL',
    'PALM',
    'VOLATILITY',
    'SUBSTITUTES',
    'TRUMP_EFFECT'
]

HORIZONS = ['1W', '1M', '3M', '6M']
