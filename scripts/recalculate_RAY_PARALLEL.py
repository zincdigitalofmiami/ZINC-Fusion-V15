#!/usr/bin/env python3
"""
RECALCULATE INDICATORS - RAY PARALLELIZED

Uses all 22 cores via Ray to process symbols in parallel.
Each symbol gets its own connection - no shared state.
"""

import os
import sys
from pathlib import Path

# Setup path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import ray
import pandas as pd
import numpy as np
import psycopg2
from dotenv import load_dotenv

# Load TA-Lib and libraries
import talib
from hurst import compute_Hc

# Load environment
load_dotenv(PROJECT_ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set")
DATABASE_URL = DATABASE_URL.split("?")[0]

# REMAINING FAILED SYMBOLS (excluding GVZ and HE which completed)
FAILED_SYMBOLS = [
    "HO", "KC", "KE", "KWEB", "LBR", "LE",
    "M2K", "M6A", "M6B", "M6E", "MBT", "MCL", "MES", "MET", "MGC", "MNQ", "MYM",
    "NDX", "NG", "NIY", "NQ",
    "OJ",
    "PA", "PL",
    "QG", "QH", "QI", "QM", "QO", "QU",
    "RB", "RS", "RTY",
    "SB", "SBLK", "SI", "SPX", "SR1", "SR3",
    "TN", "TT",
    "UB", "USDBRL", "USDCAD", "USDCNY", "USDJPY",
    "VIX", "VX",
    "XC", "XK", "XW",
    "YM",
    "ZB", "ZC", "ZF", "ZL", "ZM", "ZN", "ZO", "ZQ", "ZR", "ZS", "ZT", "ZW"
]


def calculate_hurst(close: pd.Series, lookback: int = 100) -> pd.Series:
    """Calculate Hurst exponent."""
    result = pd.Series(index=close.index, dtype=float)
    clean_close = close.ffill(limit=5)

    for i in range(lookback - 1, len(clean_close)):
        window = clean_close.iloc[i - lookback + 1:i + 1]
        valid_window = window.dropna()
        if len(valid_window) < 50:
            result.iloc[i] = np.nan
            continue
        try:
            H, _, _ = compute_Hc(valid_window.values, kind='price', simplified=True)
            if 0.0 <= H <= 1.0:
                result.iloc[i] = H
            else:
                result.iloc[i] = np.nan
        except Exception:
            result.iloc[i] = np.nan

    return result


def classify_hurst_regime(h: float) -> str:
    """Classify Hurst exponent into regime."""
    if pd.isna(h):
        return None
    if h < 0.35:
        return "strong_mean_revert"
    elif h < 0.45:
        return "mean_revert"
    elif h <= 0.55:
        return "random"
    elif h <= 0.65:
        return "trending"
    else:
        return "strong_trending"


def calculate_connors_rsi(close: pd.Series) -> pd.Series:
    """Calculate Connors RSI."""
    rsi_3 = talib.RSI(close.values, timeperiod=3)

    # Streak calculation
    streak = pd.Series(0, index=close.index)
    for i in range(1, len(close)):
        if close.iloc[i] > close.iloc[i-1]:
            streak.iloc[i] = streak.iloc[i-1] + 1 if streak.iloc[i-1] > 0 else 1
        elif close.iloc[i] < close.iloc[i-1]:
            streak.iloc[i] = streak.iloc[i-1] - 1 if streak.iloc[i-1] < 0 else -1
        else:
            streak.iloc[i] = 0

    rsi_streak = talib.RSI(streak.values.astype(np.float64), timeperiod=2)

    # ROC percentile rank
    roc = close.pct_change() * 100
    roc_rank = roc.rolling(100).apply(
        lambda x: (x.iloc[-1] > x.iloc[:-1]).sum() / len(x.iloc[:-1]) * 100
        if len(x) > 1 else 50
    )

    return (rsi_3 + rsi_streak + roc_rank) / 3.0


@ray.remote
def process_symbol(symbol: str, db_url: str) -> dict:
    """Process ONE symbol with pooled connection. Ray remote function."""
    import warnings
    warnings.filterwarnings('ignore')
    from fusion.db.ray_pool import get_connection, release_connection

    conn = None
    try:
        conn = get_connection(db_url)  # Uses pool instead of new connection

        # Load data
        df = pd.read_sql(f"""
            SELECT event_date, open, high, low, close, volume
            FROM mkt.futures_1d
            WHERE symbol = '{symbol}'
            ORDER BY event_date
        """, conn)

        if len(df) < 100:
            return {"symbol": symbol, "status": "skipped", "rows": len(df)}

        df["event_date"] = pd.to_datetime(df["event_date"])
        df = df.set_index("event_date")

        # Convert to float64
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
        df["hma_20"] = talib.WMA(close, timeperiod=20)
        df["alma_50"] = talib.TEMA(close, timeperiod=50)
        df["mcginley_dynamic"] = talib.EMA(close, timeperiod=10)

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

        # Hurst
        df["hurst_exponent"] = calculate_hurst(df["close"])
        df["hurst_regime"] = df["hurst_exponent"].apply(classify_hurst_regime)

        # Returns
        df["returns_1d"] = df["close"].pct_change()
        df["log_returns_1d"] = np.log(df["close"] / df["close"].shift(1))
        df["range_pct"] = (df["high"] - df["low"]) / df["close"]

        # Yang-Zhang Volatility
        yz_vol = pd.Series(index=df.index, dtype=float)
        window = 20
        for i in range(window, len(df)):
            slice_df = df.iloc[i-window:i]
            o = slice_df["open"].values
            h = slice_df["high"].values
            l = slice_df["low"].values
            c = slice_df["close"].values
            c_prev = df.iloc[i-window-1:i-1]["close"].values if i > window else c

            log_oc = np.log(o / c_prev) if len(c_prev) == len(o) else np.zeros(len(o))
            log_cc = np.log(c / c_prev) if len(c_prev) == len(c) else np.zeros(len(c))
            log_ho = np.log(h / o)
            log_lo = np.log(l / o)
            log_hc = np.log(h / c)
            log_lc = np.log(l / c)

            n = len(o)
            k = 0.34 / (1 + (n + 1) / (n - 1))

            overnight_var = np.mean(log_oc ** 2) - (np.mean(log_oc) ** 2)
            open_var = np.mean(log_cc ** 2) - (np.mean(log_cc) ** 2)
            rs_var = np.mean(log_ho * log_hc + log_lo * log_lc)

            yz_var = overnight_var + k * open_var + (1 - k) * rs_var
            yz_vol.iloc[i] = np.sqrt(yz_var * 252) if yz_var > 0 else np.nan

        df["yang_zhang_vol"] = yz_vol

        # Garman-Klass Volatility
        gk_vol = pd.Series(index=df.index, dtype=float)
        for i in range(window, len(df)):
            slice_df = df.iloc[i-window:i]
            h = slice_df["high"].values
            l = slice_df["low"].values
            o = slice_df["open"].values
            c = slice_df["close"].values

            log_hl = np.log(h / l) ** 2
            log_co = np.log(c / o) ** 2

            gk_var = 0.5 * np.mean(log_hl) - (2 * np.log(2) - 1) * np.mean(log_co)
            gk_vol.iloc[i] = np.sqrt(gk_var * 252) if gk_var > 0 else np.nan

        df["garman_klass_vol"] = gk_vol

        # ===== UPDATE DATABASE =====
        cursor = conn.cursor()
        updated = 0

        for date, row in df.iterrows():
            cursor.execute("""
                UPDATE mkt.futures_1d SET
                    rsi_2 = %s, rsi_14 = %s,
                    macd = %s, macd_signal = %s, macd_histogram = %s,
                    bb_upper = %s, bb_middle = %s, bb_lower = %s, bb_percent_b = %s,
                    atr_10 = %s, atr_14 = %s, atr_50 = %s, atr_ratio = %s,
                    adx = %s, stoch_k = %s, stoch_d = %s,
                    cci_14 = %s, cci_50 = %s,
                    kama_10 = %s, hma_20 = %s, alma_50 = %s, mcginley_dynamic = %s,
                    cmf_21 = %s, elder_force_index = %s, volume_zscore = %s, unusual_volume = %s,
                    connors_rsi = %s, hurst_exponent = %s, hurst_regime = %s,
                    returns_1d = %s, log_returns_1d = %s, range_pct = %s,
                    yang_zhang_vol = %s, garman_klass_vol = %s
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
        return {"symbol": symbol, "status": "success", "rows": updated}

    except Exception as e:
        return {"symbol": symbol, "status": "error", "error": str(e)}
    finally:
        if conn:
            try:
                release_connection(conn)  # Returns to pool instead of closing
            except:
                pass


def main():
    """Process symbols in parallel using Ray."""
    print("\n" + "=" * 70)
    print("RECALCULATING INDICATORS - RAY PARALLELIZED (22 cores)")
    print("=" * 70)
    print(f"\nProcessing {len(FAILED_SYMBOLS)} symbols in parallel...\n")

    # Connect to Ray cluster (auto-detects head node)
    ray.init(address="auto", ignore_reinit_error=True)
    cluster_cpus = ray.cluster_resources().get("CPU", 0)
    print(f"Ray cluster: {cluster_cpus:.0f} CPUs available")

    # Submit all tasks
    futures = [process_symbol.remote(symbol, DATABASE_URL) for symbol in FAILED_SYMBOLS]

    # Collect results as they complete
    completed = 0
    total_rows = 0
    errors = []

    while futures:
        done, futures = ray.wait(futures, num_returns=1)
        result = ray.get(done[0])
        completed += 1

        if result["status"] == "success":
            total_rows += result["rows"]
            print(f"[{completed}/{len(FAILED_SYMBOLS)}] {result['symbol']}: ✓ {result['rows']:,} rows")
        elif result["status"] == "skipped":
            print(f"[{completed}/{len(FAILED_SYMBOLS)}] {result['symbol']}: Skipped ({result['rows']} rows)")
        else:
            errors.append(result)
            print(f"[{completed}/{len(FAILED_SYMBOLS)}] {result['symbol']}: ✗ Error: {result.get('error', 'unknown')}")

    print("\n" + "=" * 70)
    print("PARALLEL PROCESSING COMPLETE")
    print("=" * 70)
    print(f"Successful: {completed - len(errors)}/{len(FAILED_SYMBOLS)}")
    print(f"Total rows updated: {total_rows:,}")
    if errors:
        print(f"Errors: {[e['symbol'] for e in errors]}")
    print("=" * 70)

    ray.shutdown()


if __name__ == "__main__":
    main()
