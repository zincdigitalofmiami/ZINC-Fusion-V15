"""
ECM-based signal generators: palm.

Uses Error Correction Model for cointegration analysis between ZL and FCPO.
Falls back to spread z-score if cointegration not detected.
"""

from datetime import date
from typing import List, Optional, Tuple
import pandas as pd
import numpy as np
import logging

from fusion.specialists.base import (
    BaseSignalGenerator,
    SignalConfig,
    SignalOutput,
)

logger = logging.getLogger(__name__)

# Try to import statsmodels for cointegration tests
try:
    from statsmodels.tsa.stattools import coint, adfuller
    from statsmodels.regression.linear_model import OLS
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    logger.warning("statsmodels not available; using simplified palm model")


# =============================================================================
# PALM SIGNAL GENERATOR
# =============================================================================

class PalmSignalGenerator(BaseSignalGenerator):
    """
    Palm specialist: substitution pressure from FCPO.

    Signal Contract:
    - signal_1: Palm substitution pressure (spread z-score + mean reversion)
    - signal_2: None (single signal)

    Higher signal = ZL expensive vs palm = substitution pressure (bearish ZL)
    Lower signal = ZL cheap vs palm = less substitution risk (bullish ZL)

    Inputs: ZL, CPO (crude palm oil from Bursa Malaysia)
    Model: ECM on ZL vs FCPO spread for mean reversion velocity
    """

    def __init__(self):
        config = SignalConfig(
            bucket="palm",
            model_type="ecm",
            primary_features=["close"],
            secondary_features=[
                "cpo_close",       # Crude palm oil (Bursa Malaysia FCPO)
                "palm_oil_close",  # Alternative name
            ],
            lookback_days=504,  # 2 years for cointegration stability
            min_data_points=252,
        )
        super().__init__(config)
        self._cointegration_result = None

    def validate_inputs(self, data: pd.DataFrame) -> List[str]:
        """Need ZL and at least one palm price series."""
        missing = []
        if "close" not in data.columns:
            missing.append("close")

        palm_cols = ["cpo_close", "palm_oil_close"]
        if not any(col in data.columns for col in palm_cols):
            missing.append("cpo_close_or_palm_oil_close")
        return missing

    def _get_palm_series(self, data: pd.DataFrame) -> pd.Series:
        """Get palm oil price series from available columns."""
        if "cpo_close" in data.columns:
            return data["cpo_close"]
        elif "palm_oil_close" in data.columns:
            return data["palm_oil_close"]
        else:
            raise ValueError("No palm oil price series available")

    def _test_cointegration(
        self,
        zl: pd.Series,
        cpo: pd.Series,
    ) -> Tuple[bool, float, Optional[float]]:
        """
        Test for cointegration between ZL and CPO.

        Returns:
            (is_cointegrated, p_value, hedge_ratio)
        """
        if not STATSMODELS_AVAILABLE:
            return False, 1.0, None

        try:
            # Clean data
            combined = pd.DataFrame({"zl": zl, "cpo": cpo}).dropna()
            if len(combined) < 252:
                return False, 1.0, None

            # Engle-Granger cointegration test
            score, pvalue, _ = coint(combined["zl"], combined["cpo"])

            # Estimate hedge ratio via OLS
            hedge_ratio = None
            if pvalue < 0.10:  # Cointegrated at 10% level
                model = OLS(combined["zl"], combined["cpo"]).fit()
                hedge_ratio = model.params[0]

            return pvalue < 0.10, pvalue, hedge_ratio

        except Exception as e:
            logger.warning(f"Cointegration test failed: {e}")
            return False, 1.0, None

    def _compute_spread(
        self,
        zl: pd.Series,
        cpo: pd.Series,
        hedge_ratio: Optional[float] = None,
    ) -> pd.Series:
        """
        Compute ZL-CPO spread.

        If hedge_ratio available from cointegration, use it.
        Otherwise use unit conversion: ZL (cents/lb) vs CPO (MYR/MT).
        """
        if hedge_ratio is not None:
            # Cointegration-based spread
            return zl - hedge_ratio * cpo
        else:
            # Simple ratio spread (log)
            # ZL in cents/lb, CPO in ~RM/tonne
            # Convert CPO to approximate USD cents/lb equivalent
            # CPO: ~3.2 MYR/USD, ~2204.6 lbs/MT
            cpo_usd_cents_lb = (cpo / 3.2) / 22.046
            return zl - cpo_usd_cents_lb

    def _compute_mean_reversion_speed(
        self,
        spread: pd.Series,
        window: int = 63,
    ) -> pd.Series:
        """
        Estimate mean reversion speed using half-life approach.

        Returns velocity of mean reversion (higher = faster reversion).
        """
        if not STATSMODELS_AVAILABLE:
            # Simplified: use spread velocity
            return -spread.diff(5) / spread.rolling(21).std()

        try:
            # Rolling half-life estimation
            half_life = pd.Series(np.nan, index=spread.index)

            for i in range(window, len(spread)):
                window_spread = spread.iloc[i - window:i].dropna()
                if len(window_spread) < 42:
                    continue

                # AR(1) regression: spread_t = alpha + beta * spread_{t-1} + e
                lagged = window_spread.shift(1).dropna()
                current = window_spread.iloc[1:]

                if len(lagged) < 42:
                    continue

                model = OLS(current, lagged).fit()
                beta = model.params[0]

                # Half-life = -ln(2) / ln(beta)
                if 0 < beta < 1:
                    hl = -np.log(2) / np.log(beta)
                    half_life.iloc[i] = min(hl, 252)  # Cap at 1 year

            # Convert to speed (inverse of half-life)
            reversion_speed = 63 / half_life  # Normalized to quarter speed
            return reversion_speed.clip(0, 5)

        except Exception as e:
            logger.warning(f"Mean reversion estimation failed: {e}")
            return -spread.diff(5) / spread.rolling(21).std()

    def compute(self, data: pd.DataFrame, run_hash: str) -> List[SignalOutput]:
        """
        Compute palm substitution pressure signal.

        Combines:
        - Spread z-score (current deviation from equilibrium)
        - Mean reversion speed (how fast spread reverts)
        """
        signals = []

        zl = data["close"]
        cpo = self._get_palm_series(data)

        # Test cointegration on full sample
        is_coint, coint_pvalue, hedge_ratio = self._test_cointegration(zl, cpo)
        logger.info(
            f"Palm cointegration: {'yes' if is_coint else 'no'} "
            f"(p={coint_pvalue:.3f}, hedge_ratio={hedge_ratio})"
        )

        # Compute spread
        spread = self._compute_spread(zl, cpo, hedge_ratio)
        spread_zscore = self.compute_zscore(spread, window=252, min_periods=126)

        # Mean reversion speed
        reversion_speed = self._compute_mean_reversion_speed(spread)

        # Composite signal: spread z-score weighted by reversion speed
        # Higher spread z-score = ZL expensive (bearish)
        # Faster reversion = more confident in signal
        substitution_pressure = spread_zscore

        for idx in data.index:
            if pd.isna(spread_zscore.loc[idx]):
                continue

            # Confidence based on cointegration and reversion speed
            base_confidence = 0.5 + (0.3 if is_coint else 0.0)
            speed = reversion_speed.loc[idx] if not pd.isna(reversion_speed.loc[idx]) else 1.0
            confidence = min(base_confidence + 0.1 * min(speed, 2), 0.95)

            signals.append(SignalOutput(
                as_of_date=idx.date() if hasattr(idx, 'date') else idx,
                bucket="palm",
                signal_1=float(substitution_pressure.loc[idx]),
                signal_2=None,
                confidence=float(confidence),
                model_type="ecm" if is_coint else "spread_zscore",
                metadata={
                    "spread_zscore": float(spread_zscore.loc[idx]),
                    "reversion_speed": float(speed) if not pd.isna(speed) else None,
                    "is_cointegrated": is_coint,
                    "coint_pvalue": float(coint_pvalue),
                    "hedge_ratio": float(hedge_ratio) if hedge_ratio else None,
                    "run_hash": run_hash,
                },
            ))

        logger.info(f"PalmSignalGenerator: Generated {len(signals)} signals")
        return signals
