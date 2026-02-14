"""
Base classes and contracts for specialist signal generators.

Each specialist implements BaseSignalGenerator to produce compact signals
that feed into the Core training matrix.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Dict, List, Tuple, Any
import hashlib
import os
import pandas as pd
import numpy as np


# =============================================================================
# CONSTANTS
# =============================================================================

# Earliest valid date for specialist signals (no meaningful market data before this)
EARLIEST_VALID_DATE = date(1990, 1, 1)

SPECIALIST_BUCKETS = [
    "crush",
    "china",
    "fx",
    "fed",
    "tariff",
    "energy",
    "biofuel",
    "palm",
    "volatility",
    "substitutes",
    "trump_effect",
]

MODEL_TYPES = {
    "crush": "xgb",
    "china": "gbm",
    "fx": "ardl",
    "fed": "ridge",
    "tariff": "tree",
    "energy": "var",
    "biofuel": "nlp_ema",
    "palm": "ecm_ridge",  # Ridge regression on ECM-derived features
    "volatility": "garch",
    "substitutes": "rf",
    "trump_effect": "event_study",
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class SignalOutput:
    """
    Output contract for all specialist signals.

    Attributes:
        as_of_date: Date for which signal is computed
        bucket: Specialist bucket name
        signal_1: Primary signal value (required)
        signal_2: Secondary signal value
        confidence: Model confidence 0-1
        model_type: Model class used (xgb, garch, ecm, etc.)
        max_input_age_days: Max input staleness in days
        source_tag: Source identifier
        degraded_level: Degradation level
        conf: Confidence for DB persistence
        data_quality: Persistable quality metadata
        metadata: Additional diagnostic info (not stored)
    """

    as_of_date: date
    bucket: str
    signal_1: float
    signal_2: Optional[float] = None
    confidence: Optional[float] = None
    model_type: str = "unknown"
    max_input_age_days: int = 0  # REQUIRED: staleness tracking (P0-1 fix)
    source_tag: Optional[str] = None
    degraded_level: Optional[int] = None
    conf: Optional[float] = None
    data_quality: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        # P0-3: Date validation - reject epoch dates and pre-1990
        if self.as_of_date < EARLIEST_VALID_DATE:
            raise ValueError(
                f"as_of_date {self.as_of_date} is before {EARLIEST_VALID_DATE}. "
                f"Specialist signals are not valid before this date."
            )
        if self.bucket not in SPECIALIST_BUCKETS:
            raise ValueError(
                f"Invalid bucket: {self.bucket}. Must be one of {SPECIALIST_BUCKETS}"
            )
        if not np.isfinite(self.signal_1):
            raise ValueError(f"signal_1 must be finite, got {self.signal_1}")
        if self.signal_2 is not None and not np.isfinite(self.signal_2):
            raise ValueError(
                f"signal_2 must be finite if provided, got {self.signal_2}"
            )
        if self.confidence is not None and not (0 <= self.confidence <= 1):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if self.conf is not None and not (0 <= self.conf <= 1):
            raise ValueError(f"conf must be in [0, 1], got {self.conf}")
        # P0-1: Staleness validation - must be non-negative
        if self.max_input_age_days < 0:
            raise ValueError(
                f"max_input_age_days must be >= 0, got {self.max_input_age_days}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        conf_value = self.conf if self.conf is not None else self.confidence
        return {
            "as_of_date": self.as_of_date,
            "bucket": self.bucket,
            "signal_1": self.signal_1,
            "signal_2": self.signal_2,
            "confidence": self.confidence,
            "model_type": self.model_type,
            "max_input_age_days": self.max_input_age_days,
            "source_tag": self.source_tag,
            "degraded_level": self.degraded_level,
            "conf": conf_value,
            "data_quality": self.data_quality,
        }


@dataclass
class SignalConfig:
    """
    Configuration for a specialist signal generator.

    Attributes:
        bucket: Specialist bucket name
        model_type: Model class to use
        primary_features: Required input features (baseline)
        secondary_features: Additional input features (lower priority)
        critical_features: Required inputs under strict mode
        strict_mode: Enforce all configured features when True
        lookback_days: Historical window for computation
        min_data_points: Minimum observations required
        max_input_age_days: Maximum staleness threshold (per Forward Fill Policy)
    """

    bucket: str
    model_type: str
    primary_features: List[str]
    secondary_features: List[str]
    critical_features: List[str] = field(default_factory=list)
    strict_mode: bool = True
    lookback_days: int = 252  # 1 year default
    min_data_points: int = 60  # ~3 months minimum
    max_input_age_days: int = 14  # Default TTL threshold per Forward Fill Policy


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================


class BaseSignalGenerator(ABC):
    """
    Abstract base class for all specialist signal generators.

    Each specialist must implement:
    - compute(): Generate signals for a date range
    - validate_inputs(): Check input data quality

    Subclasses should NOT override:
    - generate(): Main entry point with validation and error handling
    - get_run_hash(): Deterministic run identifier
    """

    def __init__(self, config: SignalConfig):
        self.config = config
        self.bucket = config.bucket
        self.model_type = config.model_type
        self.strict_mode = self._resolve_strict_mode()
        self.config.strict_mode = self.strict_mode

    def _resolve_strict_mode(self) -> bool:
        env_value = os.getenv("STRICT_DATA")
        if env_value is None:
            return bool(self.config.strict_mode)
        return env_value.strip().lower() in {"1", "true", "yes", "y"}

    @property
    def name(self) -> str:
        """Human-readable name for logging."""
        return f"{self.bucket.title()}SignalGenerator"

    def get_run_hash(self, data: pd.DataFrame) -> str:
        """
        Generate deterministic run hash from input data characteristics.
        Used for tracking and reproducibility.
        """
        hash_input = f"{self.bucket}:{self.model_type}:{len(data)}:{data.index.min()}:{data.index.max()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def generate(
        self,
        data: pd.DataFrame,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[SignalOutput]:
        """
        Main entry point for signal generation.

        Handles validation, date filtering, and error handling.
        Delegates actual computation to subclass compute() method.

        Args:
            data: Input DataFrame with features
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of SignalOutput objects
        """
        # Validate inputs
        missing = (
            self._missing_required_features(data)
            if self.strict_mode
            else self.validate_inputs(data)
        )
        if missing:
            raise ValueError(f"{self.name}: Missing required features: {missing}")

        # Filter date range
        if start_date:
            data = data[data.index >= pd.Timestamp(start_date)]
        if end_date:
            data = data[data.index <= pd.Timestamp(end_date)]

        # Check minimum data
        if len(data) < self.config.min_data_points:
            raise ValueError(
                f"{self.name}: Insufficient data. Got {len(data)}, need {self.config.min_data_points}"
            )

        # STALENESS GATE (2026-02-04): Check critical features for freshness
        # Per Forward Fill Policy (Docs/FORWARD_FILL_POLICY.md)
        max_staleness = self._check_critical_staleness(
            data, end_date or data.index.max().date()
        )
        if max_staleness > self.config.max_input_age_days:
            if self.strict_mode:
                raise ValueError(
                    f"{self.name}: STALE DATA REJECTED (strict mode). "
                    f"Max staleness: {max_staleness}d > threshold: {self.config.max_input_age_days}d"
                )
            else:
                import logging

                logging.getLogger(__name__).warning(
                    f"{self.name}: Running with stale data. "
                    f"Max staleness: {max_staleness}d > threshold: {self.config.max_input_age_days}d"
                )

        # Compute signals
        run_hash = self.get_run_hash(data)
        signals = self.compute(data, run_hash)

        # Validate outputs
        for sig in signals:
            if sig.bucket != self.bucket:
                raise ValueError(
                    f"{self.name}: Output bucket mismatch: {sig.bucket} != {self.bucket}"
                )

        return signals

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """
        Check that required features are present.

        Returns:
            List of missing feature names (empty if all present)
        """
        missing = []
        for feat in self.config.primary_features:
            if feat not in data.columns:
                missing.append(feat)
        return missing

    def _required_features(self) -> List[str]:
        """Required features for strict mode enforcement.

        FIX 2026-01-30: Enforce primary + critical features in strict mode.
        Secondary features are lower priority and may have sparse coverage.
        """
        ordered = (
            self.config.primary_features + self.config.critical_features
            # secondary_features have lower priority, not strictly required
        )
        return list(dict.fromkeys(ordered))

    def _missing_required_features(self, data: pd.DataFrame) -> List[str]:
        return [feat for feat in self._required_features() if feat not in data.columns]

    def _check_critical_staleness(self, data: pd.DataFrame, as_of_date: date) -> int:
        """
        Check staleness of critical features.

        Per Forward Fill Policy (Docs/FORWARD_FILL_POLICY.md):
        - If any critical feature exceeds max_input_age_days, signal is stale
        - Returns max staleness across all critical features

        Args:
            data: Input DataFrame
            as_of_date: Date for staleness calculation

        Returns:
            Maximum staleness in days across critical features
        """
        max_staleness = 0

        # Check critical features (not secondary - those can be sparse)
        critical_features = (
            self.config.critical_features or self.config.primary_features
        )

        for feat in critical_features:
            if feat not in data.columns:
                continue

            series = data[feat]

            # Look for corresponding is_real mask (if data loader provided it)
            is_real_col = f"{feat}_is_real"
            is_real = data.get(is_real_col)

            staleness = self.compute_staleness_days(series, as_of_date, is_real)
            max_staleness = max(max_staleness, staleness)

        return max_staleness

    @abstractmethod
    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute signals for the given data.

        Must be implemented by each specialist.

        Args:
            data: Validated input DataFrame
            run_hash: Deterministic run identifier

        Returns:
            List of SignalOutput objects (one per date)
        """
        pass

    def compute_zscore(
        self,
        series: pd.Series,
        window: int = 63,
        min_periods: int = 21,
    ) -> pd.Series:
        """
        Utility: Compute rolling z-score for normalization.

        Args:
            series: Input time series
            window: Rolling window size (default 63 = ~3 months)
            min_periods: Minimum observations for valid output

        Returns:
            Z-score normalized series
        """
        rolling_mean = series.rolling(window=window, min_periods=min_periods).mean()
        rolling_std = series.rolling(window=window, min_periods=min_periods).std()
        return (series - rolling_mean) / rolling_std.replace(0, np.nan)

    def compute_momentum(
        self,
        series: pd.Series,
        periods: List[int] | None = None,
    ) -> Dict[str, pd.Series]:
        """
        Utility: Compute momentum over multiple periods.

        Args:
            series: Input time series
            periods: List of lookback periods

        Returns:
            Dict mapping period name to momentum series
        """
        if periods is None:
            periods = [5, 21, 63]
        return {f"mom_{p}d": series.pct_change(periods=p) for p in periods}

    def compute_regime(
        self,
        zscore: pd.Series,
        thresholds: Tuple[float, float, float] = (-1.5, -0.5, 0.5, 1.5),
    ) -> pd.Series:
        """
        Utility: Map z-score to discrete regime levels.

        Regimes: -2 (very_low), -1 (low), 0 (normal), 1 (high), 2 (very_high)

        Args:
            zscore: Z-score normalized series
            thresholds: Boundaries for regime classification

        Returns:
            Integer regime series
        """
        return pd.cut(
            zscore,
            bins=[
                -np.inf,
                thresholds[0],
                thresholds[1],
                thresholds[2],
                thresholds[3],
                np.inf,
            ],
            labels=[-2, -1, 0, 1, 2],
        ).astype(float)

    def compute_staleness_days(
        self,
        series: pd.Series,
        as_of_date: date,
        is_real: Optional[pd.Series] = None,
    ) -> int:
        """
        Compute days since last non-forward-filled observation.

        Args:
            series: Time series (may contain forward-filled values)
            as_of_date: Current date for staleness calculation
            is_real: Optional boolean mask (True where raw had data, False where NaN)
                     If provided, staleness computed from last real observation.
                     If None, falls back to last_valid_index() (legacy behavior).

        Returns:
            Days since last real observation (999 if no data)
        """
        if series.empty or series.isna().all():
            return 999  # No data

        # If is_real mask provided, use it to find last real observation
        if is_real is not None:
            if not isinstance(is_real, pd.Series):
                raise ValueError("is_real must be a pandas Series")
            if not is_real.index.equals(series.index):
                raise ValueError("is_real index must match series index")

            # Find last index where is_real == True
            real_mask = is_real.fillna(False)
            if not real_mask.any():
                return 999  # No real observations

            last_real_idx = series.index[real_mask][-1] if real_mask.any() else None
            if last_real_idx is None:
                return 999

            # Calculate days since last real observation
            days_since = (pd.Timestamp(as_of_date) - pd.Timestamp(last_real_idx)).days
            return max(0, days_since)

        # Legacy behavior: find last non-null value (may be filled)
        last_valid_idx = series.last_valid_index()
        if last_valid_idx is None:
            return 999

        # Calculate days since last observation
        days_since = (pd.Timestamp(as_of_date) - pd.Timestamp(last_valid_idx)).days
        return max(0, days_since)

    def lag_features(
        self,
        data: pd.DataFrame,
        columns: List[str],
        lag: int = 1,
    ) -> pd.DataFrame:
        """
        Shift feature columns by lag days to prevent leakage.

        P0-4 FIX: For signal at date T, features should use T-lag data.
        This ensures no look-ahead bias in signal computation.

        Args:
            data: DataFrame with features indexed by date
            columns: List of column names to shift
            lag: Number of days to shift (default 1)

        Returns:
            DataFrame with shifted columns (original columns replaced)
        """
        lagged = data.copy()
        for col in columns:
            if col in lagged.columns:
                lagged[col] = lagged[col].shift(lag)
        return lagged

    def compute_max_staleness(
        self,
        data: pd.DataFrame,
        as_of_date: date,
        columns: Optional[List[str]] = None,
    ) -> int:
        """
        Compute maximum staleness across all specified columns.

        P0-1 FIX: Every signal must track max input staleness.

        Args:
            data: DataFrame with features indexed by date
            as_of_date: Date for staleness calculation
            columns: Columns to check (defaults to config.primary_features)

        Returns:
            Maximum staleness in days across all columns (999 if no data)
        """
        if columns is None:
            columns = self.config.primary_features

        staleness_days = []
        for col in columns:
            if col in data.columns:
                stale = self.compute_staleness_days(data[col], as_of_date)
                staleness_days.append(stale)

        return max(staleness_days) if staleness_days else 999

    def compute_data_quality_metadata(
        self,
        data: pd.DataFrame,
        columns: List[str],
        as_of_date: Optional[date] = None,
        is_real_masks: Optional[Dict[str, pd.Series]] = None,
    ) -> Dict[str, Any]:
        """
        Compute data quality metrics for metadata.

        Args:
            data: DataFrame with time series data
            columns: List of column names to analyze
            as_of_date: Current date (defaults to last index date)
            is_real_masks: Optional dict mapping column names to boolean masks
                          (True where raw had data, False where NaN)
                          If provided, staleness computed from real observations.

        Returns:
            Dict with coverage_pct, staleness_days, ffill_count per column
        """
        if as_of_date is None:
            as_of_date = data.index[-1].date() if len(data) > 0 else date.today()

        if is_real_masks is None:
            is_real_masks = {}

        metadata = {}

        for col in columns:
            if col not in data.columns:
                continue

            series = data[col]

            # Coverage percentage
            coverage_pct = series.notna().mean() * 100

            # Staleness days (use is_real mask if provided)
            is_real = is_real_masks.get(col)
            staleness_days = self.compute_staleness_days(
                series, as_of_date, is_real=is_real
            )

            # Forward-fill count (approximate: count consecutive identical values)
            # This is a heuristic - true ffill detection would require tracking source updates
            if len(series) > 1:
                # Count runs of identical values (potential forward-fill)
                diff = series.diff()
                ffill_count = (diff == 0).sum() - 1  # Subtract 1 for first NaN
                ffill_count = max(0, ffill_count)
            else:
                ffill_count = 0

            metadata[col] = {
                "coverage_pct": float(coverage_pct),
                "staleness_days": int(staleness_days),
                "ffill_count": int(ffill_count),
            }

        return metadata

    # =========================================================================
    # ALL ELITE INDICATORS - FULL SET FOR ANY SYMBOL
    # =========================================================================

    def add_all_elite_indicators(
        self,
        data: pd.DataFrame,
        symbol: str,
        prefix: str = None,
    ) -> pd.DataFrame:
        """
        Add ALL 27+ elite technical indicators for a given symbol.

        NO TIERS. NO LEVELS. ALL INDICATORS GET ADDED.

        Args:
            data: DataFrame with OHLCV columns
            symbol: Symbol to compute indicators for (column prefix)
            prefix: Output column prefix (defaults to symbol)

        Returns:
            DataFrame with ALL elite indicator columns added
        """
        prefix = prefix or symbol.lower()
        close_col = f"{symbol}_close" if f"{symbol}_close" in data.columns else "close"
        high_col = f"{symbol}_high" if f"{symbol}_high" in data.columns else None
        low_col = f"{symbol}_low" if f"{symbol}_low" in data.columns else None
        open_col = f"{symbol}_open" if f"{symbol}_open" in data.columns else None
        volume_col = f"{symbol}_volume" if f"{symbol}_volume" in data.columns else None

        if close_col not in data.columns:
            return data

        close = data[close_col]
        results = {}

        # =====================================================================
        # 1. HURST EXPONENT - Regime detection
        # =====================================================================
        def calc_hurst(ts):
            if len(ts) < 20 or ts.isna().any():
                return np.nan
            ts = np.array(ts)
            returns = np.diff(ts) / ts[:-1]
            returns = returns[~np.isnan(returns)]
            if len(returns) < 10:
                return np.nan
            max_k = min(int(len(returns) / 4), 50)
            if max_k < 4:
                return np.nan
            rs_list, n_list = [], []
            for k in range(4, max_k + 1):
                subperiod_len = len(returns) // k
                if subperiod_len < 2:
                    continue
                rs_values = []
                for i in range(k):
                    start, end = i * subperiod_len, (i + 1) * subperiod_len
                    subperiod = returns[start:end]
                    if len(subperiod) < 2:
                        continue
                    mean_adj = subperiod - np.mean(subperiod)
                    cumsum = np.cumsum(mean_adj)
                    R = np.max(cumsum) - np.min(cumsum)
                    S = np.std(subperiod, ddof=1)
                    if S > 0:
                        rs_values.append(R / S)
                if rs_values:
                    rs_list.append(np.mean(rs_values))
                    n_list.append(subperiod_len)
            if len(rs_list) < 3:
                return np.nan
            slope = np.polyfit(np.log(n_list), np.log(rs_list), 1)[0]
            return np.clip(slope, 0.0, 1.0)

        results[f"{prefix}_hurst"] = close.rolling(100).apply(calc_hurst, raw=False)

        # =====================================================================
        # 2. RSI VARIANTS - RSI(2), RSI(14), Cumulative RSI
        # =====================================================================
        def calc_rsi(series, period):
            delta = series.diff()
            gain = delta.where(delta > 0, 0)
            loss = (-delta).where(delta < 0, 0)
            avg_gain = gain.ewm(
                alpha=1 / period, min_periods=period, adjust=False
            ).mean()
            avg_loss = loss.ewm(
                alpha=1 / period, min_periods=period, adjust=False
            ).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            return 100 - (100 / (1 + rs))

        results[f"{prefix}_rsi_2"] = calc_rsi(close, 2)
        results[f"{prefix}_rsi_14"] = calc_rsi(close, 14)
        results[f"{prefix}_cumulative_rsi"] = (
            results[f"{prefix}_rsi_2"].rolling(3).sum()
        )

        # =====================================================================
        # 3. CONNORS RSI (3,2,100)
        # =====================================================================
        rsi_3 = calc_rsi(close, 3)
        streak = pd.Series(0.0, index=close.index)
        for i in range(1, len(close)):
            if pd.isna(close.iloc[i]) or pd.isna(close.iloc[i - 1]):
                streak.iloc[i] = 0.0
            elif close.iloc[i] > close.iloc[i - 1]:
                streak.iloc[i] = max(streak.iloc[i - 1], 0) + 1
            elif close.iloc[i] < close.iloc[i - 1]:
                streak.iloc[i] = min(streak.iloc[i - 1], 0) - 1
            else:
                streak.iloc[i] = 0.0
        rsi_streak = calc_rsi(streak, 2)
        roc_1d = close.pct_change(1) * 100
        roc_pct = roc_1d.rolling(100, min_periods=20).apply(
            lambda x: (
                (x.iloc[-1] > x.iloc[:-1]).sum() / len(x.iloc[:-1]) * 100
                if len(x) > 1
                else 50
            ),
            raw=False,
        )
        results[f"{prefix}_connors_rsi"] = (
            rsi_3.fillna(50) + rsi_streak.fillna(50) + roc_pct.fillna(50)
        ) / 3

        # =====================================================================
        # 4. MACD - Standard and Fast
        # =====================================================================
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        results[f"{prefix}_macd"] = ema_12 - ema_26
        results[f"{prefix}_macd_signal"] = (
            results[f"{prefix}_macd"].ewm(span=9, adjust=False).mean()
        )
        results[f"{prefix}_macd_hist"] = (
            results[f"{prefix}_macd"] - results[f"{prefix}_macd_signal"]
        )

        ema_5 = close.ewm(span=5, adjust=False).mean()
        ema_13 = close.ewm(span=13, adjust=False).mean()
        results[f"{prefix}_macd_fast"] = ema_5 - ema_13
        results[f"{prefix}_macd_fast_signal"] = (
            results[f"{prefix}_macd_fast"].ewm(span=4, adjust=False).mean()
        )
        results[f"{prefix}_macd_fast_hist"] = (
            results[f"{prefix}_macd_fast"] - results[f"{prefix}_macd_fast_signal"]
        )

        # =====================================================================
        # 5. MOVING AVERAGES - KAMA, HMA, ALMA, McGinley, SMA, EMA
        # =====================================================================
        # SMA
        results[f"{prefix}_sma_10"] = close.rolling(10).mean()
        results[f"{prefix}_sma_20"] = close.rolling(20).mean()
        results[f"{prefix}_sma_50"] = close.rolling(50).mean()
        results[f"{prefix}_sma_100"] = close.rolling(100).mean()
        results[f"{prefix}_sma_200"] = close.rolling(200).mean()

        # EMA
        results[f"{prefix}_ema_10"] = close.ewm(span=10, adjust=False).mean()
        results[f"{prefix}_ema_20"] = close.ewm(span=20, adjust=False).mean()
        results[f"{prefix}_ema_50"] = close.ewm(span=50, adjust=False).mean()

        # KAMA(10)
        change = abs(close - close.shift(10))
        vol_sum = abs(close.diff()).rolling(10).sum()
        er = change / vol_sum.replace(0, np.nan)
        fast_sc, slow_sc = 2 / 3, 2 / 31
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        kama = pd.Series(index=close.index, dtype=float)
        kama.iloc[9] = close.iloc[:10].mean() if len(close) >= 10 else close.iloc[0]
        for i in range(10, len(close)):
            if pd.notna(sc.iloc[i]):
                kama.iloc[i] = kama.iloc[i - 1] + sc.iloc[i] * (
                    close.iloc[i] - kama.iloc[i - 1]
                )
            else:
                kama.iloc[i] = kama.iloc[i - 1]
        results[f"{prefix}_kama_10"] = kama

        # HMA(20)
        wma_half = close.rolling(10).apply(
            lambda x: np.average(x, weights=range(1, len(x) + 1)), raw=True
        )
        wma_full = close.rolling(20).apply(
            lambda x: np.average(x, weights=range(1, len(x) + 1)), raw=True
        )
        raw_hma = 2 * wma_half - wma_full
        results[f"{prefix}_hma_20"] = raw_hma.rolling(4).apply(
            lambda x: np.average(x, weights=range(1, len(x) + 1)), raw=True
        )

        # ALMA(50)
        period, offset, sigma = 50, 0.85, 6
        m = int(offset * (period - 1))
        s = period / sigma
        weights = np.array(
            [np.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(period)]
        )
        weights = weights / weights.sum()
        results[f"{prefix}_alma_50"] = close.rolling(period, min_periods=25).apply(
            lambda x: np.dot(x, weights[-len(x) :] / weights[-len(x) :].sum()), raw=True
        )

        # McGinley Dynamic (14 and 100)
        for mcg_period in [14, 100]:
            md = pd.Series(index=close.index, dtype=float)
            md.iloc[0] = close.iloc[0]
            for i in range(1, len(close)):
                if (
                    pd.isna(close.iloc[i])
                    or pd.isna(md.iloc[i - 1])
                    or md.iloc[i - 1] == 0
                ):
                    md.iloc[i] = close.iloc[i]
                else:
                    ratio = close.iloc[i] / md.iloc[i - 1]
                    k = mcg_period * (ratio**4)
                    md.iloc[i] = (
                        md.iloc[i - 1] + (close.iloc[i] - md.iloc[i - 1]) / k
                        if k > 0
                        else md.iloc[i - 1]
                    )
            results[f"{prefix}_mcginley_{mcg_period}"] = md

        # =====================================================================
        # 6. Z-SCORES at multiple windows
        # =====================================================================
        for window in [5, 10, 21, 63, 126, 252]:
            mean = close.rolling(window).mean()
            std = close.rolling(window).std()
            results[f"{prefix}_zscore_{window}d"] = (close - mean) / std.replace(
                0, np.nan
            )

        # =====================================================================
        # 7. MOMENTUM at multiple periods
        # =====================================================================
        for period in [1, 5, 10, 21, 63, 126]:
            results[f"{prefix}_mom_{period}d"] = (
                close.pct_change(period, fill_method=None) * 100
            )

        # =====================================================================
        # 8. VOLATILITY - ATR, Garman-Klass, Yang-Zhang, Bollinger
        # =====================================================================
        if (
            high_col
            and low_col
            and high_col in data.columns
            and low_col in data.columns
        ):
            high, low = data[high_col], data[low_col]

            # True Range and ATR
            tr = pd.concat(
                [high - low, abs(high - close.shift(1)), abs(low - close.shift(1))],
                axis=1,
            ).max(axis=1)
            results[f"{prefix}_atr_10"] = tr.rolling(10).mean()
            results[f"{prefix}_atr_14"] = tr.rolling(14).mean()
            results[f"{prefix}_atr_50"] = tr.rolling(50).mean()
            results[f"{prefix}_atr_ratio"] = (
                results[f"{prefix}_atr_10"] / results[f"{prefix}_atr_50"]
            )

            # Garman-Klass
            hl_ratio = high / low
            log_hl = np.where((high == low) | (hl_ratio <= 0), 0.0, np.log(hl_ratio))
            if open_col and open_col in data.columns:
                open_p = data[open_col]
                co_ratio = close / open_p
                log_co = np.where(
                    (close == open_p) | (co_ratio <= 0) | (open_p == 0),
                    0.0,
                    np.log(co_ratio),
                )
                gk_daily = np.maximum(0.5 * log_hl**2 - 0.386 * log_co**2, 0.0)
                gk_rolling = pd.Series(gk_daily, index=data.index).rolling(20).mean()
                results[f"{prefix}_garman_klass"] = (
                    np.sqrt(np.maximum(gk_rolling, 0.0) * 252) * 100
                )

                # Yang-Zhang
                log_oc = np.log(open_p / close.shift(1))
                log_co_yz = np.log(close / open_p)
                log_ho = np.log(high / open_p)
                log_lo = np.log(low / open_p)
                log_hc = np.log(high / close)
                log_lc = np.log(low / close)
                rs = log_ho * log_hc + log_lo * log_lc
                k = 0.34 / 1.34
                var_o = log_oc.rolling(20).var()
                var_c = log_co_yz.rolling(20).var()
                var_rs = rs.rolling(20).mean()
                yz_var = var_o + k * var_c + (1 - k) * var_rs
                results[f"{prefix}_yang_zhang"] = np.sqrt(yz_var * 252) * 100

            # Bollinger Bands
            bb_mid = close.rolling(20).mean()
            bb_std = close.rolling(20).std()
            bb_upper = bb_mid + 2 * bb_std
            bb_lower = bb_mid - 2 * bb_std
            results[f"{prefix}_bb_upper"] = bb_upper
            results[f"{prefix}_bb_lower"] = bb_lower
            results[f"{prefix}_bb_pct_b"] = (close - bb_lower) / (bb_upper - bb_lower)
            results[f"{prefix}_bb_width"] = (bb_upper - bb_lower) / bb_mid

            # =====================================================================
            # 9. FISHER TRANSFORM
            # =====================================================================
            hl2 = (high + low) / 2
            highest = hl2.rolling(10).max()
            lowest = hl2.rolling(10).min()
            raw = 2 * ((hl2 - lowest) / (highest - lowest).replace(0, np.nan)) - 1
            raw = raw.clip(-0.999, 0.999)
            value = raw.ewm(span=5, adjust=False).mean()
            results[f"{prefix}_fisher"] = 0.5 * np.log((1 + value) / (1 - value))
            results[f"{prefix}_fisher_signal"] = results[f"{prefix}_fisher"].shift(1)

            # =====================================================================
            # 10. TTM SQUEEZE
            # =====================================================================
            kc_mid = close.rolling(20).mean()
            atr_kc = tr.rolling(20).mean()
            kc_upper = kc_mid + 1.5 * atr_kc
            kc_lower = kc_mid - 1.5 * atr_kc
            squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)
            results[f"{prefix}_ttm_squeeze_on"] = squeeze_on.astype(int)

            midline = (high.rolling(20).max() + low.rolling(20).min()) / 2
            midline = (midline + close.rolling(20).mean()) / 2
            results[f"{prefix}_ttm_squeeze_mom"] = close - midline

            # =====================================================================
            # 11. CCI (14, 50)
            # =====================================================================
            typical = (high + low + close) / 3
            for cci_period in [14, 50]:
                sma_tp = typical.rolling(cci_period).mean()
                mad = typical.rolling(cci_period).apply(
                    lambda x: np.abs(x - x.mean()).mean(), raw=True
                )
                results[f"{prefix}_cci_{cci_period}"] = (typical - sma_tp) / (
                    0.015 * mad
                )

            # =====================================================================
            # 12. SCHAFF TREND CYCLE
            # =====================================================================
            macd_stc = ema_5 - close.ewm(span=50, adjust=False).mean()
            lowest_macd = macd_stc.rolling(10).min()
            highest_macd = macd_stc.rolling(10).max()
            stoch1 = (
                100
                * (macd_stc - lowest_macd)
                / (highest_macd - lowest_macd).replace(0, np.nan)
            )
            pf = stoch1.ewm(span=3, adjust=False).mean()
            lowest_pf = pf.rolling(10).min()
            highest_pf = pf.rolling(10).max()
            stoch2 = (
                100 * (pf - lowest_pf) / (highest_pf - lowest_pf).replace(0, np.nan)
            )
            results[f"{prefix}_schaff"] = stoch2.ewm(span=3, adjust=False).mean()

            # =====================================================================
            # 13. RELATIVE VIGOR INDEX
            # =====================================================================
            if open_col and open_col in data.columns:
                open_p = data[open_col]
                vigor = close - open_p
                range_hl = high - low

                def swma(s):
                    return (s + 2 * s.shift(1) + 2 * s.shift(2) + s.shift(3)) / 6

                vigor_smooth = swma(vigor)
                range_smooth = swma(range_hl)
                vigor_sum = vigor_smooth.rolling(10).sum()
                range_sum = range_smooth.rolling(10).sum()
                results[f"{prefix}_rvi"] = vigor_sum / range_sum.replace(0, np.nan)
                results[f"{prefix}_rvi_signal"] = swma(results[f"{prefix}_rvi"])

        # =====================================================================
        # 14. VOLUME INDICATORS (if volume available)
        # =====================================================================
        if volume_col and volume_col in data.columns:
            volume = data[volume_col]

            # Volume Z-Score
            vol_mean = volume.rolling(20).mean()
            vol_std = volume.rolling(20).std()
            results[f"{prefix}_volume_zscore"] = (volume - vol_mean) / vol_std.replace(
                0, np.nan
            )

            # CMF (21)
            if high_col and low_col:
                high, low = data[high_col], data[low_col]
                hl_range = high - low
                mfm = np.where(hl_range == 0, 0.0, (2 * close - high - low) / hl_range)
                mfm = pd.Series(mfm, index=data.index).fillna(0)
                mfv = mfm * volume.fillna(0)
                mfv_sum = mfv.rolling(21).sum()
                vol_sum = volume.fillna(0).rolling(21).sum()
                results[f"{prefix}_cmf_21"] = np.where(
                    vol_sum == 0, 0.0, mfv_sum / vol_sum
                )

            # Elder Force Index
            results[f"{prefix}_elder_force"] = (
                (close.diff() * volume).ewm(span=13).mean()
            )

            # OBV
            obv = pd.Series(0.0, index=data.index)
            for i in range(1, len(close)):
                if close.iloc[i] > close.iloc[i - 1]:
                    obv.iloc[i] = obv.iloc[i - 1] + volume.iloc[i]
                elif close.iloc[i] < close.iloc[i - 1]:
                    obv.iloc[i] = obv.iloc[i - 1] - volume.iloc[i]
                else:
                    obv.iloc[i] = obv.iloc[i - 1]
            results[f"{prefix}_obv"] = obv

        # =====================================================================
        # 15. PRICE DISTANCE FROM MAs
        # =====================================================================
        for ma_col in [
            "sma_10",
            "sma_20",
            "sma_50",
            "sma_100",
            "sma_200",
            "ema_10",
            "ema_20",
            "ema_50",
        ]:
            full_col = f"{prefix}_{ma_col}"
            if full_col in results:
                results[f"{prefix}_dist_{ma_col}"] = (
                    (close - results[full_col]) / results[full_col] * 100
                )

        # =====================================================================
        # 16. RATE OF CHANGE
        # =====================================================================
        for period in [5, 10, 21]:
            results[f"{prefix}_roc_{period}"] = (
                (close - close.shift(period)) / close.shift(period)
            ) * 100

        # =====================================================================
        # 17. STOCHASTIC OSCILLATOR
        # =====================================================================
        if (
            high_col
            and low_col
            and high_col in data.columns
            and low_col in data.columns
        ):
            high, low = data[high_col], data[low_col]
            for period in [14, 21]:
                lowest_low = low.rolling(period).min()
                highest_high = high.rolling(period).max()
                stoch_k = (
                    100
                    * (close - lowest_low)
                    / (highest_high - lowest_low).replace(0, np.nan)
                )
                results[f"{prefix}_stoch_k_{period}"] = stoch_k
                results[f"{prefix}_stoch_d_{period}"] = stoch_k.rolling(3).mean()

        # =====================================================================
        # 18. WILLIAMS %R
        # =====================================================================
        if (
            high_col
            and low_col
            and high_col in data.columns
            and low_col in data.columns
        ):
            high, low = data[high_col], data[low_col]
            highest_high = high.rolling(14).max()
            lowest_low = low.rolling(14).min()
            results[f"{prefix}_williams_r"] = (
                -100
                * (highest_high - close)
                / (highest_high - lowest_low).replace(0, np.nan)
            )

        # =====================================================================
        # 19. ADX
        # =====================================================================
        if (
            high_col
            and low_col
            and high_col in data.columns
            and low_col in data.columns
        ):
            high, low = data[high_col], data[low_col]
            plus_dm = high.diff()
            minus_dm = -low.diff()
            plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
            minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

            tr = pd.concat(
                [high - low, abs(high - close.shift(1)), abs(low - close.shift(1))],
                axis=1,
            ).max(axis=1)
            atr_14 = tr.ewm(span=14, adjust=False).mean()

            plus_di = 100 * (plus_dm.ewm(span=14, adjust=False).mean() / atr_14)
            minus_di = 100 * (minus_dm.ewm(span=14, adjust=False).mean() / atr_14)

            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
            results[f"{prefix}_adx"] = dx.ewm(span=14, adjust=False).mean()
            results[f"{prefix}_plus_di"] = plus_di
            results[f"{prefix}_minus_di"] = minus_di

        # =====================================================================
        # 20. CORRELATION WITH CLOSE
        # =====================================================================
        for period in [21, 63, 126]:
            results[f"{prefix}_autocorr_{period}d"] = close.rolling(period).apply(
                lambda x: x.autocorr(lag=1) if len(x) > 1 else np.nan, raw=False
            )

        # =====================================================================
        # ADD ALL RESULTS TO DATAFRAME
        # =====================================================================
        for col_name, series in results.items():
            if isinstance(series, np.ndarray):
                data[col_name] = pd.Series(series, index=data.index)
            else:
                data[col_name] = series

        return data

    def get_all_elite_indicator_names(self, prefix: str) -> List[str]:
        """Return list of ALL elite indicator column names for a given prefix."""
        return [
            # Hurst
            f"{prefix}_hurst",
            # RSI variants
            f"{prefix}_rsi_2",
            f"{prefix}_rsi_14",
            f"{prefix}_cumulative_rsi",
            f"{prefix}_connors_rsi",
            # MACD
            f"{prefix}_macd",
            f"{prefix}_macd_signal",
            f"{prefix}_macd_hist",
            f"{prefix}_macd_fast",
            f"{prefix}_macd_fast_signal",
            f"{prefix}_macd_fast_hist",
            # Moving averages
            f"{prefix}_sma_10",
            f"{prefix}_sma_20",
            f"{prefix}_sma_50",
            f"{prefix}_sma_100",
            f"{prefix}_sma_200",
            f"{prefix}_ema_10",
            f"{prefix}_ema_20",
            f"{prefix}_ema_50",
            f"{prefix}_kama_10",
            f"{prefix}_hma_20",
            f"{prefix}_alma_50",
            f"{prefix}_mcginley_14",
            f"{prefix}_mcginley_100",
            # Z-scores
            f"{prefix}_zscore_5d",
            f"{prefix}_zscore_10d",
            f"{prefix}_zscore_21d",
            f"{prefix}_zscore_63d",
            f"{prefix}_zscore_126d",
            f"{prefix}_zscore_252d",
            # Momentum
            f"{prefix}_mom_1d",
            f"{prefix}_mom_5d",
            f"{prefix}_mom_10d",
            f"{prefix}_mom_21d",
            f"{prefix}_mom_63d",
            f"{prefix}_mom_126d",
            # Volatility
            f"{prefix}_atr_10",
            f"{prefix}_atr_14",
            f"{prefix}_atr_50",
            f"{prefix}_atr_ratio",
            f"{prefix}_garman_klass",
            f"{prefix}_yang_zhang",
            f"{prefix}_bb_upper",
            f"{prefix}_bb_lower",
            f"{prefix}_bb_pct_b",
            f"{prefix}_bb_width",
            # Oscillators
            f"{prefix}_fisher",
            f"{prefix}_fisher_signal",
            f"{prefix}_ttm_squeeze_on",
            f"{prefix}_ttm_squeeze_mom",
            f"{prefix}_cci_14",
            f"{prefix}_cci_50",
            f"{prefix}_schaff",
            f"{prefix}_rvi",
            f"{prefix}_rvi_signal",
            # Volume
            f"{prefix}_volume_zscore",
            f"{prefix}_cmf_21",
            f"{prefix}_elder_force",
            f"{prefix}_obv",
            # Distance from MAs
            f"{prefix}_dist_sma_10",
            f"{prefix}_dist_sma_20",
            f"{prefix}_dist_sma_50",
            f"{prefix}_dist_sma_100",
            f"{prefix}_dist_sma_200",
            f"{prefix}_dist_ema_10",
            f"{prefix}_dist_ema_20",
            f"{prefix}_dist_ema_50",
            # ROC
            f"{prefix}_roc_5",
            f"{prefix}_roc_10",
            f"{prefix}_roc_21",
            # Stochastic
            f"{prefix}_stoch_k_14",
            f"{prefix}_stoch_d_14",
            f"{prefix}_stoch_k_21",
            f"{prefix}_stoch_d_21",
            # Williams %R
            f"{prefix}_williams_r",
            # ADX
            f"{prefix}_adx",
            f"{prefix}_plus_di",
            f"{prefix}_minus_di",
            # Autocorrelation
            f"{prefix}_autocorr_21d",
            f"{prefix}_autocorr_63d",
            f"{prefix}_autocorr_126d",
        ]
