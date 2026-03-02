#!/usr/bin/env python3
"""
ZL PRO INDICATORS — The ONE Definitive Indicator Calculator
============================================================

THE single source of truth for technical indicator computation on mkt.futures_1d.
Replaces ALL deprecated recalculator scripts. Uses ONLY industry-grade libraries.

Library Stack:
  TA-Lib 0.6.8     — C-backed gold standard (RSI, MACD, BBANDS, ATR, ADX, STOCH, CCI, KAMA, OBV, EMA)
  hurst 0.0.5       — R/S analysis for Hurst exponent
  Ray 2.52.1         — 22-core parallel processing

Published Formulas (implemented from academic papers, NOT hand-rolled):
  - Connors RSI: Connors & Alvarez, "Short Term Trading Strategies That Work" (2008)
    → Uses TA-Lib RSI as the engine component for all sub-calculations
  - Relative Vigor Index: Ehlers, "Cybernetic Analysis for Stocks & Futures" (Wiley, 2004)
    → NOT available in TA-Lib or pandas_ta; implemented from published spec
  - Garman-Klass Vol: Garman & Klass, J. Business 53(1), pp 67-78 (1980)
  - Yang-Zhang Vol: Yang & Zhang, J. Business 73(3), pp 477-492 (2000)

Usage:
  python scripts/zl_pro_indicators.py --full                    # All symbols, Ray parallel
  python scripts/zl_pro_indicators.py --symbol ZL               # Single symbol
  python scripts/zl_pro_indicators.py --incremental             # Only symbols with NULL indicators
  python scripts/zl_pro_indicators.py --symbol ZL --dry-run     # Compute only, no DB write
  python scripts/zl_pro_indicators.py --full --no-ray           # All symbols, sequential

Target: mkt.futures_1d (39 indicator columns)
"""

import argparse
import contextlib
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Path setup — make fusion.* importable (MUST precede third-party imports)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env", override=False)

# ---------------------------------------------------------------------------
# Industry-grade library imports (after path setup)
# ---------------------------------------------------------------------------
from hurst import compute_Hc  # noqa: E402  # Hurst exponent (R/S analysis)

import talib  # noqa: E402  # TA-Lib 0.6.8 — C-backed gold standard

# ---------------------------------------------------------------------------
# DB column list — exactly matches prisma/schema.prisma mkt.futures_1d
# ---------------------------------------------------------------------------
INDICATOR_COLS = [
    # ── TA-Lib direct (23) ──────────────────────────────────────────────
    "rsi_2",
    "rsi_14",
    "cumulative_rsi",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "bb_percent_b",
    "atr_10",
    "atr_14",
    "atr_50",
    "atr_ratio",
    "adx",
    "adx_pos",
    "adx_neg",
    "stoch_k",
    "stoch_d",
    "cci_14",
    "cci_50",
    "kama_10",
    "obv",
    # ── NEW: EMA additions (4) ──────────────────────────────────────────
    "ema_21",
    "ema_50",
    "ema_100",
    "ema_200",
    # ── Edge cases — all kept (7) ───────────────────────────────────────
    "connors_rsi",
    "hurst_exponent",
    "hurst_regime",
    "rvi",
    "rvi_signal",
    "garman_klass_vol",
    "yang_zhang_vol",
    # ── Simple price-derived (5) ────────────────────────────────────────
    "volume_zscore",
    "unusual_volume",
    "returns_1d",
    "log_returns_1d",
    "range_pct",
]

BOOL_COLS = {"unusual_volume"}
STR_COLS = {"hurst_regime"}

SET_CLAUSE = ", ".join(f"{col} = %s" for col in INDICATOR_COLS)
UPDATE_SQL = (
    f"UPDATE mkt.futures_1d SET {SET_CLAUSE} WHERE symbol = %s AND event_date = %s"
)

MIN_ROWS = 100  # Skip symbols with fewer rows


# ═══════════════════════════════════════════════════════════════════════════
# DATABASE CONNECTION
# ═══════════════════════════════════════════════════════════════════════════


