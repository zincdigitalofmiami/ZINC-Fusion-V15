"""
ZINC-FUSION-V15 Pulse Compute Utilities
========================================

Quant computation utilities for generating pulse metrics.
AI is the operator - Python computes.

This module provides:
- Linear regression for trend analysis
- Correlation calculations
- Quant payload generation from external sources
"""

import math
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime


def linear_regression(x: List[float], y: List[float]) -> Tuple[float, float]:
    """
    Simple linear regression returning slope and intercept.

    Args:
        x: Independent variable values
        y: Dependent variable values

    Returns:
        Tuple of (slope, intercept)

    Example:
        >>> slope, intercept = linear_regression([1,2,3,4,5], [2.1, 4.0, 5.9, 8.1, 9.8])
        >>> round(slope, 2)
        1.94
    """
    if len(x) != len(y) or len(x) < 2:
        return (0.0, 0.0)

    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi ** 2 for xi in x)

    denominator = n * sum_x2 - sum_x ** 2
    if abs(denominator) < 1e-10:
        return (0.0, sum_y / n if n > 0 else 0.0)

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n

    return (slope, intercept)


def correlation(a: List[float], b: List[float]) -> Optional[float]:
    """
    Pearson correlation coefficient between two series.

    Args:
        a: First series
        b: Second series

    Returns:
        Correlation coefficient between -1 and 1, or None if insufficient data

    Example:
        >>> corr = correlation([1,2,3,4,5], [2,4,5,4,5])
        >>> round(corr, 2)
        0.82
    """
    if len(a) != len(b) or len(a) < 2:
        return None

    n = len(a)
    mean_a = sum(a) / n
    mean_b = sum(b) / n

    numerator = sum((ai - mean_a) * (bi - mean_b) for ai, bi in zip(a, b))

    var_a = sum((ai - mean_a) ** 2 for ai in a)
    var_b = sum((bi - mean_b) ** 2 for bi in b)

    denominator = math.sqrt(var_a * var_b)
    if abs(denominator) < 1e-10:
        return None

    return numerator / denominator


def zscore(value: float, mean: float, std: float) -> float:
    """
    Calculate z-score for a value.

    Args:
        value: The observation
        mean: Population/sample mean
        std: Population/sample standard deviation

    Returns:
        Z-score (standard deviations from mean)
    """
    if abs(std) < 1e-10:
        return 0.0
    return (value - mean) / std


def percentile_rank(value: float, series: List[float]) -> float:
    """
    Calculate percentile rank of a value within a series.

    Args:
        value: The value to rank
        series: Historical series to compare against

    Returns:
        Percentile rank (0-100)
    """
    if not series:
        return 50.0

    below = sum(1 for v in series if v < value)
    equal = sum(1 for v in series if v == value)

    return 100.0 * (below + 0.5 * equal) / len(series)


def rolling_mean(series: List[float], window: int) -> List[float]:
    """
    Calculate rolling mean with specified window.

    Args:
        series: Input data
        window: Window size

    Returns:
        Rolling mean values (first window-1 values are partial)
    """
    if not series or window < 1:
        return []

    result = []
    for i in range(len(series)):
        start = max(0, i - window + 1)
        window_data = series[start:i + 1]
        result.append(sum(window_data) / len(window_data))

    return result


def rolling_std(series: List[float], window: int) -> List[float]:
    """
    Calculate rolling standard deviation with specified window.

    Args:
        series: Input data
        window: Window size

    Returns:
        Rolling std values
    """
    if not series or window < 2:
        return [0.0] * len(series)

    result = []
    for i in range(len(series)):
        start = max(0, i - window + 1)
        window_data = series[start:i + 1]
        if len(window_data) < 2:
            result.append(0.0)
            continue

        mean = sum(window_data) / len(window_data)
        variance = sum((x - mean) ** 2 for x in window_data) / (len(window_data) - 1)
        result.append(math.sqrt(variance))

    return result


def compute_momentum(series: List[float], period: int = 14) -> float:
    """
    Calculate momentum (rate of change) over period.

    Args:
        series: Price/value series
        period: Lookback period

    Returns:
        Momentum as percentage change
    """
    if len(series) < period + 1:
        return 0.0

    current = series[-1]
    past = series[-(period + 1)]

    if abs(past) < 1e-10:
        return 0.0

    return 100.0 * (current - past) / past


def compute_volatility(returns: List[float], annualize: bool = True) -> float:
    """
    Calculate volatility (standard deviation of returns).

    Args:
        returns: Daily/periodic returns
        annualize: Whether to annualize (assumes daily data, 252 trading days)

    Returns:
        Volatility (annualized if specified)
    """
    if len(returns) < 2:
        return 0.0

    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)

    if annualize:
        std *= math.sqrt(252)

    return std


