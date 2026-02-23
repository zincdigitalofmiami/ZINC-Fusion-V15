"""Tests for BaseSignalGenerator utility methods."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from fusion.specialists.base import BaseSignalGenerator, SignalConfig


class _StubGenerator(BaseSignalGenerator):
    """Minimal concrete subclass for testing base utilities."""

    def compute(self, data, run_hash):
        return []


@pytest.fixture
def generator():
    config = SignalConfig(
        bucket="crush",
        model_type="test",
        primary_features=["close"],
        secondary_features=[],
    )
    return _StubGenerator(config)


class TestComputeZscore:
    def test_zero_mean(self, generator):
        s = pd.Series(np.random.default_rng(42).normal(50, 5, 100))
        z = generator.compute_zscore(s, window=63)
        # After window warm-up, mean should be near 0
        valid = z.dropna()
        assert abs(valid.mean()) < 0.5

    def test_handles_zero_std(self, generator):
        s = pd.Series([5.0] * 50)
        z = generator.compute_zscore(s, window=30, min_periods=10)
        # Constant series -> NaN z-scores (div by zero handled)
        assert z.dropna().empty or z.isna().all()

    def test_respects_min_periods(self, generator):
        s = pd.Series(np.arange(30, dtype=float))
        z = generator.compute_zscore(s, window=25, min_periods=21)
        # First 20 values should be NaN (not enough data for min_periods=21)
        assert z.iloc[:20].isna().all()


class TestComputeMomentum:
    def test_returns_dict_with_period_keys(self, generator):
        s = pd.Series(np.arange(100, dtype=float))
        result = generator.compute_momentum(s, periods=[5, 21])
        assert "mom_5d" in result
        assert "mom_21d" in result
        assert len(result) == 2


class TestComputeRegime:
    def test_maps_zscore_to_regime_labels(self, generator):
        z = pd.Series([-3.0, -1.0, 0.0, 1.0, 3.0])
        regime = generator.compute_regime(z)
        assert regime.iloc[0] == -2  # extreme negative
        assert regime.iloc[2] == 0  # neutral
        assert regime.iloc[4] == 2  # extreme positive


class TestComputeStaleness:
    def test_empty_series_returns_999(self, generator):
        s = pd.Series([], dtype=float)
        assert generator.compute_staleness_days(s, date(2024, 1, 10)) == 999

    def test_all_nan_returns_999(self, generator):
        dates = pd.date_range("2024-01-01", periods=10)
        s = pd.Series([np.nan] * 10, index=dates)
        assert generator.compute_staleness_days(s, date(2024, 1, 10)) == 999

    def test_fresh_data_returns_0(self, generator):
        dates = pd.date_range("2024-01-01", periods=10)
        s = pd.Series([1.0] * 10, index=dates)
        assert generator.compute_staleness_days(s, date(2024, 1, 10)) == 0

    def test_stale_data_returns_gap(self, generator):
        dates = pd.date_range("2024-01-01", periods=10)
        s = pd.Series([1.0] * 10, index=dates)
        assert generator.compute_staleness_days(s, date(2024, 1, 20)) == 10

    def test_is_real_mask_overrides_filled_values(self, generator):
        dates = pd.date_range("2024-01-01", periods=10)
        original = pd.Series([1.0] + [np.nan] * 9, index=dates)
        filled = original.ffill()
        is_real = original.notna()
        staleness = generator.compute_staleness_days(
            filled, date(2024, 1, 5), is_real=is_real
        )
        assert staleness == 4


class TestGenerate:
    def test_rejects_insufficient_data(self, generator):
        dates = pd.date_range("2024-01-01", periods=5)
        data = pd.DataFrame({"close": [1.0] * 5}, index=dates)
        with pytest.raises(ValueError, match="Insufficient data"):
            generator.generate(data, end_date=date(2024, 1, 5))
