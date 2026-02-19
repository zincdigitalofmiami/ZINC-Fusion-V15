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
from typing import ClassVar

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
    CHINA_SEASONALITY: ClassVar[dict[int, float]] = {
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

    def validate_inputs(self, data: pd.DataFrame) -> list[str]:
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

    def _get_brl_column(self, data: pd.DataFrame) -> str | None:
        """Find BRL column."""
        for col in ["fred_dexbzus", "fx_usdbrl", "usdbrl", "brl_close"]:
            if col in data.columns and data[col].notna().sum() > 30:
                return col
        return None

    def _get_shipping_column(self, data: pd.DataFrame) -> str | None:
        """Find shipping column."""
        for col in ["bdry_close", "sblk_close"]:
            if col in data.columns and data[col].notna().sum() > 30:
                return col
        return None

    def _prepare_features(self, data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """Prepare China-specific features with ALL elite indicators."""
        features = {}

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL, HG, SHIPPING
        # =====================================================================
        data = self.add_all_technical_indicators(data, "close", "zl")

        # Copper elite indicators
        if "hg_close" in data.columns:
            hg_data = data.copy()
            hg_data["close"] = data["hg_close"]
            hg_data = self.add_all_technical_indicators(hg_data, "close", "hg")
            for c in hg_data.columns:
                if c.startswith("hg_") and c not in data.columns:
                    data[c] = hg_data[c]

        # BDRY elite indicators
        if "bdry_close" in data.columns:
            bdry_data = data.copy()
            bdry_data["close"] = data["bdry_close"]
            bdry_data = self.add_all_technical_indicators(bdry_data, "close", "bdry")
            for c in bdry_data.columns:
                if c.startswith("bdry_") and c not in data.columns:
                    data[c] = bdry_data[c]

        # SBLK elite indicators
        if "sblk_close" in data.columns:
            sblk_data = data.copy()
            sblk_data["close"] = data["sblk_close"]
            sblk_data = self.add_all_technical_indicators(sblk_data, "close", "sblk")
            for c in sblk_data.columns:
                if c.startswith("sblk_") and c not in data.columns:
                    data[c] = sblk_data[c]

        # FXI elite indicators (China proxy)
        if "fxi_close" in data.columns:
            fxi_data = data.copy()
            fxi_data["close"] = data["fxi_close"]
            fxi_data = self.add_all_technical_indicators(fxi_data, "close", "fxi")
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
            ) and col not in features:
                features[col] = data[col]

        df = pd.DataFrame(features, index=data.index)
        return df, list(df.columns)

    def _compute_brazil_competition(self, data: pd.DataFrame) -> tuple[pd.Series, bool]:
        """Compute Brazil competition z-score for signal_2."""
        brl_col = self._get_brl_column(data)
        if brl_col is None:
            return pd.Series(0.0, index=data.index), False

        brl = data[brl_col]
        if "dexbzus" in brl_col.lower():
            brl = 1 / brl

        return self.compute_zscore(brl, window=126, min_periods=42), True

    def compute(self, data: pd.DataFrame, run_hash: str) -> list[SignalOutput]:
        """
        Compute China demand signals using GradientBoosting model.
        """
        signals = []

        # Try to load existing model
        if not self._load_model():
            logger.info("   No existing model, will train on first pass")

        # Prepare features
        X_full, _feature_names = self._prepare_features(data)

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
                else:
                    signal_2_val = 0.0
                    # Penalty for missing secondary
                    base_confidence = base_confidence * 0.7

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
