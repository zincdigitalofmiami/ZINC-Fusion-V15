"""
Event-based signal generators: tariff, biofuel, trump_effect.

These specialists use rule-based logic, event studies, and sentiment
aggregation rather than traditional ML models.
"""

import logging
from datetime import date
from typing import ClassVar

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
    TARIFF_EVENTS: ClassVar[list[tuple[str, str]]] = [
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

    def validate_inputs(self, data: pd.DataFrame) -> list[str]:
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

    def compute(self, data: pd.DataFrame, run_hash: str) -> list[SignalOutput]:
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
        data = self.add_all_technical_indicators(data, "close", "zl")

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
                epu_data = self.add_all_technical_indicators(epu_data, "close", prefix)
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
            # Empty list can trigger invalid downstream defaults
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
            for name in epu_components:
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
