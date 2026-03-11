"""
ARDL/Ridge-based signal generators: fx, fed.

FX Specialist: Real ARDL model with carry trade signals.
Fed Specialist: Ridge regression on lagged rates.

PATCHED 2026-01-23: Implemented real ARDL and carry trade
- Real ARDL model with optimal lag selection
- Carry trade signal from interest rate differentials
- Dynamic FX weights based on ZL correlation
- Trade-weighted effective exchange rate
"""

import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from fusion.specialists.base import (
    BaseSignalGenerator,
    SignalConfig,
    SignalOutput,
)

logger = logging.getLogger(__name__)

# Model persistence directory
MODELS_DIR = Path(__file__).parent.parent.parent.parent / "models" / "specialists"

# Try to import statsmodels for ARDL
try:
    import statsmodels.api as sm  # noqa: F401
    from statsmodels.regression.linear_model import OLS  # noqa: F401
    from statsmodels.tsa.stattools import adfuller, kpss  # noqa: F401

    ARDL_AVAILABLE = True
except ImportError:
    ARDL_AVAILABLE = False
    logger.warning("statsmodels ARDL not available; using simplified FX model")


# =============================================================================
# FX SIGNAL GENERATOR - REAL ARDL WITH CARRY TRADE
# =============================================================================


# =============================================================================
# FED SIGNAL GENERATOR
# =============================================================================


