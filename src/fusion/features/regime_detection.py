"""
ZINC Fusion V15: Regime Detection & Dynamic Weighting
======================================================
Adaptive weight allocation based on market regime identification.

This module provides:
1. Multi-factor regime classification
2. Dynamic bucket weight allocation
3. Regime transition detection
4. Historical regime analysis
"""

import warnings
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


# =============================================================================
# REGIME DEFINITIONS
# =============================================================================


class MarketRegime(Enum):
    """Global market regime classification."""

    CRISIS = "crisis"  # High vol, negative growth
    STRESS = "stress"  # Elevated vol, uncertainty
    RISK_OFF = "risk_off"  # Defensive positioning
    NEUTRAL = "neutral"  # Normal conditions
    RISK_ON = "risk_on"  # Growth/risk seeking
    EUPHORIA = "euphoria"  # Low vol, strong growth


class CommodityRegime(Enum):
    """Commodity-specific regime."""

    CONTANGO_STEEP = "contango_steep"  # Strong carry negative
    CONTANGO_MILD = "contango_mild"  # Mild carry negative
    FLAT = "flat"  # Neutral term structure
    BACKWARDATION_MILD = "backwardation_mild"  # Mild carry positive
    BACKWARDATION_STEEP = "backwardation_steep"  # Strong carry positive


class SoyOilRegime(Enum):
    """Soybean oil specific regimes."""

    CRUSH_SQUEEZE = "crush_squeeze"  # Low crush margins
    NORMAL = "normal"  # Standard conditions
    OIL_PREMIUM = "oil_premium"  # Oil share elevated
    MEAL_PREMIUM = "meal_premium"  # Meal share elevated
    BIOFUEL_DRIVEN = "biofuel_driven"  # RIN/mandate driven
    DEMAND_SHOCK = "demand_shock"  # China/export driven


@dataclass
class RegimeState:
    """Current regime state with confidence."""

    market_regime: MarketRegime
    commodity_regime: CommodityRegime
    soy_oil_regime: SoyOilRegime
    confidence: float  # 0-1
    regime_age_days: int
    transition_probability: float


# =============================================================================
# BASE BUCKET WEIGHTS (Default allocation for Big-11)
# =============================================================================

BASE_WEIGHTS = {
    "crush": 0.32,  # 32% - Primary driver (soybean complex)
    "china": 0.19,  # 19% - Key demand (imports, copper proxy)
    "energy": 0.12,  # 12% - Petroleum complex (CL, HO, cracks)
    "palm": 0.10,  # 10% - Malaysia/Indonesia palm dynamics
    "biofuel": 0.08,  # 8%  - Mandates (RINs, LCFS, RFS)
    "substitutes": 0.05,  # 5%  - Non-palm competing oils (canola, sunflower)
    "tariff": 0.04,  # 4%  - Trade policy
    "fx": 0.04,  # 4%  - Export competitiveness
    "fed": 0.03,  # 3%  - Cost of carry
    "volatility": 0.03,  # 3%  - Risk premium
}


# =============================================================================
# REGIME-SPECIFIC WEIGHT ADJUSTMENTS (Big-11)
# =============================================================================

