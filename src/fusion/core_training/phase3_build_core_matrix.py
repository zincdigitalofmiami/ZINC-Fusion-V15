"""
Phase 3: Build Core Feature Matrix
===================================

Assembles training.matrix_1d from:
- features.elite_1d (27 elite indicators + OHLCV)
- features.options_1d (IV/Greeks from Phase 1)
- features.weather_1d (weather aggregates)
- econ.* tables (rates, inflation, labor, activity, vol_indices, commodities, fx, money)
- mkt.fx_1d (FX rates)

SCHEMA UPDATE 2026-01-17:
- FRED data migrated from raw.fred_observations_1d to domain-specific econ.* tables
- gold.* renamed to features.* (elite_1d, options_1d, weather_1d)
- training.core_matrix_curated_1d renamed to training.matrix_1d

Design Principles:
- Blanket inclusion WITH enforced curation (120-350 features)
- All features as OBSERVED covariates (not known)
- RAW features stored (NO global normalization - prevents leakage)
- Normalization happens in Phase 6 PER CV WINDOW (training data only)
- ONE immutable matrix per rebuild
- Target: ~213 features after curation

CRITICAL: This phase stores RAW features. Normalization is NOT done here.
Phase 6 fits scalers on training windows only to prevent future data leakage.
"""

from __future__ import annotations

import logging
import hashlib
from datetime import datetime
from typing import Optional, Tuple, List

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values

from .config import DATABASE_URL, TARGET_SYMBOL, HORIZONS, FeatureMatrixConfig as FMC

logger = logging.getLogger(__name__)


def load_elite_indicators(conn, symbol: str) -> pd.DataFrame:
    """Load features.elite_1d for target symbol."""
    logger.info("Loading elite indicators from features.elite_1d...")

    query = """
        SELECT *
        FROM features.elite_1d
        WHERE symbol = %s
        ORDER BY trade_date
    """
    df = pd.read_sql(query, conn, params=(symbol,))
    logger.info(f"   Loaded {len(df):,} rows, {len(df.columns)} columns")
    return df


def load_options_features(conn, symbol: str) -> pd.DataFrame:
    """Load features.options_1d (Phase 1 output)."""
    logger.info("Loading options features from features.options_1d...")

    try:
        query = """
            SELECT *
            FROM features.options_1d
            WHERE symbol = %s
            ORDER BY trade_date
        """
        df = pd.read_sql(query, conn, params=(symbol,))
        logger.info(f"   Loaded {len(df):,} rows, {len(df.columns)} columns")
        return df
    except Exception as e:
        logger.warning(f"   Options features not available: {e}")
        return pd.DataFrame()


def load_fred_macro(conn) -> pd.DataFrame:
    """Load FRED macro series from econ.* tables and pivot to wide format.

    NEW SCHEMA (2026-01-17):
    FRED data is now split across domain-specific tables:
    - econ.rates_1d (interest rates, yields, spreads)
    - econ.inflation_1d (CPI, PCE)
    - econ.labor_1d (payrolls, claims)
    - econ.activity_1d (GDP, industrial production, sentiment)
    - econ.vol_indices_1d (VIX, NFCI)
    - econ.commodities_1d (commodity prices)
    - mkt.fx_1d (FRED FX rates - consolidated, filtered by source='FRED')
    - econ.money_1d (money supply, Fed balance sheet)
    """
    logger.info("Loading FRED macro series from econ.* tables...")

    FMC_INSTANCE = FMC()
    fred_series = list(FMC_INSTANCE.FRED_MACRO_SERIES)
    placeholders = ",".join(["%s"] * len(fred_series))

    # UNION ALL from all econ tables
    # Each table has same structure: series_id, event_date, value
    query = f"""
        WITH all_econ AS (
            SELECT series_id, event_date, value FROM econ.rates_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.inflation_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.labor_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.activity_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.vol_indices_1d
            UNION ALL
            SELECT series_id, event_date, value FROM econ.commodities_1d
            UNION ALL
            -- FX consolidated to mkt.fx_1d - map pair back to series_id format
            SELECT
                CASE pair
                    WHEN 'EUR/USD' THEN 'DEXUSEU'
                    WHEN 'USD/JPY' THEN 'DEXJPUS'
                    WHEN 'BRL/USD' THEN 'DEXBZUS'
                    WHEN 'CNY/USD' THEN 'DEXCHUS'
                    WHEN 'MXN/USD' THEN 'DEXMXUS'
                    WHEN 'CAD/USD' THEN 'DEXCAUS'
                    WHEN 'KRW/USD' THEN 'DEXKOUS'
                    WHEN 'INR/USD' THEN 'DEXINUS'
                    WHEN 'TWD/USD' THEN 'DEXTAUS'
                    WHEN 'AUD/USD' THEN 'DEXUSAL'
                    WHEN 'DXY_BROAD' THEN 'DTWEXBGS'
                    WHEN 'DXY_AFE' THEN 'DTWEXAFEGS'
                    WHEN 'DXY_EME' THEN 'DTWEXEMEGS'
                    WHEN 'DXY_MAJOR' THEN 'DTWEXM'
                    ELSE pair
                END as series_id,
                event_date,
                rate as value
            FROM mkt.fx_1d
            WHERE source = 'FRED'
            UNION ALL
            SELECT series_id, event_date, value FROM econ.money_1d
        )
        SELECT DISTINCT ON (series_id, event_date)
            event_date::date as trade_date,
            series_id,
            value
        FROM all_econ
        WHERE series_id IN ({placeholders})
        ORDER BY series_id, event_date
    """

    df = pd.read_sql(query, conn, params=tuple(fred_series))

    # Pivot to wide format
    if len(df) > 0:
        df_wide = df.pivot(index="trade_date", columns="series_id", values="value")
        df_wide = df_wide.reset_index()
        # Prefix column names
        df_wide.columns = ["trade_date"] + [
            f"fred_{col.lower()}" for col in df_wide.columns[1:]
        ]
        logger.info(f"   Loaded {len(df_wide):,} rows, {len(df_wide.columns)-1} series")
        return df_wide

    logger.warning("   No FRED data loaded")
    return pd.DataFrame()