class FedSignalGenerator(BaseSignalGenerator):
    """
    Fed specialist: macro rate regime influence.

    Signal Contract:
    - signal_1: Rates regime score (financial conditions level)
    - signal_2: Regime change momentum (rate of change in conditions)

    Higher signal = tighter conditions = generally bearish risk assets
    Lower signal = easier conditions = generally bullish risk assets

    Inputs: Fed funds, Treasury yields, yield curve, NFCI, breakevens
    Model: Ridge regression on lagged rates (simplified to z-score composite)

    PATCHED 2026-01-21: Added yield curve dynamics and real rate signals
    - Curve momentum: flattening vs steepening
    - Curve inversion: predictive of recession
    - Real rates: nominal - inflation expectations (bearish for commodities)
    """

    def __init__(self):
        config = SignalConfig(
            bucket="fed",
            model_type="ridge",
            primary_features=[
                "close",
                # YIELD CURVE COMPLEX - Full term structure
                "fred_dff",  # Daily Fed Funds rate (replaces monthly FEDFUNDS)
                "fred_dgs3mo",  # 3-month Treasury (near-term)
                "fred_dgs2",  # 2Y Treasury (policy expectations)
                "fred_dgs10",  # 10Y Treasury (long-term)
                # FINANCIAL CONDITIONS - NFCI is weekly, will have NaN on non-release days
                "fred_nfci",  # Chicago NFCI (financial stress) - WEEKLY
            ],
            secondary_features=[
                # Extended yield curve
                "fred_dgs1",  # 1Y Treasury
                "fred_dgs5",  # 5Y Treasury
                "fred_dgs30",  # 30Y Treasury
                # Inflation expectations (from econ.inflation_1d)
                "fred_t10yie",  # 10Y breakeven inflation
                "fred_t5yie",  # 5Y breakeven inflation
                # Real yields (TIPS)
                "fred_dfii10",  # 10Y TIPS real yield
                # Credit spreads (replaces discontinued TEDRATE)
                "fred_bamlh0a0hym2",  # High yield spread (daily)
            ],
            lookback_days=252,
            min_data_points=63,
        )
        super().__init__(config)

    def validate_inputs(self, data: pd.DataFrame) -> list[str]:
        """Require FULL yield curve + financial conditions.

        NOTE: NFCI is weekly - presence in columns is required, but NaN values
        on non-release days are expected and acceptable.
        """
        missing = []
        if "close" not in data.columns:
            missing.append("close")
        # REQUIRE daily fed funds (DFF, not FEDFUNDS which is monthly)
        if "fred_dff" not in data.columns:
            missing.append("fred_dff")
        # REQUIRE core yield curve
        if "fred_dgs3mo" not in data.columns:
            missing.append("fred_dgs3mo")
        if "fred_dgs2" not in data.columns:
            missing.append("fred_dgs2")
        if "fred_dgs10" not in data.columns:
            missing.append("fred_dgs10")
        # REQUIRE financial conditions column (NaN on non-release days is OK)
        if "fred_nfci" not in data.columns:
            missing.append("fred_nfci")
        return missing

    def _compute_yield_curve(self, data: pd.DataFrame) -> pd.Series | None:
        """Compute yield curve slope (10Y - 2Y)."""
        if "fred_dgs10" in data.columns and "fred_dgs2" in data.columns:
            return data["fred_dgs10"] - data["fred_dgs2"]
        return None

    def _compute_curve_dynamics(self, data: pd.DataFrame) -> tuple:
        """
        Compute yield curve dynamics.

        NEW (2026-01-21): Enhanced curve analysis
        - 2s10s spread: Classic recession predictor
        - 3m10y spread: Near-term policy expectations
        - Curve momentum: Flattening vs steepening
        - Inversion indicator: Binary signal

        Returns:
            (curve_2s10s, curve_3m10y, curve_momentum, is_inverted)
        """
        curve_2s10s = pd.Series(np.nan, index=data.index)
        curve_3m10y = pd.Series(np.nan, index=data.index)
        curve_momentum = pd.Series(0.0, index=data.index)
        is_inverted = pd.Series(False, index=data.index)

        # 2s10s spread
        if "fred_dgs10" in data.columns and "fred_dgs2" in data.columns:
            curve_2s10s = data["fred_dgs10"] - data["fred_dgs2"]
            is_inverted = curve_2s10s < 0
            # Momentum: is curve flattening (-) or steepening (+)?
            curve_momentum = curve_2s10s.diff(21)

        # 3m10y spread (policy expectations)
        if "fred_dgs10" in data.columns and "fred_dgs3mo" in data.columns:
            curve_3m10y = data["fred_dgs10"] - data["fred_dgs3mo"]
        elif "fred_dgs10" in data.columns and "fred_fedfunds" in data.columns:
            # Use fed funds as proxy for short end
            curve_3m10y = data["fred_dgs10"] - data["fred_fedfunds"]

        return curve_2s10s, curve_3m10y, curve_momentum, is_inverted

    def _compute_real_rate(self, data: pd.DataFrame) -> pd.Series:
        """
        Compute real rate signal.

        NEW (2026-01-21): Real rates = Nominal - Inflation expectations
        Rising real rates are bearish for commodities.
        """
        real_rate = pd.Series(np.nan, index=data.index)

        # Try to get breakeven inflation
        breakeven_col = None
        for col in data.columns:
            if "t10yie" in col.lower() or "breakeven" in col.lower():
                breakeven_col = col
                break

        if "fred_dgs10" in data.columns:
            nominal = data["fred_dgs10"]
            if breakeven_col and breakeven_col in data.columns:
                # Actual breakeven data
                breakeven = data[breakeven_col]
                real_rate = nominal - breakeven
                logger.info(f"   Using actual breakeven inflation: {breakeven_col}")
            else:
                # Assume 2% inflation expectations as fallback
                real_rate = nominal - 2.0
                logger.info("   Using 2% assumed inflation (no breakeven data)")

        return real_rate

    def compute(self, data: pd.DataFrame, run_hash: str) -> list[SignalOutput]:
        """
        Compute Fed regime signals with ALL elite indicators.

        PATCHED 2026-01-21: Enhanced with curve dynamics and real rates

        Composite of:
        - Fed funds level z-score
        - 10Y yield z-score
        - Yield curve (10Y-2Y) z-score + dynamics
        - Real rate z-score (nominal - breakeven)
        - NFCI (if available)
        - ALL elite indicators on rates
        """
        signals = []

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL AND ALL RATE SERIES
        # =====================================================================
        data = self.add_all_technical_indicators(data, "close", "zl")

        # Add elite indicators for key rate series
        # NOTE: Using fred_dff (daily) instead of fred_fedfunds (monthly, stale)
        for rate_col in [
            "fred_dff",
            "fred_dgs2",
            "fred_dgs10",
            "fred_dgs30",
            "fred_dgs3mo",
            "fred_nfci",
            "fred_t10yie",
        ]:
            if rate_col in data.columns and data[rate_col].notna().sum() > 30:
                rate_data = data.copy()
                rate_data["close"] = data[rate_col]
                prefix = rate_col.replace("fred_", "")
                rate_data = self.add_all_technical_indicators(
                    rate_data, "close", prefix
                )
                for c in rate_data.columns:
                    if c.startswith(f"{prefix}_") and c not in data.columns:
                        data[c] = rate_data[c]

        # FIX 2026-02-03: Removed erroneous rate price lagging
        # Z-scores computed below use 252-day windows - already backward-looking
        # Lagging raw prices before z-score computation creates double-staleness

        # Compute component z-scores
        components = {}
        weights = {}

        # Fed funds (daily DFF, not monthly FEDFUNDS)
        if "fred_dff" in data.columns:
            components["dff"] = self.compute_zscore(
                data["fred_dff"], window=252, min_periods=126
            )
            weights["dff"] = 0.25

        # 10Y yield
        if "fred_dgs10" in data.columns:
            components["dgs10"] = self.compute_zscore(
                data["fred_dgs10"], window=252, min_periods=126
            )
            weights["dgs10"] = 0.20

        # Yield curve dynamics (NEW)
        curve_2s10s, _curve_3m10y, curve_momentum, is_inverted = (
            self._compute_curve_dynamics(data)
        )
        has_curve = not curve_2s10s.isna().all()

        if has_curve:
            # Inverted curve is tighter conditions (higher score)
            components["curve_2s10s"] = -self.compute_zscore(
                curve_2s10s, window=252, min_periods=126
            )
            weights["curve_2s10s"] = 0.20

        # Real rate (NEW)
        real_rate = self._compute_real_rate(data)
        has_real_rate = not real_rate.isna().all()

        if has_real_rate:
            # Higher real rate = tighter conditions = bearish commodities
            components["real_rate"] = self.compute_zscore(
                real_rate, window=252, min_periods=126
            )
            weights["real_rate"] = 0.15

        # NFCI (already a conditions index)
        if "fred_nfci" in data.columns:
            components["nfci"] = self.compute_zscore(
                data["fred_nfci"], window=252, min_periods=126
            )
            weights["nfci"] = 0.20

        if not components:
            logger.warning("FedSignalGenerator: No rate data available")
            return signals

        # Normalize weights
        total_weight = sum(weights.values())
        normalized = {k: v / total_weight for k, v in weights.items()}

        # Weighted composite - NO FILLNA
        # For each date, compute weighted average of available components only
        # This handles weekly NFCI gracefully without synthetic fills
        regime_score = pd.Series(np.nan, index=data.index)

        for idx in data.index:
            available_sum = 0.0
            available_weight = 0.0
            for name, zscore in components.items():
                if not pd.isna(zscore.loc[idx]):
                    available_sum += normalized[name] * zscore.loc[idx]
                    available_weight += normalized[name]

            # Only compute score if we have at least 50% of weighted components
            if available_weight >= 0.5:
                # Renormalize by available weight
                regime_score.loc[idx] = available_sum / available_weight

        # Regime change: combine score momentum + curve momentum
        score_momentum = regime_score.diff(21)
        if has_curve:
            # Flattening curve (negative momentum) = tightening signal
            curve_zscore_mom = self.compute_zscore(
                curve_momentum, window=63, min_periods=21
            )
            # Only add curve momentum where both are available (no fillna)
            combined_momentum = score_momentum.copy()
            valid_both = score_momentum.notna() & curve_zscore_mom.notna()
            combined_momentum.loc[valid_both] = (
                score_momentum.loc[valid_both] - 0.3 * curve_zscore_mom.loc[valid_both]
            )
        else:
            combined_momentum = score_momentum

        for idx in data.index:
            if pd.isna(regime_score.loc[idx]):
                continue

            # Confidence based on component availability
            available_count = sum(
                1 for name, zs in components.items() if not pd.isna(zs.loc[idx])
            )
            base_confidence = min(available_count / 5, 1.0) * 0.7 + 0.2

            # Boost confidence if we have curve dynamics
            if has_curve and not pd.isna(curve_2s10s.loc[idx]):
                base_confidence += 0.05
            if has_real_rate and not pd.isna(real_rate.loc[idx]):
                base_confidence += 0.05

            confidence = min(base_confidence, 0.95)

            change = (
                combined_momentum.loc[idx]
                if not pd.isna(combined_momentum.loc[idx])
                else 0.0
            )

            # Build metadata
            meta = {
                "components_used": list(components.keys()),
                "run_hash": run_hash,
            }

            # Add curve dynamics to metadata if available
            if has_curve:
                meta["curve_2s10s"] = (
                    float(curve_2s10s.loc[idx])
                    if not pd.isna(curve_2s10s.loc[idx])
                    else None
                )
                meta["curve_inverted"] = bool(is_inverted.loc[idx])
                meta["curve_momentum"] = (
                    float(curve_momentum.loc[idx])
                    if not pd.isna(curve_momentum.loc[idx])
                    else None
                )

            if has_real_rate:
                meta["real_rate"] = (
                    float(real_rate.loc[idx])
                    if not pd.isna(real_rate.loc[idx])
                    else None
                )

            as_of = idx.date() if hasattr(idx, "date") else idx
            # P0-3: Skip dates before EARLIEST_VALID_DATE
            if as_of < date(1990, 1, 1):
                continue

            # P0-1: Compute max staleness for this date
            rate_cols = [
                c
                for c in (self.config.primary_features + self.config.secondary_features)
                if c in data.columns
            ]
            max_staleness = self.compute_max_staleness(data, as_of, rate_cols)

            signals.append(
                SignalOutput(
                    as_of_date=as_of,
                    bucket="fed",
                    signal_1=float(regime_score.loc[idx]),
                    signal_2=float(change),
                    confidence=float(confidence),
                    model_type="ridge",
                    max_input_age_days=max_staleness,  # P0-1: Staleness tracking
                    metadata=meta,
                )
            )

        logger.info(
            f"FedSignalGenerator: Generated {len(signals)} signals (curve: {has_curve}, real_rate: {has_real_rate})"
        )
        return signals
