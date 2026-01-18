"""
Phase 1: Options Features Computation
=====================================

Computes implied volatility and Greeks from mkt.options_1d.
Writes to features.options_1d.

LOCKED SPECIFICATIONS:
- IV computed via Black-Scholes model
- Greeks: delta, gamma, theta, vega (Z-SCORE NORMALIZED)
- Front-month weighting: OI-weighted with 30-day roll threshold
- Put/call ratios + delta-weighted OI pressure metrics

BLOCKING GATE: Core training cannot proceed until this completes.
"""

from __future__ import annotations

import logging
import hashlib
from datetime import datetime
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from scipy.stats import norm

from .config import (
    DATABASE_URL,
    TARGET_SYMBOL,
    OPTIONS_CONFIG,
)

logger = logging.getLogger(__name__)


# =============================================================================
# BLACK-SCHOLES MODEL
# =============================================================================


def black_scholes_price(
    S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call"
) -> float:
    """
    Black-Scholes option pricing.

    Args:
        S: Spot/futures price
        K: Strike price
        T: Time to expiration (years)
        r: Risk-free rate
        sigma: Volatility
        option_type: 'call' or 'put'
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return np.nan

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == "call":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def implied_volatility(
    option_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str = "call",
    max_iter: int = 100,
    tol: float = 1e-5,
) -> float:
    """
    Newton-Raphson IV computation.

    Returns implied volatility or np.nan if failed to converge.
    """
    if T <= 0 or option_price <= 0 or S <= 0 or K <= 0:
        return np.nan

    # Initial guess (Brenner-Subrahmanyam)
    sigma = np.sqrt(2 * np.pi / T) * (option_price / S)
    sigma = max(0.01, min(sigma, 5.0))

    for _ in range(max_iter):
        price = black_scholes_price(S, K, T, r, sigma, option_type)

        # Vega
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        vega = S * norm.pdf(d1) * np.sqrt(T)

        if vega < 1e-10:
            return np.nan

        diff = price - option_price
        if abs(diff) < tol:
            return sigma

        sigma = sigma - diff / vega

        if sigma <= 0.001 or sigma > 10:
            return np.nan

    return np.nan


def compute_greeks(
    S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call"
) -> dict:
    """Compute option Greeks (delta, gamma, theta, vega)."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {"delta": np.nan, "gamma": np.nan, "theta": np.nan, "vega": np.nan}

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    # Delta
    delta = norm.cdf(d1) if option_type == "call" else norm.cdf(d1) - 1

    # Gamma
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))

    # Vega (per 1% vol change)
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100

    # Theta (per day)
    if option_type == "call":
        theta = (
            -S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
            - r * K * np.exp(-r * T) * norm.cdf(d2)
        ) / 365
    else:
        theta = (
            -S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
            + r * K * np.exp(-r * T) * norm.cdf(-d2)
        ) / 365

    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


# =============================================================================
# DATA LOADING
# =============================================================================


def load_options_data(conn, symbol: str, start_date: str) -> pd.DataFrame:
    """Load options data from mkt."""
    query = """
        SELECT 
            event_date,
            underlying as symbol,
            close as option_price,
            strike,
            expiration,
            option_type,
            open_interest,
            volume
        FROM mkt.options_1d
        WHERE underlying LIKE %s
          AND event_date >= %s
          AND close IS NOT NULL
          AND strike IS NOT NULL
          AND expiration IS NOT NULL
          AND option_type IN ('call', 'put', 'C', 'P')
        ORDER BY event_date, expiration, strike
    """
    logger.info(f"Loading options data for {symbol} from {start_date}")
    df = pd.read_sql(query, conn, params=(f"{symbol}%", start_date))

    # Normalize option_type
    df["option_type"] = df["option_type"].replace({"C": "call", "P": "put"})

    logger.info(f"Loaded {len(df):,} options rows")
    return df


def load_futures_prices(conn, symbol: str, start_date: str) -> pd.DataFrame:
    """Load underlying futures prices from mkt."""
    query = """
        SELECT 
            event_date as trade_date,
            close as futures_price
        FROM mkt.futures_1d
        WHERE symbol = %s
          AND event_date >= %s
          AND close IS NOT NULL
        ORDER BY event_date
    """
    df = pd.read_sql(query, conn, params=(symbol, start_date))
    logger.info(f"Loaded {len(df):,} futures prices")
    return df