REGIME_WEIGHT_OVERRIDES = {
    # Market Regimes
    MarketRegime.CRISIS: {
        "crush": 0.18,
        "china": 0.10,
        "energy": 0.10,
        "palm": 0.08,
        "biofuel": 0.05,
        "substitutes": 0.05,
        "tariff": 0.05,
        "fx": 0.10,
        "fed": 0.10,
        "volatility": 0.14,  # Vol dominates in crisis
    },
    MarketRegime.STRESS: {
        "crush": 0.25,
        "china": 0.15,
        "energy": 0.10,
        "palm": 0.08,
        "biofuel": 0.06,
        "substitutes": 0.05,
        "tariff": 0.05,
        "fx": 0.08,
        "fed": 0.08,
        "volatility": 0.10,
    },
    MarketRegime.EUPHORIA: {
        "crush": 0.38,
        "china": 0.25,
        "energy": 0.10,
        "palm": 0.08,
        "biofuel": 0.07,
        "substitutes": 0.05,
        "tariff": 0.02,
        "fx": 0.02,
        "fed": 0.02,
        "volatility": 0.01,
    },
    # SoyOil Regimes
    SoyOilRegime.CRUSH_SQUEEZE: {
        "crush": 0.45,  # Crush margins dominate
        "china": 0.16,
        "energy": 0.08,
        "palm": 0.08,
        "biofuel": 0.06,
        "substitutes": 0.05,
        "tariff": 0.04,
        "fx": 0.04,
        "fed": 0.02,
        "volatility": 0.02,
    },
    SoyOilRegime.BIOFUEL_DRIVEN: {
        "crush": 0.20,
        "china": 0.10,
        "energy": 0.16,  # Energy coupling strengthens
        "palm": 0.10,
        "biofuel": 0.25,  # Biofuel mandates dominate
        "substitutes": 0.05,
        "tariff": 0.04,
        "fx": 0.04,
        "fed": 0.03,
        "volatility": 0.03,
    },
    SoyOilRegime.DEMAND_SHOCK: {
        "crush": 0.22,
        "china": 0.32,  # China dominates
        "energy": 0.08,
        "palm": 0.12,  # Palm substitution matters in China shock
        "biofuel": 0.05,
        "substitutes": 0.06,
        "tariff": 0.06,
        "fx": 0.05,
        "fed": 0.02,
        "volatility": 0.02,
    },
}


# =============================================================================
# REGIME DETECTOR
# =============================================================================


class RegimeDetector:
    """
    Multi-factor regime detection for ZINC Fusion.

    Uses:
    - VIX levels and momentum
    - Yield curve shape
    - Financial conditions index
    - Crush margin levels
    - Oil share levels
    - China demand signals
    """

    def __init__(self):
        self.regime_history = []

    def detect_market_regime(self, df: pd.DataFrame) -> MarketRegime:
        """
        Detect current market regime based on:
        - VIX level
        - VIX momentum
        - Yield curve
        - Financial conditions
        """
        latest = df.iloc[-1]

        # Default to neutral
        regime = MarketRegime.NEUTRAL

        # VIX-based classification
        vix = latest.get("vix", latest.get("vix_close", 20))
        vix_momentum = latest.get("vix_momentum_21d", 0)

        if vix >= 40:
            regime = MarketRegime.CRISIS
        elif vix >= 30:
            regime = MarketRegime.STRESS
        elif vix >= 25:
            regime = MarketRegime.RISK_OFF
        elif vix <= 12:
            regime = MarketRegime.EUPHORIA
        elif vix <= 15:
            regime = MarketRegime.RISK_ON

        # Override if VIX spiking
        if vix_momentum > 10 and vix > 20:
            regime = MarketRegime.STRESS

        return regime

    def detect_commodity_regime(
        self, df: pd.DataFrame, front_col: str = "close", back_col: str = "zl_back"
    ) -> CommodityRegime:
        """
        Detect commodity term structure regime.
        """
        latest = df.iloc[-1]

        if front_col not in df.columns or back_col not in df.columns:
            return CommodityRegime.FLAT

        front = latest[front_col]
        back = latest[back_col]

        if pd.isna(front) or pd.isna(back):
            return CommodityRegime.FLAT

        spread_pct = (back - front) / front * 100

        if spread_pct > 5:
            return CommodityRegime.CONTANGO_STEEP
        elif spread_pct > 1:
            return CommodityRegime.CONTANGO_MILD
        elif spread_pct < -5:
            return CommodityRegime.BACKWARDATION_STEEP
        elif spread_pct < -1:
            return CommodityRegime.BACKWARDATION_MILD
        else:
            return CommodityRegime.FLAT

    def detect_soyoil_regime(self, df: pd.DataFrame) -> SoyOilRegime:
        """
        Detect soybean oil specific regime.
        """
        latest = df.iloc[-1]

        # Crush margin based
        crush_zscore = latest.get("crush_zscore", 0)
        oil_share = latest.get("oil_share", 0.40)
        rin_d4 = latest.get("rin_d4", latest.get("rin_d4_price", 1.0))
        china_demand = latest.get("china_demand_index", 50)

        # Check for crush squeeze
        if crush_zscore < -1.5:
            return SoyOilRegime.CRUSH_SQUEEZE

        # Check for oil premium (biodiesel/RD demand)
        if oil_share > 0.45:
            return SoyOilRegime.OIL_PREMIUM

        # Check for meal premium
        if oil_share < 0.35:
            return SoyOilRegime.MEAL_PREMIUM

        # Check for biofuel driven
        if rin_d4 > 1.50:
            return SoyOilRegime.BIOFUEL_DRIVEN

        # Check for demand shock
        if china_demand > 80 or china_demand < 20:
            return SoyOilRegime.DEMAND_SHOCK

        return SoyOilRegime.NORMAL

    def get_current_regime(self, df: pd.DataFrame) -> RegimeState:
        """
        Get complete current regime state.
        """
        market_regime = self.detect_market_regime(df)
        commodity_regime = self.detect_commodity_regime(df)
        soyoil_regime = self.detect_soyoil_regime(df)

        # Calculate confidence based on signal clarity
        confidence = self._calculate_confidence(df, market_regime, soyoil_regime)

        # Calculate regime age
        regime_age = self._calculate_regime_age(market_regime)

        # Estimate transition probability
        transition_prob = self._estimate_transition_probability(regime_age, confidence)

        return RegimeState(
            market_regime=market_regime,
            commodity_regime=commodity_regime,
            soy_oil_regime=soyoil_regime,
            confidence=confidence,
            regime_age_days=regime_age,
            transition_probability=transition_prob,
        )

    def _calculate_confidence(
        self, df: pd.DataFrame, market_regime: MarketRegime, soyoil_regime: SoyOilRegime
    ) -> float:
        """Calculate confidence in regime classification."""
        latest = df.iloc[-1]

        confidence = 0.5  # Base confidence

        # Higher confidence if VIX clearly in regime
        vix = latest.get("vix", 20)
        if (market_regime == MarketRegime.CRISIS and vix > 45) or (
            market_regime == MarketRegime.EUPHORIA and vix < 12
        ):
            confidence += 0.2

        # Higher confidence if crush signals clear
        crush_zscore = latest.get("crush_zscore", 0)
        if abs(crush_zscore) > 2:
            confidence += 0.15

        return min(confidence, 1.0)

    def _calculate_regime_age(self, current_regime: MarketRegime) -> int:
        """Calculate how long we've been in current regime."""
        if not self.regime_history:
            return 1

        age = 1
        for past_regime in reversed(self.regime_history):
            if past_regime == current_regime:
                age += 1
            else:
                break
        return age

    def _estimate_transition_probability(self, age: int, confidence: float) -> float:
        """
        Estimate probability of regime transition.

        Regimes tend to persist but likelihood of transition increases with age.
        """
        # Base transition probability increases with age
        base_prob = min(0.05 * np.sqrt(age), 0.50)

        # Lower confidence = higher transition probability
        confidence_adj = (1 - confidence) * 0.2

        return min(base_prob + confidence_adj, 0.80)