def load_fx_rates(conn) -> pd.DataFrame:
    """Load FX rates from mkt."""
    logger.info("Loading FX rates from mkt.fx_1d...")

    try:
        # mkt.fx_1d uses pair and rate columns
        # All 5 available pairs: BRL, CNY, EUR, GBP, JPY
        query = """
            SELECT 
                event_date as trade_date,
                pair,
                rate as fx_rate
            FROM mkt.fx_1d
            WHERE pair IN ('USDBRL', 'USDCNY', 'USDEUR', 'USDGBP', 'USDJPY')
            ORDER BY trade_date, pair
        """
        df = pd.read_sql(query, conn)

        # Pivot to wide format
        if len(df) > 0:
            df_wide = df.pivot(
                index="trade_date", columns="pair", values="fx_rate"
            )
            df_wide = df_wide.reset_index()
            df_wide.columns = ["trade_date"] + [
                f"fx_{col.lower()}" for col in df_wide.columns[1:]
            ]
            logger.info(
                f"   Loaded {len(df_wide):,} rows, {len(df_wide.columns)-1} pairs"
            )
            return df_wide

    except Exception as e:
        logger.warning(f"   FX rates not available: {e}")

    return pd.DataFrame()


def load_weather_aggregates(conn) -> pd.DataFrame:
    """Load weather data aggregated by region from features.weather_1d."""
    logger.info("Loading weather aggregates from features.weather_1d...")

    FMC_INSTANCE = FMC()

    try:
        # Load pre-computed weather features from features layer
        # features.weather_1d has regional aggregates (US, BR, AR) with:
        # - Temperature (avg, min, max), precipitation, humidity, wind
        # - Anomalies vs 30-day rolling mean
        # - Growing degree days (GDD)
        # - Rolling sums (7d, 14d precip)
        query = """
            SELECT *
            FROM features.weather_1d
            ORDER BY trade_date
        """

        df = pd.read_sql(query, conn)

        if len(df) > 0:
            # Drop id and created_at columns
            df = df.drop(columns=["id", "created_at"], errors="ignore")
            logger.info(
                f"   Loaded {len(df):,} rows, {len(df.columns)-1} weather features"
            )
            return df

    except Exception as e:
        logger.warning(f"   Weather data not available: {e}")

    return pd.DataFrame()


