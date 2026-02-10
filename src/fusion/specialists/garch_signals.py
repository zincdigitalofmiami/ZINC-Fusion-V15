"""
Volatility Signal Generator - GJR-GARCH(1,1) Conditional Variance.

SIGNAL TYPE: continuous (GARCH conditional variance z-score)
OUTPUT:
  - signal_1: GARCH conditional variance z-score (CONTINUOUS, NOT discrete regime)
  - signal_2: Regime transition probability

This specialist outputs CONTINUOUS CONDITIONAL VARIANCE from GJR-GARCH model.
The discrete regime classification (0-3) is stored in metadata for reference only.

PATCHED 2026-02-02: Changed from discrete_regime to continuous GARCH output.
- signal_1 was: discrete regime (0,1,2,3) - WRONG, only 4 unique values
- signal_1 now: GARCH conditional variance z-score (continuous)
- This provides Core model with actual volatility information, not just buckets
"""

from datetime import date
from typing import List, Optional, Dict
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


# Conservative guard against obviously corrupt daily jumps in raw futures prices.
# Soybean oil daily returns above 20% are treated as invalid observations.
MAX_ABS_DAILY_RETURN = 0.20


# =============================================================================
# VOLATILITY SIGNAL GENERATOR
# =============================================================================


class VolatilitySignalGenerator(BaseSignalGenerator):
    """
    Volatility specialist: GJR-GARCH(1,1) conditional variance.

    SIGNAL TYPE: continuous (GARCH conditional variance z-score)
    ==============================================================
    This specialist outputs CONTINUOUS CONDITIONAL VARIANCE Z-SCORES from
    a fitted GJR-GARCH(1,1) model. The discrete regime classification is
    stored in metadata for reference.

    Signal Contract:
    - signal_1: GARCH conditional variance z-score (CONTINUOUS)
        - Negative = low volatility (below average)
        - Zero = normal volatility (at average)
        - Positive = high volatility (above average)
        - >2.0 = crisis-level volatility
    - signal_2: Regime transition probability (0.0-1.0)

    Health Metrics:
    - Standard continuous metrics (variance, correlation, coverage)
    - GARCH model diagnostics (AIC, persistence)

    Inputs: ZL returns, VIX term structure as exogenous indicator
    Model: GJR-GARCH(1,1) with Student-t errors

    PATCHED 2026-01-21: Added VIX term structure for improved regime detection
    PATCHED 2026-02-02: Changed from discrete_regime to continuous GARCH output
    - Core model needs continuous variance signal, not 4-bucket classification
    - Discrete regime now stored in metadata only
    """

    # =========================================================================
    # VOLATILITY INDICES - Complete Vol Surface
    # =========================================================================
    VOL_INDICES = {
        # VIX Complex
        "fred_vixcls": {
            "name": "VIX",
            "asset": "spx",
            "desc": "S&P 500 30-day implied vol",
        },
        "fred_vix3mcls": {
            "name": "VIX3M",
            "asset": "spx",
            "desc": "S&P 500 3-month implied vol",
        },
        "fred_vix9dcls": {
            "name": "VIX9D",
            "asset": "spx",
            "desc": "S&P 500 9-day implied vol",
        },
        "fred_vxvcls": {
            "name": "VXV",
            "asset": "spx",
            "desc": "S&P 500 3-month implied vol (CBOE VIX3M)",
        },
        # Commodity Vol
        "fred_ovxcls": {"name": "OVX", "asset": "oil", "desc": "Crude oil volatility"},
        "fred_gvzcls": {"name": "GVZ", "asset": "gold", "desc": "Gold volatility"},
        "fred_evzcls": {"name": "EVZ", "asset": "eur", "desc": "Euro FX volatility"},
        # EM/FX Vol
        "fred_vxeemcls": {
            "name": "VXEEM",
            "asset": "em",
            "desc": "Emerging markets vol",
        },
        "fred_vxfxicls": {
            "name": "VXFXI",
            "asset": "china",
            "desc": "China FXI volatility",
        },
    }

    # PATCHED 2026-02-02: Changed to continuous GARCH output
    SIGNAL_TYPE = "continuous"  # GARCH conditional variance z-score
    REGIME_LEVELS = [0, 1, 2, 3]  # For metadata only: Low, Normal, High, Crisis
    REGIME_LABELS = {0: "low", 1: "normal", 2: "high", 3: "crisis"}

    def __init__(self):
        config = SignalConfig(
            bucket="volatility",
            model_type="garch",  # PATCHED 2026-02-02: Restored to "garch" - outputs continuous variance
            primary_features=[
                "close",
                "returns_1d",
                # VIX TERM STRUCTURE - Active series only
                "fred_vixcls",  # VIX spot (30-day)
                "fred_vix3mcls",  # VIX 3-month (aliased from VXVCLS)
                "fred_vxvcls",  # VXVCLS raw (same as VIX3M)
                # COMMODITY VOL
                "fred_ovxcls",  # OVX (oil vol - energy spillover)
                "fred_gvzcls",  # GVZ (gold vol - safe haven)
            ],
            secondary_features=[
                # EM VOL (still active)
                "fred_vxeemcls",  # EM volatility
                # ELITE INDICATORS ON VIX (computed in _compute_elite_vol_indicators)
                "vix_rsi_14",  # VIX RSI
                "vix_zscore_21d",  # VIX z-score
                "vix_term_slope",  # VIX - VIX3M
                "realized_vs_implied",  # RV - IV spread
                # PRECIOUS METALS ETF (computed in _compute_elite_vol_indicators)
                "gld_momentum_21d",  # Gold ETF momentum (safe haven proxy)
                "slv_momentum_21d",  # Silver ETF momentum
                "gold_silver_ratio",  # GLD/SLV ratio (risk-on/off regime)
                "gold_silver_zscore",  # Z-score of ratio
                # NOTE: Discontinued series removed:
                # - fred_vix9dcls (VIX9D) - not available in FRED
                # - fred_evzcls (Euro FX vol) - discontinued March 2025
                # - fred_vxfxicls (China FXI vol) - discontinued Feb 2022
            ],
            lookback_days=504,  # 2 years for GARCH stability
            min_data_points=252,
        )
        super().__init__(config)
        self._vol_percentiles = None

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Require VIX term structure + commodity vol.

        NOTE: Only validates active series. Discontinued series are not required.
        """
        missing = []
        if "close" not in data.columns and "returns_1d" not in data.columns:
            missing.append("close_or_returns_1d")
        # REQUIRE VIX (core)
        if "fred_vixcls" not in data.columns:
            missing.append("fred_vixcls")
        # REQUIRE VIX term structure (either vix3mcls or vxvcls)
        if "fred_vix3mcls" not in data.columns and "fred_vxvcls" not in data.columns:
            missing.append("fred_vix3mcls_or_vxvcls")
        # REQUIRE commodity vol
        if "fred_ovxcls" not in data.columns:
            missing.append("fred_ovxcls")
        if "fred_gvzcls" not in data.columns:
            missing.append("fred_gvzcls")
        return missing

    def _compute_elite_vol_indicators(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """Compute elite technical indicators for volatility indices."""
        elite = {}

        if "fred_vixcls" in data.columns:
            vix = data["fred_vixcls"]

            # RSI-14 on VIX
            delta = vix.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss.replace(0, np.nan)
            elite["vix_rsi_14"] = 100 - (100 / (1 + rs))

            # Z-scores
            for window in [5, 21, 63]:
                mean = vix.rolling(window).mean()
                std = vix.rolling(window).std()
                elite[f"vix_zscore_{window}d"] = (vix - mean) / std.replace(0, np.nan)

            # VIX percentile rank
            elite["vix_percentile"] = vix.rolling(252).apply(
                lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
            )

        # Term structure slope
        if "fred_vixcls" in data.columns and "fred_vix3mcls" in data.columns:
            elite["vix_term_slope"] = data["fred_vixcls"] - data["fred_vix3mcls"]
            elite["vix_term_slope_zscore"] = self.compute_zscore(
                elite["vix_term_slope"], 63
            )

        # Vol of Vol
        if "fred_vxvcls" in data.columns:
            vvix = data["fred_vxvcls"]
            elite["vvix_zscore"] = self.compute_zscore(vvix, 63)

        # Realized vs Implied spread
        if "returns_1d" in data.columns and "fred_vixcls" in data.columns:
            realized_vol = data["returns_1d"].rolling(21).std() * np.sqrt(252) * 100
            elite["realized_vol_21d"] = realized_vol
            elite["rv_iv_spread"] = realized_vol - data["fred_vixcls"]

        # Precious Metals ETF indicators (GLD, SLV from mkt.etf_1d)
        # These are loaded separately and merged - check if available
        if "gld_close" in data.columns:
            gld = data["gld_close"]
            elite["gld_momentum_21d"] = (gld / gld.rolling(21).mean() - 1) * 100
            elite["gld_zscore_63d"] = self.compute_zscore(gld, 63)

        if "slv_close" in data.columns:
            slv = data["slv_close"]
            elite["slv_momentum_21d"] = (slv / slv.rolling(21).mean() - 1) * 100
            elite["slv_zscore_63d"] = self.compute_zscore(slv, 63)

        # Gold/Silver ratio (risk regime indicator)
        if "gld_close" in data.columns and "slv_close" in data.columns:
            gld = data["gld_close"]
            slv = data["slv_close"]
            gs_ratio = gld / slv.replace(0, np.nan)
            elite["gold_silver_ratio"] = gs_ratio
            elite["gold_silver_zscore"] = self.compute_zscore(gs_ratio, 63)

            # Ratio regime: high ratio = flight to quality (fear), low = risk-on
            # Historical range ~40-100, elevated >80 = fear, depressed <60 = greed
            elite["gold_silver_regime"] = pd.cut(
                gs_ratio,
                bins=[0, 55, 65, 75, 85, float("inf")],
                labels=[1, 2, 3, 4, 5],  # 1=extreme risk-on, 5=extreme fear
            ).astype(float)

        return elite

    def _compute_returns(self, data: pd.DataFrame) -> pd.Series:
        """Compute returns with no implicit forward-fill."""
        # Prefer raw close-to-close returns so we can enforce fill_method=None.
        if "close" in data.columns:
            returns = data["close"].pct_change(fill_method=None)
            outlier_mask = returns.abs() > MAX_ABS_DAILY_RETURN
            if outlier_mask.any():
                logger.warning(
                    "VOLATILITY_RETURN_OUTLIERS: masking %d returns with abs(ret) > %.2f",
                    int(outlier_mask.sum()),
                    MAX_ABS_DAILY_RETURN,
                )
                returns = returns.mask(outlier_mask)
            return returns
        elif "returns_1d" in data.columns:
            return data["returns_1d"]
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
                mean="Constant",
                vol="GARCH",
                p=1,
                o=1,
                q=1,  # o=1 for asymmetric term
                dist="t",
            )
            result = model.fit(disp="off", show_warning=False)
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
        # Use explicit raw-column priority to avoid matching derived indicator columns
        # (e.g., vix3m_autocorr_126d) after elite feature expansion.
        lower_to_original = {c.lower(): c for c in data.columns}

        vix_col = None
        for key in ("fred_vixcls", "vixcls"):
            if key in lower_to_original:
                vix_col = lower_to_original[key]
                break

        vix3m_col = None
        for key in (
            "fred_vix3mcls",
            "fred_vxvcls",
            "vix3mcls",
            "vxvcls",
            "vix3m",
            "vix_3m",
        ):
            if key in lower_to_original:
                vix3m_col = lower_to_original[key]
                break

        if vix_col is None or vix3m_col is None:
            # LOUD WARNING: Missing data should never silently become zeros
            missing = []
            if vix_col is None:
                missing.append("VIX (VIXCLS)")
            if vix3m_col is None:
                missing.append("VIX3M (VXVCLS)")
            logger.warning(
                f"MISSING_TERM_STRUCTURE_DATA: {', '.join(missing)} not found. "
                f"Available columns: {[c for c in data.columns if 'vix' in c.lower() or 'vxv' in c.lower()]}. "
                f"Term structure feature will return NaN, not zeros."
            )
            # Return NaN/NA, not zeros/False — those are data fabrication
            # pd.NA for boolean = "unknown", not "False" (which would imply contango)
            return (
                pd.Series(np.nan, index=data.index),  # term_slope
                pd.Series(
                    pd.NA, index=data.index, dtype="boolean"
                ),  # is_backwardation (unknown, not False)
                pd.Series(np.nan, index=data.index),  # term_zscore
                pd.Series(np.nan, index=data.index),  # term_slope_normalized
            )

        vix = data[vix_col]
        vix3m = data[vix3m_col]

        # Term structure slope: positive = backwardation (fear)
        term_slope = vix - vix3m

        # Normalized term slope as per plan: (VIX3M - VIX) / VIX
        # Positive = contango (normal), Negative = backwardation (stress)
        term_slope_normalized = (vix3m - vix) / vix.replace(0, np.nan)

        # Backwardation indicator (using unnormalized for clarity)
        is_backwardation = term_slope > 0

        # Z-score of term slope for magnitude
        term_zscore = self.compute_zscore(term_slope, window=252, min_periods=63)

        logger.info(f"   VIX term structure: using {vix_col} and {vix3m_col}")
        return term_slope, is_backwardation, term_zscore, term_slope_normalized

    def _validate_required_series(
        self, data: pd.DataFrame, min_recent_days: int = 5
    ) -> dict:
        """
        Validate required series are present and fresh.

        Data Contract:
        - VIXCLS: Required for VIX adjustment
        - VXVCLS: Required for term structure (via fred_vxvcls or fred_vix3mcls alias)

        Returns dict with validation status and any warnings.
        """
        issues = []
        warnings = []

        # Check for VIXCLS
        if "fred_vixcls" not in data.columns:
            issues.append("VIXCLS not in data columns")
        else:
            recent_vix = data["fred_vixcls"].iloc[-min_recent_days:].notna().sum()
            if recent_vix == 0:
                warnings.append(f"VIXCLS has no data in last {min_recent_days} days")

        # Check for VXVCLS (term structure)
        vxv_col = None
        for col in ["fred_vxvcls", "fred_vix3mcls"]:
            if col in data.columns:
                vxv_col = col
                break
        if vxv_col is None:
            warnings.append(
                "VXVCLS/VIX3M not in data columns - term structure will be NaN"
            )
        else:
            recent_vxv = data[vxv_col].iloc[-min_recent_days:].notna().sum()
            if recent_vxv == 0:
                warnings.append(f"{vxv_col} has no data in last {min_recent_days} days")

        # Log issues
        for issue in issues:
            logger.error(f"VOLATILITY_DATA_CONTRACT_VIOLATION: {issue}")
        for warn in warnings:
            logger.warning(f"VOLATILITY_DATA_FRESHNESS: {warn}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
        }

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute volatility regime signals with ALL elite indicators.

        Uses rolling realized volatility + GARCH conditional variance
        + VIX as exogenous regime indicator.

        PATCHED 2026-01-21: Added VIX term structure for improved panic detection
        PATCHED 2026-01-28: Added data contract validation to prevent silent failures
        """
        # Validate data contract before computing
        validation = self._validate_required_series(data)
        if not validation["valid"]:
            raise ValueError(
                f"Volatility specialist data contract violated: {validation['issues']}"
            )

        signals = []

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL AND ALL VOL INDICES
        # =====================================================================
        data = self.add_all_elite_indicators(data, "close", "zl")

        # Add elite indicators for all volatility indices
        for vol_col in [
            "fred_vixcls",
            "fred_vix3mcls",
            "fred_ovxcls",
            "fred_gvzcls",
            "fred_vxvcls",
            "fred_vxeemcls",
            "fred_vxfxicls",
            "fred_evzcls",
        ]:
            if vol_col in data.columns and data[vol_col].notna().sum() > 30:
                vol_data = data.copy()
                vol_data["close"] = data[vol_col]
                prefix = vol_col.replace("fred_", "").replace("cls", "")
                vol_data = self.add_all_elite_indicators(vol_data, "close", prefix)
                for c in vol_data.columns:
                    if c.startswith(f"{prefix}_") and c not in data.columns:
                        data[c] = vol_data[c]

        # Compute elite vol indicators
        elite_vol = self._compute_elite_vol_indicators(data)
        for col_name, series in elite_vol.items():
            data[col_name] = series

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
        term_slope, is_backwardation, term_zscore, term_slope_normalized = (
            self._compute_vix_term_structure(data)
        )
        has_term_structure = term_slope.notna().any()

        # Term structure adjustment: backwardation adds to fear signal
        term_adjustment = pd.Series(0.0, index=data.index)
        if has_term_structure:
            # Backwardation (positive slope) = fear = add to regime
            # Strong backwardation (>2 pts) = significant
            term_adjustment = 0.25 * term_zscore.clip(-2, 2)
            logger.info(
                f"   VIX term structure active: {is_backwardation.sum()} backwardation days"
            )

        # Regime change probability (based on vol velocity + term structure shifts)
        # NO FILLNA - if data is missing, velocity is NaN (not zero)
        vol_velocity = vol_zscore.diff(5)  # 5-day change in vol regime

        # Combine velocities only where both are available
        if has_term_structure:
            term_velocity = term_zscore.diff(5)
            # Only add term velocity where it's valid
            combined_velocity = vol_velocity.copy()
            valid_term = term_velocity.notna()
            combined_velocity.loc[valid_term] = (
                vol_velocity.loc[valid_term].fillna(0)
                + 0.3 * term_velocity.loc[valid_term]
            )
        else:
            combined_velocity = vol_velocity

        regime_change_prob = (np.abs(combined_velocity) / 2).clip(0, 1)

        # Fit GARCH for conditional variance - THIS IS THE CORE MODEL
        garch_result = None
        garch_cond_vol = None  # Series of GARCH conditional volatility
        garch_cond_vol_zscore = None  # Z-score of conditional volatility

        if ARCH_AVAILABLE and len(returns.dropna()) >= 504:
            # Fit on recent 2 years
            recent_returns = returns.iloc[-504:]
            garch_result = self._fit_garch(recent_returns)

            # PATCHED 2026-02-02: Extract GARCH conditional variance for signal_1
            if garch_result is not None:
                try:
                    # Get conditional volatility (sqrt of variance)
                    # Scale back from percentage returns (we multiplied by 100 in _fit_garch)
                    cond_vol = (
                        garch_result.conditional_volatility / 100
                    )  # Back to decimal

                    # Align with data index (GARCH was fit on recent 504 days)
                    garch_cond_vol = pd.Series(np.nan, index=data.index)
                    aligned_idx = recent_returns.dropna().index[-len(cond_vol) :]
                    garch_cond_vol.loc[aligned_idx] = cond_vol.values

                    # No forward-fill (policy) - leave gaps outside training window

                    # Z-score the conditional volatility (rolling 252-day window)
                    garch_cond_vol_zscore = self.compute_zscore(
                        garch_cond_vol, window=252, min_periods=126
                    )

                    logger.info(
                        f"   GARCH conditional vol: mean={garch_cond_vol.mean():.6f}, "
                        f"std={garch_cond_vol.std():.6f}, non-null={garch_cond_vol.notna().sum()}"
                    )
                except Exception as e:
                    logger.warning(
                        f"   Failed to extract GARCH conditional variance: {e}"
                    )
                    garch_cond_vol = None
                    garch_cond_vol_zscore = None

        for idx in data.index:
            # Skip non-trading/null-price rows to avoid fabricating daily signals.
            if "close" in data.columns and pd.isna(data.loc[idx, "close"]):
                continue

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
            change_prob = (
                regime_change_prob.loc[idx]
                if not pd.isna(regime_change_prob.loc[idx])
                else 0.0
            )

            # Confidence based on data quality
            confidence = 0.7
            if "fred_vixcls" in data.columns and not pd.isna(
                data.loc[idx, "fred_vixcls"]
            ):
                confidence += 0.1
            if has_term_structure:
                confidence += 0.05  # Boost for term structure data
            if garch_result is not None:
                confidence += 0.05

            # PATCHED 2026-02-02: signal_1 is now CONTINUOUS GARCH variance z-score
            # Prefer GARCH conditional variance, fallback to realized vol z-score
            if garch_cond_vol_zscore is not None and not pd.isna(
                garch_cond_vol_zscore.loc[idx]
            ):
                signal_1_value = float(garch_cond_vol_zscore.loc[idx])
                signal_source = "garch_conditional_variance"
            else:
                # Fallback: use combined z-score (realized vol + VIX adjustments)
                signal_1_value = float(combined_zscore)
                signal_source = "realized_vol_zscore"

            # Build metadata - regime is now metadata only, not signal_1
            meta = {
                "signal_type": self.SIGNAL_TYPE,  # "continuous"
                "signal_source": signal_source,
                # Regime classification in metadata (for reference)
                "regime_state": regime_level,
                "regime_label": self.REGIME_LABELS[regime_level],
                # Volatility components
                "vol_zscore": float(combined_zscore),
                "realized_vol": float(realized_vol.loc[idx])
                if not pd.isna(realized_vol.loc[idx])
                else None,
                "garch_cond_vol": float(garch_cond_vol.loc[idx])
                if garch_cond_vol is not None and not pd.isna(garch_cond_vol.loc[idx])
                else None,
                "garch_fitted": garch_result is not None,
                "run_hash": run_hash,
            }

            # Add term structure metadata if available
            if has_term_structure:
                meta["vix_term_slope"] = (
                    float(term_slope.loc[idx])
                    if not pd.isna(term_slope.loc[idx])
                    else None
                )
                meta["vix_term_slope_normalized"] = (
                    float(term_slope_normalized.loc[idx])
                    if not pd.isna(term_slope_normalized.loc[idx])
                    else None
                )
                meta["is_backwardation"] = bool(is_backwardation.loc[idx])

            as_of = idx.date() if hasattr(idx, "date") else idx
            # P0-3: Skip dates before EARLIEST_VALID_DATE
            if as_of < date(1990, 1, 1):
                continue

            # P0-1: Compute max staleness for this date
            max_staleness = self.compute_max_staleness(data, as_of)

            signals.append(
                SignalOutput(
                    as_of_date=as_of,
                    bucket="volatility",
                    signal_1=signal_1_value,  # CONTINUOUS: GARCH cond vol z-score or realized vol z-score
                    signal_2=float(change_prob),  # Regime transition probability
                    confidence=float(min(confidence, 0.95)),
                    model_type="garch",  # PATCHED 2026-02-02: Restored to "garch"
                    max_input_age_days=max_staleness,  # P0-1: Staleness tracking
                    metadata=meta,
                )
            )

        # Operational metrics for data quality monitoring
        term_nan_count = (
            term_slope.isna().sum() if term_slope is not None else len(data)
        )
        term_nan_pct = (term_nan_count / len(data) * 100) if len(data) > 0 else 0
        (is_backwardation.isna().sum() if is_backwardation is not None else len(data))

        if term_nan_pct > 10:
            logger.warning(
                f"VOLATILITY_DATA_QUALITY: term_structure NaN rate = {term_nan_pct:.1f}% "
                f"({term_nan_count}/{len(data)}). Check VIXCLS/VXVCLS freshness."
            )

        # Count GARCH vs fallback signals
        garch_signal_count = sum(
            1
            for s in signals
            if s.metadata
            and s.metadata.get("signal_source") == "garch_conditional_variance"
        )

        logger.info(
            f"VolatilitySignalGenerator: Generated {len(signals)} signals "
            f"(GARCH: {garch_signal_count}, fallback: {len(signals) - garch_signal_count}, "
            f"term_structure: {has_term_structure})"
        )
        return signals