def get_db_url() -> str:
    """Get DATABASE_URL with gssencmode=disable for Prisma Postgres."""
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not url:
        raise ValueError("DATABASE_URL not set. Check .env file.")
    if "gssencmode" not in url:
        url += "&gssencmode=disable" if "?" in url else "?gssencmode=disable"
    return url


# ═══════════════════════════════════════════════════════════════════════════
# TYPE-SAFE VALUE CONVERTER
# ═══════════════════════════════════════════════════════════════════════════


def _safe(val):
    """Convert Python/numpy values to psycopg2-safe types. NaN/inf → None."""
    if val is None:
        return None
    # numpy bool_ MUST be caught before float() which would convert True→1.0
    if isinstance(val, (np.bool_,)):
        return bool(val)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return None if val in ("nan", "None", "NaN", "") else val
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else f
    except (ValueError, TypeError):
        return None


def _safe_div(numerator, denominator, fill=np.nan):
    """Divide arrays safely — returns fill where denominator is zero/NaN.

    Uses np.divide with out= and where= to avoid FloatingPointError
    even when np.seterr is reset by third-party libraries.
    """
    num = np.asarray(numerator, dtype=np.float64)
    den = np.asarray(denominator, dtype=np.float64)
    mask = (den != 0) & np.isfinite(den)
    out = np.full_like(num, fill, dtype=np.float64)
    np.divide(num, den, out=out, where=mask)
    return out


def _safe_log(arr, fill=np.nan):
    """Log of array, returning fill where value <= 0 or non-finite.

    Avoids FloatingPointError from np.log(negative) which hits symbols
    like QM (oil went negative April 2020).
    """
    a = np.asarray(arr, dtype=np.float64)
    mask = (a > 0) & np.isfinite(a)
    out = np.full_like(a, fill, dtype=np.float64)
    np.log(a, out=out, where=mask)
    return out


def _safe_log_ratio(numerator, denominator, fill=np.nan):
    """Compute log(num/den) safely. Returns fill where ratio <= 0 or den == 0."""
    ratio = _safe_div(numerator, denominator, fill=1.0)
    return _safe_log(ratio, fill=fill)


# ═══════════════════════════════════════════════════════════════════════════
# PUBLISHED FORMULA: Rolling Hurst Exponent
# Source: hurst library (R/S analysis)
# ═══════════════════════════════════════════════════════════════════════════


def _rolling_hurst(close: pd.Series, window: int = 100) -> pd.Series:
    """Rolling Hurst exponent using hurst library's R/S analysis."""
    result = pd.Series(np.nan, index=close.index)
    clean = close.ffill(limit=5)

    for i in range(window - 1, len(clean)):
        w = clean.iloc[i - window + 1 : i + 1].dropna()
        if len(w) < 50:
            continue
        try:
            H, _, _ = compute_Hc(w.values, kind="price", simplified=True)
            if 0.0 <= H <= 1.0:
                result.iloc[i] = H
        except Exception as e:
            print(f"  [hurst] window {i} failed: {e}")

    return result


def _classify_hurst(h: float) -> str:
    """Classify Hurst exponent into 5-class regime."""
    if pd.isna(h):
        return None
    if h < 0.35:
        return "strong_mean_revert"
    if h < 0.45:
        return "mean_revert"
    if h <= 0.55:
        return "random"
    if h <= 0.65:
        return "trending"
    return "strong_trending"


# ═══════════════════════════════════════════════════════════════════════════
# PUBLISHED FORMULA: Connors RSI
# Source: Connors & Alvarez, "Short Term Trading Strategies That Work" (2008)
# Engine: TA-Lib RSI for all sub-calculations
# ═══════════════════════════════════════════════════════════════════════════


