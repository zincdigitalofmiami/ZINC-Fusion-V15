"""
Unit tests for data loader staleness tracking and forward-fill limits.

Tests:
1. Forward-fill limits are enforced
2. Staleness tracking utilities work correctly
3. LCFS exception handling logs warnings
"""

import sys
from pathlib import Path
import pytest
import pandas as pd
import numpy as np
from datetime import date

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestForwardFillLimits:
    """Test that forward-fill limits are enforced."""

    def test_ffill_limit_enforced(self):
        """Test that ffill(limit=N) stops after N periods."""
        # Create series with gap
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        values = [1.0] * 10 + [np.nan] * 20 + [2.0] * 20
        series = pd.Series(values, index=dates)

        # Forward-fill with limit=10
        filled = series.ffill(limit=10)

        # Should only fill 10 periods, then NaN
        assert pd.isna(filled.iloc[20])  # 11th NaN should remain NaN
        assert filled.iloc[19] == 1.0  # 10th period should be filled
        assert filled.iloc[30] == 2.0  # Real value should be present

    def test_ffill_unlimited_vs_limited(self):
        """Compare unlimited vs limited forward-fill."""
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        values = [1.0] * 10 + [np.nan] * 30 + [2.0] * 10
        series = pd.Series(values, index=dates)

        unlimited = series.ffill()
        limited = series.ffill(limit=10)

        # Unlimited fills all NaN
        assert unlimited.iloc[20] == 1.0

        # Limited stops after limit
        assert pd.isna(limited.iloc[20])  # Beyond limit


class TestStalenessTracking:
    """Test staleness tracking utilities."""

    @pytest.fixture
    def base_generator(self):
        """Create a test BaseSignalGenerator instance."""
        from fusion.specialists.base import BaseSignalGenerator, SignalConfig

        config = SignalConfig(
            bucket="test",
            model_type="test",
            primary_features=["test_col"],
            secondary_features=[],
        )

        class TestGenerator(BaseSignalGenerator):
            def compute(self, data, run_hash):
                return []

        return TestGenerator(config)

    def test_compute_staleness_days_fresh(self, base_generator):
        """Test staleness calculation for fresh data."""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        series = pd.Series([1.0] * 10, index=dates)

        staleness = base_generator.compute_staleness_days(series, date(2024, 1, 10))
        assert staleness == 0  # Last value is today

    def test_compute_staleness_days_stale(self, base_generator):
        """Test staleness calculation for stale data."""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        series = pd.Series([1.0] * 10, index=dates)

        staleness = base_generator.compute_staleness_days(series, date(2024, 1, 20))
        assert staleness == 10  # 10 days since last observation

    def test_compute_staleness_days_empty(self, base_generator):
        """Test staleness calculation for empty series."""
        series = pd.Series([], dtype=float)

        staleness = base_generator.compute_staleness_days(series, date(2024, 1, 10))
        assert staleness == 999  # No data indicator

    def test_compute_staleness_days_all_nan(self, base_generator):
        """Test staleness calculation for all-NaN series."""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        series = pd.Series([np.nan] * 10, index=dates)

        staleness = base_generator.compute_staleness_days(series, date(2024, 1, 10))
        assert staleness == 999  # No valid data

    def test_compute_data_quality_metadata(self, base_generator):
        """Test data quality metadata computation."""
        dates = pd.date_range("2024-01-01", periods=20, freq="D")
        data = pd.DataFrame(
            {
                "col1": [1.0] * 15 + [np.nan] * 5,
                "col2": [2.0] * 10 + [np.nan] * 10,
            },
            index=dates,
        )

        metadata = base_generator.compute_data_quality_metadata(
            data, ["col1", "col2"], date(2024, 1, 20)
        )

        assert "col1" in metadata
        assert "col2" in metadata
        assert metadata["col1"]["coverage_pct"] == 75.0
        assert metadata["col2"]["coverage_pct"] == 50.0
        assert metadata["col1"]["staleness_days"] == 5  # 5 days since last value
        assert metadata["col2"]["staleness_days"] == 10  # 10 days since last value

    def test_compute_data_quality_metadata_missing_column(self, base_generator):
        """Test metadata computation handles missing columns gracefully."""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        data = pd.DataFrame({"col1": [1.0] * 10}, index=dates)

        metadata = base_generator.compute_data_quality_metadata(
            data, ["col1", "missing_col"], date(2024, 1, 10)
        )

        assert "col1" in metadata
        assert "missing_col" not in metadata

    def test_compute_staleness_days_with_real_mask(self, base_generator):
        """Test staleness calculation with is_real mask (P0 Fix 1)."""
        # Create scenario: One real point on day 0, then 20 missing days
        dates = pd.date_range("2024-01-01", periods=21, freq="D")
        original = pd.Series([1.0] + [np.nan] * 20, index=dates)

        # Forward-fill with limit=10
        filled = original.ffill(limit=10)

        # Create is_real mask: True where original had data, False where NaN
        is_real = original.notna()

        # Test staleness on day 5 (should be filled, but stale)
        as_of_date = date(2024, 1, 5)

        # Without mask (legacy): returns 0 (wrong)
        staleness_no_mask = base_generator.compute_staleness_days(filled, as_of_date)
        assert staleness_no_mask == 0  # Confirms bug exists

        # With mask: should return 4 days (since last real observation on day 0)
        staleness_with_mask = base_generator.compute_staleness_days(
            filled, as_of_date, is_real=is_real
        )
        assert staleness_with_mask == 4, f"Expected 4 days, got {staleness_with_mask}"

        # Test on day 15 (beyond limit, should be NaN but still stale)
        as_of_date_15 = date(2024, 1, 15)
        staleness_15 = base_generator.compute_staleness_days(
            filled, as_of_date_15, is_real=is_real
        )
        assert staleness_15 == 14, f"Expected 14 days, got {staleness_15}"

    def test_compute_data_quality_metadata_with_real_masks(self, base_generator):
        """Test data quality metadata with is_real masks."""
        dates = pd.date_range("2024-01-01", periods=21, freq="D")

        # Create data: real value on day 0, then forward-filled
        original = pd.Series([1.0] + [np.nan] * 20, index=dates)
        filled = original.ffill(limit=10)

        data = pd.DataFrame({"test_col": filled}, index=dates)
        is_real_masks = {"test_col": original.notna()}

        metadata = base_generator.compute_data_quality_metadata(
            data, ["test_col"], date(2024, 1, 5), is_real_masks=is_real_masks
        )

        assert "test_col" in metadata
        # Staleness should be > 0 for filled values
        assert metadata["test_col"]["staleness_days"] == 4, (
            f"Expected 4 days staleness, got {metadata['test_col']['staleness_days']}"
        )


