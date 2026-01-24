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

from datetime import date
from typing import List, Optional, Dict, Tuple
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

# Try to import statsmodels for ARDL
try:
    from statsmodels.tsa.ardl import ARDL
    from statsmodels.tsa.stattools import adfuller, kpss
    from statsmodels.regression.linear_model import OLS
    import statsmodels.api as sm
    ARDL_AVAILABLE = True
except ImportError:
    ARDL_AVAILABLE = False
    logger.warning("statsmodels ARDL not available; using simplified FX model")


# =============================================================================
# FX SIGNAL GENERATOR - REAL ARDL WITH CARRY TRADE
# =============================================================================

class FxSignalGenerator(BaseSignalGenerator):
    """
    FX specialist: currency pressure on export competitiveness.

    ACTUAL MODEL: Autoregressive Distributed Lag (ARDL) model

    Signal Contract:
    - signal_1: FX pressure index (ARDL-based when available)
    - signal_2: Carry trade signal (interest rate differentials)

    Higher signal = stronger USD = bearish for US ag exports (bearish ZL)
    Lower signal = weaker USD = bullish for exports (bullish ZL)

    Inputs: DXY, major ag-relevant FX pairs, interest rates
    Model: ARDL on ZL returns ~ FX changes with optimal lag selection

    PATCHED 2026-01-23: Real ARDL implementation
    - Optimal lag selection via AIC/BIC
    - Dynamic weights from rolling ZL correlation
    - Carry trade signal from rate differentials
    - Trade-weighted effective exchange rate
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
                # Interest rates for carry trade
                "fred_fedfunds",  # US Fed Funds
                "fred_dgs2",      # US 2Y
                # Foreign interest rates (dynamic when available)
                "fred_ir3tib01cnm156n",  # China 3M interbank rate
            ],
            lookback_days=2520,   # 10 years of historical data for deep context
            min_data_points=756,   # Minimum 3 years of data required for robust estimation
        )
        super().__init__(config)

        # Base trade weights for FX pairs (from USDA export data)
        # These are starting points, dynamically adjusted by correlation
        self.base_trade_weights = {
            "fred_dexbzus": 0.30,   # Brazil - #1 soy competitor
            "fred_dexchus": 0.35,   # China - #1 importer
            "fred_dxy": 0.15,       # Broad dollar benchmark
            "fred_dexmxus": 0.12,   # Mexico - USMCA partner
            "fred_dexusal": 0.08,   # Australia - competitor
        }

        # Foreign interest rate columns (dynamic rates from FRED when available)
        # Maps country -> FRED column name in DataFrame
        self.foreign_rate_columns = {
            "china": "fred_ir3tib01cnm156n",  # China 3M interbank rate
            # Note: Brazil/Mexico/Australia rates require dynamic series columns
        }

        self.ardl_model = None
        self.dynamic_weights = None
        self.ardl_lags = 5  # Default ARDL lags
        self.correlation_window = 504   # 2-year rolling correlation for stable dynamic weights
        self.zscore_window = 1260       # 5-year z-score normalization for deep context

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Need at least one FX indicator."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")

        # Check for at least one FX series
        available_fx = [col for col in self.base_trade_weights.keys() if col in data.columns]
        if not available_fx:
            missing.append("at_least_one_fx_pair")
        return missing

    def _compute_dynamic_weights(
        self,
        data: pd.DataFrame,
    ) -> Dict[str, pd.Series]:
        """
        Compute dynamic FX weights based on rolling correlation with ZL.

        Base trade weights are adjusted by how well each currency explains
        ZL movements over the rolling window.

        Returns:
            Dict mapping FX column to time series of weights
        """
        zl = data["close"]
        zl_returns = zl.pct_change(fill_method=None)

        dynamic_weights = {}
        available_fx = [col for col in self.base_trade_weights.keys() if col in data.columns]

        if not available_fx:
            return {}

        # Compute rolling correlations
        correlations = {}
        for col in available_fx:
            fx_series = data[col]
            # Invert if needed (DXY is already USD strength)
            if col != "fred_dxy":
                fx_returns = (1 / fx_series).pct_change(fill_method=None)
            else:
                fx_returns = fx_series.pct_change(fill_method=None)

            # Rolling correlation with ZL
            rolling_corr = zl_returns.rolling(self.correlation_window).corr(fx_returns)
            correlations[col] = rolling_corr.abs()  # Use absolute correlation

        # Convert to weights: correlation-weighted trade importance
        # Higher abs correlation = more relevant for ZL
        for col in available_fx:
            base_weight = self.base_trade_weights[col]

            # Correlation-adjusted weight: base * (1 + corr_zscore)
            corr_zscore = (correlations[col] - correlations[col].rolling(252).mean()) / correlations[col].rolling(252).std().replace(0, 1)
            corr_zscore = corr_zscore.clip(-2, 2)  # Limit extremes

            # Dynamic weight = base * correlation adjustment factor
            adjustment = 1 + 0.5 * corr_zscore.fillna(0)  # ±50% adjustment max
            dynamic_weights[col] = base_weight * adjustment

        # Normalize weights to sum to 1 at each time point
        weight_df = pd.DataFrame(dynamic_weights)
        row_sums = weight_df.sum(axis=1).replace(0, 1)
        for col in dynamic_weights:
            dynamic_weights[col] = dynamic_weights[col] / row_sums

        return dynamic_weights

    def _get_foreign_rate(
        self,
        country: str,
        data: pd.DataFrame,
    ) -> pd.Series:
        """
        Get foreign interest rate from dynamic data columns.

        Args:
            country: Country name (brazil, china, mexico, australia)
            data: DataFrame with potential rate columns

        Returns:
            Series of interest rates (dynamic); NaNs if not available
        """
        # Check if we have a dynamic rate column for this country
        if country in self.foreign_rate_columns:
            rate_col = self.foreign_rate_columns[country]
            if rate_col in data.columns and not data[rate_col].isna().all():
                logger.debug(f"   Using dynamic rate for {country} from {rate_col}")
                return data[rate_col]

        # No rate available
        return pd.Series(np.nan, index=data.index)

    def _compute_carry_trade_signal(
        self,
        data: pd.DataFrame,
    ) -> Tuple[pd.Series, Dict[str, pd.Series]]:
        """
        Compute carry trade signal from interest rate differentials.

        Carry trade = borrow low-rate currency, invest in high-rate currency.
        Positive carry differential makes USD attractive (bullish USD).

        Uses dynamic FRED rates when available; falls back to proxy-based
        estimation using credit spreads and yield curve when individual
        country rates are not available.

        Returns:
            (composite_carry, individual_carries)
        """
        us_rate = pd.Series(np.nan, index=data.index)

        # Get US interest rate (prefer fed funds, fallback to 2Y)
        if "fred_fedfunds" in data.columns:
            us_rate = data["fred_fedfunds"]
        elif "fred_dgs2" in data.columns:
            us_rate = data["fred_dgs2"]

        if us_rate.isna().all():
            logger.info("   No US rate data for carry trade")
            return pd.Series(0.0, index=data.index), {}

        # Compute carry vs each country
        carries = {}
        carry_weights = {}

        # Brazil carry: High EM rate - should attract capital, weaken BRL
        if "fred_dexbzus" in data.columns:
            brazil_rate = self._get_foreign_rate("brazil", data)
            if not brazil_rate.isna().all():
                carries["brazil"] = brazil_rate - us_rate  # Positive = Brazil higher
                carry_weights["brazil"] = 0.30
            else:
                logger.debug("   Missing dynamic rate for brazil; will use proxy")

        # China carry: Lower rates, managed currency
        if "fred_dexchus" in data.columns:
            china_rate = self._get_foreign_rate("china", data)
            if not china_rate.isna().all():
                carries["china"] = china_rate - us_rate
                carry_weights["china"] = 0.35
            else:
                logger.debug("   Missing dynamic rate for china; will use proxy")

        # Mexico carry: High rates
        if "fred_dexmxus" in data.columns:
            mexico_rate = self._get_foreign_rate("mexico", data)
            if not mexico_rate.isna().all():
                carries["mexico"] = mexico_rate - us_rate
                carry_weights["mexico"] = 0.20
            else:
                logger.debug("   Missing dynamic rate for mexico; will use proxy")

        # Australia carry
        if "fred_dexusal" in data.columns:
            australia_rate = self._get_foreign_rate("australia", data)
            if not australia_rate.isna().all():
                carries["australia"] = australia_rate - us_rate
                carry_weights["australia"] = 0.15
            else:
                logger.debug("   Missing dynamic rate for australia; will use proxy")

        # If no individual country rates, use proxy-based carry signal
        if not carries:
            return self._compute_proxy_carry_signal(data, us_rate)

        # Normalize weights
        total_weight = sum(carry_weights.values())
        normalized = {k: v / total_weight for k, v in carry_weights.items()}

        # Composite carry signal
        composite = pd.Series(0.0, index=data.index)
        for country, carry in carries.items():
            # Negative carry differential = capital flows to foreign = USD weakness
            # Positive carry differential = capital flows to US = USD strength
            composite -= normalized[country] * carry.fillna(0)

        # Z-score normalize using 5-year window for deep context
        composite_zscore = (composite - composite.rolling(1260).mean()) / composite.rolling(1260).std().replace(0, 1)

        logger.info(f"   Carry trade computed for: {list(carries.keys())}")

        return composite_zscore, carries

    def _compute_proxy_carry_signal(
        self,
        data: pd.DataFrame,
        us_rate: pd.Series,
    ) -> Tuple[pd.Series, Dict[str, pd.Series]]:
        """
        Compute proxy carry trade signal when individual country rates unavailable.

        Uses market-based proxies that reflect global carry conditions:
        1. TED spread: 3M LIBOR - T-Bill (credit/liquidity risk premium)
        2. High Yield spread: EM rates correlate with HY (risk appetite)
        3. Yield curve slope: Steeper = higher future rates = USD attractive
        4. DXY momentum: Confirms/dampens carry signal

        Theory:
        - Higher credit spreads = risk-off = capital flows to USD = bullish USD
        - Steeper yield curve = US rate expectations rising = bullish USD
        - DXY strength confirms carry flow direction

        Returns:
            (proxy_carry_zscore, proxy_components)
        """
        components = {}

        # === Component 1: TED Spread (credit risk) ===
        # Higher TED = more credit risk = flight to safety = USD strength
        if "fred_tedrate" in data.columns:
            ted = data["fred_tedrate"].copy()
            ted_zscore = (ted - ted.rolling(504).mean()) / ted.rolling(504).std().replace(0, 1)
            components["ted_spread"] = ted_zscore.fillna(0)
            logger.debug("   Using TED spread for carry proxy")

        # === Component 2: High Yield Spread (EM risk proxy) ===
        # EM rates track HY spreads; wider HY = EM weakness = USD strength
        # Use change in HY spread as signal (rising = risk-off)
        if "fred_bamlh0a0hym2" in data.columns:
            hy = data["fred_bamlh0a0hym2"].copy()
            hy_change = hy.pct_change(21, fill_method=None)  # 1-month change
            hy_zscore = (hy_change - hy_change.rolling(252).mean()) / hy_change.rolling(252).std().replace(0, 1)
            components["hy_spread"] = hy_zscore.fillna(0)
            logger.debug("   Using HY spread for carry proxy")

        # === Component 3: Yield Curve Slope ===
        # Steeper curve = higher future rates = USD attractive
        if "fred_t10y2y" in data.columns:
            curve = data["fred_t10y2y"].copy()
            curve_zscore = (curve - curve.rolling(504).mean()) / curve.rolling(504).std().replace(0, 1)
            components["yield_curve"] = curve_zscore.fillna(0)
            logger.debug("   Using yield curve for carry proxy")

        # === Component 4: US Rate Level ===
        # Higher absolute US rate = more attractive to hold USD
        us_rate_zscore = (us_rate - us_rate.rolling(504).mean()) / us_rate.rolling(504).std().replace(0, 1)
        components["us_rate_level"] = us_rate_zscore.fillna(0)

        if not components:
            logger.warning("   No proxy data available for carry trade")
            return pd.Series(0.0, index=data.index), {}

        # === Combine Components ===
        # Weight by theoretical importance for FX carry
        weights = {
            "ted_spread": 0.25,      # Credit risk is key driver
            "hy_spread": 0.30,       # EM risk proxy (most relevant for ag FX)
            "yield_curve": 0.20,     # Future rate expectations
            "us_rate_level": 0.25,   # Absolute rate attractiveness
        }

        composite = pd.Series(0.0, index=data.index)
        active_weight = 0.0

        for name, component in components.items():
            w = weights.get(name, 0.1)
            composite += w * component
            active_weight += w

        # Normalize by active weight
        if active_weight > 0:
            composite = composite / active_weight

        # Final z-score normalization
        composite_zscore = (composite - composite.rolling(504).mean()) / composite.rolling(504).std().replace(0, 1)

        logger.info(f"   Carry trade proxy computed using: {list(components.keys())}")

        return composite_zscore.fillna(0), components

    def _fit_ardl_model(
        self,
        data: pd.DataFrame,
        fx_cols: List[str],
        max_lags: int = 10,
    ) -> Optional[object]:
        """
        Fit real ARDL model: ZL returns ~ lagged ZL + distributed lags of FX.

        Uses AIC to select optimal lag structure with proper numerical stability.

        Returns:
            Fitted ARDL model or None if fitting fails
        """
        if not ARDL_AVAILABLE:
            return None

        try:
            # Step 1: Prepare returns data with proper handling
            zl_prices = data["close"].copy()
            # Replace zeros to avoid division issues
            zl_prices = zl_prices.replace(0, np.nan)
            zl_returns = zl_prices.pct_change(fill_method=None).dropna()

            # Step 2: Build FX returns DataFrame with numerical stability
            fx_returns_data = {}
            for col in fx_cols:
                fx = data[col].copy()
                # Replace zeros to avoid division issues
                fx = fx.replace(0, np.nan)

                if col == "fred_dxy":
                    fx_returns_data[col] = fx.pct_change(fill_method=None)
                else:
                    # Safe inversion with protection
                    inverted = 1.0 / fx.where(fx.abs() > 1e-10, np.nan)
                    fx_returns_data[col] = inverted.pct_change(fill_method=None)

            fx_returns = pd.DataFrame(fx_returns_data).dropna()

            # Step 3: Align indices
            common_idx = zl_returns.index.intersection(fx_returns.index)
            if len(common_idx) < 500:
                logger.warning(f"Insufficient data for ARDL: {len(common_idx)} < 500 required")
                return None

            y = zl_returns.loc[common_idx].copy()
            X = fx_returns.loc[common_idx].copy()

            # Step 4: Remove NaN, Inf, and extreme outliers
            # Replace inf with nan
            y = y.replace([np.inf, -np.inf], np.nan)
            X = X.replace([np.inf, -np.inf], np.nan)

            # Remove rows with any nan
            mask = y.notna() & X.notna().all(axis=1)
            y = y[mask]
            X = X[mask]

            if len(y) < 500:
                logger.warning(f"Insufficient clean data for ARDL: {len(y)} < 500 required")
                return None

            # Step 5: Winsorize extreme values (clip at 3 std)
            y_std = y.std()
            y_mean = y.mean()
            y = y.clip(y_mean - 3 * y_std, y_mean + 3 * y_std)

            for col in X.columns:
                x_std = X[col].std()
                x_mean = X[col].mean()
                X[col] = X[col].clip(x_mean - 3 * x_std, x_mean + 3 * x_std)

            # Step 6: Scale data to improve numerical stability
            # Multiply by 100 to get percentage returns
            y = y * 100
            X = X * 100

            # Step 7: Final check for numerical validity
            if not np.isfinite(y).all():
                logger.warning("   Non-finite values in y after preprocessing")
                return None
            if not np.isfinite(X.values).all():
                logger.warning("   Non-finite values in X after preprocessing")
                return None

            # Step 8: Test for stationarity (ADF test)
            try:
                adf_result = adfuller(y.dropna(), autolag='AIC')
                logger.info(f"   ADF test p-value: {adf_result[1]:.4f}")
                if adf_result[1] > 0.05:
                    logger.warning("   ZL returns may not be stationary")
            except Exception as e:
                logger.warning(f"   ADF test failed: {e}")

            # Step 9: Fit ARDL with lag selection
            # Search lag space for best model by AIC
            best_aic = np.inf
            best_model = None
            best_lags = (1, 1)

            # Use numpy error handling to catch numerical issues
            with np.errstate(divide='ignore', over='ignore', invalid='ignore'):
                for ar_lag in range(1, min(max_lags, 11)):
                    for dl_lag in range(1, min(max_lags, 11)):
                        try:
                            model = ARDL(
                                y.values,  # Use numpy array to avoid date index warnings
                                lags=ar_lag,
                                exog=X.values,
                                order=dl_lag,  # Same lag for all exog
                                trend='c',
                            )
                            result = model.fit()

                            # Check if AIC is valid
                            if np.isfinite(result.aic) and result.aic < best_aic:
                                best_aic = result.aic
                                best_model = result
                                best_lags = (ar_lag, dl_lag)

                        except Exception:
                            continue

            if best_model is not None:
                # Validate coefficients are numerically stable
                params = best_model.params
                if not np.isfinite(params).all():
                    logger.warning("   ARDL model has non-finite coefficients, rejecting")
                    return None

                max_coef = np.abs(params).max()
                if max_coef > 1e6:
                    logger.warning(f"   ARDL model has extreme coefficients (max={max_coef:.2e}), rejecting")
                    return None

                # Log coefficient summary
                coef_stats = f"min={params.min():.4f}, max={params.max():.4f}, mean={params.mean():.4f}"
                logger.info(f"   ARDL fitted: AR({best_lags[0]}), DL({best_lags[1]}), AIC={best_aic:.2f}")
                logger.info(f"   ARDL observations: {best_model.nobs}, coefficients: {coef_stats}")
                self.ardl_lags = best_lags

                # Save model
                model_dir = MODELS_DIR / self.bucket
                model_dir.mkdir(parents=True, exist_ok=True)
                joblib.dump(best_model, model_dir / "ardl_model.joblib")

                return best_model

            logger.warning("   No valid ARDL model found")
            return None

        except Exception as e:
            logger.warning(f"ARDL fitting failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None

    def _extract_ardl_signal(
        self,
        ardl_result,
        data: pd.DataFrame,
        fx_cols: List[str],
    ) -> pd.Series:
        """
        Extract FX pressure signal from fitted ARDL model coefficients.

        PATCHED 2026-01-23: Avoid using fittedvalues (causes matmul warnings).
        Instead, extract the exogenous variable coefficients directly and
        use them to weight the FX inputs. This is more interpretable and
        numerically stable.

        The ARDL model: ZL_ret = const + AR terms + sum(beta_i * FX_i_lags) + error

        We extract the beta_i coefficients for each FX variable and use them
        as weights to construct a coefficient-weighted FX pressure index.
        """
        if ardl_result is None:
            return pd.Series(0.0, index=data.index)

        try:
            # Step 1: Extract model parameters
            params = ardl_result.params
            param_names = ardl_result.model.exog_names if hasattr(ardl_result.model, 'exog_names') else None

            # Validate params are numerically stable
            if not np.isfinite(params).all():
                logger.warning("   ARDL params contain non-finite values, skipping signal")
                return pd.Series(0.0, index=data.index)

            # Check for extreme coefficient values (sign of ill-conditioning)
            max_coef = np.abs(params).max()
            if max_coef > 1e6:
                logger.warning(f"   ARDL params contain extreme values (max={max_coef:.2e}), skipping signal")
                return pd.Series(0.0, index=data.index)

            # Step 2: Extract exogenous variable coefficients
            # ARDL params structure: [const, AR lags, exog lags for each variable]
            # The number of AR lags is stored in ardl_lags[0]
            # The number of exog lags per variable is stored in ardl_lags[1]
            ar_lags = self.ardl_lags[0]
            dl_lags = self.ardl_lags[1]
            n_exog = len(fx_cols)

            # Count parameters: 1 (const) + ar_lags (AR terms) + n_exog * dl_lags (exog terms)
            expected_params = 1 + ar_lags + n_exog * dl_lags
            actual_params = len(params)

            if actual_params != expected_params:
                logger.info(f"   ARDL param count mismatch: expected {expected_params}, got {actual_params}")
                # Fall back to using all exog coefficients (skip const and AR terms)
                exog_start = 1 + ar_lags
                exog_coefs = params[exog_start:] if exog_start < len(params) else params[1:]
            else:
                # Extract exogenous coefficients (after const and AR terms)
                exog_start = 1 + ar_lags
                exog_coefs = params[exog_start:]

            # Step 3: Sum coefficients by FX variable to get aggregate effect
            # Each FX variable has dl_lags coefficients
            fx_weights = {}
            for i, col in enumerate(fx_cols):
                start_idx = i * dl_lags
                end_idx = start_idx + dl_lags
                if end_idx <= len(exog_coefs):
                    # Sum all lag coefficients for this variable (total impact)
                    total_coef = exog_coefs[start_idx:end_idx].sum()
                    fx_weights[col] = total_coef
                else:
                    # Not enough coefficients, use equal weight
                    fx_weights[col] = 0.0

            # Step 4: Normalize weights (absolute values sum to 1)
            total_abs = sum(abs(w) for w in fx_weights.values())
            if total_abs > 0:
                for col in fx_weights:
                    fx_weights[col] = fx_weights[col] / total_abs
            else:
                # Equal weights if all zero
                for col in fx_weights:
                    fx_weights[col] = 1.0 / len(fx_weights)

            weights_str = ', '.join(f'{k.replace("fred_", "")}: {v:.3f}' for k, v in fx_weights.items())
            logger.info(f"   ARDL coefficient weights: {{{weights_str}}}")

            # Step 5: Construct coefficient-weighted FX pressure signal
            pressure = pd.Series(0.0, index=data.index)
            for col in fx_cols:
                if col not in data.columns:
                    continue

                fx = data[col].copy()
                fx = fx.replace(0, np.nan)

                # DXY is already USD strength; others need inversion
                if col == "fred_dxy":
                    fx_returns = fx.pct_change(fill_method=None)
                else:
                    # Invert: higher value = stronger USD
                    inverted = 1.0 / fx.where(fx.abs() > 1e-10, np.nan)
                    fx_returns = inverted.pct_change(fill_method=None)

                # Weight by ARDL coefficient
                # Positive coefficient = positive FX return increases ZL return
                # We want higher signal = stronger USD = bearish ZL
                weighted_returns = fx_weights[col] * fx_returns.fillna(0)
                pressure += weighted_returns

            # Step 6: Cumsum to get cumulative pressure
            cum_pressure = pressure.cumsum()

            # Step 7: Z-score normalize
            pressure_zscore = (cum_pressure - cum_pressure.rolling(self.zscore_window, min_periods=252).mean()) / \
                              cum_pressure.rolling(self.zscore_window, min_periods=252).std().replace(0, 1)

            # Replace any remaining non-finite values
            pressure_zscore = pressure_zscore.replace([np.inf, -np.inf], np.nan).fillna(0)

            return pressure_zscore

        except Exception as e:
            logger.warning(f"ARDL signal extraction failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return pd.Series(0.0, index=data.index)

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute FX pressure index with real ARDL and carry trade.

        Components:
        1. Dynamic-weighted FX z-scores
        2. ARDL model fitted value (if available)
        3. Carry trade signal
        """
        signals = []

        # Step 1: Compute dynamic weights
        dynamic_weights = self._compute_dynamic_weights(data)
        available_fx = list(dynamic_weights.keys())

        if not available_fx:
            logger.warning("FxSignalGenerator: No FX data available")
            return signals

        # Step 2: Compute FX z-scores with dynamic weights
        # Use deep 5-year z-score window for robust normalization
        fx_zscores = {}
        for col in available_fx:
            series = data[col]
            # DXY is already USD strength; others need inversion
            if col == "fred_dxy":
                fx_zscores[col] = self.compute_zscore(series, window=self.zscore_window, min_periods=252)
            else:
                # FRED FX is foreign/USD, invert to USD/foreign for consistency
                inverted = 1 / series
                fx_zscores[col] = self.compute_zscore(inverted, window=self.zscore_window, min_periods=252)

        # Compute dynamically-weighted composite
        composite = pd.Series(0.0, index=data.index)
        for col, zscore in fx_zscores.items():
            weighted = dynamic_weights[col] * zscore.fillna(0)
            composite += weighted

        # Step 3: Fit ARDL model
        ardl_model = None
        ardl_signal = pd.Series(0.0, index=data.index)

        if ARDL_AVAILABLE and len(data) >= 500:
            # Use deeper lag search for robust model
            ardl_model = self._fit_ardl_model(data, available_fx, max_lags=21)
            if ardl_model is not None:
                ardl_signal = self._extract_ardl_signal(ardl_model, data, available_fx)
                self.ardl_model = ardl_model
                logger.info(f"   ARDL signal computed, AIC={ardl_model.aic:.2f}")

        # Step 4: Compute carry trade signal
        carry_signal, carries = self._compute_carry_trade_signal(data)
        has_carry = not carry_signal.isna().all() and carry_signal.abs().sum() > 0

        # Step 5: Combine signals
        # Weights: z-score composite (40%), ARDL (40%), carry (20%)
        final_signal = pd.Series(0.0, index=data.index)
        component_weights = []

        # Z-score composite
        final_signal += 0.40 * composite
        component_weights.append(("zscore", 0.40))

        # ARDL signal (if fitted)
        if ardl_model is not None:
            final_signal += 0.40 * ardl_signal.fillna(0)
            component_weights.append(("ardl", 0.40))
        else:
            # Give more weight to z-score if no ARDL
            final_signal += 0.40 * composite
            component_weights.append(("zscore_extra", 0.40))

        # Carry trade
        if has_carry:
            final_signal += 0.20 * carry_signal.fillna(0)
            component_weights.append(("carry", 0.20))

        # Renormalize
        total_weight = sum(w for _, w in component_weights)
        if total_weight > 0:
            final_signal = final_signal / total_weight

        # ZL-FX correlation for context
        zl = data["close"]
        zl_fx_corr = pd.Series(np.nan, index=data.index)
        if "fred_dxy" in fx_zscores:
            zl_fx_corr = zl.rolling(63).corr(data["fred_dxy"])

        for idx in data.index:
            if pd.isna(final_signal.loc[idx]):
                continue

            # Count available FX pairs for confidence
            available_count = sum(
                1 for col, zs in fx_zscores.items()
                if not pd.isna(zs.loc[idx])
            )
            base_confidence = min(available_count / 5, 1.0) * 0.6 + 0.2

            # Boost for ARDL model
            if ardl_model is not None:
                base_confidence += 0.15

            # Boost for carry trade
            if has_carry:
                base_confidence += 0.05

            confidence = min(base_confidence, 0.95)

            # Carry signal for signal_2
            carry_val = carry_signal.loc[idx] if not pd.isna(carry_signal.loc[idx]) else 0.0

            # Build metadata
            meta = {
                "fx_pairs_used": available_fx,
                "zl_dxy_corr": float(zl_fx_corr.loc[idx]) if not pd.isna(zl_fx_corr.loc[idx]) else None,
                "run_hash": run_hash,
                "ardl_fitted": ardl_model is not None,
                "carry_computed": has_carry,
            }

            # Add dynamic weights snapshot
            for col in available_fx:
                weight_val = dynamic_weights[col].loc[idx] if not pd.isna(dynamic_weights[col].loc[idx]) else self.base_trade_weights.get(col, 0)
                meta[f"weight_{col.replace('fred_', '')}"] = float(weight_val)

            # Add ARDL diagnostics
            if ardl_model is not None:
                meta["ardl_ar_lags"] = self.ardl_lags[0]
                meta["ardl_dl_lags"] = self.ardl_lags[1]
                meta["ardl_aic"] = float(ardl_model.aic)
                meta["ardl_bic"] = float(ardl_model.bic)
                meta["ardl_nobs"] = int(ardl_model.nobs)

            # Add carry details
            if has_carry:
                for country, carry in carries.items():
                    if not pd.isna(carry.loc[idx]):
                        meta[f"carry_{country}"] = float(carry.loc[idx])

            signals.append(SignalOutput(
                as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                bucket="fx",
                signal_1=float(final_signal.loc[idx]),
                signal_2=float(carry_val),
                confidence=float(confidence),
                model_type="ardl",
                metadata=meta,
            ))

        ardl_status = "with ARDL" if ardl_model else "no ARDL"
        carry_status = "with carry" if has_carry else "no carry"
        logger.info(f"FxSignalGenerator: Generated {len(signals)} signals ({ardl_status}, {carry_status})")
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
