"""
Base classes and contracts for specialist signal generators.

Each specialist implements BaseSignalGenerator to produce compact signals
that feed into the Core training matrix.
"""

import hashlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

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
    "crush": "gbm",
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
        model_type: Model class used (gbm, garch, ecm, etc.)
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
    signal_2: float | None = None
    confidence: float | None = None
    model_type: str = "unknown"
    max_input_age_days: int = 0  # REQUIRED: staleness tracking (P0-1 fix)
    source_tag: str | None = None
    degraded_level: int | None = None
    conf: float | None = None
    data_quality: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

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

    def to_dict(self) -> dict[str, Any]:
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
    primary_features: list[str]
    secondary_features: list[str]
    critical_features: list[str] = field(default_factory=list)
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
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[SignalOutput]:
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

    def validate_inputs(self, data: pd.DataFrame) -> list[str]:
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

    def _required_features(self) -> list[str]:
        """Required features for strict mode enforcement.

        FIX 2026-01-30: Enforce primary + critical features in strict mode.
        Secondary features are lower priority and may have sparse coverage.
        """
        ordered = (
            self.config.primary_features + self.config.critical_features
            # secondary_features have lower priority, not strictly required
        )
        return list(dict.fromkeys(ordered))

    def _missing_required_features(self, data: pd.DataFrame) -> list[str]:
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
    def compute(self, data: pd.DataFrame, run_hash: str) -> list[SignalOutput]:
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
        periods: list[int] | None = None,
    ) -> dict[str, pd.Series]:
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
        thresholds: tuple[float, float, float] = (-1.5, -0.5, 0.5, 1.5),
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
        is_real: pd.Series | None = None,
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
        columns: list[str],
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
        columns: list[str] | None = None,
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
        columns: list[str],
        as_of_date: date | None = None,
        is_real_masks: dict[str, pd.Series] | None = None,
    ) -> dict[str, Any]:
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
    # LEGACY INDICATOR HOOKS (RETIRED)
    # =========================================================================

    def add_all_technical_indicators(
        self,
        data: pd.DataFrame,
        symbol: str,
        prefix: str = None,
    ) -> pd.DataFrame:
        """Legacy no-op hook kept for backward compatibility."""
        return data

    def get_all_elite_indicator_names(self, prefix: str) -> list[str]:
        """Legacy no-op hook kept for backward compatibility."""
        return []