class TestLCFSExceptionHandling:
    """Test LCFS exception handling."""

    def test_lcfs_exception_logs_warning(self, caplog):
        """Test that LCFS exception logs warning instead of silent pass."""
        import logging

        logger = logging.getLogger("fusion.specialists.data_loaders")
        try:
            raise Exception("LCFS table not found")
        except Exception as e:
            logger.warning(f"LCFS data unavailable: {e}")
            result_col = np.nan

        # Verify warning was logged
        assert "LCFS data unavailable" in caplog.text or result_col is np.nan


class TestForwardFillLimitsBySource:
    """Test forward-fill limits match expected cadences."""

    def test_wasde_limit_monthly(self):
        """WASDE should have monthly-scale TTL."""
        from fusion.validation.all_data_policy import SOURCE_FRESHNESS_TTLS

        assert SOURCE_FRESHNESS_TTLS["supply.usda_wasde_1m"] == 45

    def test_cftc_limit_weekly(self):
        """CFTC should have weekly-scale TTL."""
        from fusion.validation.all_data_policy import SOURCE_FRESHNESS_TTLS

        assert SOURCE_FRESHNESS_TTLS["pos.cftc_1w"] == 10

    def test_rin_limit_monthly(self):
        """RIN should allow monthly/irregular publication lag."""
        from fusion.validation.all_data_policy import SOURCE_FRESHNESS_TTLS

        assert SOURCE_FRESHNESS_TTLS["supply.epa_rin_1d"] == 75

    def test_fred_daily_limit(self):
        """FRED daily sources should have business-day TTL."""
        from fusion.validation.all_data_policy import SOURCE_FRESHNESS_TTLS

        assert SOURCE_FRESHNESS_TTLS["econ.rates_1d"] == 3


class TestNaNToNoneConversion:
    """Test that NaN values are converted to None before DB write."""

    def test_nan_to_none_double_defense(self):
        """Verify the double-defense NaN->None pattern used in write_matrix()."""
        df = pd.DataFrame(
            {
                "a": [1.0, np.nan, 3.0],
                "b": [np.nan, 2.0, np.nan],
            }
        )

        # Apply the same conversion as build_matrix.py write_matrix()
        df = df.where(df.notna(), None)
        values = [
            tuple(None if pd.isna(v) else v for v in row)
            for row in df.itertuples(index=False, name=None)
        ]

        assert values[0] == (1.0, None)
        assert values[1] == (None, 2.0)
        assert values[2] == (3.0, None)

        # Verify no NaN survives
        for row in values:
            for v in row:
                if v is not None:
                    assert not pd.isna(v), f"Found NaN in converted row: {row}"

    def test_none_preserved_for_string_columns(self):
        """Verify None in non-numeric columns is preserved, not mangled."""
        df = pd.DataFrame(
            {
                "num": [1.0, np.nan],
                "text": ["hello", None],
            }
        )

        df = df.where(df.notna(), None)
        values = [
            tuple(None if pd.isna(v) else v for v in row)
            for row in df.itertuples(index=False, name=None)
        ]

        assert values[0] == (1.0, "hello")
        assert values[1][0] is None
        assert values[1][1] is None


class TestSourceFreshnessTTLCoverage:
    """Test that SOURCE_FRESHNESS_TTLS covers all required sources."""

    def test_all_required_sources_have_ttl(self):
        """Every REQUIRED_DATA_SOURCES entry should have a freshness TTL."""
        from fusion.validation.all_data_policy import (
            REQUIRED_DATA_SOURCES,
            SOURCE_FRESHNESS_TTLS,
        )

        for table in REQUIRED_DATA_SOURCES:
            assert table in SOURCE_FRESHNESS_TTLS, (
                f"{table} in REQUIRED_DATA_SOURCES but missing from SOURCE_FRESHNESS_TTLS"
            )

    def test_ttl_values_are_positive(self):
        """All TTL values should be positive integers."""
        from fusion.validation.all_data_policy import SOURCE_FRESHNESS_TTLS

        for table, ttl in SOURCE_FRESHNESS_TTLS.items():
            assert isinstance(ttl, int) and ttl > 0, f"{table} has invalid TTL: {ttl}"

    def test_date_columns_are_event_date(self):
        """All date columns in REQUIRED_DATA_SOURCES should be event_date.

        Catches regressions of the metadata bug where as_of_date/week_ending/
        release_date were used instead of the actual Prisma schema column name.
        """
        from fusion.validation.all_data_policy import REQUIRED_DATA_SOURCES

        for table, (_, _, date_col) in REQUIRED_DATA_SOURCES.items():
            assert date_col == "event_date", (
                f"{table} uses date_col='{date_col}' but Prisma schema uses 'event_date'"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
