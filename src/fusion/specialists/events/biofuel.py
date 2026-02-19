"""
Event-based signal generators: tariff, biofuel, trump_effect.

These specialists use rule-based logic, event studies, and sentiment
aggregation rather than traditional ML models.
"""

import logging
from datetime import date

import numpy as np
import pandas as pd

from fusion.specialists.base import (
    BaseSignalGenerator,
    SignalConfig,
    SignalOutput,
)

# Tariff deadline features integration
try:
    from fusion.features.tariff_deadlines import (
        TariffDeadlineFeatureEngine,
        calculate_deadline_risk_score,
    )

    HAS_TARIFF_DEADLINES = True
except ImportError:
    HAS_TARIFF_DEADLINES = False
    TariffDeadlineFeatureEngine = None
    calculate_deadline_risk_score = None

logger = logging.getLogger(__name__)


# =============================================================================
# TARIFF SIGNAL GENERATOR
# =============================================================================


# =============================================================================
# BIOFUEL SIGNAL GENERATOR
# =============================================================================


class BiofuelSignalGenerator(BaseSignalGenerator):
    """
    Biofuel specialist: regulatory demand shifts (RFS, 45Z, CI scoring).

    Signal Contract:
    - signal_1: Policy pressure score (RIN/LCFS weighted sentiment)
    - signal_2: RIN momentum (fast vs slow)

    Higher signal = bullish biofuel policy environment = bullish ZL
    Lower signal = weak biofuel incentives = less demand pull

    Inputs: RIN prices (D4 biomass-based diesel), LCFS credits
    Model: EMA-smoothed price signals + policy regime detection

    PATCHED 2026-01-21: Now uses actual EPA RIN data from supply.epa_rin_1d
    """

    def __init__(self):
        config = SignalConfig(
            bucket="biofuel",
            model_type="nlp_ema",
            primary_features=[
                "close",
                # RIN COMPLEX - Full renewable fuel credit suite
                "rin_d4_price",  # D4 RIN (biomass-based diesel) - CORE
                "rin_d6_price",  # D6 RIN (cellulosic ethanol)
                # BIODIESEL ECONOMICS
                "ho_close",  # Heating Oil (biodiesel value proxy)
                "lcfs_credit",  # CA LCFS credit price
            ],
            secondary_features=[
                # Additional RINs
                "rin_d3_price",  # D3 RIN (cellulosic biofuel)
                "rin_d5_price",  # D5 RIN (advanced biofuel)
                # Feedstock/margin inputs
                "cl_close",  # Crude (energy parity)
                "zm_close",  # Soybean meal (byproduct value)
                # Ethanol for full biofuel picture
                "fred_dpropanembtx",  # Propane (energy arbitrage)
            ],
            lookback_days=252,
            min_data_points=63,
        )
        super().__init__(config)

    def validate_inputs(self, data: pd.DataFrame) -> list[str]:
        """Require FULL RIN complex + biodiesel economics."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")
        # REQUIRE RIN complex
        if "rin_d4_price" not in data.columns:
            missing.append("rin_d4_price")
        if "rin_d6_price" not in data.columns:
            missing.append("rin_d6_price")
        # REQUIRE biodiesel economics
        if "ho_close" not in data.columns:
            missing.append("ho_close")
        if "lcfs_credit" not in data.columns:
            missing.append("lcfs_credit")
        return missing

    def _get_rin_series(self, data: pd.DataFrame) -> tuple:
        """
        Get best available RIN price series.

        Priority: D4 > D6 > D3 > D5 > None

        PATCHED 2026-02-03: NO forward-fill. Use event-only RIN values.
        Rolling computations tolerate NaNs with min_periods guards.

        Returns:
            (series, source_name) or (None, None) if no RIN data
        """
        rin_cols = ["rin_d4_price", "rin_d6_price", "rin_d3_price", "rin_d5_price"]

        for col in rin_cols:
            if col in data.columns:
                series = data[col]
                valid_count = series.notna().sum()
                if valid_count >= 100:  # Need at least 100 valid points
                    logger.info(f"   Using {col} ({valid_count:,} valid values)")
                    return series, col.replace("rin_", "").replace("_price", "")

        return None, None

    def _compute_biodiesel_margin_proxy(self, data: pd.DataFrame) -> pd.Series:
        """
        Compute biodiesel margin proxy from ZL and HO.

        Biodiesel premium = ZL (feedstock cost) relative to HO (product proxy)
        Higher ZL relative to HO = higher feedstock cost = margin compression
        """
        zl = data["close"]

        if "ho_close" in data.columns:
            ho = data["ho_close"]
            # ZL in cents/lb, HO in dollars/gallon
            # Convert ZL: cents/lb -> dollars/gallon (7.7 lb/gallon)
            zl_per_gal = (zl / 100) * 7.7
            margin_proxy = ho - zl_per_gal  # Positive = margin, negative = loss
            return margin_proxy
        else:
            # Fallback: use ZL momentum as proxy
            return zl.pct_change(21, fill_method=None) * 100

    def _compute_rin_momentum(self, rin: pd.Series) -> pd.Series:
        """
        Compute RIN momentum signal (fast EMA vs slow EMA).

        Positive momentum = RIN prices rising = stronger biofuel incentives
        """
        fast_ema = rin.ewm(span=10, adjust=False).mean()
        slow_ema = rin.ewm(span=30, adjust=False).mean()

        # Momentum as percentage spread
        momentum = (fast_ema - slow_ema) / slow_ema.replace(0, np.nan) * 100
        return momentum.clip(-50, 50)  # Cap extreme values

    def _classify_rin_regime(self, rin_zscore: pd.Series) -> pd.Series:
        """
        Classify RIN price regime.

        Returns:
            1.0 = HIGH (bullish biofuel)
            0.0 = NEUTRAL
           -1.0 = LOW (bearish biofuel)
        """
        regime = pd.Series(0.0, index=rin_zscore.index)
        regime[rin_zscore > 1.0] = 1.0  # High RIN = bullish
        regime[rin_zscore < -1.0] = -1.0  # Low RIN = bearish
        return regime

    def compute(self, data: pd.DataFrame, run_hash: str) -> list[SignalOutput]:
        """
        Compute biofuel policy pressure signal with ALL elite indicators.

        PATCHED 2026-01-31: Added staleness-aware gating to prevent stale signals.

        signal_1: Policy pressure (RIN z-score or margin proxy)
        signal_2: RIN momentum (if using real RIN data)
        """
        signals = []

        # =================================================================
        # STALENESS CONFIGURATION
        # EPA RIN = weekly volume-weighted avg, updated monthly (not daily). TTL 45d.
        # LCFS = weekly. No forward-fill.
        # =================================================================
        MAX_RIN_STALENESS_DAYS = 45  # EPA cadence: weekly series, updated monthly
        MAX_LCFS_STALENESS_DAYS = 14  # Same for LCFS

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL, HO, RIN SERIES
        # =====================================================================
        data = self.add_all_technical_indicators(data, "close", "zl")

        # HO elite indicators (biodiesel proxy)
        if "ho_close" in data.columns and data["ho_close"].notna().sum() > 30:
            ho_data = data.copy()
            ho_data["close"] = data["ho_close"]
            ho_data = self.add_all_technical_indicators(ho_data, "close", "ho")
            for c in ho_data.columns:
                if c.startswith("ho_") and c not in data.columns:
                    data[c] = ho_data[c]

        # RIN elite indicators
        for rin_col in ["rin_d4_price", "rin_d6_price"]:
            if rin_col in data.columns and data[rin_col].notna().sum() > 30:
                rin_data = data.copy()
                rin_data["close"] = data[rin_col]
                prefix = rin_col.replace("_price", "")
                rin_data = self.add_all_technical_indicators(rin_data, "close", prefix)
                for c in rin_data.columns:
                    if c.startswith(f"{prefix}_") and c not in data.columns:
                        data[c] = rin_data[c]

        # LCFS elite indicators
        if "lcfs_credit" in data.columns and data["lcfs_credit"].notna().sum() > 30:
            lcfs_data = data.copy()
            lcfs_data["close"] = data["lcfs_credit"]
            lcfs_data = self.add_all_technical_indicators(lcfs_data, "close", "lcfs")
            for c in lcfs_data.columns:
                if c.startswith("lcfs_") and c not in data.columns:
                    data[c] = lcfs_data[c]

        # =================================================================
        # COMPUTE STALENESS FROM _last_obs COLUMNS (set by data loader)
        # PATCHED 2026-01-31: Use pre-computed last observation dates from
        # data loader instead of trying to infer from filled data
        # =================================================================
        def staleness_from_last_obs(
            last_obs_col: str, daily_index: pd.Index
        ) -> pd.Series:
            """Compute staleness (days since last observation) from _last_obs column."""
            staleness = pd.Series(999, index=daily_index)
            if last_obs_col not in data.columns:
                return staleness
            last_obs_series = data[last_obs_col]
            for idx in daily_index:
                last_obs = last_obs_series.loc[idx]
                if pd.notna(last_obs):
                    staleness.loc[idx] = (idx - last_obs).days
            return staleness

        # Get RIN staleness from _last_obs columns
        rin_staleness = pd.Series(999, index=data.index)
        for rin_col in ["rin_d4_price", "rin_d6_price", "rin_d3_price", "rin_d5_price"]:
            last_obs_col = f"{rin_col}_last_obs"
            if last_obs_col in data.columns:
                rin_staleness = staleness_from_last_obs(last_obs_col, data.index)
                if rin_staleness.min() < 999:
                    logger.info(
                        f"   BIOFUEL: Using {last_obs_col} for staleness tracking"
                    )
                    break

        # LCFS staleness from _last_obs column
        lcfs_staleness = pd.Series(999, index=data.index)
        if "lcfs_credit_last_obs" in data.columns:
            lcfs_staleness = staleness_from_last_obs("lcfs_credit_last_obs", data.index)

        # Try to get real RIN data (no forward-fill)
        rin_series, rin_source = self._get_rin_series(data)

        # EPA RIN = weekly series updated monthly; acceptable staleness 45d
        rin_is_stale = (
            rin_staleness.iloc[-1] > MAX_RIN_STALENESS_DAYS
            if len(rin_staleness) > 0
            else True
        )

        has_index = (
            "rin_pressure_index_zscore" in data.columns
            and data["rin_pressure_index_zscore"].notna().sum() > 100
        )
        index_series = data["rin_pressure_index_zscore"] if has_index else None

        if rin_series is not None and not rin_is_stale:
            # EPA fresh: use it and always blend in daily RIN pressure index when available (strengthens signal)
            epa_pressure = self.compute_zscore(rin_series, window=126, min_periods=42)
            if index_series is not None:
                policy_pressure = 0.5 * epa_pressure + 0.5 * index_series
                source = f"rin_{rin_source}_plus_index"
                base_confidence = 0.88  # Slightly higher: two anchors
            else:
                policy_pressure = epa_pressure
                source = f"rin_{rin_source}"
                base_confidence = 0.85
            rin_momentum = self._compute_rin_momentum(rin_series)
            use_momentum = True
            input_staleness = rin_staleness
            max_staleness = MAX_RIN_STALENESS_DAYS
        elif has_index:
            # EPA stale: use daily RIN pressure index only
            logger.warning(
                f"Biofuel: RIN stale ({int(rin_staleness.iloc[-1])}d) - using daily RIN pressure index"
            )
            policy_pressure = index_series
            idx_series = data.get("rin_pressure_index", data["close"])
            rin_momentum = idx_series.pct_change(21, fill_method=None) * 10
            source = "rin_pressure_index_stale_rin"
            use_momentum = True
            base_confidence = 0.65
            input_staleness = pd.Series(0, index=data.index)
            max_staleness = 999
        elif (
            "biodiesel_margin_zscore" in data.columns
            and data["biodiesel_margin_zscore"].notna().sum() > 100
        ):
            # Fallback: biodiesel margin only (e.g. pre-ETH or missing RB/ZC)
            logger.warning(
                f"Biofuel: RIN stale ({int(rin_staleness.iloc[-1])}d) - using biodiesel_margin_proxy"
            )
            policy_pressure = data["biodiesel_margin_zscore"]
            margin_proxy = data.get("biodiesel_margin_proxy", data["close"])
            rin_momentum = margin_proxy.pct_change(21, fill_method=None) * 10
            source = "margin_proxy_stale_rin"
            use_momentum = True
            base_confidence = 0.60
            input_staleness = pd.Series(0, index=data.index)
            max_staleness = 999
        elif "lcfs_credit" in data.columns and data["lcfs_credit"].notna().sum() > 100:
            # Use LCFS as alternative (no forward-fill)
            lcfs = data["lcfs_credit"]
            policy_pressure = self.compute_zscore(lcfs, window=126, min_periods=42)
            rin_momentum = lcfs.pct_change(21, fill_method=None)  # Simple momentum
            source = "lcfs"
            use_momentum = True
            base_confidence = 0.75
            input_staleness = lcfs_staleness
            max_staleness = MAX_LCFS_STALENESS_DAYS
        else:
            # Fallback to biodiesel margin proxy
            # WARNING: This is a fundamentally different signal than RIN-based policy pressure
            logger.warning(
                "Biofuel: No RIN or LCFS data available - falling back to margin_proxy"
            )
            logger.warning("   margin_proxy uses ZL/HO ratio, NOT policy incentives")
            margin_proxy = self._compute_biodiesel_margin_proxy(data)
            policy_pressure = self.compute_zscore(
                margin_proxy, window=126, min_periods=42
            )
            rin_momentum = None
            source = "margin_proxy"
            use_momentum = False
            base_confidence = 0.50
            input_staleness = pd.Series(
                0, index=data.index
            )  # Margin proxy doesn't have staleness
            max_staleness = 999  # No staleness limit for fallback

        # EMA smoothing (21-day) for noise reduction
        policy_smoothed = policy_pressure.ewm(span=21, adjust=False).mean()

        for idx in data.index:
            staleness_days = int(input_staleness.loc[idx])

            # =================================================================
            # STALENESS-AWARE GATING
            # =================================================================
            if staleness_days > max_staleness:
                # Abstain due to stale input data
                as_of = idx.date() if hasattr(idx, "date") else idx
                # Skip dates before EARLIEST_VALID_DATE
                if as_of < date(1990, 1, 1):
                    continue
                signals.append(
                    SignalOutput(
                        as_of_date=as_of,
                        bucket="biofuel",
                        signal_1=0.0,
                        signal_2=0.0,  # CONTRACT: Never None on abstain
                        confidence=0.0,  # CONTRACT: Zero confidence on abstain
                        model_type="nlp_ema",
                        max_input_age_days=staleness_days,  # P0-1: Staleness tracking
                        metadata={
                            "abstained": True,
                            "reason": f"STALE_INPUT_{source.upper()}",
                            "staleness_days": staleness_days,
                            "max_allowed_staleness": max_staleness,
                            "signal_source": source,
                            "run_hash": run_hash,
                        },
                    )
                )
                continue

            if pd.isna(policy_smoothed.loc[idx]):
                continue

            # Confidence adjustment based on data recency
            # Reduce confidence as staleness increases
            confidence = base_confidence
            if staleness_days > 7:
                # Linear degradation: lose 0.05 confidence per week beyond 7 days
                weeks_stale = (staleness_days - 7) / 7
                confidence = max(base_confidence - (0.05 * weeks_stale), 0.50)

            # Signal 2: momentum (CONTRACT: must never be None)
            sig2 = 0.0  # Default to 0.0 instead of None
            if use_momentum and rin_momentum is not None:
                momentum_val = rin_momentum.loc[idx]
                if not pd.isna(momentum_val):
                    sig2 = float(momentum_val)
                else:
                    # Penalty for missing secondary
                    confidence = confidence * 0.7

            # Determine if signal is degraded (using proxy instead of real EPA RIN)
            is_degraded = source in (
                "margin_proxy",
                "margin_proxy_stale_rin",
                "rin_pressure_index_stale_rin",
            )

            as_of = idx.date() if hasattr(idx, "date") else idx
            # Skip dates before EARLIEST_VALID_DATE
            if as_of < date(1990, 1, 1):
                continue

            signals.append(
                SignalOutput(
                    as_of_date=as_of,
                    bucket="biofuel",
                    signal_1=float(policy_smoothed.loc[idx]),
                    signal_2=sig2,
                    confidence=float(confidence),
                    model_type="nlp_ema",
                    max_input_age_days=staleness_days,  # P0-1: Staleness tracking
                    metadata={
                        # Signal source tracking (prominent placement)
                        "signal_source": source,  # "rin_d4", "rin_d6", "lcfs", or "margin_proxy"
                        "signal_degraded": is_degraded,  # True if using margin_proxy fallback
                        # Staleness tracking (NEW)
                        "input_staleness_days": staleness_days,
                        "max_allowed_staleness": max_staleness,
                        # Original fields
                        "source": source,  # Kept for backwards compatibility
                        "raw_zscore": (
                            float(policy_pressure.loc[idx])
                            if not pd.isna(policy_pressure.loc[idx])
                            else None
                        ),
                        "rin_momentum": sig2,
                        "run_hash": run_hash,
                    },
                )
            )

        # Count abstains
        abstain_count = sum(
            1 for s in signals if s.metadata and s.metadata.get("abstained", False)
        )
        logger.info(
            f"BiofuelSignalGenerator: Generated {len(signals)} signals (source: {source}, abstains: {abstain_count})"
        )
        return signals
