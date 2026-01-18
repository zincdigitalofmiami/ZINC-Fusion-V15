# ZINC-FUSION-V15 Forecasting Module
"""
Forecasting module for soybean oil (ZL) price prediction.

Components:
- volatility.py: GARCH-based volatility forecasting
- ga_vmd_lstm.py: GA-VMD-LSTM for strategic horizons (Nature 2025 paper)

Strategic (63d/126d): GA-VMD-LSTM
- 67.5% MAPE reduction vs standalone LSTM on soybean oil
- VMD decomposes into K=12 IMFs (GA-optimized)
- Each IMF gets LSTM with frequency-appropriate lookback
- Reference: https://www.nature.com/articles/s41598-025-94173-0

Tactical (5d/21d): AutoGluon Chronos-Bolt ensemble
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

# GA-VMD-LSTM (strategic horizons)
try:
    from .ga_vmd_lstm import (
        GAVMDLSTMForecaster,
        GAVMDLSTMConfig,
        GAVMDLSTMWrapper,
        CONFIG_63D,
        CONFIG_126D,
        quick_forecast,
    )
    GA_VMD_LSTM_AVAILABLE = True
except ImportError as e:
    GA_VMD_LSTM_AVAILABLE = False
    import logging
    logging.getLogger(__name__).warning(f"GA-VMD-LSTM unavailable: {e}")

__all__ = [
    # Volatility
    "fit_garch",
    "forecast_volatility",
    "calculate_sharpe_ratio",
    "calculate_sortino_ratio",
    "calculate_risk_metrics",
    "GARCHResult",
    "VolatilityForecast",
    "RiskMetrics",
    # GA-VMD-LSTM
    "GAVMDLSTMForecaster",
    "GAVMDLSTMConfig",
    "GAVMDLSTMWrapper",
    "CONFIG_63D",
    "CONFIG_126D",
    "quick_forecast",
    "GA_VMD_LSTM_AVAILABLE",
]
