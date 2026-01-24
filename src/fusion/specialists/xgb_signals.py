"""
XGBoost/GBM/RF-based signal generators: crush, china, substitutes.

These specialists use REAL tree-based ML models trained on engineered features.

PATCHED 2026-01-23: Implemented actual ML models
- XGBoost for Crush
- GradientBoosting for China
- RandomForest for Substitutes
- Models train on features, predict forward returns
- Model persistence to models/specialists/{bucket}/
"""

from datetime import date
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
import pandas as pd
import numpy as np
import logging
import joblib
import hashlib

# ML Imports - REAL MODELS
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit

# XGBoost - install if missing
try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    xgb = None

from fusion.specialists.base import (
    BaseSignalGenerator,
    SignalConfig,
    SignalOutput,
)

logger = logging.getLogger(__name__)

# Model persistence directory
MODELS_DIR = Path(__file__).parent.parent.parent.parent / "models" / "specialists"


# =============================================================================
# ML MODEL BASE MIXIN
# =============================================================================

class MLModelMixin:
    """
    Mixin providing real ML model training, prediction, and persistence.

    All tree-based specialists inherit this for actual model operations.
    """

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names: List[str] = []
        self.last_train_date: Optional[date] = None
        self.train_frequency_days: int = 21  # Retrain monthly
        self.min_train_samples: int = 126  # ~6 months minimum
        self.target_horizon: int = 21  # Predict 21-day forward return

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
        """Create the ML model. Override in subclass."""
        raise NotImplementedError

    def _prepare_features(self, data: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """Prepare feature matrix. Override in subclass."""
        raise NotImplementedError

    def _train_model(self, data: pd.DataFrame, current_date: date):
        """
        Train the ML model on historical data.

        Uses expanding window: all data up to current_date.
        Target: forward return at target_horizon.
        """
        logger.info(f"   Training {self.bucket} model...")

        # Prepare features
        X, feature_names = self._prepare_features(data)
        self.feature_names = feature_names

        # Compute target: forward return
        y = self._compute_forward_return(data["close"], self.target_horizon)

        # Align X and y, drop NaN
        valid_mask = X.notna().all(axis=1) & y.notna()
        X_clean = X[valid_mask]
        y_clean = y[valid_mask]

        if len(X_clean) < self.min_train_samples:
            logger.warning(f"   Insufficient training data: {len(X_clean)} < {self.min_train_samples}")
            return False

        # Scale features
        X_scaled = self.scaler.fit_transform(X_clean)

        # Create and train model
        self.model = self._create_model()
        self.model.fit(X_scaled, y_clean)

        self.last_train_date = current_date

        # Log feature importances
        if hasattr(self.model, 'feature_importances_'):
            importances = dict(zip(feature_names, self.model.feature_importances_))
            top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:5]
            logger.info(f"   Top features: {top_features}")

        # Save model
        self._save_model()

        logger.info(f"   Trained on {len(X_clean)} samples, {len(feature_names)} features")
        return True

    def _predict(self, features: pd.DataFrame) -> np.ndarray:
        """Generate predictions from trained model."""
        if self.model is None:
            raise ValueError("Model not trained")

        # Ensure feature order matches training
        X = features[self.feature_names] if self.feature_names else features
        X_scaled = self.scaler.transform(X.fillna(0))
        return self.model.predict(X_scaled)


# =============================================================================
# CRUSH SIGNAL GENERATOR - REAL XGBOOST
# =============================================================================

