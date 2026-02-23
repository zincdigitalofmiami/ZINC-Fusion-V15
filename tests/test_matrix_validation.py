"""Tests for matrix validation gates."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fusion.core_training.matrix_validation import (
    check_daily_observed_rate,
    check_date_floor_gate,
    check_epoch_date_gate,
    check_infinity_gate,
    check_null_gate,
    validate_matrix,
)


class TestNullGate:
    def test_passes_clean_df(self, sample_matrix_df):
        passed, failures = check_null_gate(sample_matrix_df)
        assert passed
        assert failures == []

    def test_fails_on_feature_nulls(self, sample_matrix_df):
        df = sample_matrix_df.copy()
        df.loc[df.index[0], "close"] = np.nan
        passed, failures = check_null_gate(df)
        assert not passed
        assert any("close" in f for f in failures)

    def test_excludes_target_columns(self, sample_matrix_df):
        df = sample_matrix_df.copy()
        df.loc[df.index[0], "target_price_5d"] = np.nan
        passed, _ = check_null_gate(df)
        assert passed  # target columns are excluded

    def test_excludes_age_days_columns(self, sample_matrix_df):
        df = sample_matrix_df.copy()
        df["fred_dff_age_days"] = np.nan
        passed, _ = check_null_gate(df)
        assert passed  # _age_days excluded

    def test_excludes_event_value_columns(self, sample_matrix_df):
        df = sample_matrix_df.copy()
        df["wasde_production_event_value"] = np.nan
        passed, _ = check_null_gate(df)
        assert passed


class TestInfinityGate:
    def test_passes_finite(self, sample_matrix_df):
        passed, failures = check_infinity_gate(sample_matrix_df)
        assert passed

    def test_fails_on_pos_inf(self, sample_matrix_df):
        df = sample_matrix_df.copy()
        df.loc[df.index[0], "close"] = float("inf")
        passed, failures = check_infinity_gate(df)
        assert not passed

    def test_fails_on_neg_inf(self, sample_matrix_df):
        df = sample_matrix_df.copy()
        df.loc[df.index[0], "close"] = float("-inf")
        passed, failures = check_infinity_gate(df)
        assert not passed


class TestEpochDateGate:
    def test_passes_modern_dates(self, sample_matrix_df):
        passed, _ = check_epoch_date_gate(sample_matrix_df)
        assert passed

    def test_fails_on_epoch(self, sample_matrix_df):
        df = sample_matrix_df.copy()
        df.loc[df.index[0], "trade_date"] = pd.Timestamp("1970-01-01")
        passed, failures = check_epoch_date_gate(df)
        assert not passed
        assert any("1970" in f for f in failures)


class TestDateFloorGate:
    def test_passes_modern_dates(self, sample_matrix_df):
        passed, _ = check_date_floor_gate(sample_matrix_df)
        assert passed

    def test_fails_on_pre_1990(self, sample_matrix_df):
        df = sample_matrix_df.copy()
        df.loc[df.index[0], "trade_date"] = pd.Timestamp("1985-01-01")
        passed, failures = check_date_floor_gate(df)
        assert not passed


class TestDailyObservedRate:
    def test_passes_at_threshold(self):
        n = 100
        df = pd.DataFrame({"col": [1.0] * n})
        passed, rate = check_daily_observed_rate(df, "col", threshold=0.95)
        assert passed
        assert rate == 1.0

    def test_fails_below_threshold(self):
        values = [1.0] * 94 + [np.nan] * 6
        df = pd.DataFrame({"col": values})
        passed, rate = check_daily_observed_rate(df, "col", threshold=0.95)
        assert not passed
        assert rate == pytest.approx(0.94)

    def test_missing_column_fails(self):
        df = pd.DataFrame({"other": [1.0]})
        passed, rate = check_daily_observed_rate(df, "missing_col")
        assert not passed
        assert rate == 0.0


class TestValidateMatrix:
    def test_clean_matrix_passes(self, sample_matrix_df):
        result = validate_matrix(sample_matrix_df, strict=False)
        assert result.passed

    def test_nulls_cause_hard_failure(self, sample_matrix_df):
        df = sample_matrix_df.copy()
        df.loc[df.index[0], "close"] = np.nan
        result = validate_matrix(df, strict=True)
        assert not result.passed
        assert len(result.hard_failures) > 0
