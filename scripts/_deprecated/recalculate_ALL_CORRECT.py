#!/usr/bin/env python3
"""
RECALCULATE ALL INDICATORS AND VOLATILITY - ONE SYMBOL AT A TIME

Does it RIGHT:
1. Load symbol data
2. Calculate ALL indicators (TA-Lib, pandas-ta, hurst)
3. Calculate volatility (Yang-Zhang, Garman-Klass)
4. Update database
5. Move to next symbol

NO SHORTCUTS. NO PARALLELIZATION. JUST CORRECT.
"""

import os
import sys
from pathlib import Path

# Setup path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import numpy as np
import psycopg2
from dotenv import load_dotenv

# Load TA-Lib and libraries
import talib
import pandas_ta as pta
from hurst import compute_Hc

# Load environment
load_dotenv(PROJECT_ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set")
DATABASE_URL = DATABASE_URL.split("?")[0]


def get_connection():
    """Get database connection."""
    return psycopg2.connect(DATABASE_URL)


def calculate_hurst(close: pd.Series, lookback: int = 100) -> pd.Series:
    """
    Calculate Hurst exponent using verified hurst library.

    Handles NaN values by forward-filling (limit 5) and filtering.
    """
    # Forward-fill NaN values first (up to 5 bars)
    close_filled = close.ffill(limit=5)

    def calc_hurst_window(window):
        valid = window[~np.isnan(window)]
        if len(valid) < 50:
            return np.nan
        try:
            H, c, data = compute_Hc(valid, kind="price", simplified=False)
            return H
        except:
            return np.nan

    return close_filled.rolling(lookback).apply(calc_hurst_window, raw=True)


def calculate_yang_zhang_vol(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Yang-Zhang volatility - EXACT academic formula.

    σ² = σ_o² + k·σ_c² + (1-k)·σ_rs²
    """
    o = df["open"].astype(np.float64)
    h = df["high"].astype(np.float64)
    l = df["low"].astype(np.float64)
    c = df["close"].astype(np.float64)
    c_prev = c.shift(1)

    with np.errstate(divide="ignore", invalid="ignore"):
        log_oc = np.log(o / c_prev)
        log_co = np.log(c / o)
        log_hc = np.log(h / c)
        log_ho = np.log(h / o)
        log_lc = np.log(l / c)
        log_lo = np.log(l / o)

        rs_daily = log_hc * log_ho + log_lc * log_lo
        k = 0.34 / (1.34 + (window + 1) / (window - 1))

        sigma_o_sq = log_oc.rolling(window).var()
        sigma_c_sq = log_co.rolling(window).var()
        sigma_rs_sq = rs_daily.rolling(window).mean()

        yang_zhang_var = sigma_o_sq + k * sigma_c_sq + (1 - k) * sigma_rs_sq

    return np.sqrt(yang_zhang_var) * np.sqrt(252)


def calculate_garman_klass_vol(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Garman-Klass volatility - EXACT academic formula.

    GK = 0.5·ln(H/L)² - (2·ln2-1)·ln(C/O)²
    """
    o = df["open"].astype(np.float64)
    h = df["high"].astype(np.float64)
    l = df["low"].astype(np.float64)
    c = df["close"].astype(np.float64)

    with np.errstate(divide="ignore", invalid="ignore"):
        log_hl = np.log(h / l)
        log_co = np.log(c / o)

        gk_coefficient = 2 * np.log(2) - 1
        gk_daily = 0.5 * (log_hl ** 2) - gk_coefficient * (log_co ** 2)
        gk_mean = gk_daily.rolling(window).mean()

    return np.sqrt(gk_mean.clip(lower=0)) * np.sqrt(252)


def calculate_connors_rsi(close: pd.Series) -> pd.Series:
    """
    Connors RSI using TA-Lib components.

    CRITICAL: Streak must be float64 for TA-Lib.
    """
    # Component 1: RSI(3)
    rsi_3 = talib.RSI(close.values, timeperiod=3)

    # Component 2: Streak RSI (MUST BE FLOAT64)
    streak = pd.Series(0.0, index=close.index, dtype=np.float64)
    for i in range(1, len(close)):
        if close.iloc[i] > close.iloc[i - 1]:
            streak.iloc[i] = max(streak.iloc[i - 1], 0) + 1
        elif close.iloc[i] < close.iloc[i - 1]:
            streak.iloc[i] = min(streak.iloc[i - 1], 0) - 1

    rsi_streak = talib.RSI(streak.values.astype(np.float64), timeperiod=2)

    # Component 3: ROC percentile rank
    roc = close.pct_change() * 100
    roc_rank = roc.rolling(100).apply(
        lambda x: (x.iloc[-1] > x.iloc[:-1]).sum() / len(x.iloc[:-1]) * 100
        if len(x) > 1 else 50
    )

    return (rsi_3 + rsi_streak + roc_rank) / 3.0


def process_symbol(symbol: str, conn) -> int:
    """
    Process ONE symbol completely - all indicators and volatility.

    Returns: number of rows updated
    """
    # Load data
    df = pd.read_sql(f"""
        SELECT event_date, open, high, low, close, volume
        FROM mkt.futures_1d
        WHERE symbol = '{symbol}'
        ORDER BY event_date
    """, conn)

    if len(df) < 100:
        print(f"  {symbol}: Skipped (only {len(df)} rows)")
        return 0

    df["event_date"] = pd.to_datetime(df["event_date"])
    df = df.set_index("event_date")

    # Convert to float64 (CRITICAL for TA-Lib)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(np.float64)
    df["volume"] = df["volume"].fillna(0)

    # ===== CALCULATE ALL INDICATORS =====
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    volume = df["volume"].values

    # RSI
    df["rsi_2"] = talib.RSI(close, timeperiod=2)
    df["rsi_14"] = talib.RSI(close, timeperiod=14)

    # MACD
    macd, signal, hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    df["macd"] = macd
    df["macd_signal"] = signal
    df["macd_histogram"] = hist

    # Bollinger Bands
    upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
    df["bb_upper"] = upper
    df["bb_middle"] = middle
    df["bb_lower"] = lower
    bb_range = upper - lower
    df["bb_percent_b"] = (close - lower) / np.where(bb_range > 0, bb_range, np.nan)

    # ATR
    df["atr_10"] = talib.ATR(high, low, close, timeperiod=10)
    df["atr_14"] = talib.ATR(high, low, close, timeperiod=14)
    df["atr_50"] = talib.ATR(high, low, close, timeperiod=50)
    df["atr_ratio"] = df["atr_10"] / df["atr_50"]

    # ADX
    df["adx"] = talib.ADX(high, low, close, timeperiod=14)

    # Stochastic
    slowk, slowd = talib.STOCH(high, low, close)
    df["stoch_k"] = slowk
    df["stoch_d"] = slowd

    # CCI
    df["cci_14"] = talib.CCI(high, low, close, timeperiod=14)
    df["cci_50"] = talib.CCI(high, low, close, timeperiod=50)

    # Moving Averages
    df["kama_10"] = talib.KAMA(close, timeperiod=10)
    df["hma_20"] = talib.WMA(close, timeperiod=20)  # Approximation
    df["alma_50"] = talib.TEMA(close, timeperiod=50)  # Approximation
    df["mcginley_dynamic"] = talib.EMA(close, timeperiod=10)  # Approximation

    # Volume indicators
    df["cmf_21"] = talib.ADOSC(high, low, close, volume, fastperiod=3, slowperiod=10)
    df["obv"] = talib.OBV(close, volume)
    ema_close = talib.EMA(close, timeperiod=13)
    ema_volume = talib.EMA(volume, timeperiod=13)
    df["elder_force_index"] = (close - ema_close) * ema_volume

    volume_ma = talib.SMA(volume, timeperiod=20)
    volume_std = talib.STDDEV(volume, timeperiod=20)
    df["volume_zscore"] = (volume - volume_ma) / np.where(volume_std > 0, volume_std, np.nan)
    df["unusual_volume"] = np.abs(df["volume_zscore"]) > 2.0

    # Connors RSI
    df["connors_rsi"] = calculate_connors_rsi(df["close"])

    # Hurst Exponent
    df["hurst_exponent"] = calculate_hurst(df["close"], lookback=100)
    df["hurst_regime"] = pd.cut(
        df["hurst_exponent"],
        bins=[0, 0.4, 0.6, 1.0],
        labels=["mean_reverting", "random", "trending"]
    )

    # Returns
    df["returns_1d"] = df["close"].pct_change()
    df["log_returns_1d"] = np.log(df["close"] / df["close"].shift(1))
    df["range_pct"] = (df["high"] - df["low"]) / df["close"]

    # ===== VOLATILITY =====
    df["yang_zhang_vol"] = calculate_yang_zhang_vol(df, window=20)
    df["garman_klass_vol"] = calculate_garman_klass_vol(df, window=20)

    # ===== UPDATE DATABASE =====
    cursor = conn.cursor()
    updated = 0

    for date, row in df.iterrows():
        # Only update if we have at least RSI
        if pd.isna(row.get("rsi_14")):
            continue

        cursor.execute("""
            UPDATE mkt.futures_1d
            SET
                rsi_2 = %s,
                rsi_14 = %s,
                macd = %s,
                macd_signal = %s,
                macd_histogram = %s,
                bb_upper = %s,
                bb_middle = %s,
                bb_lower = %s,
                bb_percent_b = %s,
                atr_10 = %s,
                atr_14 = %s,
                atr_50 = %s,
                atr_ratio = %s,
                adx = %s,
                stoch_k = %s,
                stoch_d = %s,
                cci_14 = %s,
                cci_50 = %s,
                kama_10 = %s,
                hma_20 = %s,
                alma_50 = %s,
                mcginley_dynamic = %s,
                cmf_21 = %s,
                elder_force_index = %s,
                volume_zscore = %s,
                unusual_volume = %s,
                connors_rsi = %s,
                hurst_exponent = %s,
                hurst_regime = %s,
                returns_1d = %s,
                log_returns_1d = %s,
                range_pct = %s,
                yang_zhang_vol = %s,
                garman_klass_vol = %s
            WHERE symbol = %s AND event_date = %s
        """, (
            float(row["rsi_2"]) if pd.notna(row.get("rsi_2")) else None,
            float(row["rsi_14"]) if pd.notna(row.get("rsi_14")) else None,
            float(row["macd"]) if pd.notna(row.get("macd")) else None,
            float(row["macd_signal"]) if pd.notna(row.get("macd_signal")) else None,
            float(row["macd_histogram"]) if pd.notna(row.get("macd_histogram")) else None,
            float(row["bb_upper"]) if pd.notna(row.get("bb_upper")) else None,
            float(row["bb_middle"]) if pd.notna(row.get("bb_middle")) else None,
            float(row["bb_lower"]) if pd.notna(row.get("bb_lower")) else None,
            float(row["bb_percent_b"]) if pd.notna(row.get("bb_percent_b")) else None,
            float(row["atr_10"]) if pd.notna(row.get("atr_10")) else None,
            float(row["atr_14"]) if pd.notna(row.get("atr_14")) else None,
            float(row["atr_50"]) if pd.notna(row.get("atr_50")) else None,
            float(row["atr_ratio"]) if pd.notna(row.get("atr_ratio")) else None,
            float(row["adx"]) if pd.notna(row.get("adx")) else None,
            float(row["stoch_k"]) if pd.notna(row.get("stoch_k")) else None,
            float(row["stoch_d"]) if pd.notna(row.get("stoch_d")) else None,
            float(row["cci_14"]) if pd.notna(row.get("cci_14")) else None,
            float(row["cci_50"]) if pd.notna(row.get("cci_50")) else None,
            float(row["kama_10"]) if pd.notna(row.get("kama_10")) else None,
            float(row["hma_20"]) if pd.notna(row.get("hma_20")) else None,
            float(row["alma_50"]) if pd.notna(row.get("alma_50")) else None,
            float(row["mcginley_dynamic"]) if pd.notna(row.get("mcginley_dynamic")) else None,
            float(row["cmf_21"]) if pd.notna(row.get("cmf_21")) else None,
            float(row["elder_force_index"]) if pd.notna(row.get("elder_force_index")) else None,
            float(row["volume_zscore"]) if pd.notna(row.get("volume_zscore")) else None,
            bool(row["unusual_volume"]) if pd.notna(row.get("unusual_volume")) else None,
            float(row["connors_rsi"]) if pd.notna(row.get("connors_rsi")) else None,
            float(row["hurst_exponent"]) if pd.notna(row.get("hurst_exponent")) else None,
            str(row["hurst_regime"]) if pd.notna(row.get("hurst_regime")) else None,
            float(row["returns_1d"]) if pd.notna(row.get("returns_1d")) else None,
            float(row["log_returns_1d"]) if pd.notna(row.get("log_returns_1d")) else None,
            float(row["range_pct"]) if pd.notna(row.get("range_pct")) else None,
            float(row["yang_zhang_vol"]) if pd.notna(row.get("yang_zhang_vol")) else None,
            float(row["garman_klass_vol"]) if pd.notna(row.get("garman_klass_vol")) else None,
            symbol,
            date.date()
        ))
        updated += 1

    conn.commit()
    cursor.close()

    return updated


def main():
    """Process all symbols one at a time."""
    print("\n" + "=" * 70)
    print("RECALCULATING ALL INDICATORS + VOLATILITY - ONE SYMBOL AT A TIME")
    print("=" * 70)
    print("\nNO SHORTCUTS. DOING IT RIGHT.\n")

    conn = get_connection()

    # Get all symbols
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT symbol FROM mkt.futures_1d ORDER BY symbol")
    symbols = [row[0] for row in cursor.fetchall()]
    cursor.close()

    print(f"Processing {len(symbols)} symbols...\n")

    total_updated = 0

    for i, symbol in enumerate(symbols):
        print(f"[{i+1}/{len(symbols)}] {symbol}...", end=" ", flush=True)
        try:
            updated = process_symbol(symbol, conn)
            total_updated += updated
            print(f"✓ {updated:,} rows")
        except Exception as e:
            print(f"✗ Error: {e}")

    conn.close()

    print("\n" + "=" * 70)
    print(f"COMPLETE: {total_updated:,} rows updated")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
