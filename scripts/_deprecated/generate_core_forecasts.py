#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Generate Forward Forecasts from Trained Core Model

Forecast inference under governance. This script:
1. Reads audit rows (NEVER writes them)
2. Generates P10/P50/P90 quantiles
3. Writes to forecasts.forecast_quantiles

Execution Contract:
- Audit gating is FIRST operation
- Training run ID is explicit input
- 126d is SKIPPED (not synthesized)
- Data loading matches train_core_v15.py exactly

Usage:
    python scripts/generate_core_forecasts.py --training-run-id core_v15_21d_20260102_5cc6801
    python scripts/generate_core_forecasts.py --horizon 21 --date 20260102 --git-sha 5cc6801
    python scripts/generate_core_forecasts.py --horizon all --date 20260102 --git-sha 5cc6801
"""

from __future__ import annotations

import os

os.environ["TF_USE_LEGACY_KERAS"] = "1"
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Project imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()
load_dotenv(".env.vercel")

# =============================================================================
# CONSTANTS (LOCKED)
# =============================================================================

# Model roots by horizon family
# 5d, 21d are always tactical (core_chronos2/horizon_Xd/)
# 63d, 126d are strategic but have tactical/ subfolder for one-off models
CORE_MODEL_ROOT = PROJECT_ROOT / "models" / "core_chronos2"

# Horizons that are by default tactical (1w/1m)
DEFAULT_TACTICAL_HORIZONS = [5, 21]
# Horizons that are strategic but currently using tactical models (3m/6m)
STRATEGIC_WITH_TACTICAL_HORIZONS = [63, 126]

TACTICAL_HORIZONS = [5, 21, 63]  # 63d trained with tactical features
STRATEGIC_HORIZONS = [126]


def get_model_path(horizon: int) -> Path:
    """Return full model path based on horizon.

    - 5d, 21d: models/core_chronos2/horizon_Xd/
    - 63d, 126d: models/core_chronos2/horizon_Xd/tactical/ (one-off tactical models)
    """
    base_path = CORE_MODEL_ROOT / f"horizon_{horizon}d"

    if horizon in STRATEGIC_WITH_TACTICAL_HORIZONS:
        # 3m/6m use tactical subfolder for one-off models
        return base_path / "tactical"
    else:
        # 1w/1m are directly in horizon folder
        return base_path


def get_model_root(horizon: int) -> Path:
    """Return model root based on horizon family (legacy compatibility)."""
    # For 63d tactical, return path that load_predictor will append horizon_63d to
    # This is tricky - we need the parent of where the model actually is
    if horizon in STRATEGIC_WITH_TACTICAL_HORIZONS:
        # Return a synthetic path so horizon_63d/tactical gets constructed
        return CORE_MODEL_ROOT
    else:
        return CORE_MODEL_ROOT


# Horizon allowlist - 126d now enabled (tactical model trained 2026-01-05)
ALLOWED_HORIZONS = [5, 21, 63, 126]
FORBIDDEN_HORIZONS = []  # Previously had 126d, now enabled

# Known covariates (must match train_core_v15.py exactly)
KNOWN_COVARIATES = [
    "day_of_week",
    "month",
    "quarter",
    "is_month_end",
    "is_quarter_end",
    "days_to_expiry",
]

# Exit codes
EXIT_SUCCESS = 0
EXIT_AUDIT_FAIL = 1
EXIT_MODEL_NOT_FOUND = 2
EXIT_DATA_FAIL = 3
EXIT_DB_ERROR = 4


# =============================================================================
# DATABASE CONNECTION
# =============================================================================


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


# =============================================================================
# AUDIT GATING (FIRST OPERATION - HARD REQUIREMENT)
# =============================================================================


def check_audit_approval(conn, training_run_id: str) -> Tuple[bool, Optional[str]]:
    """
    Check if training run is approved in model_core_audit.

    Returns:
        (approved, failure_reason) - approved=True if final_approved=true
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT final_approved, failure_reason, horizon
            FROM model.model_core_audit
            WHERE training_run_id = %s
        """,
            (training_run_id,),
        )

        row = cur.fetchone()

        if row is None:
            return False, f"No audit record found for {training_run_id}"

        final_approved, failure_reason, horizon = row

        if not final_approved:
            reason = failure_reason or "Audit not approved (no reason given)"
            return False, reason

        return True, None


def enforce_audit_gate(conn, training_run_id: str) -> str:
    """
    Enforce audit gate. Hard-fail if not approved.

    Returns:
        horizon string (e.g., "21d") extracted from audit record
    """
    logger.info(f"[AUDIT GATE] Checking approval for: {training_run_id}")

    approved, failure_reason = check_audit_approval(conn, training_run_id)

    if not approved:
        logger.error(f"[AUDIT GATE] FAILED: {failure_reason}")
        logger.error("Forecast generation cannot proceed without approval.")
        sys.exit(EXIT_AUDIT_FAIL)

    # Extract horizon from training_run_id
    # Format: core_v15_<horizon>_<YYYYMMDD>_<git_sha>
    parts = training_run_id.split("_")
    if len(parts) >= 3:
        horizon_str = parts[2]  # e.g., "5d", "21d", "63d"
    else:
        logger.error(f"[AUDIT GATE] Invalid training_run_id format: {training_run_id}")
        sys.exit(EXIT_AUDIT_FAIL)

    logger.info(f"[AUDIT GATE] PASSED - Horizon: {horizon_str}")
    return horizon_str


# =============================================================================
# TRAINING RUN ID HANDLING
# =============================================================================


def build_training_run_id(horizon: int, date_str: str, git_sha: str) -> str:
    """
    Build canonical training_run_id from components.

    Format: core_v15_<horizon>_<YYYYMMDD>_<git_short_sha>
    """
    return f"core_v15_{horizon}d_{date_str}_{git_sha}"


def parse_training_run_id(training_run_id: str) -> Tuple[int, str, str]:
    """
    Parse training_run_id into components.

    Returns:
        (horizon_days, date_str, git_sha)
    """
    parts = training_run_id.split("_")
    if len(parts) != 5 or parts[0] != "core" or parts[1] != "v15":
        raise ValueError(f"Invalid training_run_id format: {training_run_id}")

    horizon_str = parts[2]  # e.g., "5d"
    horizon_days = int(horizon_str.rstrip("d"))
    date_str = parts[3]
    git_sha = parts[4]

    return horizon_days, date_str, git_sha


# =============================================================================
# DATA LOADING (PARITY WITH train_core_v15.py)
# =============================================================================


def load_base_data(conn, start_date: str = "2000-01-01") -> pd.DataFrame:
    """
    Load daily ZL data with OHLCV.

    This function MUST match train_core_v15.py exactly.
    """
    logger.info(f"Loading ZL daily data from {start_date}...")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                event_date as timestamp,
                open, high, low, close, volume
            FROM "raw"."market_futures_1d"
            WHERE symbol = 'ZL'
              AND event_date >= %s
            ORDER BY event_date
        """,
            (start_date,),
        )
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=columns)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["item_id"] = "ZL"
    df["target"] = df["close"]

    logger.info(f"  Loaded {len(df):,} rows")
    return df


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add known calendar covariates.

    This function MUST match train_core_v15.py exactly.
    """
    df = df.copy()
    ts = df["timestamp"]

    df["day_of_week"] = ts.dt.dayofweek
    df["month"] = ts.dt.month
    df["quarter"] = ts.dt.quarter
    df["is_month_end"] = ts.dt.is_month_end.astype(int)
    df["is_quarter_end"] = ts.dt.is_quarter_end.astype(int)
    df["days_to_expiry"] = (15 - ts.dt.day).clip(lower=0)

    return df


def add_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add technical indicator features.

    This function MUST match train_core_v15.py exactly.
    """
    df = df.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"].fillna(0)

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    gain7 = delta.where(delta > 0, 0).rolling(7).mean()
    loss7 = (-delta.where(delta < 0, 0)).rolling(7).mean()
    rs7 = gain7 / loss7.replace(0, np.nan)
    df["rsi_7"] = 100 - (100 / (1 + rs7))

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # Bollinger Bands
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["bb_upper"] = sma20 + 2 * std20
    df["bb_lower"] = sma20 - 2 * std20
    df["bb_pct"] = (close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

    # ATR
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()

    # Volatility proxies
    df["intraday_range"] = (high - low) / close
    df["garman_klass_vol"] = (
        np.sqrt(
            0.5 * np.log(high / low) ** 2
            - (2 * np.log(2) - 1) * np.log(close / close.shift()) ** 2
        )
        .rolling(20)
        .mean()
    )
    df["parkinson_vol"] = (
        np.sqrt(np.log(high / low) ** 2 / (4 * np.log(2))).rolling(20).mean()
    )
    df["close_to_close_vol"] = close.pct_change().rolling(20).std() * np.sqrt(252)
    df["overnight_gap"] = (df["open"] / close.shift() - 1).abs()

    # Additional indicators
    # ADX (Average Directional Index)
    up_move = high.diff()
    down_move = low.shift(1) - low
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_14 = tr.ewm(alpha=1 / 14, adjust=False).mean()
    plus_di = (
        100 * plus_dm.ewm(alpha=1 / 14, adjust=False).mean() / atr_14.replace(0, np.nan)
    )
    minus_di = (
        100
        * minus_dm.ewm(alpha=1 / 14, adjust=False).mean()
        / atr_14.replace(0, np.nan)
    )
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx_14"] = dx.ewm(alpha=1 / 14, adjust=False).mean()
    df["cci_20"] = (close - sma20) / (
        0.015 * close.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
    )
    df["willr_14"] = (
        -100
        * (high.rolling(14).max() - close)
        / (high.rolling(14).max() - low.rolling(14).min())
    )
    # MFI (Money Flow Index)
    typical_price = (high + low + close) / 3.0
    volume_filled = volume.fillna(0)
    money_flow = typical_price * volume_filled
    tp_diff = typical_price.diff()
    positive_flow = money_flow.where(tp_diff > 0, 0.0)
    negative_flow = money_flow.where(tp_diff < 0, 0.0)
    positive_mf = positive_flow.rolling(14).sum()
    negative_mf = negative_flow.rolling(14).sum().abs()
    mf_ratio = positive_mf / negative_mf.replace(0, np.nan)
    df["mfi_14"] = 100 - (100 / (1 + mf_ratio))
    df["obv"] = (np.sign(close.diff()) * volume).cumsum()
    df["vwap"] = (close * volume).cumsum() / volume.cumsum()
    df["keltner_upper"] = close.ewm(span=20).mean() + 2 * df["atr_14"]
    df["keltner_lower"] = close.ewm(span=20).mean() - 2 * df["atr_14"]

    return df


def add_fundamental_features(conn, df: pd.DataFrame) -> pd.DataFrame:
    """Add fundamental features (matches train_core_v15.py for 63d strategic)."""
    df = df.copy()

    # Load FRED data
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT series_id, event_date as timestamp, value
            FROM "raw"."fred_observations_1d"
            WHERE series_id IN ('DCOILWTICO', 'VIXCLS', 'DTWEXBGS')
            ORDER BY event_date
        """
        )
        fred_rows = cur.fetchall()

    if fred_rows:
        fred_df = pd.DataFrame(fred_rows, columns=["series_id", "timestamp", "value"])
        fred_df["timestamp"] = pd.to_datetime(fred_df["timestamp"])
        fred_pivot = fred_df.pivot(
            index="timestamp", columns="series_id", values="value"
        )
        fred_pivot = fred_pivot.rename(
            columns={
                "DCOILWTICO": "wti_crude",
                "VIXCLS": "vix",
                "DTWEXBGS": "dxy_index",
            }
        )
        df = df.merge(fred_pivot, left_on="timestamp", right_index=True, how="left")

    # Load COT data
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT report_date, managed_money_net
            FROM "raw"."cftc_cot_1w"
            WHERE symbol = 'ZL'
            ORDER BY report_date
        """
        )
        cot_rows = cur.fetchall()

    if cot_rows:
        cot_df = pd.DataFrame(cot_rows, columns=["timestamp", "cot_managed_money_net"])
        cot_df["timestamp"] = pd.to_datetime(cot_df["timestamp"])
        df = pd.merge_asof(
            df.sort_values("timestamp"),
            cot_df.sort_values("timestamp"),
            on="timestamp",
            direction="backward",
        )

    # Calculate crush spread (ZS - ZL - ZM proxy)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_date as timestamp, symbol, close
            FROM "raw"."market_futures_1d"
            WHERE symbol IN ('ZS', 'ZM')
            ORDER BY event_date
        """
        )
        soy_rows = cur.fetchall()

    if soy_rows:
        soy_df = pd.DataFrame(soy_rows, columns=["timestamp", "symbol", "close"])
        soy_df["timestamp"] = pd.to_datetime(soy_df["timestamp"])
        soy_pivot = soy_df.pivot(index="timestamp", columns="symbol", values="close")
        soy_pivot["crush_spread"] = (
            soy_pivot.get("ZS", 0) * 0.022 - soy_pivot.get("ZM", 0) * 0.011
        )
        df = df.merge(
            soy_pivot[["crush_spread"]],
            left_on="timestamp",
            right_index=True,
            how="left",
        )

    # Fill placeholders for missing fundamentals
    for col in [
        "bopo_spread",
        "rin_d4_price",
        "wasde_ending_stocks",
        "wasde_production",
        "export_sales_net",
        "precip_anom",
        "temp_anom",
    ]:
        if col not in df.columns:
            df[col] = np.nan

    return df


# =============================================================================
# STRATEGIC FEATURE BUILDER (63d/126d PARITY WITH train_core_chronos.py)
# =============================================================================
# The 63d model was trained on ~900 features from all data sources.
# This function replicates load_training_data() from train_core_chronos.py
# to build the exact same feature matrix for inference.
# =============================================================================

# FRED series lists (must match train_core_chronos.py exactly)
FRED_DAILY = [
    "TEDRATE",
    "SOFR",
    "DGS10",
    "DGS2",
    "DGS1",
    "DGS5",
    "DGS7",
    "DGS20",
    "DGS30",
    "DGS1MO",
    "DGS3MO",
    "DGS6MO",
    "T10Y2Y",
    "T10Y3M",
    "T10YIE",
    "DFII5",
    "DFII7",
    "DFII10",
    "DFII20",
    "DFII30",
    "DPRIME",
    "DFF",
    "DTB3",
    "DTB6",
    "DBAA",
    "DAAA",
    "DFEDTARL",
    "DFEDTARU",
    "BAMLH0A0HYM2",
    "BAMLC0A0CM",
    "DEXCHUS",
    "DEXUSEU",
    "DEXJPUS",
    "DEXUSUK",
    "DEXCAUS",
    "DEXMXUS",
    "DEXBZUS",
    "DEXINUS",
    "DEXMAUS",
    "DEXKOUS",
    "DEXSIUS",
    "DEXTHUS",
    "DEXHKUS",
    "DEXSZUS",
    "DEXSFUS",
    "DEXTAUS",
    "DEXUSAL",
    "DEXNOUS",
    "DTWEXBGS",
    "DTWEXAFEGS",
    "DTWEXEMEGS",
    "DTWEXM",
    "DCOILWTICO",
    "DCOILBRENTEU",
    "DHHNGSP",
    "DHOILNYH",
    "VIXCLS",
    "NASDAQCOM",
    "USEPUINDXD",
]
FRED_WEEKLY = [
    "GASREGW",
    "GASDESW",
    "ICSA",
    "CCSA",
    "NFCI",
    "STLFSI",
    "STLFSI4",
    "WALCL",
    "WRESBAL",
    "MORTGAGE30US",
    "RRPONTSYD",
    "DDFUELUSGULF",
    "SP500",
]
FRED_MONTHLY = [
    "CPIAUCSL",
    "CPILFESL",
    "PCEPI",
    "PCEPILFE",
    "PCE",
    "CHNCPIALLMINMEI",
    "PPIACO",
    "WPSFD49207",
    "WPSFD49502",
    "WPUFD49116",
    "WPUFD49207",
    "WPUSI012011",
    "WPU06140341",
    "WPU01830171",
    "WPU057303",
    "PCU311224311224",
    "APU000074714",
    "CUSR0000SAF11",
    "CUSR0000SETA01",
    "CUSR0000SETA02",
    "CUSR0000SETB01",
    "CUSR0000SAH1",
    "UNRATE",
    "PAYEMS",
    "MANEMP",
    "AWHMAN",
    "CES0500000003",
    "JTSJOL",
    "M2SL",
    "TOTRESNS",
    "BOGMBASE",
    "FEDFUNDS",
    "BUSLOANS",
    "INDPRO",
    "DGORDER",
    "NEWORDER",
    "RSAFS",
    "RSXFS",
    "DSPIC96",
    "UMCSENT",
    "MICH",
    "PSAVERT",
    "HOUST",
    "PERMIT",
    "CSUSHPISA",
    "BOPGSTB",
    "BOPGTB",
    "IEABC",
    "CHNMAINLANDTPU",
    "MYAGM2CNM189N",
    "IMPCH",
    "XTEXVA01CNM667S",
    "XTIMVA01CNM667S",
    "PSOILUSDM",
    "PSOYBUSDM",
    "PPOILUSDM",
    "PROILUSDM",
    "PSUNOUSDM",
    "PCOPPUSDM",
    "PMAIZMTUSDM",
    "PWHEAMTUSDM",
    "PRICENPQUSDM",
    "PNGASEUUSDM",
    "USEPUINDXM",
    "EMVTRADEPOLEMV",
    "EPUTRADE",
    "OVXCLS",
]
FRED_QUARTERLY = [
    "GDPC1",
    "GDP",
    "DRCCLACBS",
    "B235RC1Q027SBEA",
    "CHNGDPNQDSMEI",
    "EXPGS",
    "IMPGS",
    "WPU01830161",
    "IR3TIB01CNM156N",
    "PPIFGS",
]

# Volatility proxy symbols - NOT IN TRAINED MODEL, skip
VOL_PROXY_SYMBOLS = []

# Weather variables - ONLY these 5 are in the trained 63d model
WEATHER_VARS = ["tavg_c", "tmin_c", "tmax_c", "prcp_mm", "snow_mm"]

# FX - load from fx_spot_1d table (30 pairs), NOT from FRED
# Model expects: fx_AUDUSD, fx_DEXBZUS, ..., fx_USDJPY (30 total)
FX_FROM_SPOT_TABLE = True

# COT metrics
COT_METRICS = [
    "open_interest",
    "managed_money_net",
    "managed_money_net_pct_oi",
    "prod_merc_net",
    "prod_merc_net_pct_oi",
]


def build_strategic_features(conn, start_date: str = "2000-01-01") -> pd.DataFrame:
    """
    Build strategic feature matrix for 63d/126d models.

    EXACT PARITY with load_training_data() from train_core_chronos.py.
    Builds ~900 features from all data sources.

    Returns:
        DataFrame with ts_event, target, item_id, and all 900+ feature columns
    """
    logger.info("=" * 60)
    logger.info("BUILDING STRATEGIC FEATURES (OMNI-MARKET PARITY)")
    logger.info("=" * 60)

    # =========================================================================
    # 1. BASE: Market futures (DAILY) - PIVOT ALL SYMBOLS WIDE
    # =========================================================================
    logger.info("1. Loading ALL market futures (wide pivot)...")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT symbol, event_date as ts_event, open, high, low, close, volume
            FROM "raw"."market_futures_1d"
            WHERE event_date >= %s
            ORDER BY event_date, symbol
        """,
            (start_date,),
        )
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
    df_long = pd.DataFrame(rows, columns=columns)
    df_long["ts_event"] = pd.to_datetime(df_long["ts_event"])

    n_symbols = df_long["symbol"].nunique()
    logger.info(f"   Loaded {len(df_long):,} rows, {n_symbols} symbols")

    # Create wide dataframe starting with timestamps from ZL
    zl_data = df_long[df_long["symbol"] == "ZL"][["ts_event", "close"]].copy()
    zl_data = zl_data.rename(columns={"close": "target"})
    zl_data = zl_data.set_index("ts_event")

    # Pivot each price column
    for col in ["open", "high", "low", "close", "volume"]:
        pivot = df_long.pivot(index="ts_event", columns="symbol", values=col)
        pivot.columns = [f"{sym}_{col}" for sym in pivot.columns]
        zl_data = zl_data.join(pivot, how="left")

    df = zl_data.reset_index()
    df["trade_date"] = df["ts_event"].dt.date

    n_features = len(
        [c for c in df.columns if c not in ["ts_event", "target", "trade_date"]]
    )
    logger.info(f"   Wide format: {len(df):,} rows, {n_features} symbol features")

    # =========================================================================
    # 1b. VOLATILITY PROXY FEATURES
    # =========================================================================
    logger.info("   Engineering volatility proxy features...")
    vol_features_added = 0
    for sym in VOL_PROXY_SYMBOLS:
        open_col = f"{sym}_open"
        high_col = f"{sym}_high"
        low_col = f"{sym}_low"
        close_col = f"{sym}_close"

        if close_col not in df.columns:
            continue

        if high_col in df.columns and low_col in df.columns:
            df[f"{sym}_daily_range"] = df[high_col] - df[low_col]
            df[f"{sym}_daily_range_pct"] = (df[high_col] - df[low_col]) / df[
                close_col
            ].replace(0, np.nan)
            vol_features_added += 2

        if open_col in df.columns:
            df[f"{sym}_overnight_gap"] = df[open_col] - df[close_col].shift(1)
            prev_close = df[close_col].shift(1)
            df[f"{sym}_overnight_gap_pct"] = (
                df[open_col] - prev_close
            ) / prev_close.replace(0, np.nan)
            vol_features_added += 2

        if high_col in df.columns and low_col in df.columns:
            daily_range = df[high_col] - df[low_col]
            df[f"{sym}_close_location"] = (
                df[close_col] - df[low_col]
            ) / daily_range.replace(0, np.nan)
            vol_features_added += 1

        if open_col in df.columns and high_col in df.columns and low_col in df.columns:
            daily_range = df[high_col] - df[low_col]
            df[f"{sym}_body_ratio"] = abs(
                df[close_col] - df[open_col]
            ) / daily_range.replace(0, np.nan)
            vol_features_added += 1

    logger.info(f"   Added {vol_features_added} volatility proxy features")

    # NOTE: Elite indicators were NOT included in the 63d training run.
    # They must be added to the NEXT training run, not inference.

    # =========================================================================
    # 2. FRED Economic Data - MERGE_ASOF by frequency
    # =========================================================================
    logger.info("2. Loading FRED economic data...")

    fred_long = pd.read_sql(
        """
        SELECT event_date as as_of_date, series_id, value
        FROM "raw"."fred_observations_1d"
        ORDER BY event_date, series_id
    """,
        conn,
    )
    fred_long["as_of_date"] = pd.to_datetime(fred_long["as_of_date"])
    logger.info(
        f"   Long format: {len(fred_long):,} rows, {fred_long['series_id'].nunique()} series"
    )

    daily_dates = pd.DataFrame(
        {"as_of_date": pd.to_datetime(df["ts_event"].unique())}
    ).sort_values("as_of_date")

    def merge_fred_group(series_list: list, freq_name: str) -> pd.DataFrame:
        group_data = fred_long[fred_long["series_id"].isin(series_list)]
        if group_data.empty:
            return pd.DataFrame()
        pivoted = (
            group_data.pivot_table(
                index="as_of_date", columns="series_id", values="value", aggfunc="last"
            )
            .sort_index()
            .reset_index()
        )
        merged = pd.merge_asof(
            daily_dates.sort_values("as_of_date"),
            pivoted.sort_values("as_of_date"),
            on="as_of_date",
            direction="backward",
        )
        actual_cols = [c for c in series_list if c in merged.columns]
        logger.info(f"   {freq_name}: {len(actual_cols)} series merged")
        return merged

    fred_daily = merge_fred_group(FRED_DAILY, "Daily")
    fred_weekly = merge_fred_group(FRED_WEEKLY, "Weekly")
    fred_monthly = merge_fred_group(FRED_MONTHLY, "Monthly")
    fred_quarterly = merge_fred_group(FRED_QUARTERLY, "Quarterly")

    fred_df = daily_dates.copy()
    for freq_df in [fred_daily, fred_weekly, fred_monthly, fred_quarterly]:
        if not freq_df.empty:
            other_cols = [c for c in freq_df.columns if c != "as_of_date"]
            if other_cols:
                fred_df = fred_df.merge(
                    freq_df[["as_of_date"] + other_cols], on="as_of_date", how="left"
                )

    fred_df["trade_date"] = fred_df["as_of_date"].dt.date
    fred_features = [
        c for c in fred_df.columns if c not in ("as_of_date", "trade_date")
    ]
    fred_df[fred_features] = fred_df[fred_features].bfill()
    logger.info(f"   Combined: {len(fred_features)} FRED features")

    # =========================================================================
    # 3. WEATHER Data - pivot by station
    # =========================================================================
    logger.info("3. Loading NOAA weather data...")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT station_id, event_date as as_of_date,
                   tavg_c, tmin_c, tmax_c, prcp_mm, snow_mm,
                   awnd_ms, snwd_mm, evap_mm, rhav_pct, wsfg_ms
            FROM "raw"."weather_noaa_1d"
            ORDER BY event_date, station_id
        """
        )
        weather_cols = [desc[0] for desc in cur.description]
        weather_rows = cur.fetchall()
    weather_long = pd.DataFrame(weather_rows, columns=weather_cols)
    weather_long["trade_date"] = pd.to_datetime(weather_long["as_of_date"]).dt.date

    weather_pivot_dfs = []
    for var in WEATHER_VARS:
        pivot = weather_long.pivot_table(
            index="trade_date", columns="station_id", values=var, aggfunc="first"
        )
        pivot.columns = [f"weather_{var}_{c}" for c in pivot.columns]
        weather_pivot_dfs.append(pivot)
    weather_df = pd.concat(weather_pivot_dfs, axis=1).reset_index()

    weather_features = [c for c in weather_df.columns if c != "trade_date"]
    weather_df[weather_features] = weather_df[weather_features].ffill().bfill()
    logger.info(f"   Loaded {len(weather_df.columns)-1} weather features")

    # =========================================================================
    # 4. FX Spot Data from fx_spot_1d (30 pairs - matches trained model)
    # =========================================================================
    logger.info("4. Loading FX spot data from fx_spot_1d...")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT pair, event_date as as_of_date, rate
            FROM "raw"."fx_spot_1d"
            ORDER BY event_date
        """
        )
        fx_rows = cur.fetchall()
    fx_df = pd.DataFrame(fx_rows, columns=["pair", "as_of_date", "rate"])
    fx_df["trade_date"] = pd.to_datetime(fx_df["as_of_date"]).dt.date

    fx_wide = fx_df.pivot_table(
        index="trade_date", columns="pair", values="rate", aggfunc="last"
    )
    fx_wide.columns = [f"fx_{c}" for c in fx_wide.columns]
    fx_wide = fx_wide.reset_index()
    fx_wide = fx_wide.ffill().bfill()
    logger.info(f"   Loaded {len(fx_wide.columns)-1} FX pairs")

    # =========================================================================
    # 5. CFTC COT Positioning
    # =========================================================================
    logger.info("5. Loading CFTC COT positioning...")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT report_date, symbol, open_interest, managed_money_net,
                   managed_money_net_pct_oi, prod_merc_net, prod_merc_net_pct_oi
            FROM "raw"."cftc_cot_1w"
            ORDER BY report_date, symbol
        """
        )
        cot_rows = cur.fetchall()
    cot_long = pd.DataFrame(
        cot_rows,
        columns=[
            "report_date",
            "symbol",
            "open_interest",
            "managed_money_net",
            "managed_money_net_pct_oi",
            "prod_merc_net",
            "prod_merc_net_pct_oi",
        ],
    )
    cot_long["report_date"] = pd.to_datetime(cot_long["report_date"])

    cot_pivot_dfs = []
    for metric in COT_METRICS:
        pivot = cot_long.pivot_table(
            index="report_date", columns="symbol", values=metric, aggfunc="first"
        )
        pivot.columns = [f"cot_{metric}_{c}" for c in pivot.columns]
        cot_pivot_dfs.append(pivot)
    cot_native = pd.concat(cot_pivot_dfs, axis=1).reset_index()

    cot_wide = pd.merge_asof(
        daily_dates.rename(columns={"as_of_date": "trade_date"}).assign(
            trade_date=lambda x: pd.to_datetime(x["trade_date"])
        ),
        cot_native.rename(columns={"report_date": "trade_date"}).sort_values(
            "trade_date"
        ),
        on="trade_date",
        direction="backward",
    )
    cot_features = [c for c in cot_wide.columns if c.startswith("cot_")]
    cot_wide[cot_features] = cot_wide[cot_features].bfill()
    cot_wide["trade_date"] = cot_wide["trade_date"].dt.date
    logger.info(f"   Loaded {len(cot_features)} COT features")

    # =========================================================================
    # 6. USDA Export Sales
    # =========================================================================
    logger.info("6. Loading USDA export sales...")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT report_date,
                SUM(CASE WHEN commodity = 'Soybeans' THEN net_sales_mt END) as usda_soy_net_sales,
                SUM(CASE WHEN commodity = 'Soybeans' THEN exports_mt END) as usda_soy_exports,
                SUM(CASE WHEN commodity = 'Soybean Oil' THEN net_sales_mt END) as usda_zl_net_sales,
                SUM(CASE WHEN commodity = 'Soybean Oil' THEN exports_mt END) as usda_zl_exports,
                SUM(CASE WHEN commodity = 'Soybean Meal' THEN net_sales_mt END) as usda_zm_net_sales
            FROM "raw"."usda_export_sales_1w"
            GROUP BY report_date
            ORDER BY report_date
        """
        )
        usda_rows = cur.fetchall()
    usda_native = pd.DataFrame(
        usda_rows,
        columns=[
            "report_date",
            "usda_soy_net_sales",
            "usda_soy_exports",
            "usda_zl_net_sales",
            "usda_zl_exports",
            "usda_zm_net_sales",
        ],
    )
    usda_native["report_date"] = pd.to_datetime(usda_native["report_date"])

    usda_df = pd.merge_asof(
        daily_dates.rename(columns={"as_of_date": "trade_date"}).assign(
            trade_date=lambda x: pd.to_datetime(x["trade_date"])
        ),
        usda_native.rename(columns={"report_date": "trade_date"}).sort_values(
            "trade_date"
        ),
        on="trade_date",
        direction="backward",
    )
    usda_features = [c for c in usda_df.columns if c.startswith("usda_")]
    usda_df[usda_features] = usda_df[usda_features].bfill()
    usda_df["trade_date"] = usda_df["trade_date"].dt.date
    logger.info(f"   Loaded {len(usda_features)} USDA features")

    # =========================================================================
    # 7. USDA WASDE
    # =========================================================================
    logger.info("7. Loading USDA WASDE...")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT report_date,
                SUM(CASE WHEN commodity = 'Soybeans' AND metric = 'production' THEN value END) as wasde_soy_production,
                SUM(CASE WHEN commodity = 'Soybeans' AND metric = 'exports' THEN value END) as wasde_soy_exports,
                SUM(CASE WHEN commodity = 'Soybeans' AND metric = 'ending_stocks' THEN value END) as wasde_soy_stocks,
                SUM(CASE WHEN commodity = 'Soybean Oil' AND metric = 'production' THEN value END) as wasde_zl_production,
                SUM(CASE WHEN commodity = 'Soybean Oil' AND metric = 'exports' THEN value END) as wasde_zl_exports
            FROM "raw"."usda_wasde_1m"
            GROUP BY report_date
            ORDER BY report_date
        """
        )
        wasde_rows = cur.fetchall()
    wasde_native = pd.DataFrame(
        wasde_rows,
        columns=[
            "report_date",
            "wasde_soy_production",
            "wasde_soy_exports",
            "wasde_soy_stocks",
            "wasde_zl_production",
            "wasde_zl_exports",
        ],
    )
    wasde_native["report_date"] = pd.to_datetime(wasde_native["report_date"])

    wasde_df = pd.merge_asof(
        daily_dates.rename(columns={"as_of_date": "trade_date"}).assign(
            trade_date=lambda x: pd.to_datetime(x["trade_date"])
        ),
        wasde_native.rename(columns={"report_date": "trade_date"}).sort_values(
            "trade_date"
        ),
        on="trade_date",
        direction="backward",
    )
    wasde_features = [c for c in wasde_df.columns if c.startswith("wasde_")]
    wasde_df[wasde_features] = wasde_df[wasde_features].bfill()
    wasde_df["trade_date"] = wasde_df["trade_date"].dt.date
    logger.info(f"   Loaded {len(wasde_features)} WASDE features")

    # =========================================================================
    # 8. EPA RIN Prices
    # =========================================================================
    logger.info("8. Loading EPA RIN prices...")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_date as as_of_date, rin_type, price
            FROM (
                SELECT DISTINCT ON (event_date, rin_type)
                    event_date, rin_type, price, source, created_at
                FROM "raw"."epa_rin_prices_1d"
                ORDER BY
                    event_date,
                    rin_type,
                    CASE source
                        WHEN 'epa_qlik_public' THEN 0
                        WHEN 'epa_api' THEN 1
                        ELSE 2
                    END,
                    created_at DESC
            ) t
            ORDER BY event_date
        """
        )
        rin_rows = cur.fetchall()
    rin_df = pd.DataFrame(rin_rows, columns=["as_of_date", "rin_type", "price"])
    rin_df["trade_date"] = pd.to_datetime(rin_df["as_of_date"]).dt.date
    rin_wide = rin_df.pivot_table(
        index="trade_date", columns="rin_type", values="price", aggfunc="last"
    )
    rin_wide.columns = [f"rin_{c}" for c in rin_wide.columns]
    rin_wide = rin_wide.reset_index()
    rin_features = [c for c in rin_wide.columns if c != "trade_date"]
    rin_wide[rin_features] = rin_wide[rin_features].ffill().bfill()
    logger.info(f"   Loaded {len(rin_features)} RIN features")

    # =========================================================================
    # 9. NEWS Sentiment - Model expects ONLY 3 columns:
    #    news_article_count, news_sentiment_avg, news_trump_count
    # =========================================================================
    logger.info("9. Loading news sentiment...")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_date as as_of_date, zl_sentiment, is_trump_related
                FROM "raw"."news_articles_1d"
                ORDER BY event_date
            """
            )
            news_rows = cur.fetchall()

        news_raw = pd.DataFrame(
            news_rows, columns=["as_of_date", "zl_sentiment", "is_trump_related"]
        )
        news_raw["trade_date"] = pd.to_datetime(news_raw["as_of_date"]).dt.date

        news_agg = news_raw.groupby("trade_date").agg(
            {
                "zl_sentiment": "mean",
                "is_trump_related": "sum",
            }
        )
        news_agg.columns = ["news_sentiment_avg", "news_trump_count"]
        news_agg = news_agg.reset_index()
        news_agg["news_article_count"] = news_raw.groupby("trade_date").size().values

        # Keep only the 3 columns the model expects
        news_df = news_agg[
            [
                "trade_date",
                "news_article_count",
                "news_sentiment_avg",
                "news_trump_count",
            ]
        ]
        news_df = news_df.fillna(0)

        logger.info(f"   Computed 3 news features (model expects exactly these)")
    except Exception as e:
        logger.warning(f"   News sentiment failed: {e}, creating empty frame")
        news_df = pd.DataFrame({"trade_date": df["trade_date"].unique()})
        news_df["news_article_count"] = 0
        news_df["news_sentiment_avg"] = 0.0
        news_df["news_trump_count"] = 0

    # =========================================================================
    # JOIN ALL DATA TO DAILY BASE
    # =========================================================================
    logger.info("=" * 60)
    logger.info("JOINING ALL FEATURES TO DAILY BASE")
    logger.info("=" * 60)

    logger.info(f"  Base: {len(df):,} rows")

    # Join FRED
    df = df.merge(fred_df, on="trade_date", how="left")
    logger.info(f"  + FRED: {len(fred_features)} features")

    # Join Weather (lagged by 1 day)
    weather_df_lagged = weather_df.copy()
    weather_df_lagged["trade_date"] = pd.to_datetime(
        weather_df_lagged["trade_date"]
    ) + pd.Timedelta(days=1)
    weather_df_lagged["trade_date"] = weather_df_lagged["trade_date"].dt.date
    df = df.merge(weather_df_lagged, on="trade_date", how="left")
    logger.info(f"  + Weather: {len(weather_features)} features (lagged 1d)")

    # Join FX
    df = df.merge(fx_wide, on="trade_date", how="left")
    logger.info(f"  + FX: {len(fx_wide.columns)-1} features")

    # Join COT
    df = df.merge(cot_wide, on="trade_date", how="left")
    logger.info(f"  + COT: {len(cot_features)} features")

    # Join USDA
    df = df.merge(usda_df, on="trade_date", how="left")
    logger.info(f"  + USDA: {len(usda_features)} features")

    # Join WASDE
    df = df.merge(wasde_df, on="trade_date", how="left")
    logger.info(f"  + WASDE: {len(wasde_features)} features")

    # Join RIN
    df = df.merge(rin_wide, on="trade_date", how="left")
    logger.info(f"  + RIN: {len(rin_features)} features")

    # Join News
    df = df.merge(news_df, on="trade_date", how="left")
    logger.info(f"  + News: {len(news_df.columns)-1} features")

    # Drop trade_date helper column
    df = df.drop(columns=["trade_date"])

    # Sort by timestamp and fill all NaNs
    df = df.sort_values("ts_event")
    logger.info("  Filling NaN values (ffill then bfill)...")
    df = df.ffill()
    df = df.bfill()

    # Fill any remaining with 0
    remaining_nans = df.isna().sum().sum()
    if remaining_nans > 0:
        logger.warning(f"  Filled {remaining_nans} remaining NaNs with 0")
        df = df.fillna(0)

    # Drop rows with no target
    df = df.dropna(subset=["target"])

    # Add item_id for TimeSeriesDataFrame
    df["item_id"] = "ZL"

    feature_cols = [c for c in df.columns if c not in ["ts_event", "target", "item_id"]]
    logger.info("=" * 60)
    logger.info(f"FINAL DATASET: {len(df):,} rows, {len(feature_cols)} features")
    logger.info("=" * 60)

    return df


def prepare_forecast_data(conn, horizon: int) -> Tuple[any, datetime]:
    """
    Prepare data for forecast generation.

    Uses different loading logic based on horizon family:
    - Tactical (5d/21d): Simple ZL data with calendar/technical features
    - Strategic (63d/126d): Full 900+ feature matrix matching training
    """
    from autogluon.timeseries import TimeSeriesDataFrame

    # Strategic horizons need full feature parity with training
    if horizon in STRATEGIC_HORIZONS:
        logger.info(f"Strategic horizon {horizon}d: Building full feature matrix...")
        start_date = "2000-01-01"
        df = build_strategic_features(conn, start_date)

        # Get as-of date (last date in data)
        as_of_date = df["ts_event"].max()
        logger.info(f"  As-of date: {as_of_date.date()}")

        # Convert to TimeSeriesDataFrame
        ts_data = TimeSeriesDataFrame.from_data_frame(
            df,
            id_column="item_id",
            timestamp_column="ts_event",
        )

        logger.info(f"  Prepared {len(ts_data)} rows, {len(ts_data.columns)} features")
        return ts_data, as_of_date

    # Tactical horizons use simpler feature set
    logger.info(f"Tactical horizon {horizon}d: Using simple feature set...")
    from datetime import timedelta

    start_date = (datetime.now() - timedelta(days=7 * 365)).strftime("%Y-%m-%d")

    # Load base data
    df = load_base_data(conn, start_date)

    # Add features
    df = add_calendar_features(df)
    df = add_technical_features(df)

    # 63d was trained as "strategic" with fundamental features
    if horizon == 63:
        df = add_fundamental_features(conn, df)

    # Forward-fill then back-fill NaNs (matches training)
    df = df.ffill().bfill()

    # Get as-of date (last date in data)
    as_of_date = df["timestamp"].max()
    logger.info(f"  As-of date: {as_of_date.date()}")

    # Convert to TimeSeriesDataFrame
    ts_data = TimeSeriesDataFrame.from_data_frame(
        df,
        id_column="item_id",
        timestamp_column="timestamp",
    )

    logger.info(f"  Prepared {len(ts_data)} rows, {len(ts_data.columns)} features")

    return ts_data, as_of_date


# =============================================================================
# MODEL LOADING
# =============================================================================


def load_predictor(horizon: int, training_run_id: str):
    """
    Load model artifacts and validate against training_run_id.
    """
    from autogluon.timeseries import TimeSeriesPredictor

    model_dir = get_model_path(horizon)

    if not model_dir.exists():
        logger.error(f"Model directory not found: {model_dir}")
        sys.exit(EXIT_MODEL_NOT_FOUND)

    predictor_file = model_dir / "predictor.pkl"
    if not predictor_file.exists():
        logger.error(f"Predictor not found: {predictor_file}")
        sys.exit(EXIT_MODEL_NOT_FOUND)

    logger.info(f"Loading predictor from {model_dir}")
    predictor = TimeSeriesPredictor.load(str(model_dir))

    logger.info(f"  Best model: {predictor.model_best}")
    logger.info(f"  Prediction length: {predictor.prediction_length}")

    # Validate prediction length matches horizon
    if predictor.prediction_length != horizon:
        logger.error(
            f"Prediction length mismatch: {predictor.prediction_length} != {horizon}"
        )
        sys.exit(EXIT_MODEL_NOT_FOUND)

    return predictor


# =============================================================================
# MODEL CHANGE DETECTION
# =============================================================================


def check_model_change(
    conn, horizon: int, training_run_id: str
) -> Tuple[bool, Optional[str]]:
    """
    Check if model has changed since last forecast.

    Returns:
        (needs_regeneration, previous_run_id)
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT model_name, MAX(created_at)
            FROM forecasts.forecast_quantiles
            WHERE horizon = %s
            GROUP BY model_name
            ORDER BY MAX(created_at) DESC
            LIMIT 1
        """,
            (horizon,),
        )

        row = cur.fetchone()

        if row is None:
            return True, None  # No previous forecasts

        previous_model_name = row[0]

        # Model name IS training_run_id - direct compare
        if previous_model_name != training_run_id:
            return True, previous_model_name

        return False, previous_model_name


# =============================================================================
# FORECAST GENERATION
# =============================================================================


def validate_known_covariates(predictor) -> bool:
    """
    Validate predictor's known_covariates_names.

    Strategic horizons (63d+): Chronos2 trained with past_covariates only
    Tactical horizons (5d/21d): Trained with known_covariates (calendar features)

    Returns:
        True if model expects known_covariates (must provide them)
        False if model has no known_covariates (predict without them)
    """
    model_covariates = predictor.known_covariates_names or []

    if not model_covariates:
        logger.info("  Model uses past_covariates only (no known_covariates)")
        logger.info("  Will predict without future calendar features")
        return False

    if set(model_covariates) != set(KNOWN_COVARIATES):
        logger.error("KNOWN_COVARIATES MISMATCH DETECTED")
        logger.error(f"  Model expects: {sorted(model_covariates)}")
        logger.error(f"  Script defines: {sorted(KNOWN_COVARIATES)}")
        raise ValueError(
            f"Known covariates mismatch: model={sorted(model_covariates)}, "
            f"script={sorted(KNOWN_COVARIATES)}"
        )

    logger.info(f"  Known covariates validated: {sorted(KNOWN_COVARIATES)}")
    return True


def generate_future_known_covariates(
    as_of_date: datetime, horizon: int
) -> pd.DataFrame:
    """
    Generate known covariates (calendar features) for future prediction dates.

    The model was trained with known_covariates_names, so we must provide
    these for the prediction horizon.
    """
    from autogluon.timeseries import TimeSeriesDataFrame

    # Generate future business dates (B = business day)
    future_dates = pd.bdate_range(
        start=as_of_date + pd.Timedelta(days=1), periods=horizon, freq="B"
    )

    # Create DataFrame with item_id and calendar features
    df = pd.DataFrame(
        {
            "item_id": ["ZL"] * len(future_dates),
            "timestamp": future_dates,
        }
    )

    # Add calendar features (must match add_calendar_features exactly)
    ts = df["timestamp"]
    df["day_of_week"] = ts.dt.dayofweek
    df["month"] = ts.dt.month
    df["quarter"] = ts.dt.quarter
    df["is_month_end"] = ts.dt.is_month_end.astype(int)
    df["is_quarter_end"] = ts.dt.is_quarter_end.astype(int)
    df["days_to_expiry"] = (15 - ts.dt.day).clip(lower=0)

    # Convert to TimeSeriesDataFrame
    known_covariates = TimeSeriesDataFrame.from_data_frame(
        df, id_column="item_id", timestamp_column="timestamp"
    )

    logger.info(f"  Generated known_covariates for {len(future_dates)} future dates")
    logger.info(
        f"  Future date range: {future_dates[0].date()} to {future_dates[-1].date()}"
    )

    return known_covariates


def generate_quantile_forecasts(
    predictor, ts_data, horizon: int, as_of_date: datetime
) -> pd.DataFrame:
    """
    Generate P10/P50/P90 quantile forecasts.

    Args:
        predictor: Loaded TimeSeriesPredictor
        ts_data: TimeSeriesDataFrame with historical data
        horizon: Forecast horizon in days
        as_of_date: The date we are forecasting FROM
    """
    logger.info(f"Generating {horizon}d quantile forecasts...")

    # Check if model expects known_covariates
    needs_known_covariates = validate_known_covariates(predictor)

    if needs_known_covariates:
        # Tactical models (21d): Generate and pass known_covariates
        known_covariates = generate_future_known_covariates(as_of_date, horizon)
        predictions = predictor.predict(ts_data, known_covariates=known_covariates)
    else:
        # Strategic models (63d): Predict without known_covariates
        predictions = predictor.predict(ts_data)

    logger.info(f"  Generated {len(predictions)} prediction rows")
    logger.info(f"  Columns: {list(predictions.columns)}")

    return predictions


# =============================================================================
# WRITE PATH
# =============================================================================


def save_forecasts(
    conn,
    predictions: pd.DataFrame,
    horizon: int,
    training_run_id: str,
    as_of_date: datetime,
) -> int:
    """
    Save forecasts to forecasts.forecast_quantiles.

    Enforces idempotency: replaces existing rows for same (model_name, horizon, forecast_date).
    """
    # Extract quantile columns
    p10_col = "0.1" if "0.1" in predictions.columns else "mean"
    p50_col = "0.5" if "0.5" in predictions.columns else "mean"
    p90_col = "0.9" if "0.9" in predictions.columns else "mean"

    logger.info(f"  Using columns: p10={p10_col}, p50={p50_col}, p90={p90_col}")

    # Model name IS training_run_id for full traceability
    model_name = training_run_id

    # Clear existing forecasts for this model/horizon
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM forecasts.forecast_quantiles
            WHERE model_name = %s AND horizon = %s
        """,
            (model_name, horizon),
        )
    conn.commit()
    logger.info(f"  Cleared existing forecasts for {model_name} @ {horizon}d")

    # Prepare batch insert
    batch = []
    created_at = datetime.now()

    for idx, row in predictions.iterrows():
        # idx is (item_id, timestamp) tuple
        if isinstance(idx, tuple):
            target_date = idx[1]
            symbol = idx[0]
        else:
            target_date = idx
            symbol = "ZL"

        # Convert to date
        if hasattr(target_date, "date"):
            target_date = target_date.date()

        batch.append(
            (
                model_name,
                horizon,
                as_of_date.date(),
                target_date,
                symbol,
                float(row[p10_col]) if pd.notna(row[p10_col]) else None,
                float(row[p50_col]) if pd.notna(row[p50_col]) else None,
                float(row[p90_col]) if pd.notna(row[p90_col]) else None,
                created_at,
            )
        )

    # Plain INSERT - idempotency already handled by DELETE above
    insert_query = """
        INSERT INTO forecasts.forecast_quantiles
            (model_name, horizon, forecast_date, target_date, symbol, p10, p50, p90, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=100)
    conn.commit()

    logger.info(f"  Saved {len(batch)} forecasts to forecasts.forecast_quantiles")
    return len(batch)


# =============================================================================
# MAIN EXECUTION
# =============================================================================


def generate_forecast_for_horizon(
    conn, training_run_id: str, force: bool = False
) -> int:
    """
    Generate forecast for a single horizon (derived from training_run_id).

    EXECUTION ORDER (LOCKED):
    1. Parse horizon from training_run_id
    2. Check horizon allowlist (skip forbidden)
    3. AUDIT GATE (first governance check)
    4. Model change detection
    5. Load predictor
    6. Load data
    7. Generate forecasts
    8. Write to database

    Returns:
        Number of rows written, or 0 if skipped
    """
    # Step 1: Parse horizon from training_run_id
    horizon, date_str, git_sha = parse_training_run_id(training_run_id)

    logger.info("=" * 60)
    logger.info(f"GENERATING FORECAST: {training_run_id}")
    logger.info("=" * 60)

    # Step 2: Check horizon allowlist (before any expensive operations)
    if horizon in FORBIDDEN_HORIZONS:
        logger.info(f"horizon={horizon}d status=SKIPPED reason=FORBIDDEN_HORIZON")
        return 0

    if horizon not in ALLOWED_HORIZONS:
        logger.info(f"horizon={horizon}d status=SKIPPED reason=NOT_IN_ALLOWLIST")
        return 0

    # Step 3: AUDIT GATE (FIRST GOVERNANCE CHECK - before model/data loading)
    enforce_audit_gate(conn, training_run_id)

    # Step 4: Model change detection
    needs_regen, previous_run = check_model_change(conn, horizon, training_run_id)

    if not needs_regen and not force:
        logger.info(f"Forecasts up-to-date for {training_run_id}")
        logger.info(f"  Previous run: {previous_run}")
        logger.info(f"  Use --force to regenerate")
        return 0

    if previous_run:
        logger.info(f"  Model changed: {previous_run} -> {training_run_id}")

    # Step 5: Load predictor
    predictor = load_predictor(horizon, training_run_id)

    # Step 6: Load data (with parity to training)
    ts_data, as_of_date = prepare_forecast_data(conn, horizon)

    # Step 7: Generate forecasts
    predictions = generate_quantile_forecasts(predictor, ts_data, horizon, as_of_date)

    # Step 8: Write to database
    rows_written = save_forecasts(
        conn, predictions, horizon, training_run_id, as_of_date
    )

    logger.info(f"\n{'='*60}")
    logger.info(f"FORECAST COMPLETE: {training_run_id}")
    logger.info(f"  Horizon: {horizon}d")
    logger.info(f"  As-of date: {as_of_date.date()}")
    logger.info(f"  Rows written: {rows_written}")
    logger.info(f"{'='*60}")

    return rows_written


def main():
    parser = argparse.ArgumentParser(
        description="Generate forward forecasts from trained Core model"
    )

    # Option 1: Explicit training_run_id
    parser.add_argument(
        "--training-run-id",
        type=str,
        help="Full training run ID (e.g., core_v15_21d_20260102_5cc6801)",
    )

    # Option 2: Build training_run_id from components
    parser.add_argument(
        "--horizon", type=str, help="Horizon in days (5, 21, 63) or 'all'"
    )
    parser.add_argument("--date", type=str, help="Training date (YYYYMMDD)")
    parser.add_argument("--git-sha", type=str, help="Git short SHA")

    # Flags
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even if model unchanged",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.training_run_id:
        training_run_ids = [args.training_run_id]
    elif args.horizon and args.date and args.git_sha:
        if args.horizon.lower() == "all":
            training_run_ids = [
                build_training_run_id(h, args.date, args.git_sha)
                for h in ALLOWED_HORIZONS
            ]
        else:
            horizon = int(args.horizon)
            training_run_ids = [build_training_run_id(horizon, args.date, args.git_sha)]
    else:
        parser.error(
            "Provide either --training-run-id or (--horizon, --date, --git-sha)"
        )

    # Connect to database
    try:
        conn = get_postgres_connection()
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(EXIT_DB_ERROR)

    # Process each training run
    total_rows = 0
    try:
        for training_run_id in training_run_ids:
            try:
                rows = generate_forecast_for_horizon(conn, training_run_id, args.force)
                total_rows += rows
            except SystemExit:
                raise  # Re-raise audit failures
            except Exception as e:
                logger.error(f"Failed for {training_run_id}: {e}")
                raise
    finally:
        conn.close()

    logger.info("\n" + "=" * 60)
    logger.info("FORECAST GENERATION COMPLETE")
    logger.info(f"  Total rows written: {total_rows}")
    logger.info("=" * 60)

    sys.exit(EXIT_SUCCESS)


if __name__ == "__main__":
    main()
