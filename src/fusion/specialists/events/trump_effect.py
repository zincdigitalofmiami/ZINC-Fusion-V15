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

    def validate_inputs(self, data: pd.DataFrame) -> list[str]:
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
        return dt >= pd.Timestamp("2025-01-20")

    def compute(self, data: pd.DataFrame, run_hash: str) -> list[SignalOutput]:
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
        data = self.add_all_technical_indicators(data, "close", "zl")

        # HG elite indicators (China demand)
        if "hg_close" in data.columns and data["hg_close"].notna().sum() > 30:
            hg_data = data.copy()
            hg_data["close"] = data["hg_close"]
            hg_data = self.add_all_technical_indicators(hg_data, "close", "hg")
            for c in hg_data.columns:
                if c.startswith("hg_") and c not in data.columns:
                    data[c] = hg_data[c]

        # FXI elite indicators (China ETF)
        if "fxi_close" in data.columns and data["fxi_close"].notna().sum() > 30:
            fxi_data = data.copy()
            fxi_data["close"] = data["fxi_close"]
            fxi_data = self.add_all_technical_indicators(fxi_data, "close", "fxi")
            for c in fxi_data.columns:
                if c.startswith("fxi_") and c not in data.columns:
                    data[c] = fxi_data[c]

        # KWEB elite indicators (China tech)
        if "kweb_close" in data.columns and data["kweb_close"].notna().sum() > 30:
            kweb_data = data.copy()
            kweb_data["close"] = data["kweb_close"]
            kweb_data = self.add_all_technical_indicators(kweb_data, "close", "kweb")
            for c in kweb_data.columns:
                if c.startswith("kweb_") and c not in data.columns:
                    data[c] = kweb_data[c]

        # VIX elite indicators
        if "fred_vixcls" in data.columns and data["fred_vixcls"].notna().sum() > 30:
            vix_data = data.copy()
            vix_data["close"] = data["fred_vixcls"]
            vix_data = self.add_all_technical_indicators(vix_data, "close", "vix")
            for c in vix_data.columns:
                if c.startswith("vix_") and c not in data.columns:
                    data[c] = vix_data[c]

        # EPU elite indicators
        for epu_col in ["fred_eputrade", "fred_usepuindxm"]:
            if epu_col in data.columns and data[epu_col].notna().sum() > 30:
                epu_data = data.copy()
                epu_data["close"] = data[epu_col]
                prefix = epu_col.replace("fred_", "")
                epu_data = self.add_all_technical_indicators(epu_data, "close", prefix)
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
        _total_zscore, trade_share, trade_epu_zscore = self._compute_epu_decomposition(
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
                except (KeyError, IndexError):
                    pass
            if "hg_close" in data.columns:
                try:
                    if not pd.isna(data.loc[idx, "hg_close"]):
                        confidence += 0.1
                except (KeyError, IndexError):
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
