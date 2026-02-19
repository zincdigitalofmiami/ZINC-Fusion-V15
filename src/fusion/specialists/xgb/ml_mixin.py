"""
GBM/RF-based signal generators: crush, china, substitutes.

These specialists use REAL tree-based ML models trained on engineered features.

PATCHED 2026-01-23: Implemented actual ML models
- GradientBoosting for Crush
- GradientBoosting for China
- RandomForest for Substitutes
- Models train on features, predict forward returns
- Model persistence to models/specialists/{bucket}/
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
from sklearn.preprocessing import StandardScaler

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
        """Create the ML model. Override in subclass."""
        raise NotImplementedError

    def _prepare_features(self, data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
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

        # Scale features
        X_scaled = self.scaler.fit_transform(X_clean)

        # Create and train model
        self.model = self._create_model()
        self.model.fit(X_scaled, y_clean)

        self.last_train_date = current_date

        # Log feature importances
        # FIX 2026-02-03: Use self.feature_names (trained features) not feature_names (all features)
        if hasattr(self.model, "feature_importances_"):
            importances = dict(
                zip(self.feature_names, self.model.feature_importances_, strict=False)
            )
            top_features = sorted(
                importances.items(), key=lambda x: x[1], reverse=True
            )[:5]
            logger.info(f"   Top features: {top_features}")

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
        X = features.copy()
        if self.feature_names:
            # Model artifacts can outlive feature schema tweaks.
            # Add missing trained columns as NaN so missingness policy can abstain
            # instead of throwing KeyError and silently skipping rows.
            missing_cols = [c for c in self.feature_names if c not in X.columns]
            for col in missing_cols:
                X[col] = np.nan
            X = X[self.feature_names]
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
