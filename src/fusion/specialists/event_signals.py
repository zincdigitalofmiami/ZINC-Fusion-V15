"""
Event-based signal generators: tariff, biofuel, trump_effect.

These specialists use rule-based logic, event studies, and sentiment
aggregation rather than traditional ML models.
"""

from datetime import date
from typing import List
import pandas as pd
import numpy as np
import logging

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


class TariffSignalGenerator(BaseSignalGenerator):
    """
    Tariff specialist: discrete policy shocks on trade flows.

    Signal Contract:
    - signal_1: Tariff risk score (policy uncertainty level)
    - signal_2: EPU spike indicator (event detection)

    Higher signal = higher trade policy uncertainty = generally bearish ag
    Lower signal = stable trade regime = less policy risk

    Inputs: EPU indices (trade policy uncertainty), event tags
    Model: Rule-based on EPU thresholds + event intensity

    PATCHED 2026-01-21: Enhanced with spike detection and tariff regime tracking
    """

    # Key tariff event dates for regime detection
    TARIFF_EVENTS = [
        ("2018-03-22", "Section 301 investigation"),
        ("2018-07-06", "First $34B tariffs"),
        ("2018-09-24", "$200B tariffs at 10%"),
        ("2019-05-10", "Tariffs raised to 25%"),
        ("2020-01-15", "Phase One deal signed"),
        ("2025-01-20", "Trump 2.0 inauguration"),
    ]

    def __init__(self):
        config = SignalConfig(
            bucket="tariff",
            model_type="tree",
            primary_features=[
                "close",
                # EPU COMPLEX - Full policy uncertainty suite
                "fred_eputrade",  # Trade Policy Uncertainty (CORE)
                "fred_usepuindxm",  # US Economic Policy Uncertainty (monthly)
                "fred_emvtradepolemv",  # Equity Market Vol - Trade Policy
            ],
            secondary_features=[
                # Extended EPU indices
                "fred_usepuindxd",  # US EPU (daily when available)
                "fred_chnmainlandtpu",  # China Trade Policy Uncertainty
                # Trade flow proxies
                "fred_impch",  # US Imports from China
                "fred_b235rc1q027sbea",  # Customs duties (tariff receipts)
                # Market fear gauge
                "fred_vixcls",  # VIX (general uncertainty)
            ],
            lookback_days=252,
            min_data_points=63,
        )
        super().__init__(config)

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Require FULL EPU complex for tariff risk."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")
        # REQUIRE full EPU complex
        if "fred_eputrade" not in data.columns:
            missing.append("fred_eputrade")
        if "fred_usepuindxm" not in data.columns:
            missing.append("fred_usepuindxm")
        if "fred_emvtradepolemv" not in data.columns:
            missing.append("fred_emvtradepolemv")
        return missing

    def _detect_epu_spike(self, zscore: pd.Series, threshold: float = 2.0) -> pd.Series:
        """
        Detect EPU spikes (events) based on z-score threshold.

        Returns:
            1.0 = spike (tariff event likely)
            0.0 = normal
        """
        spike = pd.Series(0.0, index=zscore.index)
        spike[zscore > threshold] = 1.0
        return spike

    def _compute_tariff_regime(self, data: pd.DataFrame) -> pd.Series:
        """
        Compute tariff regime indicator based on timeline.

        Returns:
            0 = Pre-trade war (before 2018-07)
            1 = Active trade war (2018-07 to 2020-01)
            2 = Phase One (2020-01 to 2024-12)
            3 = Trump 2.0 (2025-01+)
        """
        regime = pd.Series(0, index=data.index)

        for idx in data.index:
            dt = pd.to_datetime(idx)
            if dt >= pd.Timestamp("2025-01-20"):
                regime.loc[idx] = 3
            elif dt >= pd.Timestamp("2020-01-15"):
                regime.loc[idx] = 2
            elif dt >= pd.Timestamp("2018-07-06"):
                regime.loc[idx] = 1
            else:
                regime.loc[idx] = 0

        return regime

    def _compute_deadline_risk(self, data: pd.DataFrame) -> tuple:
        """
        Compute tariff deadline risk features.

        Uses sigmoid function: risk accelerates as deadline approaches.
        - At 180+ days: ~0.05 (low risk)
        - At 90 days: 0.5 (medium risk - inflection point)
        - At 30 days: ~0.88 (high risk)
        - At 0 days: ~0.95 (very high risk)

        Returns:
            (deadline_risk, deadline_vol_multiplier, min_days_to_deadline, deadline_names, nearest_deadline_dates)
        """
        deadline_risk = pd.Series(0.0, index=data.index)
        vol_multiplier = pd.Series(1.0, index=data.index)
        min_days = pd.Series(365, index=data.index)
        deadline_names = {}
        nearest_deadline_dates = {}  # NEW: Track actual deadline dates

        if HAS_TARIFF_DEADLINES and TariffDeadlineFeatureEngine is not None:
            try:
                engine = TariffDeadlineFeatureEngine()

                for idx in data.index:
                    as_of_date = idx.date() if hasattr(idx, "date") else idx
                    features = engine.compute_features_for_date(as_of_date)

                    deadline_risk.loc[idx] = features.deadline_risk_score
                    vol_multiplier.loc[idx] = features.deadline_vol_multiplier
                    min_days.loc[idx] = features.min_days_to_any_deadline
                    deadline_names[idx] = features.active_deadline_names
                    # Track nearest deadline date if available
                    if hasattr(features, "nearest_deadline_date"):
                        nearest_deadline_dates[idx] = features.nearest_deadline_date
                    else:
                        nearest_deadline_dates[idx] = None

                logger.info(f"   Loaded tariff deadline features for {len(data)} dates")
            except Exception as e:
                logger.warning(f"   Could not load tariff deadline features: {e}")
        else:
            # Fallback: hardcoded key dates if module not available
            import math

            DEADLINES = [
                (date(2026, 11, 10), "section_301_suspension"),
                (date(2026, 12, 31), "china_ag_tariff_suspension"),
            ]

            for idx in data.index:
                as_of_date = idx.date() if hasattr(idx, "date") else idx
                min_days_val = 365
                active_names = []
                nearest_date = None  # Track nearest deadline date

                for deadline_date, name in DEADLINES:
                    days_to_expiry = (deadline_date - as_of_date).days
                    if days_to_expiry >= 0:
                        active_names.append(name)
                        if days_to_expiry < min_days_val:
                            min_days_val = days_to_expiry
                            nearest_date = deadline_date  # Track the date

                # Sigmoid risk calculation
                if min_days_val < 365:
                    exponent = (min_days_val - 90) / 30
                    risk = 1.0 / (1.0 + math.exp(exponent))
                else:
                    risk = 0.0

                deadline_risk.loc[idx] = risk
                vol_multiplier.loc[idx] = 1.0 + (0.5 * risk)
                min_days.loc[idx] = min_days_val
                deadline_names[idx] = active_names
                nearest_deadline_dates[idx] = nearest_date  # Store the date

        return (
            deadline_risk,
            vol_multiplier,
            min_days,
            deadline_names,
            nearest_deadline_dates,
        )

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute tariff risk score with ALL elite indicators.

        PATCHED 2026-01-21: Enhanced with spike detection and regime tracking

        signal_1: Trade policy uncertainty composite z-score
        signal_2: EPU spike indicator (event flag)
        """
        signals = []

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL AND EPU SERIES
        # =====================================================================
        data = self.add_all_elite_indicators(data, "close", "zl")

        # Add elite indicators for EPU series
        for epu_col in [
            "fred_eputrade",
            "fred_usepuindxm",
            "fred_emvtradepolemv",
            "fred_usepuindxd",
            "fred_chnmainlandtpu",
        ]:
            if epu_col in data.columns and data[epu_col].notna().sum() > 30:
                epu_data = data.copy()
                epu_data["close"] = data[epu_col]
                prefix = epu_col.replace("fred_", "")
                epu_data = self.add_all_elite_indicators(epu_data, "close", prefix)
                for c in epu_data.columns:
                    if c.startswith(f"{prefix}_") and c not in data.columns:
                        data[c] = epu_data[c]

        # =================================================================
        # EPU Z-SCORE COMPUTATION - FREQUENCY-AWARE
        # Monthly series (EPUTRADE, USEPUINDXM, EMVTRADEPOLEMV) need:
        #   - min_periods at monthly cadence (24-36 months, not 126 days)
        #   - Forward-fill to daily with staleness tracking
        # Daily series (USEPUINDXD) can use standard daily z-score
        # =================================================================
        MAX_MONTHLY_EPU_STALENESS_DAYS = 45  # ~1.5 months + buffer

        epu_components = {}
        epu_staleness = {}  # Track staleness for each component
        weights = {}

        def compute_monthly_zscore_to_daily(
            monthly_series: pd.Series, daily_index: pd.Index
        ) -> tuple:
            """
            Compute z-score at native monthly frequency, then map to daily.

            Returns:
                (daily_zscore_series, staleness_days_series)
            """
            # Extract non-null monthly values
            monthly_vals = monthly_series.dropna()
            if len(monthly_vals) < 24:  # Need 2+ years of monthly data
                return pd.Series(np.nan, index=daily_index), pd.Series(
                    999, index=daily_index
                )

            # Compute z-score at monthly frequency (min_periods=24 = 2 years)
            monthly_zscore = (
                monthly_vals - monthly_vals.rolling(36, min_periods=24).mean()
            ) / monthly_vals.rolling(36, min_periods=24).std()

            # Map to daily WITHOUT forward-fill (policy)
            daily_zscore = monthly_zscore.reindex(daily_index)

            # Compute staleness (days since last valid monthly update)
            staleness = pd.Series(np.nan, index=daily_index)
            for idx in daily_index:
                # Find most recent monthly value
                prior_monthly = monthly_vals.index[monthly_vals.index <= idx]
                if len(prior_monthly) > 0:
                    last_update = prior_monthly[-1]
                    staleness.loc[idx] = (idx - last_update).days
                else:
                    staleness.loc[idx] = 999

            return daily_zscore, staleness

        # PRIMARY: Daily EPU (USEPUINDXD) - 99% coverage, no staleness issues
        if (
            "fred_usepuindxd" in data.columns
            and data["fred_usepuindxd"].notna().sum() > 252
        ):
            daily_epu = data["fred_usepuindxd"]
            epu_components["daily"] = self.compute_zscore(
                daily_epu, window=252, min_periods=126
            )
            # Staleness for daily = days since last non-null value
            staleness = pd.Series(0, index=data.index)
            last_valid = None
            for idx in data.index:
                if not pd.isna(daily_epu.loc[idx]):
                    last_valid = idx
                    staleness.loc[idx] = 0
                elif last_valid is not None:
                    staleness.loc[idx] = (idx - last_valid).days
                else:
                    staleness.loc[idx] = 999
            epu_staleness["daily"] = staleness
            weights["daily"] = 0.50  # Daily EPU is primary when available
            logger.info(
                f"   TARIFF: Using daily EPU (USEPUINDXD), {epu_components['daily'].notna().sum()} non-null z-scores"
            )

        # SECONDARY: Trade-specific EPU (monthly) - most relevant for tariff risk
        if "fred_eputrade" in data.columns and data["fred_eputrade"].notna().sum() > 24:
            zscore, staleness = compute_monthly_zscore_to_daily(
                data["fred_eputrade"], data.index
            )
            if zscore.notna().sum() > 0:
                epu_components["trade"] = zscore
                epu_staleness["trade"] = staleness
                weights["trade"] = 0.30
                logger.info(
                    f"   TARIFF: Using monthly trade EPU, {zscore.notna().sum()} non-null z-scores"
                )

        # TERTIARY: Equity market vol from trade policy (monthly)
        if (
            "fred_emvtradepolemv" in data.columns
            and data["fred_emvtradepolemv"].notna().sum() > 24
        ):
            zscore, staleness = compute_monthly_zscore_to_daily(
                data["fred_emvtradepolemv"], data.index
            )
            if zscore.notna().sum() > 0:
                epu_components["emv"] = zscore
                epu_staleness["emv"] = staleness
                weights["emv"] = 0.20
                logger.info(
                    f"   TARIFF: Using monthly EMV trade, {zscore.notna().sum()} non-null z-scores"
                )

        if not epu_components:
            # P0-2 FIX: Emit abstain signals instead of returning empty list
            # Empty list causes downstream to fill with -1.0 placeholder
            logger.warning(
                "TariffSignalGenerator: No EPU data - emitting abstain signals"
            )
            for idx in data.index:
                as_of = idx.date() if hasattr(idx, "date") else idx
                # Skip dates before EARLIEST_VALID_DATE (handled by SignalOutput validation)
                if as_of < date(1990, 1, 1):
                    continue
                reason = "PRE_EPU_ERA" if as_of < date(1985, 1, 1) else "NO_EPU_DATA"
                signals.append(
                    SignalOutput(
                        as_of_date=as_of,
                        bucket="tariff",
                        signal_1=0.0,  # Neutral abstain (NOT -1.0)
                        signal_2=0.0,
                        confidence=0.0,  # Zero confidence = abstain
                        model_type="tree",
                        max_input_age_days=999,  # Max staleness for abstain
                        metadata={"abstained": True, "reason": reason},
                    )
                )
            return signals

        # Normalize weights
        total_weight = sum(weights.values())
        normalized = {k: v / total_weight for k, v in weights.items()}

        # Weighted composite with staleness-aware gating
        tariff_risk = pd.Series(np.nan, index=data.index)
        is_stale = pd.Series(False, index=data.index)
        stale_components = {idx: [] for idx in data.index}

        for idx in data.index:
            # Check if ALL components are stale for this date
            all_stale = True
            weighted_sum = 0.0
            weight_used = 0.0

            for name, zscore in epu_components.items():
                staleness_days = (
                    epu_staleness[name].loc[idx] if name in epu_staleness else 0
                )
                z_val = zscore.loc[idx] if not pd.isna(zscore.loc[idx]) else None

                # Monthly components: check against MAX_MONTHLY_EPU_STALENESS_DAYS
                # Daily components: check against 7 days
                max_staleness = 7 if name == "daily" else MAX_MONTHLY_EPU_STALENESS_DAYS

                if staleness_days > max_staleness:
                    stale_components[idx].append(f"{name}:{staleness_days}d")
                elif z_val is not None:
                    all_stale = False
                    weighted_sum += normalized[name] * z_val
                    weight_used += normalized[name]

            if all_stale:
                is_stale.loc[idx] = True
                tariff_risk.loc[idx] = np.nan  # Will trigger abstain
            elif weight_used > 0:
                tariff_risk.loc[idx] = weighted_sum / weight_used  # Re-normalize
            else:
                tariff_risk.loc[idx] = np.nan

        # Spike detection (NEW)
        epu_spike = self._detect_epu_spike(tariff_risk, threshold=2.0)

        # Tariff regime (NEW)
        tariff_regime = self._compute_tariff_regime(data)

        # Deadline risk (NEW - integrates tariff_deadlines.py)
        (
            deadline_risk,
            deadline_vol_mult,
            min_days_to_deadline,
            deadline_names,
            nearest_deadline_dates,
        ) = self._compute_deadline_risk(data)

        # Combine EPU-based risk with deadline risk
        # When deadline is approaching, amplify the tariff risk signal
        # FIX 2026-01-30: Corrected parentheses - additive term must be 0 when deadline_risk=0
        combined_risk = tariff_risk + deadline_risk * (deadline_vol_mult - 1.0)

        for idx in data.index:
            regime = tariff_regime.loc[idx]

            # Check for staleness-triggered abstain
            if is_stale.loc[idx] or pd.isna(tariff_risk.loc[idx]):
                # Emit abstain signal with reason
                stale_list = stale_components.get(idx, [])
                as_of = idx.date() if hasattr(idx, "date") else idx
                # Skip dates before EARLIEST_VALID_DATE
                if as_of < date(1990, 1, 1):
                    continue
                signals.append(
                    SignalOutput(
                        as_of_date=as_of,
                        bucket="tariff",
                        signal_1=0.0,
                        signal_2=0.0,
                        confidence=0.2,  # Degraded confidence
                        model_type="tree",
                        max_input_age_days=999,  # P0-1: Staleness tracking for abstain
                        metadata={
                            "abstained": True,
                            "reason": (
                                "EPU_STALE" if stale_list else "INSUFFICIENT_DATA"
                            ),
                            "stale_components": stale_list,
                            "tariff_regime": int(regime),
                            "run_hash": run_hash,
                        },
                    )
                )
                continue

            # Confidence based on component availability and staleness
            available_count = sum(
                1 for name, zs in epu_components.items() if not pd.isna(zs.loc[idx])
            )
            base_confidence = (
                min(available_count / len(epu_components), 1.0) * 0.7 + 0.2
            )

            # Boost confidence if in active tariff regime
            if regime >= 1:  # Active trade war or later
                base_confidence += 0.1

            confidence = min(base_confidence, 0.95)

            # Signal 2: spike indicator
            spike = epu_spike.loc[idx] if not pd.isna(epu_spike.loc[idx]) else 0.0

            # Get deadline info for this date
            dl_risk = (
                deadline_risk.loc[idx] if not pd.isna(deadline_risk.loc[idx]) else 0.0
            )
            dl_vol = (
                deadline_vol_mult.loc[idx]
                if not pd.isna(deadline_vol_mult.loc[idx])
                else 1.0
            )
            dl_days = (
                min_days_to_deadline.loc[idx]
                if not pd.isna(min_days_to_deadline.loc[idx])
                else 365
            )
            dl_names = deadline_names.get(idx, [])
            dl_nearest_date = nearest_deadline_dates.get(
                idx
            )  # May be None if no deadline

            # P0-1: Compute max staleness across EPU components for this date
            max_staleness = 0
            for name in epu_components.keys():
                if name in epu_staleness:
                    stale_val = epu_staleness[name].loc[idx]
                    if not pd.isna(stale_val):
                        max_staleness = max(max_staleness, int(stale_val))

            as_of = idx.date() if hasattr(idx, "date") else idx
            # Skip dates before EARLIEST_VALID_DATE
            if as_of < date(1990, 1, 1):
                continue

            signals.append(
                SignalOutput(
                    as_of_date=as_of,
                    bucket="tariff",
                    signal_1=float(
                        combined_risk.loc[idx]
                    ),  # Now includes deadline risk
                    signal_2=float(spike),
                    confidence=float(confidence),
                    model_type="tree",
                    max_input_age_days=max_staleness,  # P0-1: Staleness tracking
                    metadata={
                        "components_used": list(epu_components.keys()),
                        "tariff_regime": int(regime),
                        "is_spike": spike > 0,
                        "epu_risk": float(tariff_risk.loc[idx]),  # Pure EPU component
                        # Deadline proximity tracking (Task 4.3)
                        "nearest_deadline": (
                            dl_nearest_date.isoformat() if dl_nearest_date else None
                        ),
                        "days_to_deadline": int(dl_days),
                        "deadline_risk_factor": float(dl_risk),
                        # Original fields (kept for backwards compatibility)
                        "deadline_risk_score": float(dl_risk),
                        "deadline_vol_multiplier": float(dl_vol),
                        "min_days_to_deadline": int(dl_days),
                        "active_deadlines": dl_names,
                        "run_hash": run_hash,
                    },
                )
            )

        # Count imminent deadlines for logging
        imminent_count = sum(
            1 for idx in data.index if min_days_to_deadline.loc[idx] < 60
        )
        logger.info(
            f"TariffSignalGenerator: Generated {len(signals)} signals (spikes: {int(epu_spike.sum())}, imminent_deadlines: {imminent_count})"
        )
        return signals


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

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
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

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
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
        data = self.add_all_elite_indicators(data, "close", "zl")

        # HO elite indicators (biodiesel proxy)
        if "ho_close" in data.columns and data["ho_close"].notna().sum() > 30:
            ho_data = data.copy()
            ho_data["close"] = data["ho_close"]
            ho_data = self.add_all_elite_indicators(ho_data, "close", "ho")
            for c in ho_data.columns:
                if c.startswith("ho_") and c not in data.columns:
                    data[c] = ho_data[c]

        # RIN elite indicators
        for rin_col in ["rin_d4_price", "rin_d6_price"]:
            if rin_col in data.columns and data[rin_col].notna().sum() > 30:
                rin_data = data.copy()
                rin_data["close"] = data[rin_col]
                prefix = rin_col.replace("_price", "")
                rin_data = self.add_all_elite_indicators(rin_data, "close", prefix)
                for c in rin_data.columns:
                    if c.startswith(f"{prefix}_") and c not in data.columns:
                        data[c] = rin_data[c]

        # LCFS elite indicators
        if "lcfs_credit" in data.columns and data["lcfs_credit"].notna().sum() > 30:
            lcfs_data = data.copy()
            lcfs_data["close"] = data["lcfs_credit"]
            lcfs_data = self.add_all_elite_indicators(lcfs_data, "close", "lcfs")
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


# =============================================================================
# TRUMP EFFECT SIGNAL GENERATOR
# =============================================================================


class TrumpEffectSignalGenerator(BaseSignalGenerator):
    """
    Trump Effect specialist: trade/rhetoric risk premium.

    Signal Contract:
    - signal_1: Event intensity (trade action/rhetoric level)
    - signal_2: Policy uncertainty score (with trade share decomposition)

    This specialist captures regime-dependent policy dynamics:
    - Trade war escalation/de-escalation
    - Tariff announcements and retaliations
    - EPA waiver activity
    - MFP (Market Facilitation Program) payments

    Inputs: EPU indices, news sentiment, proxy tickers (HG copper)
    Model: Event study + sentiment composite

    PATCHED 2026-01-21: Added EPU decomposition (trade share) and regime amplification
    """

    def __init__(self):
        # =====================================================================
        # STRICT 95%+ COVERAGE POLICY - NO EXCEPTIONS
        # All primary features MUST have 95%+ coverage from 2017-present
        # =====================================================================
        config = SignalConfig(
            bucket="trump_effect",
            model_type="event_study",
            primary_features=[
                # === 100% COVERAGE ===
                "fred_usepuindxd",  # US EPU Daily (100%)
                "fred_vixcls",  # VIX (100%)
                "fred_dff",  # Fed Funds Rate (100%)
                "fred_dgs10",  # 10Y Treasury (100%)
                "fred_t10y2y",  # Yield Curve 10Y-2Y (100%)
                "fred_bamlc0a0cm",  # Investment Grade Credit Spread (100%)
                "fred_bamlh0a0hym2",  # High Yield Credit Spread (100%)
                # === 99%+ COVERAGE ===
                "hg_close",  # Copper - China demand proxy (99.2%)
                "6e_close",  # EUR/USD futures (99.6%)
                "6j_close",  # USD/JPY futures (99.6%)
                "6m_close",  # MXN/USD futures (98.2%)
                "zn_close",  # 10Y Treasury futures (99.0%)
                "es_close",  # S&P 500 futures (99.2%)
                "trump_weighted_action_score",  # Trump action intensity (99.7%)
            ],
            secondary_features=[
                # 95-99% coverage - acceptable for secondary
                "fred_ovxcls",  # Oil VIX (100%)
                "fred_gvzcls",  # Gold VIX (99.7%)
                "fred_vxvcls",  # VIX of VIX (100%)
                "fred_dgs2",  # 2Y Treasury (100%)
                "6a_close",  # AUD/USD futures (99.5%)
                "6b_close",  # GBP/USD futures (99.5%)
                "6c_close",  # CAD/USD futures (99.4%)
                "6l_close",  # BRL/USD futures (95.1%)
                "zb_close",  # 30Y Treasury futures (99.0%)
                "zf_close",  # 5Y Treasury futures (98.5%)
                "nq_close",  # Nasdaq futures (99.2%)
                "trump_eo_count_7d",  # EO count 7d (99.7%)
                "trump_action_velocity",  # Action velocity (99.7%)
                "tariff_deadline_count",  # Tariff deadlines (100%)
                "legis_eo_count",  # Executive orders (100%)
                # <95% coverage - sparse but useful when available
                "fxi_close",  # China ETF (62.6% - starts 2019)
                "kweb_close",  # China Internet ETF (62.6%)
                "fred_nfci",  # Financial Conditions (83.3%)
                "fred_eputrade",  # Trade EPU monthly (19.5%)
                "usd_cny",  # CNY rate (50%)
                "usd_mxn",  # MXN rate (50%)
            ],
            lookback_days=504,
            min_data_points=126,
        )
        super().__init__(config)

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """
        Validate inputs - ONLY require 95%+ coverage features.

        Required (all 95%+ coverage):
        - fred_usepuindxd (100%)
        - fred_vixcls (100%)
        - fred_dff (100%)
        - hg_close (99.2%)
        - 6e_close (99.6%)
        """
        missing = []
        # Core uncertainty
        if "fred_usepuindxd" not in data.columns:
            missing.append("fred_usepuindxd")
        # Market fear
        if "fred_vixcls" not in data.columns:
            missing.append("fred_vixcls")
        # Fed policy
        if "fred_dff" not in data.columns:
            missing.append("fred_dff")
        # China demand (via copper)
        if "hg_close" not in data.columns:
            missing.append("hg_close")
        # FX exposure
        if "6e_close" not in data.columns:
            missing.append("6e_close")
        return missing

    def _compute_trade_tension_proxy(self, data: pd.DataFrame) -> tuple:
        """
        Compute trade tension proxy from available indicators.

        FIXED 2026-01-31: Priority changed - daily EPU first (99% coverage)
        Monthly EPUTRADE used only as supplementary signal.

        Priority:
        1. Daily EPU (USEPUINDXD) - 99% coverage, no staleness issues
        2. VIX as risk sentiment fallback
        3. ZL volatility as ultimate fallback

        Returns:
            (trade_tension_series, staleness_series)
        """
        staleness = pd.Series(0, index=data.index)

        # PRIMARY: Daily EPU (USEPUINDXD) - 99% coverage
        if (
            "fred_usepuindxd" in data.columns
            and data["fred_usepuindxd"].notna().sum() > 252
        ):
            zscore = self.compute_zscore(
                data["fred_usepuindxd"], window=252, min_periods=126
            )
            # Compute staleness
            last_valid = None
            for idx in data.index:
                if not pd.isna(data["fred_usepuindxd"].loc[idx]):
                    last_valid = idx
                    staleness.loc[idx] = 0
                elif last_valid is not None:
                    staleness.loc[idx] = (idx - last_valid).days
                else:
                    staleness.loc[idx] = 999
            return zscore, staleness

        # FALLBACK: VIX as risk sentiment proxy
        if "fred_vixcls" in data.columns and data["fred_vixcls"].notna().sum() > 252:
            zscore = (
                self.compute_zscore(data["fred_vixcls"], window=252, min_periods=126)
                * 0.5
            )
            last_valid = None
            for idx in data.index:
                if not pd.isna(data["fred_vixcls"].loc[idx]):
                    last_valid = idx
                    staleness.loc[idx] = 0
                elif last_valid is not None:
                    staleness.loc[idx] = (idx - last_valid).days
                else:
                    staleness.loc[idx] = 999
            return zscore, staleness

        # ULTIMATE FALLBACK: ZL volatility as stress proxy
        zl = data["close"]
        zl_vol = zl.pct_change(fill_method=None).rolling(21).std() * np.sqrt(252)
        zscore = self.compute_zscore(zl_vol, window=252, min_periods=126) * 0.3
        return zscore, staleness

    def _compute_china_exposure_proxy(self, data: pd.DataFrame) -> pd.Series:
        """
        Compute China exposure/risk proxy.

        Uses copper (HG) as the China demand proxy.
        """
        if "hg_close" in data.columns and not data["hg_close"].isna().all():
            # Copper as China demand proxy
            hg = data["hg_close"]
            hg_ret = hg.pct_change(21, fill_method=None)
            return -self.compute_zscore(hg_ret, window=126, min_periods=42) * 0.5
        return pd.Series(0.0, index=data.index)

    def _compute_epu_decomposition(self, data: pd.DataFrame) -> tuple:
        """
        Decompose EPU into trade vs total share.

        FIXED 2026-01-31: Handle monthly EPUTRADE at native frequency.

        Returns:
            (total_epu_zscore, trade_share, trade_epu_zscore)
        """
        # Total EPU from daily source (primary)
        total_zscore = pd.Series(np.nan, index=data.index)
        if (
            "fred_usepuindxd" in data.columns
            and data["fred_usepuindxd"].notna().sum() > 252
        ):
            total_zscore = self.compute_zscore(
                data["fred_usepuindxd"], window=252, min_periods=126
            )

        # Trade EPU is MONTHLY - compute at native frequency then map to daily
        trade_zscore = pd.Series(np.nan, index=data.index)
        if "fred_eputrade" in data.columns and data["fred_eputrade"].notna().sum() > 24:
            monthly_vals = data["fred_eputrade"].dropna()
            if len(monthly_vals) >= 24:
                # Z-score at monthly frequency (36 months window, 24 min)
                monthly_zscore = (
                    monthly_vals - monthly_vals.rolling(36, min_periods=24).mean()
                ) / monthly_vals.rolling(36, min_periods=24).std()
                # Map to daily without forward-fill (policy)
                trade_zscore = monthly_zscore.reindex(data.index)

        # Trade share: ratio of trade EPU to total EPU (compute on matching monthly dates)
        trade_share = pd.Series(np.nan, index=data.index)
        if "fred_eputrade" in data.columns and "fred_usepuindxm" in data.columns:
            trade_epu = data["fred_eputrade"].dropna()
            total_epu_m = data["fred_usepuindxm"].dropna()
            if len(trade_epu) > 24 and len(total_epu_m) > 24:
                # Compute share on aligned dates
                common_dates = trade_epu.index.intersection(total_epu_m.index)
                if len(common_dates) > 24:
                    share = trade_epu.loc[common_dates] / total_epu_m.loc[
                        common_dates
                    ].replace(0, np.nan)
                    share_zscore = (
                        share - share.rolling(36, min_periods=24).mean()
                    ) / share.rolling(36, min_periods=24).std()
                    trade_share = share_zscore.reindex(data.index)

        return total_zscore, trade_share, trade_zscore

    def _is_trump_regime(self, idx) -> bool:
        """Check if date is during a Trump administration."""
        dt = pd.to_datetime(idx)
        # Trump 1.0: 2017-01-20 to 2021-01-20
        # Trump 2.0: 2025-01-20 onwards
        if dt >= pd.Timestamp("2017-01-20") and dt < pd.Timestamp("2021-01-20"):
            return True
        if dt >= pd.Timestamp("2025-01-20"):
            return True
        return False

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute Trump Effect signals with ALL elite indicators.

        PATCHED 2026-01-21: Enhanced with EPU decomposition and regime amplification

        signal_1: Event intensity (trade tension + China exposure)
        signal_2: Trade uncertainty share (trade EPU / total EPU)
        """
        signals = []

        # =====================================================================
        # ADD ALL 81 ELITE INDICATORS FOR ZL, HG, FXI, KWEB, EPU
        # =====================================================================
        data = self.add_all_elite_indicators(data, "close", "zl")

        # HG elite indicators (China demand)
        if "hg_close" in data.columns and data["hg_close"].notna().sum() > 30:
            hg_data = data.copy()
            hg_data["close"] = data["hg_close"]
            hg_data = self.add_all_elite_indicators(hg_data, "close", "hg")
            for c in hg_data.columns:
                if c.startswith("hg_") and c not in data.columns:
                    data[c] = hg_data[c]

        # FXI elite indicators (China ETF)
        if "fxi_close" in data.columns and data["fxi_close"].notna().sum() > 30:
            fxi_data = data.copy()
            fxi_data["close"] = data["fxi_close"]
            fxi_data = self.add_all_elite_indicators(fxi_data, "close", "fxi")
            for c in fxi_data.columns:
                if c.startswith("fxi_") and c not in data.columns:
                    data[c] = fxi_data[c]

        # KWEB elite indicators (China tech)
        if "kweb_close" in data.columns and data["kweb_close"].notna().sum() > 30:
            kweb_data = data.copy()
            kweb_data["close"] = data["kweb_close"]
            kweb_data = self.add_all_elite_indicators(kweb_data, "close", "kweb")
            for c in kweb_data.columns:
                if c.startswith("kweb_") and c not in data.columns:
                    data[c] = kweb_data[c]

        # VIX elite indicators
        if "fred_vixcls" in data.columns and data["fred_vixcls"].notna().sum() > 30:
            vix_data = data.copy()
            vix_data["close"] = data["fred_vixcls"]
            vix_data = self.add_all_elite_indicators(vix_data, "close", "vix")
            for c in vix_data.columns:
                if c.startswith("vix_") and c not in data.columns:
                    data[c] = vix_data[c]

        # EPU elite indicators
        for epu_col in ["fred_eputrade", "fred_usepuindxm"]:
            if epu_col in data.columns and data[epu_col].notna().sum() > 30:
                epu_data = data.copy()
                epu_data["close"] = data[epu_col]
                prefix = epu_col.replace("fred_", "")
                epu_data = self.add_all_elite_indicators(epu_data, "close", prefix)
                for c in epu_data.columns:
                    if c.startswith(f"{prefix}_") and c not in data.columns:
                        data[c] = epu_data[c]

        # Trade tension proxy (now returns tuple with staleness)
        trade_tension, trade_staleness = self._compute_trade_tension_proxy(data)
        MAX_EPU_STALENESS_DAYS = 7  # Daily EPU should be within 7 days

        # China exposure proxy
        china_exposure = self._compute_china_exposure_proxy(data)

        # =====================================================================
        # COMPUTE INDIVIDUAL EVENT COMPONENT Z-SCORES (Task 4.4)
        # =====================================================================
        # FXI z-score (China ETF - direct China exposure)
        fxi_zscore = pd.Series(np.nan, index=data.index)
        if "fxi_close" in data.columns and data["fxi_close"].notna().sum() > 30:
            fxi_ret = data["fxi_close"].pct_change(21, fill_method=None)
            fxi_zscore = self.compute_zscore(fxi_ret, window=126, min_periods=42)

        # VIX z-score (fear gauge)
        vix_zscore = pd.Series(np.nan, index=data.index)
        if "fred_vixcls" in data.columns and data["fred_vixcls"].notna().sum() > 30:
            vix_zscore = self.compute_zscore(
                data["fred_vixcls"], window=252, min_periods=126
            )

        # EPU decomposition (handles monthly EPUTRADE properly)
        total_zscore, trade_share, trade_epu_zscore = self._compute_epu_decomposition(
            data
        )
        has_decomposition = not trade_share.isna().all()

        # Event intensity = trade tension + china risk
        # Weight more toward trade tension during Trump regimes
        # Also track staleness for gating
        event_intensity = pd.Series(np.nan, index=data.index)
        is_stale = pd.Series(False, index=data.index)

        for idx in data.index:
            # Check staleness first
            staleness_days = trade_staleness.loc[idx]
            if staleness_days > MAX_EPU_STALENESS_DAYS:
                is_stale.loc[idx] = True
                continue

            if pd.isna(trade_tension.loc[idx]):
                continue

            is_trump = self._is_trump_regime(idx)
            china_val = (
                china_exposure.loc[idx] if not pd.isna(china_exposure.loc[idx]) else 0.0
            )

            if is_trump:
                # During Trump: higher weight on trade tension
                event_intensity.loc[idx] = (
                    0.7 * trade_tension.loc[idx] + 0.3 * china_val
                )
            else:
                event_intensity.loc[idx] = (
                    0.5 * trade_tension.loc[idx] + 0.5 * china_val
                )

        # Signal 2: Trade uncertainty share or velocity
        if has_decomposition:
            # Use trade share as signal_2 (higher = more trade-focused uncertainty)
            signal_2_series = trade_share
        else:
            # Fallback: uncertainty velocity
            uncertainty = trade_tension.rolling(21).std()
            signal_2_series = self.compute_zscore(
                uncertainty, window=126, min_periods=42
            )

        for idx in data.index:
            is_trump = self._is_trump_regime(idx)

            # Check for staleness-triggered abstain
            if is_stale.loc[idx]:
                staleness_days = int(trade_staleness.loc[idx])
                as_of = idx.date() if hasattr(idx, "date") else idx
                # Skip dates before EARLIEST_VALID_DATE
                if as_of < date(1990, 1, 1):
                    continue
                signals.append(
                    SignalOutput(
                        as_of_date=as_of,
                        bucket="trump_effect",
                        signal_1=0.0,
                        signal_2=0.0,
                        confidence=0.2,
                        model_type="event_study",
                        max_input_age_days=staleness_days,  # P0-1: Staleness tracking
                        metadata={
                            "abstained": True,
                            "reason": "EPU_STALE",
                            "staleness_days": staleness_days,
                            "is_trump_regime": is_trump,
                            "run_hash": run_hash,
                        },
                    )
                )
                continue

            if pd.isna(event_intensity.loc[idx]):
                continue

            # Determine confidence based on data quality
            confidence = 0.5
            if "fred_eputrade" in data.columns:
                try:
                    if not pd.isna(data.loc[idx, "fred_eputrade"]):
                        confidence += 0.15
                except:
                    pass
            if "hg_close" in data.columns:
                try:
                    if not pd.isna(data.loc[idx, "hg_close"]):
                        confidence += 0.1
                except:
                    pass
            if has_decomposition:
                confidence += 0.1  # Bonus for EPU decomposition

            # Amplify confidence during Trump regimes (signal is more meaningful)
            if is_trump:
                confidence += 0.1

            sig2 = (
                signal_2_series.loc[idx]
                if not pd.isna(signal_2_series.loc[idx])
                else 0.0
            )

            # Task 4.4: Event detection flag (threshold = 1.5 for significant events)
            event_detected = float(event_intensity.loc[idx]) > 1.5

            as_of = idx.date() if hasattr(idx, "date") else idx
            # Skip dates before EARLIEST_VALID_DATE
            if as_of < date(1990, 1, 1):
                continue

            # P0-1: Get staleness for this date
            staleness_days = (
                int(trade_staleness.loc[idx])
                if not pd.isna(trade_staleness.loc[idx])
                else 0
            )

            signals.append(
                SignalOutput(
                    as_of_date=as_of,
                    bucket="trump_effect",
                    signal_1=float(event_intensity.loc[idx]),
                    signal_2=float(sig2),
                    confidence=float(min(confidence, 0.95)),
                    model_type="event_study",
                    max_input_age_days=staleness_days,  # P0-1: Staleness tracking
                    metadata={
                        "trade_tension": (
                            float(trade_tension.loc[idx])
                            if not pd.isna(trade_tension.loc[idx])
                            else None
                        ),
                        "china_exposure": (
                            float(china_exposure.loc[idx])
                            if not pd.isna(china_exposure.loc[idx])
                            else None
                        ),
                        "is_trump_regime": is_trump,
                        "has_epu_decomposition": has_decomposition,
                        # Task 4.4: Event detection and component z-scores
                        "event_detected": event_detected,
                        "event_components": {
                            "fxi_zscore": (
                                float(fxi_zscore.loc[idx])
                                if not pd.isna(fxi_zscore.loc[idx])
                                else None
                            ),
                            "vix_zscore": (
                                float(vix_zscore.loc[idx])
                                if not pd.isna(vix_zscore.loc[idx])
                                else None
                            ),
                            "trade_epu_zscore": (
                                float(trade_epu_zscore.loc[idx])
                                if not pd.isna(trade_epu_zscore.loc[idx])
                                else None
                            ),
                        },
                        "run_hash": run_hash,
                    },
                )
            )

        trump_days = sum(1 for idx in data.index if self._is_trump_regime(idx))
        logger.info(
            f"TrumpEffectSignalGenerator: Generated {len(signals)} signals (trump_regime_days: {trump_days})"
        )
        return signals