def create_target_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Create forward returns as training targets (for supervised OOF)."""
    logger.info("Creating target columns...")

    for horizon in HORIZONS:
        target_col = f"target_ret_{horizon}d"
        df[target_col] = df["close"].pct_change(horizon).shift(-horizon)
        logger.info(f"   Created {target_col}")

    return df


def zscore_normalize(df: pd.DataFrame, exclude_cols: List[str]) -> pd.DataFrame:
    """
    DEPRECATED - DO NOT USE

    This function was previously used to normalize the entire dataset globally.
    This causes FUTURE DATA LEAKAGE because mean/std are computed on all data
    including future rows that wouldn't be available at training time.

    Normalization now happens in Phase 6, PER CV WINDOW, fitting only on
    training data before cutoff_date.

    This function is retained only for reference. It should NEVER be called.
    """
    raise RuntimeError(
        "zscore_normalize() is DEPRECATED. "
        "Global normalization causes future data leakage. "
        "Normalization must happen in Phase 6 per CV window."
    )


def drop_low_coverage_cols(df: pd.DataFrame, min_coverage: float = 0.7) -> pd.DataFrame:
    """Drop columns with too many nulls."""
    logger.info(f"Dropping columns with <{min_coverage*100:.0f}% coverage...")

    before_cols = len(df.columns)
    coverage = df.notna().mean()
    keep_cols = coverage[coverage >= min_coverage].index.tolist()
    df = df[keep_cols]
    dropped = before_cols - len(df.columns)

    logger.info(f"   Dropped {dropped} columns, kept {len(df.columns)}")
    return df


def enforce_feature_guardrails(df: pd.DataFrame) -> Tuple[pd.DataFrame, bool]:
    """
    Enforce 120-350 feature guardrail.

    Returns:
        (df, passed): DataFrame and whether guardrail passed
    """
    FMC_INSTANCE = FMC()

    exclude_cols = {"trade_date", "symbol", "item_id", "timestamp"} | {
        f"target_ret_{h}d" for h in HORIZONS
    }

    feature_cols = [c for c in df.columns if c not in exclude_cols]
    feature_count = len(feature_cols)

    logger.info(f"Feature count: {feature_count}")
    logger.info(f"   Min allowed: {FMC_INSTANCE.MIN_FEATURES}")
    logger.info(f"   Max allowed: {FMC_INSTANCE.MAX_FEATURES}")
    logger.info(f"   Target: {FMC_INSTANCE.TARGET_FEATURES}")

    passed = FMC_INSTANCE.MIN_FEATURES <= feature_count <= FMC_INSTANCE.MAX_FEATURES

    if passed:
        logger.info(f"✅ Feature count {feature_count} within guardrails")
    else:
        logger.error(
            f"❌ Feature count {feature_count} OUTSIDE guardrails [{FMC_INSTANCE.MIN_FEATURES}, {FMC_INSTANCE.MAX_FEATURES}]"
        )
        logger.error("   HARD FAIL - Phase 5 will also catch this")

    return df, passed


def write_matrix(conn, df: pd.DataFrame, matrix_version: str) -> int:
    """Write matrix to training.matrix_1d."""
    logger.info("Writing to training.matrix_1d...")

    # Add metadata columns first (before table creation)
    df["matrix_version"] = matrix_version
    df["created_at"] = datetime.utcnow()

    # Always drop and recreate to ensure schema matches
    # This table is rebuilt from scratch each time (immutable rebuild pattern)
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS training.matrix_1d CASCADE")
        logger.info("   Dropped existing table (clean rebuild)")

    # Create table dynamically based on DataFrame columns
    logger.info("   Creating training.matrix_1d table...")
    create_table_from_df(conn, df, "training", "matrix_1d", matrix_version)

    # Insert rows
    cols = list(df.columns)
    insert_sql = f"""
        INSERT INTO training.matrix_1d ({','.join(cols)})
        VALUES %s
    """

    values = [tuple(row) for row in df.itertuples(index=False, name=None)]

    with conn.cursor() as cur:
        execute_values(cur, insert_sql, values, page_size=1000)

    conn.commit()
    logger.info(f"   Inserted {len(df):,} rows")

    return len(df)


def create_table_from_df(conn, df: pd.DataFrame, schema: str, table: str, version: str):
    """Create table dynamically from DataFrame structure."""

    dtype_map = {
        "int64": "BIGINT",
        "int32": "INTEGER",
        "float64": "DOUBLE PRECISION",
        "float32": "REAL",
        "bool": "BOOLEAN",
        "datetime64[ns]": "TIMESTAMP",
        "object": "TEXT",
    }

    col_defs = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        sql_type = dtype_map.get(dtype, "TEXT")

        if col == "trade_date":
            col_defs.append(f'"{col}" DATE NOT NULL')
        elif col == "symbol":
            col_defs.append(f'"{col}" VARCHAR(20) NOT NULL')
        else:
            col_defs.append(f'"{col}" {sql_type}')

    create_sql = f"""
        CREATE TABLE IF NOT EXISTS {schema}.{table} (
            {','.join(col_defs)},
            PRIMARY KEY (trade_date, symbol)
        )
    """

    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()

    logger.info(f"   Created table {schema}.{table}")


def compute_matrix_version(df: pd.DataFrame) -> str:
    """Compute hash of matrix for lineage tracking."""
    content = (
        f"{len(df)}_{len(df.columns)}_{df['trade_date'].min()}_{df['trade_date'].max()}"
    )
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def run(symbol: str = TARGET_SYMBOL) -> Tuple[bool, Optional[str], int]:
    """
    Execute Phase 3: Build Core Feature Matrix.

    Returns:
        (success: bool, matrix_version: Optional[str], feature_count: int)
    """
    logger.info("=" * 60)
    logger.info("PHASE 3: BUILD CORE FEATURE MATRIX")
    logger.info("=" * 60)
    logger.info(f"Symbol: {symbol}")
    logger.info(
        f"Target features: {FMC.TARGET_FEATURES} (guardrails: {FMC.MIN_FEATURES}-{FMC.MAX_FEATURES})"
    )
    logger.info("=" * 60)

    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("✅ Database connected")

        # Load all source tables
        df_elite = load_elite_indicators(conn, symbol)
        df_options = load_options_features(conn, symbol)
        df_fred = load_fred_macro(conn)
        df_fx = load_fx_rates(conn)
        df_weather = load_weather_aggregates(conn)

        # Start with elite indicators as base
        df = df_elite.copy()

        # Merge options features
        if len(df_options) > 0:
            logger.info("Merging options features...")
            df = df.merge(
                df_options,
                on=["trade_date", "symbol"],
                how="left",
                suffixes=("", "_opt"),
            )

        # Merge FRED macro
        if len(df_fred) > 0:
            logger.info("Merging FRED macro...")
            df = df.merge(df_fred, on="trade_date", how="left")

        # Merge FX rates
        if len(df_fx) > 0:
            logger.info("Merging FX rates...")
            df = df.merge(df_fx, on="trade_date", how="left")

        # Merge weather
        if len(df_weather) > 0:
            logger.info("Merging weather aggregates...")
            df = df.merge(df_weather, on="trade_date", how="left")

        logger.info(f"Combined matrix: {len(df):,} rows, {len(df.columns)} columns")

        # Create target columns (forward returns)
        df = create_target_columns(df)

        # Forward-fill macro/fx/weather data (they update less frequently)
        logger.info("Forward-filling slow-updating series...")
        macro_cols = [
            c
            for c in df.columns
            if c.startswith("fred_") or c.startswith("fx_") or c.startswith("wx_")
        ]
        df[macro_cols] = df[macro_cols].fillna(method="ffill")

        # Drop low-coverage columns
        exclude_from_drop = ["trade_date", "symbol"] + [
            f"target_ret_{h}d" for h in HORIZONS
        ]
        df = drop_low_coverage_cols(df, min_coverage=0.7)

        # NOTE: NO NORMALIZATION HERE
        # Normalization happens in Phase 6 per CV window to prevent leakage
        # Raw features are stored in the matrix
        logger.info("⚠️ Storing RAW features (no normalization)")
        logger.info("   Normalization will be done in Phase 6 per CV window")

        # Enforce guardrails
        df, guardrail_passed = enforce_feature_guardrails(df)

        # Compute version hash
        matrix_version = compute_matrix_version(df)

        # Count features (excluding metadata and targets)
        exclude_cols = {"trade_date", "symbol", "matrix_version", "created_at"} | {
            f"target_ret_{h}d" for h in HORIZONS
        }
        feature_count = len([c for c in df.columns if c not in exclude_cols])

        # Write to database
        rows_written = write_matrix(conn, df, matrix_version)

        conn.close()

        logger.info("=" * 60)
        logger.info("✅ PHASE 3 COMPLETE - Core matrix built")
        logger.info(f"   Rows: {rows_written:,}")
        logger.info(f"   Features: {feature_count}")
        logger.info(f"   Matrix version: {matrix_version}")
        logger.info(f"   Guardrails passed: {guardrail_passed}")
        logger.info("=" * 60)

        return True, matrix_version, feature_count

    except Exception as e:
        logger.error(f"❌ PHASE 3 FAILED: {e}", exc_info=True)
        return False, None, 0


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Phase 3: Build Core Matrix")
    parser.add_argument("--symbol", default=TARGET_SYMBOL)
    args = parser.parse_args()

    success, version, features = run(args.symbol)
    exit(0 if success else 1)
