"""
ARDL/Ridge-based signal generators: fx, fed.

These specialists use autoregressive distributed lag models
or ridge regression for stable coefficient estimation.
"""

from datetime import date
from typing import List, Optional
import pandas as pd
import numpy as np
import logging

from fusion.specialists.base import (
    BaseSignalGenerator,
    SignalConfig,
    SignalOutput,
)

logger = logging.getLogger(__name__)


# =============================================================================
# FX SIGNAL GENERATOR
# =============================================================================

class FxSignalGenerator(BaseSignalGenerator):
    """
    FX specialist: currency pressure on export competitiveness.

    Signal Contract:
    - signal_1: FX pressure index (composite of USD/BRL, USD/CNY, USD/ARS, DXY)
    - signal_2: None (single composite signal)

    Higher signal = stronger USD = bearish for US ag exports (bearish ZL)
    Lower signal = weaker USD = bullish for exports (bullish ZL)

    Inputs: DXY, major ag-relevant FX pairs
    Model: Weighted composite of FX z-scores
    """

    def __init__(self):
        config = SignalConfig(
            bucket="fx",
            model_type="ardl",
            primary_features=["close"],
            secondary_features=[
                "fred_dexbzus",  # BRL/USD (inverted to USD/BRL)
                "fred_dexchus",  # CNY/USD (inverted to USD/CNY)
                "fred_dxy",      # DXY index
                "fred_dexmxus",  # MXN/USD
                "fred_dexusal",  # AUD/USD
            ],
            lookback_days=252,
            min_data_points=63,
        )
        super().__init__(config)

        # FX pair weights for ag exports
        self.fx_weights = {
            "fred_dexbzus": 0.35,   # Brazil - major soy competitor
            "fred_dexchus": 0.30,   # China - major importer
            "fred_dxy": 0.20,       # Broad dollar
            "fred_dexmxus": 0.10,   # Mexico
            "fred_dexusal": 0.05,   # Australia
        }

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Need at least one FX indicator."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")

        # Check for at least one FX series
        available_fx = [col for col in self.fx_weights.keys() if col in data.columns]
        if not available_fx:
            missing.append("at_least_one_fx_pair")
        return missing

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute FX pressure index.

        Weighted average of USD strength z-scores against ag-relevant currencies.
        """
        signals = []

        # Collect available FX z-scores
        fx_zscores = {}
        total_weight = 0.0

        for col, weight in self.fx_weights.items():
            if col in data.columns:
                series = data[col]
                # DXY is already USD strength; others need inversion
                if col == "fred_dxy":
                    fx_zscores[col] = self.compute_zscore(series, window=126, min_periods=42)
                else:
                    # FRED FX is foreign/USD, invert to USD/foreign for consistency
                    inverted = 1 / series
                    fx_zscores[col] = self.compute_zscore(inverted, window=126, min_periods=42)
                total_weight += weight

        if not fx_zscores:
            logger.warning("FxSignalGenerator: No FX data available")
            return signals

        # Normalize weights to sum to 1
        normalized_weights = {k: self.fx_weights[k] / total_weight for k in fx_zscores.keys()}

        # Compute weighted composite
        composite = pd.Series(0.0, index=data.index)
        for col, zscore in fx_zscores.items():
            composite += normalized_weights[col] * zscore.fillna(0)

        # ZL-FX correlation for context
        zl = data["close"]
        zl_fx_corr = pd.Series(np.nan, index=data.index)
        if "fred_dxy" in fx_zscores:
            zl_fx_corr = zl.rolling(63).corr(data["fred_dxy"])

        for idx in data.index:
            if pd.isna(composite.loc[idx]):
                continue

            # Count available FX pairs for confidence
            available_count = sum(
                1 for col, zs in fx_zscores.items()
                if not pd.isna(zs.loc[idx])
            )
            confidence = min(available_count / 5, 1.0) * 0.8 + 0.2

            signals.append(SignalOutput(
                as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                bucket="fx",
                signal_1=float(composite.loc[idx]),
                signal_2=None,
                confidence=float(confidence),
                model_type="ardl",
                metadata={
                    "fx_pairs_used": list(fx_zscores.keys()),
                    "zl_dxy_corr": float(zl_fx_corr.loc[idx]) if not pd.isna(zl_fx_corr.loc[idx]) else None,
                    "run_hash": run_hash,
                },
            ))

        logger.info(f"FxSignalGenerator: Generated {len(signals)} signals")
        return signals


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
            primary_features=["close"],
            secondary_features=[
                "fred_fedfunds",   # Fed funds rate
                "fred_dgs10",      # 10Y Treasury
                "fred_dgs2",       # 2Y Treasury
                "fred_dgs3mo",     # 3-month Treasury
                "fred_t10yie",     # 10Y breakeven inflation
                "fred_nfci",       # Chicago NFCI
            ],
            lookback_days=252,
            min_data_points=63,
        )
        super().__init__(config)

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Need at least one rates indicator."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")

        rate_cols = ["fred_fedfunds", "fred_dgs10", "fred_dgs2", "fred_nfci"]
        available = [col for col in rate_cols if col in data.columns]
        if not available:
            missing.append("at_least_one_rate_indicator")
        return missing

    def _compute_yield_curve(self, data: pd.DataFrame) -> Optional[pd.Series]:
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
            if 't10yie' in col.lower() or 'breakeven' in col.lower():
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

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute Fed regime signals.

        PATCHED 2026-01-21: Enhanced with curve dynamics and real rates

        Composite of:
        - Fed funds level z-score
        - 10Y yield z-score
        - Yield curve (10Y-2Y) z-score + dynamics
        - Real rate z-score (nominal - breakeven)
        - NFCI (if available)
        """
        signals = []

        # Compute component z-scores
        components = {}
        weights = {}

        # Fed funds
        if "fred_fedfunds" in data.columns:
            components["fedfunds"] = self.compute_zscore(
                data["fred_fedfunds"], window=252, min_periods=126
            )
            weights["fedfunds"] = 0.25

        # 10Y yield
        if "fred_dgs10" in data.columns:
            components["dgs10"] = self.compute_zscore(
                data["fred_dgs10"], window=252, min_periods=126
            )
            weights["dgs10"] = 0.20

        # Yield curve dynamics (NEW)
        curve_2s10s, curve_3m10y, curve_momentum, is_inverted = self._compute_curve_dynamics(data)
        has_curve = not curve_2s10s.isna().all()

        if has_curve:
            # Inverted curve is tighter conditions (higher score)
            components["curve_2s10s"] = -self.compute_zscore(curve_2s10s, window=252, min_periods=126)
            weights["curve_2s10s"] = 0.20

        # Real rate (NEW)
        real_rate = self._compute_real_rate(data)
        has_real_rate = not real_rate.isna().all()

        if has_real_rate:
            # Higher real rate = tighter conditions = bearish commodities
            components["real_rate"] = self.compute_zscore(real_rate, window=252, min_periods=126)
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

        # Weighted composite
        regime_score = pd.Series(0.0, index=data.index)
        for name, zscore in components.items():
            regime_score += normalized[name] * zscore.fillna(0)

        # Regime change: combine score momentum + curve momentum
        score_momentum = regime_score.diff(21)
        if has_curve:
            # Flattening curve (negative momentum) = tightening signal
            curve_zscore_mom = self.compute_zscore(curve_momentum, window=63, min_periods=21)
            combined_momentum = score_momentum - 0.3 * curve_zscore_mom.fillna(0)
        else:
            combined_momentum = score_momentum

        for idx in data.index:
            if pd.isna(regime_score.loc[idx]):
                continue

            # Confidence based on component availability
            available_count = sum(
                1 for name, zs in components.items()
                if not pd.isna(zs.loc[idx])
            )
            base_confidence = min(available_count / 5, 1.0) * 0.7 + 0.2

            # Boost confidence if we have curve dynamics
            if has_curve and not pd.isna(curve_2s10s.loc[idx]):
                base_confidence += 0.05
            if has_real_rate and not pd.isna(real_rate.loc[idx]):
                base_confidence += 0.05

            confidence = min(base_confidence, 0.95)

            change = combined_momentum.loc[idx] if not pd.isna(combined_momentum.loc[idx]) else 0.0

            # Build metadata
            meta = {
                "components_used": list(components.keys()),
                "run_hash": run_hash,
            }

            # Add curve dynamics to metadata if available
            if has_curve:
                meta["curve_2s10s"] = float(curve_2s10s.loc[idx]) if not pd.isna(curve_2s10s.loc[idx]) else None
                meta["curve_inverted"] = bool(is_inverted.loc[idx])
                meta["curve_momentum"] = float(curve_momentum.loc[idx]) if not pd.isna(curve_momentum.loc[idx]) else None

            if has_real_rate:
                meta["real_rate"] = float(real_rate.loc[idx]) if not pd.isna(real_rate.loc[idx]) else None

            signals.append(SignalOutput(
                as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                bucket="fed",
                signal_1=float(regime_score.loc[idx]),
                signal_2=float(change),
                confidence=float(confidence),
                model_type="ridge",
                metadata=meta,
            ))

        logger.info(f"FedSignalGenerator: Generated {len(signals)} signals (curve: {has_curve}, real_rate: {has_real_rate})")
        return signals
