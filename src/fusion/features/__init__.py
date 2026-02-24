"""
Fusion - Feature Engineering Module
===================================

This module provides comprehensive feature engineering for the Fusion
soybean oil forecasting system.

Components:
-----------
1. technical_indicators: 130+ technical indicators using ta, TA-Lib, pandas-ta
2. specialist_buckets: Big-11 bucket-specific indicators (Crush, China, Energy, Biofuel, Substitutes, Trump Effect, etc.)
3. regime_detection: Market regime classification and dynamic weighting

Usage:
------
    from fusion.features import (
        FusionIndicators,
        FusionBucketIndicators,
        RegimeDetector,
        DynamicWeightAllocator
    )

    # Compute technical indicators
    ti = ZincFusionIndicators(df)
    df_with_ta = ti.compute_all()

    # Compute specialist bucket indicators
    bi = ZincFusionBucketIndicators(df)
    df_with_buckets = bi.compute_all_buckets()

    # Get dynamic weights based on regime
    detector = RegimeDetector()
    allocator = DynamicWeightAllocator(detector)
    weights = allocator.get_dynamic_weights(df)
"""

# Technical Indicators (130+ indicators)
from .technical_indicators import ZincFusionIndicators

# Specialist Bucket Indicators (Big-9)
from .specialist_buckets import (
    # Bucket configurations
    BUCKET_CONFIGS,
    BucketConfig,
    # Individual bucket calculators
    CrushBucketIndicators,
    ChinaBucketIndicators,
    EnergyBucketIndicators,
    BiofuelBucketIndicators,
    SubstitutesBucketIndicators,
    FXBucketIndicators,
    FedBucketIndicators,
    VolatilityBucketIndicators,
    TariffBucketIndicators,
    # Master bucket calculator
    ZincFusionBucketIndicators,
)

# Regime Detection & Dynamic Weighting
from .regime_detection import (
    # Regime enums
    MarketRegime,
    CommodityRegime,
    SoybeanOilRegime,
    RegimeState,
    # Base weights
    BASE_WEIGHTS,
    REGIME_WEIGHT_OVERRIDES,
    # Detectors and allocators
    RegimeDetector,
    DynamicWeightAllocator,
    RegimeFeatureGenerator,
)

__all__ = [
    # Technical Indicators
    "ZincFusionIndicators",
    # Bucket configs
    "BUCKET_CONFIGS",
    "BucketConfig",
    # Bucket calculators (Big-9)
    "CrushBucketIndicators",
    "ChinaBucketIndicators",
    "EnergyBucketIndicators",
    "BiofuelBucketIndicators",
    "SubstitutesBucketIndicators",
    "FXBucketIndicators",
    "FedBucketIndicators",
    "VolatilityBucketIndicators",
    "TariffBucketIndicators",
    "ZincFusionBucketIndicators",
    # Regime detection
    "MarketRegime",
    "CommodityRegime",
    "SoybeanOilRegime",
    "RegimeState",
    "BASE_WEIGHTS",
    "REGIME_WEIGHT_OVERRIDES",
    "RegimeDetector",
    "DynamicWeightAllocator",
    "RegimeFeatureGenerator",
    # Convenience
    "compute_all_features",
]


def compute_all_features(
    df, include_ta=True, include_buckets=True, include_regime=True, **kwargs
):
    """
    Convenience function to compute all features in one call.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe with OHLCV data
    include_ta : bool
        Include technical indicators
    include_buckets : bool
        Include specialist bucket indicators
    include_regime : bool
        Include regime features
    **kwargs
        Additional arguments passed to bucket indicators

    Returns
    -------
    pd.DataFrame
        DataFrame with all computed features
    """
    result = df.copy()

    if include_ta:
        ti = ZincFusionIndicators(result)
        result = ti.compute_all()

    if include_buckets:
        bi = ZincFusionBucketIndicators(result)
        result = bi.compute_all_buckets(**kwargs)

    if include_regime:
        detector = RegimeDetector()
        fg = RegimeFeatureGenerator(detector)
        result = fg.generate_regime_features(result)

    return result
