#!/usr/bin/env python3
"""
CORRECT Yang-Zhang and Garman-Klass Volatility Estimators

Yang-Zhang (2000) - "Drift Independent Volatility Estimation"
Garman-Klass (1980) - "On the Estimation of Security Price Volatilities from Historical Data"

EXACT ACADEMIC FORMULAS - ZERO APPROXIMATIONS.

References:
- Yang, D., & Zhang, Q. (2000). Drift Independent Volatility Estimation
- Garman, M. B., & Klass, M. J. (1980). On the Estimation of Security Price Volatilities

Author: ZINC-FUSION-V15
Date: 2026-01-31
"""

import json
import numpy as np
import os
from pathlib import Path
import pandas as pd
import psycopg2
import resource
import signal
import sys
import time
from tqdm import tqdm

DEBUG_LOG_PATH = "/Volumes/Satechi Hub/ZINC-FUSION-V15/.cursor/debug.log"


def _debug_log(payload: dict) -> None:
    try:
        Path(DEBUG_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def load_env():
    """Load environment variables from .env file."""
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line and "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip().strip('"').strip("'")


def get_db_connection():
    """Get database connection."""
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL.split("?")[0])


def yang_zhang_volatility(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Calculate Yang-Zhang volatility estimator.

    EXACT FORMULA from Yang & Zhang (2000):

    σ² = σ_o² + k*σ_c² + (1-k)*σ_rs²

    Where:
    - σ_o² = Overnight variance: variance of log(Open_t / Close_{t-1})
    - σ_c² = Close-to-close variance: variance of log(Close_t / Open_t)
    - σ_rs² = Rogers-Satchell variance:
        mean of [log(H/C)*log(H/O) + log(L/C)*log(L/O)]
    - k = 0.34 / (1.34 + (N+1)/(N-1))

    Args:
        df: DataFrame with 'open', 'high', 'low', 'close' columns
        window: Rolling window size (default 20)

    Returns:
        Series of Yang-Zhang volatility estimates
    """
    # Ensure float64 for precision
    o = df["open"].astype(np.float64)
    h = df["high"].astype(np.float64)
    l = df["low"].astype(np.float64)
    c = df["close"].astype(np.float64)

    # Previous close
    c_prev = c.shift(1)

    # Log returns (handle zeros/negatives)
    with np.errstate(divide="ignore", invalid="ignore"):
        # Overnight return: log(Open_t / Close_{t-1})
        log_oc = np.log(o / c_prev)

        # Open-to-close return: log(Close_t / Open_t)
        log_co = np.log(c / o)

        # Rogers-Satchell components
        log_hc = np.log(h / c)
        log_ho = np.log(h / o)
        log_lc = np.log(l / c)
        log_lo = np.log(l / o)

    # Rogers-Satchell variance (per bar)
    rs_daily = log_hc * log_ho + log_lc * log_lo

    # Calculate k factor
    # k = 0.34 / (1.34 + (N+1)/(N-1))
    # For N=20: k = 0.34 / (1.34 + 21/19) = 0.34 / 2.445 ≈ 0.139
    k = 0.34 / (1.34 + (window + 1) / (window - 1))

    # Rolling variances
    # σ_o² = variance of overnight returns
    sigma_o_sq = log_oc.rolling(window).var()

    # σ_c² = variance of open-to-close returns
    sigma_c_sq = log_co.rolling(window).var()

    # σ_rs² = mean of daily Rogers-Satchell values
    sigma_rs_sq = rs_daily.rolling(window).mean()

    # Yang-Zhang variance: σ² = σ_o² + k*σ_c² + (1-k)*σ_rs²
    yang_zhang_var = sigma_o_sq + k * sigma_c_sq + (1 - k) * sigma_rs_sq

    # Return standard deviation (not variance), annualized
    # Annualization factor: sqrt(252) for daily data
    yang_zhang_vol = np.sqrt(yang_zhang_var) * np.sqrt(252)

    return yang_zhang_vol


def garman_klass_volatility(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Calculate Garman-Klass volatility estimator.

    EXACT FORMULA from Garman & Klass (1980):

    For each day:
    GK_daily = 0.5 * ln(H/L)² - (2*ln(2) - 1) * ln(C/O)²

    Rolling GK volatility = sqrt(mean(GK_daily)) * sqrt(252)

    Note: The coefficient (2*ln(2) - 1) ≈ 0.386 corrects for the
    close-to-open information.

    Args:
        df: DataFrame with 'open', 'high', 'low', 'close' columns
        window: Rolling window size (default 20)

    Returns:
        Series of Garman-Klass volatility estimates
    """
    # Ensure float64 for precision
    o = df["open"].astype(np.float64)
    h = df["high"].astype(np.float64)
    l = df["low"].astype(np.float64)
    c = df["close"].astype(np.float64)

    with np.errstate(divide="ignore", invalid="ignore"):
        # Log of High/Low ratio
        log_hl = np.log(h / l)

        # Log of Close/Open ratio
        log_co = np.log(c / o)

    # Garman-Klass daily variance estimate
    # GK = 0.5 * ln(H/L)² - (2*ln(2) - 1) * ln(C/O)²
    gk_coefficient = 2 * np.log(2) - 1  # ≈ 0.386
    gk_daily = 0.5 * (log_hl**2) - gk_coefficient * (log_co**2)

    # Rolling mean, then square root for volatility
    gk_mean = gk_daily.rolling(window).mean()

    # Annualized volatility: sqrt(mean) * sqrt(252)
    gk_vol = np.sqrt(gk_mean.clip(lower=0)) * np.sqrt(252)

    return gk_vol


def calculate_for_symbol(symbol: str, conn) -> tuple:
    """
    Calculate Yang-Zhang and Garman-Klass volatility for a single symbol.

    Returns:
        (records_updated, error_message)
    """
    try:
        # Load data
        df = pd.read_sql(
            f"""
            SELECT event_date, open, high, low, close, volume
            FROM mkt.futures_1d
            WHERE symbol = %s
            ORDER BY event_date
        """,
            conn,
            params=(symbol,),
        )

        if len(df) < 30:
            return 0, f"Insufficient data ({len(df)} rows)"

        df["event_date"] = pd.to_datetime(df["event_date"])
        df = df.set_index("event_date")

        # Calculate volatilities using EXACT formulas
        df["yang_zhang_vol"] = yang_zhang_volatility(df, window=20)
        df["garman_klass_vol"] = garman_klass_volatility(df, window=20)

        # Filter valid rows
        valid_rows = df[df["yang_zhang_vol"].notna() & df["garman_klass_vol"].notna()]

        if len(valid_rows) == 0:
            return 0, "No valid volatility values"

        # Update database
        cursor = conn.cursor()
        updated = 0

        for date, row in valid_rows.iterrows():
            cursor.execute(
                """
                UPDATE mkt.futures_1d
                SET yang_zhang_vol = %s,
                    garman_klass_vol = %s
                WHERE symbol = %s AND event_date = %s
            """,
                (
                    (
                        float(row["yang_zhang_vol"])
                        if pd.notna(row["yang_zhang_vol"])
                        else None
                    ),
                    (
                        float(row["garman_klass_vol"])
                        if pd.notna(row["garman_klass_vol"])
                        else None
                    ),
                    symbol,
                    date.date(),
                ),
            )
            updated += 1

        conn.commit()
        cursor.close()

        return updated, None

    except Exception as e:
        return 0, str(e)


def main():
    """Calculate Yang-Zhang and Garman-Klass volatility for all symbols."""
    run_id = f"volatility_{int(time.time() * 1000)}"
    status = "started"
    error_msg = None
    total_updated = 0
    errors = []
    conn = None
    start_ts = time.time()

    def _signal_handler(signum, _frame):
        # #region agent log
        _debug_log(
            {
                "sessionId": "debug-session",
                "runId": run_id,
                "hypothesisId": "H4",
                "location": "calculate_volatility_CORRECT.py:signal",
                "message": "volatility_signal",
                "data": {
                    "signal": int(signum),
                    "elapsed_s": round(time.time() - start_ts, 2),
                    "rss_kb": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
                },
                "timestamp": int(time.time() * 1000),
            }
        )
        # #endregion

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGHUP, _signal_handler)

    # #region agent log
    _debug_log(
        {
            "sessionId": "debug-session",
            "runId": run_id,
            "hypothesisId": "H1",
            "location": "calculate_volatility_CORRECT.py:main:start",
            "message": "volatility_script_start",
            "data": {
                "pid": os.getpid(),
                "cwd": os.getcwd(),
                "python": sys.executable,
                "env_file_exists": Path(".env").exists(),
                "env_local_exists": Path("frontend/.env.local").exists(),
                "database_url_set": bool(os.getenv("DATABASE_URL")),
            },
            "timestamp": int(time.time() * 1000),
        }
    )
    # #endregion

    try:
        print("\n" + "=" * 70)
        print("YANG-ZHANG & GARMAN-KLASS VOLATILITY - EXACT ACADEMIC FORMULAS")
        print("=" * 70)
        print("\nYang-Zhang (2000): σ² = σ_o² + k·σ_c² + (1-k)·σ_rs²")
        print("Garman-Klass (1980): GK = 0.5·ln(H/L)² - (2·ln2-1)·ln(C/O)²")
        print("=" * 70 + "\n")

        load_env()

        # #region agent log
        _debug_log(
            {
                "sessionId": "debug-session",
                "runId": run_id,
                "hypothesisId": "H1",
                "location": "calculate_volatility_CORRECT.py:main:after_load_env",
                "message": "volatility_env_after_load",
                "data": {
                    "database_url_set": bool(os.getenv("DATABASE_URL")),
                    "env_file_exists": Path(".env").exists(),
                    "env_local_exists": Path("frontend/.env.local").exists(),
                },
                "timestamp": int(time.time() * 1000),
            }
        )
        # #endregion

        conn = get_db_connection()

        # Get all symbols
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM mkt.futures_1d ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()

        # #region agent log
        _debug_log(
            {
                "sessionId": "debug-session",
                "runId": run_id,
                "hypothesisId": "H2",
                "location": "calculate_volatility_CORRECT.py:main:after_symbols",
                "message": "volatility_symbols_loaded",
                "data": {
                    "symbol_count": len(symbols),
                    "db_connected": True,
                },
                "timestamp": int(time.time() * 1000),
            }
        )
        # #endregion

        print(f"Processing {len(symbols)} symbols...\n")

        total_symbols = len(symbols)
        for idx, symbol in enumerate(
            tqdm(symbols, desc="Calculating volatility"), start=1
        ):
            updated, error = calculate_for_symbol(symbol, conn)
            total_updated += updated
            if error:
                errors.append((symbol, error))
            if idx % 5 == 0:
                # #region agent log
                _debug_log(
                    {
                        "sessionId": "debug-session",
                        "runId": run_id,
                        "hypothesisId": "H5",
                        "location": "calculate_volatility_CORRECT.py:loop",
                        "message": "volatility_heartbeat",
                        "data": {
                            "processed_symbols": idx,
                            "total_symbols": total_symbols,
                            "rss_kb": int(
                                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                            ),
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                # #endregion

        conn.close()

        print(f"\n{'='*70}")
        print(f"✅ COMPLETE: {total_updated:,} rows updated with CORRECT volatility")
        print(f"{'='*70}")

        if errors:
            print(f"\n⚠️  {len(errors)} symbols had issues:")
            for sym, err in errors[:10]:
                print(f"   {sym}: {err}")
            if len(errors) > 10:
                print(f"   ... and {len(errors) - 10} more")

        print(
            "\n✅ YANG-ZHANG: Exact formula with overnight + intraday + Rogers-Satchell"
        )
        print("✅ GARMAN-KLASS: Exact formula with (2·ln2-1) coefficient")
        print("✅ Both annualized (×√252)")
        print("=" * 70 + "\n")
        status = "success"
    except Exception as e:
        status = "error"
        error_msg = f"{type(e).__name__}: {e}"
        raise
    finally:
        # #region agent log
        _debug_log(
            {
                "sessionId": "debug-session",
                "runId": run_id,
                "hypothesisId": "H3",
                "location": "calculate_volatility_CORRECT.py:main:exit",
                "message": "volatility_script_exit",
                "data": {
                    "status": status,
                    "error": error_msg,
                    "total_updated": total_updated,
                    "error_count": len(errors),
                },
                "timestamp": int(time.time() * 1000),
            }
        )
        # #endregion


if __name__ == "__main__":
    main()
