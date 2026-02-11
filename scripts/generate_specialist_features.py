#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Generate DOMAIN-SPECIFIC Specialist Features

CRITICAL DISTINCTION FROM CORE:
- CORE uses ALL 800+ features → AutoGluon figures out what matters
- SPECIALISTS use HAND-PICKED features (20-50 per domain) → Expert curation

Each specialist receives ONLY the features relevant to their domain:
- CRUSH: board_crush, oil_share, ZL/ZS/ZM ratios, NOPA, CFTC positioning
- CHINA: copper (HG), USD/CNY, Dalian proxies, export sales to China
- FX: DXY, USD/BRL, USD/CNY, carry trades, real effective rates
- FED: Fed funds, yield curve, NFCI, real rates, credit spreads
- TARIFF: policy uncertainty, trade war sentiment, retaliatory risk
- ENERGY: CL, HO, crack spreads, BOHO spread, refinery margins
- BIOFUEL: D4/D6 RINs, LCFS credits, biodiesel production
- PALM: palm/soy ratio, Malaysia production/inventory, export levies
- VOLATILITY: VIX, OVX, soybean IV, skew, term structure
- SUBSTITUTES: canola, sunflower, rapeseed spreads vs ZL
- TRUMP_EFFECT: tariff regime, EPA waivers, MFP, election cycle

This is NOT all_data_policy - that's for CORE only.

Usage:
    python scripts/generate_specialist_features.py --dry-run
    python scripts/generate_specialist_features.py
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_batch

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import FRED routing module for v2 schema (7 econ.* tables)
# Option B: bucket-aware loading queries only 1-2 tables per specialist
from src.fusion.db.fred_routing import (
    build_specialist_query,
    get_specialist_series,
)

# ═══════════════════════════════════════════════════════════════════════════════
# SPECIALIST FEATURE POLICY (NOT ALL DATA!)
# ═══════════════════════════════════════════════════════════════════════════════
# SPECIALISTS get HAND-PICKED features per domain, NOT all 800+.
#
# - CORE model uses ALL DATA POLICY (800+ features, AutoGluon decides)
# - SPECIALISTS use DOMAIN-SPECIFIC features (20-50 each, expert curated)
#
# This is intentional. Each specialist is an expert in ONE thing.
# The domain-specific feature definitions are in SPECIALIST_FEATURE_CONFIGS below.
# ═══════════════════════════════════════════════════════════════════════════════

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv(".env.vercel")

# =============================================================================
# SPECIALIST FEATURE CONFIGURATIONS
# =============================================================================
# Each specialist gets HAND-PICKED features specific to their domain.
# This is the OPPOSITE of Core's all_data_policy.
#
# Feature counts per specialist: 20-50 (NOT 800+!)

SPECIALIST_FEATURE_CONFIGS = {
    # =========================================================================
    # CRUSH - Soybean complex fundamentals
    # =========================================================================
    # This is THE most important specialist. Crush dynamics drive ZL pricing.
    "crush": {
        "description": "Soybean complex fundamentals - board crush, oil share, ratios",
        "symbols": ["ZL", "ZM", "ZS"],  # Core soy complex only
        "primary_features": [
            # From specialist_buckets.py BUCKET_CONFIGS
            "board_crush",  # ZS*11 - ZL*11 - ZM (processing economics)
            "oil_share",  # ZL value / (ZL + ZM) - value split
            "zl_zs_ratio",  # SoyOil/Soybean ratio
            "zm_zs_ratio",  # SoyMeal/Soybean ratio
            "crush_margin",  # Crush profitability
            "nopa_crush_utilization",  # US processing capacity usage
            "cftc_zl_net_position",  # Speculative flows
        ],
        "secondary_features": [
            "canola_spread",  # ZL vs canola
            "sunflower_spread",  # ZL vs sunflower
            "rapeseed_spread",  # ZL vs rapeseed
            "argentina_crush",  # SA competition
            "brazil_crush",  # SA competition
            "crush_momentum_21d",  # Trend
        ],
        "derived_indicators": [
            # From CrushBucketIndicators class
            "crush_zscore",  # Z-score of board crush
            "oil_share_zscore",  # Z-score of oil share
            "crush_bb_pct",  # Bollinger band position
            "crush_squeeze_prob",  # Regime probability
            "crush_bucket_signal",  # Composite signal
            "crush_percentile",  # Historical percentile rank
        ],
        "fred_series": [],  # Crush is pure fundamentals, no macro
        "fx_pairs": ["USDBRL", "USDARS"],  # SA currency = crush competition
        "cot_symbols": ["ZL", "ZS", "ZM"],
        "include_rin": False,
        "include_trump_features": False,
        "expected_features": 40,
    },
    # =========================================================================
    # CHINA - Chinese import demand
    # =========================================================================
    # China buys 60%+ of global soybean trade. Copper = China demand proxy.
    "china": {
        "description": "Chinese import demand - copper proxy, CNY, trade flows",
        "symbols": ["ZL", "ZS", "HG"],  # Soybeans + copper (Dr. Copper)
        "primary_features": [
            "china_soy_imports",  # Actual import data
            "dalian_soy_close",  # Dalian soybean price
            "hg_close",  # Copper = China industrial proxy
            "shanghai_copper",  # Shanghai copper
            "usda_export_sales_china",  # US exports to China
            "china_crushing_margin",  # China processor profitability
        ],
        "secondary_features": [
            "china_pmi",  # Manufacturing PMI
            "china_gdp_proxy",  # GDP growth proxy
            "pork_hog_ratio",  # Protein demand cycle
            "china_inventory",  # Port stocks
            "brazil_premium",  # Brazil vs US pricing
            "usd_cny",  # Currency effect
        ],
        "derived_indicators": [
            # From ChinaBucketIndicators class
            "hg_zscore",  # Copper z-score
            "hg_momentum_21d",  # Copper momentum
            "hg_zl_corr_21d",  # Copper/ZL correlation
            "china_demand_regime",  # very_weak to very_strong
            "china_bucket_signal",  # Composite signal
            "cny_devalue_prob",  # CNY devaluation risk
        ],
        "fred_series": ["PCOPPUSDM"],  # FRED copper
        "fx_pairs": ["USDCNY"],  # Only CNY matters
        "cot_symbols": ["ZS", "ZL"],
        "include_usda_exports": True,
        "include_rin": False,
        "include_trump_features": False,
        "expected_features": 35,
    },
    # =========================================================================
    # ENERGY - Petroleum complex
    # =========================================================================
    # Biodiesel economics: SoyOil competes with Heating Oil.
    "energy": {
        "description": "Petroleum complex - crude, HO, crack spreads, BOHO",
        "symbols": ["ZL", "CL", "HO", "RB", "NG"],
        "primary_features": [
            "cl_close",  # WTI crude
            "ho_close",  # Heating oil (biodiesel substitute)
            "rb_close",  # Gasoline
            "ng_close",  # Natural gas
            "crack_spread_321",  # Refining margin
            "boho_spread",  # SoyOil - HO = biodiesel premium
        ],
        "secondary_features": [
            "brent_wti_spread",  # Crude arbitrage
            "gasoline_crack",  # RB-CL spread
            "diesel_crack",  # HO-CL spread
            "energy_inventory",  # DOE inventory
            "refinery_utilization",  # Refinery run rates
            "opec_spare_capacity",  # Supply buffer
        ],
        "derived_indicators": [
            # From EnergyBucketIndicators class
            "boho_zscore",  # BOHO z-score
            "boho_percentile",  # BOHO historical rank
            "cl_zscore",  # Crude z-score
            "crack_zscore",  # Crack spread z-score
            "energy_bucket_signal",  # Composite signal
            "zl_cl_corr_21d",  # ZL/Crude correlation
        ],
        "fred_series": ["DCOILWTICO", "DCOILBRENTEU"],
        "fx_pairs": [],  # Energy not FX sensitive
        "cot_symbols": ["ZL", "CL"],
        "include_rin": False,
        "include_trump_features": False,
        "expected_features": 40,
    },
    # =========================================================================
    # PALM - Palm oil complex
    # =========================================================================
    # Palm is the world's largest vegetable oil. ZL competes with palm.
    "palm": {
        "description": "Palm oil complex - Malaysia/Indonesia production & spreads",
        "symbols": ["ZL", "CPO"],  # CPO = Crude Palm Oil (3,767 rows from 2010-2025)
        "primary_features": [
            "palm_oil_close",  # BMD palm close
            "palm_oil_front",  # Front month
            "zl_palm_spread",  # ZL - Palm absolute
            "zl_palm_ratio",  # ZL/Palm ratio
            "palm_production_malaysia",  # Production data
            "palm_inventory_malaysia",  # MPOB inventory
        ],
        "secondary_features": [
            "palm_export_levy_indonesia",  # Indo levy
            "palm_export_levy_malaysia",  # Malaysia levy
            "indonesia_export_policy",  # DMO/DPO policy
            "palm_biodiesel_mandate",  # B30/B35 mandate
            "el_nino_index",  # Weather impact
            "la_nina_index",  # Weather impact
        ],
        "derived_indicators": [
            # From PalmBucketIndicators class
            "zl_palm_zscore",  # Spread z-score
            "palm_inventory_zscore",  # Inventory vs history
            "palm_regime",  # premium/discount/parity
            "palm_bucket_signal",  # Composite signal
        ],
        "fred_series": [],  # No relevant FRED series
        "fx_pairs": ["USDMYR", "USDIDR"],  # Ringgit & Rupiah
        "cot_symbols": ["ZL"],
        "include_rin": False,
        "include_trump_features": False,
        "include_weather": True,  # El Nino affects palm yields
        "expected_features": 30,
    },
    # =========================================================================
    # BIOFUEL - Renewable mandates
    # =========================================================================
    # RFS/LCFS mandates drive soybean oil demand for biodiesel.
    "biofuel": {
        "description": "Renewable mandates - RINs, LCFS, biodiesel/RD capacity",
        "symbols": ["ZL", "CL", "HO"],
        "primary_features": [
            "rin_d4_price",  # D4 biodiesel RIN
            "rin_d6_price",  # D6 ethanol RIN
            "lcfs_credit",  # California carbon credit
            "rfs_mandate_level",  # Federal mandate volume
            "biodiesel_production",  # Monthly production
            "renewable_diesel_capacity",  # RD nameplate capacity
        ],
        "secondary_features": [
            "sbo_biodiesel_pct",  # SBO share of feedstock
            "epa_waivers",  # Small refinery exemptions
            "saf_demand",  # Sustainable aviation fuel
            "carbon_credit_price",  # Global carbon
            "blender_tax_credit",  # $1/gal blender tax credit status
            "e15_waiver_status",  # E15 summer status
        ],
        "derived_indicators": [
            # From BiofuelBucketIndicators class
            "rin_d4_zscore",  # D4 z-score
            "rin_d4_percentile",  # D4 historical rank
            "rin_d4_d6_spread",  # D4-D6 spread
            "rin_regime",  # weak/neutral/strong
            "biofuel_bucket_signal",  # Composite signal
            "lcfs_zscore",  # LCFS z-score
        ],
        "fred_series": [],  # RINs ARE the signal
        "fx_pairs": [],
        "cot_symbols": ["ZL"],
        "include_rin": True,  # Core to this specialist
        "include_trump_features": True,  # EPA waivers = Trump policy
        "expected_features": 35,
    },
    # =========================================================================
    # FX - Currency effects on trade
    # =========================================================================
    # Dollar strength affects commodity pricing, BRL/CNY affect trade flows.
    "fx": {
        "description": "Currency effects - dollar, EM currencies, carry trades",
        "symbols": ["ZL", "DX"],
        "primary_features": [
            "dxy",  # Dollar index
            "usd_brl",  # Brazil Real
            "usd_cny",  # Chinese Yuan
            "usd_ars",  # Argentine Peso
            "fx_volatility",  # Currency vol
            "em_currency_index",  # EM FX composite
        ],
        "secondary_features": [
            "eur_usd",  # Euro cross
            "real_effective_rate",  # Real exchange rate
            "carry_trade_index",  # Risk appetite
            "fx_intervention_risk",  # Central bank action
            "current_account_balance",  # Trade balance
            "terms_of_trade",  # Export prices
        ],
        "derived_indicators": [
            "dxy_zscore",  # Dollar z-score
            "brl_devalue_prob",  # BRL stress
            "cny_devalue_prob",  # CNY devalue risk
            "fx_bucket_signal",  # Composite signal
        ],
        "fred_series": ["DTWEXBGS"],  # Trade-weighted dollar
        "fx_pairs": ["EURUSD", "USDJPY", "USDBRL", "USDCNY", "USDARS"],
        "cot_symbols": ["ZL"],
        "include_rin": False,
        "include_trump_features": False,
        "expected_features": 30,
    },
    # =========================================================================
    # FED - Monetary policy impacts
    # =========================================================================
    # Rate policy affects commodity carry, financial conditions affect risk appetite.
    "fed": {
        "description": "Monetary policy - rates, yield curve, financial conditions",
        "symbols": ["ZL", "ZN", "ZB"],
        "primary_features": [
            "fed_funds_rate",  # Effective FF rate
            "fed_funds_target",  # FOMC target
            "t10y2y",  # Yield curve slope
            "real_rates",  # Real interest rates
            "nfci",  # Financial conditions
            "financial_conditions_index",  # Chicago Fed FCI
        ],
        "secondary_features": [
            "fed_balance_sheet",  # Fed assets
            "qe_pace",  # QE/QT monthly pace
            "fomc_dots",  # Fed projections
            "market_fed_expectations",  # Fed funds futures
            "inflation_breakevens",  # TIPS spread
            "tips_spreads",  # Real yield spreads
            "credit_spreads",  # HY-IG spread
        ],
        "derived_indicators": [
            "yield_curve_regime",  # Inverted/flat/steep
            "financial_stress_zscore",  # NFCI z-score
            "fed_bucket_signal",  # Composite signal
        ],
        "fred_series": ["FEDFUNDS", "DGS10", "DGS2", "T10Y2Y", "NFCI"],
        "fx_pairs": ["EURUSD"],  # Dollar response to Fed
        "cot_symbols": ["ZL"],
        "include_rin": False,
        "include_trump_features": False,
        "expected_features": 30,
    },
    # =========================================================================
    # TARIFF - Trade policy impacts
    # =========================================================================
    # Trade war regime, policy uncertainty, retaliation risk.
    "tariff": {
        "description": "Trade policy - tariffs, uncertainty, retaliation risk",
        "symbols": ["ZL", "ZS", "ZM"],
        "primary_features": [
            "effective_tariff_rate",  # Actual tariff rate
            "trade_war_sentiment",  # News sentiment
            "policy_uncertainty_index",  # EPU index
            "china_tariff_rate",  # China retaliatory tariff
            "retaliatory_tariff_risk",  # Risk score
        ],
        "secondary_features": [
            "trade_negotiation_score",  # Deal probability
            "diplomatic_sentiment",  # Diplomatic relations
            "news_volume",  # Trade news frequency
            "trump_trade_tweets",  # Tweet volume
            "section_301_risk",  # IP investigation risk
            "wto_dispute_count",  # WTO cases
        ],
        "derived_indicators": [
            "trade_war_regime",  # -5 to +5 scale
            "tariff_bucket_signal",  # Composite signal
            "policy_uncertainty_zscore",
        ],
        "fred_series": ["USEPUINDXM"],  # Policy Uncertainty
        "fx_pairs": ["USDCNY", "USDBRL"],
        "cot_symbols": ["ZL", "ZS"],
        "include_rin": False,
        "include_trump_features": True,  # Tariff = Trump regime
        "expected_features": 30,
    },
    # =========================================================================
    # VOLATILITY - Market stress/fear
    # =========================================================================
    # VIX, realized vol, term structure, correlation breakdown.
    "volatility": {
        "description": "Market stress - VIX, vol surfaces, correlation, skew",
        "symbols": ["ZL", "ES", "VX"],
        "primary_features": [
            "vix",  # VIX index (VIXCLS)
            "ovx",  # Oil VIX (OVXCLS)
            "stress_index",  # Financial Stress (STLFSI4)
            "realized_vol_20d",  # 20d realized vol
            "vol_risk_premium",  # IV - RV
        ],
        "secondary_features": [
            "skew_index",  # Put skew
            "put_call_ratio",  # Options sentiment
            "vvix",  # Vol of vol
            "correlation_index",  # Asset correlation
        ],
        "derived_indicators": [
            "vix_zscore",  # VIX z-score
            "ovx_zscore",  # OVX z-score
            "vix_regime",  # low/normal/high/crisis
            "vol_bucket_signal",  # Composite signal
        ],
        "fred_series": ["VIXCLS", "OVXCLS", "STLFSI4"],  # VIX + Oil VIX + Stress Index
        "fx_pairs": [],  # Vol not FX sensitive
        "cot_symbols": ["ZL"],
        "include_rin": False,
        "include_trump_features": False,
        "expected_features": 40,
    },
    # =========================================================================
    # SUBSTITUTES - Competing vegetable oils
    # =========================================================================
    # Canola, sunflower, rapeseed compete with soybean oil.
    "substitutes": {
        "description": "Competing oils - canola, sunflower, rapeseed spreads",
        "symbols": ["ZL", "RS"],  # RS = Canola (ICE) - 3,575 rows from 2011
        "primary_features": [
            "canola_close",  # ICE Canola (RS)
            "sunflower_close",  # FRED PSUNOUSDM
            "zl_canola_spread",  # ZL - Canola
            "zl_sunflower_spread",  # ZL - Sunflower
        ],
        "secondary_features": [
            "eu_rapeseed_production",  # EU production
            "black_sea_sunflower",  # Ukraine/Russia
            "canola_crush_canada",  # Canada crush
        ],
        "derived_indicators": [
            "zl_canola_zscore",  # Spread z-score
            "zl_sunflower_zscore",  # Spread z-score
            "substitutes_bucket_signal",  # Composite
        ],
        "fred_series": ["PSUNOUSDM"],  # Sunflower Oil Price (427 rows from 1990)
        "fx_pairs": ["USDCAD", "EURUSD"],  # Canola/Rapeseed currencies
        "cot_symbols": ["ZL"],
        "include_rin": False,
        "include_trump_features": False,
        "expected_features": 35,
    },
    # =========================================================================
    # TRUMP_EFFECT (variable weight) - Policy regime dynamics
    # =========================================================================
    # Trump is a REGIME: tariffs + EPA waivers + MFP + tweets.
    "trump_effect": {
        "description": "Trump/policy regime - tariffs, EPA waivers, MFP, WhiteHouse actions",
        "symbols": ["ZL", "ZS", "HG", "ES", "DX"],
        "primary_features": [
            # Binary regime flags
            "trump_in_office",  # Is Trump president
            "trump_transition",  # 60-day inauguration window
            "china_tariff_active",  # 25% tariff on soybeans
            "phase_one_active",  # Trade deal in effect
            "mfp_active",  # MFP payments active
            # WhiteHouse action counts
            "wh_eo_count",  # Executive orders
            "wh_trade_related",  # Trade-related actions
            "wh_ag_related",  # Agriculture-related actions
        ],
        "secondary_features": [
            # Continuous regime scores
            "policy_uncertainty",  # USEPUINDXD
            "trade_policy_uncertainty",  # EPUTRADE
            "trump_regime_score",  # Composite score
            "days_to_election",  # Election cycle
        ],
        "derived_indicators": [
            "policy_uncertainty_zscore",  # Uncertainty z-score
            "trump_bucket_signal",  # Composite signal
        ],
        "fred_series": [
            "VIXCLS",
            "T10Y2Y",
            "USEPUINDXD",
            "EPUTRADE",
        ],  # Policy uncertainty
        "fx_pairs": ["USDCNY", "USDBRL", "USDMXN"],
        "cot_symbols": ["ZL", "ZS"],
        "include_rin": True,  # EPA waivers affect RINs
        "include_trump_features": True,
        "expected_features": 60,
    },
}

