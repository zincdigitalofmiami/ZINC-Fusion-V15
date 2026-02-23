"""
Tests for volatility specialist data contract validation.

Validates:
1. Missing VIXCLS → raises ValueError
2. Missing/stale VXVCLS → warns + returns NaN term structure (not zeros)
3. Backwardation returns pd.NA (not False) when data missing

Run with: pytest tests/test_volatility_specialist.py -v
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.slow


class TestVolatilityDataContract:
    """Test the volatility specialist's data contract enforcement."""

    @pytest.fixture
    def sample_dates(self):
        """Generate sample date index."""
        return pd.date_range("2024-01-01", periods=30, freq="D")

    @pytest.fixture
    def valid_data(self, sample_dates):
        """Create valid data with all required columns."""
        return pd.DataFrame(
            {
                "close": np.random.uniform(50, 60, len(sample_dates)),
                "fred_vixcls": np.random.uniform(15, 25, len(sample_dates)),
                "fred_vxvcls": np.random.uniform(16, 26, len(sample_dates)),
            },
            index=sample_dates,
        )

    @pytest.fixture
    def volatility_generator(self):
        """Import and return the VolatilitySignalGenerator."""
        from fusion.specialists.garch_signals import VolatilitySignalGenerator

        return VolatilitySignalGenerator()

    def test_missing_vixcls_raises_error(self, volatility_generator, sample_dates):
        """Missing VIXCLS (required) should raise ValueError."""
        # Data without VIXCLS
        data = pd.DataFrame(
            {
                "close": np.random.uniform(50, 60, len(sample_dates)),
                "fred_vxvcls": np.random.uniform(16, 26, len(sample_dates)),
            },
            index=sample_dates,
        )

        result = volatility_generator._validate_required_series(data)

        assert result["valid"] is False
        assert "VIXCLS not in data columns" in result["issues"]

    def test_missing_vxvcls_warns_but_valid(self, volatility_generator, sample_dates):
        """Missing VXVCLS should warn but not fail validation."""
        # Data without VXVCLS
        data = pd.DataFrame(
            {
                "close": np.random.uniform(50, 60, len(sample_dates)),
                "fred_vixcls": np.random.uniform(15, 25, len(sample_dates)),
            },
            index=sample_dates,
        )

        result = volatility_generator._validate_required_series(data)

        assert result["valid"] is True  # Still valid, just degraded
        assert any("VXVCLS" in w or "VIX3M" in w for w in result["warnings"])

    def test_stale_vxvcls_warns(self, volatility_generator, sample_dates):
        """VXVCLS with all NaN in recent days should warn."""
        data = pd.DataFrame(
            {
                "close": np.random.uniform(50, 60, len(sample_dates)),
                "fred_vixcls": np.random.uniform(15, 25, len(sample_dates)),
                "fred_vxvcls": [16.0] * 25 + [np.nan] * 5,  # Last 5 days NaN
            },
            index=sample_dates,
        )

        result = volatility_generator._validate_required_series(data)

        assert result["valid"] is True
        assert any("no data in last 5 days" in w for w in result["warnings"])

    def test_term_structure_returns_nan_not_zeros(
        self, volatility_generator, sample_dates
    ):
        """When VIX/VXV missing, term structure should return NaN, not zeros."""
        # Data without VXV
        data = pd.DataFrame(
            {
                "close": np.random.uniform(50, 60, len(sample_dates)),
                "fred_vixcls": np.random.uniform(15, 25, len(sample_dates)),
                # No fred_vxvcls
            },
            index=sample_dates,
        )

        term_slope, is_backwardation, term_zscore, term_slope_normalized = (
            volatility_generator._compute_vix_term_structure(data)
        )

        # Should be NaN, not zeros
        assert term_slope.isna().all(), "term_slope should be all NaN when VXV missing"
        assert term_zscore.isna().all(), (
            "term_zscore should be all NaN when VXV missing"
        )
        assert term_slope_normalized.isna().all(), (
            "term_slope_normalized should be all NaN"
        )

        # Backwardation should be pd.NA (unknown), not False (contango)
        assert is_backwardation.isna().all(), (
            "is_backwardation should be pd.NA, not False"
        )

    def test_term_structure_valid_data(self, volatility_generator, valid_data):
        """With valid data, term structure should compute normally."""
        term_slope, is_backwardation, term_zscore, term_slope_normalized = (
            volatility_generator._compute_vix_term_structure(valid_data)
        )

        # Should have actual values (not all NaN)
        assert not term_slope.isna().all(), "term_slope should have values"
        # Backwardation should be boolean, not pd.NA
        assert is_backwardation.dtype == bool or not is_backwardation.isna().any()

    def test_backwardation_is_boolean_not_na_when_data_present(
        self, volatility_generator, valid_data
    ):
        """When data is present, backwardation should be True/False, not pd.NA."""
        term_slope, is_backwardation, _, _ = (
            volatility_generator._compute_vix_term_structure(valid_data)
        )

        # With valid data, backwardation should be computable
        assert not is_backwardation.isna().any(), (
            "backwardation should be True/False when data present, not pd.NA"
        )

    def test_term_structure_prefers_raw_vix3m_over_derived_columns(
        self, volatility_generator, sample_dates
    ):
        """
        Term structure should use raw VIX3M/VXV columns, not derived feature columns.
        """
        data = pd.DataFrame(
            {
                "close": np.random.uniform(50, 60, len(sample_dates)),
                "fred_vixcls": np.linspace(18, 22, len(sample_dates)),
                "fred_vix3mcls": np.linspace(20, 24, len(sample_dates)),
                # Derived feature that previously could be selected by substring match.
                "vix3m_autocorr_126d": [np.nan] * len(sample_dates),
            },
            index=sample_dates,
        )

        term_slope, is_backwardation, term_zscore, term_slope_normalized = (
            volatility_generator._compute_vix_term_structure(data)
        )

        expected = data["fred_vixcls"] - data["fred_vix3mcls"]
        pd.testing.assert_series_equal(term_slope, expected, check_names=False)
        assert not is_backwardation.isna().all()
        assert not term_slope_normalized.isna().all()
        # Small sample -> zscore can be NaN; this assertion mainly guards source selection.
        assert term_zscore.index.equals(data.index)

    def test_compute_returns_from_close_uses_no_fill_method(
        self, volatility_generator, sample_dates
    ):
        """
        Returns from close should not bridge across missing close values.
        """
        data = pd.DataFrame(
            {
                "close": [100.0, np.nan, 110.0] + [111.0] * (len(sample_dates) - 3),
                # Fabricated precomputed returns should be ignored when close is present.
                "returns_1d": [np.nan, 0.0, 0.1] + [0.0] * (len(sample_dates) - 3),
            },
            index=sample_dates,
        )

        returns = volatility_generator._compute_returns(data)

        assert pd.isna(returns.iloc[0])
        assert pd.isna(returns.iloc[1])
        assert pd.isna(returns.iloc[2])

    def test_compute_returns_masks_extreme_outliers(
        self, volatility_generator, sample_dates
    ):
        """
        Extreme daily jumps (>20%) should be masked as invalid returns.
        """
        data = pd.DataFrame(
            {
                "close": [100.0, 130.0, 131.0] + [132.0] * (len(sample_dates) - 3),
            },
            index=sample_dates,
        )

        returns = volatility_generator._compute_returns(data)

        # 30% jump should be masked.
        assert pd.isna(returns.iloc[1])
        # Normal next-day move should remain.
        assert returns.iloc[2] == pytest.approx((131.0 / 130.0) - 1.0)


