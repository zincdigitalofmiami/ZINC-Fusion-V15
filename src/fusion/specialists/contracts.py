"""Stable contracts for specialist signal generators."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

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
    abstained: bool = False
    warmup: bool = False
    signal_type: str = "continuous"
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
        if not isinstance(self.abstained, bool):
            raise ValueError(f"abstained must be bool, got {type(self.abstained)}")
        if not isinstance(self.warmup, bool):
            raise ValueError(f"warmup must be bool, got {type(self.warmup)}")
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
            "abstained": self.abstained,
            "warmup": self.warmup,
            "signal_type": self.signal_type,
            "max_input_age_days": self.max_input_age_days,
            "source_tag": self.source_tag,
            "degraded_level": self.degraded_level,
            "conf": conf_value,
            "data_quality": self.data_quality,
            "metadata": self.metadata,
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


__all__ = [
    "EARLIEST_VALID_DATE",
    "MODEL_TYPES",
    "SPECIALIST_BUCKETS",
    "SignalConfig",
    "SignalOutput",
]
