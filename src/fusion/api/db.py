"""
Database abstraction layer for ZINC-FUSION-V15.

Supports both DuckDB (legacy) and Prisma Postgres (production).
The active backend is determined by environment variables.

NON-NEGOTIABLE: Postgres is the source of truth when available.
"""

import os
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

# Try to import both backends
try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False


def _get_postgres_url() -> Optional[str]:
    """Get Postgres connection URL from environment."""
    return os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")


def _get_duckdb_path() -> Optional[str]:
    """Get DuckDB path from environment or default."""
    from fusion.config import FUSION_DB_PATH
    return FUSION_DB_PATH if os.path.exists(FUSION_DB_PATH) else None


def get_backend() -> str:
    """
    Determine which database backend to use.

    Priority:
    1. FUSION_DB_BACKEND env var (explicit override)
    2. Postgres if DATABASE_URL is set
    3. DuckDB if fusion.db exists
    4. Error if neither available
    """
    explicit = os.getenv("FUSION_DB_BACKEND", "").lower()
    if explicit in ("postgres", "postgresql", "pg"):
        return "postgres"
    if explicit in ("duckdb", "duck"):
        return "duckdb"

    # Auto-detect
    if _get_postgres_url() and HAS_POSTGRES:
        return "postgres"
    if _get_duckdb_path() and HAS_DUCKDB:
        return "duckdb"

    raise RuntimeError("No database backend available. Set DATABASE_URL or ensure fusion.db exists.")