class TestTermStructureSemantics:
    """Test that term structure semantics are correct."""

    @pytest.fixture
    def volatility_generator(self):
        from fusion.specialists.garch_signals import VolatilitySignalGenerator

        return VolatilitySignalGenerator()

    def test_backwardation_when_vix_higher_than_vix3m(self, volatility_generator):
        """Backwardation = VIX > VIX3M (fear regime)."""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        data = pd.DataFrame(
            {
                "close": [55.0] * 10,
                "fred_vixcls": [25.0] * 10,  # VIX higher
                "fred_vxvcls": [20.0] * 10,  # VIX3M lower
            },
            index=dates,
        )

        term_slope, is_backwardation, _, _ = (
            volatility_generator._compute_vix_term_structure(data)
        )

        # VIX - VIX3M = 25 - 20 = 5 (positive = backwardation)
        assert (term_slope == 5.0).all()
        assert is_backwardation.all(), "Should be backwardation when VIX > VIX3M"

    def test_contango_when_vix3m_higher_than_vix(self, volatility_generator):
        """Contango = VIX3M > VIX (normal regime)."""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        data = pd.DataFrame(
            {
                "close": [55.0] * 10,
                "fred_vixcls": [18.0] * 10,  # VIX lower
                "fred_vxvcls": [22.0] * 10,  # VIX3M higher
            },
            index=dates,
        )

        term_slope, is_backwardation, _, _ = (
            volatility_generator._compute_vix_term_structure(data)
        )

        # VIX - VIX3M = 18 - 22 = -4 (negative = contango)
        assert (term_slope == -4.0).all()
        assert not is_backwardation.any(), "Should be contango when VIX3M > VIX"
