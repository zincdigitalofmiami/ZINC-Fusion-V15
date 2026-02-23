"""Tests for matrix manifest: schema hash, column stats, observed rate."""

from __future__ import annotations

import numpy as np
import pandas as pd

from fusion.core_training.matrix_manifest import (
    compute_column_stats,
    compute_raw_observed_rate,
    compute_schema_hash,
)


class TestSchemaHash:
    def test_deterministic(self, sample_matrix_df):
        h1 = compute_schema_hash(sample_matrix_df)
        h2 = compute_schema_hash(sample_matrix_df)
        assert h1 == h2

    def test_changes_on_added_column(self, sample_matrix_df):
        h1 = compute_schema_hash(sample_matrix_df)
        df2 = sample_matrix_df.copy()
        df2["new_feature"] = 0.0
        h2 = compute_schema_hash(df2)
        assert h1 != h2

    def test_changes_on_dtype_change(self, sample_matrix_df):
        h1 = compute_schema_hash(sample_matrix_df)
        df2 = sample_matrix_df.copy()
        df2["volume"] = df2["volume"].astype(int)
        h2 = compute_schema_hash(df2)
        assert h1 != h2

    def test_hash_length_64(self, sample_matrix_df):
        h = compute_schema_hash(sample_matrix_df)
        assert len(h) == 64


class TestColumnStats:
    def test_numeric_produces_percentiles(self, sample_matrix_df):
        stats = compute_column_stats(sample_matrix_df, "close")
        assert stats["p50"] is not None
        assert stats["mean"] is not None
        assert stats["std"] is not None

    def test_non_numeric_returns_nulls(self):
        df = pd.DataFrame({"text": ["a", "b", "c"]})
        stats = compute_column_stats(df, "text")
        assert stats["p50"] is None
        assert stats["mean"] is None

    def test_zero_rate_computed(self, sample_matrix_df):
        stats = compute_column_stats(sample_matrix_df, "close")
        assert stats["zero_rate"] is not None
        assert 0.0 <= stats["zero_rate"] <= 1.0


class TestRawObservedRate:
    def test_empty_df_returns_0(self):
        df = pd.DataFrame({"col": pd.Series([], dtype=float)})
        assert compute_raw_observed_rate(df, "col") == 0.0

    def test_full_col_returns_1(self):
        df = pd.DataFrame({"col": [1.0, 2.0, 3.0]})
        assert compute_raw_observed_rate(df, "col") == 1.0

    def test_half_null_returns_half(self):
        df = pd.DataFrame({"col": [1.0, np.nan, 1.0, np.nan]})
        assert compute_raw_observed_rate(df, "col") == 0.5

    def test_missing_column_returns_0(self):
        df = pd.DataFrame({"other": [1.0]})
        assert compute_raw_observed_rate(df, "missing") == 0.0
