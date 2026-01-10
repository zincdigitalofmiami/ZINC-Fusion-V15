"""
ZINC-FUSION-V15 Pulse Feature Extractors
=========================================

Extract training features from AI-generated pulses (Intel Drops).
These are TRAINING FEATURES, not display widgets.

Each pulse generates quantitative features that feed into specialist models.
"""

import re
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class ExtractedFeatures:
    """Features extracted from a pulse for model training."""
    domain: str
    horizon: str
    as_of_ts: datetime

    # Core directional features
    direction: int  # -1, 0, 1
    pressure_cents: float
    edge: float  # 0.0 to 1.0

    # Driver weights (sum to 1.0)
    driver_weights: Dict[str, float] = field(default_factory=dict)

    # Top drivers ordered by importance
    top_drivers: List[str] = field(default_factory=list)

    # Regime classification
    regime_tags: List[str] = field(default_factory=list)

    # Quality indicators
    quality_flags: List[str] = field(default_factory=list)
    data_gaps: List[str] = field(default_factory=list)

    # Quantitative metrics from the pulse
    quant_metrics: Dict[str, float] = field(default_factory=dict)

    # Neural discoveries (AI-found signals)
    neural_signals: List[Dict[str, Any]] = field(default_factory=list)

    # Correlation data
    correlations: Dict[str, float] = field(default_factory=dict)


def extract_direction(pulse_data: Dict[str, Any], horizon: str = '1W') -> int:
    """
    Extract directional signal from pulse.

    Args:
        pulse_data: Parsed pulse JSON
        horizon: Time horizon (1W, 1M, 3M, 6M)

    Returns:
        Direction: -1 (bearish), 0 (neutral), 1 (bullish)
    """
    # Try quantitative_analysis.primary_forecast first
    quant = pulse_data.get('quantitative_analysis', {})
    forecast = quant.get('primary_forecast', {})

    horizon_key = f'horizon_{horizon.lower()}'
    if horizon_key in forecast:
        return forecast[horizon_key].get('direction', 0)

    # Fallback to top-level direction
    if 'direction' in pulse_data:
        return pulse_data['direction']

    # Try to infer from tl_dr
    tl_dr = pulse_data.get('tl_dr', '').lower()
    if any(word in tl_dr for word in ['bearish', 'negative', 'weak', 'decline']):
        return -1
    if any(word in tl_dr for word in ['bullish', 'positive', 'strong', 'rally']):
        return 1

    return 0


def extract_pressure_cents(pulse_data: Dict[str, Any], horizon: str = '1W') -> float:
    """
    Extract expected price pressure in cents.

    Args:
        pulse_data: Parsed pulse JSON
        horizon: Time horizon

    Returns:
        Pressure in cents (positive = up, negative = down)
    """
    quant = pulse_data.get('quantitative_analysis', {})
    forecast = quant.get('primary_forecast', {})

    horizon_key = f'horizon_{horizon.lower()}'
    if horizon_key in forecast:
        return forecast[horizon_key].get('pressure_cents', 0.0)

    return pulse_data.get('pressure_cents', 0.0)


def extract_edge(pulse_data: Dict[str, Any], horizon: str = '1W') -> float:
    """
    Extract confidence/edge score.

    Args:
        pulse_data: Parsed pulse JSON
        horizon: Time horizon

    Returns:
        Edge score (0.0 to 1.0)
    """
    quant = pulse_data.get('quantitative_analysis', {})
    forecast = quant.get('primary_forecast', {})

    horizon_key = f'horizon_{horizon.lower()}'
    if horizon_key in forecast:
        return forecast[horizon_key].get('edge', 0.5)

    return pulse_data.get('edge', pulse_data.get('confidence', 0.5))


