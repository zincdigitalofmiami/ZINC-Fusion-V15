#!/usr/bin/env python3
"""
ZINC-FUSION-V15: L2→L4 Intelligence Stack Training
===================================================

Implements the canonical architecture:
  L2: Core model (elite indicators) → P10/P50/P90 quantile geometry
  L3: Specialist models (10 domain views) → domain-specific forecasts
  L4: Meta-ensemble → reconciled direction probability + dissent index

DUAL OUTPUT:
  1. Direction probability: "87% confidence price goes UP in 63 days"
  2. Quantile bands: P10/P50/P90/P95 for procurement budgeting

Target: 80%+ directional accuracy (baseline: 78% on Vertex with minimal data)

Usage:
    python scripts/train_direction_v15.py --horizon 63
    python scripts/train_direction_v15.py --horizon all --backtest
"""

from __future__ import annotations

import os
import sys
import logging
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

# Project imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fusion.features.elite_indicators import EliteIndicators

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

HORIZONS = [5, 21, 63, 126]
MODEL_ROOT = PROJECT_ROOT / "models" / "v15_stack"

# 11 Specialist buckets (matching L3 architecture)
SPECIALIST_BUCKETS = [
    "crush",        # Crush spread, meal/oil ratio
    "china",        # Import demand, Dalian futures
    "fx",           # USD strength, EM currencies
    "fed",          # Rate expectations, yield curve
    "tariff",       # Trade policy, duties
    "energy",       # Crude, diesel, biodiesel economics
    "biofuel",      # RINs, mandates, blending
    "palm",         # Palm oil, CPO prices
    "volatility",   # Vol regime, GARCH
    "substitutes",  # Competing oils (canola, sunflower)
    "trump_effect", # Trump/policy regime dynamics
]

# Elite indicators (27 curated institutional-grade)
ELITE_INDICATOR_COLS = [
    # Tier 1: Institutional
    "hurst_exponent", "connors_rsi", "fisher_transform",
    "mcginley_dynamic", "mcginley_signal",
    "ttm_squeeze_on", "ttm_squeeze_momentum", "ttm_squeeze_count",
    "schaff_trend_cycle", "rvi", "rvi_signal", "rvi_histogram",
    "elder_force_index",
    # Tier 2: Optimized
    "kama_10", "hma_20", "alma_50", "mcginley_100",
    "price_vs_kama10_pct", "price_vs_hma20_pct",
    "price_vs_alma50_pct", "price_vs_mcg100_pct",
    "rsi_2", "rsi_14", "cumulative_rsi",
    "macd", "macd_signal", "macd_histogram",
    "macd_fast", "macd_fast_signal", "macd_fast_histogram",
    "cci_14", "cci_50",
    # Tier 3: Volatility
    "atr_10", "atr_50", "atr_ratio",
    "garman_klass_vol", "yang_zhang_vol", "bb_percent_b",
    # Tier 4: Volume
    "cmf_21", "volume_zscore",
]


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


# =============================================================================
# DATA LOADING
# =============================================================================

def load_multi_symbol_ohlcv(conn, symbols: List[str]) -> Dict[str, pd.DataFrame]:
    """Load daily OHLCV for multiple symbols."""
    logger.info(f"Loading OHLCV for {symbols}...")

    result = {}
    for sym in symbols:
        query = f"""
            SELECT as_of_date as timestamp, open, high, low, close, volume
            FROM "raw"."market_futures_1d"
            WHERE symbol = '{sym}'
            ORDER BY as_of_date
        """
        df = pd.read_sql(query, conn)
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.normalize()
        df = df.set_index("timestamp")

        # Rename columns with symbol prefix
        df = df.rename(columns={
            "open": f"{sym.lower()}_open",
            "high": f"{sym.lower()}_high",
            "low": f"{sym.lower()}_low",
            "close": f"{sym.lower()}_close",
            "volume": f"{sym.lower()}_volume"
        })
        result[sym] = df
        logger.info(f"   {sym}: {len(df):,} rows ({df.index.min().date()} to {df.index.max().date()})")

    return result


