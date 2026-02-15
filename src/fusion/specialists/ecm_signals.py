"""
ECM-based signal generators: palm.

Uses Error Correction Model for cointegration analysis between ZL and FCPO.
Now includes REAL Ridge regression for forward return prediction.

PATCHED 2026-01-23: Implemented real Ridge regression model
- Model trains on ECM features to predict 21-day forward return
- Cointegration residuals as primary feature
- Mean reversion speed as secondary feature
- Real FX conversion using FRED MYR/USD when available
"""

import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

# ML Imports - REAL MODELS
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from fusion.specialists.base import (
    BaseSignalGenerator,
    SignalConfig,
    SignalOutput,
)

logger = logging.getLogger(__name__)

# Model persistence directory
MODELS_DIR = Path(__file__).parent.parent.parent.parent / "models" / "specialists"

# Try to import statsmodels for cointegration tests
try:
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tsa.stattools import adfuller, coint  # noqa: F401

    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    logger.warning("statsmodels not available; using simplified palm model")


# =============================================================================
# ML MODEL MIXIN FOR PALM (Ridge-specific)
# =============================================================================


class PalmMLMixin:
    """
    ML mixin for Palm specialist using Ridge regression.

    Ridge is appropriate for ECM features because:
    - Cointegration coefficients can be noisy, regularization helps
    - Spread features are often correlated, Ridge handles multicollinearity
    - Linear model matches the ECM theoretical framework
    """

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names: list[str] = []
        self.last_train_date: date | None = None
        self.train_frequency_days: int = 21  # Retrain monthly
        self.min_train_samples: int = 126  # ~6 months minimum
        self.target_horizon: int = 21  # Predict 21-day forward return
        self.missingness_threshold: float = 0.30
        self.degraded_confidence: float = 0.20

    def _get_model_path(self) -> Path:
        """Get path for model persistence."""
        model_dir = MODELS_DIR / self.bucket
        model_dir.mkdir(parents=True, exist_ok=True)
        return model_dir / "model.joblib"

    def _get_scaler_path(self) -> Path:
        """Get path for scaler persistence."""
        model_dir = MODELS_DIR / self.bucket
        model_dir.mkdir(parents=True, exist_ok=True)
        return model_dir / "scaler.joblib"

    def _save_model(self):
        """Persist model and scaler to disk."""
        if self.model is not None:
            joblib.dump(self.model, self._get_model_path())
            joblib.dump(self.scaler, self._get_scaler_path())
            # Save metadata
            meta = {
                "feature_names": self.feature_names,
                "last_train_date": self.last_train_date,
                "target_horizon": self.target_horizon,
            }
            joblib.dump(meta, MODELS_DIR / self.bucket / "metadata.joblib")
            logger.info(f"   Saved model to {self._get_model_path()}")

    def _load_model(self) -> bool:
        """Load model from disk if exists. Returns True if loaded."""
        model_path = self._get_model_path()
        scaler_path = self._get_scaler_path()
        meta_path = MODELS_DIR / self.bucket / "metadata.joblib"

        if model_path.exists() and scaler_path.exists() and meta_path.exists():
            try:
                self.model = joblib.load(model_path)
                self.scaler = joblib.load(scaler_path)
                meta = joblib.load(meta_path)
                self.feature_names = meta.get("feature_names", [])
                self.last_train_date = meta.get("last_train_date")
                self.target_horizon = meta.get("target_horizon", 21)
                logger.info(f"   Loaded existing model from {model_path}")
                return True
            except Exception as e:
                logger.warning(f"   Could not load model: {e}")
                return False
        return False

    def _should_retrain(self, current_date: date) -> bool:
        """Check if model needs retraining."""
        force = os.getenv("FORCE_SPECIALIST_RETRAIN", "").strip().lower()
        if force in {"1", "true", "yes", "y"}:
            return True
        if self.model is None:
            return True
        if self.last_train_date is None:
            return True
        days_since_train = (current_date - self.last_train_date).days
        return days_since_train >= self.train_frequency_days

    def _compute_forward_return(self, prices: pd.Series, horizon: int) -> pd.Series:
        """Compute forward return as training target."""
        return prices.pct_change(periods=horizon).shift(-horizon)

    def _create_model(self):
        """Create Ridge regression model."""
        return Ridge(
            alpha=1.0,  # Regularization strength
            fit_intercept=True,
            random_state=42,
        )

    def _prepare_features(self, data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """Prepare ECM-specific features. Implemented in PalmSignalGenerator."""
        raise NotImplementedError

    def _train_model(self, data: pd.DataFrame, current_date: date):
        """
        Train the Ridge model on historical data.

        Uses expanding window: all data up to current_date.
        Target: forward return at target_horizon.

        FIX 2026-01-30: Use coverage-based feature filtering (same as xgb_signals.py)
        """
        logger.info(f"   Training {self.bucket} model (Ridge)...")

        # Prepare features
        X, feature_names = self._prepare_features(data)

        # Compute target: forward return
        y = self._compute_forward_return(data["close"], self.target_horizon)

        # FIX: Filter to features with sufficient coverage (>50% non-NaN)
        coverage = X.notna().mean()
        usable_features = coverage[coverage > 0.5].index.tolist()

        if len(usable_features) < 5:
            logger.warning(f"   Too few usable features: {len(usable_features)}")
            return False

        logger.info(
            f"   Using {len(usable_features)}/{len(feature_names)} features with >50% coverage"
        )

        X_filtered = X[usable_features]
        self.feature_names = usable_features  # Only train on usable features

        # Align X and y, drop rows where any USABLE feature is NaN
        valid_mask = X_filtered.notna().all(axis=1) & y.notna()
        X_clean = X_filtered[valid_mask]
        y_clean = y[valid_mask]

        if len(X_clean) < self.min_train_samples:
            logger.warning(
                f"   Insufficient training data: {len(X_clean)} < {self.min_train_samples}"
            )
            return False

        # === TWO-PHASE TRAINING: Feature Selection + Refit ===
        # Phase 1: Initial fit on all features
        X_scaled = self.scaler.fit_transform(X_clean)
        self.model = self._create_model()
        self.model.fit(X_scaled, y_clean)

        # Phase 2: Prune low-importance features, keeping ECM + news protected
        ECM_PROTECTED = {
            "spread_zscore",
            "ecm_residual_zscore",
            "reversion_speed",
            "spread_mom_5d",
            "spread_mom_21d",
            "spread_mom_63d",
            "is_cointegrated",
            "coint_strength",
            "spread_vol_21d",
            "spread_vol_63d",
            "palm_news_intensity",
            "palm_article_count",
            "palm_articles_7d",
        }
        MAX_FEATURES = 50  # Cap total features for interpretability

        coef_importance = dict(zip(usable_features, abs(self.model.coef_)))
        protected = [f for f in usable_features if f in ECM_PROTECTED]
        remaining = [f for f in usable_features if f not in ECM_PROTECTED]
        remaining_sorted = sorted(
            remaining, key=lambda f: coef_importance.get(f, 0), reverse=True
        )
        top_remaining = remaining_sorted[: MAX_FEATURES - len(protected)]
        selected_features = protected + top_remaining

        if len(selected_features) < len(usable_features):
            logger.info(
                f"   Feature pruning: {len(usable_features)} -> {len(selected_features)} "
                f"({len(protected)} ECM/news protected + {len(top_remaining)} by importance)"
            )
            # Refit on selected features only
            X_selected = X_clean[selected_features]
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X_selected)
            self.model = self._create_model()
            self.model.fit(X_scaled, y_clean)
            self.feature_names = selected_features

        self.last_train_date = current_date

        # Log coefficients
        if hasattr(self.model, "coef_"):
            coefs = dict(zip(self.feature_names, self.model.coef_))
            ecm_coefs = {k: v for k, v in coefs.items() if k in ECM_PROTECTED}
            top_coefs = sorted(coefs.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
            logger.info(f"   Top coefficients: {top_coefs}")
            if ecm_coefs:
                top_ecm = sorted(
                    ecm_coefs.items(), key=lambda x: abs(x[1]), reverse=True
                )[:5]
                logger.info(f"   ECM coefficients: {top_ecm}")

        # Save model
        self._save_model()

        logger.info(
            f"   Trained on {len(X_clean)} samples, {len(self.feature_names)} features"
        )
        return True

    def _predict(
        self, features: pd.DataFrame
    ) -> tuple[np.ndarray | None, dict[str, Any]]:
        """Generate predictions from trained model with missingness policy."""
        if self.model is None:
            raise ValueError("Model not trained")

        # Ensure feature order matches training
        X = features[self.feature_names] if self.feature_names else features
        if X.empty:
            return None, {
                "degraded_level": 2,
                "source_tag": "insufficient_features",
                "conf": self.degraded_confidence,
                "nan_pct_latest": 1.0,
                "missing_features": [],
                "abstained": True,
                "reason": "empty_features",
            }

        latest = X.iloc[-1]
        nan_pct_latest = float(latest.isna().mean())
        missing_features = latest[latest.isna()].index.tolist()

        # PATCHED 2026-01-31: Relaxed missingness policy for cross-market data
        # Only abstain if >30% of features are missing (threshold check)
        # For <30% missing, impute with training means and proceed with degraded confidence
        if nan_pct_latest > self.missingness_threshold:
            return None, {
                "degraded_level": 2,
                "source_tag": "insufficient_features",
                "conf": self.degraded_confidence,
                "nan_pct_latest": nan_pct_latest,
                "missing_features": missing_features,
                "abstained": True,
                "reason": "nan_pct_threshold",
            }

        # REMOVED: Strict "any NaN = abstain" policy
        # Cross-market data (CPO vs ZL) has calendar misalignment
        # Rolling features have startup NaN - this is normal, not an error
        # Instead: impute missing with training means and adjust confidence

        # Impute missing values with training feature means (stored in scaler)
        X_imputed = X.copy()
        if nan_pct_latest > 0:
            # Use scaler's mean for imputation (fitted during training)
            for i, col in enumerate(X.columns):
                if X_imputed[col].isna().any():
                    X_imputed[col] = X_imputed[col].fillna(self.scaler.mean_[i])

        X_scaled = self.scaler.transform(X_imputed)

        # Adjust confidence based on missingness
        # Full confidence at 0% missing, degraded at threshold
        conf_adjustment = 1.0 - (nan_pct_latest / self.missingness_threshold) * 0.3

        return self.model.predict(X_scaled), {
            "nan_pct_latest": nan_pct_latest,
            "missing_features": missing_features,
            "abstained": False,
            "imputed": nan_pct_latest > 0,
            "conf_adjustment": conf_adjustment,
        }


# =============================================================================
# PALM SIGNAL GENERATOR - REAL RIDGE REGRESSION
# =============================================================================


class PalmSignalGenerator(BaseSignalGenerator, PalmMLMixin):
    """
    Palm specialist: substitution pressure from FCPO.

    ACTUAL MODEL: Ridge Regression

    Signal Contract:
    - signal_1: Model prediction of forward ZL return based on ECM features
    - signal_2: Mean reversion speed (how fast spread reverts)

    Higher prediction = bullish ZL expected
    Lower prediction = bearish ZL expected

    Features:
    - ECM residual (cointegration error)
    - Spread z-score
    - Spread momentum (multiple horizons)
    - Mean reversion speed (half-life based)
    - Real MYR/USD FX rate when available
    - Cointegration regime indicator

    Target: 21-day forward ZL return

    PATCHED 2026-01-23: Real Ridge model with ECM features
    """

    def __init__(self):
        config = SignalConfig(
            bucket="palm",
            model_type="ridge",  # ECM + Ridge for cointegration modeling
            primary_features=[
                "close",
                # PALM COMPLEX - Full cointegration system
                "cpo_close",  # Crude Palm Oil (Bursa Malaysia FCPO)
                "fred_dexmaus",  # MYR/USD (FX conversion for spread)
                # PRODUCTION REGION FX
                "fred_dexinus",  # IDR/USD (Indonesia - #1 producer)
            ],
            secondary_features=[
                # Alternative names
                "palm_oil_close",  # Alternative CPO column
                "myr_usd",  # Alternative MYR column
                # Extended palm complex
                "pko_close",  # Palm kernel oil
                # Indonesian production proxies
                "indo_palm_production",
                # Weather/seasonal
                "el_nino_index",  # El Nino (production impact)
                # Cross-commodity
                "cpo_zl_spread",  # Pre-computed spread
            ],
            lookback_days=504,  # 2 years for cointegration stability
            min_data_points=252,
        )
        BaseSignalGenerator.__init__(self, config)
        PalmMLMixin.__init__(self)
        self._cointegration_result = None
        self._hedge_ratio_cache = None

    def validate_inputs(self, data: pd.DataFrame) -> list[str]:
        """Require FULL palm cointegration complex."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")
        # REQUIRE palm oil
        if "cpo_close" not in data.columns:
            missing.append("cpo_close")
        # REQUIRE FX for proper spread calculation
        if "fred_dexmaus" not in data.columns:
            missing.append("fred_dexmaus")
        return missing

    def _get_palm_series(self, data: pd.DataFrame) -> pd.Series:
        """Get palm oil price series from available columns."""
        if "cpo_close" in data.columns:
            return data["cpo_close"]
        elif "palm_oil_close" in data.columns:
            return data["palm_oil_close"]
        else:
            raise ValueError("No palm oil price series available")

    def _get_myr_usd_rate(self, data: pd.DataFrame) -> pd.Series | None:
        """
        Get MYR/USD exchange rate if available (for auxiliary features only).

        Note: CPO data is in USD/tonne, so MYR FX is NOT
        needed for spread calculation. This is only used for FX-as-feature.
        """
        # Try different column name patterns
        fx_cols = ["fred_dexmaus", "myr_usd", "usdmyr", "fred_exmaus"]
        for col in fx_cols:
            if col in data.columns and data[col].notna().sum() > 30:
                logger.info(f"   Using MYR/USD FX as feature: {col}")
                return data[col]

        # Fallback: check for any column with 'myr' in name
        for col in data.columns:
            if "myr" in col.lower() and data[col].notna().sum() > 30:
                logger.info(f"   Using MYR FX column as feature: {col}")
                return data[col]

        return None

    def _test_cointegration(
        self,
        zl: pd.Series,
        cpo: pd.Series,
    ) -> tuple[bool, float, float | None]:
        """
        Test for cointegration between ZL and CPO.

        Returns:
            (is_cointegrated, p_value, hedge_ratio)
        """
        if not STATSMODELS_AVAILABLE:
            return False, 1.0, None

        try:
            # Clean data
            combined = pd.DataFrame({"zl": zl, "cpo": cpo}).dropna()
            if len(combined) < 252:
                return False, 1.0, None

            # Engle-Granger cointegration test
            score, pvalue, _ = coint(combined["zl"], combined["cpo"])

            # Estimate hedge ratio via OLS
            hedge_ratio = None
            if pvalue < 0.10:  # Cointegrated at 10% level
                model = OLS(combined["zl"], combined["cpo"]).fit()
                hedge_ratio = model.params.iloc[0]

            return pvalue < 0.10, pvalue, hedge_ratio

        except Exception as e:
            logger.warning(f"Cointegration test failed: {e}")
            return False, 1.0, None

    def _compute_spread(
        self,
        zl: pd.Series,
        cpo: pd.Series,
        hedge_ratio: float | None = None,
        myr_usd: pd.Series | None = None,
    ) -> pd.Series:
        """
        Compute ZL-CPO spread.

        If hedge_ratio available from cointegration, use it.
        Otherwise use unit conversion.

        Units:
        - ZL: cents/lb (CME Soybean Oil)
        - CPO: USD/tonne (palm oil futures)

        Conversion: CPO USD/tonne → cents/lb
        1 tonne = 2204.6 lbs
        CPO_cents_lb = (CPO / 2204.6) * 100

        PATCHED 2026-01-23: Fixed unit conversion (CPO is USD/tonne, not MYR/tonne)
        """
        if hedge_ratio is not None:
            # Cointegration-based spread (units already aligned by regression)
            return zl - hedge_ratio * cpo
        else:
            # Unit conversion spread
            # CPO in USD/tonne → convert to cents/lb
            # 1 tonne = 2204.6 lbs
            cpo_cents_lb = (cpo / 2204.6) * 100

            logger.debug(
                f"   CPO conversion: {cpo.iloc[-1]:.2f} USD/tonne → {cpo_cents_lb.iloc[-1]:.2f} cents/lb"
            )

            return zl - cpo_cents_lb

    def _compute_mean_reversion_speed(
        self,
        spread: pd.Series,
        window: int = 63,
    ) -> pd.Series:
        """
        Estimate mean reversion speed using half-life approach.

        Returns velocity of mean reversion (higher = faster reversion).
        """
        if not STATSMODELS_AVAILABLE:
            # Simplified: use spread velocity
            return -spread.diff(5) / spread.rolling(21).std()

        try:
            # Rolling half-life estimation
            half_life = pd.Series(np.nan, index=spread.index)

            for i in range(window, len(spread)):
                window_spread = spread.iloc[i - window : i].dropna()
                if len(window_spread) < 42:
                    continue

                # AR(1) regression: spread_t = alpha + beta * spread_{t-1} + e
                lagged = window_spread.shift(1).dropna()
                current = window_spread.iloc[1:]

                if len(lagged) < 42:
                    continue

                model = OLS(current, lagged).fit()
                beta = model.params.iloc[0]

                # Half-life = -ln(2) / ln(beta)
                if 0 < beta < 1:
                    hl = -np.log(2) / np.log(beta)
                    half_life.iloc[i] = min(hl, 252)  # Cap at 1 year

            # Convert to speed using percentile rank for better variability
            # Old: reversion_speed = 63 / half_life  → constant 1.0 when hl=63
            # New: z-score the half-life, then invert so faster reversion = higher score
            hl_clean = half_life.dropna()
            if len(hl_clean) > 30:
                hl_median = half_life.rolling(252, min_periods=63).median()
                hl_iqr = half_life.rolling(252, min_periods=63).apply(
                    lambda x: x.quantile(0.75) - x.quantile(0.25), raw=False
                )
                # Robust z-score: negative = faster than median (good for mean reversion)
                hl_zscore = -(half_life - hl_median) / hl_iqr.replace(0, np.nan)
                # Map to 0-5 range with sigmoid-like transform
                reversion_speed = 2.5 + 2.5 * np.tanh(hl_zscore * 0.5)
            else:
                reversion_speed = 63 / half_life  # Fallback
            return reversion_speed.clip(0, 5)

        except Exception as e:
            logger.warning(f"Mean reversion estimation failed: {e}")
            return -spread.diff(5) / spread.rolling(21).std()

    def _compute_ecm_residual(
        self,
        zl: pd.Series,
        cpo: pd.Series,
        hedge_ratio: float,
    ) -> pd.Series:
        """
        Compute Error Correction Model residual.

        ECM residual = ZL - hedge_ratio * CPO
        This represents the deviation from long-run equilibrium.
        """
        return zl - hedge_ratio * cpo

    def _prepare_features(self, data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """
        Prepare ECM-specific features for Ridge regression with ALL elite indicators.

        Features designed to capture:
        1. Current deviation from equilibrium (spread z-score)
        2. Speed of mean reversion (half-life based)
        3. Spread dynamics (momentum at multiple horizons)
        4. Cointegration strength (regime indicator)
        5. Cross-market correlations
        6. ALL elite indicators on ZL, CPO, and FX
        """
        features = {}

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL, CPO, MYR
        # =====================================================================
        data = self.add_all_technical_indicators(data, "close", "zl")

        # CPO elite indicators
        if "cpo_close" in data.columns and data["cpo_close"].notna().sum() > 30:
            cpo_data = data.copy()
            cpo_data["close"] = data["cpo_close"]
            cpo_data = self.add_all_technical_indicators(cpo_data, "close", "cpo")
            for c in cpo_data.columns:
                if c.startswith("cpo_") and c not in data.columns:
                    data[c] = cpo_data[c]

        # MYR/USD elite indicators
        for fx_col in ["fred_dexmaus", "myr_usd"]:
            if fx_col in data.columns and data[fx_col].notna().sum() > 30:
                fx_data = data.copy()
                fx_data["close"] = data[fx_col]
                fx_data = self.add_all_technical_indicators(fx_data, "close", "myr")
                for c in fx_data.columns:
                    if c.startswith("myr_") and c not in data.columns:
                        data[c] = fx_data[c]
                break

        # IDR/USD elite indicators
        if "fred_dexinus" in data.columns and data["fred_dexinus"].notna().sum() > 30:
            idr_data = data.copy()
            idr_data["close"] = data["fred_dexinus"]
            idr_data = self.add_all_technical_indicators(idr_data, "close", "idr")
            for c in idr_data.columns:
                if c.startswith("idr_") and c not in data.columns:
                    data[c] = idr_data[c]

        zl = data["close"]
        cpo = self._get_palm_series(data)
        myr_usd = self._get_myr_usd_rate(data)

        # Test cointegration (cache result)
        is_coint, coint_pvalue, hedge_ratio = self._test_cointegration(zl, cpo)
        self._hedge_ratio_cache = hedge_ratio

        # Compute spread (CPO already in USD/tonne, no FX needed)
        spread = self._compute_spread(zl, cpo, hedge_ratio)

        # === Core ECM Features ===

        # 1. Spread z-score (current deviation from equilibrium)
        features["spread_zscore"] = self.compute_zscore(
            spread, window=252, min_periods=126
        )

        # 2. ECM residual (if cointegrated)
        if hedge_ratio is not None:
            ecm_resid = self._compute_ecm_residual(zl, cpo, hedge_ratio)
            features["ecm_residual_zscore"] = self.compute_zscore(
                ecm_resid, window=252, min_periods=126
            )

        # 3. Mean reversion speed
        reversion_speed = self._compute_mean_reversion_speed(spread)
        features["reversion_speed"] = reversion_speed

        # 4. Spread momentum at multiple horizons
        features["spread_mom_5d"] = spread.pct_change(5, fill_method=None)
        features["spread_mom_21d"] = spread.pct_change(21, fill_method=None)
        features["spread_mom_63d"] = spread.pct_change(63, fill_method=None)

        # 5. Spread volatility
        spread_returns = spread.pct_change(fill_method=None)
        features["spread_vol_21d"] = spread_returns.rolling(21).std()
        features["spread_vol_63d"] = spread_returns.rolling(63).std()

        # === Market Features ===

        # 6. ZL momentum (own price dynamics)
        features["zl_mom_5d"] = zl.pct_change(5, fill_method=None)
        features["zl_mom_21d"] = zl.pct_change(21, fill_method=None)
        features["zl_vol_21d"] = zl.pct_change(fill_method=None).rolling(21).std()

        # 7. CPO momentum
        features["cpo_mom_5d"] = cpo.pct_change(5, fill_method=None)
        features["cpo_mom_21d"] = cpo.pct_change(21, fill_method=None)

        # 8. ZL-CPO correlation
        features["zl_cpo_corr_63d"] = zl.rolling(63).corr(cpo)

        # 9. Cointegration regime indicator (binary feature)
        features["is_cointegrated"] = float(is_coint) * np.ones(len(data))

        # 10. Cointegration p-value (continuous regime strength)
        features["coint_strength"] = (1 - coint_pvalue) * np.ones(len(data))

        # === FX Features (if available) ===

        if myr_usd is not None:
            features["myr_zscore"] = self.compute_zscore(
                myr_usd, window=126, min_periods=42
            )
            features["myr_mom_21d"] = myr_usd.pct_change(21, fill_method=None)

        # ADD ALL ELITE INDICATORS TO FEATURES
        for col in data.columns:
            if (
                col.startswith("zl_")
                or col.startswith("cpo_")
                or col.startswith("myr_")
                or col.startswith("idr_")
            ):
                if col not in features:
                    features[col] = data[col]

        # === MPOB FUNDAMENTAL FEATURES ===
        # load_palm_data() now joins supply.mpob_palm_1m (monthly, ffill to daily)
        if "palm_production_mt" in data.columns:
            prod = data["palm_production_mt"]
            exp = data["palm_exports_mt"]
            stk = data["palm_stocks_mt"]
            # Production momentum (month-over-month change in production level)
            features["mpob_prod_mom_1m"] = prod.pct_change(21, fill_method=None)
            features["mpob_prod_mom_3m"] = prod.pct_change(63, fill_method=None)
            # Stocks-to-production ratio (supply tightness)
            features["mpob_stocks_prod_ratio"] = stk / prod.replace(0, np.nan)
            features["mpob_stocks_prod_zscore"] = self.compute_zscore(
                features["mpob_stocks_prod_ratio"], window=252, min_periods=63
            )
            # Export pace relative to production
            features["mpob_export_rate"] = exp / prod.replace(0, np.nan)
            # Stocks z-score (absolute supply level signal)
            features["mpob_stocks_zscore"] = self.compute_zscore(
                stk, window=252, min_periods=63
            )
            logger.debug("   MPOB fundamental features added (6 features)")

        # === NEWS ARTICLE FEATURES ===
        # Accept both legacy and current loader contracts:
        # - article_count / news_article_count
        article_col = None
        if "news_article_count" in data.columns:
            article_col = "news_article_count"
        elif "article_count" in data.columns:
            article_col = "article_count"

        if article_col is not None:
            features["palm_article_count"] = data[article_col].fillna(0)
            features["palm_articles_7d"] = (
                data[article_col].fillna(0).rolling(7, min_periods=1).sum()
            )
            features["palm_articles_21d"] = (
                data[article_col].fillna(0).rolling(21, min_periods=5).sum()
            )
            # Article surge indicator (z-score of article flow)
            art_mean = features["palm_articles_21d"].rolling(63, min_periods=21).mean()
            art_std = features["palm_articles_21d"].rolling(63, min_periods=21).std()
            features["palm_news_intensity"] = (
                (features["palm_articles_21d"] - art_mean) / art_std.replace(0, np.nan)
            ).fillna(0)

        df = pd.DataFrame(features, index=data.index)
        return df, list(df.columns)

    def compute(self, data: pd.DataFrame, run_hash: str) -> list[SignalOutput]:
        """
        Compute palm substitution pressure signal using Ridge regression.

        PATCHED 2026-01-23: Real ML model predictions
        """
        signals = []

        # Try to load existing model
        if not self._load_model():
            logger.info("   No existing model, will train on first pass")

        # Prepare features for entire dataset
        X_full, feature_names = self._prepare_features(data)

        # Get palm series and FX for metadata
        zl = data["close"]
        cpo = self._get_palm_series(data)
        myr_usd = self._get_myr_usd_rate(data)

        # Test cointegration (for metadata)
        is_coint, coint_pvalue, hedge_ratio = self._test_cointegration(zl, cpo)
        logger.info(
            f"Palm cointegration: {'yes' if is_coint else 'no'} "
            f"(p={coint_pvalue:.3f}, hedge_ratio={hedge_ratio})"
        )

        # Compute spread for metadata (CPO already in USD/tonne)
        spread = self._compute_spread(zl, cpo, hedge_ratio)
        spread_zscore = self.compute_zscore(spread, window=252, min_periods=126)

        # Mean reversion speed for signal_2
        reversion_speed = self._compute_mean_reversion_speed(spread)

        # Get the most recent date with valid data
        # FIX 2026-01-30: Only require primary features to be non-NaN
        core_cols = [c for c in self.config.primary_features if c in X_full.columns]
        X_valid = X_full.dropna(subset=core_cols) if core_cols else X_full.dropna()
        last_valid_idx = X_valid.index[-1] if len(X_valid) > 0 else None

        if last_valid_idx is None:
            logger.warning(
                "PalmSignalGenerator: No valid data after dropna(subset=primary_features)"
            )
            return signals

        current_date = (
            last_valid_idx.date() if hasattr(last_valid_idx, "date") else last_valid_idx
        )

        # Check if retraining needed
        if self._should_retrain(current_date):
            train_data = data[data.index <= last_valid_idx]
            self._train_model(train_data, current_date)

        if self.model is None:
            logger.warning("PalmSignalGenerator: Model not trained")
            return signals

        # Generate predictions for each valid date
        for idx in data.index:
            if idx not in X_full.index:
                continue

            row_features = X_full.loc[[idx]]

            try:
                prediction, pred_meta = self._predict(row_features)
                if prediction is None:
                    degraded_conf = float(
                        pred_meta.get("conf", self.degraded_confidence)
                    )
                    logger.warning(
                        f"   Palm abstain on {idx}: nan_pct_latest={pred_meta.get('nan_pct_latest')}"
                    )
                    # P0-3: Skip pre-1990 dates
                    as_of = idx.date() if hasattr(idx, "date") else idx
                    if as_of < date(1990, 1, 1):
                        continue

                    signals.append(
                        SignalOutput(
                            as_of_date=as_of,
                            bucket="palm",
                            signal_1=0.0,
                            signal_2=0.0,  # CONTRACT: Never None on abstain
                            confidence=0.0,  # CONTRACT: Zero confidence on abstain
                            model_type="ridge",
                            max_input_age_days=999,  # P0-1: Abstain = max staleness
                            source_tag=pred_meta.get(
                                "source_tag", "insufficient_features"
                            ),
                            degraded_level=pred_meta.get("degraded_level", 2),
                            conf=degraded_conf,
                            data_quality={
                                "nan_pct_latest": pred_meta.get("nan_pct_latest"),
                                "missing_features": pred_meta.get("missing_features"),
                                "reason": pred_meta.get("reason"),
                            },
                            metadata={
                                "run_hash": run_hash,
                                "abstained": True,
                                "nan_pct_latest": pred_meta.get("nan_pct_latest"),
                                "missing_features": pred_meta.get("missing_features"),
                                "reason": pred_meta.get("reason"),
                            },
                        )
                    )
                    continue

                # REAL MODEL PREDICTION
                prediction = prediction[0]

                # Confidence based on cointegration and data quality
                base_confidence = 0.5 + (0.3 if is_coint else 0.0)

                # Boost for real FX data
                if myr_usd is not None:
                    base_confidence += 0.05

                # Boost for strong reversion speed
                speed = (
                    reversion_speed.loc[idx]
                    if not pd.isna(reversion_speed.loc[idx])
                    else 1.0
                )
                base_confidence += 0.05 * min(speed, 2)

                confidence = min(base_confidence, 0.95)

                # P0-3: Skip pre-1990 dates
                as_of = idx.date() if hasattr(idx, "date") else idx
                if as_of < date(1990, 1, 1):
                    continue

                # P0-1: Compute staleness for this row
                staleness = self.compute_max_staleness(
                    data, as_of, self.config.primary_features
                )

                # CONTRACT: signal_2 must never be None
                if not pd.isna(speed):
                    signal_2_val = float(speed)
                else:
                    signal_2_val = 0.0
                    # Penalty for missing secondary
                    confidence = confidence * 0.7

                signals.append(
                    SignalOutput(
                        as_of_date=as_of,
                        bucket="palm",
                        signal_1=float(prediction),  # MODEL PREDICTION
                        signal_2=signal_2_val,  # CONTRACT: Never None (reversion speed)
                        confidence=float(confidence),
                        model_type="ridge",
                        max_input_age_days=staleness,  # P0-1: Staleness tracking
                        metadata={
                            "spread_zscore": (
                                float(spread_zscore.loc[idx])
                                if not pd.isna(spread_zscore.loc[idx])
                                else None
                            ),
                            "reversion_speed": (
                                float(speed) if not pd.isna(speed) else None
                            ),
                            "is_cointegrated": is_coint,
                            "coint_pvalue": float(coint_pvalue),
                            "hedge_ratio": float(hedge_ratio) if hedge_ratio else None,
                            "has_real_fx": myr_usd is not None,
                            "model_trained": str(self.last_train_date),
                            "n_features": len(self.feature_names),
                            "run_hash": run_hash,
                        },
                    )
                )
            except Exception as e:
                logger.debug(f"   Skipping {idx}: {e}")
                continue

        logger.info(
            f"PalmSignalGenerator: Generated {len(signals)} signals (Ridge model, coint: {is_coint})"
        )
        return signals