def compute_quant_payload(external_sources: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate quantitative payload from external source data.

    This is the main function that converts raw fetched data into
    computed metrics for the Intel Drop.

    Args:
        external_sources: Dictionary of fetched source data

    Returns:
        Quant payload with computed metrics

    Example:
        >>> sources = {
        ...     'fred_rates': {'DGS10': [4.2, 4.3, 4.25, 4.28, 4.30]},
        ...     'eia_crude': {'wti': [75.5, 76.0, 75.8, 76.2, 77.0]}
        ... }
        >>> payload = compute_quant_payload(sources)
        >>> 'metrics' in payload
        True
    """
    payload = {
        'computed_at': datetime.utcnow().isoformat(),
        'metrics': {},
        'correlations': {},
        'trends': {},
        'signals': []
    }

    # Extract key series if available
    series_data = {}

    # FRED rates
    if 'fred_rates' in external_sources:
        for series_id, values in external_sources['fred_rates'].items():
            if isinstance(values, list) and values:
                series_data[series_id] = values

                # Compute metrics for each series
                if len(values) >= 5:
                    payload['metrics'][series_id] = {
                        'current': values[-1] if values else None,
                        'change_5d': values[-1] - values[-5] if len(values) >= 5 else None,
                        'momentum_14d': compute_momentum(values, 14) if len(values) >= 15 else None,
                        'zscore_20d': zscore(values[-1], sum(values[-20:]) / min(len(values), 20),
                                            compute_volatility(values[-20:], False)) if len(values) >= 20 else None
                    }

    # EIA crude data
    if 'eia_crude' in external_sources:
        for series_id, values in external_sources['eia_crude'].items():
            if isinstance(values, list) and values:
                series_data[f'eia_{series_id}'] = values
                payload['metrics'][f'eia_{series_id}'] = {
                    'current': values[-1],
                    'volatility_20d': compute_volatility(
                        [(values[i] - values[i-1]) / values[i-1] if values[i-1] != 0 else 0
                         for i in range(1, min(21, len(values)))]
                    ) if len(values) >= 2 else None
                }

    # Compute cross-series correlations
    series_names = list(series_data.keys())
    for i, name1 in enumerate(series_names):
        for name2 in series_names[i+1:]:
            s1, s2 = series_data[name1], series_data[name2]
            min_len = min(len(s1), len(s2))
            if min_len >= 10:
                corr = correlation(s1[-min_len:], s2[-min_len:])
                if corr is not None:
                    payload['correlations'][f'{name1}_vs_{name2}'] = round(corr, 3)

    # Compute trends
    for name, values in series_data.items():
        if len(values) >= 20:
            x = list(range(len(values[-20:])))
            slope, _ = linear_regression(x, values[-20:])
            payload['trends'][name] = {
                'slope_20d': round(slope, 4),
                'direction': 'up' if slope > 0 else 'down' if slope < 0 else 'flat'
            }

    # Generate signals based on thresholds
    for name, metrics in payload['metrics'].items():
        zscore_val = metrics.get('zscore_20d')
        if zscore_val is not None:
            if abs(zscore_val) > 2.0:
                payload['signals'].append({
                    'series': name,
                    'signal_type': 'extreme_zscore',
                    'value': round(zscore_val, 2),
                    'direction': 'high' if zscore_val > 0 else 'low'
                })

    return payload


def compute_driver_weights(
    domain: str,
    signal_snapshot: Dict[str, Any],
    recent_changes: Dict[str, float]
) -> Dict[str, float]:
    """
    Compute driver weights for a domain based on current signals.

    This estimates which factors are most influential right now.

    Args:
        domain: Specialist domain
        signal_snapshot: Current signal values
        recent_changes: Recent % changes in key metrics

    Returns:
        Dictionary of driver -> weight (should sum to 1.0)
    """
    # Base weights by domain (from historical analysis)
    base_weights = {
        'CRUSH': {
            'crush_margin': 0.25,
            'supply': 0.20,
            'demand': 0.20,
            'spreads': 0.15,
            'basis': 0.10,
            'technical': 0.10
        },
        'CHINA': {
            'import_demand': 0.30,
            'port_stocks': 0.20,
            'fx_usd_cny': 0.15,
            'policy': 0.15,
            'margins': 0.10,
            'technical': 0.10
        },
        'ENERGY': {
            'crude_price': 0.35,
            'refinery_margins': 0.20,
            'inventories': 0.15,
            'demand': 0.15,
            'geopolitics': 0.10,
            'technical': 0.05
        },
        'BIOFUEL': {
            'rin_prices': 0.30,
            'rd_margins': 0.25,
            'policy': 0.20,
            'feedstock': 0.15,
            'capacity': 0.10
        },
        'FED': {
            'rates': 0.35,
            'inflation': 0.25,
            'employment': 0.15,
            'yield_curve': 0.15,
            'speeches': 0.10
        }
    }

    weights = base_weights.get(domain, {
        'fundamental': 0.40,
        'technical': 0.30,
        'sentiment': 0.20,
        'positioning': 0.10
    })

    # Adjust weights based on recent volatility in each driver
    # Higher volatility = higher weight (more influential right now)
    if recent_changes:
        total_abs_change = sum(abs(v) for v in recent_changes.values())
        if total_abs_change > 0:
            for driver, change in recent_changes.items():
                if driver in weights:
                    # Increase weight proportional to recent movement
                    volatility_boost = abs(change) / total_abs_change * 0.2
                    weights[driver] = weights.get(driver, 0) + volatility_boost

    # Normalize to sum to 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}

    return weights
