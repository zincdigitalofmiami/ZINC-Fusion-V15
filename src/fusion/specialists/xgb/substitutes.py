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
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# ML Imports - REAL MODELS
from sklearn.ensemble import RandomForestRegressor

from fusion.specialists.base import (
    BaseSignalGenerator,
    SignalConfig,
    SignalOutput,
)

from .ml_mixin import MLModelMixin

logger = logging.getLogger(__name__)

# Model persistence directory
MODELS_DIR = Path(__file__).parent.parent.parent.parent / "models" / "specialists"


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

    def validate_inputs(self, data: pd.DataFrame) -> list[str]:
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

    def _prepare_features(self, data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """Prepare substitutes-specific features with ALL elite indicators."""
        features = {}
        zl = data["close"]

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL AND ALL SUBSTITUTES
        # =====================================================================
        data = self.add_all_technical_indicators(data, "close", "zl")

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
                    sub_data = self.add_all_technical_indicators(
                        sub_data, "close", name
                    )
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
            if (
                col.startswith("zl_") or col.startswith("rs_") or col.startswith("cpo_")
            ) and col not in features:
                # Note: sunf_ and rape_ elite indicators not added (monthly data)
                features[col] = data[col]

        df = pd.DataFrame(features, index=data.index)
        return df, list(df.columns)

    def compute(self, data: pd.DataFrame, run_hash: str) -> list[SignalOutput]:
        """
        Compute substitutes signals using RandomForest model.
        """
        signals = []

        # Try to load existing model
        if not self._load_model():
            logger.info("   No existing model, will train on first pass")

        # Prepare features
        X_full, _feature_names = self._prepare_features(data)

        # FIX 2026-02-03: Removed erroneous X_full.shift(1)
        # Rolling features (z-scores, momentum, correlations) are already backward-looking
        # For EOD signal generation, using T's data for signal at T is correct
        # The previous "P0-4 FIX" was overly conservative and reduced signal freshness

        # FIX 2026-01-30: Only require primary features to be non-NaN (not all elite indicators)
        core_cols = [c for c in self.config.primary_features if c in X_full.columns]
        X_valid = X_full.dropna(subset=core_cols) if core_cols else X_full.dropna()
        last_valid_idx = X_valid.index[-1] if len(X_valid) > 0 else None
        if last_valid_idx is None:
            logger.warning(
                "SubstitutesSignalGenerator: No valid data after dropna(subset=primary_features)"
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
                else:
                    signal_2_val = float(richness_val)

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
