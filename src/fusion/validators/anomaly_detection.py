"""
ZINC-FUSION-V15 Anomaly Detection Module

Computes anomaly_flags and quality_score for all raw.* tables.
These fields are REQUIRED by the Bronze Contract but were never implemented.

Usage:
    # Backfill all tables
    python -m src.fusion.validators.anomaly_detection --backfill

    # Check specific table
    python -m src.fusion.validators.anomaly_detection --table market_futures_1d

Reference: Docs/BRONZE_CONTRACT_SPEC_LOCKED.md
"""

import os
import sys
import argparse
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import json

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# =============================================================================
# ANOMALY FLAG DEFINITIONS BY TABLE TYPE
# =============================================================================

@dataclass
class AnomalyThresholds:
    """Thresholds for anomaly detection."""
    zscore_extreme: float = 4.0      # >4 std = extreme outlier
    zscore_warning: float = 3.0      # >3 std = warning
    pct_change_spike: float = 0.15   # 15% single-day move
    pct_change_extreme: float = 0.25 # 25% single-day move
    gap_threshold: float = 0.05      # 5% gap up/down
    volume_spike_mult: float = 5.0   # 5x average volume


# Market Futures Anomaly Flags
MARKET_ANOMALY_FLAGS = [
    "price_spike",           # >15% single-day move
    "price_extreme",         # >25% single-day move
    "volume_spike",          # >5x 20-day average volume
    "volume_zero",           # Zero volume (data issue)
    "gap_up",                # >5% gap from prior close
    "gap_down",              # <-5% gap from prior close
    "limit_move",            # Hit exchange limits
    "stale_price",           # Same OHLC as prior day
    "invalid_ohlc",          # High < Low or Open/Close outside range
    "weekend_data",          # Data on Saturday/Sunday (suspicious)
    "holiday_data",          # Data on known holiday (suspicious)
]

# Weather Anomaly Flags
WEATHER_ANOMALY_FLAGS = [
    "temp_spike",            # >20C daily change
    "temp_extreme_high",     # >50C (record territory)
    "temp_extreme_low",      # <-50C (record territory)
    "precip_extreme",        # >200mm single day
    "precip_negative",       # Negative precipitation (data error)
    "snow_in_summer",        # Snow where/when impossible
    "missing_station",       # Station ID unknown
    "duplicate_reading",     # Exact same values as prior day
    "implausible_humidity",  # >100% or <0%
]

# FRED Anomaly Flags
FRED_ANOMALY_FLAGS = [
    "value_spike",           # >4 std from rolling mean
    "value_negative",        # Negative for always-positive series
    "revision_large",        # >10% revision from prior value
    "future_dated",          # Event date in future
    "stale_series",          # No update in expected window
    "duplicate_value",       # Exact same value as prior observation
]

# News Anomaly Flags
NEWS_ANOMALY_FLAGS = [
    "sentiment_extreme",     # |sentiment| > 0.95
    "duplicate_content",     # Same content hash
    "empty_content",         # No content/headline
    "future_published",      # Published date in future
    "ancient_article",       # >30 days old at ingestion
]

# COT Anomaly Flags
COT_ANOMALY_FLAGS = [
    "position_spike",        # >50% weekly change in net position
    "oi_spike",              # >30% weekly change in open interest
    "impossible_position",   # Net position > OI
    "zero_oi",               # Zero open interest
    "stale_report",          # Same values as prior week
]

# FX Anomaly Flags
FX_ANOMALY_FLAGS = [
    "rate_spike",            # >5% single-day move
    "rate_extreme",          # >10% single-day move
    "rate_negative",         # Negative rate (data error)
    "rate_zero",             # Zero rate (data error)
    "stale_rate",            # Same rate as prior day
    "weekend_rate",          # Rate on weekend
]

# RIN Anomaly Flags
RIN_ANOMALY_FLAGS = [
    "price_spike",           # >20% single-day move
    "price_negative",        # Negative RIN price
    "price_extreme_high",    # >$3.00/RIN (historically rare)
    "price_zero",            # Zero price (data error)
    "stale_price",           # Same price 5+ consecutive days
]


# =============================================================================
# ANOMALY DETECTION FUNCTIONS
# =============================================================================

