# ZINC-FUSION-V15 Forecasting Module
"""
Forecasting module for soybean oil (ZL) price prediction.

Components:
- volatility.py: GARCH-based volatility forecasting and risk metrics
"""

from .volatility import (
    fit_garch,
    forecast_volatility,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_risk_metrics,
    GARCHResult,
    VolatilityForecast,
    RiskMetrics,
)

__all__ = [
    "fit_garch",
    "forecast_volatility",
    "calculate_sharpe_ratio",
    "calculate_sortino_ratio",
    "calculate_risk_metrics",
    "GARCHResult",
    "VolatilityForecast",
    "RiskMetrics",
]
