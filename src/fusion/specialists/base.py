"""
Base classes and contracts for specialist signal generators.

Each specialist implements BaseSignalGenerator to produce compact signals
that feed into the Core training matrix.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, List, Tuple, Any
import hashlib
import pandas as pd
import numpy as np


# =============================================================================
# CONSTANTS
# =============================================================================

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
    "palm": "ecm",
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
        signal_2: Secondary signal value (optional)
        confidence: Model confidence 0-1 (optional)
        model_type: Model class used (xgb, garch, ecm, etc.)
        metadata: Additional diagnostic info (not stored)
    """
    as_of_date: date
    bucket: str
    signal_1: float
    signal_2: Optional[float] = None
    confidence: Optional[float] = None
    model_type: str = "unknown"
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.bucket not in SPECIALIST_BUCKETS:
            raise ValueError(f"Invalid bucket: {self.bucket}. Must be one of {SPECIALIST_BUCKETS}")
        if not np.isfinite(self.signal_1):
            raise ValueError(f"signal_1 must be finite, got {self.signal_1}")
        if self.signal_2 is not None and not np.isfinite(self.signal_2):
            raise ValueError(f"signal_2 must be finite if provided, got {self.signal_2}")
        if self.confidence is not None and not (0 <= self.confidence <= 1):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "as_of_date": self.as_of_date,
            "bucket": self.bucket,
            "signal_1": self.signal_1,
            "signal_2": self.signal_2,
            "confidence": self.confidence,
            "model_type": self.model_type,
        }


@dataclass
class SignalConfig:
    """
    Configuration for a specialist signal generator.

    Attributes:
        bucket: Specialist bucket name
        model_type: Model class to use
        primary_features: Required input features
        secondary_features: Optional input features
        lookback_days: Historical window for computation
        min_data_points: Minimum observations required
    """
    bucket: str
    model_type: str
    primary_features: List[str]
    secondary_features: List[str]
    lookback_days: int = 252  # 1 year default
    min_data_points: int = 60  # ~3 months minimum


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
        missing = self.validate_inputs(data)
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

        # Compute signals
        run_hash = self.get_run_hash(data)
        signals = self.compute(data, run_hash)

        # Validate outputs
        for sig in signals:
            if sig.bucket != self.bucket:
                raise ValueError(f"{self.name}: Output bucket mismatch: {sig.bucket} != {self.bucket}")

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
        periods: List[int] = [5, 21, 63],
    ) -> Dict[str, pd.Series]:
        """
        Utility: Compute momentum over multiple periods.

        Args:
            series: Input time series
            periods: List of lookback periods

        Returns:
            Dict mapping period name to momentum series
        """
        return {
            f"mom_{p}d": series.pct_change(periods=p)
            for p in periods
        }

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
            bins=[-np.inf, thresholds[0], thresholds[1], thresholds[2], thresholds[3], np.inf],
            labels=[-2, -1, 0, 1, 2],
        ).astype(float)