def _serialize_value(value: Any) -> Any:
    """Serialize values for JSON response."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return value


class DatabaseConnection:
    """Unified database connection wrapper."""

    def __init__(self):
        self.backend = get_backend()
        self._conn = None

    def connect(self):
        """Establish connection to the database."""
        if self.backend == "postgres":
            url = _get_postgres_url()
            self._conn = psycopg2.connect(url)
        else:
            path = _get_duckdb_path()
            self._conn = duckdb.connect(path, read_only=True)
        return self

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def execute(self, query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dicts."""
        if self.backend == "postgres":
            return self._execute_postgres(query, params)
        else:
            return self._execute_duckdb(query, params)

    def _execute_postgres(self, query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute query on Postgres."""
        # Convert ? placeholders to %s for psycopg2
        pg_query = query.replace("?", "%s")

        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(pg_query, params or [])
            if cur.description:
                rows = cur.fetchall()
                return [
                    {k: _serialize_value(v) for k, v in dict(row).items()}
                    for row in rows
                ]
            return []

    def _execute_duckdb(self, query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute query on DuckDB."""
        cursor = self._conn.execute(query, params or [])
        if cursor.description:
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            return [
                {columns[idx]: _serialize_value(value) for idx, value in enumerate(row)}
                for row in rows
            ]
        return []


def fetch_rows(query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    """
    Execute a query and return results.

    This is the main entry point for database queries.
    Automatically handles connection management and backend selection.
    """
    with DatabaseConnection() as db:
        return db.execute(query, params)


# Table name mappings: DuckDB schema.table -> Postgres table
# Postgres uses flat namespace, DuckDB uses schema.table
TABLE_MAP = {
    # Raw layer
    "raw.market_futures_1d": "raw_market_futures",
    "raw.market_futures_1h": "raw_market_futures",  # Same table, different granularity in DuckDB
    "raw.fred_observations_1d": "raw_fred_observations",
    "raw.fx_spot_1d": "raw_fx_spot",
    "raw.weather_observations_1d": "raw_weather_observations",
    "raw.epa_rin_prices_1d": "raw_epa_rin_prices",
    "raw.cftc_cot_1w": "raw_cftc_cot",
    "raw.news_articles": "raw_news_articles",
    "raw.news_articles_event": "raw_news_articles",
    # Training layer
    "training.oof_core_zl_1d": "oof_predictions",
    "training.core_matrix_full_1d": "core_features",
    "training.cv_folds": "cv_folds",
    "training.specialist_features": "specialist_features",
    "training.oof_specialist_combined_1d": "oof_predictions",
    # Individual specialist OOF tables map to unified oof_predictions
    "training.oof_specialist_crush_1d": "oof_predictions",
    "training.oof_specialist_china_1d": "oof_predictions",
    "training.oof_specialist_fx_1d": "oof_predictions",
    "training.oof_specialist_fed_1d": "oof_predictions",
    "training.oof_specialist_tariff_1d": "oof_predictions",
    "training.oof_specialist_energy_1d": "oof_predictions",
    "training.oof_specialist_biofuel_1d": "oof_predictions",
    "training.oof_specialist_palm_1d": "oof_predictions",
    "training.oof_specialist_volatility_1d": "oof_predictions",
    "training.oof_specialist_substitutes_1d": "oof_predictions",
    # Specialist feature tables map to unified specialist_features
    "training.specialist_crush_1d": "specialist_features",
    "training.specialist_china_1d": "specialist_features",
    "training.specialist_fx_1d": "specialist_features",
    "training.specialist_fed_1d": "specialist_features",
    "training.specialist_tariff_1d": "specialist_features",
    "training.specialist_energy_1d": "specialist_features",
    "training.specialist_biofuel_1d": "specialist_features",
    "training.specialist_palm_1d": "specialist_features",
    "training.specialist_volatility_1d": "specialist_features",
    "training.specialist_substitutes_1d": "specialist_features",
    # Forecast layer
    "forecasts.forecast_quantiles_1d": "forecast_quantiles",
    "forecasts.procurement_actions_1d": "procurement_actions",
    "forecasts.probability_bands_1d": "forecast_quantiles",
    "forecasts.risk_metrics": "risk_metrics",
    "forecasts.value_timing_windows_1d": "value_timing_windows",
    "forecasts.zl_autogluon_5d": "forecast_quantiles",
    "forecasts.zl_autogluon_21d": "forecast_quantiles",
    "forecasts.zl_autogluon_63d": "forecast_quantiles",
    "forecasts.zl_autogluon_126d": "forecast_quantiles",
    # Features
    "features.driver_scores_1d": "driver_scores",
    # Specialist
    "specialist.drivers": "specialist_drivers",
    # Meta
    "training.meta_ensemble": "meta_ensemble",
}


def translate_table(table_ref: str, backend: str) -> str:
    """
    Translate table reference for the target backend.

    DuckDB uses: schema.table_name
    Postgres uses: table_name (flat namespace)
    """
    if backend == "postgres":
        return TABLE_MAP.get(table_ref, table_ref.split(".")[-1])
    return table_ref


def translate_query(query: str, backend: str) -> str:
    """
    Translate a query for the target backend.

    Handles:
    - Table name translation
    - Type casting differences
    - Function differences
    - Column name differences
    """
    if backend == "duckdb":
        return query  # DuckDB queries are the source format

    # Postgres translations
    result = query

    # Replace table references
    for duck_table, pg_table in TABLE_MAP.items():
        result = result.replace(duck_table, pg_table)

    # Replace DuckDB-specific syntax
    result = result.replace("::BIGINT", "::bigint")

    # Column name translations for Postgres schema differences
    # raw_fx_spot uses 'pair' instead of 'symbol'
    if "raw_fx_spot" in result:
        result = result.replace("COUNT(DISTINCT symbol)", "COUNT(DISTINCT pair)")
        result = result.replace("symbol,", "pair,")
        result = result.replace("WHERE symbol", "WHERE pair")

    return result


class QueryBuilder:
    """Helper for building backend-agnostic queries."""

    def __init__(self):
        self.backend = get_backend()

    def table(self, table_ref: str) -> str:
        """Get the correct table name for this backend."""
        return translate_table(table_ref, self.backend)

    def query(self, sql: str) -> str:
        """Translate a query for this backend."""
        return translate_query(sql, self.backend)


# Convenience function for simple queries
def get_query_builder() -> QueryBuilder:
    """Get a query builder for the current backend."""
    return QueryBuilder()
