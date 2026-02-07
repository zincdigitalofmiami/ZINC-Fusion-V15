#!/usr/bin/env python3
"""
RECALCULATE INDICATORS - RAY DISTRIBUTED (22 cores across 2 Macs)

Uses Ray cluster for distributed processing across Mac A (4 CPUs) + Mac B (10 CPUs).
"""

import os
import sys
from pathlib import Path
import ray

# Setup path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

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

# REMAINING FAILED SYMBOLS
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


def calculate_hurst(close_values, lookback: int = 100):
    """Calculate Hurst exponent for array."""
    result = np.full(len(close_values), np.nan)
    close = pd.Series(close_values).ffill(limit=5).values

    for i in range(lookback - 1, len(close)):
        window = close[i - lookback + 1:i + 1]
        valid = window[~np.isnan(window)]
        if len(valid) < 50:
            continue
        try:
            H, _, _ = compute_Hc(valid, kind='price', simplified=True)
            if 0.0 <= H <= 1.0:
                result[i] = H
        except:
            pass

    return result


def classify_hurst_regime(h):
    """Classify Hurst exponent into regime."""
    if pd.isna(h) or h is None:
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


def calculate_connors_rsi(close_series):
    """Calculate Connors RSI."""
    close = close_series.values
    rsi_3 = talib.RSI(close, timeperiod=3)

    # Streak
    streak = np.zeros(len(close))
    for i in range(1, len(close)):
        if close[i] > close[i-1]:
            streak[i] = streak[i-1] + 1 if streak[i-1] > 0 else 1
        elif close[i] < close[i-1]:
            streak[i] = streak[i-1] - 1 if streak[i-1] < 0 else -1

    rsi_streak = talib.RSI(streak.astype(np.float64), timeperiod=2)

    # ROC percentile
    roc = close_series.pct_change().values * 100
    roc_rank = np.full(len(close), np.nan)
    for i in range(100, len(close)):
        window = roc[i-99:i+1]
        roc_rank[i] = (window[-1] > window[:-1]).sum() / len(window[:-1]) * 100

    result = (rsi_3 + rsi_streak + roc_rank) / 3.0
    return pd.Series(result, index=close_series.index)


@ray.remote
def process_symbol(symbol):
    """Process ONE symbol with its own connection. Runs on Ray cluster."""
    import warnings
    warnings.filterwarnings('ignore')

    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)

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
        hurst_values = calculate_hurst(close)
        df["hurst_exponent"] = hurst_values
        df["hurst_regime"] = [classify_hurst_regime(h) for h in hurst_values]

        # Returns
        df["returns_1d"] = df["close"].pct_change()
        df["log_returns_1d"] = np.log(df["close"] / df["close"].shift(1))
        df["range_pct"] = (df["high"] - df["low"]) / df["close"]

        # Yang-Zhang Volatility
        window = 20
        yz_vol = np.full(len(df), np.nan)
        for i in range(window, len(df)):
            o = df["open"].values[i-window:i]
            h = df["high"].values[i-window:i]
            l = df["low"].values[i-window:i]
            c = df["close"].values[i-window:i]
            c_prev = df["close"].values[i-window-1:i-1] if i > window else c

            if len(c_prev) == len(o):
                log_oc = np.log(o / c_prev)
                log_cc = np.log(c / c_prev)
            else:
                log_oc = np.zeros(len(o))
                log_cc = np.zeros(len(c))

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
            yz_vol[i] = np.sqrt(yz_var * 252) if yz_var > 0 else np.nan

        df["yang_zhang_vol"] = yz_vol

        # Garman-Klass Volatility
        gk_vol = np.full(len(df), np.nan)
        for i in range(window, len(df)):
            h = df["high"].values[i-window:i]
            l = df["low"].values[i-window:i]
            o = df["open"].values[i-window:i]
            c = df["close"].values[i-window:i]

            log_hl = np.log(h / l) ** 2
            log_co = np.log(c / o) ** 2

            gk_var = 0.5 * np.mean(log_hl) - (2 * np.log(2) - 1) * np.mean(log_co)
            gk_vol[i] = np.sqrt(gk_var * 252) if gk_var > 0 else np.nan

        df["garman_klass_vol"] = gk_vol

        # UPDATE DATABASE
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
                conn.close()
            except:
                pass


def main():
    """Process symbols in parallel using Ray distributed cluster."""
    # Connect to Ray cluster (Mac A + Mac B)
    ray.init(address='auto', ignore_reinit_error=True)

    cluster_cpus = ray.cluster_resources().get('CPU', 0)
    print("\n" + "=" * 70, flush=True)
    print(f"RECALCULATING INDICATORS - RAY DISTRIBUTED ({cluster_cpus:.0f} CPUs)", flush=True)
    print("=" * 70, flush=True)
    print(f"\nProcessing {len(FAILED_SYMBOLS)} symbols across cluster...\n", flush=True)

    total_rows = 0
    completed = 0
    errors = []

    # Submit all tasks to Ray cluster
    futures = [process_symbol.remote(sym) for sym in FAILED_SYMBOLS]

    # Collect results as they complete
    while futures:
        done, futures = ray.wait(futures, num_returns=1)
        result = ray.get(done[0])
        completed += 1

        if result["status"] == "success":
            total_rows += result["rows"]
            print(f"[{completed}/{len(FAILED_SYMBOLS)}] {result['symbol']}: ✓ {result['rows']:,} rows", flush=True)
        elif result["status"] == "skipped":
            print(f"[{completed}/{len(FAILED_SYMBOLS)}] {result['symbol']}: Skipped ({result['rows']} rows)", flush=True)
        else:
            errors.append(result)
            print(f"[{completed}/{len(FAILED_SYMBOLS)}] {result['symbol']}: ✗ Error: {result.get('error', 'unknown')}", flush=True)

    print("\n" + "=" * 70)
    print("PARALLEL PROCESSING COMPLETE")
    print("=" * 70)
    print(f"Successful: {completed - len(errors)}/{len(FAILED_SYMBOLS)}")
    print(f"Total rows updated: {total_rows:,}")
    if errors:
        print(f"Errors: {[e['symbol'] for e in errors]}")
    print("=" * 70)


if __name__ == "__main__":
    main()