# =============================================================================
# DYNAMIC WEIGHT ALLOCATOR
# =============================================================================


class DynamicWeightAllocator:
    """
    Allocates specialist bucket weights based on:
    1. Current regime
    2. Bucket performance (rolling accuracy)
    3. Feature importance signals
    4. Market conditions
    """

    def __init__(self, regime_detector: RegimeDetector | None = None):
        self.regime_detector = regime_detector or RegimeDetector()
        self.weight_history = []
        self.performance_tracker = {}

    def get_base_weights(self) -> dict[str, float]:
        """Return base (default) weights."""
        return BASE_WEIGHTS.copy()

    def get_regime_weights(self, regime_state: RegimeState) -> dict[str, float]:
        """
        Get weights adjusted for current regime.
        """
        # Start with base weights
        weights = BASE_WEIGHTS.copy()

        # Apply market regime override if available
        if regime_state.market_regime in REGIME_WEIGHT_OVERRIDES:
            regime_weights = REGIME_WEIGHT_OVERRIDES[regime_state.market_regime]
            # Blend based on confidence
            for bucket, weight in regime_weights.items():
                weights[bucket] = (
                    regime_state.confidence * weight
                    + (1 - regime_state.confidence) * weights[bucket]
                )

        # Apply soy oil regime override if more relevant
        if regime_state.soy_oil_regime in REGIME_WEIGHT_OVERRIDES:
            soyoil_weights = REGIME_WEIGHT_OVERRIDES[regime_state.soy_oil_regime]
            # Use stronger signal
            for bucket, weight in soyoil_weights.items():
                soyoil_adj = (
                    regime_state.confidence * weight
                    + (1 - regime_state.confidence) * weights[bucket]
                )
                # Take average of market and soyoil adjustments
                weights[bucket] = (weights[bucket] + soyoil_adj) / 2

        # Normalize to sum to 1
        total = sum(weights.values())
        weights = {k: v / total for k, v in weights.items()}

        return weights

    def get_performance_adjusted_weights(
        self, regime_weights: dict[str, float], bucket_performance: dict[str, float]
    ) -> dict[str, float]:
        """
        Adjust weights based on recent bucket performance.

        bucket_performance: Dict of bucket_name -> rolling accuracy (0-1)
        """
        weights = regime_weights.copy()

        if not bucket_performance:
            return weights

        # Calculate performance adjustment factor
        avg_perf = np.mean(list(bucket_performance.values()))

        for bucket, perf in bucket_performance.items():
            if bucket in weights:
                # Increase weight for outperforming buckets
                # Decrease for underperforming
                perf_ratio = (perf / avg_perf) if avg_perf > 0 else 1.0

                # Limit adjustment to ±30%
                adj_factor = np.clip(perf_ratio, 0.7, 1.3)
                weights[bucket] *= adj_factor

        # Re-normalize
        total = sum(weights.values())
        weights = {k: v / total for k, v in weights.items()}

        return weights

    def get_dynamic_weights(
        self, df: pd.DataFrame, bucket_performance: dict[str, float] | None = None
    ) -> dict[str, float]:
        """
        Get fully dynamic weights based on all factors.
        """
        # Detect current regime
        regime_state = self.regime_detector.get_current_regime(df)

        # Get regime-adjusted weights
        weights = self.get_regime_weights(regime_state)

        # Apply performance adjustment if available
        if bucket_performance:
            weights = self.get_performance_adjusted_weights(weights, bucket_performance)

        # Store for history
        self.weight_history.append(
            {
                "timestamp": pd.Timestamp.now(),
                "regime": regime_state.market_regime.value,
                "weights": weights.copy(),
            }
        )

        return weights


