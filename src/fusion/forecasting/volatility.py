#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Volatility Forecasting Module

Provides GARCH-based volatility forecasting and risk-adjusted return metrics.

Components:
1. GARCH(1,1) - Standard volatility clustering model
2. GJR-GARCH - Asymmetric volatility (leverage effect)
3. EGARCH - Exponential GARCH for fat tails
4. Sharpe Ratio - Risk-adjusted returns
5. Sortino Ratio - Downside risk-adjusted returns

Usage:
    from src.fusion.forecasting.volatility import (
        fit_garch,
        forecast_volatility,
        calculate_sharpe_ratio,
        calculate_sortino_ratio,
    )

    # Fit GARCH model
    model = fit_garch(returns, model_type='gjr-garch')

    # Forecast volatility
    vol_forecast = forecast_volatility(model, horizon=21)

    # Calculate risk metrics
    sharpe = calculate_sharpe_ratio(returns, risk_free_rate=0.05)
    sortino = calculate_sortino_ratio(returns, risk_free_rate=0.05)
"""

import logging
from typing import Dict, Optional, Tuple, Union
from dataclasses import dataclass

import numpy as np
import pandas as pd
from arch import arch_model

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class GARCHResult:
    """Results from GARCH model fitting."""

    model_type: str
    omega: float  # Constant in variance equation
    alpha: float  # ARCH term (yesterday's shock)
    beta: float  # GARCH term (yesterday's variance)
    gamma: Optional[float]  # Asymmetry term (GJR-GARCH only)
    persistence: float  # alpha + beta (should be < 1)
    unconditional_vol: float  # Long-run volatility (annualized)
    aic: float
    bic: float
    log_likelihood: float
    fitted_model: object  # The fitted arch model


@dataclass
class VolatilityForecast:
    """Volatility forecast results."""

    horizon: int
    daily_vol: np.ndarray  # Daily volatility path
    annualized_vol: np.ndarray  # Annualized volatility path
    mean_vol: float  # Average daily vol over horizon
    terminal_vol: float  # Vol at end of horizon
    vol_of_vol: float  # Volatility of volatility (uncertainty)


@dataclass
class RiskMetrics:
    """Risk-adjusted return metrics."""

    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: Optional[float]  # If max drawdown available
    information_ratio: Optional[float]  # If benchmark available
    annualized_return: float
    annualized_vol: float
    max_drawdown: Optional[float]
    var_95: float  # 95% Value at Risk
    cvar_95: float  # 95% Conditional VaR (Expected Shortfall)


# =============================================================================
# GARCH MODEL FITTING
# =============================================================================


def fit_garch(
    returns: Union[pd.Series, np.ndarray],
    model_type: str = "gjr-garch",
    p: int = 1,
    q: int = 1,
    dist: str = "t",  # Student-t for fat tails
    rescale: bool = True,
) -> GARCHResult:
    """
    Fit a GARCH model to return series.

    Args:
        returns: Return series (daily returns, not prices)
        model_type: 'garch', 'gjr-garch', or 'egarch'
        p: GARCH lag order
        q: ARCH lag order
        dist: Error distribution ('normal', 't', 'skewt')
        rescale: Rescale returns for numerical stability

    Returns:
        GARCHResult with fitted model and parameters
    """
    # Convert to array and handle NaN
    if isinstance(returns, pd.Series):
        returns = returns.dropna().values
    returns = np.asarray(returns)
    returns = returns[~np.isnan(returns)]

    if len(returns) < 100:
        logger.warning(f"Only {len(returns)} observations - GARCH may be unstable")

    # Scale returns to percentage (arch library expects ~1-10 scale)
    if rescale:
        scale_factor = 100
        returns_scaled = returns * scale_factor
    else:
        scale_factor = 1
        returns_scaled = returns

    # Build model based on type
    if model_type.lower() == "garch":
        model = arch_model(
            returns_scaled, mean="Constant", vol="GARCH", p=p, q=q, dist=dist
        )
    elif model_type.lower() == "gjr-garch":
        model = arch_model(
            returns_scaled,
            mean="Constant",
            vol="GARCH",
            p=p,
            o=1,
            q=q,  # o=1 adds asymmetric term
            dist=dist,
        )
    elif model_type.lower() == "egarch":
        model = arch_model(
            returns_scaled, mean="Constant", vol="EGARCH", p=p, q=q, dist=dist
        )
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

    # Fit model
    try:
        res = model.fit(disp="off", show_warning=False)
    except Exception as e:
        logger.error(f"GARCH fitting failed: {e}")
        raise

    # Extract parameters
    params = res.params
    omega = params.get("omega", 0) / (scale_factor**2)  # Rescale back

    if model_type.lower() == "egarch":
        alpha = params.get("alpha[1]", 0)
        beta = params.get("beta[1]", 0)
        gamma = params.get("gamma[1]", None)
        persistence = np.abs(beta)  # EGARCH persistence
    else:
        alpha = params.get("alpha[1]", 0)
        beta = params.get("beta[1]", 0)
        gamma = params.get("gamma[1]", None) if "gamma[1]" in params else None
        persistence = alpha + beta + (gamma / 2 if gamma else 0)

    # Unconditional (long-run) variance
    if persistence < 1:
        unconditional_var = omega / (1 - persistence)
        unconditional_vol = np.sqrt(unconditional_var * 252)  # Annualized
    else:
        unconditional_vol = np.nan
        logger.warning(f"GARCH persistence >= 1 ({persistence:.3f}), non-stationary")

    return GARCHResult(
        model_type=model_type,
        omega=omega,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        persistence=persistence,
        unconditional_vol=unconditional_vol,
        aic=res.aic,
        bic=res.bic,
        log_likelihood=res.loglikelihood,
        fitted_model=res,
    )


def forecast_volatility(
    garch_result: GARCHResult,
    horizon: int = 21,
    method: str = "analytic",
) -> VolatilityForecast:
    """
    Forecast volatility using fitted GARCH model.

    Args:
        garch_result: Fitted GARCH model result
        horizon: Forecast horizon in days
        method: 'analytic' or 'simulation'

    Returns:
        VolatilityForecast with volatility path
    """
    res = garch_result.fitted_model

    # Generate forecasts
    forecasts = res.forecast(horizon=horizon, method=method)

    # Extract variance forecasts and convert to volatility
    variance_forecast = forecasts.variance.iloc[-1].values
    daily_vol = np.sqrt(variance_forecast) / 100  # Rescale from percentage

    # Annualize
    annualized_vol = daily_vol * np.sqrt(252)

    # Statistics
    mean_vol = np.mean(daily_vol)
    terminal_vol = daily_vol[-1]
    vol_of_vol = np.std(daily_vol)

    return VolatilityForecast(
        horizon=horizon,
        daily_vol=daily_vol,
        annualized_vol=annualized_vol,
        mean_vol=mean_vol,
        terminal_vol=terminal_vol,
        vol_of_vol=vol_of_vol,
    )


# =============================================================================
# RISK-ADJUSTED RETURN METRICS
# =============================================================================


def calculate_sharpe_ratio(
    returns: Union[pd.Series, np.ndarray],
    risk_free_rate: float = 0.05,
    periods_per_year: int = 252,
) -> float:
    """
    Calculate annualized Sharpe Ratio.

    Sharpe = (Mean Return - Risk Free Rate) / Volatility

    Args:
        returns: Daily returns (not cumulative)
        risk_free_rate: Annual risk-free rate (default 5%)
        periods_per_year: Trading days per year

    Returns:
        Annualized Sharpe Ratio
    """
    if isinstance(returns, pd.Series):
        returns = returns.dropna().values
    returns = np.asarray(returns)
    returns = returns[~np.isnan(returns)]

    if len(returns) < 2:
        return np.nan

    # Daily metrics
    daily_rf = risk_free_rate / periods_per_year
    excess_returns = returns - daily_rf

    mean_excess = np.mean(excess_returns)
    std_returns = np.std(returns, ddof=1)

    if std_returns == 0:
        return np.nan

    # Annualize
    sharpe = (mean_excess / std_returns) * np.sqrt(periods_per_year)

    return sharpe


def calculate_sortino_ratio(
    returns: Union[pd.Series, np.ndarray],
    risk_free_rate: float = 0.05,
    periods_per_year: int = 252,
    target_return: Optional[float] = None,
) -> float:
    """
    Calculate annualized Sortino Ratio (downside risk-adjusted).

    Sortino = (Mean Return - Target) / Downside Deviation

    Unlike Sharpe, Sortino only penalizes downside volatility,
    making it more appropriate for asymmetric return distributions.

    Args:
        returns: Daily returns
        risk_free_rate: Annual risk-free rate
        periods_per_year: Trading days per year
        target_return: Target return (default: risk-free rate)

    Returns:
        Annualized Sortino Ratio
    """
    if isinstance(returns, pd.Series):
        returns = returns.dropna().values
    returns = np.asarray(returns)
    returns = returns[~np.isnan(returns)]

    if len(returns) < 2:
        return np.nan

    # Daily target
    if target_return is None:
        daily_target = risk_free_rate / periods_per_year
    else:
        daily_target = target_return / periods_per_year

    excess_returns = returns - daily_target

    # Downside deviation (only negative excess returns)
    downside_returns = excess_returns[excess_returns < 0]
    if len(downside_returns) == 0:
        return np.inf  # No downside - perfect

    downside_std = np.sqrt(np.mean(downside_returns**2))

    if downside_std == 0:
        return np.nan

    mean_excess = np.mean(excess_returns)

    # Annualize
    sortino = (mean_excess / downside_std) * np.sqrt(periods_per_year)

    return sortino


def calculate_risk_metrics(
    returns: Union[pd.Series, np.ndarray],
    risk_free_rate: float = 0.05,
    periods_per_year: int = 252,
    benchmark_returns: Optional[np.ndarray] = None,
) -> RiskMetrics:
    """
    Calculate comprehensive risk metrics.

    Args:
        returns: Daily returns
        risk_free_rate: Annual risk-free rate
        periods_per_year: Trading days per year
        benchmark_returns: Optional benchmark for Information Ratio

    Returns:
        RiskMetrics dataclass with all metrics
    """
    if isinstance(returns, pd.Series):
        returns = returns.dropna().values
    returns = np.asarray(returns)
    returns = returns[~np.isnan(returns)]

    if len(returns) < 2:
        return RiskMetrics(
            sharpe_ratio=np.nan,
            sortino_ratio=np.nan,
            calmar_ratio=None,
            information_ratio=None,
            annualized_return=np.nan,
            annualized_vol=np.nan,
            max_drawdown=None,
            var_95=np.nan,
            cvar_95=np.nan,
        )

    # Sharpe and Sortino
    sharpe = calculate_sharpe_ratio(returns, risk_free_rate, periods_per_year)
    sortino = calculate_sortino_ratio(returns, risk_free_rate, periods_per_year)

    # Annualized return and vol
    annualized_return = np.mean(returns) * periods_per_year
    annualized_vol = np.std(returns, ddof=1) * np.sqrt(periods_per_year)

    # Max drawdown
    cumulative = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - running_max) / running_max
    max_drawdown = np.min(drawdowns)

    # Calmar ratio (return / max drawdown)
    if max_drawdown != 0:
        calmar = annualized_return / abs(max_drawdown)
    else:
        calmar = None

    # Information ratio (if benchmark provided)
    if benchmark_returns is not None:
        tracking_error = np.std(returns - benchmark_returns) * np.sqrt(periods_per_year)
        excess_return = (
            annualized_return - np.mean(benchmark_returns) * periods_per_year
        )
        information_ratio = (
            excess_return / tracking_error if tracking_error > 0 else None
        )
    else:
        information_ratio = None

    # VaR and CVaR (95%)
    var_95 = np.percentile(returns, 5)  # 5th percentile = 95% VaR
    cvar_95 = np.mean(returns[returns <= var_95])  # Expected shortfall

    return RiskMetrics(
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        information_ratio=information_ratio,
        annualized_return=annualized_return,
        annualized_vol=annualized_vol,
        max_drawdown=max_drawdown,
        var_95=var_95,
        cvar_95=cvar_95,
    )


# =============================================================================
# INTEGRATION WITH MONTE CARLO
# =============================================================================


def garch_volatility_for_monte_carlo(
    returns: Union[pd.Series, np.ndarray],
    horizon: int,
    model_type: str = "gjr-garch",
) -> Tuple[np.ndarray, float, float]:
    """
    Get GARCH volatility forecast for Monte Carlo simulation.

    This replaces the simple asymmetric diffusion with GARCH-based forecasts.

    Args:
        returns: Historical daily returns
        horizon: Forecast horizon in days
        model_type: GARCH variant to use

    Returns:
        Tuple of:
        - daily_vol: Array of daily volatility forecasts
        - upside_vol_mult: Multiplier for upside moves (from asymmetry)
        - downside_vol_mult: Multiplier for downside moves
    """
    # Fit GARCH
    result = fit_garch(returns, model_type=model_type)

    # Log parameters
    logger.info(f"GARCH({result.model_type}) fitted:")
    logger.info(f"  Persistence: {result.persistence:.4f}")
    logger.info(f"  Unconditional Vol: {result.unconditional_vol:.2%}")
    if result.gamma:
        logger.info(f"  Asymmetry (gamma): {result.gamma:.4f}")

    # Forecast
    forecast = forecast_volatility(result, horizon=horizon)

    # Calculate asymmetry multipliers from GJR-GARCH gamma
    if result.gamma and result.gamma > 0:
        # Gamma > 0 means downside shocks have bigger impact
        downside_vol_mult = 1.0 + result.gamma / 2
        upside_vol_mult = 1.0
    else:
        upside_vol_mult = 1.0
        downside_vol_mult = 1.0

    return forecast.daily_vol, upside_vol_mult, downside_vol_mult


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def quick_garch_summary(returns: pd.Series) -> Dict:
    """
    Quick GARCH analysis for a return series.

    Returns dict suitable for JSON storage or logging.
    """
    result = fit_garch(returns, model_type="gjr-garch")
    metrics = calculate_risk_metrics(returns)

    return {
        "garch_type": result.model_type,
        "persistence": round(result.persistence, 4),
        "unconditional_vol": round(result.unconditional_vol, 4),
        "alpha": round(result.alpha, 4),
        "beta": round(result.beta, 4),
        "gamma": round(result.gamma, 4) if result.gamma else None,
        "aic": round(result.aic, 2),
        "sharpe_ratio": round(metrics.sharpe_ratio, 3),
        "sortino_ratio": round(metrics.sortino_ratio, 3),
        "annualized_vol": round(metrics.annualized_vol, 4),
        "max_drawdown": round(metrics.max_drawdown, 4)
        if metrics.max_drawdown
        else None,
        "var_95": round(metrics.var_95, 4),
        "cvar_95": round(metrics.cvar_95, 4),
    }
