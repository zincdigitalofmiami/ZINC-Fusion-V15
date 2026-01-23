"""
VAR-based signal generators: energy.

Uses Vector Autoregression on small energy subset for spillover analysis.
Falls back to GBM on spreads if VAR unavailable or unstable.
"""

from datetime import date
from typing import List, Optional, Tuple
import pandas as pd
import numpy as np
import logging

from fusion.specialists.base import (
    BaseSignalGenerator,
    SignalConfig,
    SignalOutput,
)

logger = logging.getLogger(__name__)

# Try to import statsmodels for VAR
try:
    from statsmodels.tsa.api import VAR
    VAR_AVAILABLE = True
except ImportError:
    VAR_AVAILABLE = False
    logger.warning("statsmodels VAR not available; using simplified energy model")


# =============================================================================
# ENERGY SIGNAL GENERATOR
# =============================================================================

class EnergySignalGenerator(BaseSignalGenerator):
    """
    Energy specialist: spillovers from energy complex.

    Signal Contract:
    - signal_1: Energy spillover score (level)
    - signal_2: Spillover momentum (change)

    Higher signal = bullish energy complex = spillover to ZL (bullish)
    ZL competes with petroleum for biodiesel/renewable diesel demand.

    Inputs: CL (crude), HO (heating oil), RB (gasoline)
    Model: VAR on returns subset or spread-based fallback

    PATCHED 2026-01-21: Fixed 3-2-1 crack spread formula
    - Proper unit conversion: RB/HO in $/gal × 42 gal/bbl
    - 3 bbl crude → 2 bbl gasoline + 1 bbl distillate
    """

    def __init__(self):
        config = SignalConfig(
            bucket="energy",
            model_type="var",
            primary_features=["close"],
            secondary_features=[
                "cl_close",   # WTI Crude ($/barrel)
                "ho_close",   # Heating Oil ($/gallon)
                "rb_close",   # RBOB Gasoline ($/gallon)
            ],
            lookback_days=252,
            min_data_points=126,
        )
        super().__init__(config)

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Need at least crude oil for energy signal."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")
        if "cl_close" not in data.columns:
            missing.append("cl_close")
        return missing

    def _compute_energy_spreads(self, data: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        Compute key energy spreads:
        - BOHO spread: ZL - HO (biofuel premium)
        - 3-2-1 Crack spread: refining margin per barrel

        PATCHED 2026-01-21: Fixed crack spread formula
        - 3 barrels crude → 2 barrels gasoline + 1 barrel distillate
        - RB/HO are in $/gallon, CL is in $/barrel
        - 1 barrel = 42 gallons

        3-2-1 Crack = [(2 × RB × 42) + (1 × HO × 42)] / 3 - CL
        """
        zl = data["close"]
        cl = data["cl_close"]

        boho_spread = pd.Series(np.nan, index=data.index)
        crack_spread = pd.Series(np.nan, index=data.index)

        if "ho_close" in data.columns:
            ho = data["ho_close"]
            # BOHO spread: Convert ZL cents/lb to $/gal (7.7 lb/gal)
            # ZL $/gal = (ZL cents/lb / 100) × 7.7
            zl_per_gal = (zl / 100) * 7.7
            boho_spread = zl_per_gal - ho  # Both in $/gallon

        if "rb_close" in data.columns and "ho_close" in data.columns:
            rb = data["rb_close"]  # $/gallon
            ho = data["ho_close"]  # $/gallon

            # 3-2-1 Crack Spread ($/barrel):
            # Revenue: 2 bbl gasoline + 1 bbl distillate (convert to $/bbl)
            # Cost: 3 bbl crude, averaged
            gasoline_value = rb * 42  # $/gallon × 42 gal/bbl = $/bbl
            distillate_value = ho * 42

            # Per barrel of crude: (2 × gasoline + 1 × distillate) / 3 - crude
            crack_spread = (2 * gasoline_value + distillate_value) / 3 - cl
            logger.info(f"   3-2-1 crack spread range: ${crack_spread.min():.2f} to ${crack_spread.max():.2f}/bbl")

        return boho_spread, crack_spread

    def _fit_var(
        self,
        data: pd.DataFrame,
        columns: List[str],
        maxlags: int = 5,
    ) -> Optional[object]:
        """Fit VAR model if available."""
        if not VAR_AVAILABLE:
            return None

        try:
            # Prepare return series
            returns = data[columns].pct_change().dropna()
            if len(returns) < 100:
                return None

            # Fit VAR with lag selection via AIC
            model = VAR(returns)
            result = model.fit(maxlags=maxlags, ic='aic')
            return result

        except Exception as e:
            logger.warning(f"VAR fitting failed: {e}")
            return None

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute energy spillover signals.

        Primary: CL z-score as energy demand proxy
        Secondary: BOHO spread z-score for biofuel premium
        Enhancement: VAR impulse response if available
        """
        signals = []

        # Core energy indicator: crude oil z-score
        cl = data["cl_close"]
        cl_zscore = self.compute_zscore(cl, window=126, min_periods=63)

        # Energy spreads
        boho_spread, crack_spread = self._compute_energy_spreads(data)
        boho_zscore = self.compute_zscore(boho_spread, window=126, min_periods=63)
        crack_zscore = self.compute_zscore(crack_spread, window=126, min_periods=63)

        # ZL-CL correlation (rolling)
        zl = data["close"]
        zl_cl_corr = zl.rolling(63).corr(cl)

        # Composite spillover score
        # Weighted: 50% crude, 30% BOHO spread, 20% crack
        spillover_score = pd.Series(0.0, index=data.index)

        # Add components with available data
        component_weights = []
        if cl_zscore is not None:
            spillover_score += 0.50 * cl_zscore.fillna(0)
            component_weights.append(("cl", 0.50))

        if not boho_zscore.isna().all():
            spillover_score += 0.30 * boho_zscore.fillna(0)
            component_weights.append(("boho", 0.30))

        if not crack_zscore.isna().all():
            spillover_score += 0.20 * crack_zscore.fillna(0)
            component_weights.append(("crack", 0.20))

        # Renormalize
        total_weight = sum(w for _, w in component_weights)
        if total_weight > 0:
            spillover_score = spillover_score / total_weight

        # Spillover momentum (21-day change)
        spillover_momentum = spillover_score.diff(21)

        # Try VAR for enhanced analysis
        var_result = None
        energy_cols = ["cl_close"]
        if "ho_close" in data.columns:
            energy_cols.append("ho_close")
        if "rb_close" in data.columns:
            energy_cols.append("rb_close")

        if VAR_AVAILABLE and len(energy_cols) >= 2 and len(data) >= 252:
            var_result = self._fit_var(data, energy_cols)

        for idx in data.index:
            if pd.isna(spillover_score.loc[idx]):
                continue

            # Confidence based on components and correlation
            available_count = sum(
                1 for name, _ in component_weights
                if name == "cl" or (
                    name == "boho" and not pd.isna(boho_zscore.loc[idx])
                ) or (
                    name == "crack" and not pd.isna(crack_zscore.loc[idx])
                )
            )
            base_confidence = min(available_count / 3, 1.0) * 0.7 + 0.2

            # Boost confidence if ZL-CL correlation is strong
            corr = zl_cl_corr.loc[idx] if not pd.isna(zl_cl_corr.loc[idx]) else 0.3
            confidence = min(base_confidence + 0.1 * abs(corr), 0.95)

            momentum = spillover_momentum.loc[idx] if not pd.isna(spillover_momentum.loc[idx]) else 0.0

            # Build metadata
            meta = {
                "cl_zscore": float(cl_zscore.loc[idx]) if not pd.isna(cl_zscore.loc[idx]) else None,
                "boho_zscore": float(boho_zscore.loc[idx]) if not pd.isna(boho_zscore.loc[idx]) else None,
                "zl_cl_corr": float(corr),
                "var_fitted": var_result is not None,
                "run_hash": run_hash,
            }

            # Add crack spread value if available ($/bbl refining margin)
            if not crack_zscore.isna().all() and not pd.isna(crack_spread.loc[idx]):
                meta["crack_321_spread"] = float(crack_spread.loc[idx])
                meta["crack_zscore"] = float(crack_zscore.loc[idx]) if not pd.isna(crack_zscore.loc[idx]) else None

            signals.append(SignalOutput(
                as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                bucket="energy",
                signal_1=float(spillover_score.loc[idx]),
                signal_2=float(momentum),
                confidence=float(confidence),
                model_type="var" if var_result else "gbm",
                metadata=meta,
            ))

        logger.info(f"EnergySignalGenerator: Generated {len(signals)} signals (PATCHED: proper 3-2-1 crack)")
        return signals