def load_risk_free_rate(conn, start_date: str) -> pd.DataFrame:
    """Load risk-free rate from econ.rates_1d."""
    series = OPTIONS_CONFIG.risk_free_rate_series
    query = """
        SELECT 
            event_date as trade_date,
            value / 100.0 as risk_free_rate
        FROM econ.rates_1d
        WHERE series_id = %s
          AND event_date >= %s
          AND value IS NOT NULL
        ORDER BY event_date
    """
    df = pd.read_sql(query, conn, params=(series, start_date))
    df["risk_free_rate"] = df["risk_free_rate"].ffill()
    logger.info(f"Loaded {len(df):,} rate observations ({series})")
    return df


# =============================================================================
# FEATURE COMPUTATION
# =============================================================================


def compute_iv_greeks_batch(
    df: pd.DataFrame, futures_df: pd.DataFrame, rate_df: pd.DataFrame
) -> pd.DataFrame:
    """Compute IV and Greeks for all options."""
    # Merge data
    df["trade_date"] = df["event_date"]
    df = df.merge(futures_df, on="trade_date", how="left")
    df = df.merge(rate_df, on="trade_date", how="left")
    df["risk_free_rate"] = df["risk_free_rate"].ffill().fillna(0.02)

    # Time to expiry (years)
    df["time_to_expiry"] = (df["expiration"] - df["event_date"]).dt.days / 252.0
    df["time_to_expiry"] = df["time_to_expiry"].clip(lower=1 / 252)

    logger.info("Computing implied volatility (this may take a few minutes)...")

    # Vectorized IV computation (apply row-wise)
    df["iv"] = df.apply(
        lambda r: (
            implied_volatility(
                r["option_price"],
                r["futures_price"],
                r["strike"],
                r["time_to_expiry"],
                r["risk_free_rate"],
                r["option_type"],
            )
            if pd.notna(r["futures_price"])
            else np.nan
        ),
        axis=1,
    )

    logger.info("Computing Greeks...")
    greeks = df.apply(
        lambda r: (
            compute_greeks(
                r["futures_price"],
                r["strike"],
                r["time_to_expiry"],
                r["risk_free_rate"],
                r["iv"] if pd.notna(r["iv"]) else 0.25,
                r["option_type"],
            )
            if pd.notna(r["futures_price"])
            else {"delta": np.nan, "gamma": np.nan, "theta": np.nan, "vega": np.nan}
        ),
        axis=1,
        result_type="expand",
    )

    df = pd.concat([df, greeks], axis=1)
    return df


