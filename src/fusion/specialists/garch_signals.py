"""
GARCH-based signal generators: volatility.

Uses GJR-GARCH for asymmetric volatility modeling with VIX as exogenous input.
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

# Try to import arch for GARCH models
try:
    from arch import arch_model
    ARCH_AVAILABLE = True
except ImportError:
    ARCH_AVAILABLE = False
    logger.warning("arch package not available; using simplified volatility model")


# =============================================================================
# VOLATILITY SIGNAL GENERATOR
# =============================================================================

class VolatilitySignalGenerator(BaseSignalGenerator):
    """
    Volatility specialist: regime risk and variance shifts.

    Signal Contract:
    - signal_1: Volatility regime level (0-3 scale: low/normal/high/crisis)
    - signal_2: Volatility regime change (probability of regime shift)

    Inputs: ZL returns, VIX as exogenous regime indicator
    Model: GJR-GARCH(1,1) with Student-t errors

    PATCHED 2026-01-21: Added VIX term structure for improved regime detection
    - Backwardation (VIX > VIX3M) = near-term fear/panic
    - Contango (VIX < VIX3M) = complacency
    """

    def __init__(self):
        config = SignalConfig(
            bucket="volatility",
            model_type="garch",
            primary_features=["close", "returns_1d"],
            secondary_features=[
                "fred_vixcls",     # VIX spot
                "fred_vix3mcls",   # VIX 3-month (term structure)
                "fred_ovxcls",     # OVX (oil volatility)
            ],
            lookback_days=504,  # 2 years for GARCH stability
            min_data_points=252,
        )
        super().__init__(config)
        self._vol_percentiles = None

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Returns can be computed from close if not present."""
        missing = []
        if "close" not in data.columns and "returns_1d" not in data.columns:
            missing.append("close_or_returns_1d")
        return missing

    def _compute_returns(self, data: pd.DataFrame) -> pd.Series:
        """Compute returns from close if not present."""
        if "returns_1d" in data.columns:
            return data["returns_1d"]
        elif "close" in data.columns:
            return data["close"].pct_change()
        else:
            raise ValueError("Neither returns_1d nor close available")

    def _fit_garch(self, returns: pd.Series) -> Optional[object]:
        """Fit GJR-GARCH model if arch is available."""
        if not ARCH_AVAILABLE:
            return None

        try:
            # Scale returns for numerical stability
            returns_pct = returns.dropna() * 100

            if len(returns_pct) < 252:
                logger.warning("Insufficient data for GARCH fitting")
                return None

            # GJR-GARCH(1,1) with Student-t
            model = arch_model(
                returns_pct,
                mean='Constant',
                vol='GARCH',
                p=1, o=1, q=1,  # o=1 for asymmetric term
                dist='t'
            )
            result = model.fit(disp='off', show_warning=False)
            return result

        except Exception as e:
            logger.warning(f"GARCH fitting failed: {e}")
            return None

    def _classify_regime(self, vol_zscore: float) -> int:
        """
        Map volatility z-score to regime level.

        Returns:
            0: Low volatility (zscore < -1)
            1: Normal volatility (-1 <= zscore < 1)
            2: High volatility (1 <= zscore < 2)
            3: Crisis volatility (zscore >= 2)
        """
        if vol_zscore < -1:
            return 0
        elif vol_zscore < 1:
            return 1
        elif vol_zscore < 2:
            return 2
        else:
            return 3

    def _compute_vix_term_structure(self, data: pd.DataFrame) -> tuple:
        """
        Compute VIX term structure signals.

        NEW (2026-01-21): VIX term structure is a powerful regime indicator:
        - Backwardation (VIX > VIX3M): Near-term fear, panic mode
        - Contango (VIX < VIX3M): Normal structure, complacency

        Returns:
            (term_slope, is_backwardation, term_zscore)
        """
        # Try different column name patterns
        # VIX: VIXCLS (FRED)
        # VIX3M: VXVCLS (FRED) - 3-month VIX for term structure
        vix_col = None
        vix3m_col = None

        for col in data.columns:
            col_lower = col.lower()
            if 'vixcls' in col_lower and 'vxv' not in col_lower:
                vix_col = col
            elif 'vxvcls' in col_lower or 'vix3m' in col_lower or 'vix_3m' in col_lower:
                vix3m_col = col

        if vix_col is None or vix3m_col is None:
            # Return empty series if term structure data not available
            return (
                pd.Series(0.0, index=data.index),
                pd.Series(False, index=data.index),
                pd.Series(0.0, index=data.index),
            )

        vix = data[vix_col]
        vix3m = data[vix3m_col]

        # Term structure slope: positive = backwardation (fear)
        term_slope = vix - vix3m

        # Backwardation indicator
        is_backwardation = term_slope > 0

        # Z-score of term slope for magnitude
        term_zscore = self.compute_zscore(term_slope, window=252, min_periods=63)

        logger.info(f"   VIX term structure: using {vix_col} and {vix3m_col}")
        return term_slope, is_backwardation, term_zscore

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute volatility regime signals.

        Uses rolling realized volatility + GARCH conditional variance
        + VIX as exogenous regime indicator.

        PATCHED 2026-01-21: Added VIX term structure for improved panic detection
        """
        signals = []

        # Compute returns
        returns = self._compute_returns(data)

        # Realized volatility (21-day rolling std, annualized)
        realized_vol = returns.rolling(21, min_periods=10).std() * np.sqrt(252)

        # Long-term vol for z-score normalization
        vol_mean = realized_vol.rolling(252, min_periods=126).mean()
        vol_std = realized_vol.rolling(252, min_periods=126).std()
        vol_zscore = (realized_vol - vol_mean) / vol_std.replace(0, np.nan)

        # VIX overlay if available (enhances regime detection)
        vix_adjustment = pd.Series(0.0, index=data.index)
        if "fred_vixcls" in data.columns:
            vix = data["fred_vixcls"]
            vix_zscore = self.compute_zscore(vix, window=252, min_periods=126)
            # VIX spike adds to regime level
            vix_adjustment = 0.3 * vix_zscore.clip(-2, 2)

        # VIX term structure (NEW)
        term_slope, is_backwardation, term_zscore = self._compute_vix_term_structure(data)
        has_term_structure = term_slope.abs().sum() > 0

        # Term structure adjustment: backwardation adds to fear signal
        term_adjustment = pd.Series(0.0, index=data.index)
        if has_term_structure:
            # Backwardation (positive slope) = fear = add to regime
            # Strong backwardation (>2 pts) = significant
            term_adjustment = 0.25 * term_zscore.clip(-2, 2)
            logger.info(f"   VIX term structure active: {is_backwardation.sum()} backwardation days")

        # Regime change probability (based on vol velocity + term structure shifts)
        vol_velocity = vol_zscore.diff(5)  # 5-day change in vol regime
        term_velocity = term_zscore.diff(5) if has_term_structure else pd.Series(0.0, index=data.index)
        combined_velocity = vol_velocity.fillna(0) + 0.3 * term_velocity.fillna(0)
        regime_change_prob = (np.abs(combined_velocity) / 2).clip(0, 1)

        # Fit GARCH for conditional variance (optional enhancement)
        garch_result = None
        if ARCH_AVAILABLE and len(returns.dropna()) >= 504:
            # Fit on recent 2 years
            recent_returns = returns.iloc[-504:]
            garch_result = self._fit_garch(recent_returns)

        for idx in data.index:
            if pd.isna(vol_zscore.loc[idx]):
                continue

            # Combine realized vol z-score with VIX and term structure adjustments
            combined_zscore = vol_zscore.loc[idx]
            if not pd.isna(vix_adjustment.loc[idx]):
                combined_zscore += vix_adjustment.loc[idx]
            if has_term_structure and not pd.isna(term_adjustment.loc[idx]):
                combined_zscore += term_adjustment.loc[idx]

            # Map to regime level (0-3)
            regime_level = self._classify_regime(combined_zscore)

            # Boost to crisis (3) if in backwardation with high VIX
            if has_term_structure and is_backwardation.loc[idx]:
                if regime_level == 2:  # High vol + backwardation → crisis
                    regime_level = 3

            # Regime change probability
            change_prob = regime_change_prob.loc[idx] if not pd.isna(regime_change_prob.loc[idx]) else 0.0

            # Confidence based on data quality
            confidence = 0.7
            if "fred_vixcls" in data.columns and not pd.isna(data.loc[idx, "fred_vixcls"]):
                confidence += 0.1
            if has_term_structure:
                confidence += 0.05  # Boost for term structure data
            if garch_result is not None:
                confidence += 0.05

            # Build metadata
            meta = {
                "vol_zscore": float(combined_zscore),
                "realized_vol": float(realized_vol.loc[idx]) if not pd.isna(realized_vol.loc[idx]) else None,
                "garch_fitted": garch_result is not None,
                "run_hash": run_hash,
            }

            # Add term structure metadata if available
            if has_term_structure:
                meta["vix_term_slope"] = float(term_slope.loc[idx]) if not pd.isna(term_slope.loc[idx]) else None
                meta["is_backwardation"] = bool(is_backwardation.loc[idx])

            signals.append(SignalOutput(
                as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                bucket="volatility",
                signal_1=float(regime_level),
                signal_2=float(change_prob),
                confidence=float(min(confidence, 0.95)),
                model_type="garch",
                metadata=meta,
            ))

        logger.info(f"VolatilitySignalGenerator: Generated {len(signals)} signals (term_structure: {has_term_structure})")
        return signals