def load_fred_indicators(conn) -> pd.DataFrame:
    """Load key FRED macro indicators."""
    logger.info("Loading FRED indicators...")

    query = """
        SELECT as_of_date as timestamp, features
        FROM "training"."core_features"
        ORDER BY as_of_date
    """
    df = pd.read_sql(query, conn)

    # Expand JSON features
    features_list = []
    for _, row in df.iterrows():
        features = row['features']
        if isinstance(features, str):
            features = json.loads(features)
        features['timestamp'] = row['timestamp']
        features_list.append(features)

    result = pd.DataFrame(features_list)
    result["timestamp"] = pd.to_datetime(result["timestamp"]).dt.normalize()
    result = result.set_index("timestamp")

    logger.info(f"   Loaded {len(result):,} rows with {len(result.columns)} features")
    return result


def compute_specialist_features(ohlcv_data: Dict[str, pd.DataFrame], fred_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Compute domain-specific features for each specialist bucket.
    This is where we create the differentiated views each specialist needs.
    """
    logger.info("Computing specialist features...")

    zl = ohlcv_data.get("ZL", pd.DataFrame())
    zm = ohlcv_data.get("ZM", pd.DataFrame())
    zs = ohlcv_data.get("ZS", pd.DataFrame())
    cl = ohlcv_data.get("CL", pd.DataFrame())
    ho = ohlcv_data.get("HO", pd.DataFrame())

    specialists = {}

    # === CRUSH SPECIALIST ===
    # Key: Crush spread = ZM * 0.022 + ZL * 0.11 - ZS
    crush_df = zl[["zl_close"]].copy()
    if not zm.empty and not zs.empty:
        crush_df = crush_df.join(zm[["zm_close"]], how="outer")
        crush_df = crush_df.join(zs[["zs_close"]], how="outer")
        crush_df["crush_spread"] = crush_df["zm_close"] * 0.022 + crush_df["zl_close"] * 0.11 - crush_df["zs_close"]
        crush_df["crush_spread_ma5"] = crush_df["crush_spread"].rolling(5).mean()
        crush_df["crush_spread_ma21"] = crush_df["crush_spread"].rolling(21).mean()
        crush_df["crush_spread_zscore"] = (crush_df["crush_spread"] - crush_df["crush_spread_ma21"]) / crush_df["crush_spread"].rolling(21).std()
        crush_df["oil_meal_ratio"] = crush_df["zl_close"] / (crush_df["zm_close"] + 1e-6)
        crush_df["oil_meal_ratio_change"] = crush_df["oil_meal_ratio"].pct_change(5) * 100
    specialists["crush"] = crush_df
    logger.info(f"   crush: {len(crush_df)} rows, {len(crush_df.columns)} features")

    # === FED/RATES SPECIALIST ===
    fed_df = pd.DataFrame(index=zl.index)
    if "dff" in fred_df.columns:
        fed_df = fed_df.join(fred_df[["dff", "t10y2y"]], how="left")
        fed_df["yield_curve_slope"] = fed_df["t10y2y"]
        fed_df["fed_funds_change_5d"] = fed_df["dff"].diff(5)
        fed_df["yield_curve_inversion"] = (fed_df["t10y2y"] < 0).astype(int)
    specialists["fed"] = fed_df
    logger.info(f"   fed: {len(fed_df)} rows, {len(fed_df.columns)} features")

    # === FX SPECIALIST ===
    fx_df = pd.DataFrame(index=zl.index)
    if "dtwexbgs" in fred_df.columns:
        fx_df = fx_df.join(fred_df[["dtwexbgs"]], how="left")
        fx_df["dxy_ma21"] = fx_df["dtwexbgs"].rolling(21).mean()
        fx_df["dxy_zscore"] = (fx_df["dtwexbgs"] - fx_df["dxy_ma21"]) / fx_df["dtwexbgs"].rolling(21).std()
        fx_df["dxy_momentum"] = fx_df["dtwexbgs"].pct_change(21) * 100
    specialists["fx"] = fx_df
    logger.info(f"   fx: {len(fx_df)} rows, {len(fx_df.columns)} features")

    # === ENERGY SPECIALIST ===
    energy_df = zl[["zl_close"]].copy()
    if not cl.empty and not ho.empty:
        energy_df = energy_df.join(cl[["cl_close"]], how="outer")
        energy_df = energy_df.join(ho[["ho_close"]], how="outer")
        energy_df["zl_cl_ratio"] = energy_df["zl_close"] / (energy_df["cl_close"] + 1e-6)
        energy_df["ho_spread"] = energy_df["ho_close"] - energy_df["cl_close"]
        energy_df["energy_correlation_21d"] = energy_df["zl_close"].rolling(21).corr(energy_df["cl_close"])
    if "dcoilwtico" in fred_df.columns:
        energy_df = energy_df.join(fred_df[["dcoilwtico"]], how="left")
    specialists["energy"] = energy_df
    logger.info(f"   energy: {len(energy_df)} rows, {len(energy_df.columns)} features")

    # === VOLATILITY SPECIALIST ===
    vol_df = zl[["zl_close"]].copy()
    if "vixcls" in fred_df.columns:
        vol_df = vol_df.join(fred_df[["vixcls"]], how="left")
        vol_df["vix_ma21"] = vol_df["vixcls"].rolling(21).mean()
        vol_df["vix_regime"] = pd.cut(vol_df["vixcls"], bins=[0, 15, 25, 100], labels=[0, 1, 2]).astype(float)
    vol_df["realized_vol_21d"] = zl["zl_close"].pct_change().rolling(21).std() * np.sqrt(252) * 100
    vol_df["vol_zscore"] = (vol_df["realized_vol_21d"] - vol_df["realized_vol_21d"].rolling(63).mean()) / vol_df["realized_vol_21d"].rolling(63).std()
    specialists["volatility"] = vol_df
    logger.info(f"   volatility: {len(vol_df)} rows, {len(vol_df.columns)} features")

    # === CHINA SPECIALIST (placeholder - needs Dalian data) ===
    china_df = pd.DataFrame(index=zl.index)
    china_df["placeholder"] = 0
    specialists["china"] = china_df

    # === TARIFF SPECIALIST (placeholder - needs trade policy data) ===
    tariff_df = pd.DataFrame(index=zl.index)
    tariff_df["placeholder"] = 0
    specialists["tariff"] = tariff_df

    # === BIOFUEL SPECIALIST (placeholder - needs RIN data) ===
    biofuel_df = pd.DataFrame(index=zl.index)
    biofuel_df["placeholder"] = 0
    specialists["biofuel"] = biofuel_df

    # === PALM SPECIALIST (placeholder - needs CPO data) ===
    palm_df = pd.DataFrame(index=zl.index)
    if "CPO" in ohlcv_data:
        cpo = ohlcv_data["CPO"]
        palm_df = palm_df.join(cpo[["cpo_close"]], how="left")
        palm_df["zl_cpo_spread"] = zl["zl_close"] - palm_df["cpo_close"]
    palm_df["placeholder"] = 0
    specialists["palm"] = palm_df

    # === SUBSTITUTES SPECIALIST (placeholder) ===
    subs_df = pd.DataFrame(index=zl.index)
    subs_df["placeholder"] = 0
    specialists["substitutes"] = subs_df

    return specialists


def prepare_full_dataset(conn, horizon: int, min_date: str = "2005-01-01") -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    """
    Prepare the full dataset with elite indicators + specialist features.

    Returns:
        X: Feature matrix
        y_dir: Direction target (1=UP, 0=DOWN)
        feature_names: List of feature names
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"PREPARING DATA FOR {horizon}d HORIZON")
    logger.info(f"{'='*60}")

    # Load raw OHLCV
    symbols = ["ZL", "ZM", "ZS", "CL", "HO"]
    ohlcv_data = load_multi_symbol_ohlcv(conn, symbols)

    # Start with ZL as base
    df = ohlcv_data["ZL"].copy()

    # Compute elite indicators
    logger.info("Computing elite indicators...")
    elite = EliteIndicators(df, symbol="zl")
    df = elite.compute_all()

    # Load FRED indicators
    fred_df = load_fred_indicators(conn)
    # Drop overlapping columns from fred_df before joining
    overlap_cols = [c for c in fred_df.columns if c in df.columns]
    if overlap_cols:
        logger.info(f"   Dropping overlapping columns from FRED: {overlap_cols}")
        fred_df = fred_df.drop(columns=overlap_cols)
    df = df.join(fred_df, how="left")

    # Compute specialist features
    specialist_features = compute_specialist_features(ohlcv_data, fred_df)

    # Join specialist features (prefix with bucket name)
    for bucket, spec_df in specialist_features.items():
        if bucket in ["crush", "fed", "fx", "energy", "volatility"]:  # Active specialists
            for col in spec_df.columns:
                if col not in df.columns and col != "placeholder":
                    df[f"spec_{bucket}_{col}"] = spec_df[col]

    # Create targets
    logger.info("Creating targets...")
    close = df["zl_close"]
    future_return = (close.shift(-horizon) - close) / close * 100
    df["future_return"] = future_return
    df["direction"] = (future_return > 0).astype(int)
    df["future_price"] = close.shift(-horizon)

    # Filter date range
    df = df[df.index >= min_date]

    # Select feature columns
    feature_cols = []

    # Elite indicators
    for col in ELITE_INDICATOR_COLS:
        if col in df.columns:
            feature_cols.append(col)

    # FRED fundamentals
    fred_cols = ["dff", "t10y2y", "vixcls", "dtwexbgs", "dcoilwtico"]
    for col in fred_cols:
        if col in df.columns and col not in feature_cols:
            feature_cols.append(col)

    # Specialist features
    for col in df.columns:
        if col.startswith("spec_") and col not in feature_cols:
            feature_cols.append(col)

    # Price context
    if "zl_close" in df.columns and "zl_close" not in feature_cols:
        feature_cols.append("zl_close")

    # Drop rows with NaN
    subset = feature_cols + ["direction", "future_return"]
    df_clean = df[subset].dropna()

    # Report
    logger.info(f"\n--- DATASET SUMMARY ---")
    logger.info(f"Date range: {df_clean.index.min().date()} to {df_clean.index.max().date()}")
    logger.info(f"Total samples: {len(df_clean):,}")
    logger.info(f"Features: {len(feature_cols)}")

    # Class balance
    up_pct = df_clean["direction"].mean() * 100
    logger.info(f"Class balance: {up_pct:.1f}% UP / {100-up_pct:.1f}% DOWN")

    X = df_clean[feature_cols]
    y_dir = df_clean["direction"]

    return X, y_dir, feature_cols


