#!/usr/bin/env python3
"""
Rebuild Elite Indicators with Fixed Code

This script recomputes gold.elite_indicators_1d using the fixed 
elite_indicators.py that handles edge cases:
- connors_rsi: division-safe RSI (no NaN on flat tape)
- garman_klass_vol: flat bar safe (H=L → 0, not NaN)
- cmf_21: zero volume safe (neutral outputs)

Usage:
    python scripts/rebuild_elite_indicators.py
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

from fusion.features.elite_indicators import EliteIndicators

# Database URL from environment or default
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgres://d687a7ec267e124a21607a1e5dd9a89d60c9a122d219e499e32f3eee42a858c0:sk_NLg8ZV3VJ61FPM0F_QHMe@db.prisma.io:5432/postgres?sslmode=require"
)

TARGET_SYMBOL = "ZL"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_ohlcv_data(conn, symbol: str) -> pd.DataFrame:
    """Load OHLCV data from raw.market_futures_1d."""
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
        FROM raw.market_futures_1d
        WHERE symbol = %s
        ORDER BY event_date
    """
    
    df = pd.read_sql(query, conn, params=(symbol,))
    logger.info(f"   Loaded {len(df):,} rows")
    logger.info(f"   Date range: {df['trade_date'].min()} to {df['trade_date'].max()}")
    
    # Rename columns to match EliteIndicators expected format
    df = df.rename(columns={
        'open': f'{symbol}_open',
        'high': f'{symbol}_high',
        'low': f'{symbol}_low',
        'close': f'{symbol}_close',
        'volume': f'{symbol}_volume',
    })
    
    return df


def compute_additional_features(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Add returns and other base features."""
    close_col = f'{symbol}_close'
    
    df['close'] = df[close_col]
    df['open'] = df[f'{symbol}_open']
    df['high'] = df[f'{symbol}_high']
    df['low'] = df[f'{symbol}_low']
    df['volume'] = df[f'{symbol}_volume']
    
    # Returns
    df['returns_1d'] = df['close'].pct_change(1)
    df['log_returns_1d'] = np.log(df['close'] / df['close'].shift(1))
    df['range_pct'] = (df['high'] - df['low']) / df['close'].shift(1)
    
    return df


def write_to_gold(conn, df: pd.DataFrame, symbol: str) -> int:
    """Write computed indicators to gold.elite_indicators_1d."""
    logger.info("Writing to gold.elite_indicators_1d...")
    
    # Filter to only the columns we want to store
    keep_cols = [
        'trade_date', 'symbol',
        'open', 'high', 'low', 'close', 'volume',
        'returns_1d', 'log_returns_1d', 'range_pct',
        # Tier 1
        'hurst_exponent', 'hurst_regime',
        'connors_rsi', 'connors_rsi_overbought', 'connors_rsi_oversold',
        'fisher_transform', 'fisher_signal', 'fisher_overbought', 'fisher_oversold',
        'mcginley_dynamic', 'mcginley_signal',
        'ttm_squeeze_on', 'ttm_squeeze_momentum', 'ttm_squeeze_count',
        'schaff_trend_cycle', 'stc_bullish', 'stc_bearish',
        'rvi', 'rvi_signal', 'rvi_histogram',
        'elder_force_index', 'efi_bullish', 'efi_bearish',
        # Tier 2
        'kama_10', 'hma_20', 'alma_50', 'mcginley_100',
        'price_vs_kama10_pct', 'price_vs_hma20_pct', 'price_vs_alma50_pct', 'price_vs_mcg100_pct',
        'rsi_2', 'rsi_14', 'cumulative_rsi', 'rsi2_buy_signal', 'rsi2_sell_signal',
        'macd', 'macd_signal', 'macd_histogram',
        'macd_fast', 'macd_fast_signal', 'macd_fast_histogram',
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
    
    # Add metadata
    df_out['created_at'] = datetime.utcnow()
    
    # Ensure symbol column
    if 'symbol' not in df_out.columns:
        df_out['symbol'] = symbol
    
    # Clear existing data
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM gold.elite_indicators_1d WHERE symbol = %s",
            (symbol,)
        )
        deleted = cur.rowcount
        logger.info(f"   Cleared {deleted} existing rows")
    
    # Insert new data
    cols = list(df_out.columns)
    insert_sql = f"""
        INSERT INTO gold.elite_indicators_1d ({','.join(cols)})
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
            FROM gold.elite_indicators_1d
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
                FROM gold.elite_indicators_1d
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
                    FROM gold.elite_indicators_1d
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


def main(dry_run: bool = False):
    """Main rebuild function."""
    logger.info("=" * 70)
    logger.info("ELITE INDICATORS REBUILD")
    logger.info("=" * 70)
    logger.info(f"Symbol: {TARGET_SYMBOL}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 70)
    
    # Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    logger.info("✅ Database connected")
    
    try:
        # Load OHLCV data
        df = load_ohlcv_data(conn, TARGET_SYMBOL)
        
        # Filter to 2000+ (matches existing gold table)
        from datetime import date
        df = df[df['trade_date'] >= date(2000, 1, 1)].copy()
        logger.info(f"   Filtered to 2000+: {len(df):,} rows")
        
        # Compute elite indicators
        logger.info("")
        logger.info("-" * 70)
        elite = EliteIndicators(df, symbol=TARGET_SYMBOL)
        df = elite.compute_all()
        logger.info("-" * 70)
        
        # Add returns and base features
        df = compute_additional_features(df, TARGET_SYMBOL)
        
        if dry_run:
            logger.info("")
            logger.info("DRY RUN - Not writing to database")
            logger.info("")
            
            # Show null rates for verification
            for indicator in ['connors_rsi', 'garman_klass_vol', 'cmf_21']:
                null_count = df[indicator].isna().sum()
                null_rate = null_count / len(df)
                status = "✅" if null_rate <= 0.05 else "❌"
                logger.info(f"   {status} {indicator}: {null_count:,} nulls ({null_rate:.1%})")
            
        else:
            # Write to gold table
            logger.info("")
            rows_written = write_to_gold(conn, df, TARGET_SYMBOL)
            
            # Validate results
            logger.info("")
            null_results = validate_null_rates(conn, TARGET_SYMBOL)
            
            logger.info("")
            scattered_results = check_scattered_nulls(conn, TARGET_SYMBOL)
        
        conn.close()
        
        logger.info("")
        logger.info("=" * 70)
        logger.info("✅ REBUILD COMPLETE")
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
    args = parser.parse_args()
    
    success = main(dry_run=args.dry_run)
    exit(0 if success else 1)
