"""
ZINC-FUSION-V15: Domain-Specific Pressure Calculators

Each pressure has its own calculator module with real domain expertise,
not generic percentile-based scoring.

KEY MARKET DRIVERS (Dashboard Cards):
- VIX Stress (volatility_pressure.py)
- Crush Pressure (crush_pressure.py)
- China Tension (china_tension.py)
- Tariff Threat (policy_pressure.py)
"""

from .crush_pressure import calculate_crush_pressure
from .volatility_pressure import calculate_volatility_pressure
from .greed_pressure import calculate_greed_pressure
from .policy_pressure import calculate_trump_effect_pressure, calculate_tariff_pressure
from .trade_pressure import calculate_trade_pressure, calculate_correlation_pressure
from .news_pressure import calculate_news_pressure, calculate_geopolitical_pressure
from .china_tension import calculate_china_tension

__all__ = [
    # Key Market Drivers
    "calculate_volatility_pressure",  # VIX Stress
    "calculate_crush_pressure",  # Crush Pressure
    "calculate_china_tension",  # China Tension
    "calculate_tariff_pressure",  # Tariff Threat
    # Other Pressures
    "calculate_greed_pressure",
    "calculate_trump_effect_pressure",
    "calculate_trade_pressure",
    "calculate_correlation_pressure",
    "calculate_news_pressure",
    "calculate_geopolitical_pressure",
]