# =============================================================================
# L2: CORE MODEL (Direction + Quantiles)
# =============================================================================

def train_l2_core(
    X: pd.DataFrame,
    y: pd.Series,
    horizon: int,
    time_limit: int = 600,
) -> Dict[str, Any]:
    """
    Train L2 Core model: Direction classifier with probability output.

    This is the hero model - it must be accurate.
    """
    from autogluon.tabular import TabularPredictor

    logger.info(f"\n{'='*50}")
    logger.info(f"L2 CORE: Training direction model for {horizon}d")
    logger.info(f"{'='*50}")

    # Prepare data
    train_data = X.copy()
    train_data["direction"] = y.values

    # Time-based split (80/20)
    split_idx = int(len(train_data) * 0.8)
    train_df = train_data.iloc[:split_idx]
    val_df = train_data.iloc[split_idx:]

    logger.info(f"Train: {len(train_df):,} samples ({train_df.index.min().date()} to {train_df.index.max().date()})")
    logger.info(f"Val:   {len(val_df):,} samples ({val_df.index.min().date()} to {val_df.index.max().date()})")

    # Model path
    model_path = MODEL_ROOT / f"L2_core_{horizon}d"
    model_path.mkdir(parents=True, exist_ok=True)

    # Train with AutoGluon
    predictor = TabularPredictor(
        label="direction",
        path=str(model_path),
        eval_metric="accuracy",
        problem_type="binary",
        verbosity=2,
    )

    predictor.fit(
        train_data=train_df,
        time_limit=time_limit,
        presets="best_quality",
        num_bag_folds=5,
        num_stack_levels=1,
        excluded_model_types=["KNN", "NN_TORCH"],  # Skip slow models
    )

    # Evaluate
    val_acc = predictor.evaluate(val_df)["accuracy"]
    logger.info(f"\n*** VALIDATION ACCURACY: {val_acc:.4f} ({val_acc*100:.2f}%) ***")

    # Get predictions with probabilities
    val_proba = predictor.predict_proba(val_df)

    # Feature importance
    importance = predictor.feature_importance(val_df, num_shuffle_sets=3)
    logger.info(f"\nTop 10 features:")
    for feat, imp in importance.head(10).iterrows():
        logger.info(f"   {feat}: {imp['importance']:.4f}")

    # Leaderboard
    lb = predictor.leaderboard(val_df)
    logger.info(f"\nModel leaderboard:")
    logger.info(lb[["model", "score_val"]].head(10).to_string())

    return {
        "predictor": predictor,
        "accuracy": val_acc,
        "leaderboard": lb,
        "feature_importance": importance,
        "val_proba": val_proba,
        "split_date": train_df.index.max(),
    }