# Legacy alias for backwards compatibility
SPECIALIST_BUCKETS = SPECIALIST_FEATURE_CONFIGS


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def load_all_market_data(conn, start_date: str = "2000-01-01") -> pd.DataFrame:
    """Load all daily market futures data."""
    logger.info(f"Loading daily market futures >= {start_date}...")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT symbol, event_date AS as_of_date, open, high, low, close, volume
            FROM "mkt"."futures_1d"
            WHERE event_date >= %s
            ORDER BY event_date, symbol
        """,
            (start_date,),
        )
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=columns)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    logger.info(f"  Loaded {len(df):,} rows, {df['symbol'].nunique()} symbols")
    return df


# NOTE: The following functions were removed (2026-01-23) as dead code:
# - load_market_data_by_tags(): Referenced deleted specialist_tags column
# - load_fred_data_by_tags(): Referenced deleted econ fred observations table
#
# The v2 schema uses:
# - Bucket configs with curated "symbols" lists (not tags)
# - 7 domain-specific econ.* tables routed via fred_routing.py


def load_fred_data(conn) -> pd.DataFrame:
    """Load FRED economic data (long format → pivot wide).

    Post-v2 migration: FRED data is now split across 7 econ.* tables.
    We UNION ALL from all tables to reconstruct the unified view.

    NOTE: Some series may exist in multiple tables (routing mismatch during migration).
    We use pivot_table with aggfunc='last' to handle duplicates gracefully.
    """
    logger.info("Loading FRED economic data (long → pivot wide)...")
    logger.info("  Querying all 7 econ.* tables (v2 split schema)...")

    # Load long format from all 7 split tables
    fred_long = pd.read_sql(
        """
        SELECT event_date AS as_of_date, series_id, value FROM econ.rates_1d
        UNION ALL
        SELECT event_date AS as_of_date, series_id, value FROM econ.activity_1d
        UNION ALL
        SELECT event_date AS as_of_date, series_id, value FROM econ.inflation_1d
        UNION ALL
        SELECT event_date AS as_of_date, series_id, value FROM econ.labor_1d
        UNION ALL
        SELECT event_date AS as_of_date, series_id, value FROM econ.money_1d
        UNION ALL
        SELECT event_date AS as_of_date, series_id, value FROM econ.vol_indices_1d
        UNION ALL
        SELECT event_date AS as_of_date, series_id, value FROM econ.commodities_1d
        ORDER BY as_of_date, series_id
    """,
        conn,
    )
    logger.info(
        f"  Long format: {len(fred_long):,} rows, {fred_long['series_id'].nunique()} series"
    )

    if fred_long.empty:
        raise ValueError("FRED query returned 0 rows - check econ.* tables")

    # Check for duplicates and warn
    dup_check = fred_long.groupby(["as_of_date", "series_id"]).size()
    dups = dup_check[dup_check > 1]
    if len(dups) > 0:
        dup_series = dups.reset_index()["series_id"].unique()
        logger.warning(
            f"  ⚠️ Found {len(dups):,} duplicate (date, series) pairs across tables"
        )
        logger.warning(f"     Affected series: {', '.join(list(dup_series)[:10])}...")
        logger.warning("     Using pivot_table with aggfunc='last' to dedupe")

    # Pivot to wide format using pivot_table (handles duplicates)
    df = (
        fred_long.pivot_table(
            index="as_of_date",
            columns="series_id",
            values="value",
            aggfunc="last",  # If duplicate (date, series), take last value
        )
        .sort_index()
        .reset_index()
    )
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])

    # Warn on high sparsity
    feature_cols = [c for c in df.columns if c != "as_of_date"]
    missing_frac = df[feature_cols].isna().mean().mean()
    if missing_frac > 0.50:
        logger.warning(f"  ⚠️ FRED pivot has high missingness: {missing_frac:.1%}")

    logger.info(f"  Wide format: {len(df):,} rows, {len(feature_cols)} FRED features")
    return df


def load_fred_data_for_bucket(conn, bucket_name: str) -> pd.DataFrame:
    """Load FRED data for a SPECIFIC specialist bucket (Option B: bucket-aware routing).

    Instead of querying all 7 econ.* tables, this function uses build_specialist_query()
    to query only the 1-2 tables that contain series relevant to this bucket.

    Benefits:
    - Volatility bucket: 1 table (econ.vol_indices_1d), 3 series
    - Fed bucket: 2 tables (econ.rates_1d, econ.vol_indices_1d), 5 series
    - Crush/Palm/Biofuel: 0 tables (no FRED data, use fundamentals)

    Args:
        conn: Database connection
        bucket_name: Specialist bucket name (e.g., "volatility", "fed", "crush")

    Returns:
        DataFrame with as_of_date + series columns (wide format), or empty DataFrame
        if the bucket doesn't use FRED data.
    """
    # Get the series this bucket uses
    series_list = get_specialist_series(bucket_name)
    if not series_list:
        logger.info(f"  [{bucket_name}] No FRED series (using fundamentals only)")
        return pd.DataFrame(columns=["as_of_date"])

    # Build the optimized query for this bucket
    query = build_specialist_query(bucket_name)
    if not query:
        logger.info(f"  [{bucket_name}] No FRED query (bucket uses no FRED data)")
        return pd.DataFrame(columns=["as_of_date"])

    logger.info(
        f"  [{bucket_name}] Loading {len(series_list)} FRED series: {', '.join(series_list)}"
    )

    # Execute bucket-specific query (1-2 tables, not 7!)
    fred_long = pd.read_sql(query, conn)

    if fred_long.empty:
        logger.warning(f"  [{bucket_name}] FRED query returned 0 rows")
        return pd.DataFrame(columns=["as_of_date"])

    logger.info(f"    Long format: {len(fred_long):,} rows")

    # Pivot to wide format
    df = (
        fred_long.pivot_table(
            index="as_of_date", columns="series_id", values="value", aggfunc="last"
        )
        .sort_index()
        .reset_index()
    )
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])

    logger.info(f"    Wide format: {len(df):,} rows, {len(df.columns) - 1} columns")
    return df


def load_fx_data(conn) -> pd.DataFrame:
    """Load FX spot data and pivot wide."""
    logger.info("Loading FX spot data...")
    with conn.cursor() as cur:
        cur.execute(
            'SELECT pair, event_date AS as_of_date, rate FROM "mkt"."fx_1d" ORDER BY event_date'
        )
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["pair", "as_of_date", "rate"])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    # Pivot wide
    df_wide = df.pivot_table(
        index="as_of_date", columns="pair", values="rate", aggfunc="last"
    )
    df_wide.columns = [f"fx_{c}" for c in df_wide.columns]
    df_wide = df_wide.reset_index()
    logger.info(f"  Loaded {len(df_wide):,} dates, {len(df_wide.columns) - 1} FX pairs")
    return df_wide


def load_cot_data(conn) -> pd.DataFrame:
    """Load CFTC COT data and pivot wide by symbol."""
    logger.info("Loading CFTC COT data...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT event_date AS as_of_date, symbol, open_interest, managed_money_net,
                   managed_money_net_pct_oi, prod_merc_net, prod_merc_net_pct_oi
            FROM "pos"."cftc_1w"
            ORDER BY event_date, symbol
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(
        rows,
        columns=[
            "as_of_date",
            "symbol",
            "oi",
            "mm_net",
            "mm_pct",
            "prod_net",
            "prod_pct",
        ],
    )
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])

    # Pivot by symbol
    result_dfs = []
    for sym in df["symbol"].unique():
        sym_df = df[df["symbol"] == sym][
            ["as_of_date", "oi", "mm_net", "mm_pct", "prod_net", "prod_pct"]
        ].copy()
        sym_df.columns = ["as_of_date"] + [
            f"cot_{sym}_{c}" for c in ["oi", "mm_net", "mm_pct", "prod_net", "prod_pct"]
        ]
        result_dfs.append(sym_df)

    if result_dfs:
        cot_wide = result_dfs[0]
        for df_r in result_dfs[1:]:
            cot_wide = cot_wide.merge(df_r, on="as_of_date", how="outer")
    else:
        cot_wide = pd.DataFrame(columns=["as_of_date"])

    logger.info(
        f"  Loaded {len(cot_wide):,} dates, {len(cot_wide.columns) - 1} COT features"
    )
    return cot_wide


def load_usda_exports(conn) -> pd.DataFrame:
    """Load USDA export sales data."""
    logger.info("Loading USDA export sales...")
    with conn.cursor() as cur:
        cur.execute("""
            WITH per_commodity AS (
                SELECT
                    event_date AS as_of_date,
                    commodity,
                    COALESCE(
                        MAX(CASE WHEN destination_country = 'TOTAL' THEN net_sales_mt END),
                        SUM(net_sales_mt)
                    ) AS net_sales_mt,
                    COALESCE(
                        MAX(CASE WHEN destination_country = 'TOTAL' THEN exports_mt END),
                        SUM(exports_mt)
                    ) AS exports_mt
                FROM "supply"."usda_exports_1w"
                GROUP BY event_date, commodity
            )
            SELECT as_of_date,
                MAX(CASE WHEN commodity = 'Soybeans' THEN net_sales_mt END) as usda_soy_net_sales,
                MAX(CASE WHEN commodity = 'Soybeans' THEN exports_mt END) as usda_soy_exports,
                MAX(CASE WHEN commodity = 'Soybean Oil' THEN net_sales_mt END) as usda_zl_net_sales,
                MAX(CASE WHEN commodity = 'Soybean Oil' THEN exports_mt END) as usda_zl_exports,
                MAX(CASE WHEN commodity = 'Soybean Meal' THEN net_sales_mt END) as usda_zm_net_sales
            FROM per_commodity
            GROUP BY as_of_date
            ORDER BY as_of_date
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(
        rows,
        columns=[
            "as_of_date",
            "usda_soy_net_sales",
            "usda_soy_exports",
            "usda_zl_net_sales",
            "usda_zl_exports",
            "usda_zm_net_sales",
        ],
    )
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    logger.info(f"  Loaded {len(df):,} dates")
    return df


