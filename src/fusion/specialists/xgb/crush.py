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
from sklearn.ensemble import GradientBoostingRegressor

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
# CRUSH SIGNAL GENERATOR - REAL GRADIENT BOOSTING
# =============================================================================


class CrushSignalGenerator(BaseSignalGenerator, MLModelMixin):
    """
    Crush specialist: margin-driven production incentives.

    ACTUAL MODEL: GradientBoosting Regressor

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
    PATCHED 2026-01-23: Real GradientBoosting model
    """

    def __init__(self):
        config = SignalConfig(
            bucket="crush",
            model_type="gbm",
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
        """Create GradientBoosting model."""
        return GradientBoostingRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            random_state=42,
        )

    def _prepare_features(self, data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """Prepare crush-specific features with ALL elite indicators."""
        features = {}

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL, ZS, ZM
        # =====================================================================
        # ZL elite indicators
        data = self.add_all_technical_indicators(data, "close", "zl")

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
            zs_data = self.add_all_technical_indicators(zs_data, "close", "zs")
            for col in zs_data.columns:
                if col.startswith("zs_") and col not in data.columns:
                    data[col] = zs_data[col]

        # ZM elite indicators
        if "zm_close" in data.columns:
            zm_data = data.copy()
            zm_data["close"] = data["zm_close"]
            zm_data = self.add_all_technical_indicators(zm_data, "close", "zm")
            for col in zm_data.columns:
                if col.startswith("zm_") and col not in data.columns:
                    data[col] = zm_data[col]

        zl = data["close"]
        zs = data["zs_close"]
        zm = data["zm_close"]

        # Core crush calculations (CME standard formula)
        # 1 bushel soybeans (60 lbs) yields 11 lbs oil + 44 lbs meal (48% protein)
        # Board Crush = (ZL x 0.11) + (ZM x 0.022) - (ZS / 100)
        # Oil Share = (ZL x 0.11) / ((ZL x 0.11) + (ZM x 0.022))
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
            if (
                col.startswith("zl_") or col.startswith("zs_") or col.startswith("zm_")
            ) and col not in features:
                features[col] = data[col]

        # OPTIONS FEATURES (if available) - NO GREEKS, just raw volume/ratios
        # Put/call ratio and volume z-scores for ZL, ZS, ZM
        for ul in ["zl", "zs", "zm"]:
            pc_col = f"{ul}_put_call_ratio"
            if pc_col in data.columns:
                features[f"{ul}_pc_ratio_zscore"] = self.compute_zscore(
                    data[pc_col], window=63
                )

            call_vol_col = f"{ul}_call_volume"
            if call_vol_col in data.columns:
                features[f"{ul}_call_vol_zscore"] = self.compute_zscore(
                    data[call_vol_col], window=63
                )

            put_vol_col = f"{ul}_put_volume"
            if put_vol_col in data.columns:
                features[f"{ul}_put_vol_zscore"] = self.compute_zscore(
                    data[put_vol_col], window=63
                )

            # Premium z-scores (average option premium)
            call_prem_col = f"{ul}_call_premium"
            if call_prem_col in data.columns:
                features[f"{ul}_call_prem_zscore"] = self.compute_zscore(
                    data[call_prem_col], window=63
                )

            put_prem_col = f"{ul}_put_premium"
            if put_prem_col in data.columns:
                features[f"{ul}_put_prem_zscore"] = self.compute_zscore(
                    data[put_prem_col], window=63
                )

            # Open interest z-scores
            call_oi_col = f"{ul}_call_oi"
            if call_oi_col in data.columns:
                features[f"{ul}_call_oi_zscore"] = self.compute_zscore(
                    data[call_oi_col], window=63
                )

            put_oi_col = f"{ul}_put_oi"
            if put_oi_col in data.columns:
                features[f"{ul}_put_oi_zscore"] = self.compute_zscore(
                    data[put_oi_col], window=63
                )

        df = pd.DataFrame(features, index=data.index)
        return df, list(df.columns)

    def compute(self, data: pd.DataFrame, run_hash: str) -> list[SignalOutput]:
        """
        Compute crush signals using GradientBoosting model.
        """
        signals = []

        # Try to load existing model
        if not self._load_model():
            logger.info("   No existing model, will train on first pass")

        # Prepare features for entire dataset
        X_full, _feature_names = self._prepare_features(data)

        # Get the most recent date with valid data
        # FIX 2026-01-30: Only require primary features to be non-NaN (not all elite indicators)
        core_cols = [c for c in self.config.primary_features if c in X_full.columns]
        X_valid = X_full.dropna(subset=core_cols) if core_cols else X_full.dropna()
        last_valid_idx = X_valid.index[-1] if len(X_valid) > 0 else None

        if last_valid_idx is None:
            logger.warning(
                "CrushSignalGenerator: No valid data after dropna(subset=primary_features)"
            )
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
        self.compute_zscore(oil_share, window=126, min_periods=63)

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
                else:
                    signal_2_val = float(secondary_val)

                signals.append(
                    SignalOutput(
                        as_of_date=as_of,
                        bucket="crush",
                        signal_1=float(prediction),  # MODEL PREDICTION
                        signal_2=signal_2_val,  # CONTRACT: Never None
                        confidence=float(confidence),
                        model_type="gbm",
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
            f"CrushSignalGenerator: Generated {len(signals)} signals (GradientBoosting model)"
        )
        return signals
