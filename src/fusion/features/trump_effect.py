#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Trump Effect Specialist Feature Engineering

Provides feature engineering, risk calculations, and probability proxies
for the Trump Effect specialist bucket.

Components:
1. Event Intensity Scoring - shock_severity, uncertainty_score, novelty_score
2. Probability Proxies - DJT/FXI/KWEB derived metrics, rolling correlations
3. EPU Regime Detection - Policy uncertainty regime classification
4. GARCH Volatility - Trump-regime adjusted volatility forecasting
5. Risk Metrics - Sharpe, Sortino, VaR, CVaR with regime conditioning

Data Sources:
- FRED: USEPUINDXD, EPUTRADE, EMVTRADEPOLEMV, CHNMAINLANDTPU, IMPCH, B235RC1Q027SBEA
- Yahoo: DJT, FXI, KWEB (probability proxies)
- URL Events: White House, Federal Register, Truth Social

Usage:
    from src.fusion.features.trump_effect import (
        TrumpEffectFeatureEngine,
        calculate_event_intensity,
        calculate_probability_proxies,
        detect_epu_regime,
    )

    engine = TrumpEffectFeatureEngine(fred_df, yahoo_df)
    features = engine.compute_all_features()
"""

import logging
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy import stats

# Import existing volatility infrastructure
from src.fusion.forecasting.volatility import (
    fit_garch,
    forecast_volatility,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_risk_metrics,
    GARCHResult,
    RiskMetrics as BaseRiskMetrics,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class EventIntensity:
    """Event intensity scores for a single event or aggregated period."""
    shock_severity: float       # 0-1 scale, magnitude of market impact
    uncertainty_score: float    # 0-1 scale, conditional language/ambiguity
    novelty_score: float        # 0-1 scale, new vs repeated announcement
    event_count: int            # Number of events in period
    topic_distribution: Dict[str, int]  # Count by topic code


@dataclass
class ProbabilityProxies:
    """Market-implied probability proxies from Yahoo tickers."""
    djt_ret_1d: float           # DJT 1-day return
    djt_ret_5d: float           # DJT 5-day return
    djt_rv_21d: float           # DJT 21-day realized volatility
    fxi_ret_1d: float           # FXI 1-day return
    kweb_ret_1d: float          # KWEB 1-day return
    djt_minus_fxi_ret_1d: float # Relative return (idiosyncratic proxy)
    corr_djt_fxi_63d: float     # 63-day rolling correlation
    corr_djt_kweb_63d: float    # 63-day rolling correlation
    regime_decoupling: bool     # True if correlations break down


@dataclass
class EPURegime:
    """Economic Policy Uncertainty regime classification."""
    regime: str                 # low, normal, elevated, high, extreme
    epu_level: float            # Current EPU index level
    epu_zscore: float           # Z-score vs historical
    epu_percentile: float       # Percentile rank (0-1)
    trade_epu_level: float      # Trade-specific EPU
    china_tpu_level: float      # China trade policy uncertainty
    regime_change_prob: float   # Probability of regime change


@dataclass
class TrumpEffectRiskMetrics:
    """Trump Effect specific risk metrics."""
    sharpe_ratio: float
    sortino_ratio: float
    var_95: float               # 95% Value at Risk
    cvar_95: float              # 95% Conditional VaR
    max_drawdown: float
    regime_adjusted_vol: float  # Volatility adjusted for EPU regime
    tail_risk_flag: bool        # Extreme downside risk indicator
    event_sensitivity: float    # Portfolio sensitivity to Trump events


# =============================================================================
# CONSTANTS
# =============================================================================

# EPU regime thresholds (calibrated to historical distribution)
EPU_REGIME_THRESHOLDS = {
    'low': 75,
    'normal': 125,
    'elevated': 175,
    'high': 250,
    # 'extreme' is anything above 250
}

# Topic codes for event classification
TOPIC_CODES = [
    'TARIFF_CHINA',
    'TARIFF_OTHER',
    'RFS_RVO',
    'EPA_WAIVER',
    'TAX',
    'SANCTIONS',
    'EXPORT_CONTROLS',
    'TRADE_DEAL',
    'EXECUTIVE_ACTION',
    'TWEET_THREAT',
]

# Regime volatility multipliers
REGIME_VOL_MULTIPLIERS = {
    'low': 0.7,
    'normal': 1.0,
    'elevated': 1.25,
    'high': 1.5,
    'extreme': 2.0,
}


# =============================================================================
# EVENT INTENSITY SCORING
# =============================================================================

def calculate_shock_severity(
    text: str,
    topic_code: str,
    historical_events: Optional[pd.DataFrame] = None,
) -> float:
    """
    Calculate shock severity score (0-1) for an event.

    Rule-based scoring considering:
    - Topic type (tariffs > tweets > statements)
    - Magnitude keywords (billion, percent, immediate)
    - Target scope (China, global, sector-specific)
    - Action type (announcement vs implementation vs threat)

    Args:
        text: Event text/headline
        topic_code: Classified topic code
        historical_events: Historical events for calibration

    Returns:
        Shock severity score 0-1
    """
    score = 0.5  # Base score

    text_lower = text.lower() if text else ""

    # Topic-based base adjustments
    topic_weights = {
        'TARIFF_CHINA': 0.15,
        'TARIFF_OTHER': 0.10,
        'SANCTIONS': 0.12,
        'EXPORT_CONTROLS': 0.10,
        'EXECUTIVE_ACTION': 0.08,
        'RFS_RVO': 0.08,
        'EPA_WAIVER': 0.06,
        'TAX': 0.05,
        'TRADE_DEAL': -0.05,  # Positive news reduces shock
        'TWEET_THREAT': 0.03,
    }
    score += topic_weights.get(topic_code, 0)

    # Magnitude keywords
    magnitude_keywords = {
        'billion': 0.08,
        'trillion': 0.15,
        '25%': 0.06,
        '50%': 0.10,
        '100%': 0.15,
        'immediate': 0.05,
        'effective immediately': 0.08,
        'all imports': 0.10,
        'total ban': 0.12,
        'suspend': 0.08,
        'terminate': 0.10,
        'withdraw': 0.08,
    }
    for keyword, weight in magnitude_keywords.items():
        if keyword in text_lower:
            score += weight

    # Scope keywords
    scope_keywords = {
        'china': 0.05,
        'global': 0.08,
        'all countries': 0.10,
        'eu': 0.04,
        'mexico': 0.04,
        'canada': 0.03,
    }
    for keyword, weight in scope_keywords.items():
        if keyword in text_lower:
            score += weight

    # Mitigation keywords (reduce severity)
    mitigation_keywords = {
        'considering': -0.05,
        'may': -0.03,
        'could': -0.03,
        'delay': -0.05,
        'postpone': -0.05,
        'negotiating': -0.04,
        'progress': -0.04,
    }
    for keyword, weight in mitigation_keywords.items():
        if keyword in text_lower:
            score += weight

    # Clamp to 0-1
    return max(0.0, min(1.0, score))


def calculate_uncertainty_score(
    text: str,
    doc_type: str,
) -> float:
    """
    Calculate uncertainty score (0-1) for an event.

    Higher score = more ambiguity/conditional language.

    Args:
        text: Event text/headline
        doc_type: Document type (executive_action, statement, tweet, etc.)

    Returns:
        Uncertainty score 0-1
    """
    score = 0.5  # Base score

    text_lower = text.lower() if text else ""

    # Document type base scores
    doc_type_scores = {
        'executive_action': 0.2,       # Low uncertainty - action taken
        'executive_order': 0.2,
        'trade_action': 0.25,
        'fact_sheet': 0.3,
        'statement': 0.4,
        'remarks': 0.45,
        'tweet': 0.6,                  # High uncertainty - could be bluster
        'notice': 0.3,
    }
    score = doc_type_scores.get(doc_type, 0.5)

    # Uncertainty-increasing keywords
    uncertain_keywords = {
        'considering': 0.08,
        'may': 0.06,
        'might': 0.06,
        'could': 0.06,
        'should': 0.04,
        'looking at': 0.05,
        'reviewing': 0.05,
        'evaluating': 0.05,
        'if': 0.03,
        'unless': 0.04,
        'depending': 0.05,
    }
    for keyword, weight in uncertain_keywords.items():
        if keyword in text_lower:
            score += weight

    # Certainty-increasing keywords
    certain_keywords = {
        'will': -0.05,
        'shall': -0.06,
        'must': -0.05,
        'hereby': -0.08,
        'effective': -0.05,
        'signed': -0.06,
        'enacted': -0.08,
        'implemented': -0.06,
    }
    for keyword, weight in certain_keywords.items():
        if keyword in text_lower:
            score += weight

    return max(0.0, min(1.0, score))


def calculate_novelty_score(
    topic_code: str,
    event_date: datetime,
    historical_events: pd.DataFrame,
    lookback_days: int = 90,
) -> float:
    """
    Calculate novelty score (0-1) for an event.

    Lower score = repeated topic, higher score = novel announcement.

    Args:
        topic_code: Event topic classification
        event_date: Date of the event
        historical_events: DataFrame with past events
        lookback_days: Days to look back for similar events

    Returns:
        Novelty score 0-1
    """
    if historical_events is None or len(historical_events) == 0:
        return 0.8  # Assume novel if no history

    # Filter to lookback window
    cutoff = event_date - timedelta(days=lookback_days)
    recent = historical_events[
        (historical_events['event_date'] >= cutoff) &
        (historical_events['event_date'] < event_date)
    ]

    if len(recent) == 0:
        return 0.9  # Very novel - nothing recent

    # Count same-topic events in lookback
    same_topic = recent[recent['topic_code'] == topic_code]
    topic_count = len(same_topic)

    # Novelty decreases with repetition
    if topic_count == 0:
        return 0.9
    elif topic_count == 1:
        return 0.7
    elif topic_count <= 3:
        return 0.5
    elif topic_count <= 5:
        return 0.3
    else:
        return 0.1  # Very repeated


def calculate_event_intensity(
    events_df: pd.DataFrame,
    as_of_date: datetime,
    window_days: int = 1,
) -> EventIntensity:
    """
    Calculate aggregated event intensity for a date/window.

    Args:
        events_df: DataFrame with columns:
            - event_date, topic_code, doc_type, text, shock_severity,
              uncertainty_score, novelty_score
        as_of_date: Reference date
        window_days: Aggregation window

    Returns:
        EventIntensity dataclass
    """
    # Filter to window
    start_date = as_of_date - timedelta(days=window_days - 1)
    window_events = events_df[
        (events_df['event_date'] >= start_date) &
        (events_df['event_date'] <= as_of_date)
    ]

    if len(window_events) == 0:
        return EventIntensity(
            shock_severity=0.0,
            uncertainty_score=0.0,
            novelty_score=0.0,
            event_count=0,
            topic_distribution={},
        )

    # Aggregate scores (weighted average by shock severity)
    weights = window_events['shock_severity'].values
    if weights.sum() > 0:
        shock_avg = weights.mean()
        uncertainty_avg = np.average(
            window_events['uncertainty_score'].values,
            weights=weights
        )
        novelty_avg = np.average(
            window_events['novelty_score'].values,
            weights=weights
        )
    else:
        shock_avg = 0.0
        uncertainty_avg = 0.0
        novelty_avg = 0.0

    # Topic distribution
    topic_dist = window_events['topic_code'].value_counts().to_dict()

    return EventIntensity(
        shock_severity=shock_avg,
        uncertainty_score=uncertainty_avg,
        novelty_score=novelty_avg,
        event_count=len(window_events),
        topic_distribution=topic_dist,
    )


# =============================================================================
# PROBABILITY PROXIES (Yahoo-derived)
# =============================================================================

def calculate_probability_proxies(
    yahoo_df: pd.DataFrame,
    as_of_date: datetime,
) -> ProbabilityProxies:
    """
    Calculate market-implied probability proxies from Yahoo tickers.

    Required columns in yahoo_df:
        - as_of_date, ticker, close, adj_close

    Expected tickers: DJT, FXI, KWEB

    Args:
        yahoo_df: Yahoo price data
        as_of_date: Reference date

    Returns:
        ProbabilityProxies dataclass
    """
    # Pivot to wide format
    pivot = yahoo_df.pivot(index='as_of_date', columns='ticker', values='adj_close')
    pivot = pivot.sort_index()

    # Filter to as_of_date
    if as_of_date not in pivot.index:
        # Find closest prior date
        prior_dates = pivot.index[pivot.index <= as_of_date]
        if len(prior_dates) == 0:
            return _empty_probability_proxies()
        as_of_date = prior_dates[-1]

    # Calculate returns
    returns = pivot.pct_change()

    # Get values for as_of_date
    idx = pivot.index.get_loc(as_of_date)

    # 1-day returns
    djt_ret_1d = returns['DJT'].iloc[idx] if 'DJT' in returns.columns else 0.0
    fxi_ret_1d = returns['FXI'].iloc[idx] if 'FXI' in returns.columns else 0.0
    kweb_ret_1d = returns['KWEB'].iloc[idx] if 'KWEB' in returns.columns else 0.0

    # 5-day returns
    djt_ret_5d = (
        (pivot['DJT'].iloc[idx] / pivot['DJT'].iloc[max(0, idx-5)] - 1)
        if 'DJT' in pivot.columns and idx >= 5 else 0.0
    )

    # 21-day realized volatility (DJT)
    if 'DJT' in returns.columns and idx >= 21:
        djt_rv_21d = returns['DJT'].iloc[max(0, idx-20):idx+1].std() * np.sqrt(252)
    else:
        djt_rv_21d = 0.0

    # Relative return (DJT - FXI)
    djt_minus_fxi_ret_1d = djt_ret_1d - fxi_ret_1d

    # Rolling correlations (63-day)
    if 'DJT' in returns.columns and 'FXI' in returns.columns and idx >= 63:
        window_returns = returns.iloc[max(0, idx-62):idx+1]
        corr_djt_fxi_63d = window_returns['DJT'].corr(window_returns['FXI'])
    else:
        corr_djt_fxi_63d = 0.0

    if 'DJT' in returns.columns and 'KWEB' in returns.columns and idx >= 63:
        window_returns = returns.iloc[max(0, idx-62):idx+1]
        corr_djt_kweb_63d = window_returns['DJT'].corr(window_returns['KWEB'])
    else:
        corr_djt_kweb_63d = 0.0

    # Regime decoupling detection
    # Flag if correlation drops below 0.3 (historically ~0.5-0.7)
    regime_decoupling = abs(corr_djt_fxi_63d) < 0.3

    return ProbabilityProxies(
        djt_ret_1d=float(djt_ret_1d) if not np.isnan(djt_ret_1d) else 0.0,
        djt_ret_5d=float(djt_ret_5d) if not np.isnan(djt_ret_5d) else 0.0,
        djt_rv_21d=float(djt_rv_21d) if not np.isnan(djt_rv_21d) else 0.0,
        fxi_ret_1d=float(fxi_ret_1d) if not np.isnan(fxi_ret_1d) else 0.0,
        kweb_ret_1d=float(kweb_ret_1d) if not np.isnan(kweb_ret_1d) else 0.0,
        djt_minus_fxi_ret_1d=float(djt_minus_fxi_ret_1d) if not np.isnan(djt_minus_fxi_ret_1d) else 0.0,
        corr_djt_fxi_63d=float(corr_djt_fxi_63d) if not np.isnan(corr_djt_fxi_63d) else 0.0,
        corr_djt_kweb_63d=float(corr_djt_kweb_63d) if not np.isnan(corr_djt_kweb_63d) else 0.0,
        regime_decoupling=regime_decoupling,
    )


def _empty_probability_proxies() -> ProbabilityProxies:
    """Return empty probability proxies."""
    return ProbabilityProxies(
        djt_ret_1d=0.0,
        djt_ret_5d=0.0,
        djt_rv_21d=0.0,
        fxi_ret_1d=0.0,
        kweb_ret_1d=0.0,
        djt_minus_fxi_ret_1d=0.0,
        corr_djt_fxi_63d=0.0,
        corr_djt_kweb_63d=0.0,
        regime_decoupling=False,
    )


# =============================================================================
# EPU REGIME DETECTION
# =============================================================================

def detect_epu_regime(
    fred_df: pd.DataFrame,
    as_of_date: datetime,
    lookback_days: int = 252,
) -> EPURegime:
    """
    Detect EPU regime from FRED series.

    Required series in fred_df:
        - USEPUINDXD (daily) or USEPUINDXM (monthly)
        - EPUTRADE (monthly)
        - CHNMAINLANDTPU (monthly)

    Args:
        fred_df: FRED observations (long format: as_of_date, series_id, value)
        as_of_date: Reference date
        lookback_days: Days for z-score calculation

    Returns:
        EPURegime dataclass
    """
    # Filter to as_of_date
    cutoff = as_of_date - timedelta(days=lookback_days)
    recent = fred_df[fred_df['as_of_date'] <= as_of_date]

    # Get latest EPU level
    epu_daily = recent[recent['series_id'] == 'USEPUINDXD']
    epu_monthly = recent[recent['series_id'] == 'USEPUINDXM']

    if len(epu_daily) > 0:
        epu_level = float(epu_daily.iloc[-1]['value'])
        epu_series = epu_daily[epu_daily['as_of_date'] >= cutoff]['value']
    elif len(epu_monthly) > 0:
        epu_level = float(epu_monthly.iloc[-1]['value'])
        epu_series = epu_monthly[epu_monthly['as_of_date'] >= cutoff]['value']
    else:
        return _empty_epu_regime()

    # Z-score
    if len(epu_series) >= 20:
        epu_zscore = (epu_level - epu_series.mean()) / epu_series.std()
        epu_percentile = stats.percentileofscore(epu_series, epu_level) / 100
    else:
        epu_zscore = 0.0
        epu_percentile = 0.5

    # Trade EPU
    trade_epu = recent[recent['series_id'] == 'EPUTRADE']
    trade_epu_level = float(trade_epu.iloc[-1]['value']) if len(trade_epu) > 0 else 0.0

    # China TPU
    china_tpu = recent[recent['series_id'] == 'CHNMAINLANDTPU']
    china_tpu_level = float(china_tpu.iloc[-1]['value']) if len(china_tpu) > 0 else 0.0

    # Classify regime
    if epu_level < EPU_REGIME_THRESHOLDS['low']:
        regime = 'low'
    elif epu_level < EPU_REGIME_THRESHOLDS['normal']:
        regime = 'normal'
    elif epu_level < EPU_REGIME_THRESHOLDS['elevated']:
        regime = 'elevated'
    elif epu_level < EPU_REGIME_THRESHOLDS['high']:
        regime = 'high'
    else:
        regime = 'extreme'

    # Regime change probability (based on z-score and recent volatility)
    regime_change_prob = min(1.0, abs(epu_zscore) / 3.0)

    return EPURegime(
        regime=regime,
        epu_level=epu_level,
        epu_zscore=float(epu_zscore) if not np.isnan(epu_zscore) else 0.0,
        epu_percentile=float(epu_percentile) if not np.isnan(epu_percentile) else 0.5,
        trade_epu_level=trade_epu_level,
        china_tpu_level=china_tpu_level,
        regime_change_prob=regime_change_prob,
    )


def _empty_epu_regime() -> EPURegime:
    """Return empty EPU regime."""
    return EPURegime(
        regime='normal',
        epu_level=100.0,
        epu_zscore=0.0,
        epu_percentile=0.5,
        trade_epu_level=0.0,
        china_tpu_level=0.0,
        regime_change_prob=0.0,
    )


# =============================================================================
# TRUMP EFFECT RISK METRICS
# =============================================================================

def calculate_trump_effect_risk_metrics(
    returns: pd.Series,
    epu_regime: EPURegime,
    event_intensity: Optional[EventIntensity] = None,
    risk_free_rate: float = 0.05,
) -> TrumpEffectRiskMetrics:
    """
    Calculate Trump Effect specific risk metrics with regime conditioning.

    Args:
        returns: Daily return series
        epu_regime: Current EPU regime
        event_intensity: Recent event intensity (optional)
        risk_free_rate: Annual risk-free rate

    Returns:
        TrumpEffectRiskMetrics dataclass
    """
    # Base risk metrics from existing infrastructure
    base_metrics = calculate_risk_metrics(returns, risk_free_rate)

    # Regime-adjusted volatility
    vol_mult = REGIME_VOL_MULTIPLIERS.get(epu_regime.regime, 1.0)
    regime_adjusted_vol = base_metrics.annualized_vol * vol_mult

    # Event sensitivity (if events provided)
    if event_intensity and event_intensity.event_count > 0:
        # Higher sensitivity if shock severity correlates with returns
        event_sensitivity = event_intensity.shock_severity * 0.5 + 0.5
    else:
        event_sensitivity = 0.5

    # Tail risk flag
    tail_risk_flag = (
        base_metrics.var_95 < -0.05 or  # 5% daily loss
        epu_regime.regime in ['high', 'extreme'] or
        (event_intensity and event_intensity.shock_severity > 0.7)
    )

    return TrumpEffectRiskMetrics(
        sharpe_ratio=base_metrics.sharpe_ratio,
        sortino_ratio=base_metrics.sortino_ratio,
        var_95=base_metrics.var_95,
        cvar_95=base_metrics.cvar_95,
        max_drawdown=base_metrics.max_drawdown if base_metrics.max_drawdown else 0.0,
        regime_adjusted_vol=regime_adjusted_vol,
        tail_risk_flag=tail_risk_flag,
        event_sensitivity=event_sensitivity,
    )


# =============================================================================
# GARCH WITH TRUMP REGIME ADJUSTMENT
# =============================================================================

def fit_trump_regime_garch(
    returns: pd.Series,
    epu_regime: EPURegime,
    model_type: str = 'gjr-garch',
) -> Tuple[GARCHResult, float]:
    """
    Fit GARCH model with Trump regime adjustment.

    Returns fitted GARCH and regime-adjusted unconditional volatility.

    Args:
        returns: Daily return series
        epu_regime: Current EPU regime
        model_type: GARCH variant

    Returns:
        Tuple of (GARCHResult, regime_adjusted_vol)
    """
    # Fit standard GARCH
    result = fit_garch(returns, model_type=model_type)

    # Apply regime multiplier
    vol_mult = REGIME_VOL_MULTIPLIERS.get(epu_regime.regime, 1.0)
    regime_adjusted_vol = result.unconditional_vol * vol_mult

    logger.info(f"Trump Regime GARCH:")
    logger.info(f"  Base unconditional vol: {result.unconditional_vol:.2%}")
    logger.info(f"  EPU regime: {epu_regime.regime} (mult: {vol_mult})")
    logger.info(f"  Regime-adjusted vol: {regime_adjusted_vol:.2%}")

    return result, regime_adjusted_vol


# =============================================================================
# FEATURE ENGINE (Main Class)
# =============================================================================

class TrumpEffectFeatureEngine:
    """
    Main feature engineering class for Trump Effect specialist.

    Combines FRED series, Yahoo proxies, and event data into
    feature vectors for training/inference.
    """

    def __init__(
        self,
        fred_df: pd.DataFrame,
        yahoo_df: Optional[pd.DataFrame] = None,
        events_df: Optional[pd.DataFrame] = None,
    ):
        """
        Initialize with data sources.

        Args:
            fred_df: FRED observations (as_of_date, series_id, value)
            yahoo_df: Yahoo prices (as_of_date, ticker, close, adj_close)
            events_df: Event ledger (event_date, topic_code, doc_type, text, ...)
        """
        self.fred_df = fred_df
        self.yahoo_df = yahoo_df
        self.events_df = events_df

    def compute_features_for_date(
        self,
        as_of_date: datetime,
    ) -> Dict:
        """
        Compute all Trump Effect features for a single date.

        Returns dict suitable for DataFrame row or JSON storage.
        """
        features = {
            'as_of_date': as_of_date,
            'symbol': 'ZL',
        }

        # EPU Regime
        epu_regime = detect_epu_regime(self.fred_df, as_of_date)
        features['epu_regime'] = epu_regime.regime
        features['epu_level'] = epu_regime.epu_level
        features['epu_zscore'] = epu_regime.epu_zscore
        features['epu_percentile'] = epu_regime.epu_percentile
        features['trade_epu_level'] = epu_regime.trade_epu_level
        features['china_tpu_level'] = epu_regime.china_tpu_level

        # FRED series (forward-filled)
        fred_features = self._get_fred_features(as_of_date)
        features.update(fred_features)

        # Probability proxies (Yahoo)
        if self.yahoo_df is not None:
            proxies = calculate_probability_proxies(self.yahoo_df, as_of_date)
            features['djt_ret_1d'] = proxies.djt_ret_1d
            features['djt_ret_5d'] = proxies.djt_ret_5d
            features['djt_rv_21d'] = proxies.djt_rv_21d
            features['fxi_ret_1d'] = proxies.fxi_ret_1d
            features['kweb_ret_1d'] = proxies.kweb_ret_1d
            features['djt_minus_fxi_ret_1d'] = proxies.djt_minus_fxi_ret_1d
            features['corr_djt_fxi_63d'] = proxies.corr_djt_fxi_63d
            features['corr_djt_kweb_63d'] = proxies.corr_djt_kweb_63d
            features['regime_decoupling'] = int(proxies.regime_decoupling)

        # Event intensity
        if self.events_df is not None:
            intensity = calculate_event_intensity(self.events_df, as_of_date, window_days=1)
            features['event_count_1d'] = intensity.event_count
            features['shock_severity_1d'] = intensity.shock_severity
            features['uncertainty_avg_1d'] = intensity.uncertainty_score
            features['novelty_avg_1d'] = intensity.novelty_score

            # 5-day rolling
            intensity_5d = calculate_event_intensity(self.events_df, as_of_date, window_days=5)
            features['event_count_5d'] = intensity_5d.event_count
            features['shock_sum_5d'] = intensity_5d.shock_severity * intensity_5d.event_count

        # Data completeness
        features['data_completeness_score'] = self._calculate_completeness(features)

        return features

    def _get_fred_features(self, as_of_date: datetime) -> Dict:
        """Extract FRED features for date (forward-filled)."""
        features = {}

        # Series to extract
        series_map = {
            'USEPUINDXD': 'epu_us_daily',
            'USEPUINDXM': 'epu_us_monthly',
            'EPUTRADE': 'epu_trade',
            'EMVTRADEPOLEMV': 'emv_trade',
            'CHNMAINLANDTPU': 'tpu_china',
            'B235RC1Q027SBEA': 'customs_duties',
            'IMPCH': 'imports_from_china',
        }

        for series_id, feature_name in series_map.items():
            series_data = self.fred_df[
                (self.fred_df['series_id'] == series_id) &
                (self.fred_df['as_of_date'] <= as_of_date)
            ]
            if len(series_data) > 0:
                features[feature_name] = float(series_data.iloc[-1]['value'])
            else:
                features[feature_name] = None

        return features

    def _calculate_completeness(self, features: Dict) -> float:
        """Calculate data completeness score (0-1)."""
        required_fields = [
            'epu_level', 'trade_epu_level', 'china_tpu_level',
            'customs_duties', 'imports_from_china',
        ]

        present = sum(1 for f in required_fields if features.get(f) is not None)
        return present / len(required_fields)

    def compute_all_features(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Compute features for date range.

        Returns DataFrame with one row per date.
        """
        dates = pd.date_range(start_date, end_date, freq='D')
        rows = []

        for dt in dates:
            try:
                features = self.compute_features_for_date(dt)
                rows.append(features)
            except Exception as e:
                logger.warning(f"Failed to compute features for {dt}: {e}")
                continue

        return pd.DataFrame(rows)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def quick_trump_effect_summary(
    fred_df: pd.DataFrame,
    yahoo_df: Optional[pd.DataFrame] = None,
    as_of_date: Optional[datetime] = None,
) -> Dict:
    """
    Quick summary of Trump Effect regime and metrics.

    Returns dict suitable for JSON/logging.
    """
    if as_of_date is None:
        as_of_date = datetime.now()

    # EPU Regime
    epu = detect_epu_regime(fred_df, as_of_date)

    summary = {
        'as_of_date': as_of_date.isoformat(),
        'epu_regime': epu.regime,
        'epu_level': round(epu.epu_level, 1),
        'epu_zscore': round(epu.epu_zscore, 2),
        'epu_percentile': round(epu.epu_percentile, 2),
        'trade_epu': round(epu.trade_epu_level, 1),
        'china_tpu': round(epu.china_tpu_level, 1),
        'vol_multiplier': REGIME_VOL_MULTIPLIERS.get(epu.regime, 1.0),
    }

    # Probability proxies
    if yahoo_df is not None:
        proxies = calculate_probability_proxies(yahoo_df, as_of_date)
        summary['djt_ret_1d'] = round(proxies.djt_ret_1d * 100, 2)
        summary['djt_rv_21d'] = round(proxies.djt_rv_21d * 100, 2)
        summary['djt_fxi_spread'] = round(proxies.djt_minus_fxi_ret_1d * 100, 2)
        summary['regime_decoupling'] = proxies.regime_decoupling

    return summary
