"""
Event-based signal generators: tariff, biofuel, trump_effect.

These specialists use rule-based logic, event studies, and sentiment
aggregation rather than traditional ML models.
"""

from datetime import date
from typing import List, Optional, Dict, Any
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
        ('2018-03-22', 'Section 301 investigation'),
        ('2018-07-06', 'First $34B tariffs'),
        ('2018-09-24', '$200B tariffs at 10%'),
        ('2019-05-10', 'Tariffs raised to 25%'),
        ('2020-01-15', 'Phase One deal signed'),
        ('2025-01-20', 'Trump 2.0 inauguration'),
    ]

    def __init__(self):
        config = SignalConfig(
            bucket="tariff",
            model_type="tree",
            primary_features=[
                "close",
                # EPU COMPLEX - Full policy uncertainty suite
                "fred_eputrade",        # Trade Policy Uncertainty (CORE)
                "fred_usepuindxm",      # US Economic Policy Uncertainty (monthly)
                "fred_emvtradepolemv",  # Equity Market Vol - Trade Policy
            ],
            secondary_features=[
                # Extended EPU indices
                "fred_usepuindxd",      # US EPU (daily when available)
                "fred_chnmainlandtpu",  # China Trade Policy Uncertainty
                # Trade flow proxies
                "fred_impch",           # US Imports from China
                "fred_b235rc1q027sbea", # Customs duties (tariff receipts)
                # Market fear gauge
                "fred_vixcls",          # VIX (general uncertainty)
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
            if dt >= pd.Timestamp('2025-01-20'):
                regime.loc[idx] = 3
            elif dt >= pd.Timestamp('2020-01-15'):
                regime.loc[idx] = 2
            elif dt >= pd.Timestamp('2018-07-06'):
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
            (deadline_risk, deadline_vol_multiplier, min_days_to_deadline, deadline_names)
        """
        deadline_risk = pd.Series(0.0, index=data.index)
        vol_multiplier = pd.Series(1.0, index=data.index)
        min_days = pd.Series(365, index=data.index)
        deadline_names = {}

        if HAS_TARIFF_DEADLINES and TariffDeadlineFeatureEngine is not None:
            try:
                engine = TariffDeadlineFeatureEngine()

                for idx in data.index:
                    as_of_date = idx.date() if hasattr(idx, 'date') else idx
                    features = engine.compute_features_for_date(as_of_date)

                    deadline_risk.loc[idx] = features.deadline_risk_score
                    vol_multiplier.loc[idx] = features.deadline_vol_multiplier
                    min_days.loc[idx] = features.min_days_to_any_deadline
                    deadline_names[idx] = features.active_deadline_names

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
                as_of_date = idx.date() if hasattr(idx, 'date') else idx
                min_days_val = 365
                active_names = []

                for deadline_date, name in DEADLINES:
                    days_to_expiry = (deadline_date - as_of_date).days
                    if days_to_expiry >= 0:
                        active_names.append(name)
                        if days_to_expiry < min_days_val:
                            min_days_val = days_to_expiry

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

        return deadline_risk, vol_multiplier, min_days, deadline_names

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
        for epu_col in ["fred_eputrade", "fred_usepuindxm", "fred_emvtradepolemv",
                        "fred_usepuindxd", "fred_chnmainlandtpu"]:
            if epu_col in data.columns and data[epu_col].notna().sum() > 30:
                epu_data = data.copy()
                epu_data["close"] = data[epu_col]
                prefix = epu_col.replace("fred_", "")
                epu_data = self.add_all_elite_indicators(epu_data, "close", prefix)
                for c in epu_data.columns:
                    if c.startswith(f"{prefix}_") and c not in data.columns:
                        data[c] = epu_data[c]

        # Collect available EPU z-scores
        epu_components = {}
        weights = {}

        # Trade-specific EPU (most relevant)
        if "fred_eputrade" in data.columns:
            epu_components["trade"] = self.compute_zscore(
                data["fred_eputrade"], window=252, min_periods=126
            )
            weights["trade"] = 0.50

        # General EPU
        if "fred_usepuindxm" in data.columns:
            epu_components["general"] = self.compute_zscore(
                data["fred_usepuindxm"], window=252, min_periods=126
            )
            weights["general"] = 0.30

        # Equity market vol from trade policy
        if "fred_emvtradepolemv" in data.columns:
            epu_components["emv"] = self.compute_zscore(
                data["fred_emvtradepolemv"], window=252, min_periods=126
            )
            weights["emv"] = 0.20

        if not epu_components:
            logger.warning("TariffSignalGenerator: No EPU data available")
            return signals

        # Normalize weights
        total_weight = sum(weights.values())
        normalized = {k: v / total_weight for k, v in weights.items()}

        # Weighted composite
        tariff_risk = pd.Series(0.0, index=data.index)
        for name, zscore in epu_components.items():
            tariff_risk += normalized[name] * zscore.fillna(0)

        # Spike detection (NEW)
        epu_spike = self._detect_epu_spike(tariff_risk, threshold=2.0)

        # Tariff regime (NEW)
        tariff_regime = self._compute_tariff_regime(data)

        # Deadline risk (NEW - integrates tariff_deadlines.py)
        deadline_risk, deadline_vol_mult, min_days_to_deadline, deadline_names = self._compute_deadline_risk(data)

        # Combine EPU-based risk with deadline risk
        # When deadline is approaching, amplify the tariff risk signal
        combined_risk = tariff_risk + (deadline_risk * deadline_vol_mult - 1.0)

        for idx in data.index:
            if pd.isna(tariff_risk.loc[idx]):
                continue

            # Confidence based on component availability
            available_count = sum(
                1 for name, zs in epu_components.items()
                if not pd.isna(zs.loc[idx])
            )
            base_confidence = min(available_count / 3, 1.0) * 0.7 + 0.2

            # Boost confidence if in active tariff regime
            regime = tariff_regime.loc[idx]
            if regime >= 1:  # Active trade war or later
                base_confidence += 0.1

            confidence = min(base_confidence, 0.95)

            # Signal 2: spike indicator
            spike = epu_spike.loc[idx] if not pd.isna(epu_spike.loc[idx]) else 0.0

            # Get deadline info for this date
            dl_risk = deadline_risk.loc[idx] if not pd.isna(deadline_risk.loc[idx]) else 0.0
            dl_vol = deadline_vol_mult.loc[idx] if not pd.isna(deadline_vol_mult.loc[idx]) else 1.0
            dl_days = min_days_to_deadline.loc[idx] if not pd.isna(min_days_to_deadline.loc[idx]) else 365
            dl_names = deadline_names.get(idx, [])

            signals.append(SignalOutput(
                as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                bucket="tariff",
                signal_1=float(combined_risk.loc[idx]),  # Now includes deadline risk
                signal_2=float(spike),
                confidence=float(confidence),
                model_type="tree",
                metadata={
                    "components_used": list(epu_components.keys()),
                    "tariff_regime": int(regime),
                    "is_spike": spike > 0,
                    "epu_risk": float(tariff_risk.loc[idx]),  # Pure EPU component
                    "deadline_risk_score": float(dl_risk),
                    "deadline_vol_multiplier": float(dl_vol),
                    "min_days_to_deadline": int(dl_days),
                    "active_deadlines": dl_names,
                    "run_hash": run_hash,
                },
            ))

        # Count imminent deadlines for logging
        imminent_count = sum(1 for idx in data.index if min_days_to_deadline.loc[idx] < 60)
        logger.info(f"TariffSignalGenerator: Generated {len(signals)} signals (spikes: {int(epu_spike.sum())}, imminent_deadlines: {imminent_count})")
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
                "rin_d4_price",     # D4 RIN (biomass-based diesel) - CORE
                "rin_d6_price",     # D6 RIN (cellulosic ethanol)
                # BIODIESEL ECONOMICS
                "ho_close",         # Heating Oil (biodiesel value proxy)
                "lcfs_credit",      # CA LCFS credit price
            ],
            secondary_features=[
                # Additional RINs
                "rin_d3_price",     # D3 RIN (cellulosic biofuel)
                "rin_d5_price",     # D5 RIN (advanced biofuel)
                # Feedstock/margin inputs
                "cl_close",         # Crude (energy parity)
                "zm_close",         # Soybean meal (byproduct value)
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

        PATCHED 2026-01-21: Forward-fill RIN data (weekly updates) to daily
        frequency before returning. This fixes z-score computation which
        requires consecutive non-NaN values for rolling windows.

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
                    # Forward-fill weekly RIN data to daily frequency
                    # Limit to 14 days to prevent stale data propagation
                    series_filled = series.ffill(limit=14)
                    filled_count = series_filled.notna().sum()
                    logger.info(f"   Forward-filled to {filled_count:,} values")
                    return series_filled, col.replace("rin_", "").replace("_price", "")

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
        regime[rin_zscore > 1.0] = 1.0   # High RIN = bullish
        regime[rin_zscore < -1.0] = -1.0  # Low RIN = bearish
        return regime

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute biofuel policy pressure signal with ALL elite indicators.

        PATCHED: Now properly uses EPA RIN prices from supply.epa_rin_1d

        signal_1: Policy pressure (RIN z-score or margin proxy)
        signal_2: RIN momentum (if using real RIN data)
        """
        signals = []

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

        # Try to get real RIN data
        rin_series, rin_source = self._get_rin_series(data)

        if rin_series is not None:
            # Use real RIN data
            policy_pressure = self.compute_zscore(rin_series, window=126, min_periods=42)
            rin_momentum = self._compute_rin_momentum(rin_series)
            source = f"rin_{rin_source}"
            use_momentum = True
            base_confidence = 0.85
        elif "lcfs_credit" in data.columns:
            # Use LCFS as alternative
            lcfs = data["lcfs_credit"]
            policy_pressure = self.compute_zscore(lcfs, window=126, min_periods=42)
            rin_momentum = lcfs.pct_change(21, fill_method=None)  # Simple momentum
            source = "lcfs"
            use_momentum = True
            base_confidence = 0.75
        else:
            # Fallback to biodiesel margin proxy
            logger.info("   Using margin proxy (no RIN/LCFS data)")
            margin_proxy = self._compute_biodiesel_margin_proxy(data)
            policy_pressure = self.compute_zscore(margin_proxy, window=126, min_periods=42)
            rin_momentum = None
            source = "margin_proxy"
            use_momentum = False
            base_confidence = 0.50

        # EMA smoothing (21-day) for noise reduction
        policy_smoothed = policy_pressure.ewm(span=21, adjust=False).mean()

        for idx in data.index:
            if pd.isna(policy_smoothed.loc[idx]):
                continue

            # Signal 2: momentum (if available)
            sig2 = None
            if use_momentum and rin_momentum is not None:
                momentum_val = rin_momentum.loc[idx]
                if not pd.isna(momentum_val):
                    sig2 = float(momentum_val)

            # Confidence adjustment based on data recency
            confidence = base_confidence
            if source.startswith("rin_"):
                # Check if we have recent data (within 30 days)
                if rin_series is not None:
                    recent_mask = rin_series.index >= (idx - pd.Timedelta(days=30))
                    if recent_mask.any() and rin_series[recent_mask].notna().sum() > 0:
                        confidence = min(confidence + 0.05, 0.95)

            signals.append(SignalOutput(
                as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                bucket="biofuel",
                signal_1=float(policy_smoothed.loc[idx]),
                signal_2=sig2,
                confidence=float(confidence),
                model_type="nlp_ema",
                metadata={
                    "source": source,
                    "raw_zscore": float(policy_pressure.loc[idx]) if not pd.isna(policy_pressure.loc[idx]) else None,
                    "rin_momentum": sig2,
                    "run_hash": run_hash,
                },
            ))

        logger.info(f"BiofuelSignalGenerator: Generated {len(signals)} signals (source: {source})")
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
        config = SignalConfig(
            bucket="trump_effect",
            model_type="event_study",
            primary_features=[
                "close",
                # EPU COMPLEX - Full policy uncertainty decomposition
                "fred_eputrade",        # Trade Policy Uncertainty (CORE)
                "fred_usepuindxm",      # US Economic Policy Uncertainty
                # MARKET FEAR GAUGE
                "fred_vixcls",          # VIX (fear index)
                # CHINA EXPOSURE PROXIES
                "hg_close",             # Copper (China demand proxy)
                "fxi_close",            # China Large-Cap ETF (direct China exposure)
            ],
            secondary_features=[
                # Extended EPU
                "fred_usepuindxd",      # US EPU (daily)
                "fred_chnmainlandtpu",  # China Trade Policy Uncertainty
                "fred_emvtradepolemv",  # Equity Market Vol - Trade Policy
                # Additional China proxies
                "kweb_close",           # China Internet ETF
                "usd_cny",              # CNY (currency pressure)
                # Trump-linked proxies
                "djt_close",            # Trump Media stock (sentiment proxy)
            ],
            lookback_days=504,  # 2 years for regime detection
            min_data_points=126,
        )
        super().__init__(config)

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Require FULL EPU + China exposure + market fear."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")
        # REQUIRE EPU complex
        if "fred_eputrade" not in data.columns:
            missing.append("fred_eputrade")
        if "fred_usepuindxm" not in data.columns:
            missing.append("fred_usepuindxm")
        # REQUIRE market fear
        if "fred_vixcls" not in data.columns:
            missing.append("fred_vixcls")
        # REQUIRE China exposure
        if "hg_close" not in data.columns:
            missing.append("hg_close")
        if "fxi_close" not in data.columns:
            missing.append("fxi_close")
        return missing

    def _compute_trade_tension_proxy(self, data: pd.DataFrame) -> pd.Series:
        """
        Compute trade tension proxy from available indicators.

        Priority:
        1. Trade EPU (EPUTRADE)
        2. General EPU (USEPUINDXD)
        3. VIX as risk sentiment fallback
        """
        if "fred_eputrade" in data.columns:
            return self.compute_zscore(data["fred_eputrade"], window=252, min_periods=126)
        elif "fred_usepuindxd" in data.columns:
            return self.compute_zscore(data["fred_usepuindxd"], window=252, min_periods=126)
        elif "fred_vixcls" in data.columns:
            # VIX less specific but captures general risk
            return self.compute_zscore(data["fred_vixcls"], window=252, min_periods=126) * 0.5
        else:
            # Ultimate fallback: ZL volatility as stress proxy
            zl = data["close"]
            zl_vol = zl.pct_change(fill_method=None).rolling(21).std() * np.sqrt(252)
            return self.compute_zscore(zl_vol, window=252, min_periods=126) * 0.3

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

        NEW (2026-01-21): Trade policy share indicates trade-specific risk.
        High trade share = trade-driven uncertainty (Trump-specific)
        Low trade share = general economic uncertainty

        Returns:
            (total_epu_zscore, trade_share, trade_epu_zscore)
        """
        total_epu = pd.Series(np.nan, index=data.index)
        trade_epu = pd.Series(np.nan, index=data.index)

        # Get total EPU (prefer daily, fallback to monthly)
        if "fred_usepuindxd" in data.columns:
            total_epu = data["fred_usepuindxd"]
        elif "fred_usepuindxm" in data.columns:
            total_epu = data["fred_usepuindxm"]

        # Get trade EPU
        if "fred_eputrade" in data.columns:
            trade_epu = data["fred_eputrade"]

        # Z-scores
        total_zscore = self.compute_zscore(total_epu, window=252, min_periods=126)
        trade_zscore = self.compute_zscore(trade_epu, window=252, min_periods=126)

        # Trade share of total EPU (percentage)
        trade_share = pd.Series(0.0, index=data.index)
        if not total_epu.isna().all() and not trade_epu.isna().all():
            # Normalize to get relative proportion
            trade_share = trade_epu / total_epu.replace(0, np.nan)
            # Z-score the share (high share = trade-focused uncertainty)
            trade_share = self.compute_zscore(trade_share, window=126, min_periods=42)

        return total_zscore, trade_share, trade_zscore

    def _is_trump_regime(self, idx) -> bool:
        """Check if date is during a Trump administration."""
        dt = pd.to_datetime(idx)
        # Trump 1.0: 2017-01-20 to 2021-01-20
        # Trump 2.0: 2025-01-20 onwards
        if (dt >= pd.Timestamp('2017-01-20') and dt < pd.Timestamp('2021-01-20')):
            return True
        if dt >= pd.Timestamp('2025-01-20'):
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

        # Trade tension proxy
        trade_tension = self._compute_trade_tension_proxy(data)

        # China exposure proxy
        china_exposure = self._compute_china_exposure_proxy(data)

        # EPU decomposition (NEW)
        total_zscore, trade_share, trade_zscore = self._compute_epu_decomposition(data)
        has_decomposition = not trade_share.isna().all()

        # Event intensity = trade tension + china risk
        # Weight more toward trade tension during Trump regimes
        event_intensity = pd.Series(0.0, index=data.index)
        for idx in data.index:
            is_trump = self._is_trump_regime(idx)
            if is_trump:
                # During Trump: higher weight on trade tension
                event_intensity.loc[idx] = 0.7 * trade_tension.loc[idx] + 0.3 * china_exposure.loc[idx]
            else:
                event_intensity.loc[idx] = 0.5 * trade_tension.loc[idx] + 0.5 * china_exposure.loc[idx]

        # Signal 2: Trade uncertainty share or velocity
        if has_decomposition:
            # Use trade share as signal_2 (higher = more trade-focused uncertainty)
            signal_2_series = trade_share
        else:
            # Fallback: uncertainty velocity
            uncertainty = trade_tension.rolling(21).std()
            signal_2_series = self.compute_zscore(uncertainty, window=126, min_periods=42)

        for idx in data.index:
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
            is_trump = self._is_trump_regime(idx)
            if is_trump:
                confidence += 0.1

            sig2 = signal_2_series.loc[idx] if not pd.isna(signal_2_series.loc[idx]) else 0.0

            signals.append(SignalOutput(
                as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                bucket="trump_effect",
                signal_1=float(event_intensity.loc[idx]),
                signal_2=float(sig2),
                confidence=float(min(confidence, 0.95)),
                model_type="event_study",
                metadata={
                    "trade_tension": float(trade_tension.loc[idx]) if not pd.isna(trade_tension.loc[idx]) else None,
                    "china_exposure": float(china_exposure.loc[idx]) if not pd.isna(china_exposure.loc[idx]) else None,
                    "is_trump_regime": is_trump,
                    "has_epu_decomposition": has_decomposition,
                    "run_hash": run_hash,
                },
            ))

        trump_days = sum(1 for idx in data.index if self._is_trump_regime(idx))
        logger.info(f"TrumpEffectSignalGenerator: Generated {len(signals)} signals (trump_regime_days: {trump_days})")
        return signals