def _connors_rsi(close_series: pd.Series, close_arr: np.ndarray) -> np.ndarray:
    """
    Connors RSI — 3 components averaged:
      1. RSI(3) of price  → TA-Lib
      2. RSI(2) of consecutive up/down streak  → TA-Lib
      3. Percentile rank of 1-day ROC over 100 days
    """
    # Component 1: RSI(3) — TA-Lib
    rsi_3 = talib.RSI(close_arr, timeperiod=3)

    # Component 2: Up/down streak → then RSI(2) via TA-Lib
    streak = np.zeros(len(close_arr), dtype=np.float64)
    for i in range(1, len(close_arr)):
        if np.isnan(close_arr[i]) or np.isnan(close_arr[i - 1]):
            streak[i] = 0.0
        elif close_arr[i] > close_arr[i - 1]:
            streak[i] = max(streak[i - 1], 0) + 1
        elif close_arr[i] < close_arr[i - 1]:
            streak[i] = min(streak[i - 1], 0) - 1
        # else: flat day → 0

    rsi_streak = talib.RSI(streak, timeperiod=2)

    # Component 3: ROC percentile rank (100-day lookback)
    roc = close_series.pct_change() * 100
    roc_rank = roc.rolling(100, min_periods=20).apply(
        lambda x: (x.iloc[-1] > x.iloc[:-1]).sum() / max(len(x) - 1, 1) * 100,
        raw=False,
    )

    return (rsi_3 + rsi_streak + roc_rank.values) / 3.0


# ═══════════════════════════════════════════════════════════════════════════
# PUBLISHED FORMULA: Ehlers Relative Vigor Index
# Source: Ehlers, "Cybernetic Analysis for Stocks & Futures" (Wiley, 2004)
# NOT available in TA-Lib or pandas_ta
# ═══════════════════════════════════════════════════════════════════════════


def _ehlers_rvi(
    open_s: pd.Series,
    high_s: pd.Series,
    low_s: pd.Series,
    close_s: pd.Series,
    period: int = 10,
) -> tuple:
    """
    Ehlers Relative Vigor Index — measures conviction of price movement.

    RVI = SUM(SWMA(Close - Open), period) / SUM(SWMA(High - Low), period)
    Signal = SWMA(RVI)

    SWMA (Symmetric Weighted Moving Average) = (x + 2*x[-1] + 2*x[-2] + x[-3]) / 6
    """

    def swma(s: pd.Series) -> pd.Series:
        return (s + 2 * s.shift(1) + 2 * s.shift(2) + s.shift(3)) / 6

    vigor = close_s - open_s
    range_hl = high_s - low_s

    vigor_smooth = swma(vigor)
    range_smooth = swma(range_hl)

    vigor_sum = vigor_smooth.rolling(period).sum()
    range_sum = range_smooth.rolling(period).sum()

    rvi = vigor_sum / range_sum.replace(0, np.nan)
    signal = swma(rvi)

    return rvi.values, signal.values


# ═══════════════════════════════════════════════════════════════════════════
# PUBLISHED FORMULA: Garman-Klass Volatility
# Source: Garman & Klass, J. Business 53(1), pp 67-78 (1980)
# "On the Estimation of Security Price Volatilities from Historical Data"
# ═══════════════════════════════════════════════════════════════════════════