class CrushSignalGenerator(BaseSignalGenerator, MLModelMixin):
    """
    Crush specialist: margin-driven production incentives.

    ACTUAL MODEL: XGBoost Regressor

    Signal Contract:
    - signal_1: Model prediction of forward ZL return based on crush features
    - signal_2: 21-day crush momentum (rate of change)

    Features:
    - Board crush z-score
    - Oil share z-score
    - Crush momentum (multiple horizons)
    - WASDE fundamentals (when available)
    - Volume/OI indicators

    Target: 21-day forward ZL return

    PATCHED 2026-01-21: WASDE fundamentals
    PATCHED 2026-01-23: Real XGBoost model
    """

    def __init__(self):
        config = SignalConfig(
            bucket="crush",
            model_type="xgb",
            primary_features=["close", "zs_close", "zm_close"],
            secondary_features=[
                "volume", "open_interest",
                "wasde_soybean_oil_ending_stocks",
                "wasde_soybean_oil_production",
                "wasde_soybeans_crush",
            ],
            lookback_days=252,
            min_data_points=63,
        )
        BaseSignalGenerator.__init__(self, config)
        MLModelMixin.__init__(self)

    def _create_model(self):
        """Create XGBoost model."""
        if HAS_XGBOOST:
            return xgb.XGBRegressor(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1,
            )
        else:
            # Fallback to sklearn GradientBoosting if XGBoost not installed
            logger.warning("XGBoost not installed, using sklearn GradientBoosting")
            return GradientBoostingRegressor(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.1,
                subsample=0.8,
                random_state=42,
            )

    def _prepare_features(self, data: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """Prepare crush-specific features."""
        features = {}

        zl = data["close"]
        zs = data["zs_close"]
        zm = data["zm_close"]

        # Core crush calculations
        board_crush = (zs * 11) - (zl * 11) - zm
        oil_share = (zl * 11) / ((zl * 11) + zm)

        # Z-scores
        features["crush_zscore"] = self.compute_zscore(board_crush, window=252, min_periods=63)
        features["oil_share_zscore"] = self.compute_zscore(oil_share, window=252, min_periods=63)

        # Momentum at multiple horizons
        features["crush_mom_5d"] = board_crush.pct_change(5, fill_method=None)
        features["crush_mom_21d"] = board_crush.pct_change(21, fill_method=None)
        features["crush_mom_63d"] = board_crush.pct_change(63, fill_method=None)

        # Oil share momentum
        features["oil_share_mom_21d"] = oil_share.pct_change(21, fill_method=None)

        # Rolling volatility
        features["crush_vol_21d"] = board_crush.pct_change(fill_method=None).rolling(21).std()

        # Volume/OI if available
        if "volume" in data.columns:
            features["volume_zscore"] = self.compute_zscore(data["volume"], window=63)
        if "open_interest" in data.columns:
            features["oi_zscore"] = self.compute_zscore(data["open_interest"], window=63)

        # WASDE features if available
        for col in data.columns:
            if 'wasde' in col.lower():
                features[f"{col}_zscore"] = self.compute_zscore(data[col], window=24, min_periods=12)

        df = pd.DataFrame(features, index=data.index)
        return df, list(df.columns)

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute crush signals using XGBoost model.
        """
        signals = []

        # Try to load existing model
        if not self._load_model():
            logger.info("   No existing model, will train on first pass")

        # Prepare features for entire dataset
        X_full, feature_names = self._prepare_features(data)

        # Get the most recent date with valid data
        last_valid_idx = X_full.dropna().index[-1] if len(X_full.dropna()) > 0 else None

        if last_valid_idx is None:
            logger.warning("CrushSignalGenerator: No valid data")
            return signals

        current_date = last_valid_idx.date() if hasattr(last_valid_idx, 'date') else last_valid_idx

        # Check if retraining needed
        if self._should_retrain(current_date):
            # Use data up to current_date for training
            train_data = data[data.index <= last_valid_idx]
            self._train_model(train_data, current_date)

        if self.model is None:
            logger.warning("CrushSignalGenerator: Model not trained")
            return signals

        # Compute auxiliary signals for signal_2 and metadata
        zl = data["close"]
        zs = data["zs_close"]
        zm = data["zm_close"]
        board_crush = (zs * 11) - (zl * 11) - zm
        # Lag by 1 day to prevent leakage: signal at t uses data up to t-1
        crush_momentum = board_crush.pct_change(periods=21).shift(1) * 100
        oil_share = (zl * 11) / ((zl * 11) + zm)
        oil_share_zscore = self.compute_zscore(oil_share, window=252, min_periods=63)

        # Generate predictions for each valid date
        for idx in data.index:
            if idx not in X_full.index:
                continue

            row_features = X_full.loc[[idx]]
            if row_features.isna().any().any():
                continue

            try:
                # REAL MODEL PREDICTION
                prediction = self._predict(row_features)[0]

                # Confidence from model's feature importance weighted by feature values
                base_confidence = 0.6
                if hasattr(self.model, 'feature_importances_') and self.feature_names:
                    # Use only the features the model was trained on
                    model_features = row_features[self.feature_names]
                    importance_weighted = np.abs(model_features.values[0]) * self.model.feature_importances_
                    confidence_boost = min(np.mean(importance_weighted) * 0.2, 0.3)
                    base_confidence += confidence_boost

                confidence = min(base_confidence, 0.95)

                signals.append(SignalOutput(
                    as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                    bucket="crush",
                    signal_1=float(prediction),  # MODEL PREDICTION
                    signal_2=float(crush_momentum.loc[idx]) if not pd.isna(crush_momentum.loc[idx]) else None,
                    confidence=float(confidence),
                    model_type="xgb",
                    metadata={
                        "board_crush": float(board_crush.loc[idx]),
                        "oil_share": float(oil_share.loc[idx]),
                        "model_trained": str(self.last_train_date),
                        "n_features": len(self.feature_names),
                        "run_hash": run_hash,
                    },
                ))
            except Exception as e:
                logger.debug(f"   Skipping {idx}: {e}")
                continue

        logger.info(f"CrushSignalGenerator: Generated {len(signals)} signals (XGBoost model)")
        return signals


# =============================================================================
# SUBSTITUTES SIGNAL GENERATOR - REAL RANDOM FOREST
# =============================================================================

class SubstitutesSignalGenerator(BaseSignalGenerator, MLModelMixin):
    """
    Substitutes specialist: switching behavior among soft oils.

    ACTUAL MODEL: Random Forest Regressor

    Signal Contract:
    - signal_1: Model prediction of forward ZL return based on relative value features
    - signal_2: ZL richness score (how expensive ZL is vs substitutes)

    Features:
    - Spread z-scores vs each substitute
    - Ratio z-scores vs each substitute
    - Spread momentum
    - Cross-correlations

    Target: 21-day forward ZL return

    PATCHED 2026-01-21: Relative value matrix
    PATCHED 2026-01-23: Real RandomForest model
    """

    def __init__(self):
        config = SignalConfig(
            bucket="substitutes",
            model_type="rf",
            primary_features=["close"],
            secondary_features=[
                "rs_close",
                "cpo_close",
                "sunflower_close",
                "rapeseed_close",
            ],
            lookback_days=252,
            min_data_points=63,
        )
        BaseSignalGenerator.__init__(self, config)
        MLModelMixin.__init__(self)

    def _create_model(self):
        """Create RandomForest model."""
        return RandomForestRegressor(
            n_estimators=100,
            max_depth=6,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
        )

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Override to allow partial secondary features."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")
        # At least one substitute must be present
        substitutes = ["rs_close", "cpo_close", "sunflower_close", "rapeseed_close"]
        available = [s for s in substitutes if s in data.columns]
        if not available:
            missing.append("at_least_one_substitute")
        return missing

    def _prepare_features(self, data: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """Prepare substitutes-specific features."""
        features = {}
        zl = data["close"]

        substitutes = {
            "rs": ("rs_close", 1.0),  # Canola - same units
            "cpo": ("cpo_close", 88.0),  # Palm - MYR/MT to cents/lb approximation
            "sunf": ("sunflower_close", 1.0),
            "rape": ("rapeseed_close", 1.0),
        }

        for name, (col, divisor) in substitutes.items():
            if col in data.columns and data[col].notna().sum() > 30:
                sub_price = data[col] / divisor

                # Spread
                spread = zl - sub_price
                features[f"spread_{name}_zscore"] = self.compute_zscore(spread, window=126, min_periods=42)
                # Lag by 1 day to prevent leakage
                features[f"spread_{name}_mom_21d"] = spread.pct_change(21, fill_method=None).shift(1)

                # Ratio
                ratio = zl / sub_price.replace(0, np.nan)
                features[f"ratio_{name}_zscore"] = self.compute_zscore(ratio, window=252, min_periods=63)

                # Correlation
                features[f"corr_{name}_63d"] = zl.rolling(63).corr(sub_price)

        # ZL momentum (lagged to prevent leakage)
        features["zl_mom_5d"] = zl.pct_change(5, fill_method=None).shift(1)
        features["zl_mom_21d"] = zl.pct_change(21, fill_method=None).shift(1)
        features["zl_vol_21d"] = zl.pct_change(fill_method=None).rolling(21).std()

        df = pd.DataFrame(features, index=data.index)
        return df, list(df.columns)

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute substitutes signals using RandomForest model.
        """
        signals = []

        # Try to load existing model
        if not self._load_model():
            logger.info("   No existing model, will train on first pass")

        # Prepare features
        X_full, feature_names = self._prepare_features(data)

        last_valid_idx = X_full.dropna().index[-1] if len(X_full.dropna()) > 0 else None
        if last_valid_idx is None:
            logger.warning("SubstitutesSignalGenerator: No valid data")
            return signals

        current_date = last_valid_idx.date() if hasattr(last_valid_idx, 'date') else last_valid_idx

        # Check if retraining needed
        if self._should_retrain(current_date):
            train_data = data[data.index <= last_valid_idx]
            self._train_model(train_data, current_date)

        if self.model is None:
            logger.warning("SubstitutesSignalGenerator: Model not trained")
            return signals

        # Compute richness score for signal_2 (mean of ratio z-scores)
        ratio_cols = [c for c in X_full.columns if c.startswith("ratio_")]
        richness = X_full[ratio_cols].mean(axis=1) if ratio_cols else pd.Series(np.nan, index=data.index)

        # Count available substitutes
        spread_cols = [c for c in X_full.columns if c.startswith("spread_") and "zscore" in c]

        for idx in data.index:
            if idx not in X_full.index:
                continue

            row_features = X_full.loc[[idx]]
            if row_features.isna().any().any():
                continue

            try:
                # REAL MODEL PREDICTION
                prediction = self._predict(row_features)[0]

                # Confidence based on number of substitutes and feature importance
                n_subs = sum(1 for c in spread_cols if not pd.isna(row_features[c].values[0]))
                base_confidence = min(n_subs / 4, 1.0) * 0.6 + 0.3

                signals.append(SignalOutput(
                    as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                    bucket="substitutes",
                    signal_1=float(prediction),  # MODEL PREDICTION
                    signal_2=float(richness.loc[idx]) if not pd.isna(richness.loc[idx]) else None,
                    confidence=float(min(base_confidence, 0.95)),
                    model_type="rf",
                    metadata={
                        "n_substitutes": n_subs,
                        "model_trained": str(self.last_train_date),
                        "n_features": len(self.feature_names),
                        "run_hash": run_hash,
                    },
                ))
            except Exception as e:
                logger.debug(f"   Skipping {idx}: {e}")
                continue

        logger.info(f"SubstitutesSignalGenerator: Generated {len(signals)} signals (RandomForest model)")
        return signals


# =============================================================================
# CHINA SIGNAL GENERATOR - REAL GRADIENT BOOSTING
# =============================================================================

class ChinaSignalGenerator(BaseSignalGenerator, MLModelMixin):
    """
    China specialist: demand shifts and shipment intensity.

    ACTUAL MODEL: Gradient Boosting Regressor

    Signal Contract:
    - signal_1: Model prediction of forward ZL return based on China demand features
    - signal_2: Brazil competition signal (BRL weakness = bearish US exports)

    Features:
    - Copper z-score (demand proxy)
    - CNY z-score (import capacity)
    - BRL z-score (Brazil competition)
    - BDRY shipping z-score (shipping demand)
    - Seasonality encoding
    - Cross-correlations

    Target: 21-day forward ZL return

    PATCHED 2026-01-21: Brazil competition, seasonality
    PATCHED 2026-01-23: BDRY shipping, Real GBM model
    """

    # China soybean import seasonality (empirical weights)
    CHINA_SEASONALITY = {
        1: 1.15, 2: 1.10, 3: 1.05, 4: 0.85, 5: 0.80, 6: 0.85,
        7: 0.90, 8: 0.95, 9: 1.00, 10: 1.10, 11: 1.15, 12: 1.20
    }

    def __init__(self):
        config = SignalConfig(
            bucket="china",
            model_type="gbm",
            primary_features=["close", "hg_close"],
            secondary_features=[
                "usd_cny",
                "fred_dexbzus",
                "fx_usdbrl",
                "bdry_close",
                "sblk_close",
                "dalian_soy",
                "china_pmi",
            ],
            lookback_days=252,
            min_data_points=63,
        )
        BaseSignalGenerator.__init__(self, config)
        MLModelMixin.__init__(self)

    def _create_model(self):
        """Create GradientBoosting model."""
        return GradientBoostingRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            min_samples_split=10,
            random_state=42,
        )

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Copper is required; others optional."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")
        if "hg_close" not in data.columns:
            missing.append("hg_close")
        return missing

    def _get_brl_column(self, data: pd.DataFrame) -> Optional[str]:
        """Find BRL column."""
        for col in ["fred_dexbzus", "fx_usdbrl", "usdbrl", "brl_close"]:
            if col in data.columns and data[col].notna().sum() > 30:
                return col
        return None

    def _get_shipping_column(self, data: pd.DataFrame) -> Optional[str]:
        """Find shipping column."""
        for col in ["bdry_close", "sblk_close"]:
            if col in data.columns and data[col].notna().sum() > 30:
                return col
        return None

    def _prepare_features(self, data: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """Prepare China-specific features."""
        features = {}

        zl = data["close"]
        hg = data["hg_close"]

        # Copper features (primary demand proxy)
        features["hg_zscore"] = self.compute_zscore(hg, window=126, min_periods=42)
        features["hg_mom_5d"] = hg.pct_change(5, fill_method=None)
        features["hg_mom_21d"] = hg.pct_change(21, fill_method=None)
        features["hg_vol_21d"] = hg.pct_change(fill_method=None).rolling(21).std()

        # ZL-Copper correlation
        features["zl_hg_corr_63d"] = zl.rolling(63).corr(hg)

        # CNY features
        if "usd_cny" in data.columns:
            cny = data["usd_cny"]
            features["cny_zscore"] = self.compute_zscore(cny, window=126, min_periods=42)
            features["cny_mom_21d"] = cny.pct_change(21, fill_method=None)

        # BRL features (Brazil competition)
        brl_col = self._get_brl_column(data)
        if brl_col:
            brl = data[brl_col]
            # FRED format is foreign/USD, invert for USD/foreign
            if "dexbzus" in brl_col.lower():
                brl = 1 / brl
            features["brl_zscore"] = self.compute_zscore(brl, window=126, min_periods=42)
            features["brl_mom_21d"] = brl.pct_change(21, fill_method=None)

        # Shipping features
        ship_col = self._get_shipping_column(data)
        if ship_col:
            ship = data[ship_col]
            features["shipping_zscore"] = self.compute_zscore(ship, window=126, min_periods=42)
            features["shipping_mom_21d"] = ship.pct_change(21, fill_method=None)
            features["shipping_vol_21d"] = ship.pct_change(fill_method=None).rolling(21).std()

        # Seasonality features (one-hot encoded months)
        features["month_sin"] = np.sin(2 * np.pi * pd.to_datetime(data.index).month / 12)
        features["month_cos"] = np.cos(2 * np.pi * pd.to_datetime(data.index).month / 12)

        # Seasonality weight
        seasonality = pd.Series(index=data.index, dtype=float)
        for idx in data.index:
            month = pd.to_datetime(idx).month
            seasonality.loc[idx] = self.CHINA_SEASONALITY.get(month, 1.0) - 1.0
        features["seasonality"] = seasonality

        df = pd.DataFrame(features, index=data.index)
        return df, list(df.columns)

    def _compute_brazil_competition(self, data: pd.DataFrame) -> Tuple[pd.Series, bool]:
        """Compute Brazil competition z-score for signal_2."""
        brl_col = self._get_brl_column(data)
        if brl_col is None:
            return pd.Series(0.0, index=data.index), False

        brl = data[brl_col]
        if "dexbzus" in brl_col.lower():
            brl = 1 / brl

        return self.compute_zscore(brl, window=126, min_periods=42), True

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute China demand signals using GradientBoosting model.
        """
        signals = []

        # Try to load existing model
        if not self._load_model():
            logger.info("   No existing model, will train on first pass")

        # Prepare features
        X_full, feature_names = self._prepare_features(data)

        last_valid_idx = X_full.dropna().index[-1] if len(X_full.dropna()) > 0 else None
        if last_valid_idx is None:
            logger.warning("ChinaSignalGenerator: No valid data")
            return signals

        current_date = last_valid_idx.date() if hasattr(last_valid_idx, 'date') else last_valid_idx

        # Check if retraining needed
        if self._should_retrain(current_date):
            train_data = data[data.index <= last_valid_idx]
            self._train_model(train_data, current_date)

        if self.model is None:
            logger.warning("ChinaSignalGenerator: Model not trained")
            return signals

        # Compute Brazil competition for signal_2
        brazil_zscore, has_brazil = self._compute_brazil_competition(data)

        # Check data sources
        has_cny = "cny_zscore" in X_full.columns
        has_shipping = "shipping_zscore" in X_full.columns

        # ZL-Copper correlation for confidence
        zl = data["close"]
        hg = data["hg_close"]
        zl_hg_corr = zl.rolling(63).corr(hg)

        for idx in data.index:
            if idx not in X_full.index:
                continue

            row_features = X_full.loc[[idx]]
            if row_features.isna().any().any():
                continue

            try:
                # REAL MODEL PREDICTION
                prediction = self._predict(row_features)[0]

                # Confidence based on correlation and data availability
                corr = zl_hg_corr.loc[idx] if not pd.isna(zl_hg_corr.loc[idx]) else 0.3
                base_confidence = max(0.3, min(abs(corr), 0.6))
                if has_cny:
                    base_confidence += 0.1
                if has_brazil:
                    base_confidence += 0.1
                if has_shipping:
                    base_confidence += 0.1

                signals.append(SignalOutput(
                    as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                    bucket="china",
                    signal_1=float(prediction),  # MODEL PREDICTION
                    signal_2=float(brazil_zscore.loc[idx]) if has_brazil and not pd.isna(brazil_zscore.loc[idx]) else None,
                    confidence=float(min(base_confidence, 0.95)),
                    model_type="gbm",
                    metadata={
                        "has_brazil": has_brazil,
                        "has_cny": has_cny,
                        "has_shipping": has_shipping,
                        "model_trained": str(self.last_train_date),
                        "n_features": len(self.feature_names),
                        "run_hash": run_hash,
                    },
                ))
            except Exception as e:
                logger.debug(f"   Skipping {idx}: {e}")
                continue

        logger.info(f"ChinaSignalGenerator: Generated {len(signals)} signals (GBM model, brazil: {has_brazil}, shipping: {has_shipping})")
        return signals
