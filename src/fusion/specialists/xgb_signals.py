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
import os
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

        FIX 2026-01-30: Use coverage-based feature filtering instead of requiring
        ALL features to be non-NaN. With 80+ elite indicators (many needing warmup),
        the old approach dropped all rows.
        """
        logger.info(f"   Training {self.bucket} model...")

        # Prepare features
        X, feature_names = self._prepare_features(data)

        # Compute target: forward return
        y = self._compute_forward_return(data["close"], self.target_horizon)

        # FIX: Filter to features with sufficient coverage (>50% non-NaN)
        # Then require only those features to be non-NaN per row
        coverage = X.notna().mean()
        usable_features = coverage[coverage > 0.5].index.tolist()

        if len(usable_features) < 5:
            logger.warning(f"   Too few usable features: {len(usable_features)}")
            return False

        logger.info(f"   Using {len(usable_features)}/{len(feature_names)} features with >50% coverage")

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

        # Scale features
        X_scaled = self.scaler.fit_transform(X_clean)

        # Create and train model
        self.model = self._create_model()
        self.model.fit(X_scaled, y_clean)

        self.last_train_date = current_date

        # Log feature importances
        # FIX 2026-02-03: Use self.feature_names (trained features) not feature_names (all features)
        if hasattr(self.model, "feature_importances_"):
            importances = dict(zip(self.feature_names, self.model.feature_importances_))
            top_features = sorted(
                importances.items(), key=lambda x: x[1], reverse=True
            )[:5]
            logger.info(f"   Top features: {top_features}")

        # Save model
        self._save_model()

        logger.info(
            f"   Trained on {len(X_clean)} samples, {len(feature_names)} features"
        )
        return True

    def _predict(
        self, features: pd.DataFrame
    ) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
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
        # Cross-market data (CPO/RS vs ZL) has calendar misalignment
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
            primary_features=[
                "close",
                # SOYBEAN COMPLEX - Full crush calculation inputs
                "zs_close",  # Soybeans (feedstock)
                "zm_close",  # Soybean Meal (byproduct)
                # MARKET MICROSTRUCTURE
                "volume",  # ZL volume (liquidity)
                "open_interest",  # ZL open interest (positioning)
            ],
            secondary_features=[
                # WASDE FUNDAMENTALS - Supply/demand balance
                "wasde_soybean_oil_ending_stocks",
                "wasde_soybean_oil_production",
                "wasde_soybeans_crush",
                "wasde_soybean_oil_exports",
                "wasde_soybean_oil_domestic_consumption",
                # Extended complex
                "zs_volume",  # Soybeans volume
                "zm_volume",  # Meal volume
                "zs_open_interest",  # Soybeans OI
                "zm_open_interest",  # Meal OI
                # CFTC positioning
                "cftc_zl_net_spec",  # ZL speculator positioning
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
        """Prepare crush-specific features with ALL elite indicators."""
        features = {}

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL, ZS, ZM
        # =====================================================================
        # ZL elite indicators
        data = self.add_all_elite_indicators(data, "close", "zl")

        # ZS elite indicators
        if "zs_close" in data.columns:
            zs_data = data.copy()
            zs_data["close"] = data["zs_close"]
            if "zs_high" in data.columns:
                zs_data["zs_high_temp"] = data["zs_high"]
            if "zs_low" in data.columns:
                zs_data["zs_low_temp"] = data["zs_low"]
            if "zs_volume" in data.columns:
                zs_data["zs_volume_temp"] = data["zs_volume"]
            zs_data = self.add_all_elite_indicators(zs_data, "close", "zs")
            for col in zs_data.columns:
                if col.startswith("zs_") and col not in data.columns:
                    data[col] = zs_data[col]

        # ZM elite indicators
        if "zm_close" in data.columns:
            zm_data = data.copy()
            zm_data["close"] = data["zm_close"]
            zm_data = self.add_all_elite_indicators(zm_data, "close", "zm")
            for col in zm_data.columns:
                if col.startswith("zm_") and col not in data.columns:
                    data[col] = zm_data[col]

        zl = data["close"]
        zs = data["zs_close"]
        zm = data["zm_close"]

        # Core crush calculations (CME standard formula)
        # 1 bushel soybeans (60 lbs) yields 11 lbs oil + 44 lbs meal (48% protein)
        # Board Crush = (ZL × 0.11) + (ZM × 0.022) - (ZS / 100)
        # Oil Share = (ZL × 0.11) / ((ZL × 0.11) + (ZM × 0.022))
        oil_value = zl * 0.11  # 11 lbs oil per bushel
        meal_value = zm * 0.022  # 44 lbs meal / 2000 lbs per ton
        board_crush = (oil_value + meal_value) - (zs / 100)
        oil_share = oil_value / (oil_value + meal_value)

        # Z-scores (126-day = ~6 months rolling window)
        features["crush_zscore"] = self.compute_zscore(
            board_crush, window=126, min_periods=63
        )
        features["oil_share_zscore"] = self.compute_zscore(
            oil_share, window=126, min_periods=63
        )

        # Crush margin regime classification (signal enhancement)
        # Regime: -2=very_low, -1=low, 0=neutral, 1=high, 2=very_high
        crush_z = features["crush_zscore"]
        features["crush_margin_regime"] = pd.cut(
            crush_z,
            bins=[-np.inf, -1.5, -0.5, 0.5, 1.5, np.inf],
            labels=[-2, -1, 0, 1, 2],
        ).astype(float)

        # Momentum at multiple horizons
        features["crush_mom_5d"] = board_crush.pct_change(5, fill_method=None)
        features["crush_mom_21d"] = board_crush.pct_change(21, fill_method=None)
        features["crush_mom_63d"] = board_crush.pct_change(63, fill_method=None)

        # Oil share momentum
        features["oil_share_mom_21d"] = oil_share.pct_change(21, fill_method=None)

        # Rolling volatility
        features["crush_vol_21d"] = (
            board_crush.pct_change(fill_method=None).rolling(21).std()
        )

        # Volume/OI if available
        if "volume" in data.columns:
            features["volume_zscore"] = self.compute_zscore(data["volume"], window=63)
        if "open_interest" in data.columns:
            features["oi_zscore"] = self.compute_zscore(
                data["open_interest"], window=63
            )

        # WASDE features if available
        for col in data.columns:
            if "wasde" in col.lower():
                features[f"{col}_zscore"] = self.compute_zscore(
                    data[col], window=24, min_periods=12
                )

        # ADD ALL ZL/ZS/ZM ELITE INDICATORS TO FEATURES
        for col in data.columns:
            if col.startswith("zl_") or col.startswith("zs_") or col.startswith("zm_"):
                if col not in features:
                    features[col] = data[col]

        # OPTIONS FEATURES (if available) - NO GREEKS, just raw volume/ratios
        # Put/call ratio and volume z-scores for ZL, ZS, ZM
        for ul in ['zl', 'zs', 'zm']:
            pc_col = f'{ul}_put_call_ratio'
            if pc_col in data.columns:
                features[f'{ul}_pc_ratio_zscore'] = self.compute_zscore(data[pc_col], window=63)

            call_vol_col = f'{ul}_call_volume'
            if call_vol_col in data.columns:
                features[f'{ul}_call_vol_zscore'] = self.compute_zscore(data[call_vol_col], window=63)

            put_vol_col = f'{ul}_put_volume'
            if put_vol_col in data.columns:
                features[f'{ul}_put_vol_zscore'] = self.compute_zscore(data[put_vol_col], window=63)

            # Premium z-scores (average option premium)
            call_prem_col = f'{ul}_call_premium'
            if call_prem_col in data.columns:
                features[f'{ul}_call_prem_zscore'] = self.compute_zscore(data[call_prem_col], window=63)

            put_prem_col = f'{ul}_put_premium'
            if put_prem_col in data.columns:
                features[f'{ul}_put_prem_zscore'] = self.compute_zscore(data[put_prem_col], window=63)

            # Open interest z-scores
            call_oi_col = f'{ul}_call_oi'
            if call_oi_col in data.columns:
                features[f'{ul}_call_oi_zscore'] = self.compute_zscore(data[call_oi_col], window=63)

            put_oi_col = f'{ul}_put_oi'
            if put_oi_col in data.columns:
                features[f'{ul}_put_oi_zscore'] = self.compute_zscore(data[put_oi_col], window=63)

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
        # FIX 2026-01-30: Only require primary features to be non-NaN (not all elite indicators)
        core_cols = [c for c in self.config.primary_features if c in X_full.columns]
        X_valid = X_full.dropna(subset=core_cols) if core_cols else X_full.dropna()
        last_valid_idx = X_valid.index[-1] if len(X_valid) > 0 else None

        if last_valid_idx is None:
            logger.warning("CrushSignalGenerator: No valid data after dropna(subset=primary_features)")
            return signals

        current_date = (
            last_valid_idx.date() if hasattr(last_valid_idx, "date") else last_valid_idx
        )

        # Check if retraining needed
        if self._should_retrain(current_date):
            # Use data up to current_date for training
            train_data = data[data.index <= last_valid_idx]
            self._train_model(train_data, current_date)

        if self.model is None:
            logger.warning("CrushSignalGenerator: Model not trained")
            return signals

        # Compute auxiliary signals for signal_2 and metadata
        # Using CME standard formula
        zl = data["close"]
        zs = data["zs_close"]
        zm = data["zm_close"]
        oil_value = zl * 0.11
        meal_value = zm * 0.022
        board_crush = (oil_value + meal_value) - (zs / 100)
        # FIX 2026-02-03: Removed erroneous .shift(1) that created timing mismatch
        # pct_change(21) already uses backward-looking data [T-21, T]
        # signal_2 should use same timing as signal_1 (features at T for signal at T)
        crush_momentum = board_crush.pct_change(periods=21) * 100
        oil_share = oil_value / (oil_value + meal_value)
        oil_share_zscore = self.compute_zscore(oil_share, window=126, min_periods=63)

        # Generate predictions for each valid date
        for idx in data.index:
            if idx not in X_full.index:
                continue

            row_features = X_full.loc[[idx]]
            # Only check NaN in features the model uses (not all columns)
            try:
                prediction, pred_meta = self._predict(row_features)
                if prediction is None:
                    degraded_conf = float(
                        pred_meta.get("conf", self.degraded_confidence)
                    )
                    logger.warning(
                        f"   Crush abstain on {idx}: nan_pct_latest={pred_meta.get('nan_pct_latest')}"
                    )
                    as_of = idx.date() if hasattr(idx, "date") else idx
                    # P0-3: Skip dates before EARLIEST_VALID_DATE
                    if as_of < date(1990, 1, 1):
                        continue
                    signals.append(
                        SignalOutput(
                            as_of_date=as_of,
                            bucket="crush",
                            signal_1=0.0,
                            signal_2=0.0,  # CONTRACT: Never None on abstain
                            confidence=0.0,  # CONTRACT: Zero confidence on abstain
                            model_type="xgb",
                            max_input_age_days=999,  # P0-1: Max staleness for abstain
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

                # Confidence from model's feature importance weighted by feature values
                base_confidence = 0.6
                if hasattr(self.model, "feature_importances_") and self.feature_names:
                    # Use only the features the model was trained on
                    model_features = row_features[self.feature_names]
                    importance_weighted = (
                        np.abs(model_features.values[0])
                        * self.model.feature_importances_
                    )
                    confidence_boost = min(np.mean(importance_weighted) * 0.2, 0.3)
                    base_confidence += confidence_boost

                confidence = min(base_confidence, 0.95)

                as_of = idx.date() if hasattr(idx, "date") else idx
                # P0-3: Skip dates before EARLIEST_VALID_DATE
                if as_of < date(1990, 1, 1):
                    continue

                # P0-1: Compute max staleness for this date
                max_staleness = self.compute_max_staleness(data, as_of)

                # CONTRACT: signal_2 must never be None
                secondary_val = crush_momentum.loc[idx]
                if pd.isna(secondary_val):
                    signal_2_val = 0.0
                    confidence = confidence * 0.7  # Penalty for missing secondary
                    secondary_missing = True
                else:
                    signal_2_val = float(secondary_val)
                    secondary_missing = False

                signals.append(
                    SignalOutput(
                        as_of_date=as_of,
                        bucket="crush",
                        signal_1=float(prediction),  # MODEL PREDICTION
                        signal_2=signal_2_val,  # CONTRACT: Never None
                        confidence=float(confidence),
                        model_type="xgb",
                        max_input_age_days=max_staleness,  # P0-1: Staleness tracking
                        metadata={
                            "board_crush": float(board_crush.loc[idx]),
                            "oil_share": float(oil_share.loc[idx]),
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
            f"CrushSignalGenerator: Generated {len(signals)} signals (XGBoost model)"
        )
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
            primary_features=[
                "close",
                # SUBSTITUTE OILS COMPLEX - Full relative value
                "cpo_close",  # Crude Palm Oil (Malaysia)
                "rs_close",  # Canola/Rapeseed (Canada)
                "sunflower_close",  # Sunflower Oil (Ukraine/Russia)
                "rapeseed_close",  # Rapeseed (EU)
            ],
            secondary_features=[
                # Extended substitutes
                "corn_oil_close",  # Corn oil (US)
                "cotton_oil_close",  # Cottonseed oil
                # FX for conversion
                "fred_dexmaus",  # MYR/USD (palm conversion)
                "fred_dexcaus",  # CAD/USD (canola conversion)
                # Cross-commodity
                "zs_close",  # Soybeans (feedstock arbitrage)
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
        """Require core substitute oils (CPO, RS daily). Sunflower/rapeseed are monthly."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")
        # REQUIRE daily substitutes
        if "cpo_close" not in data.columns:
            missing.append("cpo_close")
        if "rs_close" not in data.columns:
            missing.append("rs_close")
        # sunflower_close and rapeseed_close are MONTHLY data (48 unique values)
        # Used for spread/ratio only, not elite indicators
        return missing

    def _prepare_features(self, data: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """Prepare substitutes-specific features with ALL elite indicators."""
        features = {}
        zl = data["close"]

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL AND ALL SUBSTITUTES
        # =====================================================================
        data = self.add_all_elite_indicators(data, "close", "zl")

        substitutes = {
            "rs": ("rs_close", 1.0),  # Canola - same units
            "cpo": ("cpo_close", 88.0),  # Palm - MYR/MT to cents/lb approximation
            "sunf": ("sunflower_close", 1.0),
            "rape": ("rapeseed_close", 1.0),
        }

        for name, (col, divisor) in substitutes.items():
            if col in data.columns and data[col].notna().sum() > 30:
                # Check if daily data (>100 unique values) or monthly (~48)
                is_daily = data[col].nunique() > 100

                # ADD ELITE INDICATORS ONLY FOR DAILY DATA (CPO, RS)
                if is_daily:
                    sub_data = data.copy()
                    sub_data["close"] = data[col]
                    sub_data = self.add_all_elite_indicators(sub_data, "close", name)
                    for c in sub_data.columns:
                        if c.startswith(f"{name}_") and c not in data.columns:
                            data[c] = sub_data[c]

                sub_price = data[col] / divisor

                # Spread (works for both daily and monthly)
                spread = zl - sub_price
                features[f"spread_{name}_zscore"] = self.compute_zscore(
                    spread, window=126, min_periods=42
                )
                if is_daily:  # Only compute momentum for daily data
                    # FIX 2026-02-03: Removed .shift(1) - pct_change is already backward-looking
                    features[f"spread_{name}_mom_21d"] = spread.pct_change(
                        21, fill_method=None
                    )

                # Ratio (works for both)
                ratio = zl / sub_price.replace(0, np.nan)
                features[f"ratio_{name}_zscore"] = self.compute_zscore(
                    ratio, window=252, min_periods=63
                )

                # Correlation (only for daily data with sufficient variance)
                if is_daily:
                    features[f"corr_{name}_63d"] = zl.rolling(63, min_periods=30).corr(
                        sub_price
                    )

        # ADD ALL ELITE INDICATORS TO FEATURES (deterministic, no filtering)
        for col in data.columns:
            if col.startswith("zl_") or col.startswith("rs_") or col.startswith("cpo_"):
                # Note: sunf_ and rape_ elite indicators not added (monthly data)
                if col not in features:
                    features[col] = data[col]

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

        # FIX 2026-02-03: Removed erroneous X_full.shift(1)
        # Rolling features (z-scores, momentum, correlations) are already backward-looking
        # For EOD signal generation, using T's data for signal at T is correct
        # The previous "P0-4 FIX" was overly conservative and reduced signal freshness

        # FIX 2026-01-30: Only require primary features to be non-NaN (not all elite indicators)
        core_cols = [c for c in self.config.primary_features if c in X_full.columns]
        X_valid = X_full.dropna(subset=core_cols) if core_cols else X_full.dropna()
        last_valid_idx = X_valid.index[-1] if len(X_valid) > 0 else None
        if last_valid_idx is None:
            logger.warning("SubstitutesSignalGenerator: No valid data after dropna(subset=primary_features)")
            return signals

        current_date = (
            last_valid_idx.date() if hasattr(last_valid_idx, "date") else last_valid_idx
        )

        # Check if retraining needed
        if self._should_retrain(current_date):
            train_data = data[data.index <= last_valid_idx]
            self._train_model(train_data, current_date)

        if self.model is None:
            logger.warning("SubstitutesSignalGenerator: Model not trained")
            return signals

        # Compute richness score for signal_2 (mean of ratio z-scores)
        ratio_cols = [c for c in X_full.columns if c.startswith("ratio_")]
        richness = (
            X_full[ratio_cols].mean(axis=1)
            if ratio_cols
            else pd.Series(np.nan, index=data.index)
        )

        # Count available substitutes
        spread_cols = [
            c for c in X_full.columns if c.startswith("spread_") and "zscore" in c
        ]

        for idx in data.index:
            if idx not in X_full.index:
                continue

            row_features = X_full.loc[[idx]]
            # Only check NaN in features the model uses (not all columns)
            try:
                prediction, pred_meta = self._predict(row_features)
                if prediction is None:
                    degraded_conf = float(
                        pred_meta.get("conf", self.degraded_confidence)
                    )
                    logger.warning(
                        f"   Substitutes abstain on {idx}: nan_pct_latest={pred_meta.get('nan_pct_latest')}"
                    )
                    as_of = idx.date() if hasattr(idx, "date") else idx
                    # P0-3: Skip dates before EARLIEST_VALID_DATE
                    if as_of < date(1990, 1, 1):
                        continue
                    signals.append(
                        SignalOutput(
                            as_of_date=as_of,
                            bucket="substitutes",
                            signal_1=0.0,
                            signal_2=0.0,  # CONTRACT: Never None on abstain
                            confidence=0.0,  # CONTRACT: Zero confidence on abstain
                            model_type="rf",
                            max_input_age_days=999,  # P0-1: Max staleness for abstain
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

                # Confidence based on number of substitutes and feature importance
                n_subs = sum(
                    1 for c in spread_cols if not pd.isna(row_features[c].values[0])
                )
                base_confidence = min(n_subs / 4, 1.0) * 0.6 + 0.3

                as_of = idx.date() if hasattr(idx, "date") else idx
                # P0-3: Skip dates before EARLIEST_VALID_DATE
                if as_of < date(1990, 1, 1):
                    continue

                # P0-1: Compute max staleness for this date
                max_staleness = self.compute_max_staleness(data, as_of)

                # CONTRACT: signal_2 must never be None
                richness_val = richness.loc[idx]
                if pd.isna(richness_val):
                    signal_2_val = 0.0
                    # Penalty for missing secondary
                    base_confidence = base_confidence * 0.7
                    secondary_missing = True
                else:
                    signal_2_val = float(richness_val)
                    secondary_missing = False

                signals.append(
                    SignalOutput(
                        as_of_date=as_of,
                        bucket="substitutes",
                        signal_1=float(prediction),  # MODEL PREDICTION
                        signal_2=signal_2_val,  # CONTRACT: Never None
                        confidence=float(min(base_confidence, 0.95)),
                        model_type="rf",
                        max_input_age_days=max_staleness,  # P0-1: Staleness tracking
                        metadata={
                            "n_substitutes": n_subs,
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
            f"SubstitutesSignalGenerator: Generated {len(signals)} signals (RandomForest model)"
        )
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
        1: 1.15,
        2: 1.10,
        3: 1.05,
        4: 0.85,
        5: 0.80,
        6: 0.85,
        7: 0.90,
        8: 0.95,
        9: 1.00,
        10: 1.10,
        11: 1.15,
        12: 1.20,
    }

    def __init__(self):
        config = SignalConfig(
            bucket="china",
            model_type="gbm",
            primary_features=[
                "close",
                # CHINA DEMAND PROXIES - Full complex
                "hg_close",  # Copper (industrial demand)
                "usd_cny",  # CNY/USD (import capacity)
                # BRAZIL COMPETITION
                "fred_dexbzus",  # BRL/USD (Brazil export competitiveness)
            ],
            secondary_features=[
                # SHIPPING/LOGISTICS (sparse ~13% coverage, moved from primary 2026-01-30)
                "bdry_close",  # Baltic Dry Index (shipping demand)
                "sblk_close",  # Dry bulk shipping ETF
                # Extended China exposure
                "fxi_close",  # China Large-Cap ETF
                "kweb_close",  # China Internet ETF
                "china_pmi",  # Manufacturing PMI
                # Additional demand proxies
                "fred_chnprinto01ixpym",  # China industrial production
                # Soybean complex for context
                "zs_close",  # Soybeans (main China import)
                # NOTE: fx_usdbrl removed 2026-01-30 (duplicate of fred_dexbzus)
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
        """Require China demand features. Shipping (BDRY/SBLK) optional due to coverage variability."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")
        # REQUIRE demand proxies
        if "hg_close" not in data.columns:
            missing.append("hg_close")
        if "usd_cny" not in data.columns:
            missing.append("usd_cny")
        # Shipping is OPTIONAL (13% coverage in BDRY/SBLK)
        # Use FXI/KWEB as China sentiment proxies instead
        # REQUIRE Brazil competition
        if "fred_dexbzus" not in data.columns:
            missing.append("fred_dexbzus")
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
        """Prepare China-specific features with ALL elite indicators."""
        features = {}

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL, HG, SHIPPING
        # =====================================================================
        data = self.add_all_elite_indicators(data, "close", "zl")

        # Copper elite indicators
        if "hg_close" in data.columns:
            hg_data = data.copy()
            hg_data["close"] = data["hg_close"]
            hg_data = self.add_all_elite_indicators(hg_data, "close", "hg")
            for c in hg_data.columns:
                if c.startswith("hg_") and c not in data.columns:
                    data[c] = hg_data[c]

        # BDRY elite indicators
        if "bdry_close" in data.columns:
            bdry_data = data.copy()
            bdry_data["close"] = data["bdry_close"]
            bdry_data = self.add_all_elite_indicators(bdry_data, "close", "bdry")
            for c in bdry_data.columns:
                if c.startswith("bdry_") and c not in data.columns:
                    data[c] = bdry_data[c]

        # SBLK elite indicators
        if "sblk_close" in data.columns:
            sblk_data = data.copy()
            sblk_data["close"] = data["sblk_close"]
            sblk_data = self.add_all_elite_indicators(sblk_data, "close", "sblk")
            for c in sblk_data.columns:
                if c.startswith("sblk_") and c not in data.columns:
                    data[c] = sblk_data[c]

        # FXI elite indicators (China proxy)
        if "fxi_close" in data.columns:
            fxi_data = data.copy()
            fxi_data["close"] = data["fxi_close"]
            fxi_data = self.add_all_elite_indicators(fxi_data, "close", "fxi")
            for c in fxi_data.columns:
                if c.startswith("fxi_") and c not in data.columns:
                    data[c] = fxi_data[c]

        zl = data["close"]
        hg = data["hg_close"]

        # Additional features (kept for domain logic)
        features["zl_hg_corr_63d"] = zl.rolling(63, min_periods=30).corr(hg)

        # CNY features
        if "usd_cny" in data.columns:
            cny = data["usd_cny"]
            features["cny_zscore"] = self.compute_zscore(
                cny, window=126, min_periods=42
            )
            features["cny_mom_21d"] = cny.pct_change(21, fill_method=None)

        # BRL features (Brazil competition)
        brl_col = self._get_brl_column(data)
        if brl_col:
            brl = data[brl_col]
            if "dexbzus" in brl_col.lower():
                brl = 1 / brl
            features["brl_zscore"] = self.compute_zscore(
                brl, window=126, min_periods=42
            )
            features["brl_mom_21d"] = brl.pct_change(21, fill_method=None)

        # Seasonality
        features["month_sin"] = np.sin(
            2 * np.pi * pd.to_datetime(data.index).month / 12
        )
        features["month_cos"] = np.cos(
            2 * np.pi * pd.to_datetime(data.index).month / 12
        )
        seasonality = pd.Series(index=data.index, dtype=float)
        for idx in data.index:
            month = pd.to_datetime(idx).month
            seasonality.loc[idx] = self.CHINA_SEASONALITY.get(month, 1.0) - 1.0
        features["seasonality"] = seasonality

        # ADD ALL ELITE INDICATORS TO FEATURES (deterministic, no filtering)
        for col in data.columns:
            if (
                col.startswith("zl_")
                or col.startswith("hg_")
                or col.startswith("bdry_")
                or col.startswith("sblk_")
                or col.startswith("fxi_")
            ):
                if col not in features:
                    features[col] = data[col]

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

        # Find last valid date from core data (not all features - some may be all-NaN)
        core_data_valid = data["close"].notna()
        if core_data_valid.sum() == 0:
            logger.warning("ChinaSignalGenerator: No valid data")
            return signals

        last_valid_idx = data[core_data_valid].index[-1]
        current_date = (
            last_valid_idx.date() if hasattr(last_valid_idx, "date") else last_valid_idx
        )

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
        zl_hg_corr = zl.rolling(63, min_periods=30).corr(hg)

        for idx in data.index:
            if idx not in X_full.index:
                continue

            row_features = X_full.loc[[idx]]
            # Only check NaN in features the model uses (not all columns)
            try:
                prediction, pred_meta = self._predict(row_features)
                if prediction is None:
                    degraded_conf = float(
                        pred_meta.get("conf", self.degraded_confidence)
                    )
                    logger.warning(
                        f"   China abstain on {idx}: nan_pct_latest={pred_meta.get('nan_pct_latest')}"
                    )
                    as_of = idx.date() if hasattr(idx, "date") else idx
                    # P0-3: Skip dates before EARLIEST_VALID_DATE
                    if as_of < date(1990, 1, 1):
                        continue
                    signals.append(
                        SignalOutput(
                            as_of_date=as_of,
                            bucket="china",
                            signal_1=0.0,
                            signal_2=0.0,  # CONTRACT: Never None on abstain
                            confidence=0.0,  # CONTRACT: Zero confidence on abstain
                            model_type="gbm",
                            max_input_age_days=999,  # P0-1: Max staleness for abstain
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

                # Confidence based on correlation and data availability
                corr = zl_hg_corr.loc[idx] if not pd.isna(zl_hg_corr.loc[idx]) else 0.3
                base_confidence = max(0.3, min(abs(corr), 0.6))
                if has_cny:
                    base_confidence += 0.1
                if has_brazil:
                    base_confidence += 0.1
                if has_shipping:
                    base_confidence += 0.1

                as_of = idx.date() if hasattr(idx, "date") else idx
                # P0-3: Skip dates before EARLIEST_VALID_DATE
                if as_of < date(1990, 1, 1):
                    continue

                # P0-1: Compute max staleness for this date
                max_staleness = self.compute_max_staleness(data, as_of)

                # CONTRACT: signal_2 must never be None
                if has_brazil and not pd.isna(brazil_zscore.loc[idx]):
                    signal_2_val = float(brazil_zscore.loc[idx])
                    secondary_missing = False
                else:
                    signal_2_val = 0.0
                    # Penalty for missing secondary
                    base_confidence = base_confidence * 0.7
                    secondary_missing = True

                signals.append(
                    SignalOutput(
                        as_of_date=as_of,
                        bucket="china",
                        signal_1=float(prediction),  # MODEL PREDICTION
                        signal_2=signal_2_val,  # CONTRACT: Never None
                        confidence=float(min(base_confidence, 0.95)),
                        model_type="gbm",
                        max_input_age_days=max_staleness,  # P0-1: Staleness tracking
                        metadata={
                            "has_brazil": has_brazil,
                            "has_cny": has_cny,
                            "has_shipping": has_shipping,
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
            f"ChinaSignalGenerator: Generated {len(signals)} signals (GBM model, brazil: {has_brazil}, shipping: {has_shipping})"
        )
        return signals