def load_wasde_data(conn) -> pd.DataFrame:
    """Load USDA WASDE data."""
    logger.info("Loading USDA WASDE data...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT event_date AS as_of_date,
                SUM(CASE WHEN commodity = 'Soybeans' AND metric = 'production' THEN value END) as wasde_soy_production,
                SUM(CASE WHEN commodity = 'Soybeans' AND metric = 'exports' THEN value END) as wasde_soy_exports,
                SUM(CASE WHEN commodity = 'Soybeans' AND metric = 'ending_stocks' THEN value END) as wasde_soy_stocks,
                SUM(CASE WHEN commodity = 'Soybean Oil' AND metric = 'production' THEN value END) as wasde_zl_production,
                SUM(CASE WHEN commodity = 'Soybean Oil' AND metric = 'exports' THEN value END) as wasde_zl_exports
            FROM "supply"."usda_wasde_1m"
            GROUP BY event_date
            ORDER BY event_date
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(
        rows,
        columns=[
            "as_of_date",
            "wasde_soy_production",
            "wasde_soy_exports",
            "wasde_soy_stocks",
            "wasde_zl_production",
            "wasde_zl_exports",
        ],
    )
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    logger.info(f"  Loaded {len(df):,} dates")
    return df


def load_rin_data(conn) -> pd.DataFrame:
    """Load EPA RIN data."""
    logger.info("Loading EPA RIN data...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT event_date AS as_of_date, rin_type, price
            FROM (
                SELECT DISTINCT ON (event_date, rin_type)
                    event_date, rin_type, price, source, ingested_at
                FROM "supply"."epa_rin_1d"
                ORDER BY
                    event_date,
                    rin_type,
                    CASE source
                        WHEN 'epa_qlik_public' THEN 0
                        WHEN 'epa_api' THEN 1
                        ELSE 2
                    END,
                    ingested_at DESC
            ) t
            ORDER BY event_date
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["as_of_date", "rin_type", "price"])
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    # Pivot by RIN type
    df_wide = df.pivot_table(
        index="as_of_date", columns="rin_type", values="price", aggfunc="last"
    )
    df_wide.columns = [f"rin_{c}" for c in df_wide.columns]
    df_wide = df_wide.reset_index()
    logger.info(
        f"  Loaded {len(df_wide):,} dates, {len(df_wide.columns) - 1} RIN types"
    )
    return df_wide


def load_weather_data(conn) -> pd.DataFrame:
    """Load NOAA weather data aggregated by date.

    Note: rhav_pct, awnd_ms, snwd_mm, evap_mm, wsfg_ms columns were dropped
    from alt.weather_1d (100% NULL values).
    """
    logger.info("Loading weather data...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT event_date AS as_of_date,
                -- Core temperature & precipitation
                AVG(tavg_c) as weather_tavg_global,
                AVG(prcp_mm) as weather_prcp_global,
                AVG(CASE WHEN country = 'Brazil' THEN tavg_c END) as weather_tavg_brazil,
                AVG(CASE WHEN country = 'Brazil' THEN prcp_mm END) as weather_prcp_brazil,
                AVG(CASE WHEN country = 'United States' THEN tavg_c END) as weather_tavg_us,
                AVG(CASE WHEN country = 'United States' THEN prcp_mm END) as weather_prcp_us,
                AVG(CASE WHEN country = 'Argentina' THEN tavg_c END) as weather_tavg_argentina,
                AVG(CASE WHEN country = 'Argentina' THEN prcp_mm END) as weather_prcp_argentina,
                -- Snow (only useful for US midwest)
                AVG(CASE WHEN country = 'United States' THEN snow_mm END) as weather_snow_us
            FROM "alt"."weather_1d"
            GROUP BY event_date
            ORDER BY event_date
        """)
        rows = cur.fetchall()

    columns = [
        "as_of_date",
        "weather_tavg_global",
        "weather_prcp_global",
        "weather_tavg_brazil",
        "weather_prcp_brazil",
        "weather_tavg_us",
        "weather_prcp_us",
        "weather_tavg_argentina",
        "weather_prcp_argentina",
        "weather_snow_us",
    ]
    df = pd.DataFrame(rows, columns=columns)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    logger.info(f"  Loaded {len(df):,} dates with {len(columns) - 1} weather features")
    return df


def add_weather_staleness(
    df: pd.DataFrame, time_col: str = "as_of_date"
) -> pd.DataFrame:
    """
    Add *_age_days columns for sparse weather variables.
    Tracks days since last fresh (non-null) observation.
    Must be called BEFORE forward-fill.
    """
    sparse_cols = [
        "weather_humidity_global",
        "weather_evap_global",
        "weather_snow_depth_global",
        "weather_max_gust_global",
    ]

    t = pd.to_datetime(df[time_col])

    for col in sparse_cols:
        if col not in df.columns:
            continue

        fresh = df[col].notna()
        last_fresh_time = t.where(fresh).ffill()
        age = (t - last_fresh_time).dt.total_seconds() / 86400.0
        df[f"{col}_age_days"] = age.fillna(0.0)

    return df


def load_news_data(conn) -> pd.DataFrame:
    """Load news sentiment data aggregated by date (legacy - global aggregate).

    MIGRATED: Previously read from the monolithic news table (deleted).
    Now unions alt.policy_news, alt.executive_actions, alt.econ_news, alt.profarmer_news.
    Note: This global aggregate is NOT used by generate_bucket_features (which uses
    news_by_bucket instead). Kept for backward compatibility.
    """
    logger.info("Loading news sentiment (global, union of alt news tables)...")
    with conn.cursor() as cur:
        cur.execute("""
            WITH all_news AS (
                SELECT event_date, zl_sentiment FROM alt.policy_news
                UNION ALL
                SELECT event_date, zl_sentiment FROM alt.executive_actions
                UNION ALL
                SELECT event_date, NULL as zl_sentiment FROM alt.econ_news
                UNION ALL
                SELECT event_date, NULL as zl_sentiment FROM alt.profarmer_news
            )
            SELECT event_date AS as_of_date,
                COUNT(*) as news_article_count,
                SUM(CASE WHEN zl_sentiment = 'bullish' THEN 1 ELSE 0 END) as news_bullish_count,
                SUM(CASE WHEN zl_sentiment = 'bearish' THEN 1 ELSE 0 END) as news_bearish_count
            FROM all_news
            WHERE event_date IS NOT NULL
            GROUP BY event_date
            ORDER BY event_date
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(
        rows,
        columns=[
            "as_of_date",
            "news_article_count",
            "news_bullish_count",
            "news_bearish_count",
        ],
    )
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    logger.info(f"  Loaded {len(df):,} dates")
    return df


def load_news_sentiment_by_bucket(conn) -> dict[str, pd.DataFrame]:
    """
    Load BUCKET-SPECIFIC news sentiment from alt news tables via specialist_tags.

    MIGRATED: Previously read from the features news sentiment table (deleted).
    Now aggregates directly from alt.policy_news, alt.executive_actions,
    alt.econ_news, alt.profarmer_news using specialist_tags[] routing.

    Returns a dict of {bucket_name: DataFrame} with aggregated sentiment features.
    """
    logger.info(
        "Loading bucket-specific news sentiment from alt news tables (specialist_tags routing)..."
    )

    # All 11 buckets
    buckets = [
        "crush",
        "china",
        "fx",
        "fed",
        "tariff",
        "energy",
        "biofuel",
        "palm",
        "volatility",
        "substitutes",
        "trump_effect",
    ]

    result = {}

    for bucket in buckets:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH all_tagged_news AS (
                    SELECT event_date, zl_sentiment, specialist_tags
                    FROM alt.policy_news WHERE %s = ANY(specialist_tags)
                    UNION ALL
                    SELECT event_date, zl_sentiment, specialist_tags
                    FROM alt.executive_actions WHERE %s = ANY(specialist_tags)
                    UNION ALL
                    SELECT event_date, NULL as zl_sentiment, specialist_tags
                    FROM alt.econ_news WHERE %s = ANY(specialist_tags)
                    UNION ALL
                    SELECT event_date, NULL as zl_sentiment, specialist_tags
                    FROM alt.profarmer_news WHERE %s = ANY(specialist_tags)
                )
                SELECT
                    event_date AS as_of_date,
                    COUNT(*) as {bucket}_news_count,
                    AVG(CASE
                        WHEN zl_sentiment = 'bullish' THEN 1.0
                        WHEN zl_sentiment = 'bearish' THEN -1.0
                        ELSE 0.0
                    END) as {bucket}_news_sentiment_avg
                FROM all_tagged_news
                WHERE event_date IS NOT NULL
                GROUP BY event_date
                ORDER BY event_date
            """,
                (bucket, bucket, bucket, bucket),
            )
            rows = cur.fetchall()

        columns = [
            "as_of_date",
            f"{bucket}_news_count",
            f"{bucket}_news_sentiment_avg",
        ]

        df = pd.DataFrame(rows, columns=columns)
        if not df.empty:
            df["as_of_date"] = pd.to_datetime(df["as_of_date"])

        result[bucket] = df
        logger.info(f"    {bucket}: {len(df):,} dates with news")

    return result


def load_whitehouse_actions(conn) -> pd.DataFrame:
    """
    Load WhiteHouse actions for trump_effect bucket.

    Aggregates executive orders, proclamations, memoranda by date.
    Returns features like action counts, EO counts, trade-related actions.
    """
    logger.info("Loading WhiteHouse actions...")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                event_date AS as_of_date,
                COUNT(*) as wh_action_count,
                SUM(CASE WHEN document_type = 'executive_order' THEN 1 ELSE 0 END) as wh_eo_count,
                SUM(CASE WHEN document_type = 'proclamation' THEN 1 ELSE 0 END) as wh_proclamation_count,
                SUM(CASE WHEN document_type = 'memorandum' THEN 1 ELSE 0 END) as wh_memo_count,
                SUM(CASE WHEN LOWER(title) LIKE '%tariff%' OR LOWER(title) LIKE '%trade%' THEN 1 ELSE 0 END) as wh_trade_related,
                SUM(CASE WHEN LOWER(title) LIKE '%china%' OR LOWER(title) LIKE '%chinese%' THEN 1 ELSE 0 END) as wh_china_related,
                SUM(CASE WHEN LOWER(title) LIKE '%soybean%' OR LOWER(title) LIKE '%agricult%' OR LOWER(title) LIKE '%farm%' THEN 1 ELSE 0 END) as wh_ag_related,
                SUM(CASE WHEN LOWER(title) LIKE '%energy%' OR LOWER(title) LIKE '%oil%' OR LOWER(title) LIKE '%fuel%' THEN 1 ELSE 0 END) as wh_energy_related
            FROM alt.legislation_1d
            GROUP BY event_date
            ORDER BY event_date
        """)
        rows = cur.fetchall()

    columns = [
        "as_of_date",
        "wh_action_count",
        "wh_eo_count",
        "wh_proclamation_count",
        "wh_memo_count",
        "wh_trade_related",
        "wh_china_related",
        "wh_ag_related",
        "wh_energy_related",
    ]

    df = pd.DataFrame(rows, columns=columns)
    if not df.empty:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"])
        # Add rolling counts
        df["wh_eo_count_7d"] = df["wh_eo_count"].rolling(7).sum()
        df["wh_eo_count_30d"] = df["wh_eo_count"].rolling(30).sum()
        df["wh_trade_intensity_30d"] = df["wh_trade_related"].rolling(30).sum()

    logger.info(f"  Loaded {len(df):,} dates with WhiteHouse actions")
    return df


def calculate_technical_indicators(
    df: pd.DataFrame, price_col: str = "close"
) -> pd.DataFrame:
    """Calculate technical indicators for a price series."""
    result = df.copy()

    # Returns
    result["return_1d"] = result[price_col].pct_change(1)
    result["return_5d"] = result[price_col].pct_change(5)
    result["return_21d"] = result[price_col].pct_change(21)

    # Simple Moving Averages
    result["sma_5"] = result[price_col].rolling(5).mean()
    result["sma_21"] = result[price_col].rolling(21).mean()
    result["sma_63"] = result[price_col].rolling(63).mean()

    # Exponential Moving Averages
    result["ema_12"] = result[price_col].ewm(span=12).mean()
    result["ema_26"] = result[price_col].ewm(span=26).mean()

    # MACD
    result["macd"] = result["ema_12"] - result["ema_26"]
    result["macd_signal"] = result["macd"].ewm(span=9).mean()

    # RSI (14-day)
    delta = result[price_col].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    result["rsi_14"] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    result["bb_middle"] = result[price_col].rolling(20).mean()
    bb_std = result[price_col].rolling(20).std()
    result["bb_upper"] = result["bb_middle"] + 2 * bb_std
    result["bb_lower"] = result["bb_middle"] - 2 * bb_std
    result["bb_pct"] = (result[price_col] - result["bb_lower"]) / (
        result["bb_upper"] - result["bb_lower"]
    )

    # Volatility
    result["volatility_21d"] = result["return_1d"].rolling(21).std() * np.sqrt(252)

    # Price relative to SMAs
    result["price_vs_sma21"] = result[price_col] / result["sma_21"] - 1
    result["price_vs_sma63"] = result[price_col] / result["sma_63"] - 1

    return result


def add_trump_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add Trump regime-specific features.

    Trump is a REGIME - the combination of policies creates unique dynamics:
    - Section 301 tariffs + China retaliation
    - EPA small refinery waivers (crushed biodiesel demand)
    - MFP payments (artificial price floor)
    - Tweet-driven volatility
    - Policy unpredictability

    Training uses Trump 1.0 (2017-2021) to predict Trump 2.0 (2025+)
    """
    df = df.copy()

    # Convert as_of_date to datetime for comparisons
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])

    # ==========================================================================
    # 1. BINARY FLAGS - Is Trump in office?
    # ==========================================================================
    # Trump 1.0: 2017-01-20 to 2021-01-20
    # Trump 2.0: 2025-01-20 onwards
    trump_1_start = pd.Timestamp("2017-01-20")
    trump_1_end = pd.Timestamp("2021-01-20")
    trump_2_start = pd.Timestamp("2025-01-20")

    df["trump_in_office"] = (
        ((df["as_of_date"] >= trump_1_start) & (df["as_of_date"] < trump_1_end))
        | (df["as_of_date"] >= trump_2_start)
    ).astype(int)

    # Transition periods (60 days before/after inauguration - heightened uncertainty)
    df["trump_transition"] = (
        (
            (df["as_of_date"] >= trump_1_start - pd.Timedelta(days=60))
            & (df["as_of_date"] < trump_1_start + pd.Timedelta(days=60))
        )
        | (
            (df["as_of_date"] >= trump_1_end - pd.Timedelta(days=60))
            & (df["as_of_date"] < trump_1_end + pd.Timedelta(days=60))
        )
        | (
            (df["as_of_date"] >= trump_2_start - pd.Timedelta(days=60))
            & (df["as_of_date"] < trump_2_start + pd.Timedelta(days=60))
        )
    ).astype(int)

    # ==========================================================================
    # 2. TRADE WAR REGIME FEATURES
    # ==========================================================================
    # Key dates in US-China trade war
    trade_war_start = pd.Timestamp("2018-03-22")  # Section 301 announced
    tariff_implemented = pd.Timestamp("2018-07-06")  # 25% tariff active
    phase_one_deal = pd.Timestamp("2020-01-15")  # Phase One signed

    # China tariff active (25% on US soybeans)
    df["china_tariff_active"] = (
        (df["as_of_date"] >= tariff_implemented)
        & (df["as_of_date"] < phase_one_deal + pd.Timedelta(days=365))
    ).astype(int)

    # Phase One active
    df["phase_one_active"] = (
        (df["as_of_date"] >= phase_one_deal) & (df["as_of_date"] < trump_1_end)
    ).astype(int)

    # Days since trade war events (for escalation timeline)
    df["days_since_tariff_announce"] = (df["as_of_date"] - trade_war_start).dt.days
    df["days_since_tariff_announce"] = df["days_since_tariff_announce"].clip(lower=0)

    # Trade war regime score (-5 to +5)
    # -5 = full war, 0 = neutral, +5 = deal
    df["trade_war_regime"] = 0.0
    df.loc[df["as_of_date"] >= trade_war_start, "trade_war_regime"] = -2.0
    df.loc[df["as_of_date"] >= tariff_implemented, "trade_war_regime"] = -4.0
    df.loc[
        df["as_of_date"] >= pd.Timestamp("2019-08-05"), "trade_war_regime"
    ] = -5.0  # CNY breaks 7
    df.loc[
        df["as_of_date"] >= pd.Timestamp("2019-10-11"), "trade_war_regime"
    ] = -2.0  # Handshake deal
    df.loc[df["as_of_date"] >= phase_one_deal, "trade_war_regime"] = 3.0
    df.loc[df["as_of_date"] >= trump_1_end, "trade_war_regime"] = 0.0  # Biden: neutral

    # ==========================================================================
    # 3. MFP (Market Facilitation Program) REGIME
    # ==========================================================================
    # MFP payments: 2018 and 2019
    mfp_2018_start = pd.Timestamp("2018-09-04")
    mfp_end = pd.Timestamp("2020-01-15")

    df["mfp_active"] = (
        (df["as_of_date"] >= mfp_2018_start) & (df["as_of_date"] < mfp_end)
    ).astype(int)

    # ==========================================================================
    # 4. EPA WAIVER REGIME (Small Refinery Exemptions)
    # ==========================================================================
    # High SRE period: 2017-2020 (Trump EPA)
    df["epa_waiver_regime"] = 0.0
    df.loc[
        (df["as_of_date"] >= trump_1_start) & (df["as_of_date"] < trump_1_end),
        "epa_waiver_regime",
    ] = -3.0
    df.loc[
        (df["as_of_date"] >= pd.Timestamp("2018-01-01"))
        & (df["as_of_date"] < pd.Timestamp("2019-06-01")),
        "epa_waiver_regime",
    ] = -5.0  # Peak waivers

    # ==========================================================================
    # 5. ELECTION CYCLE FEATURES
    # ==========================================================================
    # Days to next presidential election
    elections = [
        pd.Timestamp("2016-11-08"),
        pd.Timestamp("2020-11-03"),
        pd.Timestamp("2024-11-05"),
        pd.Timestamp("2028-11-03"),  # Projected
    ]

    def days_to_election(date):
        for elec in elections:
            if date < elec:
                return (elec - date).days
        return 0

    df["days_to_election"] = df["as_of_date"].apply(days_to_election)
    df["election_year"] = (
        df["as_of_date"].dt.year.isin([2016, 2020, 2024, 2028]).astype(int)
    )

    # ==========================================================================
    # 6. TRUMP 2.0 ANTICIPATION (2024 election cycle)
    # ==========================================================================
    # Market pricing in Trump 2.0 risk
    df["trump_2_anticipation"] = 0.0
    df.loc[df["as_of_date"] >= pd.Timestamp("2024-06-01"), "trump_2_anticipation"] = 0.3
    df.loc[df["as_of_date"] >= pd.Timestamp("2024-09-01"), "trump_2_anticipation"] = 0.5
    df.loc[df["as_of_date"] >= pd.Timestamp("2024-11-05"), "trump_2_anticipation"] = (
        1.0  # Election day
    )

    # ==========================================================================
    # 7. COMPOSITE TRUMP REGIME SCORE
    # ==========================================================================
    # Combine all Trump-related risks into single score
    df["trump_regime_score"] = (
        df["trump_in_office"] * 2
        + df["china_tariff_active"] * -3
        + df["phase_one_active"] * 2
        + df["mfp_active"] * 1
        + df["epa_waiver_regime"]
        + df["trump_transition"] * 1.5
    )

    # Convert as_of_date back to date for consistency
    df["as_of_date"] = df["as_of_date"].dt.date

    return df


def generate_bucket_features(
    bucket_name: str,
    bucket_config: dict,
    market_df: pd.DataFrame,
    fred_df: pd.DataFrame,
    fx_df: pd.DataFrame,
    cot_df: pd.DataFrame,
    usda_df: pd.DataFrame,
    wasde_df: pd.DataFrame,
    rin_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    news_df: pd.DataFrame,
    news_by_bucket: dict[str, pd.DataFrame] = None,
    whitehouse_df: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    Generate DOMAIN-SPECIFIC features for a specialist bucket.

    IMPORTANT: Specialists get HAND-PICKED features, NOT all 800+.
    This is the OPPOSITE of Core's all_data_policy.

    Each specialist receives only:
    - Symbols listed in their config
    - FRED series listed in their config
    - FX pairs listed in their config
    - COT data for listed symbols
    - Trump features if include_trump_features=True
    - RIN data if include_rin=True
    - Weather if include_weather=True
    - NEWS SENTIMENT specific to this bucket (from alt news tables via specialist_tags)
    """
    logger.info(f"  Generating DOMAIN-SPECIFIC features for: {bucket_name}")

    # Get config for this bucket
    symbols = bucket_config.get("symbols", ["ZL"])
    fred_series = bucket_config.get("fred_series", [])
    fx_pairs = bucket_config.get("fx_pairs", [])
    cot_symbols = bucket_config.get("cot_symbols", ["ZL"])
    include_rin = bucket_config.get("include_rin", False)
    include_trump = bucket_config.get("include_trump_features", False)
    include_weather = bucket_config.get("include_weather", False)
    include_usda = bucket_config.get("include_usda_exports", False)

    # ==========================================================================
    # 1. BASE: Start with ZL as base (always included)
    # ==========================================================================
    zl_df = market_df[market_df["symbol"] == "ZL"][
        ["as_of_date", "open", "high", "low", "close", "volume"]
    ].copy()
    zl_df = zl_df.rename(
        columns={
            "open": "zl_open",
            "high": "zl_high",
            "low": "zl_low",
            "close": "zl_close",
            "volume": "zl_volume",
        }
    )
    zl_df = zl_df.sort_values("as_of_date")

    # Add ZL core technical indicators
    zl_tech = calculate_technical_indicators(
        zl_df.rename(columns={"zl_close": "close"}), "close"
    )
    for col in [
        "return_1d",
        "return_5d",
        "return_21d",
        "sma_21",
        "sma_63",
        "macd",
        "rsi_14",
        "bb_pct",
        "volatility_21d",
    ]:
        if col in zl_tech.columns:
            zl_df[f"zl_{col}"] = zl_tech[col].values

    # ==========================================================================
    # 2. ADD ONLY CONFIGURED SYMBOLS (not all 84!)
    # ==========================================================================
    for sym in symbols:
        if sym == "ZL":
            continue
        sym_df = market_df[market_df["symbol"] == sym][
            ["as_of_date", "open", "high", "low", "close", "volume"]
        ].copy()
        if len(sym_df) > 0:
            sym_lower = sym.lower()
            sym_df = sym_df.rename(
                columns={
                    "open": f"{sym_lower}_open",
                    "high": f"{sym_lower}_high",
                    "low": f"{sym_lower}_low",
                    "close": f"{sym_lower}_close",
                    "volume": f"{sym_lower}_volume",
                }
            )
            # Add key returns
            sym_df[f"{sym_lower}_return_1d"] = sym_df[f"{sym_lower}_close"].pct_change(
                1
            )
            sym_df[f"{sym_lower}_return_21d"] = sym_df[f"{sym_lower}_close"].pct_change(
                21
            )
            zl_df = zl_df.merge(sym_df, on="as_of_date", how="left")
    logger.info(f"    + Symbols: {len(symbols)} ({', '.join(symbols)})")

    # ==========================================================================
    # 3. COMPUTE RICH BUCKET-SPECIFIC INDICATORS
    # ==========================================================================
    if bucket_name == "crush":
        # =====================================================================
        # CRUSH: Board crush, oil share, crush economics, momentum, regimes
        # =====================================================================
        if "zm_close" in zl_df.columns and "zs_close" in zl_df.columns:
            # Core spreads
            zl_df["board_crush"] = (
                zl_df["zl_close"] * 11 + zl_df["zm_close"] * 22 - zl_df["zs_close"] * 50
            )
            zl_df["oil_share"] = (
                zl_df["zl_close"]
                * 11
                / (zl_df["zl_close"] * 11 + zl_df["zm_close"] * 22 + 0.001)
            )
            zl_df["zl_zs_ratio"] = zl_df["zl_close"] / (zl_df["zs_close"] + 0.001)
            zl_df["zm_zs_ratio"] = zl_df["zm_close"] / (zl_df["zs_close"] + 0.001)
            zl_df["zl_zm_ratio"] = zl_df["zl_close"] / (zl_df["zm_close"] + 0.001)

            # Z-scores (normalized)
            zl_df["crush_zscore"] = (
                zl_df["board_crush"] - zl_df["board_crush"].rolling(252).mean()
            ) / zl_df["board_crush"].rolling(252).std()
            zl_df["oil_share_zscore"] = (
                zl_df["oil_share"] - zl_df["oil_share"].rolling(252).mean()
            ) / zl_df["oil_share"].rolling(252).std()

            # Percentile ranks
            zl_df["crush_percentile"] = (
                zl_df["board_crush"].rolling(252).rank(pct=True) * 100
            )
            zl_df["oil_share_percentile"] = (
                zl_df["oil_share"].rolling(252).rank(pct=True) * 100
            )

            # Bollinger bands for crush
            crush_sma = zl_df["board_crush"].rolling(20).mean()
            crush_std = zl_df["board_crush"].rolling(20).std()
            zl_df["crush_bb_upper"] = crush_sma + 2 * crush_std
            zl_df["crush_bb_lower"] = crush_sma - 2 * crush_std
            zl_df["crush_bb_pct"] = (zl_df["board_crush"] - zl_df["crush_bb_lower"]) / (
                zl_df["crush_bb_upper"] - zl_df["crush_bb_lower"] + 0.001
            )

            # Momentum
            zl_df["crush_momentum_5d"] = zl_df["board_crush"].pct_change(5) * 100
            zl_df["crush_momentum_21d"] = zl_df["board_crush"].pct_change(21) * 100
            zl_df["oil_share_change_21d"] = zl_df["oil_share"].diff(21)

            # Regime probabilities
            zl_df["crush_squeeze_prob"] = 1 / (1 + np.exp(zl_df["crush_zscore"] + 1))
            zl_df["crush_wide_prob"] = 1 / (1 + np.exp(-zl_df["crush_zscore"] + 1))

            # Signal strength (0-100)
            zl_df["crush_signal_strength"] = (
                np.abs(zl_df["crush_zscore"]).clip(0, 3) / 3 * 100
            )
            zl_df["oil_share_signal_strength"] = (
                np.abs(zl_df["oil_share_zscore"]).clip(0, 3) / 3 * 100
            )

            # Composite bucket signal
            zl_df["crush_bucket_signal"] = (
                zl_df["crush_zscore"] * 0.5 + zl_df["oil_share_zscore"] * 0.5
            )

            # Support/Resistance
            zl_df["crush_52w_high"] = zl_df["board_crush"].rolling(252).max()
            zl_df["crush_52w_low"] = zl_df["board_crush"].rolling(252).min()
            zl_df["crush_range_position"] = (
                (zl_df["board_crush"] - zl_df["crush_52w_low"])
                / (zl_df["crush_52w_high"] - zl_df["crush_52w_low"] + 0.001)
                * 100
            )

    elif bucket_name == "energy":
        # =====================================================================
        # ENERGY: BOHO, crack spreads, crude dynamics, refining economics
        # =====================================================================
        if "ho_close" in zl_df.columns:
            # BOHO spread (biodiesel premium)
            zl_df["boho_spread"] = zl_df["zl_close"] - zl_df["ho_close"]
            zl_df["boho_ratio"] = zl_df["zl_close"] / (zl_df["ho_close"] + 0.001)
            zl_df["boho_zscore"] = (
                zl_df["boho_spread"] - zl_df["boho_spread"].rolling(252).mean()
            ) / zl_df["boho_spread"].rolling(252).std()
            zl_df["boho_percentile"] = (
                zl_df["boho_spread"].rolling(252).rank(pct=True) * 100
            )

            # BOHO Bollinger bands
            boho_sma = zl_df["boho_spread"].rolling(20).mean()
            boho_std = zl_df["boho_spread"].rolling(20).std()
            zl_df["boho_bb_pct"] = (
                zl_df["boho_spread"] - (boho_sma - 2 * boho_std)
            ) / (4 * boho_std + 0.001)

            # BOHO momentum
            zl_df["boho_momentum_5d"] = zl_df["boho_spread"].pct_change(5) * 100
            zl_df["boho_momentum_21d"] = zl_df["boho_spread"].pct_change(21) * 100
            zl_df["boho_signal_strength"] = (
                np.abs(zl_df["boho_zscore"]).clip(0, 3) / 3 * 100
            )

        if "cl_close" in zl_df.columns:
            # Crude indicators
            zl_df["zl_cl_ratio"] = zl_df["zl_close"] / (zl_df["cl_close"] + 0.001)
            zl_df["cl_zscore"] = (
                zl_df["cl_close"] - zl_df["cl_close"].rolling(252).mean()
            ) / zl_df["cl_close"].rolling(252).std()
            zl_df["cl_percentile"] = zl_df["cl_close"].rolling(252).rank(pct=True) * 100
            zl_df["cl_momentum_21d"] = zl_df["cl_close"].pct_change(21) * 100
            zl_df["cl_momentum_63d"] = zl_df["cl_close"].pct_change(63) * 100
            zl_df["zl_cl_corr_21d"] = (
                zl_df["zl_close"].rolling(21).corr(zl_df["cl_close"])
            )

        if all(c in zl_df.columns for c in ["cl_close", "ho_close", "rb_close"]):
            # 3-2-1 crack spread
            zl_df["crack_spread_321"] = (
                2 * zl_df["rb_close"] + zl_df["ho_close"] - 3 * zl_df["cl_close"]
            )
            zl_df["crack_zscore"] = (
                zl_df["crack_spread_321"]
                - zl_df["crack_spread_321"].rolling(252).mean()
            ) / zl_df["crack_spread_321"].rolling(252).std()
            zl_df["crack_percentile"] = (
                zl_df["crack_spread_321"].rolling(252).rank(pct=True) * 100
            )
            zl_df["crack_momentum_21d"] = zl_df["crack_spread_321"].pct_change(21) * 100

            # Gasoline crack
            zl_df["gasoline_crack"] = zl_df["rb_close"] - zl_df["cl_close"]
            # Diesel crack
            zl_df["diesel_crack"] = zl_df["ho_close"] - zl_df["cl_close"]

        # --- FRED-based Energy Features ---
        # Brent-WTI spread (DCOILBRENTEU vs DCOILWTICO or CL futures)
        if "DCOILBRENTEU" in zl_df.columns:
            zl_df["brent"] = zl_df["DCOILBRENTEU"]
            zl_df["brent_zscore"] = (
                zl_df["brent"] - zl_df["brent"].rolling(252).mean()
            ) / zl_df["brent"].rolling(252).std()
            zl_df["brent_momentum_21d"] = zl_df["brent"].pct_change(21) * 100

            # Brent-WTI spread using FRED WTI or futures CL
            if "DCOILWTICO" in zl_df.columns:
                zl_df["brent_wti_spread"] = zl_df["DCOILBRENTEU"] - zl_df["DCOILWTICO"]
            elif "cl_close" in zl_df.columns:
                zl_df["brent_wti_spread"] = zl_df["DCOILBRENTEU"] - zl_df["cl_close"]

            if "brent_wti_spread" in zl_df.columns:
                zl_df["brent_wti_zscore"] = (
                    zl_df["brent_wti_spread"]
                    - zl_df["brent_wti_spread"].rolling(252).mean()
                ) / zl_df["brent_wti_spread"].rolling(252).std()
                zl_df["brent_wti_percentile"] = (
                    zl_df["brent_wti_spread"].rolling(252).rank(pct=True) * 100
                )
                # Arbitrage signal: wide spread = export opportunity
                zl_df["brent_wti_wide"] = (
                    zl_df["brent_wti_spread"]
                    > zl_df["brent_wti_spread"].rolling(252).quantile(0.8)
                ).astype(int)
                zl_df["brent_wti_tight"] = (
                    zl_df["brent_wti_spread"]
                    < zl_df["brent_wti_spread"].rolling(252).quantile(0.2)
                ).astype(int)

        # Natural Gas (NG) features if available
        if "ng_close" in zl_df.columns:
            zl_df["ng_zscore"] = (
                zl_df["ng_close"] - zl_df["ng_close"].rolling(252).mean()
            ) / zl_df["ng_close"].rolling(252).std()
            zl_df["ng_percentile"] = zl_df["ng_close"].rolling(252).rank(pct=True) * 100
            zl_df["ng_momentum_21d"] = zl_df["ng_close"].pct_change(21) * 100
            # CL/NG ratio (energy mix indicator)
            if "cl_close" in zl_df.columns:
                zl_df["cl_ng_ratio"] = zl_df["cl_close"] / (zl_df["ng_close"] + 0.001)

        # Composite energy signal
        energy_signals = []
        if "cl_zscore" in zl_df.columns:
            energy_signals.append(zl_df["cl_zscore"])
        if "boho_zscore" in zl_df.columns:
            energy_signals.append(zl_df["boho_zscore"])
        if "brent_wti_zscore" in zl_df.columns:
            energy_signals.append(zl_df["brent_wti_zscore"])
        if energy_signals:
            zl_df["energy_bucket_signal"] = pd.concat(energy_signals, axis=1).mean(
                axis=1
            )
            zl_df["energy_signal_strength"] = (
                np.abs(zl_df["energy_bucket_signal"]).clip(0, 3) / 3 * 100
            )
        else:
            zl_df["energy_bucket_signal"] = 0
            zl_df["energy_signal_strength"] = 0

    elif bucket_name == "china":
        # =====================================================================
        # CHINA: Copper as demand proxy, CNY effects, trade flows
        # =====================================================================
        if "hg_close" in zl_df.columns:
            # Copper z-score and momentum
            zl_df["hg_zscore"] = (
                zl_df["hg_close"] - zl_df["hg_close"].rolling(252).mean()
            ) / zl_df["hg_close"].rolling(252).std()
            zl_df["hg_percentile"] = zl_df["hg_close"].rolling(252).rank(pct=True) * 100
            zl_df["hg_momentum_5d"] = zl_df["hg_close"].pct_change(5) * 100
            zl_df["hg_momentum_21d"] = zl_df["hg_close"].pct_change(21) * 100
            zl_df["hg_momentum_63d"] = zl_df["hg_close"].pct_change(63) * 100

            # Copper Bollinger bands
            hg_sma = zl_df["hg_close"].rolling(20).mean()
            hg_std = zl_df["hg_close"].rolling(20).std()
            zl_df["hg_bb_pct"] = (zl_df["hg_close"] - (hg_sma - 2 * hg_std)) / (
                4 * hg_std + 0.001
            )

            # HG/ZL correlation (rolling)
            zl_df["hg_zl_corr_21d"] = (
                zl_df["hg_close"].rolling(21).corr(zl_df["zl_close"])
            )
            zl_df["hg_zl_corr_60d"] = (
                zl_df["hg_close"].rolling(60).corr(zl_df["zl_close"])
            )

            # HG/ZL ratio
            zl_df["hg_zl_ratio"] = zl_df["hg_close"] / zl_df["zl_close"]

            # Signal strength
            zl_df["hg_signal_strength"] = (
                np.abs(zl_df["hg_zscore"]).clip(0, 3) / 3 * 100
            )
            zl_df["hg_bullish_prob"] = 1 / (1 + np.exp(-zl_df["hg_zscore"]))

            # China demand regime (very_weak to very_strong)
            zl_df["china_demand_score"] = zl_df["hg_zscore"]

        # Composite signal
        if "hg_zscore" in zl_df.columns:
            zl_df["china_bucket_signal"] = zl_df["hg_zscore"]
            zl_df["china_signal_strength"] = (
                np.abs(zl_df["china_bucket_signal"]).clip(0, 3) / 3 * 100
            )

    elif bucket_name == "palm":
        # =====================================================================
        # PALM: Palm/soy spreads, inventory, production, weather (El Nino)
        # Using actual CPO (Crude Palm Oil) data, NOT XK proxy
        # =====================================================================
        if "cpo_close" in zl_df.columns:
            # Core spreads - ZL vs actual CPO
            zl_df["zl_palm_spread"] = zl_df["zl_close"] - zl_df["cpo_close"]
            zl_df["zl_palm_ratio"] = zl_df["zl_close"] / (zl_df["cpo_close"] + 0.001)
            zl_df["zl_palm_zscore"] = (
                zl_df["zl_palm_spread"] - zl_df["zl_palm_spread"].rolling(252).mean()
            ) / zl_df["zl_palm_spread"].rolling(252).std()
            zl_df["zl_palm_percentile"] = (
                zl_df["zl_palm_spread"].rolling(252).rank(pct=True) * 100
            )

            # CPO price features
            zl_df["cpo_sma_21"] = zl_df["cpo_close"].rolling(21).mean()
            zl_df["cpo_sma_63"] = zl_df["cpo_close"].rolling(63).mean()
            zl_df["cpo_price_vs_sma21"] = zl_df["cpo_close"] / zl_df["cpo_sma_21"] - 1
            zl_df["cpo_price_vs_sma63"] = zl_df["cpo_close"] / zl_df["cpo_sma_63"] - 1

            # Palm momentum (actual CPO)
            zl_df["cpo_momentum_5d"] = zl_df["cpo_close"].pct_change(5) * 100
            zl_df["cpo_momentum_21d"] = zl_df["cpo_close"].pct_change(21) * 100
            zl_df["zl_palm_spread_momentum"] = zl_df["zl_palm_spread"].diff(21)

            # CPO volatility
            zl_df["cpo_volatility_21d"] = zl_df["cpo_close"].pct_change(1).rolling(
                21
            ).std() * np.sqrt(252)

            # Palm Bollinger bands
            palm_sma = zl_df["zl_palm_spread"].rolling(20).mean()
            palm_std = zl_df["zl_palm_spread"].rolling(20).std()
            zl_df["palm_bb_pct"] = (
                zl_df["zl_palm_spread"] - (palm_sma - 2 * palm_std)
            ) / (4 * palm_std + 0.001)

            # Signal strength
            zl_df["palm_signal_strength"] = (
                np.abs(zl_df["zl_palm_zscore"]).clip(0, 3) / 3 * 100
            )

            # Premium/discount flag (ZL vs CPO)
            zl_df["palm_premium_flag"] = (zl_df["zl_palm_ratio"] < 1.05).astype(int)
            zl_df["palm_discount_flag"] = (zl_df["zl_palm_ratio"] > 1.15).astype(int)

            # Composite
            zl_df["palm_bucket_signal"] = zl_df["zl_palm_zscore"]

    elif bucket_name == "biofuel":
        # =====================================================================
        # BIOFUEL: RIN indicators are added separately via include_rin
        # Add biodiesel margin and SBO feedstock calculations here
        # =====================================================================
        if "ho_close" in zl_df.columns:
            # Biodiesel margin proxy (ZL vs HO, RINs added later)
            zl_df["biodiesel_margin_proxy"] = zl_df["zl_close"] - zl_df["ho_close"]
            zl_df["biodiesel_margin_zscore"] = (
                zl_df["biodiesel_margin_proxy"]
                - zl_df["biodiesel_margin_proxy"].rolling(252).mean()
            ) / zl_df["biodiesel_margin_proxy"].rolling(252).std()

        if "cl_close" in zl_df.columns:
            # Energy feedstock economics
            zl_df["zl_crude_ratio"] = zl_df["zl_close"] / (zl_df["cl_close"] + 0.001)

    elif bucket_name == "volatility":
        # =====================================================================
        # VOLATILITY: VIX, realized vol, term structure, correlation, skew
        # =====================================================================
        # ZL realized volatility
        zl_df["zl_realized_vol_10d"] = zl_df["zl_return_1d"].rolling(
            10
        ).std() * np.sqrt(252)
        zl_df["zl_realized_vol_20d"] = zl_df["zl_return_1d"].rolling(
            20
        ).std() * np.sqrt(252)
        zl_df["zl_realized_vol_60d"] = zl_df["zl_return_1d"].rolling(
            60
        ).std() * np.sqrt(252)

        # Vol of vol
        zl_df["vol_of_vol"] = zl_df["zl_realized_vol_20d"].rolling(20).std()

        # Vol regime
        vol_mean = zl_df["zl_realized_vol_20d"].rolling(252).mean()
        vol_std = zl_df["zl_realized_vol_20d"].rolling(252).std()
        zl_df["vol_zscore"] = (zl_df["zl_realized_vol_20d"] - vol_mean) / vol_std
        zl_df["vol_percentile"] = (
            zl_df["zl_realized_vol_20d"].rolling(252).rank(pct=True) * 100
        )

        # Vol momentum
        zl_df["vol_momentum_5d"] = zl_df["zl_realized_vol_20d"].pct_change(5) * 100
        zl_df["vol_momentum_21d"] = zl_df["zl_realized_vol_20d"].pct_change(21) * 100

        if "es_close" in zl_df.columns:
            # Equity correlation
            es_ret = zl_df["es_close"].pct_change()
            zl_df["es_zl_corr_21d"] = es_ret.rolling(21).corr(zl_df["zl_return_1d"])
            zl_df["es_zl_corr_60d"] = es_ret.rolling(60).corr(zl_df["zl_return_1d"])

            # ES realized vol for comparison
            zl_df["es_realized_vol_20d"] = es_ret.rolling(20).std() * np.sqrt(252)

        if "vx_close" in zl_df.columns:
            # VIX futures indicators
            zl_df["vx_zscore"] = (
                zl_df["vx_close"] - zl_df["vx_close"].rolling(252).mean()
            ) / zl_df["vx_close"].rolling(252).std()
            zl_df["vx_percentile"] = zl_df["vx_close"].rolling(252).rank(pct=True) * 100

        # Oil VIX (OVXCLS) - critical for energy/soybean oil volatility
        if "fred_OVXCLS" in zl_df.columns:
            zl_df["ovx"] = zl_df["fred_OVXCLS"]
            zl_df["ovx_zscore"] = (
                zl_df["ovx"] - zl_df["ovx"].rolling(252).mean()
            ) / zl_df["ovx"].rolling(252).std()
            zl_df["ovx_percentile"] = zl_df["ovx"].rolling(252).rank(pct=True) * 100
            zl_df["ovx_momentum_21d"] = zl_df["ovx"].pct_change(21) * 100
            # OVX vs VIX spread (commodity vs equity fear)
            if "fred_VIXCLS" in zl_df.columns:
                zl_df["ovx_vix_spread"] = zl_df["ovx"] - zl_df["fred_VIXCLS"]
                zl_df["ovx_vix_ratio"] = zl_df["ovx"] / (zl_df["fred_VIXCLS"] + 0.001)

        # Gold VIX (GVZCLS) - commodity vol cross-reference (available 2008+)
        if "fred_GVZCLS" in zl_df.columns:
            zl_df["gvz"] = zl_df["fred_GVZCLS"]
            zl_df["gvz_zscore"] = (
                zl_df["gvz"] - zl_df["gvz"].rolling(252).mean()
            ) / zl_df["gvz"].rolling(252).std()
            zl_df["gvz_percentile"] = zl_df["gvz"].rolling(252).rank(pct=True) * 100
            zl_df["gvz_momentum_21d"] = zl_df["gvz"].pct_change(21) * 100
            # GVZ availability flag (null pre-2008)
            zl_df["gvz_available"] = zl_df["gvz"].notna().astype(int)

        # Financial Stress Index (STLFSI4)
        if "fred_STLFSI4" in zl_df.columns:
            zl_df["stress_index"] = zl_df["fred_STLFSI4"]
            zl_df["stress_zscore"] = (
                zl_df["stress_index"] - zl_df["stress_index"].rolling(252).mean()
            ) / zl_df["stress_index"].rolling(252).std()
            zl_df["stress_regime_high"] = (zl_df["stress_index"] > 0).astype(
                int
            )  # >0 = stress
            zl_df["stress_regime_crisis"] = (zl_df["stress_index"] > 2).astype(
                int
            )  # >2 = crisis

        # Composite - combine multiple vol signals
        vol_signals = [zl_df["vol_zscore"]]
        if "ovx_zscore" in zl_df.columns:
            vol_signals.append(zl_df["ovx_zscore"])
        if "gvz_zscore" in zl_df.columns:
            vol_signals.append(zl_df["gvz_zscore"])
        if "stress_zscore" in zl_df.columns:
            vol_signals.append(zl_df["stress_zscore"])
        zl_df["vol_bucket_signal"] = pd.concat(vol_signals, axis=1).mean(axis=1)
        zl_df["vol_signal_strength"] = (
            np.abs(zl_df["vol_bucket_signal"]).clip(0, 3) / 3 * 100
        )

    elif bucket_name == "substitutes":
        # =====================================================================
        # SUBSTITUTES: Canola, sunflower spreads vs ZL
        # RS = ICE Canola (3,575 rows), PSUNOUSDM = Sunflower (FRED, 427 rows)
        # =====================================================================
        if "rs_close" in zl_df.columns:
            # Canola spreads
            zl_df["zl_canola_spread"] = zl_df["zl_close"] - zl_df["rs_close"]
            zl_df["zl_canola_ratio"] = zl_df["zl_close"] / (zl_df["rs_close"] + 0.001)
            zl_df["zl_canola_zscore"] = (
                zl_df["zl_canola_spread"]
                - zl_df["zl_canola_spread"].rolling(252).mean()
            ) / zl_df["zl_canola_spread"].rolling(252).std()
            zl_df["zl_canola_percentile"] = (
                zl_df["zl_canola_spread"].rolling(252).rank(pct=True) * 100
            )

            # Canola momentum
            zl_df["canola_momentum_21d"] = zl_df["rs_close"].pct_change(21) * 100
            zl_df["zl_canola_spread_momentum"] = zl_df["zl_canola_spread"].diff(21)

            # Canola Bollinger
            canola_sma = zl_df["zl_canola_spread"].rolling(20).mean()
            canola_std = zl_df["zl_canola_spread"].rolling(20).std()
            zl_df["canola_bb_pct"] = (
                zl_df["zl_canola_spread"] - (canola_sma - 2 * canola_std)
            ) / (4 * canola_std + 0.001)

            # Signal strength
            zl_df["canola_signal_strength"] = (
                np.abs(zl_df["zl_canola_zscore"]).clip(0, 3) / 3 * 100
            )

            # Canola tight flag (premium)
            zl_df["canola_tight_flag"] = (
                zl_df["zl_canola_spread"]
                < zl_df["zl_canola_spread"].rolling(252).quantile(0.2)
            ).astype(int)

        # Sunflower oil from FRED (PSUNOUSDM)
        if "fred_PSUNOUSDM" in zl_df.columns:
            # Sunflower spreads (ZL vs sunflower price)
            zl_df["zl_sunflower_spread"] = zl_df["zl_close"] - zl_df["fred_PSUNOUSDM"]
            zl_df["zl_sunflower_ratio"] = zl_df["zl_close"] / (
                zl_df["fred_PSUNOUSDM"] + 0.001
            )
            zl_df["zl_sunflower_zscore"] = (
                zl_df["zl_sunflower_spread"]
                - zl_df["zl_sunflower_spread"].rolling(252).mean()
            ) / zl_df["zl_sunflower_spread"].rolling(252).std()

            # Sunflower momentum
            zl_df["sunflower_momentum_21d"] = (
                zl_df["fred_PSUNOUSDM"].pct_change(21) * 100
            )
            zl_df["sunflower_price_vs_sma"] = (
                zl_df["fred_PSUNOUSDM"] / zl_df["fred_PSUNOUSDM"].rolling(63).mean() - 1
            )

        # Composite signal (average of available signals)
        signals = []
        if "zl_canola_zscore" in zl_df.columns:
            signals.append(zl_df["zl_canola_zscore"])
        if "zl_sunflower_zscore" in zl_df.columns:
            signals.append(zl_df["zl_sunflower_zscore"])
        if signals:
            zl_df["substitutes_bucket_signal"] = pd.concat(signals, axis=1).mean(axis=1)

    elif bucket_name == "fx":
        # =====================================================================
        # FX: Dollar strength, EM currencies, devaluation risks
        # FX pairs: EURUSD, USDJPY, USDBRL, USDCNY, USDARS
        # FRED series: DTWEXBGS (Trade-Weighted Dollar)
        # =====================================================================
        if "dx_close" in zl_df.columns:
            # DXY indicators (futures)
            zl_df["dxy_zscore"] = (
                zl_df["dx_close"] - zl_df["dx_close"].rolling(252).mean()
            ) / zl_df["dx_close"].rolling(252).std()
            zl_df["dxy_percentile"] = (
                zl_df["dx_close"].rolling(252).rank(pct=True) * 100
            )
            zl_df["dxy_momentum_21d"] = zl_df["dx_close"].pct_change(21) * 100

            # DXY Bollinger
            dx_sma = zl_df["dx_close"].rolling(20).mean()
            dx_std = zl_df["dx_close"].rolling(20).std()
            zl_df["dxy_bb_pct"] = (zl_df["dx_close"] - (dx_sma - 2 * dx_std)) / (
                4 * dx_std + 0.001
            )

            # Dollar/ZL correlation
            zl_df["dxy_zl_corr_21d"] = (
                zl_df["dx_close"].rolling(21).corr(zl_df["zl_close"])
            )

        # Trade-Weighted Dollar from FRED (DTWEXBGS)
        if "DTWEXBGS" in zl_df.columns:
            zl_df["trade_weighted_dollar"] = zl_df["DTWEXBGS"]
            zl_df["twd_zscore"] = (
                zl_df["trade_weighted_dollar"]
                - zl_df["trade_weighted_dollar"].rolling(252).mean()
            ) / zl_df["trade_weighted_dollar"].rolling(252).std()
            zl_df["twd_momentum_21d"] = (
                zl_df["trade_weighted_dollar"].pct_change(21) * 100
            )

        # --- EM Currency Features (from FX pairs merged in section 5) ---
        # Brazilian Real (USDBRL) - SA exporter currency
        if "fx_USDBRL" in zl_df.columns:
            zl_df["brl_rate"] = zl_df["fx_USDBRL"]
            zl_df["brl_zscore"] = (
                zl_df["brl_rate"] - zl_df["brl_rate"].rolling(252).mean()
            ) / zl_df["brl_rate"].rolling(252).std()
            zl_df["brl_momentum_21d"] = zl_df["brl_rate"].pct_change(21) * 100
            zl_df["brl_volatility_21d"] = zl_df["brl_rate"].pct_change(1).rolling(
                21
            ).std() * np.sqrt(252)
            # Devaluation probability: high z-score = weak BRL = devaluation risk
            zl_df["brl_devalue_prob"] = 1 / (1 + np.exp(-zl_df["brl_zscore"]))
            # BRL/ZL correlation
            zl_df["brl_zl_corr_21d"] = (
                zl_df["brl_rate"].rolling(21).corr(zl_df["zl_close"])
            )

        # Chinese Yuan (USDCNY) - demand center currency
        if "fx_USDCNY" in zl_df.columns:
            zl_df["cny_rate"] = zl_df["fx_USDCNY"]
            zl_df["cny_zscore"] = (
                zl_df["cny_rate"] - zl_df["cny_rate"].rolling(252).mean()
            ) / zl_df["cny_rate"].rolling(252).std()
            zl_df["cny_momentum_21d"] = zl_df["cny_rate"].pct_change(21) * 100
            zl_df["cny_volatility_21d"] = zl_df["cny_rate"].pct_change(1).rolling(
                21
            ).std() * np.sqrt(252)
            # CNY devaluation probability
            zl_df["cny_devalue_prob"] = 1 / (1 + np.exp(-zl_df["cny_zscore"]))
            # CNY/ZL correlation
            zl_df["cny_zl_corr_21d"] = (
                zl_df["cny_rate"].rolling(21).corr(zl_df["zl_close"])
            )

        # Argentine Peso (USDARS) - SA exporter currency
        if "fx_USDARS" in zl_df.columns:
            zl_df["ars_rate"] = zl_df["fx_USDARS"]
            zl_df["ars_zscore"] = (
                zl_df["ars_rate"] - zl_df["ars_rate"].rolling(252).mean()
            ) / zl_df["ars_rate"].rolling(252).std()
            zl_df["ars_momentum_21d"] = zl_df["ars_rate"].pct_change(21) * 100
            # ARS devaluation probability (often very high)
            zl_df["ars_devalue_prob"] = 1 / (1 + np.exp(-zl_df["ars_zscore"]))

        # EM Currency Composite Index (average of BRL, CNY, ARS weakness)
        em_signals = []
        for col in ["brl_zscore", "cny_zscore", "ars_zscore"]:
            if col in zl_df.columns:
                em_signals.append(zl_df[col])
        if em_signals:
            zl_df["em_currency_weakness"] = pd.concat(em_signals, axis=1).mean(axis=1)
            zl_df["em_currency_stress"] = (zl_df["em_currency_weakness"] > 1).astype(
                int
            )

        # Composite FX Signal
        fx_signals = []
        if "dxy_zscore" in zl_df.columns:
            fx_signals.append(
                -zl_df["dxy_zscore"]
            )  # Negative: strong dollar = bearish ZL
        if "em_currency_weakness" in zl_df.columns:
            fx_signals.append(zl_df["em_currency_weakness"])  # Weak EM = bearish ZL
        if fx_signals:
            zl_df["fx_bucket_signal"] = pd.concat(fx_signals, axis=1).mean(axis=1)
            zl_df["fx_signal_strength"] = (
                np.abs(zl_df["fx_bucket_signal"]).clip(0, 3) / 3 * 100
            )
        else:
            zl_df["fx_bucket_signal"] = 0
            zl_df["fx_signal_strength"] = 0

    elif bucket_name == "fed":
        # =====================================================================
        # FED: Yield curve, financial conditions, rate expectations
        # FRED series: FEDFUNDS, DGS10, DGS2, T10Y2Y, NFCI
        # =====================================================================
        if "zn_close" in zl_df.columns and "zb_close" in zl_df.columns:
            # Treasury spread (2s10s proxy via futures)
            zl_df["treasury_spread"] = zl_df["zn_close"] - zl_df["zb_close"]
            zl_df["treasury_spread_zscore"] = (
                zl_df["treasury_spread"] - zl_df["treasury_spread"].rolling(252).mean()
            ) / zl_df["treasury_spread"].rolling(252).std()

        if "zn_close" in zl_df.columns:
            # 10Y momentum
            zl_df["zn_momentum_21d"] = zl_df["zn_close"].pct_change(21) * 100
            zl_df["zn_zl_corr_21d"] = (
                zl_df["zn_close"].rolling(21).corr(zl_df["zl_close"])
            )

        # --- FRED-based Fed Policy Features ---
        # Fed Funds Rate (FEDFUNDS)
        if "FEDFUNDS" in zl_df.columns:
            zl_df["fed_funds_rate"] = zl_df["FEDFUNDS"]
            zl_df["fed_funds_zscore"] = (
                zl_df["fed_funds_rate"] - zl_df["fed_funds_rate"].rolling(252).mean()
            ) / zl_df["fed_funds_rate"].rolling(252).std()
            zl_df["fed_funds_change_21d"] = zl_df["fed_funds_rate"].diff(21)
            # Rate regime (rising/stable/falling)
            zl_df["fed_rate_regime"] = (
                np.sign(zl_df["fed_funds_change_21d"]).fillna(0).astype(int)
            )

        # Treasury Yields (DGS10, DGS2)
        if "DGS10" in zl_df.columns:
            zl_df["dgs10"] = zl_df["DGS10"]
            zl_df["dgs10_zscore"] = (
                zl_df["dgs10"] - zl_df["dgs10"].rolling(252).mean()
            ) / zl_df["dgs10"].rolling(252).std()
            zl_df["dgs10_momentum_21d"] = zl_df["dgs10"].diff(21)

        if "DGS2" in zl_df.columns:
            zl_df["dgs2"] = zl_df["DGS2"]
            zl_df["dgs2_zscore"] = (
                zl_df["dgs2"] - zl_df["dgs2"].rolling(252).mean()
            ) / zl_df["dgs2"].rolling(252).std()

        # Yield Curve (T10Y2Y) - 10Y minus 2Y spread
        if "T10Y2Y" in zl_df.columns:
            zl_df["t10y2y"] = zl_df["T10Y2Y"]
            zl_df["t10y2y_zscore"] = (
                zl_df["t10y2y"] - zl_df["t10y2y"].rolling(252).mean()
            ) / zl_df["t10y2y"].rolling(252).std()
            zl_df["t10y2y_momentum_21d"] = zl_df["t10y2y"].diff(21)
            # Yield curve regime (inverted/flat/steep)
            zl_df["yield_curve_inverted"] = (zl_df["t10y2y"] < 0).astype(int)
            zl_df["yield_curve_flat"] = (
                (zl_df["t10y2y"] >= 0) & (zl_df["t10y2y"] < 0.5)
            ).astype(int)
            zl_df["yield_curve_steep"] = (zl_df["t10y2y"] >= 0.5).astype(int)
            # Yield curve regime score (-1=inverted, 0=flat, 1=steep)
            zl_df["yield_curve_regime"] = np.where(
                zl_df["t10y2y"] < 0, -1, np.where(zl_df["t10y2y"] < 0.5, 0, 1)
            )

        # Financial Conditions (NFCI) - Chicago Fed National Financial Conditions Index
        if "NFCI" in zl_df.columns:
            zl_df["nfci"] = zl_df["NFCI"]
            zl_df["nfci_zscore"] = (
                zl_df["nfci"] - zl_df["nfci"].rolling(252).mean()
            ) / zl_df["nfci"].rolling(252).std()
            zl_df["financial_stress_zscore"] = zl_df["nfci_zscore"]  # Alias for config
            zl_df["nfci_momentum_21d"] = zl_df["nfci"].diff(21)
            # Financial conditions regime (loose/neutral/tight)
            zl_df["nfci_tight"] = (zl_df["nfci"] > 0).astype(
                int
            )  # >0 = tighter than average
            zl_df["nfci_loose"] = (zl_df["nfci"] < -0.5).astype(int)  # very loose
            zl_df["nfci_crisis"] = (zl_df["nfci"] > 1).astype(int)  # crisis levels

        # Composite Fed Signal
        fed_signals = []
        if "t10y2y_zscore" in zl_df.columns:
            fed_signals.append(zl_df["t10y2y_zscore"])
        if "nfci_zscore" in zl_df.columns:
            fed_signals.append(zl_df["nfci_zscore"])
        if "treasury_spread_zscore" in zl_df.columns:
            fed_signals.append(zl_df["treasury_spread_zscore"])
        if fed_signals:
            zl_df["fed_bucket_signal"] = pd.concat(fed_signals, axis=1).mean(axis=1)
            zl_df["fed_signal_strength"] = (
                np.abs(zl_df["fed_bucket_signal"]).clip(0, 3) / 3 * 100
            )
        else:
            zl_df["fed_bucket_signal"] = 0
            zl_df["fed_signal_strength"] = 0

    elif bucket_name == "tariff":
        # =====================================================================
        # TARIFF: Trade policy, tariffs, uncertainty, retaliation risk
        # FRED series: USEPUINDXM (Monthly Economic Policy Uncertainty)
        # =====================================================================
        if "zs_close" in zl_df.columns:
            # Soy complex sensitivity to trade war
            zl_df["zs_zscore"] = (
                zl_df["zs_close"] - zl_df["zs_close"].rolling(252).mean()
            ) / zl_df["zs_close"].rolling(252).std()
            zl_df["zs_percentile"] = zl_df["zs_close"].rolling(252).rank(pct=True) * 100
            zl_df["zs_momentum_21d"] = zl_df["zs_close"].pct_change(21) * 100

        if "zm_close" in zl_df.columns:
            zl_df["zm_zscore"] = (
                zl_df["zm_close"] - zl_df["zm_close"].rolling(252).mean()
            ) / zl_df["zm_close"].rolling(252).std()
            zl_df["zm_momentum_21d"] = zl_df["zm_close"].pct_change(21) * 100

        # Soy complex correlations during trade tensions
        if "zs_close" in zl_df.columns:
            zl_df["zl_zs_corr_21d"] = (
                zl_df["zl_close"].rolling(21).corr(zl_df["zs_close"])
            )

        # --- FRED-based Policy Uncertainty Features ---
        # Economic Policy Uncertainty Index (USEPUINDXM - monthly)
        if "USEPUINDXM" in zl_df.columns:
            zl_df["policy_uncertainty_index"] = zl_df["USEPUINDXM"]
            zl_df["policy_uncertainty_zscore"] = (
                zl_df["policy_uncertainty_index"]
                - zl_df["policy_uncertainty_index"].rolling(252).mean()
            ) / zl_df["policy_uncertainty_index"].rolling(252).std()
            zl_df["policy_uncertainty_percentile"] = (
                zl_df["policy_uncertainty_index"].rolling(252).rank(pct=True) * 100
            )
            zl_df["policy_uncertainty_momentum"] = (
                zl_df["policy_uncertainty_index"].pct_change(21) * 100
            )

            # Policy uncertainty regime (low/normal/high/extreme)
            zl_df["policy_uncertainty_low"] = (
                zl_df["policy_uncertainty_zscore"] < -1
            ).astype(int)
            zl_df["policy_uncertainty_high"] = (
                zl_df["policy_uncertainty_zscore"] > 1
            ).astype(int)
            zl_df["policy_uncertainty_extreme"] = (
                zl_df["policy_uncertainty_zscore"] > 2
            ).astype(int)

            # Trade war regime score (-5 to +5 scale based on uncertainty)
            zl_df["trade_war_regime"] = (zl_df["policy_uncertainty_zscore"] * 2.5).clip(
                -5, 5
            )

        # Composite Tariff Signal
        tariff_signals = []
        if "policy_uncertainty_zscore" in zl_df.columns:
            tariff_signals.append(zl_df["policy_uncertainty_zscore"])
        if "zs_zscore" in zl_df.columns:
            tariff_signals.append(
                -zl_df["zs_zscore"]
            )  # Negative: tariff fears depress soybeans
        if tariff_signals:
            zl_df["tariff_bucket_signal"] = pd.concat(tariff_signals, axis=1).mean(
                axis=1
            )
            zl_df["tariff_signal_strength"] = (
                np.abs(zl_df["tariff_bucket_signal"]).clip(0, 3) / 3 * 100
            )
        else:
            zl_df["tariff_bucket_signal"] = 0
            zl_df["tariff_signal_strength"] = 0

    elif bucket_name == "trump_effect":
        # =====================================================================
        # TRUMP_EFFECT: Policy regime dynamics, WhiteHouse actions, trade war
        # Uses alt.legislation_1d for executive order tracking
        # =====================================================================
        # WhiteHouse actions (EOs, proclamations, memoranda)
        if whitehouse_df is not None and not whitehouse_df.empty:
            zl_df = zl_df.merge(whitehouse_df, on="as_of_date", how="left")
            # Fill missing with 0 (no actions that day)
            wh_cols = [c for c in zl_df.columns if c.startswith("wh_")]
            for col in wh_cols:
                zl_df[col] = zl_df[col].fillna(0)
            logger.info(f"    + WhiteHouse: {len(wh_cols)} features")

        # DJT stock proxy for Trump sentiment (from equity market data)
        if "djt_close" in zl_df.columns:
            zl_df["djt_momentum_5d"] = zl_df["djt_close"].pct_change(5) * 100
            zl_df["djt_momentum_21d"] = zl_df["djt_close"].pct_change(21) * 100
            zl_df["djt_zscore"] = (
                zl_df["djt_close"] - zl_df["djt_close"].rolling(252).mean()
            ) / zl_df["djt_close"].rolling(252).std()
            zl_df["djt_volatility_21d"] = zl_df["djt_close"].pct_change(1).rolling(
                21
            ).std() * np.sqrt(252)

        # Policy uncertainty from FRED (USEPUINDXD)
        if "fred_USEPUINDXD" in zl_df.columns:
            zl_df["policy_uncertainty"] = zl_df["fred_USEPUINDXD"]
            zl_df["policy_uncertainty_zscore"] = (
                zl_df["policy_uncertainty"]
                - zl_df["policy_uncertainty"].rolling(252).mean()
            ) / zl_df["policy_uncertainty"].rolling(252).std()
            zl_df["policy_uncertainty_high"] = (
                zl_df["policy_uncertainty"]
                > zl_df["policy_uncertainty"].rolling(252).quantile(0.8)
            ).astype(int)

        # Trade policy uncertainty from FRED (EPUTRADE)
        if "fred_EPUTRADE" in zl_df.columns:
            zl_df["trade_policy_uncertainty"] = zl_df["fred_EPUTRADE"]
            zl_df["trade_policy_uncertainty_zscore"] = (
                zl_df["trade_policy_uncertainty"]
                - zl_df["trade_policy_uncertainty"].rolling(252).mean()
            ) / zl_df["trade_policy_uncertainty"].rolling(252).std()

        # Composite trump effect signal
        signals = []
        if "policy_uncertainty_zscore" in zl_df.columns:
            signals.append(zl_df["policy_uncertainty_zscore"])
        if "trade_policy_uncertainty_zscore" in zl_df.columns:
            signals.append(zl_df["trade_policy_uncertainty_zscore"])
        if signals:
            zl_df["trump_bucket_signal"] = pd.concat(signals, axis=1).mean(axis=1)
        else:
            zl_df["trump_bucket_signal"] = 0

    # ==========================================================================
    # 4. ADD ONLY CONFIGURED FRED SERIES (not all 111!)
    # ==========================================================================
    if fred_series and len(fred_df.columns) > 1:
        fred_cols = ["as_of_date"] + [c for c in fred_df.columns if c in fred_series]
        if len(fred_cols) > 1:
            zl_df = zl_df.merge(fred_df[fred_cols], on="as_of_date", how="left")
            logger.info(
                f"    + FRED: {len(fred_cols) - 1} series ({', '.join(fred_series[:3])}...)"
            )

    # ==========================================================================
    # 5. ADD ONLY CONFIGURED FX PAIRS (not all 30!)
    # ==========================================================================
    if fx_pairs and len(fx_df.columns) > 1:
        fx_cols_to_add = ["as_of_date"]
        for pair in fx_pairs:
            fx_col = f"fx_{pair}"
            if fx_col in fx_df.columns:
                fx_cols_to_add.append(fx_col)
        if len(fx_cols_to_add) > 1:
            zl_df = zl_df.merge(fx_df[fx_cols_to_add], on="as_of_date", how="left")
            logger.info(f"    + FX: {len(fx_cols_to_add) - 1} pairs")

    # ==========================================================================
    # 5b. POST-MERGE FX PROCESSING (bucket-specific features from FX data)
    # ==========================================================================
    # CHINA bucket: Add CNY devaluation features after FX merge
    if bucket_name == "china" and "fx_USDCNY" in zl_df.columns:
        zl_df["usd_cny"] = zl_df["fx_USDCNY"]
        zl_df["cny_zscore"] = (
            zl_df["usd_cny"] - zl_df["usd_cny"].rolling(252).mean()
        ) / zl_df["usd_cny"].rolling(252).std()
        zl_df["cny_momentum_21d"] = zl_df["usd_cny"].pct_change(21) * 100
        zl_df["cny_volatility_21d"] = zl_df["usd_cny"].pct_change(1).rolling(
            21
        ).std() * np.sqrt(252)
        # CNY devaluation probability (higher USD/CNY = weaker CNY)
        zl_df["cny_devalue_prob"] = 1 / (1 + np.exp(-zl_df["cny_zscore"]))
        # CNY regime flags
        zl_df["cny_weak"] = (zl_df["cny_zscore"] > 1).astype(int)
        zl_df["cny_strong"] = (zl_df["cny_zscore"] < -1).astype(int)
        # Update china_bucket_signal to include CNY
        if "hg_zscore" in zl_df.columns:
            # China demand = copper demand - CNY weakness (weak CNY = less imports)
            zl_df["china_bucket_signal"] = (
                zl_df["hg_zscore"] - zl_df["cny_zscore"]
            ) / 2
            zl_df["china_signal_strength"] = (
                np.abs(zl_df["china_bucket_signal"]).clip(0, 3) / 3 * 100
            )
        logger.info("    + CNY features: devaluation prob, regime, updated signal")

    # CRUSH bucket: Add SA currency features (BRL, ARS affect competition)
    if bucket_name == "crush":
        sa_signals = []
        if "fx_USDBRL" in zl_df.columns:
            zl_df["brl_rate"] = zl_df["fx_USDBRL"]
            zl_df["brl_zscore"] = (
                zl_df["brl_rate"] - zl_df["brl_rate"].rolling(252).mean()
            ) / zl_df["brl_rate"].rolling(252).std()
            zl_df["brl_momentum_21d"] = zl_df["brl_rate"].pct_change(21) * 100
            # Weak BRL = cheaper SA crush competition = bearish US crush
            sa_signals.append(zl_df["brl_zscore"])
        if "fx_USDARS" in zl_df.columns:
            zl_df["ars_rate"] = zl_df["fx_USDARS"]
            zl_df["ars_zscore"] = (
                zl_df["ars_rate"] - zl_df["ars_rate"].rolling(252).mean()
            ) / zl_df["ars_rate"].rolling(252).std()
            sa_signals.append(zl_df["ars_zscore"])
        if sa_signals:
            zl_df["sa_currency_weakness"] = pd.concat(sa_signals, axis=1).mean(axis=1)
            # Weak SA currencies = cheaper SA crush = bearish US crush
            zl_df["sa_competition_signal"] = -zl_df["sa_currency_weakness"]
            logger.info("    + SA currency features: BRL, ARS weakness indicators")

    # TARIFF bucket: Add CNY and BRL features for trade flow impact
    if bucket_name == "tariff":
        tariff_fx_signals = []
        if "fx_USDCNY" in zl_df.columns:
            zl_df["cny_tariff_rate"] = zl_df["fx_USDCNY"]
            zl_df["cny_tariff_zscore"] = (
                zl_df["cny_tariff_rate"] - zl_df["cny_tariff_rate"].rolling(252).mean()
            ) / zl_df["cny_tariff_rate"].rolling(252).std()
            tariff_fx_signals.append(zl_df["cny_tariff_zscore"])
        if "fx_USDBRL" in zl_df.columns:
            zl_df["brl_tariff_rate"] = zl_df["fx_USDBRL"]
            zl_df["brl_tariff_zscore"] = (
                zl_df["brl_tariff_rate"] - zl_df["brl_tariff_rate"].rolling(252).mean()
            ) / zl_df["brl_tariff_rate"].rolling(252).std()
            tariff_fx_signals.append(zl_df["brl_tariff_zscore"])
        if tariff_fx_signals:
            zl_df["tariff_fx_pressure"] = pd.concat(tariff_fx_signals, axis=1).mean(
                axis=1
            )
            logger.info("    + Tariff FX features: CNY/BRL pressure indicators")

    # ==========================================================================
    # 6. ADD COT FOR CONFIGURED SYMBOLS ONLY
    # ==========================================================================
    if cot_symbols and len(cot_df.columns) > 1:
        cot_cols = ["as_of_date"]
        for sym in cot_symbols:
            cot_cols.extend([c for c in cot_df.columns if c.startswith(f"cot_{sym}_")])
        cot_cols = list(set(cot_cols))
        if len(cot_cols) > 1:
            zl_df = zl_df.merge(cot_df[cot_cols], on="as_of_date", how="left")
            logger.info(f"    + COT: {len(cot_cols) - 1} features for {cot_symbols}")

    # ==========================================================================
    # 7. ADD RIN DATA (only if configured)
    # ==========================================================================
    if include_rin and len(rin_df.columns) > 1:
        zl_df = zl_df.merge(rin_df, on="as_of_date", how="left")
        # Add RIN z-scores for each RIN type
        for rin_col in [
            c
            for c in zl_df.columns
            if c.startswith("rin_") and not c.endswith("_zscore")
        ]:
            zl_df[f"{rin_col}_zscore"] = (
                zl_df[rin_col] - zl_df[rin_col].rolling(252).mean()
            ) / zl_df[rin_col].rolling(252).std()
            zl_df[f"{rin_col}_percentile"] = (
                zl_df[rin_col].rolling(252).rank(pct=True) * 100
            )
            zl_df[f"{rin_col}_momentum_21d"] = zl_df[rin_col].pct_change(21) * 100

        # D4-D6 spread (biodiesel vs ethanol RIN)
        if "rin_D4" in zl_df.columns and "rin_D6" in zl_df.columns:
            zl_df["rin_d4_d6_spread"] = zl_df["rin_D4"] - zl_df["rin_D6"]
            zl_df["rin_d4_d6_zscore"] = (
                zl_df["rin_d4_d6_spread"]
                - zl_df["rin_d4_d6_spread"].rolling(252).mean()
            ) / zl_df["rin_d4_d6_spread"].rolling(252).std()
            # D4 premium flag (biodiesel commanding premium)
            zl_df["rin_d4_premium"] = (zl_df["rin_d4_d6_spread"] > 0).astype(int)

        # RIN regime (based on D4 levels for biofuel bucket)
        if "rin_D4_zscore" in zl_df.columns:
            zl_df["rin_regime_weak"] = (zl_df["rin_D4_zscore"] < -1).astype(int)
            zl_df["rin_regime_strong"] = (zl_df["rin_D4_zscore"] > 1).astype(int)
            # RIN regime score (-1=weak, 0=neutral, 1=strong)
            zl_df["rin_regime"] = np.where(
                zl_df["rin_D4_zscore"] < -1,
                -1,
                np.where(zl_df["rin_D4_zscore"] > 1, 1, 0),
            )

        # Biofuel bucket composite signal (if this is the biofuel bucket)
        if bucket_name == "biofuel":
            biofuel_signals = []
            if "rin_D4_zscore" in zl_df.columns:
                biofuel_signals.append(zl_df["rin_D4_zscore"])
            if "biodiesel_margin_zscore" in zl_df.columns:
                biofuel_signals.append(zl_df["biodiesel_margin_zscore"])
            if "rin_d4_d6_zscore" in zl_df.columns:
                biofuel_signals.append(zl_df["rin_d4_d6_zscore"])
            if biofuel_signals:
                zl_df["biofuel_bucket_signal"] = pd.concat(
                    biofuel_signals, axis=1
                ).mean(axis=1)
                zl_df["biofuel_signal_strength"] = (
                    np.abs(zl_df["biofuel_bucket_signal"]).clip(0, 3) / 3 * 100
                )
            else:
                zl_df["biofuel_bucket_signal"] = 0
                zl_df["biofuel_signal_strength"] = 0

        logger.info(f"    + RIN: {len(rin_df.columns) - 1} types + spreads + regime")

    # ==========================================================================
    # 8. ADD USDA EXPORTS (only if configured)
    # ==========================================================================
    if include_usda and len(usda_df.columns) > 1:
        zl_df = zl_df.merge(usda_df, on="as_of_date", how="left")
        logger.info(f"    + USDA Exports: {len(usda_df.columns) - 1} features")

    # ==========================================================================
    # 9. ADD WEATHER (only if configured - mainly for palm)
    # ==========================================================================
    if include_weather and len(weather_df.columns) > 1:
        zl_df = zl_df.merge(weather_df, on="as_of_date", how="left")
        zl_df = add_weather_staleness(zl_df, time_col="as_of_date")
        logger.info(f"    + Weather: {len(weather_df.columns) - 1} features")

    # ==========================================================================
    # 10. ADD TRUMP REGIME FEATURES (only if configured)
    # ==========================================================================
    if include_trump:
        zl_df = add_trump_regime_features(zl_df)
        logger.info("    + Trump regime: 10+ features")

    # ==========================================================================
    # 11. ADD BUCKET-SPECIFIC NEWS SENTIMENT (from alt news tables via specialist_tags)
    # ==========================================================================
    # This is CRITICAL - news sentiment was loaded but NEVER merged before!
    if news_by_bucket is not None and bucket_name in news_by_bucket:
        bucket_news_df = news_by_bucket[bucket_name]
        if not bucket_news_df.empty:
            zl_df = zl_df.merge(bucket_news_df, on="as_of_date", how="left")
            # Add rolling sentiment features
            sentiment_col = f"{bucket_name}_news_sentiment_avg"
            if sentiment_col in zl_df.columns:
                # 5-day rolling sentiment average
                zl_df[f"{bucket_name}_news_sentiment_5d"] = (
                    zl_df[sentiment_col].rolling(5).mean()
                )
                # 21-day rolling sentiment average
                zl_df[f"{bucket_name}_news_sentiment_21d"] = (
                    zl_df[sentiment_col].rolling(21).mean()
                )
                # Sentiment momentum
                zl_df[f"{bucket_name}_news_sentiment_momentum"] = (
                    zl_df[sentiment_col] - zl_df[f"{bucket_name}_news_sentiment_21d"]
                )
            logger.info(
                f"    + News sentiment: {len(bucket_news_df.columns) - 1} features for {bucket_name}"
            )

    # ==========================================================================
    # FORWARD-FILL AND CLEAN
    # ==========================================================================
    zl_df = zl_df.sort_values("as_of_date")
    zl_df = zl_df.ffill()
    zl_df = zl_df.dropna(subset=["zl_close"])

    feature_cols = [c for c in zl_df.columns if c != "as_of_date"]
    expected = bucket_config.get("expected_features", 30)
    logger.info(
        f"    TOTAL: {len(zl_df):,} rows with {len(feature_cols)} features (expected ~{expected})"
    )

    return zl_df


def save_specialist_features(
    conn, bucket: str, df: pd.DataFrame, dry_run: bool = False
):
    """Save specialist features to Postgres."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would save {len(df):,} rows for bucket {bucket}")
        return

    # Convert to JSON format for storage
    insert_query = """
        INSERT INTO "training"."specialist_features" (bucket, as_of_date, features)
        VALUES (%s, %s, %s)
        ON CONFLICT (bucket, as_of_date) DO UPDATE SET features = EXCLUDED.features
    """

    batch = []
    feature_cols = [c for c in df.columns if c != "as_of_date"]

    for _, row in df.iterrows():
        features = {
            col: float(row[col]) if pd.notna(row[col]) else None for col in feature_cols
        }
        batch.append((bucket, row["as_of_date"], json.dumps(features)))

    with conn.cursor() as cur:
        # Clear existing
        cur.execute(
            'DELETE FROM "training"."specialist_features" WHERE bucket = %s', (bucket,)
        )
        # Insert new
        execute_batch(cur, insert_query, batch, page_size=500)

    conn.commit()
    logger.info(f"  Saved {len(batch):,} rows for bucket {bucket}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate specialist features from ALL data"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument(
        "--bucket", type=str, default="all", help="Specific bucket or 'all'"
    )
    parser.add_argument(
        "--start-date", type=str, default="2000-01-01", help="Start date for features"
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("ZINC-FUSION-V15: SPECIALIST FEATURE GENERATION")
    logger.info("=" * 70)
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Start date: {args.start_date}")

    conn = get_postgres_connection()

    try:
        # Load ALL data
        logger.info("\n" + "=" * 70)
        logger.info("LOADING ALL DATA SOURCES")
        logger.info("=" * 70)

        market_df = load_all_market_data(conn, args.start_date)
        # NOTE: FRED data now loaded per-bucket using Option B (bucket-aware routing)
        # This queries only 1-2 tables per bucket instead of all 7 tables
        fx_df = load_fx_data(conn)
        cot_df = load_cot_data(conn)
        usda_df = load_usda_exports(conn)
        wasde_df = load_wasde_data(conn)
        rin_df = load_rin_data(conn)
        weather_df = load_weather_data(conn)
        news_df = load_news_data(conn)  # Legacy global news
        news_by_bucket = load_news_sentiment_by_bucket(conn)  # Bucket-specific news
        whitehouse_df = load_whitehouse_actions(conn)  # WhiteHouse EOs/actions

        # Generate features for each bucket
        logger.info("\n" + "=" * 70)
        logger.info("GENERATING SPECIALIST FEATURES")
        logger.info("=" * 70)

        buckets = (
            [args.bucket] if args.bucket != "all" else list(SPECIALIST_BUCKETS.keys())
        )

        for bucket_name in buckets:
            if bucket_name not in SPECIALIST_BUCKETS:
                logger.warning(f"Unknown bucket: {bucket_name}")
                continue

            bucket_config = SPECIALIST_BUCKETS[bucket_name]

            # Option B: Load FRED data per-bucket (queries only 1-2 tables, not all 7)
            fred_df = load_fred_data_for_bucket(conn, bucket_name)

            bucket_df = generate_bucket_features(
                bucket_name,
                bucket_config,
                market_df,
                fred_df,
                fx_df,
                cot_df,
                usda_df,
                wasde_df,
                rin_df,
                weather_df,
                news_df,
                news_by_bucket=news_by_bucket,
                whitehouse_df=whitehouse_df,
            )

            save_specialist_features(conn, bucket_name, bucket_df, args.dry_run)

        logger.info("\n" + "=" * 70)
        logger.info("SPECIALIST FEATURE GENERATION COMPLETE")
        logger.info("=" * 70)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
