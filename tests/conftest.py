"""Shared pytest configuration and fixtures for ZINC-FUSION-V15."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Auto-skip integration tests when DATABASE_URL is missing
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(config, items):
    """Skip integration-marked tests when DATABASE_URL is not set."""
    import os

    if os.environ.get("DATABASE_URL"):
        return

    skip_integration = pytest.mark.skip(reason="DATABASE_URL not set")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


# ---------------------------------------------------------------------------
# Date fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_dates() -> pd.DatetimeIndex:
    """252 trading days starting 2024-01-02."""
    return pd.bdate_range("2024-01-02", periods=252)


# ---------------------------------------------------------------------------
# OHLCV fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_ohlcv(sample_dates) -> pd.DataFrame:
    """Synthetic ZL-like OHLCV data with realistic price range."""
    rng = np.random.default_rng(42)
    close = 48.0 + np.cumsum(rng.normal(0, 0.3, len(sample_dates)))
    return pd.DataFrame(
        {
            "trade_date": sample_dates,
            "symbol": "ZL",
            "open": close + rng.uniform(-0.2, 0.2, len(sample_dates)),
            "high": close + rng.uniform(0.1, 0.5, len(sample_dates)),
            "low": close - rng.uniform(0.1, 0.5, len(sample_dates)),
            "close": close,
            "volume": rng.integers(5000, 50000, len(sample_dates)),
        }
    )


# ---------------------------------------------------------------------------
# Signal output factory
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_signal_output():
    """Factory fixture returning a valid SignalOutput kwargs dict."""

    def _make(**overrides):
        defaults = {
            "as_of_date": date(2024, 6, 15),
            "bucket": "crush",
            "signal_1": 0.75,
            "signal_2": -0.3,
            "conf": 0.85,
            "abstained": False,
            "warmup": False,
            "max_input_age_days": 3,
        }
        defaults.update(overrides)
        return defaults

    return _make


# ---------------------------------------------------------------------------
# Signal config factory
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_signal_config():
    """Factory fixture returning a valid SignalConfig kwargs dict."""

    def _make(**overrides):
        defaults = {
            "bucket": "crush",
            "model_type": "test",
            "primary_features": ["close", "volume"],
            "secondary_features": [],
        }
        defaults.update(overrides)
        return defaults

    return _make


# ---------------------------------------------------------------------------
# Matrix DataFrame fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_matrix_df(sample_dates) -> pd.DataFrame:
    """Minimal valid matrix DataFrame for validation tests."""
    n = len(sample_dates)
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "trade_date": sample_dates,
            "symbol": "ZL",
            "close": 48.0 + np.cumsum(rng.normal(0, 0.3, n)),
            "volume": rng.integers(5000, 50000, n).astype(float),
            "fred_dff": rng.uniform(4.0, 5.5, n),
            "target_price_5d": rng.uniform(45, 55, n),
            "target_price_21d": rng.uniform(45, 55, n),
        }
    )
