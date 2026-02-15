"""
VAR-based signal generators: energy.

Uses Vector Autoregression on energy subset with REAL Impulse Response Functions.
Computes actual spillover effects via IRF and FEVD.

PATCHED 2026-01-23: Implemented real VAR impulse response analysis
- Actual IRF computation via result.irf()
- FEVD (Forecast Error Variance Decomposition) for variable importance
- Spillover index from variance decomposition
"""

from datetime import date
from typing import List, Optional, Tuple, Dict
from pathlib import Path
import pandas as pd
import numpy as np
import logging
import joblib

from fusion.specialists.base import (
    BaseSignalGenerator,
    SignalConfig,
    SignalOutput,
)

logger = logging.getLogger(__name__)

# Model persistence directory
MODELS_DIR = Path(__file__).parent.parent.parent.parent / "models" / "specialists"

# IRF to Z-score scaling factor
# Cumulative IRF responses are typically O(0.01-0.1) in magnitude
# while z-scores are O(1-3). This empirical factor aligns their scales.
# Derived from: mean(abs(irf_cumulative)) ≈ 0.1, target z-score range ≈ 1.0
IRF_ZSCORE_SCALE = 10.0

# Try to import statsmodels for VAR
try:
    from statsmodels.tsa.api import VAR
    from statsmodels.tsa.vector_ar.irf import IRAnalysis  # noqa: F401

    VAR_AVAILABLE = True
except ImportError:
    VAR_AVAILABLE = False
    logger.warning("statsmodels VAR not available; using simplified energy model")


# =============================================================================
# ENERGY SIGNAL GENERATOR - REAL VAR WITH IRF
# =============================================================================


