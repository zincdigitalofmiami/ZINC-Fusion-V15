"""Tests for forward-fill forbidden suffixes policy."""

from __future__ import annotations

from fusion.core_training.build_matrix import FFILL_FORBIDDEN_SUFFIXES


class TestForbiddenSuffixes:
    def test_includes_delta(self):
        assert "_delta" in FFILL_FORBIDDEN_SUFFIXES

    def test_includes_ret(self):
        assert "_ret" in FFILL_FORBIDDEN_SUFFIXES

    def test_includes_mom(self):
        assert "_mom" in FFILL_FORBIDDEN_SUFFIXES

    def test_includes_zscore(self):
        assert "_zscore" in FFILL_FORBIDDEN_SUFFIXES

    def test_includes_spread(self):
        assert "_spread" in FFILL_FORBIDDEN_SUFFIXES

    def test_includes_ratio(self):
        assert "_ratio" in FFILL_FORBIDDEN_SUFFIXES

    def test_includes_is_release_day(self):
        assert "_is_release_day" in FFILL_FORBIDDEN_SUFFIXES

    def test_is_tuple(self):
        assert isinstance(FFILL_FORBIDDEN_SUFFIXES, tuple)


class TestForbiddenSuffixFiltering:
    """Verify that column selection logic correctly excludes forbidden suffixes."""

    def test_forbidden_columns_excluded_by_suffix_check(self):
        columns = [
            "fred_dff",  # allowed
            "close_delta",  # forbidden (_delta)
            "returns_ret",  # forbidden (_ret)
            "price_mom",  # forbidden (_mom)
            "vix_zscore",  # forbidden (_zscore)
            "bo_sm_spread",  # forbidden (_spread)
            "pe_ratio",  # forbidden (_ratio)
            "wasde_is_release_day",  # forbidden
        ]
        allowed = [
            c
            for c in columns
            if not any(c.lower().endswith(s) for s in FFILL_FORBIDDEN_SUFFIXES)
        ]
        assert allowed == ["fred_dff"]

    def test_allowed_columns_pass_filter(self):
        columns = [
            "fred_dff",
            "cpo_close",
            "wx_temp_anomaly_mean",
        ]
        allowed = [
            c
            for c in columns
            if not any(c.lower().endswith(s) for s in FFILL_FORBIDDEN_SUFFIXES)
        ]
        assert allowed == columns