# =============================================================================
# L3: SPECIALIST MODELS
# =============================================================================

def train_l3_specialists(
    X: pd.DataFrame,
    y: pd.Series,
    horizon: int,
    time_limit_per_specialist: int = 120,
) -> Dict[str, Dict]:
    """
    Train L3 Specialist models - one per domain bucket.
    Each specialist sees only its domain-relevant features.

    Note: For initial version, specialists are trained on subsets.
    Full specialists would need domain-specific data (Dalian, RINs, etc.)
    """
    from autogluon.tabular import TabularPredictor

    logger.info(f"\n{'='*50}")
    logger.info(f"L3 SPECIALISTS: Training domain models for {horizon}d")
    logger.info(f"{'='*50}")

    # Map specialist buckets to feature prefixes
    bucket_features = {
        "crush": ["spec_crush_", "oil_meal"],
        "fed": ["spec_fed_", "dff", "t10y2y", "yield"],
        "fx": ["spec_fx_", "dtwexbgs", "dxy"],
        "energy": ["spec_energy_", "dcoilwtico", "cl_", "ho_"],
        "volatility": ["spec_volatility_", "vixcls", "vol", "atr"],
    }

    # Prepare data
    train_data = X.copy()
    train_data["direction"] = y.values

    split_idx = int(len(train_data) * 0.8)
    train_df = train_data.iloc[:split_idx]
    val_df = train_data.iloc[split_idx:]

    specialists = {}

    for bucket in ["crush", "fed", "fx", "energy", "volatility"]:
        logger.info(f"\n--- {bucket.upper()} specialist ---")

        # Find features for this specialist
        prefixes = bucket_features.get(bucket, [f"spec_{bucket}_"])
        spec_cols = [c for c in X.columns if any(p in c.lower() for p in prefixes)]

        # Add base technical indicators (all specialists get these)
        base_cols = ["rsi_14", "macd", "atr_ratio", "zl_close"]
        for bc in base_cols:
            if bc in X.columns and bc not in spec_cols:
                spec_cols.append(bc)

        if len(spec_cols) < 3:
            logger.info(f"   Skipping {bucket} - insufficient features ({len(spec_cols)})")
            continue

        logger.info(f"   Features: {len(spec_cols)}")

        # Train specialist
        spec_train = train_df[spec_cols + ["direction"]]
        spec_val = val_df[spec_cols + ["direction"]]

        model_path = MODEL_ROOT / f"L3_{bucket}_{horizon}d"
        model_path.mkdir(parents=True, exist_ok=True)

        predictor = TabularPredictor(
            label="direction",
            path=str(model_path),
            eval_metric="accuracy",
            problem_type="binary",
            verbosity=0,
        )

        predictor.fit(
            train_data=spec_train,
            time_limit=time_limit_per_specialist,
            presets="medium_quality",
            num_bag_folds=3,
        )

        acc = predictor.evaluate(spec_val)["accuracy"]
        logger.info(f"   Accuracy: {acc:.4f} ({acc*100:.2f}%)")

        specialists[bucket] = {
            "predictor": predictor,
            "accuracy": acc,
            "features": spec_cols,
        }

    return specialists