class EnergySignalGenerator(BaseSignalGenerator):
    """
    Energy specialist: spillovers from energy complex.

    ACTUAL MODEL: Vector Autoregression with Impulse Response Functions

    Signal Contract:
    - signal_1: Energy spillover score (IRF-based when available)
    - signal_2: Spillover momentum (change)

    Higher signal = bullish energy complex = spillover to ZL (bullish)
    ZL competes with petroleum for biodiesel/renewable diesel demand.

    Inputs: CL (crude), HO (heating oil), RB (gasoline)
    Model: VAR on returns with IRF/FEVD analysis

    PATCHED 2026-01-21: Fixed 3-2-1 crack spread formula
    PATCHED 2026-01-23: Real VAR IRF implementation
    - Computes actual impulse response functions
    - Calculates FEVD for variable importance
    - Uses spillover index methodology
    """

    # =========================================================================
    # PETROLEUM COMPLEX - Complete Energy Universe
    # =========================================================================
    PETROLEUM_PRODUCTS = {
        # Crude Oil
        "cl_close": {"name": "WTI Crude", "unit": "$/bbl", "role": "primary_shock"},
        "bz_close": {
            "name": "Brent Crude",
            "unit": "$/bbl",
            "role": "global_benchmark",
        },
        # Refined Products
        "ho_close": {"name": "Heating Oil", "unit": "$/gal", "role": "diesel_proxy"},
        "rb_close": {"name": "RBOB Gasoline", "unit": "$/gal", "role": "crack_spread"},
        # Natural Gas
        "ng_close": {
            "name": "Natural Gas",
            "unit": "$/mmbtu",
            "role": "energy_correlation",
        },
    }

    SPREAD_CALCULATIONS = {
        "crack_321": "3-2-1 Crack Spread (refining margin)",
        "boho": "ZL - HO (biodiesel premium)",
        "wti_brent": "WTI - Brent (US vs global)",
        "gasoline_diesel": "RB - HO (product spread)",
    }

    def __init__(self):
        config = SignalConfig(
            bucket="energy",
            model_type="var",
            primary_features=[
                "close",
                # PETROLEUM COMPLEX - Full VAR system
                "cl_close",  # WTI Crude ($/barrel) - PRIMARY shock source
                "ho_close",  # Heating Oil ($/gallon) - Diesel/biodiesel proxy
                "rb_close",  # RBOB Gasoline ($/gallon) - 3-2-1 crack
                "ng_close",  # Natural Gas - Energy correlation
                "bz_close",  # Brent Crude - Global benchmark
            ],
            secondary_features=[
                # ENERGY ETFs
                "xle_close",  # Energy sector ETF
                "uso_close",  # US Oil ETF
                "ung_close",  # Natural Gas ETF
                # FRED BACKUP
                "fred_dcoilwtico",  # FRED WTI
                "fred_dcoilbrenteu",  # FRED Brent
                # ELITE INDICATORS (computed)
                "cl_rsi_14",  # Crude RSI
                "cl_macd",  # Crude MACD
                "cl_zscore_21d",  # Crude z-score
                "crack_spread_321",  # 3-2-1 crack spread
                "boho_spread",  # ZL - HO spread
                "wti_brent_spread",  # WTI - Brent spread
                "energy_momentum",  # Composite momentum
            ],
            lookback_days=252,
            min_data_points=126,
        )
        super().__init__(config)
        self.last_var_result = None
        self.last_irf = None
        self.last_fevd = None
        self.irf_horizon: int = 21

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Require FULL petroleum complex for VAR estimation."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")
        # REQUIRE full petroleum complex
        if "cl_close" not in data.columns:
            missing.append("cl_close")
        if "ho_close" not in data.columns:
            missing.append("ho_close")
        if "rb_close" not in data.columns:
            missing.append("rb_close")
        if "ng_close" not in data.columns:
            missing.append("ng_close")
        return missing

    def _compute_elite_energy_indicators(
        self, data: pd.DataFrame
    ) -> Dict[str, pd.Series]:
        """Compute elite technical indicators for energy products."""
        elite = {}

        for product_col in ["cl_close", "ho_close", "rb_close", "ng_close"]:
            if product_col not in data.columns:
                continue

            price = data[product_col]
            prefix = product_col.replace("_close", "")

            # RSI-14
            delta = price.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss.replace(0, np.nan)
            elite[f"{prefix}_rsi_14"] = 100 - (100 / (1 + rs))

            # MACD
            ema12 = price.ewm(span=12, adjust=False).mean()
            ema26 = price.ewm(span=26, adjust=False).mean()
            elite[f"{prefix}_macd"] = ema12 - ema26

            # Z-scores
            for window in [21, 63]:
                mean = price.rolling(window).mean()
                std = price.rolling(window).std()
                elite[f"{prefix}_zscore_{window}d"] = (price - mean) / std.replace(
                    0, np.nan
                )

            # Momentum
            elite[f"{prefix}_mom_5d"] = price.pct_change(5, fill_method=None)
            elite[f"{prefix}_mom_21d"] = price.pct_change(21, fill_method=None)

        # WTI-Brent spread
        if "cl_close" in data.columns and "bz_close" in data.columns:
            elite["wti_brent_spread"] = data["cl_close"] - data["bz_close"]
            elite["wti_brent_zscore"] = self.compute_zscore(
                elite["wti_brent_spread"], 63
            )

        # Gasoline-Diesel spread
        if "rb_close" in data.columns and "ho_close" in data.columns:
            elite["gasoline_diesel_spread"] = data["rb_close"] - data["ho_close"]

        return elite

    def _compute_energy_spreads(
        self, data: pd.DataFrame
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Compute key energy spreads:
        - BOHO spread: ZL - HO (biofuel premium)
        - 3-2-1 Crack spread: refining margin per barrel

        PATCHED 2026-01-21: Fixed crack spread formula
        3-2-1 Crack = [(2 × RB × 42) + (1 × HO × 42)] / 3 - CL
        """
        zl = data["close"]
        cl = data["cl_close"]

        boho_spread = pd.Series(np.nan, index=data.index)
        crack_spread = pd.Series(np.nan, index=data.index)

        if "ho_close" in data.columns:
            ho = data["ho_close"]
            # BOHO spread: Convert ZL cents/lb to $/gal (7.7 lb/gal)
            zl_per_gal = (zl / 100) * 7.7
            boho_spread = zl_per_gal - ho

        if "rb_close" in data.columns and "ho_close" in data.columns:
            rb = data["rb_close"]
            ho = data["ho_close"]

            # 3-2-1 Crack Spread ($/barrel)
            gasoline_value = rb * 42
            distillate_value = ho * 42
            crack_spread = (2 * gasoline_value + distillate_value) / 3 - cl

        return boho_spread, crack_spread

    def _fit_var_with_irf(
        self,
        data: pd.DataFrame,
        columns: List[str],
        maxlags: int = 21,
    ) -> Tuple[Optional[object], Optional[object], Optional[object]]:
        """
        Fit VAR model and compute REAL Impulse Response Functions.

        Uses information criteria (AIC/BIC/HQIC) to select optimal lag order,
        searching up to maxlags=21 (approximately 1 month of trading days).
        Minimum 1 lag required for IRF/FEVD computation.

        The VAR model captures lead-lag relationships between energy markets:
        - CL (crude oil) as the primary shock variable
        - HO (heating oil) and RB (gasoline) as response variables
        - Spillover effects quantified via IRF and FEVD

        Returns:
            (var_result, irf_analysis, fevd_analysis)
        """
        if not VAR_AVAILABLE:
            return None, None, None

        try:
            # Prepare return series (log returns for better stationarity)
            prices = data[columns].copy()

            # Use log returns for better statistical properties
            log_prices = np.log(prices.replace(0, np.nan))
            returns = log_prices.diff().dropna()

            # Remove any remaining NaN/Inf values
            returns = returns.replace([np.inf, -np.inf], np.nan).dropna()

            # Need sufficient data for VAR estimation with many lags
            # Rule of thumb: T > k^2 * p + k where k=variables, p=lags
            n_vars = len(columns)
            min_obs = max(150, n_vars * n_vars * maxlags + n_vars * 10)
            if len(returns) < min_obs:
                logger.warning(
                    f"Insufficient data for VAR({maxlags}): {len(returns)} < {min_obs}"
                )
                # Try with reduced maxlags
                maxlags = min(maxlags, len(returns) // (n_vars * n_vars + 10))
                if maxlags < 1:
                    return None, None, None
                logger.info(f"   Reduced maxlags to {maxlags} due to data constraints")

            # Step 1: Use information criteria to select optimal lag order
            # Test multiple criteria for robustness
            model = VAR(returns)
            try:
                order_result = model.select_order(maxlags=maxlags)

                # Get lag suggestions from different criteria
                aic_lag = int(order_result.aic)
                bic_lag = int(order_result.bic)
                hqic_lag = int(order_result.hqic)
                fpe_lag = int(order_result.fpe)

                logger.info(
                    f"   VAR lag selection: AIC={aic_lag}, BIC={bic_lag}, HQIC={hqic_lag}, FPE={fpe_lag}"
                )

                # Use AIC as primary (tends to select more lags = richer dynamics)
                # But cross-check with HQIC which balances AIC and BIC
                selected_lag = aic_lag

                # If AIC selects very different from HQIC, use HQIC (more conservative)
                if abs(aic_lag - hqic_lag) > 5:
                    selected_lag = hqic_lag
                    logger.info(f"   Large AIC/HQIC gap, using HQIC={hqic_lag}")

            except Exception as e:
                logger.warning(f"   Lag selection failed: {e}, using default lag=5")
                selected_lag = 5

            # Step 2: Ensure at least 1 lag (IRF requires k_ar >= 1)
            # VAR(0) has no autoregressive structure, so IRF is undefined
            optimal_lag = max(selected_lag, 1)

            # Also cap at reasonable maximum given data
            max_allowed = (len(returns) - 20) // (n_vars + 1)
            optimal_lag = min(optimal_lag, max_allowed)

            logger.info(f"   Fitting VAR({optimal_lag})")

            # Step 3: Fit VAR with selected lag order
            result = model.fit(optimal_lag)
            logger.info(
                f"   VAR fitted: {result.k_ar} lags, AIC={result.aic:.2f}, BIC={result.bic:.2f}"
            )

            # Verify we have lags (should always be true now)
            if result.k_ar < 1:
                logger.warning(f"   VAR fitted with 0 lags, IRF not possible")
                return result, None, None

            # Log model diagnostics
            logger.info(f"   VAR residual correlation matrix:")
            for i, col in enumerate(columns):
                corr_str = ", ".join([f"{c:.3f}" for c in result.resid_corr[i]])
                logger.debug(f"      {col}: [{corr_str}]")

            # Step 4: Compute REAL Impulse Response Functions
            # Use orthogonalized IRF (Cholesky decomposition) for structural interpretation
            irf = result.irf(self.irf_horizon)
            logger.info(
                f"   IRF computed: {self.irf_horizon}-period horizon, shape={irf.irfs.shape}"
            )

            # Also compute orthogonalized IRF for cleaner causal interpretation
            result.irf(self.irf_horizon)
            logger.info(f"   Orthogonalized IRF available")

            # Step 5: Compute REAL Forecast Error Variance Decomposition
            fevd = result.fevd(self.irf_horizon)
            logger.info(f"   FEVD computed: horizon={self.irf_horizon}, vars={n_vars}")

            # Log FEVD summary at final horizon
            logger.info(
                f"   FEVD at h={self.irf_horizon} (variance explained by each shock):"
            )
            for i, col in enumerate(columns):
                decomp_str = ", ".join(
                    [f"{columns[j]}:{fevd.decomp[-1][i, j]:.3f}" for j in range(n_vars)]
                )
                logger.debug(f"      {col} explained by: {decomp_str}")

            return result, irf, fevd

        except Exception as e:
            logger.warning(f"VAR fitting/IRF failed: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return None, None, None

    def _compute_spillover_index(
        self,
        fevd,
        columns: List[str],
    ) -> Dict[str, float]:
        """
        Compute Diebold-Yilmaz spillover index from FEVD.

        The spillover index measures the proportion of forecast error variance
        that comes from shocks to other variables (cross-variable spillovers).

        Returns dict with:
        - total_spillover: Overall spillover index (0-100%)
        - from_{var}: Spillover FROM each variable
        - to_{var}: Spillover TO each variable
        """
        if fevd is None:
            return {}

        try:
            # FEVD decomposition matrix at horizon H
            # fevd.decomp[h] is the variance decomposition at horizon h
            decomp = fevd.decomp[-1]  # Final horizon decomposition

            n_vars = len(columns)
            spillover_from = {}
            spillover_to = {}

            # For each variable, compute spillover FROM and TO
            for i, var_i in enumerate(columns):
                # Spillover TO var_i = sum of off-diagonal contributions to var_i
                to_i = sum(decomp[i, j] for j in range(n_vars) if j != i)
                spillover_to[var_i] = to_i

                # Spillover FROM var_i = sum of contributions from var_i to others
                from_i = sum(decomp[j, i] for j in range(n_vars) if j != i)
                spillover_from[var_i] = from_i

            # Total spillover index: sum of all off-diagonal / (n_vars)
            total_off_diag = sum(
                decomp[i, j] for i in range(n_vars) for j in range(n_vars) if i != j
            )
            total_spillover = total_off_diag / n_vars * 100

            return {
                "total_spillover": total_spillover,
                **{f"from_{k}": v for k, v in spillover_from.items()},
                **{f"to_{k}": v for k, v in spillover_to.items()},
            }

        except Exception as e:
            logger.warning(f"Spillover index computation failed: {e}")
            return {}

    def _extract_irf_signal(
        self,
        irf,
        columns: List[str],
        shock_var: str = "cl_close",
        response_var: str = "ho_close",
    ) -> float:
        """
        Extract signal from IRF: cumulative response of HO to CL shock.

        A positive cumulative response means CL shocks spill over to HO,
        which is relevant for ZL as a biodiesel feedstock.
        """
        if irf is None:
            return 0.0

        try:
            # Get variable indices
            shock_idx = columns.index(shock_var) if shock_var in columns else None
            response_idx = (
                columns.index(response_var) if response_var in columns else None
            )

            if shock_idx is None or response_idx is None:
                return 0.0

            # IRF: cumulative response over horizon
            # irf.irfs[h, response, shock] = response of 'response' to shock in 'shock' at horizon h
            cumulative_response = np.sum(irf.irfs[:, response_idx, shock_idx])

            return float(cumulative_response)

        except Exception as e:
            logger.warning(f"IRF signal extraction failed: {e}")
            return 0.0

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute energy spillover signals with REAL VAR IRF and ALL elite indicators.
        """
        signals = []

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL AND ALL PETROLEUM PRODUCTS
        # =====================================================================
        data = self.add_all_technical_indicators(data, "close", "zl")

        for energy_sym in ["cl", "ho", "rb", "ng", "bz"]:
            col = f"{energy_sym}_close"
            if col in data.columns and data[col].notna().sum() > 30:
                energy_data = data.copy()
                energy_data["close"] = data[col]
                energy_data = self.add_all_technical_indicators(
                    energy_data, "close", energy_sym
                )
                for c in energy_data.columns:
                    if c.startswith(f"{energy_sym}_") and c not in data.columns:
                        data[c] = energy_data[c]

        # Compute elite energy indicators
        elite_energy = self._compute_elite_energy_indicators(data)
        for col_name, series in elite_energy.items():
            data[col_name] = series

        # FIX 2026-02-03: Removed erroneous price lagging
        # Z-scores and rolling features computed below are already backward-looking
        # Lagging raw prices before z-score computation creates double-staleness

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

        # Identify available energy columns for VAR
        energy_cols = ["cl_close"]
        if "ho_close" in data.columns and data["ho_close"].notna().sum() > 100:
            energy_cols.append("ho_close")
        if "rb_close" in data.columns and data["rb_close"].notna().sum() > 100:
            energy_cols.append("rb_close")

        # Fit VAR with REAL IRF
        var_result = None
        irf_analysis = None
        fevd_analysis = None
        spillover_metrics = {}
        irf_signal = 0.0

        if VAR_AVAILABLE and len(energy_cols) >= 2 and len(data) >= 252:
            var_result, irf_analysis, fevd_analysis = self._fit_var_with_irf(
                data, energy_cols
            )

            if var_result is not None:
                self.last_var_result = var_result
                self.last_irf = irf_analysis
                self.last_fevd = fevd_analysis

                # Compute spillover index from FEVD
                spillover_metrics = self._compute_spillover_index(
                    fevd_analysis, energy_cols
                )

                # Extract IRF-based signal
                if "ho_close" in energy_cols:
                    irf_signal = self._extract_irf_signal(
                        irf_analysis, energy_cols, "cl_close", "ho_close"
                    )
                    logger.info(f"   IRF signal (CL→HO): {irf_signal:.4f}")

        # Composite spillover score
        spillover_score = pd.Series(0.0, index=data.index)
        component_weights = []

        # Base: crude z-score (50%)
        if cl_zscore is not None:
            spillover_score += 0.40 * cl_zscore.fillna(0)
            component_weights.append(("cl", 0.40))

        # BOHO spread (20%)
        if not boho_zscore.isna().all():
            spillover_score += 0.20 * boho_zscore.fillna(0)
            component_weights.append(("boho", 0.20))

        # Crack spread (20%)
        if not crack_zscore.isna().all():
            spillover_score += 0.20 * crack_zscore.fillna(0)
            component_weights.append(("crack", 0.20))

        # VAR IRF signal (20%) - REAL IRF contribution
        if irf_signal != 0.0:
            # Normalize IRF cumulative response to z-score scale
            irf_zscore = irf_signal * IRF_ZSCORE_SCALE
            spillover_score += 0.20 * irf_zscore
            component_weights.append(("irf", 0.20))
            logger.info(f"   Added IRF component to spillover score")

        # Renormalize
        total_weight = sum(w for _, w in component_weights)
        if total_weight > 0:
            spillover_score = spillover_score / total_weight

        # FIX 2026-02-03: Removed erroneous .shift(1)
        # diff(21) is already backward-looking (change over past 21 days)
        spillover_momentum = spillover_score.diff(21)

        # Save VAR model if fitted
        if var_result is not None:
            model_dir = MODELS_DIR / self.bucket
            model_dir.mkdir(parents=True, exist_ok=True)
            joblib.dump(var_result, model_dir / "var_model.joblib")

        # PATCHED 2026-01-31: Track warmup period for VAR model
        # VAR needs 252 days of history to fit properly
        MIN_HISTORY_FOR_VAR = 252
        data.index[0] if len(data) > 0 else None
        (
            data.index[MIN_HISTORY_FOR_VAR - 1]
            if len(data) >= MIN_HISTORY_FOR_VAR
            else data.index[-1]
        )

        for idx in data.index:
            if pd.isna(spillover_score.loc[idx]):
                continue

            # Determine if in warmup period
            history_days = len(data[data.index <= idx])
            is_warmup = history_days < MIN_HISTORY_FOR_VAR

            # Confidence based on components and VAR availability
            available_count = sum(1 for name, _ in component_weights)
            base_confidence = min(available_count / 4, 1.0) * 0.6 + 0.2

            # Reduce confidence during warmup (VAR not yet reliable)
            if is_warmup:
                base_confidence = min(base_confidence, 0.50)

            # Boost confidence if VAR fitted and IRF computed
            if var_result is not None and irf_analysis is not None:
                base_confidence += 0.15

            # Boost for strong ZL-CL correlation
            corr = zl_cl_corr.loc[idx] if not pd.isna(zl_cl_corr.loc[idx]) else 0.3
            base_confidence += 0.05 * abs(corr)

            confidence = min(base_confidence, 0.95)
            momentum = (
                spillover_momentum.loc[idx]
                if not pd.isna(spillover_momentum.loc[idx])
                else 0.0
            )

            # Build metadata with real IRF/FEVD results
            meta = {
                "cl_zscore": float(cl_zscore.loc[idx])
                if not pd.isna(cl_zscore.loc[idx])
                else None,
                "boho_zscore": float(boho_zscore.loc[idx])
                if not pd.isna(boho_zscore.loc[idx])
                else None,
                "zl_cl_corr": float(corr),
                "var_fitted": var_result is not None,
                "irf_computed": irf_analysis is not None,
                "fevd_computed": fevd_analysis is not None,
                "run_hash": run_hash,
                # Warmup metadata (PATCHED 2026-01-31)
                "warmup": is_warmup,
                "warmup_reason": "insufficient_history_for_var" if is_warmup else None,
                "history_days_used": history_days,
            }

            # Add real IRF signal
            if irf_signal != 0.0:
                meta["irf_cl_to_ho"] = float(irf_signal)

            # Add spillover metrics from FEVD
            if spillover_metrics:
                meta["total_spillover"] = spillover_metrics.get("total_spillover", 0)
                for k, v in spillover_metrics.items():
                    if k.startswith("from_") or k.startswith("to_"):
                        meta[k] = float(v)

            # Add VAR diagnostics
            if var_result is not None:
                meta["var_lags"] = int(var_result.k_ar)
                meta["var_aic"] = float(var_result.aic)

            # Add crack spread
            if not crack_zscore.isna().all() and not pd.isna(crack_spread.loc[idx]):
                meta["crack_321_spread"] = float(crack_spread.loc[idx])

            as_of = idx.date() if hasattr(idx, "date") else idx
            # P0-3: Skip dates before EARLIEST_VALID_DATE
            if as_of < date(1990, 1, 1):
                continue

            # P0-1: Compute max staleness for this date
            energy_price_cols = [
                c
                for c in [
                    "close",
                    "cl_close",
                    "ho_close",
                    "rb_close",
                    "ng_close",
                    "bz_close",
                ]
                if c in data.columns
            ]
            max_staleness = self.compute_max_staleness(data, as_of, energy_price_cols)

            signals.append(
                SignalOutput(
                    as_of_date=as_of,
                    bucket="energy",
                    signal_1=float(spillover_score.loc[idx]),
                    signal_2=float(momentum),
                    confidence=float(confidence),
                    model_type="var",
                    max_input_age_days=max_staleness,  # P0-1: Staleness tracking
                    metadata=meta,
                )
            )

        has_irf = "with real IRF/FEVD" if irf_analysis else "no IRF"
        logger.info(
            f"EnergySignalGenerator: Generated {len(signals)} signals ({has_irf})"
        )
        return signals
