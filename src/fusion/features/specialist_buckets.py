"""
ZINC Fusion V15: Big-11 Specialist Bucket Indicators
=====================================================
Domain-specific indicators for each of the 11 specialist buckets.

Each bucket has custom indicators and regime detection tailored to its specific market drivers.

⚠️ CRITICAL: Specialist weights are LEARNED by the L1 meta-ensemble from market data.
   NEVER hardcode weight percentages - the market determines importance, not humans.

Buckets:
1. CRUSH - Soybean complex fundamentals
2. CHINA - Chinese import demand
3. ENERGY - Petroleum complex (CL, HO, cracks)
4. PALM - Palm oil complex (Malaysia/Indonesia)
5. BIOFUEL - Renewable mandates (RINs, LCFS, RFS)
6. SUBSTITUTES - Other competing oils (canola, sunflower, rapeseed)
7. TARIFF - Trade policy impacts
8. FX - Currency effects
9. FED - Monetary policy
10. VOLATILITY - Financial stress/fear
11. TRUMP_EFFECT - Policy regime dynamics, trade war, EPA waivers
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
import warnings

warnings.filterwarnings("ignore")


@dataclass
class BucketConfig:
    """Configuration for a specialist bucket.

    NOTE: No weight_range field - weights are learned by L1 meta-ensemble.
    """

    name: str
    primary_features: List[str]
    secondary_features: List[str]
    regime_thresholds: Dict[str, float]


# =============================================================================
# BUCKET CONFIGURATIONS
# =============================================================================

BUCKET_CONFIGS = {
    "crush": BucketConfig(
        name="Crush",
        primary_features=[
            "board_crush",
            "oil_share",
            "zl_zs_ratio",
            "zm_zs_ratio",
            "crush_margin",
            "nopa_crush_utilization",
            "cftc_zl_net_position",
        ],
        secondary_features=[
            "canola_spread",
            "sunflower_spread",
            "rapeseed_spread",
            "argentina_crush",
            "brazil_crush",
            "crush_momentum_21d",
        ],
        regime_thresholds={
            "crush_squeeze": 50,  # Board crush below this = margin squeeze
            "oil_share_high": 0.45,  # Oil share above this = ZL outperforming
            "oil_share_low": 0.38,  # Oil share below this = ZM outperforming
        },
    ),
    "china": BucketConfig(
        name="China",
        primary_features=[
            "china_soy_imports",
            "dalian_soy_close",
            "hg_close",
            "shanghai_copper",
            "usda_export_sales_china",
            "china_crushing_margin",
        ],
        secondary_features=[
            "china_pmi",
            "china_gdp_proxy",
            "pork_hog_ratio",
            "china_inventory",
            "brazil_premium",
            "usd_cny",
        ],
        regime_thresholds={
            "strong_demand": 0.7,  # China demand index above this
            "weak_demand": 0.3,  # China demand index below this
            "trade_war": 0.5,  # Trade tension above this
        },
    ),
    "energy": BucketConfig(
        name="Energy",
        primary_features=[
            "cl_close",
            "ho_close",
            "rb_close",
            "ng_close",
            "crack_spread_321",
            "boho_spread",
        ],
        secondary_features=[
            "brent_wti_spread",
            "gasoline_crack",
            "diesel_crack",
            "energy_inventory",
            "refinery_utilization",
            "opec_spare_capacity",
        ],
        regime_thresholds={
            "high_energy": 80,  # WTI above this = bullish energy
            "low_energy": 50,  # WTI below this = bearish energy
            "tight_crack": 25,  # Crack spread above this = strong refining
        },
    ),
    "palm": BucketConfig(
        name="Palm",
        primary_features=[
            "palm_oil_close",
            "palm_oil_front",
            "zl_palm_spread",
            "zl_palm_ratio",
            "palm_production_malaysia",
            "palm_inventory_malaysia",
        ],
        secondary_features=[
            "palm_export_levy_indonesia",
            "palm_export_levy_malaysia",
            "indonesia_export_policy",
            "palm_biodiesel_mandate",
            "el_nino_index",
            "la_nina_index",
        ],
        regime_thresholds={
            "palm_premium": 1.05,  # ZL/Palm ratio below this = palm premium
            "palm_discount": 1.15,  # ZL/Palm ratio above this = palm discount
            "low_inventory": 1.5,  # Malaysia inventory below 1.5M tonnes
            "high_inventory": 2.5,  # Malaysia inventory above 2.5M tonnes
        },
    ),
    "biofuel": BucketConfig(
        name="Biofuel",
        primary_features=[
            "rin_d4_price",
            "rin_d6_price",
            "lcfs_credit",
            "rfs_mandate_level",
            "biodiesel_production",
            "renewable_diesel_capacity",
        ],
        secondary_features=[
            "sbo_biodiesel_pct",
            "epa_waivers",
            "saf_demand",
            "carbon_credit_price",
            "blender_tax_credit",
            "e15_waiver_status",
        ],
        regime_thresholds={
            "rin_bullish": 1.50,  # D4 RIN above this = strong mandate
            "rin_bearish": 0.80,  # D4 RIN below this = weak mandate
            "lcfs_bullish": 150,  # LCFS above this = strong CA signal
        },
    ),
    "substitutes": BucketConfig(
        name="Substitutes",
        primary_features=[
            "canola_close",
            "sunflower_close",
            "rapeseed_close",
            "cottonseed_oil_close",
            "zl_canola_spread",
            "zl_sunflower_spread",
        ],
        secondary_features=[
            "eu_rapeseed_production",
            "black_sea_sunflower",
            "canola_crush_canada",
            "argentina_sunflower_crop",
            "india_import_policy",
            "eu_biofuel_feedstock",
        ],
        regime_thresholds={
            "canola_tight": 0.05,  # Canola spread tight
            "sunflower_shortage": -0.10,  # Sunflower at premium
            "rapeseed_surplus": 0.15,  # Rapeseed at deep discount
        },
    ),
    "tariff": BucketConfig(
        name="Tariff",
        primary_features=[
            "effective_tariff_rate",
            "trade_war_sentiment",
            "policy_uncertainty_index",
            "china_tariff_rate",
            "retaliatory_tariff_risk",
        ],
        secondary_features=[
            "trade_negotiation_score",
            "diplomatic_sentiment",
            "news_volume",
            "trump_trade_tweets",
            "section_301_risk",
            "wto_dispute_count",
        ],
        regime_thresholds={
            "escalation": 0.7,  # Trade war sentiment above this
            "detente": 0.3,  # Trade war sentiment below this
            "high_uncertainty": 150,  # Policy uncertainty index above this
        },
    ),
    "fx": BucketConfig(
        name="FX",
        primary_features=[
            "dxy",
            "usd_brl",
            "usd_cny",
            "usd_ars",
            "fx_volatility",
            "em_currency_index",
        ],
        secondary_features=[
            "eur_usd",
            "real_effective_rate",
            "carry_trade_index",
            "fx_intervention_risk",
            "current_account_balance",
            "terms_of_trade",
        ],
        regime_thresholds={
            "strong_dollar": 105,  # DXY above this
            "weak_dollar": 95,  # DXY below this
            "brl_stress": 5.5,  # USD/BRL above this = Brazil stress
            "cny_devalue": 7.3,  # USD/CNY above this = China devalue risk
        },
    ),
    "fed": BucketConfig(
        name="Fed",
        primary_features=[
            "fed_funds_rate",
            "fed_funds_target",
            "t10y2y",
            "real_rates",
            "nfci",
            "financial_conditions_index",
        ],
        secondary_features=[
            "fed_balance_sheet",
            "qe_pace",
            "fomc_dots",
            "market_fed_expectations",
            "inflation_breakevens",
            "tips_spreads",
            "credit_spreads",
        ],
        regime_thresholds={
            "hawkish": 0,  # Yield curve above this = not inverted
            "dovish": -0.5,  # Yield curve below this = inverted/easing
            "tight_financial": 0.5,  # NFCI above this = tight conditions
            "loose_financial": -0.5,  # NFCI below this = loose conditions
        },
    ),
    "volatility": BucketConfig(
        name="Volatility",
        primary_features=[
            "vix",
            "ovx",
            "soybean_iv",
            "realized_vol_20d",
            "vol_risk_premium",
            "term_structure_slope",
        ],
        secondary_features=[
            "skew_index",
            "put_call_ratio",
            "vvix",
            "correlation_index",
            "stress_index",
            "liquidity_index",
            "tail_risk_measure",
        ],
        regime_thresholds={
            "low_vol": 15,  # VIX below this = complacent
            "normal_vol": 20,  # VIX around this = normal
            "high_vol": 30,  # VIX above this = fear
            "crisis_vol": 40,  # VIX above this = crisis
        },
    ),
}


# =============================================================================
# CRUSH BUCKET INDICATORS
# =============================================================================


class CrushBucketIndicators:
    """
    CRUSH Bucket: Soybean complex fundamentals

    Key Drivers:
    - Board crush margin (processing economics)
    - Oil share (ZL vs ZM value split)
    - NOPA crush utilization (US processing capacity)
    - Global crush capacity (Argentina, Brazil)
    - CFTC positioning (speculative flows)
    """

    @staticmethod
    def compute_board_crush(zl: pd.Series, zs: pd.Series, zm: pd.Series) -> pd.Series:
        """
        Board Crush per CME formula ($/bushel):
        = (meal × 0.022) + (oil × 11) − soybeans

        Where:
        - ZL is in ¢/lb, multiply by 0.11 (11 lbs oil per bushel / 100 ¢ per $)
        - ZM is in $/short ton, multiply by 0.022 (44 lbs meal / 2000 lbs per ton)
        - ZS is in ¢/bu, divide by 100 to get $/bu

        Reference: CME Soybean Crush Reference Guide
        Hedge ratio: 10 Soybeans : 11 Meal : 9 Oil
        """
        oil_value = zl * 0.11       # 11 lbs oil per bushel, ZL in ¢/lb
        meal_value = zm * 0.022     # 44 lbs meal / 2000 lbs per ton
        return (oil_value + meal_value) - (zs / 100)

    @staticmethod
    def compute_oil_share(zl: pd.Series, zm: pd.Series) -> pd.Series:
        """
        Oil share = oil_value / (oil_value + meal_value)
        Shows relative value of oil vs meal in crush.

        Uses CME conversion factors for consistency with board_crush:
        - oil_value = ZL × 0.11 (11 lbs oil per bushel, ZL in ¢/lb)
        - meal_value = ZM × 0.022 (44 lbs meal / 2000 lbs per ton)
        """
        oil_value = zl * 0.11       # 11 lbs oil per bushel, ZL in ¢/lb
        meal_value = zm * 0.022     # 44 lbs meal / 2000 lbs per ton
        return oil_value / (oil_value + meal_value)

    @staticmethod
    def compute_crush_indicators(
        df: pd.DataFrame,
        zs_col: str = "zs_close",
        zm_col: str = "zm_close",
        zl_col: str = "close",
    ) -> pd.DataFrame:
        """Compute all crush bucket indicators with dashboard-ready features."""
        result = df.copy()

        if all(col in df.columns for col in [zl_col, zs_col, zm_col]):
            # Core crush calculations
            result["board_crush"] = CrushBucketIndicators.compute_board_crush(
                df[zl_col], df[zs_col], df[zm_col]
            )
            result["oil_share"] = CrushBucketIndicators.compute_oil_share(
                df[zl_col], df[zm_col]
            )

            # Ratios
            result["zl_zs_ratio"] = df[zl_col] / df[zs_col]
            result["zm_zs_ratio"] = df[zm_col] / df[zs_col]
            result["zl_zm_ratio"] = df[zl_col] / df[zm_col]

            # Momentum
            for period in [5, 10, 21, 63]:
                result[f"crush_momentum_{period}d"] = (
                    result["board_crush"].pct_change(period) * 100
                )
                result[f"oil_share_change_{period}d"] = result["oil_share"].diff(period)

            # Z-scores
            result["crush_zscore"] = (
                result["board_crush"] - result["board_crush"].rolling(252).mean()
            ) / result["board_crush"].rolling(252).std()
            result["oil_share_zscore"] = (
                result["oil_share"] - result["oil_share"].rolling(252).mean()
            ) / result["oil_share"].rolling(252).std()

            # ============ DASHBOARD: BOLLINGER BANDS ============
            # Crush margin bands (20-day, 2 std)
            crush_sma20 = result["board_crush"].rolling(20).mean()
            crush_std20 = result["board_crush"].rolling(20).std()
            result["crush_bb_upper"] = crush_sma20 + (2 * crush_std20)
            result["crush_bb_middle"] = crush_sma20
            result["crush_bb_lower"] = crush_sma20 - (2 * crush_std20)
            result["crush_bb_width"] = (
                (result["crush_bb_upper"] - result["crush_bb_lower"]) / crush_sma20
            ) * 100
            result["crush_bb_pct"] = (
                result["board_crush"] - result["crush_bb_lower"]
            ) / (result["crush_bb_upper"] - result["crush_bb_lower"])

            # Oil share bands
            os_sma20 = result["oil_share"].rolling(20).mean()
            os_std20 = result["oil_share"].rolling(20).std()
            result["oil_share_bb_upper"] = os_sma20 + (2 * os_std20)
            result["oil_share_bb_middle"] = os_sma20
            result["oil_share_bb_lower"] = os_sma20 - (2 * os_std20)
            result["oil_share_bb_pct"] = (
                result["oil_share"] - result["oil_share_bb_lower"]
            ) / (result["oil_share_bb_upper"] - result["oil_share_bb_lower"])

            # ============ DASHBOARD: PERCENTILE BANDS ============
            result["crush_pct_90"] = result["board_crush"].rolling(252).quantile(0.90)
            result["crush_pct_75"] = result["board_crush"].rolling(252).quantile(0.75)
            result["crush_pct_50"] = result["board_crush"].rolling(252).quantile(0.50)
            result["crush_pct_25"] = result["board_crush"].rolling(252).quantile(0.25)
            result["crush_pct_10"] = result["board_crush"].rolling(252).quantile(0.10)

            result["oil_share_pct_90"] = result["oil_share"].rolling(252).quantile(0.90)
            result["oil_share_pct_75"] = result["oil_share"].rolling(252).quantile(0.75)
            result["oil_share_pct_50"] = result["oil_share"].rolling(252).quantile(0.50)
            result["oil_share_pct_25"] = result["oil_share"].rolling(252).quantile(0.25)
            result["oil_share_pct_10"] = result["oil_share"].rolling(252).quantile(0.10)

            # ============ DASHBOARD: PROBABILITY/SIGNAL STRENGTH ============
            # Regime probability (based on zscore)
            result["crush_squeeze_prob"] = 1 / (
                1 + np.exp(result["crush_zscore"] + 1)
            )  # High when zscore < -1
            result["crush_wide_prob"] = 1 / (
                1 + np.exp(-result["crush_zscore"] + 1)
            )  # High when zscore > 1

            # Signal strength (0-100 scale)
            result["crush_signal_strength"] = (
                np.abs(result["crush_zscore"]).clip(0, 3) / 3 * 100
            )
            result["oil_share_signal_strength"] = (
                np.abs(result["oil_share_zscore"]).clip(0, 3) / 3 * 100
            )

            # Combined crush bucket signal
            result["crush_bucket_signal"] = (
                result["crush_zscore"] * 0.5 + result["oil_share_zscore"] * 0.5
            )
            result["crush_bucket_confidence"] = (
                100
                - np.abs(result["crush_zscore"] - result["oil_share_zscore"]).clip(0, 2)
                * 25
            )

            # ============ DASHBOARD: MOVING AVERAGES (OVERLAYS) ============
            result["crush_sma_10"] = result["board_crush"].rolling(10).mean()
            result["crush_sma_21"] = result["board_crush"].rolling(21).mean()
            result["crush_sma_63"] = result["board_crush"].rolling(63).mean()
            result["crush_ema_10"] = result["board_crush"].ewm(span=10).mean()
            result["crush_ema_21"] = result["board_crush"].ewm(span=21).mean()

            result["oil_share_sma_10"] = result["oil_share"].rolling(10).mean()
            result["oil_share_sma_21"] = result["oil_share"].rolling(21).mean()
            result["oil_share_sma_63"] = result["oil_share"].rolling(63).mean()

            # ============ DASHBOARD: EFFECTS/DIVERGENCE ============
            # Crush vs Oil Share divergence
            result["crush_oil_divergence"] = (
                result["crush_zscore"] - result["oil_share_zscore"]
            )
            result["crush_oil_corr_21d"] = (
                result["board_crush"].rolling(21).corr(result["oil_share"])
            )
            result["crush_oil_corr_63d"] = (
                result["board_crush"].rolling(63).corr(result["oil_share"])
            )

            # Rate of change (for overlays)
            result["crush_roc_5d"] = (
                result["board_crush"] / result["board_crush"].shift(5) - 1
            ) * 100
            result["crush_roc_21d"] = (
                result["board_crush"] / result["board_crush"].shift(21) - 1
            ) * 100
            result["oil_share_roc_21d"] = (
                result["oil_share"] / result["oil_share"].shift(21) - 1
            ) * 100

            # Regime detection
            result["crush_regime"] = pd.cut(
                result["crush_zscore"],
                bins=[-np.inf, -1, 0, 1, np.inf],
                labels=["squeeze", "tight", "normal", "wide"],
            )

            # Percentile ranks
            result["crush_percentile"] = (
                result["board_crush"].rolling(252).rank(pct=True) * 100
            )
            result["oil_share_percentile"] = (
                result["oil_share"].rolling(252).rank(pct=True) * 100
            )

            # ============ DASHBOARD: SUPPORT/RESISTANCE ============
            result["crush_52w_high"] = result["board_crush"].rolling(252).max()
            result["crush_52w_low"] = result["board_crush"].rolling(252).min()
            result["crush_range_position"] = (
                (result["board_crush"] - result["crush_52w_low"])
                / (result["crush_52w_high"] - result["crush_52w_low"])
                * 100
            )

        return result


# =============================================================================
# CHINA BUCKET INDICATORS
# =============================================================================


class ChinaBucketIndicators:
    """
    CHINA Bucket: Chinese import demand proxy

    Key Drivers:
    - China soybean imports (60%+ of global trade)
    - Copper as demand proxy (Dr. Copper)
    - Dalian soybean prices
    - USDA export sales to China
    - Pork/hog cycle (soybean meal demand)
    """

    @staticmethod
    def compute_china_demand_index(
        imports: pd.Series, copper: pd.Series, pork_ratio: pd.Series
    ) -> pd.Series:
        """
        Composite China demand index (0-100 scale).
        Combines import momentum, copper signal, and protein demand.
        """
        # Normalize each component to 0-1
        imports_norm = (imports - imports.rolling(252).min()) / (
            imports.rolling(252).max() - imports.rolling(252).min()
        )
        copper_norm = (copper - copper.rolling(252).min()) / (
            copper.rolling(252).max() - copper.rolling(252).min()
        )
        pork_norm = (pork_ratio - pork_ratio.rolling(252).min()) / (
            pork_ratio.rolling(252).max() - pork_ratio.rolling(252).min()
        )

        # Weighted composite
        return (imports_norm * 0.50 + copper_norm * 0.30 + pork_norm * 0.20) * 100

    @staticmethod
    def compute_china_indicators(
        df: pd.DataFrame, hg_col: str = "hg_close", usd_cny_col: str = "usd_cny"
    ) -> pd.DataFrame:
        """Compute all China bucket indicators with dashboard-ready features."""
        result = df.copy()

        # Copper as China demand proxy
        if hg_col in df.columns:
            result["hg_momentum_5d"] = df[hg_col].pct_change(5) * 100
            result["hg_momentum_21d"] = df[hg_col].pct_change(21) * 100
            result["hg_momentum_63d"] = df[hg_col].pct_change(63) * 100
            result["hg_zscore"] = (df[hg_col] - df[hg_col].rolling(252).mean()) / df[
                hg_col
            ].rolling(252).std()

            # ============ DASHBOARD: BOLLINGER BANDS ============
            hg_sma20 = df[hg_col].rolling(20).mean()
            hg_std20 = df[hg_col].rolling(20).std()
            result["hg_bb_upper"] = hg_sma20 + (2 * hg_std20)
            result["hg_bb_middle"] = hg_sma20
            result["hg_bb_lower"] = hg_sma20 - (2 * hg_std20)
            result["hg_bb_width"] = (
                (result["hg_bb_upper"] - result["hg_bb_lower"]) / hg_sma20
            ) * 100
            result["hg_bb_pct"] = (df[hg_col] - result["hg_bb_lower"]) / (
                result["hg_bb_upper"] - result["hg_bb_lower"]
            )

            # ============ DASHBOARD: PERCENTILE BANDS ============
            result["hg_pct_90"] = df[hg_col].rolling(252).quantile(0.90)
            result["hg_pct_75"] = df[hg_col].rolling(252).quantile(0.75)
            result["hg_pct_50"] = df[hg_col].rolling(252).quantile(0.50)
            result["hg_pct_25"] = df[hg_col].rolling(252).quantile(0.25)
            result["hg_pct_10"] = df[hg_col].rolling(252).quantile(0.10)
            result["hg_percentile"] = df[hg_col].rolling(252).rank(pct=True) * 100

            # ============ DASHBOARD: MOVING AVERAGES (OVERLAYS) ============
            result["hg_sma_10"] = df[hg_col].rolling(10).mean()
            result["hg_sma_21"] = df[hg_col].rolling(21).mean()
            result["hg_sma_63"] = df[hg_col].rolling(63).mean()
            result["hg_sma_200"] = df[hg_col].rolling(200).mean()
            result["hg_ema_10"] = df[hg_col].ewm(span=10).mean()
            result["hg_ema_21"] = df[hg_col].ewm(span=21).mean()

            # ============ DASHBOARD: SIGNAL STRENGTH ============
            result["hg_signal_strength"] = (
                np.abs(result["hg_zscore"]).clip(0, 3) / 3 * 100
            )
            result["hg_bullish_prob"] = 1 / (1 + np.exp(-result["hg_zscore"]))
            result["hg_bearish_prob"] = 1 - result["hg_bullish_prob"]

            # ============ DASHBOARD: SUPPORT/RESISTANCE ============
            result["hg_52w_high"] = df[hg_col].rolling(252).max()
            result["hg_52w_low"] = df[hg_col].rolling(252).min()
            result["hg_range_position"] = (
                (df[hg_col] - result["hg_52w_low"])
                / (result["hg_52w_high"] - result["hg_52w_low"])
                * 100
            )

            # Rate of change
            result["hg_roc_5d"] = (df[hg_col] / df[hg_col].shift(5) - 1) * 100
            result["hg_roc_21d"] = (df[hg_col] / df[hg_col].shift(21) - 1) * 100

            # China demand regime
            result["china_demand_regime"] = pd.cut(
                result["hg_zscore"],
                bins=[-np.inf, -1.5, -0.5, 0.5, 1.5, np.inf],
                labels=["very_weak", "weak", "neutral", "strong", "very_strong"],
            )

            # HG/ZL correlation (rolling)
            if "close" in df.columns:
                result["hg_zl_corr_21d"] = df[hg_col].rolling(21).corr(df["close"])
                result["hg_zl_corr_60d"] = df[hg_col].rolling(60).corr(df["close"])
                result["hg_zl_corr_252d"] = df[hg_col].rolling(252).corr(df["close"])

                # Beta (HG sensitivity to ZL)
                hg_ret = df[hg_col].pct_change()
                zl_ret = df["close"].pct_change()
                result["hg_zl_beta_60d"] = (
                    hg_ret.rolling(60).cov(zl_ret) / zl_ret.rolling(60).var()
                )

        # FX impact (CNY)
        if usd_cny_col in df.columns:
            result["cny_momentum_5d"] = df[usd_cny_col].pct_change(5) * 100
            result["cny_momentum_21d"] = df[usd_cny_col].pct_change(21) * 100
            result["cny_zscore"] = (
                df[usd_cny_col] - df[usd_cny_col].rolling(252).mean()
            ) / df[usd_cny_col].rolling(252).std()
            result["cny_devalue_risk"] = (df[usd_cny_col] > 7.3).astype(int)
            result["cny_devalue_prob"] = 1 / (
                1 + np.exp(-(df[usd_cny_col] - 7.2) * 5)
            )  # Sigmoid around 7.2

            # CNY bands
            cny_sma20 = df[usd_cny_col].rolling(20).mean()
            cny_std20 = df[usd_cny_col].rolling(20).std()
            result["cny_bb_upper"] = cny_sma20 + (2 * cny_std20)
            result["cny_bb_lower"] = cny_sma20 - (2 * cny_std20)

            # CNY vs ZL correlation
            if "close" in df.columns:
                result["cny_zl_corr_60d"] = (
                    df[usd_cny_col].rolling(60).corr(df["close"])
                )

        # ============ DASHBOARD: COMPOSITE CHINA SIGNAL ============
        china_signals = []
        if "hg_zscore" in result.columns:
            china_signals.append(result["hg_zscore"])
        if "cny_zscore" in result.columns:
            china_signals.append(
                -result["cny_zscore"]
            )  # Negative = strong CNY = bullish

        if china_signals:
            result["china_bucket_signal"] = pd.concat(china_signals, axis=1).mean(
                axis=1
            )
            result["china_bucket_confidence"] = (
                100 - pd.concat(china_signals, axis=1).std(axis=1).clip(0, 1) * 50
            )
            result["china_signal_strength"] = (
                np.abs(result["china_bucket_signal"]).clip(0, 3) / 3 * 100
            )

        return result


# =============================================================================
# ENERGY BUCKET INDICATORS
# =============================================================================


class EnergyBucketIndicators:
    """
    ENERGY Bucket: Energy complex coupling

    Key Drivers:
    - Crude oil (biodiesel feedstock economics)
    - Heating oil (biodiesel substitute)
    - Crack spreads (refining margins)
    - Energy inventories
    """

    @staticmethod
    def compute_boho_spread(zl: pd.Series, ho: pd.Series) -> pd.Series:
        """
        BOHO spread = Soybean Oil - Heating Oil
        Biodiesel premium over petroleum diesel.
        """
        return zl - ho

    @staticmethod
    def compute_crack_spread_321(
        cl: pd.Series, rb: pd.Series, ho: pd.Series
    ) -> pd.Series:
        """
        3-2-1 Crack spread = 2×RB + 1×HO - 3×CL
        Refining margin proxy.
        """
        return 2 * rb + ho - 3 * cl

    @staticmethod
    def compute_energy_indicators(
        df: pd.DataFrame,
        cl_col: str = "cl_close",
        ho_col: str = "ho_close",
        rb_col: str = "rb_close",
        zl_col: str = "close",
    ) -> pd.DataFrame:
        """Compute all energy bucket indicators with dashboard-ready features."""
        result = df.copy()

        # BOHO spread (Biodiesel premium)
        if ho_col in df.columns and zl_col in df.columns:
            result["boho_spread"] = df[zl_col] - df[ho_col]
            result["boho_ratio"] = df[zl_col] / df[ho_col]
            result["boho_momentum_5d"] = result["boho_spread"].pct_change(5) * 100
            result["boho_momentum_21d"] = result["boho_spread"].pct_change(21) * 100
            result["boho_zscore"] = (
                result["boho_spread"] - result["boho_spread"].rolling(252).mean()
            ) / result["boho_spread"].rolling(252).std()

            # BOHO Bollinger Bands
            boho_sma20 = result["boho_spread"].rolling(20).mean()
            boho_std20 = result["boho_spread"].rolling(20).std()
            result["boho_bb_upper"] = boho_sma20 + (2 * boho_std20)
            result["boho_bb_middle"] = boho_sma20
            result["boho_bb_lower"] = boho_sma20 - (2 * boho_std20)
            result["boho_bb_pct"] = (
                result["boho_spread"] - result["boho_bb_lower"]
            ) / (result["boho_bb_upper"] - result["boho_bb_lower"])

            # BOHO percentile bands
            result["boho_pct_90"] = result["boho_spread"].rolling(252).quantile(0.90)
            result["boho_pct_50"] = result["boho_spread"].rolling(252).quantile(0.50)
            result["boho_pct_10"] = result["boho_spread"].rolling(252).quantile(0.10)
            result["boho_percentile"] = (
                result["boho_spread"].rolling(252).rank(pct=True) * 100
            )

            # Signal strength
            result["boho_signal_strength"] = (
                np.abs(result["boho_zscore"]).clip(0, 3) / 3 * 100
            )

        # Crude oil
        if cl_col in df.columns:
            result["cl_momentum_5d"] = df[cl_col].pct_change(5) * 100
            result["cl_momentum_21d"] = df[cl_col].pct_change(21) * 100
            result["cl_momentum_63d"] = df[cl_col].pct_change(63) * 100
            result["cl_zscore"] = (df[cl_col] - df[cl_col].rolling(252).mean()) / df[
                cl_col
            ].rolling(252).std()

            # CL Bollinger Bands
            cl_sma20 = df[cl_col].rolling(20).mean()
            cl_std20 = df[cl_col].rolling(20).std()
            result["cl_bb_upper"] = cl_sma20 + (2 * cl_std20)
            result["cl_bb_middle"] = cl_sma20
            result["cl_bb_lower"] = cl_sma20 - (2 * cl_std20)
            result["cl_bb_pct"] = (df[cl_col] - result["cl_bb_lower"]) / (
                result["cl_bb_upper"] - result["cl_bb_lower"]
            )

            # CL percentile bands
            result["cl_pct_90"] = df[cl_col].rolling(252).quantile(0.90)
            result["cl_pct_75"] = df[cl_col].rolling(252).quantile(0.75)
            result["cl_pct_50"] = df[cl_col].rolling(252).quantile(0.50)
            result["cl_pct_25"] = df[cl_col].rolling(252).quantile(0.25)
            result["cl_pct_10"] = df[cl_col].rolling(252).quantile(0.10)
            result["cl_percentile"] = df[cl_col].rolling(252).rank(pct=True) * 100

            # Moving averages
            result["cl_sma_21"] = df[cl_col].rolling(21).mean()
            result["cl_sma_63"] = df[cl_col].rolling(63).mean()
            result["cl_sma_200"] = df[cl_col].rolling(200).mean()

            # Signal strength
            result["cl_signal_strength"] = (
                np.abs(result["cl_zscore"]).clip(0, 3) / 3 * 100
            )
            result["cl_bullish_prob"] = 1 / (1 + np.exp(-result["cl_zscore"]))

            # Energy regime
            result["energy_regime"] = pd.cut(
                df[cl_col],
                bins=[0, 50, 70, 90, np.inf],
                labels=["low", "normal", "elevated", "high"],
            )

            # Support/resistance
            result["cl_52w_high"] = df[cl_col].rolling(252).max()
            result["cl_52w_low"] = df[cl_col].rolling(252).min()
            result["cl_range_position"] = (
                (df[cl_col] - result["cl_52w_low"])
                / (result["cl_52w_high"] - result["cl_52w_low"])
                * 100
            )

            # ZL/CL correlation
            if zl_col in df.columns:
                result["zl_cl_corr_21d"] = df[zl_col].rolling(21).corr(df[cl_col])
                result["zl_cl_corr_60d"] = df[zl_col].rolling(60).corr(df[cl_col])
                result["zl_cl_ratio"] = df[zl_col] / df[cl_col]

        # Crack spread
        if all(col in df.columns for col in [cl_col, ho_col, rb_col]):
            result["crack_spread_321"] = (
                EnergyBucketIndicators.compute_crack_spread_321(
                    df[cl_col], df[rb_col], df[ho_col]
                )
            )
            result["crack_momentum_21d"] = (
                result["crack_spread_321"].pct_change(21) * 100
            )
            result["crack_zscore"] = (
                result["crack_spread_321"]
                - result["crack_spread_321"].rolling(252).mean()
            ) / result["crack_spread_321"].rolling(252).std()

            # Crack spread bands
            crack_sma20 = result["crack_spread_321"].rolling(20).mean()
            crack_std20 = result["crack_spread_321"].rolling(20).std()
            result["crack_bb_upper"] = crack_sma20 + (2 * crack_std20)
            result["crack_bb_middle"] = crack_sma20
            result["crack_bb_lower"] = crack_sma20 - (2 * crack_std20)
            result["crack_percentile"] = (
                result["crack_spread_321"].rolling(252).rank(pct=True) * 100
            )

        # ============ DASHBOARD: COMPOSITE ENERGY SIGNAL ============
        energy_signals = []
        if "cl_zscore" in result.columns:
            energy_signals.append(result["cl_zscore"])
        if "boho_zscore" in result.columns:
            energy_signals.append(result["boho_zscore"])
        if "crack_zscore" in result.columns:
            energy_signals.append(result["crack_zscore"])

        if energy_signals:
            result["energy_bucket_signal"] = pd.concat(energy_signals, axis=1).mean(
                axis=1
            )
            result["energy_bucket_confidence"] = (
                100 - pd.concat(energy_signals, axis=1).std(axis=1).clip(0, 1.5) * 33
            )
            result["energy_signal_strength"] = (
                np.abs(result["energy_bucket_signal"]).clip(0, 3) / 3 * 100
            )

        return result


# =============================================================================
# BIOFUEL BUCKET INDICATORS
# =============================================================================


class BiofuelBucketIndicators:
    """
    BIOFUEL Bucket: Renewable fuel mandates

    Key Drivers:
    - RIN prices (D4 biodiesel, D6 ethanol)
    - LCFS credits (California)
    - Biodiesel production capacity
    - RFS mandate levels
    - EPA small refinery exemptions
    """

    @staticmethod
    def compute_biofuel_indicators(
        df: pd.DataFrame,
        rin_d4_col: str = "rin_d4",
        rin_d6_col: str = "rin_d6",
        lcfs_col: str = "lcfs_credit",
    ) -> pd.DataFrame:
        """Compute all biofuel bucket indicators with dashboard-ready features."""
        result = df.copy()

        # RIN D4 (Biodiesel)
        if rin_d4_col in df.columns:
            result["rin_d4_momentum_5d"] = df[rin_d4_col].pct_change(5) * 100
            result["rin_d4_momentum_21d"] = df[rin_d4_col].pct_change(21) * 100
            result["rin_d4_zscore"] = (
                df[rin_d4_col] - df[rin_d4_col].rolling(252).mean()
            ) / df[rin_d4_col].rolling(252).std()

            # RIN D4 Bollinger Bands
            rin_sma20 = df[rin_d4_col].rolling(20).mean()
            rin_std20 = df[rin_d4_col].rolling(20).std()
            result["rin_d4_bb_upper"] = rin_sma20 + (2 * rin_std20)
            result["rin_d4_bb_middle"] = rin_sma20
            result["rin_d4_bb_lower"] = rin_sma20 - (2 * rin_std20)
            result["rin_d4_bb_pct"] = (df[rin_d4_col] - result["rin_d4_bb_lower"]) / (
                result["rin_d4_bb_upper"] - result["rin_d4_bb_lower"]
            )

            # RIN percentile bands
            result["rin_d4_pct_90"] = df[rin_d4_col].rolling(252).quantile(0.90)
            result["rin_d4_pct_50"] = df[rin_d4_col].rolling(252).quantile(0.50)
            result["rin_d4_pct_10"] = df[rin_d4_col].rolling(252).quantile(0.10)
            result["rin_d4_percentile"] = (
                df[rin_d4_col].rolling(252).rank(pct=True) * 100
            )

            # Signal strength
            result["rin_d4_signal_strength"] = (
                np.abs(result["rin_d4_zscore"]).clip(0, 3) / 3 * 100
            )
            result["rin_d4_bullish_prob"] = 1 / (1 + np.exp(-result["rin_d4_zscore"]))

            # RIN regime
            result["rin_regime"] = pd.cut(
                df[rin_d4_col],
                bins=[0, 0.80, 1.20, 1.60, np.inf],
                labels=["weak", "neutral", "strong", "very_strong"],
            )

        # RIN D6 (Ethanol)
        if rin_d6_col in df.columns:
            result["rin_d6_momentum_5d"] = df[rin_d6_col].pct_change(5) * 100
            result["rin_d6_momentum_21d"] = df[rin_d6_col].pct_change(21) * 100
            result["rin_d6_zscore"] = (
                df[rin_d6_col] - df[rin_d6_col].rolling(252).mean()
            ) / df[rin_d6_col].rolling(252).std()

            # D4/D6 spread
            if rin_d4_col in df.columns:
                result["rin_d4_d6_spread"] = df[rin_d4_col] - df[rin_d6_col]
                result["rin_d4_d6_ratio"] = df[rin_d4_col] / df[rin_d6_col]

        # LCFS credits
        if lcfs_col in df.columns:
            result["lcfs_momentum_21d"] = df[lcfs_col].pct_change(21) * 100
            result["lcfs_zscore"] = (
                df[lcfs_col] - df[lcfs_col].rolling(252).mean()
            ) / df[lcfs_col].rolling(252).std()

            # LCFS bands
            lcfs_sma20 = df[lcfs_col].rolling(20).mean()
            lcfs_std20 = df[lcfs_col].rolling(20).std()
            result["lcfs_bb_upper"] = lcfs_sma20 + (2 * lcfs_std20)
            result["lcfs_bb_middle"] = lcfs_sma20
            result["lcfs_bb_lower"] = lcfs_sma20 - (2 * lcfs_std20)
            result["lcfs_percentile"] = df[lcfs_col].rolling(252).rank(pct=True) * 100
            result["lcfs_signal_strength"] = (
                np.abs(result["lcfs_zscore"]).clip(0, 3) / 3 * 100
            )

        # ============ DASHBOARD: COMPOSITE BIOFUEL SIGNAL ============
        biofuel_signals = []
        if "rin_d4_zscore" in result.columns:
            biofuel_signals.append(result["rin_d4_zscore"])
        if "rin_d6_zscore" in result.columns:
            biofuel_signals.append(result["rin_d6_zscore"])
        if "lcfs_zscore" in result.columns:
            biofuel_signals.append(result["lcfs_zscore"])

        if biofuel_signals:
            result["biofuel_bucket_signal"] = pd.concat(biofuel_signals, axis=1).mean(
                axis=1
            )
            result["biofuel_bucket_confidence"] = (
                100 - pd.concat(biofuel_signals, axis=1).std(axis=1).clip(0, 1.5) * 33
            )
            result["biofuel_signal_strength"] = (
                np.abs(result["biofuel_bucket_signal"]).clip(0, 3) / 3 * 100
            )

        return result


# =============================================================================
# PALM BUCKET INDICATORS
# =============================================================================


class PalmBucketIndicators:
    """
    PALM Bucket: Malaysia/Indonesia palm oil dynamics

    Key Drivers:
    - BMD palm oil futures (Malaysia)
    - Palm production seasonality
    - Malaysia/Indonesia inventory levels
    - Export levy policies
    - El Niño/La Niña impact on production
    - ZL vs Palm spread dynamics
    """

    @staticmethod
    def compute_palm_indicators(
        df: pd.DataFrame,
        palm_col: str = "palm_oil_close",
        zl_col: str = "close",
        inventory_col: str = "palm_inventory_malaysia",
        production_col: str = "palm_production_malaysia",
    ) -> pd.DataFrame:
        """Compute all palm bucket indicators with dashboard-ready features."""
        result = df.copy()

        # Palm oil price dynamics
        if palm_col in df.columns:
            # Multi-timeframe momentum
            result["palm_momentum_5d"] = df[palm_col].pct_change(5) * 100
            result["palm_momentum_10d"] = df[palm_col].pct_change(10) * 100
            result["palm_momentum_21d"] = df[palm_col].pct_change(21) * 100
            result["palm_momentum_63d"] = df[palm_col].pct_change(63) * 100

            # Z-score (1y lookback)
            result["palm_zscore"] = (
                df[palm_col] - df[palm_col].rolling(252).mean()
            ) / df[palm_col].rolling(252).std()

            # ============ DASHBOARD: BOLLINGER BANDS ============
            palm_sma20 = df[palm_col].rolling(20).mean()
            palm_std20 = df[palm_col].rolling(20).std()
            result["palm_bb_upper"] = palm_sma20 + (2 * palm_std20)
            result["palm_bb_middle"] = palm_sma20
            result["palm_bb_lower"] = palm_sma20 - (2 * palm_std20)
            result["palm_bb_width"] = (
                (result["palm_bb_upper"] - result["palm_bb_lower"]) / palm_sma20
            ) * 100
            result["palm_bb_pct"] = (df[palm_col] - result["palm_bb_lower"]) / (
                result["palm_bb_upper"] - result["palm_bb_lower"]
            )

            # ============ DASHBOARD: PERCENTILE BANDS ============
            result["palm_pct_90"] = df[palm_col].rolling(252).quantile(0.90)
            result["palm_pct_75"] = df[palm_col].rolling(252).quantile(0.75)
            result["palm_pct_50"] = df[palm_col].rolling(252).quantile(0.50)
            result["palm_pct_25"] = df[palm_col].rolling(252).quantile(0.25)
            result["palm_pct_10"] = df[palm_col].rolling(252).quantile(0.10)
            result["palm_percentile"] = df[palm_col].rolling(252).rank(pct=True) * 100

            # ============ DASHBOARD: MOVING AVERAGES (OVERLAYS) ============
            result["palm_sma_10"] = df[palm_col].rolling(10).mean()
            result["palm_sma_21"] = df[palm_col].rolling(21).mean()
            result["palm_sma_63"] = df[palm_col].rolling(63).mean()
            result["palm_sma_200"] = df[palm_col].rolling(200).mean()
            result["palm_ema_10"] = df[palm_col].ewm(span=10).mean()
            result["palm_ema_21"] = df[palm_col].ewm(span=21).mean()

            # ============ DASHBOARD: SIGNAL STRENGTH ============
            result["palm_signal_strength"] = (
                np.abs(result["palm_zscore"]).clip(0, 3) / 3 * 100
            )
            result["palm_bullish_prob"] = 1 / (1 + np.exp(-result["palm_zscore"]))
            result["palm_bearish_prob"] = 1 - result["palm_bullish_prob"]

            # Rate of change
            result["palm_roc_5d"] = (df[palm_col] / df[palm_col].shift(5) - 1) * 100
            result["palm_roc_21d"] = (df[palm_col] / df[palm_col].shift(21) - 1) * 100

            # Volatility metrics
            result["palm_volatility_21d"] = (
                df[palm_col].pct_change().rolling(21).std() * np.sqrt(252) * 100
            )
            result["palm_volatility_63d"] = (
                df[palm_col].pct_change().rolling(63).std() * np.sqrt(252) * 100
            )
            result["palm_vol_regime"] = pd.cut(
                result["palm_volatility_21d"],
                bins=[0, 15, 25, 40, np.inf],
                labels=["low", "normal", "elevated", "high"],
            )

            # Support/resistance
            result["palm_52w_high"] = df[palm_col].rolling(252).max()
            result["palm_52w_low"] = df[palm_col].rolling(252).min()
            result["palm_range_position"] = (
                (df[palm_col] - result["palm_52w_low"])
                / (result["palm_52w_high"] - result["palm_52w_low"])
                * 100
            )

        # ZL vs Palm spread (critical competitive relationship)
        if palm_col in df.columns and zl_col in df.columns:
            result["zl_palm_spread"] = df[zl_col] - df[palm_col]
            result["zl_palm_ratio"] = df[zl_col] / df[palm_col]

            # Spread z-score
            result["zl_palm_spread_zscore"] = (
                result["zl_palm_spread"] - result["zl_palm_spread"].rolling(252).mean()
            ) / result["zl_palm_spread"].rolling(252).std()

            # ============ DASHBOARD: SPREAD BANDS ============
            spread_sma20 = result["zl_palm_spread"].rolling(20).mean()
            spread_std20 = result["zl_palm_spread"].rolling(20).std()
            result["zl_palm_spread_bb_upper"] = spread_sma20 + (2 * spread_std20)
            result["zl_palm_spread_bb_middle"] = spread_sma20
            result["zl_palm_spread_bb_lower"] = spread_sma20 - (2 * spread_std20)
            result["zl_palm_spread_bb_pct"] = (
                result["zl_palm_spread"] - result["zl_palm_spread_bb_lower"]
            ) / (result["zl_palm_spread_bb_upper"] - result["zl_palm_spread_bb_lower"])

            # Spread percentile bands
            result["zl_palm_spread_pct_90"] = (
                result["zl_palm_spread"].rolling(252).quantile(0.90)
            )
            result["zl_palm_spread_pct_50"] = (
                result["zl_palm_spread"].rolling(252).quantile(0.50)
            )
            result["zl_palm_spread_pct_10"] = (
                result["zl_palm_spread"].rolling(252).quantile(0.10)
            )
            result["zl_palm_spread_percentile"] = (
                result["zl_palm_spread"].rolling(252).rank(pct=True) * 100
            )

            # Spread momentum
            result["zl_palm_spread_momentum_5d"] = result["zl_palm_spread"].diff(5)
            result["zl_palm_spread_momentum_21d"] = result["zl_palm_spread"].diff(21)
            result["zl_palm_spread_roc_21d"] = (
                result["zl_palm_spread"] / result["zl_palm_spread"].shift(21) - 1
            ) * 100

            # ============ DASHBOARD: PROBABILITY/CONVERGENCE ============
            # Probability of spread convergence/divergence
            result["palm_premium_prob"] = 1 / (
                1 + np.exp(result["zl_palm_spread_zscore"])
            )
            result["zl_premium_prob"] = 1 - result["palm_premium_prob"]

            # Substitution signal (negative = palm attractive, positive = ZL attractive)
            result["palm_substitution_signal"] = result["zl_palm_spread_zscore"]
            result["palm_substitution_strength"] = (
                np.abs(result["zl_palm_spread_zscore"]).clip(0, 3) / 3 * 100
            )

            # Ratio regime detection
            result["palm_regime"] = pd.cut(
                result["zl_palm_ratio"],
                bins=[0, 1.00, 1.08, 1.15, np.inf],
                labels=[
                    "palm_premium",
                    "parity",
                    "zl_premium",
                    "zl_strong_premium",
                ],
            )

            # Correlation dynamics
            result["zl_palm_corr_21d"] = df[zl_col].rolling(21).corr(df[palm_col])
            result["zl_palm_corr_63d"] = df[zl_col].rolling(63).corr(df[palm_col])
            result["zl_palm_corr_252d"] = df[zl_col].rolling(252).corr(df[palm_col])

            # Beta (Palm sensitivity to ZL)
            palm_ret = df[palm_col].pct_change()
            zl_ret = df[zl_col].pct_change()
            result["palm_zl_beta_60d"] = (
                palm_ret.rolling(60).cov(zl_ret) / zl_ret.rolling(60).var()
            )

        # Malaysia inventory dynamics
        if inventory_col in df.columns:
            result["palm_inv_momentum_1m"] = df[inventory_col].pct_change(21) * 100
            result["palm_inv_zscore"] = (
                df[inventory_col] - df[inventory_col].rolling(252).mean()
            ) / df[inventory_col].rolling(252).std()

            # Inventory bands
            result["palm_inv_pct_90"] = df[inventory_col].rolling(252).quantile(0.90)
            result["palm_inv_pct_50"] = df[inventory_col].rolling(252).quantile(0.50)
            result["palm_inv_pct_10"] = df[inventory_col].rolling(252).quantile(0.10)

            # Inventory regime
            result["palm_inv_regime"] = pd.cut(
                df[inventory_col],
                bins=[0, 1.5, 2.0, 2.5, np.inf],
                labels=["critical_low", "low", "normal", "surplus"],
            )

            # Low inventory probability
            result["palm_inv_critical_prob"] = 1 / (
                1 + np.exp((df[inventory_col] - 1.5) * 2)
            )

        # Production seasonality
        if production_col in df.columns:
            result["palm_prod_momentum_1m"] = df[production_col].pct_change(21) * 100
            result["palm_prod_zscore"] = (
                df[production_col] - df[production_col].rolling(252).mean()
            ) / df[production_col].rolling(252).std()

            # Production bands
            result["palm_prod_pct_90"] = df[production_col].rolling(252).quantile(0.90)
            result["palm_prod_pct_50"] = df[production_col].rolling(252).quantile(0.50)
            result["palm_prod_pct_10"] = df[production_col].rolling(252).quantile(0.10)

            # Production regime
            result["palm_prod_regime"] = pd.cut(
                df[production_col],
                bins=[0, 1.4, 1.6, 1.8, np.inf],
                labels=["low_output", "below_avg", "above_avg", "peak_output"],
            )

        # ============ DASHBOARD: COMPOSITE PALM SIGNAL ============
        signal_cols = [
            col
            for col in [
                "palm_zscore",
                "palm_inv_zscore",
                "palm_prod_zscore",
                "zl_palm_spread_zscore",
            ]
            if col in result.columns
        ]
        if signal_cols:
            result["palm_fundamental_signal"] = result[signal_cols].mean(axis=1)
            result["palm_bucket_confidence"] = (
                100 - result[signal_cols].std(axis=1).clip(0, 1.5) * 33
            )
            result["palm_bucket_signal_strength"] = (
                np.abs(result["palm_fundamental_signal"]).clip(0, 3) / 3 * 100
            )

        return result


# =============================================================================
# SUBSTITUTES BUCKET INDICATORS
# =============================================================================


class SubstitutesBucketIndicators:
    """
    SUBSTITUTES Bucket: Non-palm competing vegetable oils

    Key Drivers:
    - Canola/Rapeseed prices (Canada, EU)
    - Sunflower oil prices (Black Sea)
    - Cottonseed oil prices
    - ZL spreads vs alternatives
    - Regional production/export dynamics
    """

    @staticmethod
    def compute_substitutes_indicators(
        df: pd.DataFrame,
        canola_col: str = "canola_close",
        sunflower_col: str = "sunflower_close",
        cottonseed_col: str = "cottonseed_oil_close",
        zl_col: str = "close",
    ) -> pd.DataFrame:
        """Compute all substitutes bucket indicators with dashboard-ready features."""
        result = df.copy()

        # Canola
        if canola_col in df.columns:
            result["canola_momentum_5d"] = df[canola_col].pct_change(5) * 100
            result["canola_momentum_21d"] = df[canola_col].pct_change(21) * 100
            result["canola_zscore"] = (
                df[canola_col] - df[canola_col].rolling(252).mean()
            ) / df[canola_col].rolling(252).std()

            # Canola Bollinger Bands
            canola_sma20 = df[canola_col].rolling(20).mean()
            canola_std20 = df[canola_col].rolling(20).std()
            result["canola_bb_upper"] = canola_sma20 + (2 * canola_std20)
            result["canola_bb_middle"] = canola_sma20
            result["canola_bb_lower"] = canola_sma20 - (2 * canola_std20)
            result["canola_percentile"] = (
                df[canola_col].rolling(252).rank(pct=True) * 100
            )
            result["canola_signal_strength"] = (
                np.abs(result["canola_zscore"]).clip(0, 3) / 3 * 100
            )

            # ZL vs Canola spread
            if zl_col in df.columns:
                result["zl_canola_spread"] = df[zl_col] - df[canola_col]
                result["zl_canola_ratio"] = df[zl_col] / df[canola_col]
                result["zl_canola_corr_60d"] = (
                    df[zl_col].rolling(60).corr(df[canola_col])
                )
                result["zl_canola_spread_zscore"] = (
                    result["zl_canola_spread"]
                    - result["zl_canola_spread"].rolling(252).mean()
                ) / result["zl_canola_spread"].rolling(252).std()

        # Sunflower
        if sunflower_col in df.columns:
            result["sunflower_momentum_5d"] = df[sunflower_col].pct_change(5) * 100
            result["sunflower_momentum_21d"] = df[sunflower_col].pct_change(21) * 100
            result["sunflower_zscore"] = (
                df[sunflower_col] - df[sunflower_col].rolling(252).mean()
            ) / df[sunflower_col].rolling(252).std()

            # ZL vs Sunflower spread
            if zl_col in df.columns:
                result["zl_sunflower_spread"] = df[zl_col] - df[sunflower_col]
                result["zl_sunflower_ratio"] = df[zl_col] / df[sunflower_col]

        # Cottonseed oil
        if cottonseed_col in df.columns:
            result["cottonseed_momentum_5d"] = df[cottonseed_col].pct_change(5) * 100
            result["cottonseed_momentum_21d"] = df[cottonseed_col].pct_change(21) * 100

            if zl_col in df.columns:
                result["zl_cottonseed_spread"] = df[zl_col] - df[cottonseed_col]
                result["zl_cottonseed_ratio"] = df[zl_col] / df[cottonseed_col]

        # Substitution index (composite - excluding palm, now in its own bucket)
        spread_cols = []
        if canola_col in df.columns and zl_col in df.columns:
            result["_canola_spread_pct"] = (df[zl_col] - df[canola_col]) / df[
                canola_col
            ]
            spread_cols.append("_canola_spread_pct")
        if sunflower_col in df.columns and zl_col in df.columns:
            result["_sunflower_spread_pct"] = (df[zl_col] - df[sunflower_col]) / df[
                sunflower_col
            ]
            spread_cols.append("_sunflower_spread_pct")

        if spread_cols:
            result["substitution_index"] = result[spread_cols].mean(axis=1) * 100
            result["substitution_regime"] = pd.cut(
                result["substitution_index"],
                bins=[-np.inf, -10, 0, 10, np.inf],
                labels=[
                    "zl_cheap",
                    "zl_slight_discount",
                    "zl_slight_premium",
                    "zl_expensive",
                ],
            )
            # Clean up temp columns
            result = result.drop(columns=spread_cols, errors="ignore")

        # ============ DASHBOARD: COMPOSITE SUBSTITUTES SIGNAL ============
        sub_signals = []
        if "canola_zscore" in result.columns:
            sub_signals.append(result["canola_zscore"])
        if "sunflower_zscore" in result.columns:
            sub_signals.append(result["sunflower_zscore"])

        if sub_signals:
            result["substitutes_bucket_signal"] = pd.concat(sub_signals, axis=1).mean(
                axis=1
            )
            result["substitutes_signal_strength"] = (
                np.abs(result["substitutes_bucket_signal"]).clip(0, 3) / 3 * 100
            )

        return result


# =============================================================================
# FX BUCKET INDICATORS
# =============================================================================


class FXBucketIndicators:
    """
    FX Bucket: Currency effects on export competitiveness

    Key Drivers:
    - DXY (dollar strength)
    - USD/BRL (Brazil competitiveness)
    - USD/CNY (China import costs)
    - USD/ARS (Argentina competitiveness)
    - EM currency index
    """

    @staticmethod
    def compute_fx_indicators(
        df: pd.DataFrame,
        dxy_col: str = "dxy",
        brl_col: str = "usd_brl",
        cny_col: str = "usd_cny",
    ) -> pd.DataFrame:
        """Compute all FX bucket indicators with dashboard-ready features."""
        result = df.copy()

        # DXY (Dollar Index)
        if dxy_col in df.columns:
            result["dxy_momentum_5d"] = df[dxy_col].pct_change(5) * 100
            result["dxy_momentum_21d"] = df[dxy_col].pct_change(21) * 100
            result["dxy_zscore"] = (df[dxy_col] - df[dxy_col].rolling(252).mean()) / df[
                dxy_col
            ].rolling(252).std()

            # Dollar regime
            result["dollar_regime"] = pd.cut(
                df[dxy_col],
                bins=[0, 95, 100, 105, np.inf],
                labels=["weak", "neutral", "strong", "very_strong"],
            )

            # DXY vs ZL correlation
            if "close" in df.columns:
                result["dxy_zl_corr_60d"] = df[dxy_col].rolling(60).corr(df["close"])

        # Brazilian Real
        if brl_col in df.columns:
            result["brl_momentum_5d"] = df[brl_col].pct_change(5) * 100
            result["brl_momentum_21d"] = df[brl_col].pct_change(21) * 100
            result["brl_zscore"] = (df[brl_col] - df[brl_col].rolling(252).mean()) / df[
                brl_col
            ].rolling(252).std()
            result["brl_stress"] = (df[brl_col] > 5.5).astype(int)
            result["brl_stress_prob"] = 1 / (1 + np.exp(-(df[brl_col] - 5.5) * 2))

            # BRL bands
            result["brl_pct_90"] = df[brl_col].rolling(252).quantile(0.90)
            result["brl_pct_50"] = df[brl_col].rolling(252).quantile(0.50)
            result["brl_pct_10"] = df[brl_col].rolling(252).quantile(0.10)
            result["brl_percentile"] = df[brl_col].rolling(252).rank(pct=True) * 100

            # BRL vs ZL correlation (usually negative)
            if "close" in df.columns:
                result["brl_zl_corr_60d"] = df[brl_col].rolling(60).corr(df["close"])

        # Chinese Yuan
        if cny_col in df.columns:
            result["cny_momentum_5d"] = df[cny_col].pct_change(5) * 100
            result["cny_momentum_21d"] = df[cny_col].pct_change(21) * 100
            result["cny_devalue_risk"] = (df[cny_col] > 7.3).astype(int)

        # ============ DASHBOARD: COMPOSITE FX SIGNAL ============
        fx_signals = []
        if "dxy_zscore" in result.columns:
            fx_signals.append(result["dxy_zscore"])
        if "brl_zscore" in result.columns:
            fx_signals.append(result["brl_zscore"])

        if fx_signals:
            result["fx_bucket_signal"] = pd.concat(fx_signals, axis=1).mean(axis=1)
            result["fx_signal_strength"] = (
                np.abs(result["fx_bucket_signal"]).clip(0, 3) / 3 * 100
            )

        return result


# =============================================================================
# FED BUCKET INDICATORS
# =============================================================================


class FedBucketIndicators:
    """
    FED Bucket: US monetary policy impacts

    Key Drivers:
    - Fed funds rate
    - Yield curve (10Y-2Y spread)
    - NFCI (financial conditions)
    - Real rates
    - Fed balance sheet
    """

    @staticmethod
    def compute_fed_indicators(
        df: pd.DataFrame,
        dff_col: str = "dff",
        t10y2y_col: str = "t10y2y",
        nfci_col: str = "nfci",
    ) -> pd.DataFrame:
        """Compute all Fed bucket indicators with dashboard-ready features."""
        result = df.copy()

        # Fed Funds Rate
        if dff_col in df.columns:
            result["fed_funds_change_21d"] = df[dff_col].diff(21)
            result["fed_funds_direction"] = np.sign(df[dff_col].diff(63))
            result["fed_funds_zscore"] = (
                df[dff_col] - df[dff_col].rolling(252).mean()
            ) / df[dff_col].rolling(252).std()

            # Fed funds bands
            result["fed_funds_pct_90"] = df[dff_col].rolling(252).quantile(0.90)
            result["fed_funds_pct_50"] = df[dff_col].rolling(252).quantile(0.50)
            result["fed_funds_pct_10"] = df[dff_col].rolling(252).quantile(0.10)
            result["fed_funds_percentile"] = (
                df[dff_col].rolling(252).rank(pct=True) * 100
            )

            # Rate regime
            result["rate_regime"] = pd.cut(
                df[dff_col],
                bins=[0, 2, 4, 6, np.inf],
                labels=["low", "moderate", "restrictive", "very_restrictive"],
            )

        # Yield Curve
        if t10y2y_col in df.columns:
            result["yield_curve_momentum"] = df[t10y2y_col].diff(21)
            result["yield_curve_inverted"] = (df[t10y2y_col] < 0).astype(int)
            result["yield_curve_zscore"] = (
                df[t10y2y_col] - df[t10y2y_col].rolling(252).mean()
            ) / df[t10y2y_col].rolling(252).std()

            # Inversion streak
            result["inversion_streak"] = (
                result["yield_curve_inverted"]
                .groupby(
                    (
                        result["yield_curve_inverted"]
                        != result["yield_curve_inverted"].shift()
                    ).cumsum()
                )
                .cumsum()
            )

        # NFCI (Financial Conditions)
        if nfci_col in df.columns:
            result["nfci_momentum_21d"] = df[nfci_col].diff(21)
            result["nfci_zscore"] = df[nfci_col]  # NFCI is already z-scored

            # NFCI bands
            result["nfci_pct_90"] = df[nfci_col].rolling(252).quantile(0.90)
            result["nfci_pct_50"] = df[nfci_col].rolling(252).quantile(0.50)
            result["nfci_pct_10"] = df[nfci_col].rolling(252).quantile(0.10)
            result["nfci_percentile"] = df[nfci_col].rolling(252).rank(pct=True) * 100

            # Financial conditions regime
            result["financial_conditions"] = pd.cut(
                df[nfci_col],
                bins=[-np.inf, -0.5, 0, 0.5, np.inf],
                labels=["very_loose", "loose", "neutral", "tight"],
            )

            # Tight conditions probability
            result["nfci_tight_prob"] = 1 / (1 + np.exp(-df[nfci_col] * 2))

        # ============ DASHBOARD: COMPOSITE FED SIGNAL ============
        fed_signals = []
        if "fed_funds_zscore" in result.columns:
            fed_signals.append(result["fed_funds_zscore"])
        if "yield_curve_zscore" in result.columns:
            fed_signals.append(
                -result["yield_curve_zscore"]
            )  # Invert: negative YC = hawkish
        if "nfci_zscore" in result.columns:
            fed_signals.append(result["nfci_zscore"])

        if fed_signals:
            result["fed_bucket_signal"] = pd.concat(fed_signals, axis=1).mean(axis=1)
            result["fed_signal_strength"] = (
                np.abs(result["fed_bucket_signal"]).clip(0, 3) / 3 * 100
            )

        return result


# =============================================================================
# VOLATILITY BUCKET INDICATORS
# =============================================================================


class VolatilityBucketIndicators:
    """
    VOLATILITY Bucket: Financial stress and fear

    Key Drivers:
    - VIX (equity fear gauge)
    - OVX (oil volatility)
    - Realized volatility
    - Term structure slope
    - Skew index
    """

    @staticmethod
    def compute_volatility_indicators(
        df: pd.DataFrame, vix_col: str = "vix", stlfsi_col: str = "stlfsi4"
    ) -> pd.DataFrame:
        """Compute all volatility bucket indicators with dashboard-ready features."""
        result = df.copy()

        # VIX
        if vix_col in df.columns:
            result["vix_momentum_5d"] = df[vix_col].diff(5)
            result["vix_momentum_21d"] = df[vix_col].diff(21)
            result["vix_momentum_63d"] = df[vix_col].diff(63)
            result["vix_zscore"] = (df[vix_col] - df[vix_col].rolling(252).mean()) / df[
                vix_col
            ].rolling(252).std()

            # ============ DASHBOARD: BOLLINGER BANDS ============
            vix_sma20 = df[vix_col].rolling(20).mean()
            vix_std20 = df[vix_col].rolling(20).std()
            result["vix_bb_upper"] = vix_sma20 + (2 * vix_std20)
            result["vix_bb_middle"] = vix_sma20
            result["vix_bb_lower"] = vix_sma20 - (2 * vix_std20)
            result["vix_bb_width"] = (
                (result["vix_bb_upper"] - result["vix_bb_lower"]) / vix_sma20
            ) * 100
            result["vix_bb_pct"] = (df[vix_col] - result["vix_bb_lower"]) / (
                result["vix_bb_upper"] - result["vix_bb_lower"]
            )

            # ============ DASHBOARD: PERCENTILE BANDS ============
            result["vix_pct_95"] = df[vix_col].rolling(252).quantile(0.95)
            result["vix_pct_90"] = df[vix_col].rolling(252).quantile(0.90)
            result["vix_pct_75"] = df[vix_col].rolling(252).quantile(0.75)
            result["vix_pct_50"] = df[vix_col].rolling(252).quantile(0.50)
            result["vix_pct_25"] = df[vix_col].rolling(252).quantile(0.25)
            result["vix_pct_10"] = df[vix_col].rolling(252).quantile(0.10)
            result["vix_percentile"] = df[vix_col].rolling(252).rank(pct=True) * 100

            # ============ DASHBOARD: MOVING AVERAGES (OVERLAYS) ============
            result["vix_sma_10"] = df[vix_col].rolling(10).mean()
            result["vix_sma_21"] = df[vix_col].rolling(21).mean()
            result["vix_sma_63"] = df[vix_col].rolling(63).mean()
            result["vix_sma_200"] = df[vix_col].rolling(200).mean()
            result["vix_ema_10"] = df[vix_col].ewm(span=10).mean()
            result["vix_ema_21"] = df[vix_col].ewm(span=21).mean()

            # ============ DASHBOARD: SIGNAL STRENGTH/PROBABILITY ============
            result["vix_signal_strength"] = (
                np.abs(result["vix_zscore"]).clip(0, 3) / 3 * 100
            )
            # Fear probability (high when VIX elevated)
            result["vix_fear_prob"] = 1 / (1 + np.exp(-(df[vix_col] - 25) / 5))
            # Complacency probability (high when VIX low)
            result["vix_complacent_prob"] = 1 / (1 + np.exp((df[vix_col] - 15) / 3))
            # Crisis probability
            result["vix_crisis_prob"] = 1 / (1 + np.exp(-(df[vix_col] - 35) / 5))

            # VIX regime
            result["vol_regime"] = pd.cut(
                df[vix_col],
                bins=[0, 15, 20, 30, 40, np.inf],
                labels=["complacent", "low", "normal", "elevated", "crisis"],
            )

            # VIX spike detection
            result["vix_spike"] = (
                df[vix_col] > df[vix_col].rolling(20).mean() * 1.5
            ).astype(int)
            result["vix_spike_intensity"] = (
                df[vix_col] / df[vix_col].rolling(20).mean() - 1
            ) * 100

            # VIX mean reversion signal
            result["vix_mean_revert"] = np.where(
                df[vix_col] > df[vix_col].rolling(252).quantile(0.9),
                -1,  # Likely to fall
                np.where(
                    df[vix_col] < df[vix_col].rolling(252).quantile(0.1), 1, 0
                ),  # Likely to rise
            )
            result["vix_mean_revert_strength"] = np.abs(result["vix_zscore"]).clip(0, 3)

            # Rate of change
            result["vix_roc_5d"] = (df[vix_col] / df[vix_col].shift(5) - 1) * 100
            result["vix_roc_21d"] = (df[vix_col] / df[vix_col].shift(21) - 1) * 100

            # Support/resistance
            result["vix_52w_high"] = df[vix_col].rolling(252).max()
            result["vix_52w_low"] = df[vix_col].rolling(252).min()
            result["vix_range_position"] = (
                (df[vix_col] - result["vix_52w_low"])
                / (result["vix_52w_high"] - result["vix_52w_low"])
                * 100
            )

            # Correlation with ZL
            if "close" in df.columns:
                result["vix_zl_corr_21d"] = df[vix_col].rolling(21).corr(df["close"])
                result["vix_zl_corr_60d"] = df[vix_col].rolling(60).corr(df["close"])

        # St. Louis Fed Financial Stress Index
        if stlfsi_col in df.columns:
            result["stlfsi_momentum_21d"] = df[stlfsi_col].diff(21)
            result["stlfsi_zscore"] = df[stlfsi_col]  # Already a z-score
            result["stlfsi_elevated"] = (df[stlfsi_col] > 0).astype(int)
            result["stlfsi_crisis"] = (df[stlfsi_col] > 1.5).astype(int)

            # STLFSI bands
            result["stlfsi_pct_90"] = df[stlfsi_col].rolling(252).quantile(0.90)
            result["stlfsi_pct_50"] = df[stlfsi_col].rolling(252).quantile(0.50)
            result["stlfsi_pct_10"] = df[stlfsi_col].rolling(252).quantile(0.10)

            # Stress probability
            result["stlfsi_stress_prob"] = 1 / (1 + np.exp(-df[stlfsi_col] * 2))

        # Realized volatility
        if "close" in df.columns:
            returns = np.log(df["close"] / df["close"].shift(1))
            result["realized_vol_10d"] = returns.rolling(10).std() * np.sqrt(252) * 100
            result["realized_vol_20d"] = returns.rolling(20).std() * np.sqrt(252) * 100
            result["realized_vol_60d"] = returns.rolling(60).std() * np.sqrt(252) * 100
            result["realized_vol_252d"] = (
                returns.rolling(252).std() * np.sqrt(252) * 100
            )

            # ============ DASHBOARD: REALIZED VOL BANDS ============
            rv_sma20 = result["realized_vol_20d"].rolling(20).mean()
            rv_std20 = result["realized_vol_20d"].rolling(20).std()
            result["rv_bb_upper"] = rv_sma20 + (2 * rv_std20)
            result["rv_bb_middle"] = rv_sma20
            result["rv_bb_lower"] = rv_sma20 - (2 * rv_std20)

            # Realized vol percentile bands
            result["rv_pct_90"] = result["realized_vol_20d"].rolling(252).quantile(0.90)
            result["rv_pct_75"] = result["realized_vol_20d"].rolling(252).quantile(0.75)
            result["rv_pct_50"] = result["realized_vol_20d"].rolling(252).quantile(0.50)
            result["rv_pct_25"] = result["realized_vol_20d"].rolling(252).quantile(0.25)
            result["rv_pct_10"] = result["realized_vol_20d"].rolling(252).quantile(0.10)
            result["rv_percentile"] = (
                result["realized_vol_20d"].rolling(252).rank(pct=True) * 100
            )

            # Volatility of volatility
            result["vol_of_vol"] = result["realized_vol_20d"].rolling(20).std()
            result["vol_of_vol_zscore"] = (
                result["vol_of_vol"] - result["vol_of_vol"].rolling(252).mean()
            ) / result["vol_of_vol"].rolling(252).std()

            # Vol regime (realized)
            result["realized_vol_regime"] = pd.cut(
                result["realized_vol_20d"],
                bins=[0, 15, 25, 40, np.inf],
                labels=["low", "normal", "elevated", "high"],
            )

            # Vol term structure (short vs long)
            result["vol_term_structure"] = (
                result["realized_vol_10d"] - result["realized_vol_60d"]
            )
            result["vol_term_inverted"] = (result["vol_term_structure"] > 5).astype(int)

        # ============ DASHBOARD: COMPOSITE VOLATILITY SIGNAL ============
        vol_signals = []
        if "vix_zscore" in result.columns:
            vol_signals.append(result["vix_zscore"])
        if "stlfsi_zscore" in result.columns:
            vol_signals.append(result["stlfsi_zscore"])
        if "realized_vol_20d" in result.columns:
            rv_zscore = (
                result["realized_vol_20d"]
                - result["realized_vol_20d"].rolling(252).mean()
            ) / result["realized_vol_20d"].rolling(252).std()
            vol_signals.append(rv_zscore)

        if vol_signals:
            result["vol_bucket_signal"] = pd.concat(vol_signals, axis=1).mean(axis=1)
            result["vol_bucket_confidence"] = (
                100 - pd.concat(vol_signals, axis=1).std(axis=1).clip(0, 1.5) * 33
            )
            result["vol_bucket_signal_strength"] = (
                np.abs(result["vol_bucket_signal"]).clip(0, 3) / 3 * 100
            )

        return result


# =============================================================================
# TARIFF BUCKET INDICATORS
# =============================================================================


class TariffBucketIndicators:
    """
    TARIFF Bucket: Trade policy impacts

    Key Drivers:
    - Effective tariff rates
    - Trade war sentiment
    - Policy uncertainty index
    - Retaliatory tariff risk
    - Trade negotiation progress
    """

    @staticmethod
    def compute_tariff_indicators(
        df: pd.DataFrame,
        epu_col: str = "economic_policy_uncertainty",
        sentiment_col: str = "trade_war_sentiment",
    ) -> pd.DataFrame:
        """Compute all tariff bucket indicators with dashboard-ready features."""
        result = df.copy()

        # Economic Policy Uncertainty
        if epu_col in df.columns:
            result["epu_momentum_21d"] = df[epu_col].pct_change(21) * 100
            result["epu_zscore"] = (df[epu_col] - df[epu_col].rolling(252).mean()) / df[
                epu_col
            ].rolling(252).std()
            result["epu_elevated"] = (
                df[epu_col] > df[epu_col].rolling(252).quantile(0.75)
            ).astype(int)

            # EPU bands
            result["epu_pct_90"] = df[epu_col].rolling(252).quantile(0.90)
            result["epu_pct_75"] = df[epu_col].rolling(252).quantile(0.75)
            result["epu_pct_50"] = df[epu_col].rolling(252).quantile(0.50)
            result["epu_pct_25"] = df[epu_col].rolling(252).quantile(0.25)
            result["epu_percentile"] = df[epu_col].rolling(252).rank(pct=True) * 100

            # EPU signal strength
            result["epu_signal_strength"] = (
                np.abs(result["epu_zscore"]).clip(0, 3) / 3 * 100
            )

        # Trade War Sentiment
        if sentiment_col in df.columns:
            result["trade_sentiment_momentum"] = df[sentiment_col].diff(21)
            result["trade_tension_high"] = (df[sentiment_col] > 0.7).astype(int)
            result["trade_detente"] = (df[sentiment_col] < 0.3).astype(int)
            result["trade_escalation_prob"] = df[sentiment_col]  # Already 0-1 scale

        # ============ DASHBOARD: COMPOSITE TARIFF SIGNAL ============
        tariff_signals = []
        if "epu_zscore" in result.columns:
            tariff_signals.append(result["epu_zscore"])

        if tariff_signals:
            result["tariff_bucket_signal"] = pd.concat(tariff_signals, axis=1).mean(
                axis=1
            )
            result["tariff_signal_strength"] = (
                np.abs(result["tariff_bucket_signal"]).clip(0, 3) / 3 * 100
            )

        return result


# =============================================================================
# MASTER BUCKET CALCULATOR
# =============================================================================


class ZincFusionBucketIndicators:
    """
    Master class to compute all Big-11 specialist bucket indicators.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

    def compute_all_buckets(
        self,
        zs_df: Optional[pd.DataFrame] = None,
        zm_df: Optional[pd.DataFrame] = None,
        cl_df: Optional[pd.DataFrame] = None,
        ho_df: Optional[pd.DataFrame] = None,
        rb_df: Optional[pd.DataFrame] = None,
        hg_df: Optional[pd.DataFrame] = None,
        palm_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Compute indicators for all 11 specialist buckets.

        Returns DataFrame with all bucket indicators added.
        """
        result = self.df.copy()

        print("🎯 Computing Big-11 Specialist Bucket Indicators...")

        # 1. CRUSH Bucket
        print("   → CRUSH bucket...")
        if zs_df is not None and zm_df is not None:
            # Merge auxiliary data
            result = result.merge(
                zs_df[["trade_date", "close"]].rename(columns={"close": "zs_close"}),
                on="trade_date",
                how="left",
            )
            result = result.merge(
                zm_df[["trade_date", "close"]].rename(columns={"close": "zm_close"}),
                on="trade_date",
                how="left",
            )
        result = CrushBucketIndicators.compute_crush_indicators(result)

        # 2. CHINA Bucket
        print("   → CHINA bucket...")
        if hg_df is not None:
            result = result.merge(
                hg_df[["trade_date", "close"]].rename(columns={"close": "hg_close"}),
                on="trade_date",
                how="left",
            )
        result = ChinaBucketIndicators.compute_china_indicators(result)

        # 3. ENERGY Bucket
        print("   → ENERGY bucket...")
        if cl_df is not None:
            result = result.merge(
                cl_df[["trade_date", "close"]].rename(columns={"close": "cl_close"}),
                on="trade_date",
                how="left",
            )
        if ho_df is not None:
            result = result.merge(
                ho_df[["trade_date", "close"]].rename(columns={"close": "ho_close"}),
                on="trade_date",
                how="left",
            )
        if rb_df is not None:
            result = result.merge(
                rb_df[["trade_date", "close"]].rename(columns={"close": "rb_close"}),
                on="trade_date",
                how="left",
            )
        result = EnergyBucketIndicators.compute_energy_indicators(result)

        # 4. PALM Bucket
        print("   → PALM bucket...")
        if palm_df is not None:
            result = result.merge(
                palm_df[["trade_date", "close"]].rename(
                    columns={"close": "palm_oil_close"}
                ),
                on="trade_date",
                how="left",
            )
        result = PalmBucketIndicators.compute_palm_indicators(result)

        # 5. BIOFUEL Bucket
        print("   → BIOFUEL bucket...")
        result = BiofuelBucketIndicators.compute_biofuel_indicators(result)

        # 6. SUBSTITUTES Bucket
        print("   → SUBSTITUTES bucket...")
        result = SubstitutesBucketIndicators.compute_substitutes_indicators(result)

        # 7. FX Bucket
        print("   → FX bucket...")
        result = FXBucketIndicators.compute_fx_indicators(result)

        # 8. FED Bucket
        print("   → FED bucket...")
        result = FedBucketIndicators.compute_fed_indicators(result)

        # 9. VOLATILITY Bucket
        print("   → VOLATILITY bucket...")
        result = VolatilityBucketIndicators.compute_volatility_indicators(result)

        # 10. TARIFF Bucket
        print("   → TARIFF bucket...")
        result = TariffBucketIndicators.compute_tariff_indicators(result)

        # Summary
        bucket_cols = [
            c
            for c in result.columns
            if any(
                x in c.lower()
                for x in [
                    "crush",
                    "oil_share",
                    "zl_zs",
                    "zm_zs",
                    "hg_",
                    "china",
                    "boho",
                    "energy",
                    "cl_",
                    "crack",
                    "palm_",
                    "zl_palm",
                    "rin_",
                    "lcfs",
                    "canola",
                    "sunflower",
                    "substitut",
                    "dxy",
                    "brl",
                    "cny",
                    "fed_",
                    "yield_curve",
                    "nfci",
                    "vix",
                    "vol_",
                    "stlfsi",
                    "realized_vol",
                    "epu",
                    "trade_",
                    "tariff",
                ]
            )
        ]

        print(f"\n✅ Computed {len(bucket_cols)} specialist bucket indicators")

        return result

    def get_bucket_features(self) -> Dict[str, List[str]]:
        """Return dictionary of indicator columns by bucket."""
        cols = self.df.columns.tolist()

        return {
            "crush": [
                c
                for c in cols
                if any(
                    x in c.lower()
                    for x in ["crush", "oil_share", "zl_zs", "zm_zs", "zl_zm"]
                )
            ],
            "china": [
                c
                for c in cols
                if any(x in c.lower() for x in ["hg_", "china", "cny_zl"])
            ],
            "energy": [
                c
                for c in cols
                if any(
                    x in c.lower()
                    for x in ["cl_", "ho_", "rb_", "boho", "crack", "energy"]
                )
            ],
            "palm": [
                c
                for c in cols
                if any(
                    x in c.lower()
                    for x in ["palm_", "zl_palm", "palm_inv", "palm_prod"]
                )
            ],
            "biofuel": [
                c
                for c in cols
                if any(x in c.lower() for x in ["rin_", "lcfs", "biofuel"])
            ],
            "substitutes": [
                c
                for c in cols
                if any(
                    x in c.lower()
                    for x in [
                        "canola",
                        "sunflower",
                        "cottonseed",
                        "substitut",
                        "rapeseed",
                    ]
                )
            ],
            "fx": [
                c
                for c in cols
                if any(x in c.lower() for x in ["dxy", "brl", "dollar", "fx_"])
            ],
            "fed": [
                c
                for c in cols
                if any(
                    x in c.lower()
                    for x in ["fed_", "yield_curve", "nfci", "rate_", "financial_cond"]
                )
            ],
            "volatility": [
                c
                for c in cols
                if any(
                    x in c.lower() for x in ["vix", "vol_", "stlfsi", "realized_vol"]
                )
            ],
            "tariff": [
                c
                for c in cols
                if any(x in c.lower() for x in ["epu", "trade_", "tariff", "tension"])
            ],
        }


# =============================================================================
# MAIN - Test
# =============================================================================

if __name__ == "__main__":
    print("🚀 ZINC Fusion V15 Big-11 Specialist Bucket Indicators")
    print("=" * 60)

    # Show bucket configurations
    for bucket_name, config in BUCKET_CONFIGS.items():
        print(f"\n{config.name.upper()} Bucket:")
        print(f"   Primary features: {len(config.primary_features)}")
        print(f"   Secondary features: {len(config.secondary_features)}")