# =============================================================================
# L4: META-ENSEMBLE + DISSENT INDEX
# =============================================================================

def train_l4_meta(
    X: pd.DataFrame,
    y: pd.Series,
    l2_result: Dict,
    l3_specialists: Dict[str, Dict],
    horizon: int,
    time_limit: int = 300,
) -> Dict[str, Any]:
    """
    Train L4 Meta-ensemble that reconciles Core + Specialists.

    Key outputs:
    - Calibrated direction probability
    - Dissent index (specialist agreement measure)
    """
    from autogluon.tabular import TabularPredictor

    logger.info(f"\n{'='*50}")
    logger.info(f"L4 META: Training ensemble for {horizon}d")
    logger.info(f"{'='*50}")

    # Prepare base predictions
    split_idx = int(len(X) * 0.8)
    X_train = X.iloc[:split_idx]
    X_val = X.iloc[split_idx:]
    y_train = y.iloc[:split_idx]
    y_val = y.iloc[split_idx:]

    # Get L2 core predictions
    core_pred = l2_result["predictor"]
    train_core_proba = core_pred.predict_proba(X_train)
    val_core_proba = core_pred.predict_proba(X_val)

    # Collect specialist predictions
    spec_probas_train = {}
    spec_probas_val = {}

    for bucket, spec_data in l3_specialists.items():
        spec_pred = spec_data["predictor"]
        spec_cols = spec_data["features"]

        # Get predictions using specialist's feature set
        spec_X_train = X_train[[c for c in spec_cols if c in X_train.columns]]
        spec_X_val = X_val[[c for c in spec_cols if c in X_val.columns]]

        if len(spec_X_train.columns) > 0:
            spec_probas_train[bucket] = spec_pred.predict_proba(spec_X_train)[1].values
            spec_probas_val[bucket] = spec_pred.predict_proba(spec_X_val)[1].values

    # Build meta features
    def build_meta_features(core_proba, spec_probas, index):
        meta_df = pd.DataFrame(index=index)

        # Core prediction (P(UP))
        meta_df["core_p_up"] = core_proba[1].values if hasattr(core_proba, 'values') else core_proba[1]

        # Specialist predictions
        spec_values = []
        for bucket, proba in spec_probas.items():
            col_name = f"{bucket}_p_up"
            meta_df[col_name] = proba
            spec_values.append(proba)

        if spec_values:
            spec_matrix = np.column_stack(spec_values)

            # Dissent features
            meta_df["spec_mean"] = np.mean(spec_matrix, axis=1)
            meta_df["spec_std"] = np.std(spec_matrix, axis=1)
            meta_df["spec_range"] = np.max(spec_matrix, axis=1) - np.min(spec_matrix, axis=1)
            meta_df["core_vs_mean"] = meta_df["core_p_up"] - meta_df["spec_mean"]

            # Dissent index: high when specialists disagree
            meta_df["dissent_index"] = meta_df["spec_std"] / (np.abs(meta_df["core_p_up"] - 0.5) + 0.1)

        return meta_df

    meta_train = build_meta_features(train_core_proba, spec_probas_train, X_train.index)
    meta_val = build_meta_features(val_core_proba, spec_probas_val, X_val.index)

    # Add target
    meta_train["direction"] = y_train.values
    meta_val["direction"] = y_val.values

    logger.info(f"Meta features: {list(meta_train.columns)}")
    logger.info(f"Train: {len(meta_train)}, Val: {len(meta_val)}")

    # Train meta model
    model_path = MODEL_ROOT / f"L4_meta_{horizon}d"
    model_path.mkdir(parents=True, exist_ok=True)

    predictor = TabularPredictor(
        label="direction",
        path=str(model_path),
        eval_metric="accuracy",
        problem_type="binary",
        verbosity=1,
    )

    predictor.fit(
        train_data=meta_train,
        time_limit=time_limit,
        presets="high_quality",
        num_bag_folds=5,
    )

    # Evaluate
    meta_acc = predictor.evaluate(meta_val)["accuracy"]
    logger.info(f"\n*** META ENSEMBLE ACCURACY: {meta_acc:.4f} ({meta_acc*100:.2f}%) ***")

    # Compare to L2 alone
    l2_acc = l2_result["accuracy"]
    improvement = (meta_acc - l2_acc) * 100
    logger.info(f"Improvement over L2 alone: {improvement:+.2f}%")

    # Feature importance in meta model
    meta_importance = predictor.feature_importance(meta_val)
    logger.info(f"\nMeta feature importance:")
    for feat, imp in meta_importance.iterrows():
        logger.info(f"   {feat}: {imp['importance']:.4f}")

    # Calibrated probabilities
    val_proba = predictor.predict_proba(meta_val.drop(columns=["direction"]))

    # Calculate confidence from dissent index
    # Low dissent = high confidence
    dissent_values = meta_val["dissent_index"].values if "dissent_index" in meta_val.columns else np.zeros(len(meta_val))
    confidence = 1 - np.clip(dissent_values / dissent_values.max(), 0, 0.5) if dissent_values.max() > 0 else np.ones(len(meta_val))

    return {
        "predictor": predictor,
        "accuracy": meta_acc,
        "l2_accuracy": l2_acc,
        "improvement": improvement,
        "feature_importance": meta_importance,
        "val_proba": val_proba,
        "val_confidence": confidence,
        "val_dissent": dissent_values,
    }