class AnomalyDetector:
    """Detects anomalies in raw data tables."""

    def __init__(self, conn, thresholds: Optional[AnomalyThresholds] = None):
        self.conn = conn
        self.thresholds = thresholds or AnomalyThresholds()

    def detect_market_futures(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect anomalies in market_futures_1d data.

        Returns DataFrame with anomaly_flags and quality_score columns.
        """
        results = []

        # Group by symbol for symbol-specific stats
        for symbol, group in df.groupby('symbol'):
            group = group.sort_values('event_date').copy()

            for idx, row in group.iterrows():
                flags = []
                quality_deductions = 0

                # Get prior row for comparisons
                prior_idx = group.index.get_loc(idx)
                prior_row = group.iloc[prior_idx - 1] if prior_idx > 0 else None

                # 1. Price spike detection
                if prior_row is not None and prior_row['close'] > 0:
                    pct_change = abs(row['close'] - prior_row['close']) / prior_row['close']
                    if pct_change > self.thresholds.pct_change_extreme:
                        flags.append('price_extreme')
                        quality_deductions += 20
                    elif pct_change > self.thresholds.pct_change_spike:
                        flags.append('price_spike')
                        quality_deductions += 10

                # 2. Gap detection
                if prior_row is not None and prior_row['close'] > 0:
                    gap = (row['open'] - prior_row['close']) / prior_row['close']
                    if gap > self.thresholds.gap_threshold:
                        flags.append('gap_up')
                        quality_deductions += 5
                    elif gap < -self.thresholds.gap_threshold:
                        flags.append('gap_down')
                        quality_deductions += 5

                # 3. Volume spike (compare to 20-day average)
                if prior_idx >= 20:
                    avg_vol = group.iloc[prior_idx-20:prior_idx]['volume'].mean()
                    if avg_vol > 0 and row['volume'] > avg_vol * self.thresholds.volume_spike_mult:
                        flags.append('volume_spike')
                        quality_deductions += 5

                # 4. Zero volume
                if row['volume'] == 0:
                    flags.append('volume_zero')
                    quality_deductions += 15

                # 5. Invalid OHLC
                if row['high'] < row['low']:
                    flags.append('invalid_ohlc')
                    quality_deductions += 30
                if row['open'] > row['high'] or row['open'] < row['low']:
                    flags.append('invalid_ohlc')
                    quality_deductions += 30
                if row['close'] > row['high'] or row['close'] < row['low']:
                    flags.append('invalid_ohlc')
                    quality_deductions += 30

                # 6. Stale price (same OHLC as prior day)
                if prior_row is not None:
                    if (row['open'] == prior_row['open'] and
                        row['high'] == prior_row['high'] and
                        row['low'] == prior_row['low'] and
                        row['close'] == prior_row['close']):
                        flags.append('stale_price')
                        quality_deductions += 20

                # 7. Weekend data
                if hasattr(row['event_date'], 'weekday'):
                    if row['event_date'].weekday() >= 5:  # Saturday=5, Sunday=6
                        flags.append('weekend_data')
                        quality_deductions += 10

                # Calculate quality score (100 - deductions, min 0)
                quality_score = max(0, 100 - quality_deductions)

                results.append({
                    'event_date': row['event_date'],
                    'symbol': symbol,
                    'anomaly_flags': flags if flags else None,
                    'quality_score': quality_score,
                })

        return pd.DataFrame(results)

    def detect_weather(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect anomalies in weather_noaa_1d data."""
        results = []

        for idx, row in df.iterrows():
            flags = []
            quality_deductions = 0

            # Temperature checks
            if pd.notna(row.get('tavg_c')):
                if row['tavg_c'] > 50:
                    flags.append('temp_extreme_high')
                    quality_deductions += 25
                elif row['tavg_c'] < -50:
                    flags.append('temp_extreme_low')
                    quality_deductions += 25

            if pd.notna(row.get('tmax_c')) and pd.notna(row.get('tmin_c')):
                if row['tmax_c'] - row['tmin_c'] > 40:
                    flags.append('temp_spike')
                    quality_deductions += 15

            # Precipitation checks
            if pd.notna(row.get('prcp_mm')):
                if row['prcp_mm'] < 0:
                    flags.append('precip_negative')
                    quality_deductions += 30
                elif row['prcp_mm'] > 200:
                    flags.append('precip_extreme')
                    quality_deductions += 10

            # Humidity checks
            if pd.notna(row.get('rhav_pct')):
                if row['rhav_pct'] > 100 or row['rhav_pct'] < 0:
                    flags.append('implausible_humidity')
                    quality_deductions += 25

            quality_score = max(0, 100 - quality_deductions)

            results.append({
                'id': row.get('id'),
                'anomaly_flags': flags if flags else None,
                'quality_score': quality_score,
            })

        return pd.DataFrame(results)

    def detect_fred(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect anomalies in fred_observations_1d data."""
        results = []

        # Group by series for series-specific stats
        for series_id, group in df.groupby('series_id'):
            group = group.sort_values('event_date').copy()

            # Calculate rolling stats for z-score
            if len(group) >= 20:
                group['rolling_mean'] = group['value'].rolling(20).mean()
                group['rolling_std'] = group['value'].rolling(20).std()

            for idx, row in group.iterrows():
                flags = []
                quality_deductions = 0

                # Get prior row
                prior_idx = group.index.get_loc(idx)
                prior_row = group.iloc[prior_idx - 1] if prior_idx > 0 else None

                # 1. Z-score spike
                if pd.notna(row.get('rolling_mean')) and pd.notna(row.get('rolling_std')):
                    if row['rolling_std'] > 0:
                        zscore = abs(row['value'] - row['rolling_mean']) / row['rolling_std']
                        if zscore > self.thresholds.zscore_extreme:
                            flags.append('value_spike')
                            quality_deductions += 15

                # 2. Large revision
                if prior_row is not None and prior_row['value'] != 0:
                    pct_change = abs(row['value'] - prior_row['value']) / abs(prior_row['value'])
                    if pct_change > 0.10:
                        flags.append('revision_large')
                        quality_deductions += 10

                # 3. Future dated
                if hasattr(row['event_date'], 'date'):
                    if row['event_date'].date() > datetime.now().date():
                        flags.append('future_dated')
                        quality_deductions += 20

                # 4. Duplicate value (same as prior)
                if prior_row is not None and row['value'] == prior_row['value']:
                    flags.append('duplicate_value')
                    quality_deductions += 5

                quality_score = max(0, 100 - quality_deductions)

                results.append({
                    'id': row.get('id'),
                    'anomaly_flags': flags if flags else None,
                    'quality_score': quality_score,
                })

        return pd.DataFrame(results)

    def detect_news(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect anomalies in news_articles_1d data."""
        results = []

        for idx, row in df.iterrows():
            flags = []
            quality_deductions = 0

            # 1. Extreme sentiment
            if pd.notna(row.get('sentiment_score')):
                if abs(row['sentiment_score']) > 0.95:
                    flags.append('sentiment_extreme')
                    quality_deductions += 10

            # 2. Empty content
            if pd.isna(row.get('headline')) or str(row.get('headline', '')).strip() == '':
                flags.append('empty_content')
                quality_deductions += 30

            # 3. Future published
            if pd.notna(row.get('published_at')):
                if hasattr(row['published_at'], 'date'):
                    if row['published_at'].date() > datetime.now().date():
                        flags.append('future_published')
                        quality_deductions += 25

            quality_score = max(0, 100 - quality_deductions)

            results.append({
                'id': row.get('id'),
                'anomaly_flags': flags if flags else None,
                'quality_score': quality_score,
            })

        return pd.DataFrame(results)

    def detect_cot(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect anomalies in cftc_cot_1w data."""
        results = []

        for symbol, group in df.groupby('symbol'):
            group = group.sort_values('event_date').copy()

            for idx, row in group.iterrows():
                flags = []
                quality_deductions = 0

                prior_idx = group.index.get_loc(idx)
                prior_row = group.iloc[prior_idx - 1] if prior_idx > 0 else None

                # 1. Position spike (>50% weekly change)
                if prior_row is not None and prior_row['managed_money_net'] != 0:
                    pct_change = abs(row['managed_money_net'] - prior_row['managed_money_net']) / abs(prior_row['managed_money_net'])
                    if pct_change > 0.50:
                        flags.append('position_spike')
                        quality_deductions += 15

                # 2. OI spike (>30% weekly change)
                if prior_row is not None and prior_row['open_interest'] > 0:
                    oi_change = abs(row['open_interest'] - prior_row['open_interest']) / prior_row['open_interest']
                    if oi_change > 0.30:
                        flags.append('oi_spike')
                        quality_deductions += 10

                # 3. Zero OI
                if row['open_interest'] == 0:
                    flags.append('zero_oi')
                    quality_deductions += 25

                # 4. Impossible position (net > OI)
                if abs(row['managed_money_net']) > row['open_interest']:
                    flags.append('impossible_position')
                    quality_deductions += 30

                quality_score = max(0, 100 - quality_deductions)

                results.append({
                    'id': row.get('id'),
                    'anomaly_flags': flags if flags else None,
                    'quality_score': quality_score,
                })

        return pd.DataFrame(results)

    def detect_fx(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect anomalies in fx_spot_1d data."""
        results = []

        for pair, group in df.groupby('pair'):
            group = group.sort_values('event_date').copy()

            for idx, row in group.iterrows():
                flags = []
                quality_deductions = 0

                prior_idx = group.index.get_loc(idx)
                prior_row = group.iloc[prior_idx - 1] if prior_idx > 0 else None

                # 1. Rate spike
                if prior_row is not None and prior_row['rate'] > 0:
                    pct_change = abs(row['rate'] - prior_row['rate']) / prior_row['rate']
                    if pct_change > 0.10:
                        flags.append('rate_extreme')
                        quality_deductions += 20
                    elif pct_change > 0.05:
                        flags.append('rate_spike')
                        quality_deductions += 10

                # 2. Rate errors
                if row['rate'] <= 0:
                    flags.append('rate_zero' if row['rate'] == 0 else 'rate_negative')
                    quality_deductions += 30

                # 3. Stale rate
                if prior_row is not None and row['rate'] == prior_row['rate']:
                    flags.append('stale_rate')
                    quality_deductions += 10

                # 4. Weekend rate
                if hasattr(row['event_date'], 'weekday'):
                    if row['event_date'].weekday() >= 5:
                        flags.append('weekend_rate')
                        quality_deductions += 10

                quality_score = max(0, 100 - quality_deductions)

                results.append({
                    'id': row.get('id'),
                    'anomaly_flags': flags if flags else None,
                    'quality_score': quality_score,
                })

        return pd.DataFrame(results)

    def detect_rin(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect anomalies in epa_rin_prices_1d data."""
        results = []

        for rin_type, group in df.groupby('rin_type'):
            group = group.sort_values('event_date').copy()

            for idx, row in group.iterrows():
                flags = []
                quality_deductions = 0

                prior_idx = group.index.get_loc(idx)
                prior_row = group.iloc[prior_idx - 1] if prior_idx > 0 else None

                # 1. Price spike
                if prior_row is not None and prior_row['price'] > 0:
                    pct_change = abs(row['price'] - prior_row['price']) / prior_row['price']
                    if pct_change > 0.20:
                        flags.append('price_spike')
                        quality_deductions += 15

                # 2. Price errors
                if row['price'] < 0:
                    flags.append('price_negative')
                    quality_deductions += 30
                elif row['price'] == 0:
                    flags.append('price_zero')
                    quality_deductions += 25
                elif row['price'] > 3.00:
                    flags.append('price_extreme_high')
                    quality_deductions += 10

                quality_score = max(0, 100 - quality_deductions)

                results.append({
                    'id': row.get('id'),
                    'anomaly_flags': flags if flags else None,
                    'quality_score': quality_score,
                })

        return pd.DataFrame(results)


# =============================================================================
# BACKFILL FUNCTIONS
# =============================================================================

def backfill_market_futures(conn, batch_size: int = 1000) -> int:
    """Backfill anomaly_flags and quality_score for market_futures_1d."""
    logger.info("Backfilling market_futures_1d...")

    # Load data
    df = pd.read_sql("""
        SELECT event_date, symbol, open, high, low, close, volume
        FROM raw.market_futures_1d
        ORDER BY symbol, event_date
    """, conn)

    if df.empty:
        logger.warning("No data in market_futures_1d")
        return 0

    logger.info(f"  Loaded {len(df):,} rows")

    # Detect anomalies
    detector = AnomalyDetector(conn)
    results = detector.detect_market_futures(df)

    # Update database
    update_query = """
        UPDATE raw.market_futures_1d
        SET anomaly_flags = %s, quality_score = %s
        WHERE event_date = %s AND symbol = %s
    """

    updates = []
    for _, row in results.iterrows():
        flags = row['anomaly_flags'] if row['anomaly_flags'] else []
        updates.append((flags, row['quality_score'], row['event_date'], row['symbol']))

    with conn.cursor() as cur:
        execute_batch(cur, update_query, updates, page_size=batch_size)
    conn.commit()

    flagged = results[results['anomaly_flags'].notna()].shape[0]
    logger.info(f"  Updated {len(results):,} rows, {flagged:,} with anomaly flags")
    return len(results)


def backfill_weather(conn, batch_size: int = 1000) -> int:
    """Backfill anomaly_flags and quality_score for weather_noaa_1d."""
    logger.info("Backfilling weather_noaa_1d...")

    df = pd.read_sql("""
        SELECT id, event_date, tavg_c, tmin_c, tmax_c, prcp_mm, rhav_pct
        FROM raw.weather_noaa_1d
    """, conn)

    if df.empty:
        return 0

    logger.info(f"  Loaded {len(df):,} rows")

    detector = AnomalyDetector(conn)
    results = detector.detect_weather(df)

    update_query = """
        UPDATE raw.weather_noaa_1d
        SET anomaly_flags = %s, quality_score = %s
        WHERE id = %s
    """

    updates = []
    for _, row in results.iterrows():
        flags = row['anomaly_flags'] if row['anomaly_flags'] else []
        updates.append((flags, row['quality_score'], row['id']))

    with conn.cursor() as cur:
        execute_batch(cur, update_query, updates, page_size=batch_size)
    conn.commit()

    flagged = results[results['anomaly_flags'].notna()].shape[0]
    logger.info(f"  Updated {len(results):,} rows, {flagged:,} with anomaly flags")
    return len(results)


def backfill_fred(conn, batch_size: int = 1000) -> int:
    """Backfill anomaly_flags and quality_score for fred_observations_1d."""
    logger.info("Backfilling fred_observations_1d...")

    df = pd.read_sql("""
        SELECT id, series_id, event_date, value
        FROM raw.fred_observations_1d
        ORDER BY series_id, event_date
    """, conn)

    if df.empty:
        return 0

    logger.info(f"  Loaded {len(df):,} rows")

    detector = AnomalyDetector(conn)
    results = detector.detect_fred(df)

    update_query = """
        UPDATE raw.fred_observations_1d
        SET anomaly_flags = %s, quality_score = %s
        WHERE id = %s
    """

    updates = []
    for _, row in results.iterrows():
        flags = row['anomaly_flags'] if row['anomaly_flags'] else []
        updates.append((flags, row['quality_score'], row['id']))

    with conn.cursor() as cur:
        execute_batch(cur, update_query, updates, page_size=batch_size)
    conn.commit()

    flagged = results[results['anomaly_flags'].notna()].shape[0]
    logger.info(f"  Updated {len(results):,} rows, {flagged:,} with anomaly flags")
    return len(results)


def backfill_news(conn, batch_size: int = 1000) -> int:
    """Backfill anomaly_flags and quality_score for news_articles_1d."""
    logger.info("Backfilling news_articles_1d...")

    df = pd.read_sql("""
        SELECT id, headline, published_at, sentiment_score
        FROM raw.news_articles_1d
    """, conn)

    if df.empty:
        return 0

    logger.info(f"  Loaded {len(df):,} rows")

    detector = AnomalyDetector(conn)
    results = detector.detect_news(df)

    update_query = """
        UPDATE raw.news_articles_1d
        SET anomaly_flags = %s, quality_score = %s
        WHERE id = %s
    """

    updates = []
    for _, row in results.iterrows():
        flags = row['anomaly_flags'] if row['anomaly_flags'] else []
        updates.append((flags, row['quality_score'], row['id']))

    with conn.cursor() as cur:
        execute_batch(cur, update_query, updates, page_size=batch_size)
    conn.commit()

    flagged = results[results['anomaly_flags'].notna()].shape[0]
    logger.info(f"  Updated {len(results):,} rows, {flagged:,} with anomaly flags")
    return len(results)


def backfill_cot(conn, batch_size: int = 1000) -> int:
    """Backfill anomaly_flags and quality_score for cftc_cot_1w."""
    logger.info("Backfilling cftc_cot_1w...")

    df = pd.read_sql("""
        SELECT id, event_date, symbol, open_interest, managed_money_net
        FROM raw.cftc_cot_1w
        ORDER BY symbol, event_date
    """, conn)

    if df.empty:
        return 0

    logger.info(f"  Loaded {len(df):,} rows")

    detector = AnomalyDetector(conn)
    results = detector.detect_cot(df)

    update_query = """
        UPDATE raw.cftc_cot_1w
        SET anomaly_flags = %s, quality_score = %s
        WHERE id = %s
    """

    updates = []
    for _, row in results.iterrows():
        flags = row['anomaly_flags'] if row['anomaly_flags'] else []
        updates.append((flags, row['quality_score'], row['id']))

    with conn.cursor() as cur:
        execute_batch(cur, update_query, updates, page_size=batch_size)
    conn.commit()

    flagged = results[results['anomaly_flags'].notna()].shape[0]
    logger.info(f"  Updated {len(results):,} rows, {flagged:,} with anomaly flags")
    return len(results)


def backfill_fx(conn, batch_size: int = 1000) -> int:
    """Backfill anomaly_flags and quality_score for fx_spot_1d."""
    logger.info("Backfilling fx_spot_1d...")

    df = pd.read_sql("""
        SELECT id, pair, event_date, rate
        FROM raw.fx_spot_1d
        ORDER BY pair, event_date
    """, conn)

    if df.empty:
        return 0

    logger.info(f"  Loaded {len(df):,} rows")

    detector = AnomalyDetector(conn)
    results = detector.detect_fx(df)

    update_query = """
        UPDATE raw.fx_spot_1d
        SET anomaly_flags = %s, quality_score = %s
        WHERE id = %s
    """

    updates = []
    for _, row in results.iterrows():
        flags = row['anomaly_flags'] if row['anomaly_flags'] else []
        updates.append((flags, row['quality_score'], row['id']))

    with conn.cursor() as cur:
        execute_batch(cur, update_query, updates, page_size=batch_size)
    conn.commit()

    flagged = results[results['anomaly_flags'].notna()].shape[0]
    logger.info(f"  Updated {len(results):,} rows, {flagged:,} with anomaly flags")
    return len(results)


def backfill_rin(conn, batch_size: int = 1000) -> int:
    """Backfill anomaly_flags and quality_score for epa_rin_prices_1d."""
    logger.info("Backfilling epa_rin_prices_1d...")

    df = pd.read_sql("""
        SELECT id, rin_type, event_date, price
        FROM raw.epa_rin_prices_1d
        ORDER BY rin_type, event_date
    """, conn)

    if df.empty:
        return 0

    logger.info(f"  Loaded {len(df):,} rows")

    detector = AnomalyDetector(conn)
    results = detector.detect_rin(df)

    update_query = """
        UPDATE raw.epa_rin_prices_1d
        SET anomaly_flags = %s, quality_score = %s
        WHERE id = %s
    """

    updates = []
    for _, row in results.iterrows():
        flags = row['anomaly_flags'] if row['anomaly_flags'] else []
        updates.append((flags, row['quality_score'], row['id']))

    with conn.cursor() as cur:
        execute_batch(cur, update_query, updates, page_size=batch_size)
    conn.commit()

    flagged = results[results['anomaly_flags'].notna()].shape[0]
    logger.info(f"  Updated {len(results):,} rows, {flagged:,} with anomaly flags")
    return len(results)


def backfill_all(conn) -> Dict[str, int]:
    """Backfill all raw tables with anomaly_flags and quality_score."""
    logger.info("=" * 60)
    logger.info("ANOMALY DETECTION BACKFILL - ALL TABLES")
    logger.info("=" * 60)

    results = {}

    results['market_futures_1d'] = backfill_market_futures(conn)
    results['weather_noaa_1d'] = backfill_weather(conn)
    results['fred_observations_1d'] = backfill_fred(conn)
    results['news_articles_1d'] = backfill_news(conn)
    results['cftc_cot_1w'] = backfill_cot(conn)
    results['fx_spot_1d'] = backfill_fx(conn)
    results['epa_rin_prices_1d'] = backfill_rin(conn)

    logger.info("=" * 60)
    logger.info("BACKFILL COMPLETE")
    logger.info("=" * 60)

    total = sum(results.values())
    logger.info(f"Total rows updated: {total:,}")
    for table, count in results.items():
        logger.info(f"  {table}: {count:,}")

    return results


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Anomaly detection for raw tables")
    parser.add_argument("--backfill", action="store_true", help="Backfill all tables")
    parser.add_argument("--table", type=str, help="Backfill specific table")
    args = parser.parse_args()

    conn_string = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not conn_string:
        print("ERROR: DATABASE_URL or POSTGRES_URL required")
        sys.exit(1)

    conn = psycopg2.connect(conn_string)

    try:
        if args.backfill:
            backfill_all(conn)
        elif args.table:
            table_map = {
                'market_futures_1d': backfill_market_futures,
                'weather_noaa_1d': backfill_weather,
                'fred_observations_1d': backfill_fred,
                'news_articles_1d': backfill_news,
                'cftc_cot_1w': backfill_cot,
                'fx_spot_1d': backfill_fx,
                'epa_rin_prices_1d': backfill_rin,
            }
            if args.table in table_map:
                table_map[args.table](conn)
            else:
                print(f"Unknown table: {args.table}")
                print(f"Available: {list(table_map.keys())}")
                sys.exit(1)
        else:
            parser.print_help()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
