"""
Regression tests for palm specialist feature contract handling.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
import pandas as pd
import pytest


def _build_base_input() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=120, freq="D")
    return pd.DataFrame(
        {
            "close": np.linspace(48.0, 56.0, len(dates)),
            "cpo_close": np.linspace(850.0, 980.0, len(dates)),
            "fred_dexmaus": np.linspace(0.22, 0.25, len(dates)),
            "fred_dexinus": np.linspace(15000.0, 16500.0, len(dates)),
            "palm_production_mt": np.linspace(1_200_000.0, 1_350_000.0, len(dates)),
            "palm_exports_mt": np.linspace(1_000_000.0, 1_150_000.0, len(dates)),
            "palm_stocks_mt": np.linspace(1_800_000.0, 1_950_000.0, len(dates)),
        },
        index=dates,
    )


@pytest.fixture
def palm_generator():
    from fusion.specialists.ecm_signals import PalmSignalGenerator

    gen = PalmSignalGenerator()
    # Keep tests deterministic and fast; these are not testing elite indicators
    # or statsmodels internals.
    gen.add_all_elite_indicators = lambda data, _close_col, _prefix: data
    gen._test_cointegration = lambda _zl, _cpo: (True, 0.05, 0.8)
    gen._compute_mean_reversion_speed = lambda spread: pd.Series(
        1.0, index=spread.index
    )
    return gen


def test_prepare_features_accepts_current_news_contract(palm_generator):
    data = _build_base_input()
    data["news_article_count"] = np.arange(len(data)) % 5
    data["news_avg_sentiment"] = np.linspace(-0.2, 0.3, len(data))

    features, _ = palm_generator._prepare_features(data)

    assert "palm_article_count" in features.columns
    assert "palm_sentiment" in features.columns
    assert "palm_news_intensity" in features.columns
    assert "mpob_stocks_zscore" in features.columns
    pd.testing.assert_series_equal(
        features["palm_article_count"], data["news_article_count"], check_names=False
    )


def test_prepare_features_accepts_legacy_news_contract(palm_generator):
    data = _build_base_input()
    data["article_count"] = np.arange(len(data)) % 3
    data["avg_sentiment"] = np.linspace(-0.1, 0.2, len(data))

    features, _ = palm_generator._prepare_features(data)

    assert "palm_article_count" in features.columns
    assert "palm_sentiment" in features.columns
    pd.testing.assert_series_equal(
        features["palm_article_count"], data["article_count"], check_names=False
    )