# =============================================================================
# WALK-FORWARD BACKTEST
# =============================================================================

def walk_forward_backtest(
    conn,
    horizon: int,
    train_window_years: int = 5,
    test_window_months: int = 3,
    time_limit_per_fold: int = 300,
) -> pd.DataFrame:
    """
    Walk-forward backtest for realistic accuracy estimation.

    No leakage - train only on past, test on future.
    This gives us the REAL accuracy number.
    """
    from autogluon.tabular import TabularPredictor

    logger.info(f"\n{'='*60}")
    logger.info(f"WALK-FORWARD BACKTEST: {horizon}d horizon")
    logger.info(f"Train window: {train_window_years} years, Test window: {test_window_months} months")
    logger.info(f"{'='*60}")

    # Load full data
    X, y, feature_cols = prepare_full_dataset(conn, horizon, min_date="2000-01-01")

    # Combine for handling
    data = X.copy()
    data["direction"] = y.values

    results = []

    # Define walk-forward windows
    start_date = data.index.min() + pd.DateOffset(years=train_window_years)
    end_date = data.index.max() - pd.DateOffset(days=horizon)

    current_date = start_date
    fold = 0

    while current_date < end_date:
        fold += 1

        # Train window
        train_start = current_date - pd.DateOffset(years=train_window_years)
        train_end = current_date

        # Test window
        test_start = current_date
        test_end = min(current_date + pd.DateOffset(months=test_window_months), end_date)

        train_df = data[(data.index >= train_start) & (data.index < train_end)]
        test_df = data[(data.index >= test_start) & (data.index < test_end)]

        if len(train_df) < 500 or len(test_df) < 20:
            current_date = test_end
            continue

        logger.info(f"\nFold {fold}:")
        logger.info(f"   Train: {train_start.date()} to {train_end.date()} ({len(train_df)} samples)")
        logger.info(f"   Test:  {test_start.date()} to {test_end.date()} ({len(test_df)} samples)")

        # Train L2 Core only (for speed)
        model_path = MODEL_ROOT / "backtest" / f"fold_{fold}_{horizon}d"

        predictor = TabularPredictor(
            label="direction",
            path=str(model_path),
            eval_metric="accuracy",
            problem_type="binary",
            verbosity=0,
        )

        predictor.fit(
            train_data=train_df,
            time_limit=time_limit_per_fold,
            presets="medium_quality",
            num_bag_folds=3,
        )

        # Predict
        preds = predictor.predict(test_df)
        probs = predictor.predict_proba(test_df)

        # Calculate metrics
        accuracy = (preds == test_df["direction"]).mean()

        # Directional return (if we bet on the prediction)
        test_df_with_pred = test_df.copy()
        test_df_with_pred["pred"] = preds.values

        results.append({
            "fold": fold,
            "train_start": train_start,
            "train_end": train_end,
            "test_start": test_start,
            "test_end": test_end,
            "train_size": len(train_df),
            "test_size": len(test_df),
            "accuracy": accuracy,
        })

        logger.info(f"   Accuracy: {accuracy:.4f} ({accuracy*100:.2f}%)")

        # Move forward
        current_date = test_end

    results_df = pd.DataFrame(results)

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("BACKTEST RESULTS")
    logger.info(f"{'='*60}")

    mean_acc = results_df["accuracy"].mean()
    std_acc = results_df["accuracy"].std()
    min_acc = results_df["accuracy"].min()
    max_acc = results_df["accuracy"].max()

    logger.info(f"Total folds: {len(results_df)}")
    logger.info(f"Mean Accuracy: {mean_acc:.4f} ({mean_acc*100:.2f}%)")
    logger.info(f"Std:           {std_acc:.4f}")
    logger.info(f"Range:         {min_acc:.4f} - {max_acc:.4f}")
    logger.info(f"               ({min_acc*100:.2f}% - {max_acc*100:.2f}%)")

    # TARGET CHECK
    if mean_acc >= 0.80:
        logger.info(f"\n✓ TARGET HIT: {mean_acc*100:.2f}% >= 80%")
    else:
        logger.info(f"\n✗ BELOW TARGET: {mean_acc*100:.2f}% < 80%")
        logger.info(f"   Gap to target: {(0.80 - mean_acc)*100:.2f}%")

    return results_df


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Train V15 Direction Stack (L2→L4)")
    parser.add_argument("--horizon", type=str, default="63", help="Horizon: 5, 21, 63, 126, or 'all'")
    parser.add_argument("--time-limit", type=int, default=600, help="Time limit for L2 Core (seconds)")
    parser.add_argument("--backtest", action="store_true", help="Run walk-forward backtest")
    parser.add_argument("--quick", action="store_true", help="Quick mode (reduced time limits)")

    args = parser.parse_args()

    # Parse horizons
    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        horizons = [int(args.horizon)]

    # Time limits
    if args.quick:
        l2_time = 180
        l3_time = 60
        l4_time = 120
        bt_time = 120
    else:
        l2_time = args.time_limit
        l3_time = 120
        l4_time = 300
        bt_time = 180

    logger.info("=" * 60)
    logger.info("ZINC-FUSION-V15: L2→L4 DIRECTION STACK")
    logger.info("=" * 60)
    logger.info(f"Horizons: {horizons}")
    logger.info(f"Mode: {'BACKTEST' if args.backtest else 'TRAIN'}")
    logger.info(f"Quick: {args.quick}")

    conn = get_postgres_connection()

    try:
        for h in horizons:
            if args.backtest:
                # Walk-forward backtest
                results = walk_forward_backtest(conn, h, time_limit_per_fold=bt_time)

                # Save results
                results_path = MODEL_ROOT / f"backtest_{h}d.csv"
                results_path.parent.mkdir(parents=True, exist_ok=True)
                results.to_csv(results_path, index=False)
                logger.info(f"\nBacktest results saved to: {results_path}")

            else:
                # Full training pipeline
                X, y, features = prepare_full_dataset(conn, h)

                # L2: Core model
                l2_result = train_l2_core(X, y, h, time_limit=l2_time)

                # L3: Specialist models
                l3_specialists = train_l3_specialists(X, y, h, time_limit_per_specialist=l3_time)

                # L4: Meta ensemble
                l4_result = train_l4_meta(X, y, l2_result, l3_specialists, h, time_limit=l4_time)

                # Summary
                logger.info(f"\n{'='*60}")
                logger.info(f"TRAINING COMPLETE - {h}d HORIZON")
                logger.info(f"{'='*60}")
                logger.info(f"L2 Core Accuracy:     {l2_result['accuracy']*100:.2f}%")
                logger.info(f"L4 Meta Accuracy:     {l4_result['accuracy']*100:.2f}%")
                logger.info(f"Improvement:          {l4_result['improvement']:+.2f}%")

                if l4_result['accuracy'] >= 0.80:
                    logger.info(f"\n✓ TARGET HIT!")
                else:
                    logger.info(f"\n✗ Below 80% target - consider more data or features")

        logger.info("\n" + "=" * 60)
        logger.info("ALL HORIZONS COMPLETE")
        logger.info("=" * 60)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