def extract_driver_weights(pulse_data: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract driver attribution weights.

    Args:
        pulse_data: Parsed pulse JSON

    Returns:
        Dictionary of driver -> weight (should sum to ~1.0)
    """
    # Try driver_attribution first
    if 'driver_attribution' in pulse_data:
        weights = pulse_data['driver_attribution']
        if isinstance(weights, dict):
            return {k: float(v) for k, v in weights.items()}

    # Try drivers list format
    if 'drivers' in pulse_data:
        drivers = pulse_data['drivers']
        if isinstance(drivers, list):
            weights = {}
            for driver in drivers:
                if isinstance(driver, dict):
                    name = driver.get('name', driver.get('driver', 'unknown'))
                    weight = driver.get('weight', driver.get('importance', 0.1))
                    weights[name] = float(weight)
            return weights

    return {}


def extract_top_drivers(pulse_data: Dict[str, Any], top_n: int = 5) -> List[str]:
    """
    Extract top N drivers by importance.

    Args:
        pulse_data: Parsed pulse JSON
        top_n: Number of top drivers to return

    Returns:
        List of driver names ordered by importance
    """
    weights = extract_driver_weights(pulse_data)
    if weights:
        sorted_drivers = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        return [d[0] for d in sorted_drivers[:top_n]]

    # Fallback to explicit top_drivers field
    if 'top_drivers' in pulse_data:
        drivers = pulse_data['top_drivers']
        if isinstance(drivers, list):
            return drivers[:top_n]

    return []


def extract_regime_tags(pulse_data: Dict[str, Any]) -> List[str]:
    """
    Extract market regime classifications.

    Args:
        pulse_data: Parsed pulse JSON

    Returns:
        List of regime tags
    """
    tags = []

    # From regime_assessment
    regime = pulse_data.get('regime_assessment', {})
    if isinstance(regime, dict):
        if 'current' in regime:
            tags.append(regime['current'])
        if 'volatility_regime' in regime:
            tags.append(f"vol_{regime['volatility_regime']}")
        if 'likely_next' in regime:
            tags.append(f"next_{regime['likely_next']}")

    # From explicit regime_tags
    if 'regime_tags' in pulse_data:
        explicit_tags = pulse_data['regime_tags']
        if isinstance(explicit_tags, list):
            tags.extend(explicit_tags)

    # Deduplicate while preserving order
    seen = set()
    unique_tags = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)

    return unique_tags


def extract_neural_signals(pulse_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract AI-discovered signals (neural discoveries).

    Args:
        pulse_data: Parsed pulse JSON

    Returns:
        List of signal dictionaries with name, correlation, lead_days
    """
    quant = pulse_data.get('quantitative_analysis', {})
    discoveries = quant.get('neural_discoveries', [])

    signals = []
    for disc in discoveries:
        if isinstance(disc, dict):
            signals.append({
                'signal': disc.get('signal', disc.get('name', 'unknown')),
                'correlation': float(disc.get('correlation', 0.0)),
                'lead_days': int(disc.get('lead_days', 0))
            })

    return signals


def extract_correlations(pulse_data: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract correlation matrix data.

    Args:
        pulse_data: Parsed pulse JSON

    Returns:
        Dictionary of asset -> correlation
    """
    quant = pulse_data.get('quantitative_analysis', {})
    corr_matrix = quant.get('correlation_matrix', {})

    if isinstance(corr_matrix, dict):
        return {k: float(v) for k, v in corr_matrix.items()}

    return {}


def extract_quality_flags(pulse_data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """
    Extract quality indicators and data gaps.

    Args:
        pulse_data: Parsed pulse JSON

    Returns:
        Tuple of (quality_flags, data_gaps)
    """
    quality_flags = []
    data_gaps = []

    # Check for explicit flags
    if 'quality_flags' in pulse_data:
        quality_flags.extend(pulse_data['quality_flags'])

    if 'data_gaps' in pulse_data:
        data_gaps.extend(pulse_data['data_gaps'])

    # Infer quality from edge score
    edge = extract_edge(pulse_data)
    if edge > 0.7:
        quality_flags.append('high_confidence')
    elif edge < 0.4:
        quality_flags.append('low_confidence')

    # Check for missing data indicators in narrative
    narrative = pulse_data.get('narrative', pulse_data.get('tl_dr', ''))
    if 'data unavailable' in narrative.lower():
        quality_flags.append('partial_data')
    if 'delayed' in narrative.lower():
        quality_flags.append('stale_data')

    return quality_flags, data_gaps


def extract_quant_metrics(pulse_data: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract quantitative metrics from risk_metrics and other sources.

    Args:
        pulse_data: Parsed pulse JSON

    Returns:
        Dictionary of metric_name -> value
    """
    metrics = {}

    quant = pulse_data.get('quantitative_analysis', {})

    # Risk metrics
    risk = quant.get('risk_metrics', {})
    if isinstance(risk, dict):
        for key, value in risk.items():
            try:
                metrics[f'risk_{key}'] = float(value)
            except (ValueError, TypeError):
                pass

    # Any numeric fields at top level
    for key, value in pulse_data.items():
        if isinstance(value, (int, float)) and key not in ['direction']:
            metrics[key] = float(value)

    return metrics


def extract_all_features(
    pulse_data: Dict[str, Any],
    domain: str,
    as_of_ts: datetime
) -> Dict[str, ExtractedFeatures]:
    """
    Extract features for all horizons from a pulse.

    Args:
        pulse_data: Parsed pulse JSON
        domain: Specialist domain
        as_of_ts: Timestamp of the pulse

    Returns:
        Dictionary of horizon -> ExtractedFeatures
    """
    horizons = ['1W', '1M', '3M', '6M']
    results = {}

    # Extract common features once
    driver_weights = extract_driver_weights(pulse_data)
    top_drivers = extract_top_drivers(pulse_data)
    regime_tags = extract_regime_tags(pulse_data)
    quality_flags, data_gaps = extract_quality_flags(pulse_data)
    neural_signals = extract_neural_signals(pulse_data)
    correlations = extract_correlations(pulse_data)
    quant_metrics = extract_quant_metrics(pulse_data)

    for horizon in horizons:
        results[horizon] = ExtractedFeatures(
            domain=domain,
            horizon=horizon,
            as_of_ts=as_of_ts,
            direction=extract_direction(pulse_data, horizon),
            pressure_cents=extract_pressure_cents(pulse_data, horizon),
            edge=extract_edge(pulse_data, horizon),
            driver_weights=driver_weights,
            top_drivers=top_drivers,
            regime_tags=regime_tags,
            quality_flags=quality_flags,
            data_gaps=data_gaps,
            quant_metrics=quant_metrics,
            neural_signals=neural_signals,
            correlations=correlations
        )

    return results


def features_to_training_row(features: ExtractedFeatures) -> Dict[str, Any]:
    """
    Convert extracted features to a flat dictionary for training.

    Args:
        features: ExtractedFeatures instance

    Returns:
        Flat dictionary suitable for DataFrame/training
    """
    row = {
        'domain': features.domain,
        'horizon': features.horizon,
        'as_of_ts': features.as_of_ts.isoformat(),
        'direction': features.direction,
        'pressure_cents': features.pressure_cents,
        'edge': features.edge,
        'regime_primary': features.regime_tags[0] if features.regime_tags else None,
        'num_quality_flags': len(features.quality_flags),
        'num_data_gaps': len(features.data_gaps),
        'has_high_confidence': 'high_confidence' in features.quality_flags,
        'num_neural_signals': len(features.neural_signals),
    }

    # Add driver weights as individual columns
    for driver, weight in features.driver_weights.items():
        row[f'driver_{driver}'] = weight

    # Add top 3 drivers
    for i, driver in enumerate(features.top_drivers[:3]):
        row[f'top_driver_{i+1}'] = driver

    # Add correlations
    for asset, corr in features.correlations.items():
        row[f'corr_{asset}'] = corr

    # Add quant metrics
    for metric, value in features.quant_metrics.items():
        row[f'metric_{metric}'] = value

    # Add top neural signal
    if features.neural_signals:
        top_signal = features.neural_signals[0]
        row['top_neural_signal'] = top_signal.get('signal')
        row['top_neural_corr'] = top_signal.get('correlation')
        row['top_neural_lead'] = top_signal.get('lead_days')

    return row


def parse_narrative_sentiment(narrative: str) -> Dict[str, Any]:
    """
    Parse sentiment indicators from narrative text.

    Args:
        narrative: Pulse narrative text

    Returns:
        Sentiment analysis results
    """
    narrative_lower = narrative.lower()

    # Bullish indicators
    bullish_words = ['bullish', 'rally', 'surge', 'strong', 'positive', 'upside',
                     'support', 'breakout', 'momentum', 'buying']
    bullish_count = sum(1 for word in bullish_words if word in narrative_lower)

    # Bearish indicators
    bearish_words = ['bearish', 'decline', 'weak', 'negative', 'downside',
                     'resistance', 'breakdown', 'selling', 'pressure', 'concern']
    bearish_count = sum(1 for word in bearish_words if word in narrative_lower)

    # Uncertainty indicators
    uncertain_words = ['uncertain', 'unclear', 'mixed', 'volatile', 'risk',
                       'cautious', 'wait', 'pending', 'depends']
    uncertain_count = sum(1 for word in uncertain_words if word in narrative_lower)

    # Calculate net sentiment
    net_sentiment = bullish_count - bearish_count
    if bullish_count + bearish_count > 0:
        sentiment_ratio = net_sentiment / (bullish_count + bearish_count)
    else:
        sentiment_ratio = 0.0

    return {
        'bullish_count': bullish_count,
        'bearish_count': bearish_count,
        'uncertain_count': uncertain_count,
        'net_sentiment': net_sentiment,
        'sentiment_ratio': sentiment_ratio,
        'word_count': len(narrative.split())
    }