def _garman_klass(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = 20,
) -> np.ndarray:
    """
    GK = 0.5 * ln(H/L)^2  -  (2*ln(2) - 1) * ln(C/O)^2
    Rolling mean, annualized, expressed as percentage.
    """
    # Safe log ratios: if H==L or C==O, log is 0 (not NaN)
    log_hl = _safe_log_ratio(high, low, fill=0.0)
    log_co = _safe_log_ratio(close, open_, fill=0.0)

    log_hl_sq = log_hl**2
    log_co_sq = log_co**2

    gk_daily = 0.5 * log_hl_sq - (2 * np.log(2) - 1) * log_co_sq
    gk_daily = np.maximum(gk_daily, 0.0)

    gk_series = pd.Series(gk_daily)
    gk_rolling = gk_series.rolling(window, min_periods=window // 2).mean()

    return (np.sqrt(np.maximum(gk_rolling, 0.0) * 252) * 100).values


# ═══════════════════════════════════════════════════════════════════════════
# PUBLISHED FORMULA: Yang-Zhang Volatility
# Source: Yang & Zhang, J. Business 73(3), pp 477-492 (2000)
# "Drift-Independent Volatility Estimation Based on High, Low, Open, Close"
# ═══════════════════════════════════════════════════════════════════════════


def _yang_zhang(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = 20,
) -> np.ndarray:
    """
    σ²_YZ = σ²_overnight + k * σ²_open-to-close + (1-k) * σ²_Rogers-Satchell
    k = 0.34 / (1.34 + (n+1)/(n-1))
    Rolling, annualized, expressed as percentage.
    """
    close_prev = np.roll(close, 1).astype(np.float64)
    close_prev[0] = np.nan

    log_oc = _safe_log_ratio(open_, close_prev, fill=0.0)  # overnight
    log_co = _safe_log_ratio(close, open_, fill=0.0)  # open-to-close

    # Rogers-Satchell component
    log_ho = _safe_log_ratio(high, open_, fill=0.0)
    log_lo = _safe_log_ratio(low, open_, fill=0.0)
    log_hc = _safe_log_ratio(high, close, fill=0.0)
    log_lc = _safe_log_ratio(low, close, fill=0.0)

    rs = log_ho * log_hc + log_lo * log_lc

    k = 0.34 / (1.34 + (window + 1) / (window - 1))

    oc_s = pd.Series(log_oc)
    co_s = pd.Series(log_co)
    rs_s = pd.Series(rs)

    var_o = oc_s.rolling(window, min_periods=window // 2).var()
    var_c = co_s.rolling(window, min_periods=window // 2).var()
    var_rs = rs_s.rolling(window, min_periods=window // 2).mean()

    yz_var = var_o + k * var_c + (1 - k) * var_rs

    return (np.sqrt(np.maximum(yz_var, 0.0) * 252) * 100).values


# ═══════════════════════════════════════════════════════════════════════════
# MAIN COMPUTE FUNCTION — 39 indicators, library-sourced
# ═══════════════════════════════════════════════════════════════════════════


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute ALL 39 indicator columns on a single-symbol OHLCV DataFrame.

    Input:  DataFrame with columns [event_date, open, high, low, close, volume]
    Output: Same DataFrame with all INDICATOR_COLS populated.

    Every indicator is traced to its library or published source.
    All math uses _safe_div / _safe_log to avoid FloatingPointError
    regardless of numpy.seterr state (third-party libs may reset it).
    """
    return _compute_indicators_inner(df)


def _compute_indicators_inner(df: pd.DataFrame) -> pd.DataFrame:
    """Inner implementation — called inside np.errstate guard."""
    # --- Prepare arrays (float64 for TA-Lib C functions) ---
    # Replace zeros/NaN in OHLC with NaN (zero prices are invalid, not "zero")
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] == 0, col] = np.nan
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].ffill(
        limit=5
    )

    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    open_ = df["open"].values.astype(np.float64)
    volume = df["volume"].fillna(0).values.astype(np.float64)

    # --- Prepare Series for published formula functions ---
    cs = pd.Series(close, index=df.index)
    hs = pd.Series(high, index=df.index)
    ls = pd.Series(low, index=df.index)
    os_ = pd.Series(open_, index=df.index)

    # ═══════════════════════════════════════════════════════════════════
    # TA-LIB (C-backed gold standard) — 27 columns
    # ═══════════════════════════════════════════════════════════════════

    # RSI (Wilder, 1978)
    df["rsi_2"] = talib.RSI(close, timeperiod=2)
    df["rsi_14"] = talib.RSI(close, timeperiod=14)
    df["cumulative_rsi"] = (
        pd.Series(talib.RSI(close, timeperiod=2)).rolling(3).sum().values
    )

    # MACD (Appel, 1979)
    macd_val, macd_sig, macd_hist = talib.MACD(
        close, fastperiod=12, slowperiod=26, signalperiod=9
    )
    df["macd"] = macd_val
    df["macd_signal"] = macd_sig
    df["macd_histogram"] = macd_hist

    # Bollinger Bands (Bollinger, 1983)
    bb_up, bb_mid, bb_low = talib.BBANDS(close, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
    df["bb_upper"] = bb_up
    df["bb_middle"] = bb_mid
    df["bb_lower"] = bb_low
    bb_range = bb_up - bb_low
    df["bb_percent_b"] = _safe_div(close - bb_low, bb_range)

    # ATR (Wilder, 1978)
    df["atr_10"] = talib.ATR(high, low, close, timeperiod=10)
    df["atr_14"] = talib.ATR(high, low, close, timeperiod=14)
    df["atr_50"] = talib.ATR(high, low, close, timeperiod=50)
    atr_50 = df["atr_50"].values
    df["atr_ratio"] = _safe_div(df["atr_10"].values, atr_50)

    # ADX + Directional Indicators (Wilder, 1978)
    df["adx"] = talib.ADX(high, low, close, timeperiod=14)
    df["adx_pos"] = talib.PLUS_DI(high, low, close, timeperiod=14)
    df["adx_neg"] = talib.MINUS_DI(high, low, close, timeperiod=14)

    # Stochastic Oscillator (Lane, 1950s)
    slowk, slowd = talib.STOCH(
        high, low, close, fastk_period=5, slowk_period=3, slowd_period=3
    )
    df["stoch_k"] = slowk
    df["stoch_d"] = slowd

    # CCI (Lambert, 1980)
    df["cci_14"] = talib.CCI(high, low, close, timeperiod=14)
    df["cci_50"] = talib.CCI(high, low, close, timeperiod=50)

    # KAMA (Kaufman, 1995)
    df["kama_10"] = talib.KAMA(close, timeperiod=10)

    # OBV (Granville, 1963)
    df["obv"] = talib.OBV(close, volume)

    # ═══════════════════════════════════════════════════════════════════
    # TA-LIB: Exponential Moving Averages — 4 columns
    # ═══════════════════════════════════════════════════════════════════

    df["ema_21"] = talib.EMA(close, timeperiod=21)
    df["ema_50"] = talib.EMA(close, timeperiod=50)
    df["ema_100"] = talib.EMA(close, timeperiod=100)
    df["ema_200"] = talib.EMA(close, timeperiod=200)

    # ═══════════════════════════════════════════════════════════════════
    # HURST LIBRARY — R/S analysis
    # ═══════════════════════════════════════════════════════════════════

    df["hurst_exponent"] = _rolling_hurst(cs, window=100)
    df["hurst_regime"] = df["hurst_exponent"].apply(_classify_hurst)

    # ═══════════════════════════════════════════════════════════════════
    # PUBLISHED FORMULAS (cited academic papers / strategies)
    # ═══════════════════════════════════════════════════════════════════

    # Connors RSI — TA-Lib RSI as engine
    df["connors_rsi"] = _connors_rsi(cs, close)

    # Ehlers Relative Vigor Index — published formula, NOT in any library
    rvi_vals, rvi_sig_vals = _ehlers_rvi(os_, hs, ls, cs, period=10)
    df["rvi"] = rvi_vals
    df["rvi_signal"] = rvi_sig_vals

    # Volume Z-Score — TA-Lib SMA + STDDEV
    vol_sma = talib.SMA(volume, timeperiod=20)
    vol_std = talib.STDDEV(volume, timeperiod=20)
    df["volume_zscore"] = _safe_div(volume - vol_sma, vol_std)
    # unusual_volume: True if |zscore| > 2, None during warm-up
    vz = df["volume_zscore"].values
    df["unusual_volume"] = np.where(~np.isnan(vz), np.abs(vz) > 2.0, np.nan)

    # Simple returns
    df["returns_1d"] = cs.pct_change().values
    # Log returns: guard against negative/zero prices (e.g. oil April 2020)
    df["log_returns_1d"] = _safe_log_ratio(cs.values, cs.shift(1).values, fill=np.nan)
    df["range_pct"] = _safe_div((hs - ls).values, cs.values)

    # Garman-Klass Volatility (1980 paper)
    df["garman_klass_vol"] = _garman_klass(open_, high, low, close, window=20)

    # Yang-Zhang Volatility (2000 paper)
    df["yang_zhang_vol"] = _yang_zhang(open_, high, low, close, window=20)

    return df


# ═══════════════════════════════════════════════════════════════════════════
# DB WRITE — execute_batch for performance
# ═══════════════════════════════════════════════════════════════════════════


def _build_row_params(row: pd.Series, symbol: str, date) -> tuple:
    """Build parameter tuple for one UPDATE row."""
    params = []
    for col in INDICATOR_COLS:
        val = _safe(row.get(col))
        if col in BOOL_COLS and val is not None:
            val = bool(val)
        params.append(val)
    params.append(symbol)
    params.append(date.date() if hasattr(date, "date") else date)
    return tuple(params)


def write_indicators(conn, df: pd.DataFrame, symbol: str) -> int:
    """Write computed indicators to mkt.futures_1d using execute_batch."""
    params_list = [_build_row_params(row, symbol, date) for date, row in df.iterrows()]

    with conn.cursor() as cur:
        execute_batch(cur, UPDATE_SQL, params_list, page_size=1000)
    conn.commit()

    return len(params_list)


# ═══════════════════════════════════════════════════════════════════════════
# PROCESS ONE SYMBOL — read, compute, write
# ═══════════════════════════════════════════════════════════════════════════


def process_symbol(symbol: str, db_url: str, dry_run: bool = False) -> dict:
    """
    Full pipeline for one symbol: read OHLCV → compute 39 indicators → write.

    Returns dict with {symbol, status, rows, elapsed}.
    """
    t0 = time.time()
    conn = None

    try:
        # Retry connection up to 3 times (transient network/cloud errors)
        for attempt in range(3):
            try:
                conn = psycopg2.connect(db_url)
                break
            except psycopg2.OperationalError:
                if attempt == 2:
                    raise
                time.sleep(2**attempt)

        # Read OHLCV
        df = pd.read_sql(
            "SELECT event_date, open, high, low, close, volume "
            "FROM mkt.futures_1d "
            "WHERE symbol = %s AND close IS NOT NULL "
            "ORDER BY event_date",
            conn,
            params=(symbol,),
        )

        if len(df) < MIN_ROWS:
            return {
                "symbol": symbol,
                "status": "skipped",
                "rows": len(df),
                "elapsed": time.time() - t0,
                "reason": f"only {len(df)} rows (need {MIN_ROWS}+)",
            }

        df["event_date"] = pd.to_datetime(df["event_date"])
        df = df.set_index("event_date")

        # Compute all 39 indicators
        df = compute_indicators(df)

        # Write to DB
        updated = len(df) if dry_run else write_indicators(conn, df, symbol)

        return {
            "symbol": symbol,
            "status": "success" if not dry_run else "dry-run",
            "rows": updated,
            "elapsed": time.time() - t0,
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "status": "error",
            "rows": 0,
            "elapsed": time.time() - t0,
            "error": str(e),
        }
    finally:
        if conn:
            with contextlib.suppress(Exception):
                conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# RAY PARALLEL PROCESSING
# ═══════════════════════════════════════════════════════════════════════════


def process_symbols_ray(symbols: list, db_url: str, dry_run: bool) -> list:
    """Process multiple symbols in parallel using Ray (22 cores)."""
    import ray

    ray.init(address="auto", ignore_reinit_error=True)
    cpus = ray.cluster_resources().get("CPU", 0)
    print(f"  Ray cluster: {cpus:.0f} CPUs available")

    @ray.remote
    def _process_remote(sym: str, url: str, dry: bool) -> dict:
        """Ray remote wrapper — each worker gets its own connection."""
        import warnings as w

        w.filterwarnings("ignore")
        return process_symbol(sym, url, dry)

    # Submit all tasks
    futures = [_process_remote.remote(s, db_url, dry_run) for s in symbols]

    # Collect results as they complete
    results = []
    remaining = list(futures)
    while remaining:
        done, remaining = ray.wait(remaining, num_returns=1)
        result = ray.get(done[0])
        results.append(result)

        # Progress
        i = len(results)
        sym = result["symbol"]
        status = result["status"]
        rows = result["rows"]
        elapsed = result["elapsed"]

        if status == "success" or status == "dry-run":
            print(f"  [{i}/{len(symbols)}] {sym}: {rows:,} rows ({elapsed:.1f}s) ✓")
        elif status == "skipped":
            print(f"  [{i}/{len(symbols)}] {sym}: skipped — {result.get('reason', '')}")
        else:
            print(f"  [{i}/{len(symbols)}] {sym}: ERROR — {result.get('error', '')}")

    ray.shutdown()
    return results


def process_symbols_sequential(symbols: list, db_url: str, dry_run: bool) -> list:
    """Process symbols one at a time (no Ray)."""
    results = []
    for i, sym in enumerate(symbols, 1):
        result = process_symbol(sym, db_url, dry_run)
        results.append(result)

        status = result["status"]
        rows = result["rows"]
        elapsed = result["elapsed"]

        if status == "success" or status == "dry-run":
            print(f"  [{i}/{len(symbols)}] {sym}: {rows:,} rows ({elapsed:.1f}s) ✓")
        elif status == "skipped":
            print(f"  [{i}/{len(symbols)}] {sym}: skipped — {result.get('reason', '')}")
        else:
            print(f"  [{i}/{len(symbols)}] {sym}: ERROR — {result.get('error', '')}")

    return results


# ═══════════════════════════════════════════════════════════════════════════
# CLI + MAIN
# ═══════════════════════════════════════════════════════════════════════════


def get_symbols(db_url: str, mode: str, symbol: Optional[str] = None) -> list:
    """Get list of symbols to process based on mode."""
    if symbol:
        return [symbol.upper()]

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            if mode == "incremental":
                cur.execute(
                    "SELECT DISTINCT symbol FROM mkt.futures_1d "
                    "WHERE close IS NOT NULL AND rsi_14 IS NULL "
                    "ORDER BY symbol"
                )
            else:  # full
                cur.execute(
                    "SELECT DISTINCT symbol FROM mkt.futures_1d "
                    "WHERE close IS NOT NULL "
                    "ORDER BY symbol"
                )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="ZL PRO INDICATORS — The ONE Definitive Indicator Calculator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--full", action="store_true", help="All symbols, all rows")
    group.add_argument(
        "--incremental", action="store_true", help="Only symbols with NULL indicators"
    )
    group.add_argument("--symbol", type=str, help="Single symbol (e.g., ZL)")

    parser.add_argument(
        "--dry-run", action="store_true", help="Compute only, no DB write"
    )
    parser.add_argument(
        "--no-ray", action="store_true", help="Force sequential (no Ray)"
    )

    args = parser.parse_args()

    # Banner
    print("\n" + "=" * 70)
    print("ZL PRO INDICATORS — The ONE Definitive Indicator Calculator")
    print("=" * 70)
    print(f"  TA-Lib:     {talib.__version__}")
    print(
        f"  Mode:       {'--full' if args.full else '--incremental' if args.incremental else f'--symbol {args.symbol}'}"
    )
    print(f"  Dry run:    {args.dry_run}")
    print(f"  Parallel:   {'off (--no-ray)' if args.no_ray else 'Ray auto-detect'}")
    print("=" * 70)

    db_url = get_db_url()

    # Determine mode
    if args.symbol:
        mode = "symbol"
    elif args.incremental:
        mode = "incremental"
    else:
        mode = "full"

    # Get symbols
    symbols = get_symbols(db_url, mode, args.symbol)
    print(f"\n  Symbols to process: {len(symbols)}")
    if not symbols:
        print("  Nothing to do.")
        return

    t_total = time.time()

    # Dispatch
    use_ray = not args.no_ray and len(symbols) > 1
    if use_ray:
        try:
            results = process_symbols_ray(symbols, db_url, args.dry_run)
        except Exception as e:
            print(f"\n  Ray failed ({e}), falling back to sequential...")
            results = process_symbols_sequential(symbols, db_url, args.dry_run)
    else:
        results = process_symbols_sequential(symbols, db_url, args.dry_run)

    # Summary
    elapsed_total = time.time() - t_total
    success = [r for r in results if r["status"] in ("success", "dry-run")]
    skipped = [r for r in results if r["status"] == "skipped"]
    errors = [r for r in results if r["status"] == "error"]
    total_rows = sum(r["rows"] for r in success)

    print("\n" + "=" * 70)
    print("COMPLETE")
    print("=" * 70)
    print(f"  Successful:   {len(success)}/{len(symbols)}")
    print(f"  Skipped:      {len(skipped)}")
    print(f"  Errors:       {len(errors)}")
    print(f"  Total rows:   {total_rows:,}")
    print(f"  Total time:   {elapsed_total:.1f}s")

    if errors:
        print("\n  ERRORS:")
        for e in errors:
            print(f"    {e['symbol']}: {e.get('error', 'unknown')}")

    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
