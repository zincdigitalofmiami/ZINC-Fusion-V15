#!/usr/bin/env python3
"""
Rebuild Elite Indicators with Fixed Code

This script recomputes features.elite_1d using the fixed
elite_indicators.py that handles edge cases:
- connors_rsi: division-safe RSI (no NaN on flat tape)
- garman_klass_vol: flat bar safe (H=L → 0, not NaN)
- cmf_21: zero volume safe (neutral outputs)

Supports multi-symbol processing for cross-asset elite indicators.

Usage:
    python scripts/rebuild_elite_indicators.py                   # All symbols
    python scripts/rebuild_elite_indicators.py --symbols ZL ZS   # Specific symbols
    python scripts/rebuild_elite_indicators.py --dry-run
"""

import sys
import os
import logging
from datetime import datetime

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fusion.features.elite_indicators_v2_INSTITUTIONAL import EliteIndicatorsV2

# Database URL from environment (load from .env if available)
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Default symbols to process (ZL primary + related instruments)
DEFAULT_SYMBOLS = [
    "ZL",   # Soybean Oil (primary)
    "ZS",   # Soybeans
    "ZM",   # Soymeal
    "CL",   # Crude Oil
    "HO",   # Heating Oil
    "RB",   # RBOB Gasoline
    "NG",   # Natural Gas
    "HG",   # Copper
    "GC",   # Gold
    "RS",   # Canola
    "CPO",  # Crude Palm Oil
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_ohlcv_data(conn, symbol: str) -> pd.DataFrame:
    """Load OHLCV data from mkt.futures_1d."""
    logger.info(f"Loading OHLCV data for {symbol}...")
    
    query = """
        SELECT 
            event_date as trade_date,
            symbol,
            open,
            high,
            low,
            close,
            volume
        FROM mkt.futures_1d
        WHERE symbol = %s
        ORDER BY event_date
    """
    
    df = pd.read_sql(query, conn, params=(symbol,))
    logger.info(f"   Loaded {len(df):,} rows")
    logger.info(f"   Date range: {df['trade_date'].min()} to {df['trade_date'].max()}")
    
    return df


def compute_additional_features(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Add returns and other base features."""
    # Ensure standard OHLCV columns exist
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' for {symbol}")

    # Returns
    df['returns_1d'] = df['close'].pct_change(1)
    df['log_returns_1d'] = np.log(df['close'] / df['close'].shift(1))
    df['range_pct'] = (df['high'] - df['low']) / df['close'].shift(1)
    
    return df


def write_to_features(conn, df: pd.DataFrame, symbol: str) -> int:
    """Write computed indicators to features.elite_1d."""
    logger.info("Writing to features.elite_1d...")
    
    # Filter to only the columns that exist in DB
    keep_cols = [
        'trade_date', 'symbol',
        'open', 'high', 'low', 'close', 'volume',
        'returns_1d', 'log_returns_1d', 'range_pct',
        # Tier 1
        'hurst_exponent', 'hurst_regime',
        'connors_rsi',
        'fisher_transform', 'fisher_signal',
        'mcginley_dynamic',
        'ttm_squeeze_on', 'ttm_squeeze_momentum',
        'schaff_trend_cycle',
        'rvi', 'rvi_signal',
        'elder_force_index',
        # Tier 2
        'kama_10', 'hma_20', 'alma_50',
        'rsi_2', 'rsi_14', 'cumulative_rsi',
        'macd', 'macd_signal', 'macd_histogram',
        'cci_14', 'cci_50',
        # Tier 3
        'atr_10', 'atr_50', 'atr_ratio',
        'garman_klass_vol', 'yang_zhang_vol', 'bb_percent_b',
        # Tier 4
        'cmf_21', 'volume_zscore', 'unusual_volume',
    ]
    
    # Keep only existing columns
    existing_cols = [c for c in keep_cols if c in df.columns]
    df_out = df[existing_cols].copy()

    # CLAMP numeric values to prevent DB overflow (precision 18, scale 6 = max 10^12)
    MAX_VALUE = 1e11  # Leave headroom below 10^12
    numeric_cols = df_out.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if col not in ['trade_date']:
            df_out[col] = df_out[col].clip(-MAX_VALUE, MAX_VALUE)
    logger.info(f"   Clamped numeric values to ±{MAX_VALUE:.0e}")

    # Cast boolean columns (DB expects bool, pandas has int)
    for bool_col in ['ttm_squeeze_on', 'unusual_volume']:
        if bool_col in df_out.columns:
            df_out[bool_col] = df_out[bool_col].astype(bool)

    # Add metadata
    df_out['created_at'] = datetime.utcnow()
    
    # Ensure symbol column
    if 'symbol' not in df_out.columns:
        df_out['symbol'] = symbol
    
    # Clear existing data
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM features.elite_1d WHERE symbol = %s",
            (symbol,)
        )
        deleted = cur.rowcount
        logger.info(f"   Cleared {deleted} existing rows")
    
    # Insert new data
    cols = list(df_out.columns)
    insert_sql = f"""
        INSERT INTO features.elite_1d ({','.join(cols)})
        VALUES %s
    """
    
    # Convert to list of tuples, handling NaN → None
    values = []
    for row in df_out.itertuples(index=False, name=None):
        row_clean = tuple(
            None if pd.isna(v) else v for v in row
        )
        values.append(row_clean)
    
    with conn.cursor() as cur:
        execute_values(cur, insert_sql, values, page_size=1000)
    
    conn.commit()
    logger.info(f"   Inserted {len(values):,} rows")
    
    return len(values)


def validate_null_rates(conn, symbol: str) -> dict:
    """Validate null rates for the three fixed indicators."""
    logger.info("Validating null rates...")
    
    results = {}
    
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 
                COUNT(*) as total,
                COUNT(*) - COUNT(connors_rsi) as null_connors,
                COUNT(*) - COUNT(garman_klass_vol) as null_gk,
                COUNT(*) - COUNT(cmf_21) as null_cmf
            FROM features.elite_1d
            WHERE symbol = %s
            """,
            (symbol,)
        )
        row = cur.fetchone()
        
        total = row[0]
        results['total_rows'] = total
        results['connors_rsi'] = {
            'nulls': row[1],
            'rate': row[1] / total if total > 0 else 0
        }
        results['garman_klass_vol'] = {
            'nulls': row[2],
            'rate': row[2] / total if total > 0 else 0
        }
        results['cmf_21'] = {
            'nulls': row[3],
            'rate': row[3] / total if total > 0 else 0
        }
    
    logger.info(f"   Total rows: {total:,}")
    for indicator in ['connors_rsi', 'garman_klass_vol', 'cmf_21']:
        rate = results[indicator]['rate']
        status = "✅" if rate <= 0.05 else "❌"
        logger.info(f"   {status} {indicator}: {results[indicator]['nulls']:,} nulls ({rate:.1%})")
    
    return results


def check_scattered_nulls(conn, symbol: str) -> dict:
    """Check for scattered nulls in the three fixed indicators."""
    logger.info("Checking for scattered nulls...")
    
    results = {}
    
    for indicator in ['connors_rsi', 'garman_klass_vol', 'cmf_21']:
        with conn.cursor() as cur:
            # Find first non-null date
            cur.execute(
                f"""
                SELECT MIN(trade_date)
                FROM features.elite_1d
                WHERE symbol = %s AND {indicator} IS NOT NULL
                """,
                (symbol,)
            )
            first_valid = cur.fetchone()[0]
            
            if first_valid:
                # Count nulls after first valid
                cur.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM features.elite_1d
                    WHERE symbol = %s 
                      AND trade_date >= %s 
                      AND {indicator} IS NULL
                    """,
                    (symbol, first_valid)
                )
                scattered = cur.fetchone()[0]
            else:
                scattered = 0
            
            results[indicator] = {
                'first_valid': str(first_valid) if first_valid else None,
                'scattered_nulls': scattered
            }
            
            status = "✅" if scattered == 0 else "❌"
            logger.info(f"   {status} {indicator}: {scattered} scattered nulls (first_valid={first_valid})")
    
    return results


def process_symbol(conn, symbol: str, dry_run: bool = False) -> dict:
    """Process a single symbol. Returns summary dict."""
    from datetime import date

    logger.info("")
    logger.info(f"Processing {symbol}...")

    # Load OHLCV data
    df = load_ohlcv_data(conn, symbol)

    if len(df) == 0:
        logger.warning(f"   No data found for {symbol}, skipping")
        return {"symbol": symbol, "status": "no_data", "rows": 0}

    # MODIFIED 2026-01-23: NO DATE FILTER - use ALL available data
    logger.info(f"   Using ALL available data: {len(df):,} rows")

    if len(df) < 50:
        logger.warning(f"   Insufficient data ({len(df)} rows < 50 min), skipping")
        return {"symbol": symbol, "status": "insufficient_data", "rows": len(df)}

    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date")

    # Compute elite indicators
    try:
        calc = EliteIndicatorsV2(df)
        df = calc.calculate_all()
    except Exception as e:
        logger.error(f"   Failed to compute indicators for {symbol}: {e}")
        return {"symbol": symbol, "status": "compute_error", "error": str(e)}

    # Add returns and base features
    df = compute_additional_features(df, symbol)
    df = df.reset_index()
    if "symbol" not in df.columns:
        df["symbol"] = symbol

    if dry_run:
        # Show null rates for verification
        for indicator in ['connors_rsi', 'garman_klass_vol', 'cmf_21']:
            if indicator in df.columns:
                null_count = df[indicator].isna().sum()
                null_rate = null_count / len(df) if len(df) > 0 else 0
                status = "✅" if null_rate <= 0.05 else "❌"
                logger.info(f"   {status} {indicator}: {null_count:,} nulls ({null_rate:.1%})")

        return {"symbol": symbol, "status": "dry_run", "rows": len(df)}
    else:
        # Write to features table
        rows_written = write_to_features(conn, df, symbol)

        # Validate results
        validate_null_rates(conn, symbol)
        check_scattered_nulls(conn, symbol)

        return {"symbol": symbol, "status": "success", "rows": rows_written}


def main(symbols: list[str] = None, dry_run: bool = False):
    """Main rebuild function for multiple symbols."""
    if symbols is None:
        symbols = DEFAULT_SYMBOLS

    logger.info("=" * 70)
    logger.info("ELITE INDICATORS REBUILD (Multi-Symbol)")
    logger.info("=" * 70)
    logger.info(f"Symbols: {', '.join(symbols)}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 70)

    # Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    logger.info("✅ Database connected")

    results = []
    try:
        for symbol in symbols:
            result = process_symbol(conn, symbol, dry_run)
            results.append(result)

        conn.close()

        # Summary
        logger.info("")
        logger.info("=" * 70)
        logger.info("SUMMARY")
        logger.info("=" * 70)
        success_count = sum(1 for r in results if r["status"] == "success")
        total_rows = sum(r.get("rows", 0) for r in results if r["status"] in ("success", "dry_run"))

        for r in results:
            status_icon = "✅" if r["status"] in ("success", "dry_run") else "❌"
            logger.info(f"  {status_icon} {r['symbol']:6s}: {r['status']:15s} ({r.get('rows', 0):,} rows)")

        logger.info("")
        if dry_run:
            logger.info(f"DRY RUN COMPLETE - {len(symbols)} symbols checked, {total_rows:,} rows would be written")
        else:
            logger.info(f"✅ REBUILD COMPLETE - {success_count}/{len(symbols)} symbols, {total_rows:,} rows written")
        logger.info("=" * 70)

    except Exception as e:
        conn.close()
        logger.error(f"❌ REBUILD FAILED: {e}", exc_info=True)
        return False

    return True


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Rebuild Elite Indicators")
    parser.add_argument('--dry-run', action='store_true',
                        help="Compute but don't write to database")
    parser.add_argument('--symbols', nargs='+', default=None,
                        help=f"Symbols to process (default: {DEFAULT_SYMBOLS})")
    args = parser.parse_args()

    success = main(symbols=args.symbols, dry_run=args.dry_run)
    exit(0 if success else 1)
