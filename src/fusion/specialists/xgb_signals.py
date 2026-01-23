"""
XGBoost/GBM-based signal generators: crush, china, substitutes.

These specialists use tree-based models on engineered features.
"""

from datetime import date
from typing import List, Optional
import pandas as pd
import numpy as np
import logging

from fusion.specialists.base import (
    BaseSignalGenerator,
    SignalConfig,
    SignalOutput,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CRUSH SIGNAL GENERATOR
# =============================================================================

class CrushSignalGenerator(BaseSignalGenerator):
    """
    Crush specialist: margin-driven production incentives.

    Signal Contract:
    - signal_1: Crush margin z-score (normalized margin level)
    - signal_2: 21-day crush momentum (rate of change)

    Inputs: ZL, ZS, ZM closes from mkt.futures_1d
    Optional: WASDE fundamentals (stocks/use ratio, production)
    Model: Uses engineered spreads (board crush, oil share)

    PATCHED 2026-01-21: Now incorporates WASDE fundamentals when available
    """

    def __init__(self):
        config = SignalConfig(
            bucket="crush",
            model_type="xgb",
            primary_features=["close", "zs_close", "zm_close"],
            secondary_features=[
                "volume", "open_interest",
                # WASDE fundamentals (added 2026-01-21)
                "wasde_soybean_oil_ending_stocks",
                "wasde_soybean_oil_production",
                "wasde_soybeans_crush",
            ],
            lookback_days=252,
            min_data_points=63,
        )
        super().__init__(config)

    def _compute_wasde_adjustment(self, data: pd.DataFrame) -> pd.Series:
        """
        Compute WASDE-based supply adjustment if data available.

        Uses stocks-to-use ratio: higher stocks = bearish (lower adjustment)
        """
        adjustment = pd.Series(0.0, index=data.index)

        # Check for WASDE columns
        stocks_col = None
        use_col = None

        for col in data.columns:
            if 'wasde' in col.lower() and 'ending_stocks' in col.lower() and 'oil' in col.lower():
                stocks_col = col
            if 'wasde' in col.lower() and ('consumption' in col.lower() or 'use' in col.lower()) and 'oil' in col.lower():
                use_col = col

        # Also check for production as proxy
        prod_col = None
        for col in data.columns:
            if 'wasde' in col.lower() and 'production' in col.lower() and 'oil' in col.lower():
                prod_col = col

        if stocks_col and stocks_col in data.columns:
            stocks = data[stocks_col]
            # Stocks-to-use if we have use data
            if use_col and use_col in data.columns:
                use = data[use_col]
                stocks_use = stocks / use.replace(0, np.nan)
                adjustment = -self.compute_zscore(stocks_use, window=24, min_periods=12)  # Monthly data
                logger.info("   Using WASDE stocks-to-use ratio")
            elif prod_col and prod_col in data.columns:
                # Use stocks-to-production as proxy
                prod = data[prod_col]
                stocks_prod = stocks / prod.replace(0, np.nan)
                adjustment = -self.compute_zscore(stocks_prod, window=24, min_periods=12)
                logger.info("   Using WASDE stocks-to-production ratio")
            else:
                # Just use stocks z-score
                adjustment = -self.compute_zscore(stocks, window=24, min_periods=12)
                logger.info("   Using WASDE stocks z-score")

        return adjustment.fillna(0) * 0.2  # 20% weight to fundamentals

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute crush signals.

        Board Crush = ZS × 11 - ZL × 11 - ZM
        Oil Share = ZL × 11 / (ZL × 11 + ZM)

        PATCHED: Now includes WASDE fundamental adjustment when available
        """
        signals = []

        # Extract price series
        zl = data["close"]  # Soybean oil (primary)
        zs = data["zs_close"]  # Soybeans
        zm = data["zm_close"]  # Soybean meal

        # Core crush calculations (from specialist_buckets.py logic)
        board_crush = (zs * 11) - (zl * 11) - zm
        oil_share = (zl * 11) / ((zl * 11) + zm)

        # Z-score normalization (252-day rolling)
        crush_zscore = self.compute_zscore(board_crush, window=252, min_periods=63)

        # WASDE fundamental adjustment (NEW)
        wasde_adj = self._compute_wasde_adjustment(data)
        has_wasde = wasde_adj.abs().sum() > 0

        # Adjusted crush signal
        crush_adjusted = crush_zscore + wasde_adj

        # Momentum (21-day)
        crush_momentum = board_crush.pct_change(periods=21) * 100

        # Oil share z-score for confidence calculation
        oil_share_zscore = self.compute_zscore(oil_share, window=252, min_periods=63)

        # Generate signal for each date
        for idx in data.index:
            if pd.isna(crush_adjusted.loc[idx]) or pd.isna(crush_momentum.loc[idx]):
                continue

            # Confidence based on oil share alignment
            # Higher confidence when crush and oil share signals agree
            os_z = oil_share_zscore.loc[idx] if not pd.isna(oil_share_zscore.loc[idx]) else 0
            crush_z = crush_adjusted.loc[idx]
            alignment = 1 - abs(np.sign(crush_z) - np.sign(os_z)) / 2
            confidence = 0.5 + 0.5 * alignment  # Range: 0.5-1.0

            # Boost confidence if WASDE data available
            if has_wasde and not pd.isna(wasde_adj.loc[idx]) and wasde_adj.loc[idx] != 0:
                confidence = min(confidence + 0.1, 0.95)

            signals.append(SignalOutput(
                as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                bucket="crush",
                signal_1=float(crush_adjusted.loc[idx]),
                signal_2=float(crush_momentum.loc[idx]),
                confidence=float(confidence),
                model_type="xgb",
                metadata={
                    "board_crush": float(board_crush.loc[idx]),
                    "oil_share": float(oil_share.loc[idx]),
                    "wasde_adjustment": float(wasde_adj.loc[idx]) if not pd.isna(wasde_adj.loc[idx]) else 0.0,
                    "has_wasde": has_wasde,
                    "run_hash": run_hash,
                },
            ))

        logger.info(f"CrushSignalGenerator: Generated {len(signals)} signals (WASDE: {has_wasde})")
        return signals


# =============================================================================
# SUBSTITUTES SIGNAL GENERATOR
# =============================================================================

class SubstitutesSignalGenerator(BaseSignalGenerator):
    """
    Substitutes specialist: switching behavior among soft oils.

    Signal Contract:
    - signal_1: Substitution pressure score (composite of relative price ratios)
    - signal_2: ZL richness score (how expensive ZL is vs substitutes)

    Inputs: ZL, canola (RS), palm (CPO/FCPO), sunflower prices
    Model: Composite of cross-oil spread and ratio z-scores

    PATCHED 2026-01-21: Enhanced with relative value matrix and palm spread
    - Price ratios (not just spreads) for better comparability
    - ZL richness indicator as signal_2
    - Palm oil integration
    """

    def __init__(self):
        config = SignalConfig(
            bucket="substitutes",
            model_type="rf",
            primary_features=["close"],  # ZL close
            secondary_features=[
                "rs_close",          # Canola (ICE RS)
                "cpo_close",         # Palm oil (Bursa CPO)
                "sunflower_close",   # Sunflower
                "rapeseed_close",    # Rapeseed
            ],
            lookback_days=252,
            min_data_points=63,
        )
        super().__init__(config)

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Override to allow partial secondary features."""
        missing = []
        for feat in self.config.primary_features:
            if feat not in data.columns:
                missing.append(feat)
        # At least one substitute must be present
        substitutes = ["rs_close", "cpo_close", "sunflower_close", "rapeseed_close"]
        available = [s for s in substitutes if s in data.columns]
        if not available:
            missing.append("at_least_one_substitute")
        return missing

    def _compute_relative_value_matrix(self, data: pd.DataFrame) -> tuple:
        """
        Compute relative value matrix using price ratios.

        NEW (2026-01-21): Ratios are more stable than spreads for
        comparing commodities with different price levels.

        Returns:
            (spread_zscores, ratio_zscores, spread_names)
        """
        zl = data["close"]
        spread_zscores = []
        ratio_zscores = []
        spread_names = []

        # Canola spread and ratio
        if "rs_close" in data.columns:
            rs = data["rs_close"]
            zl_rs_spread = zl - rs
            zl_rs_ratio = zl / rs.replace(0, np.nan)
            spread_zscores.append(self.compute_zscore(zl_rs_spread, window=126, min_periods=42))
            ratio_zscores.append(self.compute_zscore(zl_rs_ratio, window=252, min_periods=63))
            spread_names.append("zl_canola")

        # Palm oil spread and ratio
        if "cpo_close" in data.columns:
            cpo = data["cpo_close"]
            # CPO is in MYR/MT, need to convert to comparable units
            # Approximate: CPO (MYR/MT) / 88 ≈ cents/lb
            cpo_converted = cpo / 88
            zl_cpo_spread = zl - cpo_converted
            zl_cpo_ratio = zl / cpo_converted.replace(0, np.nan)
            spread_zscores.append(self.compute_zscore(zl_cpo_spread, window=126, min_periods=42))
            ratio_zscores.append(self.compute_zscore(zl_cpo_ratio, window=252, min_periods=63))
            spread_names.append("zl_palm")

        # Sunflower spread
        if "sunflower_close" in data.columns:
            sunf = data["sunflower_close"]
            zl_sunf_spread = zl - sunf
            zl_sunf_ratio = zl / sunf.replace(0, np.nan)
            spread_zscores.append(self.compute_zscore(zl_sunf_spread, window=126, min_periods=42))
            ratio_zscores.append(self.compute_zscore(zl_sunf_ratio, window=252, min_periods=63))
            spread_names.append("zl_sunflower")

        # Rapeseed spread
        if "rapeseed_close" in data.columns:
            rape = data["rapeseed_close"]
            zl_rape_spread = zl - rape
            zl_rape_ratio = zl / rape.replace(0, np.nan)
            spread_zscores.append(self.compute_zscore(zl_rape_spread, window=126, min_periods=42))
            ratio_zscores.append(self.compute_zscore(zl_rape_ratio, window=252, min_periods=63))
            spread_names.append("zl_rapeseed")

        return spread_zscores, ratio_zscores, spread_names

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute substitution pressure score.

        PATCHED 2026-01-21: Enhanced with relative value matrix

        signal_1: Substitution pressure (spread z-score composite)
            Higher = ZL expensive vs substitutes (bearish for ZL)
            Lower = ZL cheap vs substitutes (bullish for ZL)

        signal_2: ZL richness score (ratio z-score composite)
            Positive = ZL rich (mean-reversion opportunity: bearish)
            Negative = ZL cheap (mean-reversion opportunity: bullish)
        """
        signals = []

        # Get relative value matrix (spreads and ratios)
        spread_zscores, ratio_zscores, spread_names = self._compute_relative_value_matrix(data)

        if not spread_zscores:
            logger.warning("SubstitutesSignalGenerator: No substitute data available")
            return signals

        # Combine spreads with equal weight (signal_1: pressure)
        spread_combined = pd.concat(spread_zscores, axis=1).mean(axis=1)

        # Combine ratios with equal weight (signal_2: richness)
        if ratio_zscores:
            richness_combined = pd.concat(ratio_zscores, axis=1).mean(axis=1)
        else:
            richness_combined = pd.Series(np.nan, index=data.index)

        for idx in data.index:
            if pd.isna(spread_combined.loc[idx]):
                continue

            # Confidence based on number of available spreads
            available_spread_count = sum(1 for sz in spread_zscores if not pd.isna(sz.loc[idx]))
            available_ratio_count = sum(1 for rz in ratio_zscores if not pd.isna(rz.loc[idx])) if ratio_zscores else 0

            # More substitutes = higher confidence
            base_confidence = min(available_spread_count / 4, 1.0) * 0.7 + 0.2

            # Boost if we have ratio data too
            if available_ratio_count > 0:
                base_confidence += 0.05

            confidence = min(base_confidence, 0.95)

            # Signal 2: richness score
            sig2 = None
            if not richness_combined.isna().all() and not pd.isna(richness_combined.loc[idx]):
                sig2 = float(richness_combined.loc[idx])

            signals.append(SignalOutput(
                as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                bucket="substitutes",
                signal_1=float(spread_combined.loc[idx]),
                signal_2=sig2,
                confidence=float(confidence),
                model_type="rf",
                metadata={
                    "spreads_used": spread_names,
                    "num_substitutes": available_spread_count,
                    "has_ratios": available_ratio_count > 0,
                    "run_hash": run_hash,
                },
            ))

        logger.info(f"SubstitutesSignalGenerator: Generated {len(signals)} signals ({len(spread_names)} substitutes)")
        return signals


# =============================================================================
# CHINA SIGNAL GENERATOR
# =============================================================================

class ChinaSignalGenerator(BaseSignalGenerator):
    """
    China specialist: demand shifts and shipment intensity.

    Signal Contract:
    - signal_1: Demand outlook score (copper proxy + CNY risk)
    - signal_2: Brazil competition signal (BRL weakness = bearish US exports)

    Inputs: HG (copper) as demand proxy, USD/CNY and USD/BRL for trade flow risk
    Model: GBM on demand proxies

    PATCHED 2026-01-21: Added Brazil competition signal and seasonality
    - BRL weakness = Brazil more competitive = less demand for US soy
    - China import seasonality (peak Oct-Feb, trough Apr-Jun)
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
            primary_features=["close", "hg_close"],  # ZL and copper
            secondary_features=[
                "usd_cny",        # CNY risk
                "fred_dexbzus",   # BRL (Brazil competition) - FRED format
                "fx_usdbrl",      # BRL alternative column name
                "dalian_soy",
                "china_pmi",
            ],
            lookback_days=252,
            min_data_points=63,
        )
        super().__init__(config)

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Copper is required; FX is optional enhancement."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")
        if "hg_close" not in data.columns:
            missing.append("hg_close")
        return missing

    def _compute_brazil_competition(self, data: pd.DataFrame) -> tuple:
        """
        Compute Brazil competition signal.

        When BRL weakens (USD/BRL rises), Brazil exports more competitively,
        reducing demand for US soybeans → bearish for ZL.

        Returns:
            (brl_zscore, has_brl)
        """
        # Try different column names for BRL
        brl_col = None
        for col in ["fred_dexbzus", "fx_usdbrl", "usdbrl", "brl_close"]:
            if col in data.columns:
                brl_col = col
                break

        if brl_col is None:
            return pd.Series(0.0, index=data.index), False

        brl = data[brl_col]

        # For FRED format (BRL per USD), higher = weaker BRL
        # Some sources may have inverted format
        if "dexbzus" in brl_col.lower():
            # FRED is foreign per USD, so higher = stronger USD = weaker BRL
            usd_brl = 1 / brl  # Convert to USD/BRL
        else:
            usd_brl = brl

        # Z-score: positive = BRL weakness = Brazil competitive = bearish US
        brl_zscore = self.compute_zscore(usd_brl, window=126, min_periods=42)

        logger.info(f"   Brazil competition using {brl_col}")
        return brl_zscore, True

    def _compute_seasonality_adjustment(self, data: pd.DataFrame) -> pd.Series:
        """
        Compute China import seasonality adjustment.

        Peak demand: Oct-Feb (new crop arrivals from US/Brazil)
        Trough: Apr-Jun (between harvests)
        """
        adjustment = pd.Series(0.0, index=data.index)

        for idx in data.index:
            dt = pd.to_datetime(idx)
            month = dt.month
            seasonal_weight = self.CHINA_SEASONALITY.get(month, 1.0)
            # Convert to adjustment: values > 1.0 = bullish, < 1.0 = bearish
            adjustment.loc[idx] = (seasonal_weight - 1.0) * 0.5  # Scale to ~±0.1

        return adjustment

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute China demand outlook score.

        PATCHED 2026-01-21: Added Brazil competition and seasonality

        signal_1: Demand outlook (copper + CNY + seasonality)
        signal_2: Brazil competition pressure (BRL weakness = bearish)

        Uses copper (Dr. Copper) as primary demand proxy.
        Higher copper z-score = stronger China demand signal (bullish ZL)
        USD/CNY risk: CNY weakness = reduced import capacity (bearish ZL)
        BRL weakness: Brazil more competitive = less US demand (bearish ZL)
        """
        signals = []

        # Copper z-score (primary demand proxy)
        hg = data["hg_close"]
        hg_zscore = self.compute_zscore(hg, window=126, min_periods=42)

        # ZL-copper correlation (rolling)
        zl = data["close"]
        zl_hg_corr = zl.rolling(63).corr(hg)

        # CNY risk adjustment if available
        cny_adjustment = pd.Series(0.0, index=data.index)
        has_cny = False
        if "usd_cny" in data.columns:
            usd_cny = data["usd_cny"]
            # Higher USD/CNY = weaker CNY = bearish for China imports
            cny_zscore = self.compute_zscore(usd_cny, window=126, min_periods=42)
            cny_adjustment = -0.3 * cny_zscore  # Dampen CNY effect
            has_cny = True

        # Brazil competition signal (NEW)
        brazil_zscore, has_brazil = self._compute_brazil_competition(data)

        # Seasonality adjustment (NEW)
        seasonality_adj = self._compute_seasonality_adjustment(data)

        # Composite demand score = copper demand + CNY risk + seasonality
        demand_score = hg_zscore + cny_adjustment + seasonality_adj

        for idx in data.index:
            if pd.isna(demand_score.loc[idx]):
                continue

            # Confidence based on ZL-copper correlation strength and data availability
            corr = zl_hg_corr.loc[idx] if not pd.isna(zl_hg_corr.loc[idx]) else 0.3
            base_confidence = max(0.3, min(abs(corr), 0.7))

            # Boost confidence for additional data
            if has_cny:
                base_confidence += 0.1
            if has_brazil:
                base_confidence += 0.1

            confidence = min(base_confidence, 0.95)

            # Signal 2: Brazil competition (positive = Brazil competitive = bearish US)
            sig2 = None
            if has_brazil and not pd.isna(brazil_zscore.loc[idx]):
                sig2 = float(brazil_zscore.loc[idx])

            # Build metadata
            meta = {
                "hg_zscore": float(hg_zscore.loc[idx]) if not pd.isna(hg_zscore.loc[idx]) else None,
                "zl_hg_corr": float(corr),
                "has_brazil": has_brazil,
                "has_cny": has_cny,
                "seasonality_adj": float(seasonality_adj.loc[idx]),
                "run_hash": run_hash,
            }

            if has_brazil and not pd.isna(brazil_zscore.loc[idx]):
                meta["brazil_zscore"] = float(brazil_zscore.loc[idx])

            signals.append(SignalOutput(
                as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                bucket="china",
                signal_1=float(demand_score.loc[idx]),
                signal_2=sig2,
                confidence=float(confidence),
                model_type="gbm",
                metadata=meta,
            ))

        logger.info(f"ChinaSignalGenerator: Generated {len(signals)} signals (brazil: {has_brazil}, cny: {has_cny})")
        return signals