# =============================================================================
# REGIME FEATURES FOR ML
# =============================================================================


class RegimeFeatureGenerator:
    """
    Generate regime-based features for ML models.
    """

    def __init__(self, detector: RegimeDetector):
        self.detector = detector

    def generate_regime_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate regime-related features."""
        result = df.copy()

        # Rolling regime detection
        regimes = []
        for i in range(len(df)):
            window = df.iloc[max(0, i - 60) : i + 1]  # 60-day lookback
            if len(window) > 10:
                regime = self.detector.detect_market_regime(window)
                regimes.append(regime.value)
            else:
                regimes.append("neutral")

        result["market_regime"] = regimes

        # One-hot encode regimes
        for regime in MarketRegime:
            result[f"regime_{regime.value}"] = (
                result["market_regime"] == regime.value
            ).astype(int)

        # Regime duration
        result["regime_duration"] = (
            result.groupby(
                (result["market_regime"] != result["market_regime"].shift()).cumsum()
            ).cumcount()
            + 1
        )

        # Regime transition features
        result["regime_change"] = (
            result["market_regime"] != result["market_regime"].shift()
        ).astype(int)
        result["days_since_regime_change"] = (
            result["regime_change"].groupby(result["regime_change"].cumsum()).cumcount()
        )

        return result


# =============================================================================
# MAIN - Example usage
# =============================================================================

if __name__ == "__main__":
    print("🎯 ZINC Fusion V15 Regime Detection & Dynamic Weighting")
    print("=" * 60)

    # Show base weights
    print("\n📊 Base Bucket Weights:")
    for bucket, weight in sorted(BASE_WEIGHTS.items(), key=lambda x: -x[1]):
        print(f"   {bucket:12s}: {weight * 100:5.1f}%")

    # Show regime overrides
    print("\n📈 Regime-Specific Weight Overrides:")
    for regime, weights in REGIME_WEIGHT_OVERRIDES.items():
        print(f"\n   {regime}:")
        for bucket, weight in sorted(weights.items(), key=lambda x: -x[1])[:3]:
            print(f"      {bucket:12s}: {weight * 100:5.1f}%")