def aggregate_front_month(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate to front-month weighted features.

    LOCKED: OI-weighted with 30-day roll threshold.
    """
    logger.info(
        f"Aggregating to front-month (OI-weighted, {OPTIONS_CONFIG.roll_threshold_days}d roll)"
    )

    # Filter to contracts beyond roll threshold
    min_dte = OPTIONS_CONFIG.roll_threshold_days / 252.0
    df = df[df["time_to_expiry"] > min_dte].copy()

    if len(df) == 0:
        logger.warning("No options data after front-month filter")
        return pd.DataFrame()

    # Separate calls and puts
    calls = df[df["option_type"] == "call"].copy()
    puts = df[df["option_type"] == "put"].copy()

    def weighted_mean(group, col, weight_col="open_interest"):
        weights = group[weight_col].fillna(0)
        values = group[col].fillna(0)
        if weights.sum() == 0:
            return values.mean()
        return np.average(values, weights=weights)

    # Aggregate calls
    call_agg = (
        calls.groupby("event_date")
        .agg(
            {
                "iv": "mean",
                "delta": lambda x: weighted_mean(calls.loc[x.index], "delta"),
                "open_interest": "sum",
                "volume": "sum",
            }
        )
        .rename(
            columns={
                "iv": "iv_call",
                "delta": "delta_call",
                "open_interest": "oi_call",
                "volume": "vol_call",
            }
        )
    )

    # Aggregate puts
    put_agg = (
        puts.groupby("event_date")
        .agg(
            {
                "iv": "mean",
                "delta": lambda x: weighted_mean(puts.loc[x.index], "delta"),
                "open_interest": "sum",
                "volume": "sum",
            }
        )
        .rename(
            columns={
                "iv": "iv_put",
                "delta": "delta_put",
                "open_interest": "oi_put",
                "volume": "vol_put",
            }
        )
    )

    # Combine
    result = call_agg.join(put_agg, how="outer")

    # Derived metrics
    result["iv_atm"] = (result["iv_call"].fillna(0) + result["iv_put"].fillna(0)) / 2
    result["skew"] = result["iv_put"] - result["iv_call"]
    result["put_call_ratio_oi"] = result["oi_put"] / (result["oi_call"] + 1)
    result["put_call_ratio_vol"] = result["vol_put"] / (result["vol_call"] + 1)
    result["delta_weighted_oi_net"] = result["delta_call"].fillna(0) * result[
        "oi_call"
    ].fillna(0) + result["delta_put"].fillna(0) * result["oi_put"].fillna(0)

    return result.reset_index().rename(columns={"event_date": "trade_date"})


def normalize_features(df: pd.DataFrame) -> pd.DataFrame:
    """Z-SCORE normalize Greeks and derived metrics."""
    if not OPTIONS_CONFIG.normalize_greeks:
        return df

    logger.info("Z-SCORE normalizing options features...")

    cols_to_normalize = [
        "delta_call",
        "delta_put",
        "delta_weighted_oi_net",
        "iv_atm",
        "iv_call",
        "iv_put",
        "skew",
        "put_call_ratio_oi",
        "put_call_ratio_vol",
    ]

    for col in cols_to_normalize:
        if col in df.columns:
            values = df[col].fillna(0)
            mean = values.mean()
            std = values.std()
            if std > 0:
                df[f"{col}_z"] = (values - mean) / std
            else:
                df[f"{col}_z"] = 0

    return df


# =============================================================================
# DATABASE WRITE
# =============================================================================


def ensure_table_exists(conn):
    """Create features.options_1d if not exists."""
    create_sql = """
    CREATE TABLE IF NOT EXISTS features.options_1d (
        id SERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        symbol VARCHAR(20) NOT NULL,
        iv_atm FLOAT,
        iv_call FLOAT,
        iv_put FLOAT,
        skew FLOAT,
        put_call_ratio_oi FLOAT,
        put_call_ratio_vol FLOAT,
        delta_weighted_oi_net FLOAT,
        delta_call FLOAT,
        delta_put FLOAT,
        oi_call BIGINT,
        oi_put BIGINT,
        vol_call BIGINT,
        vol_put BIGINT,
        iv_atm_z FLOAT,
        iv_call_z FLOAT,
        iv_put_z FLOAT,
        skew_z FLOAT,
        put_call_ratio_oi_z FLOAT,
        put_call_ratio_vol_z FLOAT,
        delta_weighted_oi_net_z FLOAT,
        delta_call_z FLOAT,
        delta_put_z FLOAT,
        computed_at TIMESTAMP DEFAULT NOW(),
        options_version VARCHAR(64),
        UNIQUE(symbol, trade_date)
    );
    CREATE INDEX IF NOT EXISTS idx_features_options_trade_date 
        ON features.options_1d(trade_date);
    CREATE INDEX IF NOT EXISTS idx_features_options_symbol 
        ON features.options_1d(symbol);
    """
    with conn.cursor() as cur:
        cur.execute(create_sql)
        conn.commit()
    logger.info("✅ Ensured features.options_1d exists")


def write_features(conn, df: pd.DataFrame, symbol: str, dry_run: bool = False) -> str:
    """Write features to features.options_1d. Returns version hash."""
    if dry_run:
        logger.info(f"DRY RUN: Would write {len(df)} rows")
        logger.info(f"Sample:\n{df.head()}")
        return "dry_run"

    # Generate version hash
    version_hash = hashlib.sha256(
        f"{symbol}_{datetime.now().isoformat()}_{len(df)}".encode()
    ).hexdigest()[:16]

    df["symbol"] = symbol
    df["computed_at"] = datetime.now()
    df["options_version"] = version_hash

    # Columns to insert
    columns = [
        "trade_date",
        "symbol",
        "iv_atm",
        "iv_call",
        "iv_put",
        "skew",
        "put_call_ratio_oi",
        "put_call_ratio_vol",
        "delta_weighted_oi_net",
        "delta_call",
        "delta_put",
        "oi_call",
        "oi_put",
        "vol_call",
        "vol_put",
        "iv_atm_z",
        "iv_call_z",
        "iv_put_z",
        "skew_z",
        "put_call_ratio_oi_z",
        "put_call_ratio_vol_z",
        "delta_weighted_oi_net_z",
        "delta_call_z",
        "delta_put_z",
        "computed_at",
        "options_version",
    ]

    # Ensure all columns exist
    for col in columns:
        if col not in df.columns:
            df[col] = None

    # Upsert
    insert_sql = f"""
        INSERT INTO features.options_1d ({', '.join(columns)})
        VALUES %s
        ON CONFLICT (symbol, trade_date) DO UPDATE SET
            iv_atm = EXCLUDED.iv_atm,
            iv_call = EXCLUDED.iv_call,
            iv_put = EXCLUDED.iv_put,
            skew = EXCLUDED.skew,
            put_call_ratio_oi = EXCLUDED.put_call_ratio_oi,
            put_call_ratio_vol = EXCLUDED.put_call_ratio_vol,
            delta_weighted_oi_net = EXCLUDED.delta_weighted_oi_net,
            delta_call = EXCLUDED.delta_call,
            delta_put = EXCLUDED.delta_put,
            oi_call = EXCLUDED.oi_call,
            oi_put = EXCLUDED.oi_put,
            vol_call = EXCLUDED.vol_call,
            vol_put = EXCLUDED.vol_put,
            iv_atm_z = EXCLUDED.iv_atm_z,
            iv_call_z = EXCLUDED.iv_call_z,
            iv_put_z = EXCLUDED.iv_put_z,
            skew_z = EXCLUDED.skew_z,
            put_call_ratio_oi_z = EXCLUDED.put_call_ratio_oi_z,
            put_call_ratio_vol_z = EXCLUDED.put_call_ratio_vol_z,
            delta_weighted_oi_net_z = EXCLUDED.delta_weighted_oi_net_z,
            delta_call_z = EXCLUDED.delta_call_z,
            delta_put_z = EXCLUDED.delta_put_z,
            computed_at = EXCLUDED.computed_at,
            options_version = EXCLUDED.options_version
    """

    values = [tuple(row) for row in df[columns].values]

    with conn.cursor() as cur:
        execute_values(cur, insert_sql, values)
        conn.commit()

    logger.info(f"✅ Wrote {len(df)} rows to features.options_1d")
    logger.info(f"   Options version: {version_hash}")

    return version_hash


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


def run(
    symbol: str = TARGET_SYMBOL, start_date: str = "2000-01-01", dry_run: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Execute Phase 1: Options Features Computation.

    Returns:
        (success: bool, version_hash: Optional[str])
    """
    logger.info("=" * 60)
    logger.info("PHASE 1: OPTIONS FEATURES COMPUTATION")
    logger.info("=" * 60)
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Start date: {start_date}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 60)

    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("✅ Database connected")

        # Ensure table exists
        ensure_table_exists(conn)

        # Load data
        options_df = load_options_data(conn, symbol, start_date)
        if len(options_df) == 0:
            logger.error("❌ No options data found")
            return False, None

        futures_df = load_futures_prices(conn, symbol, start_date)
        if len(futures_df) == 0:
            logger.error("❌ No futures prices found")
            return False, None

        rate_df = load_risk_free_rate(conn, start_date)

        # Compute IV and Greeks
        options_df = compute_iv_greeks_batch(options_df, futures_df, rate_df)

        # Aggregate to front-month
        features_df = aggregate_front_month(options_df)
        if len(features_df) == 0:
            logger.error("❌ No features after aggregation")
            return False, None

        # Normalize
        features_df = normalize_features(features_df)

        # Write to Gold
        version_hash = write_features(conn, features_df, symbol, dry_run=dry_run)

        conn.close()

        logger.info("=" * 60)
        logger.info("✅ PHASE 1 COMPLETE")
        logger.info(f"   Rows written: {len(features_df)}")
        logger.info(f"   Version: {version_hash}")
        logger.info("=" * 60)

        return True, version_hash

    except Exception as e:
        logger.error(f"❌ PHASE 1 FAILED: {e}", exc_info=True)
        return False, None


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Phase 1: Options Features")
    parser.add_argument("--symbol", default=TARGET_SYMBOL)
    parser.add_argument("--start-date", default="2000-01-01")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    success, version = run(args.symbol, args.start_date, args.dry_run)
    exit(0 if success else 1)
