"""
Database abstraction layer for ZINC-FUSION-V15.

AUTHORITATIVE: Prisma Postgres is the ONLY production database.
DuckDB (data/fusion.db) is ARCHIVE ONLY - do not use for training or operations.

NON-NEGOTIABLE: Postgres is the source of truth. Period.
"""

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False


def _get_postgres_url() -> Optional[str]:
    """Get Postgres connection URL from environment or .env file."""
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if url:
        return url

    # Try loading from .env file
    from pathlib import Path
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def get_backend() -> str:
    """
    Determine which database backend to use.

    ALWAYS returns 'postgres' - DuckDB is deprecated for all operations.
    """
    if not _get_postgres_url():
        raise RuntimeError(
            "DATABASE_URL not set. Prisma Postgres is required. "
            "Set DATABASE_URL in environment or .env file."
        )
    if not HAS_POSTGRES:
        raise RuntimeError("psycopg2 not installed. Run: pip install psycopg2-binary")
    return "postgres"


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
    """Prisma Postgres connection wrapper."""

    def __init__(self):
        self.backend = "postgres"
        self._conn = None

    def connect(self):
        """Establish connection to Prisma Postgres."""
        url = _get_postgres_url()
        if not url:
            raise RuntimeError("DATABASE_URL not set")
        self._conn = psycopg2.connect(url)
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
        return self._execute_postgres(query, params)

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


def fetch_rows(query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    """
    Execute a query and return results.

    This is the main entry point for database queries.
    Automatically handles connection management.
    """
    with DatabaseConnection() as db:
        return db.execute(query, params)


def get_connection():
    """Get a raw psycopg2 connection to Prisma Postgres."""
    url = _get_postgres_url()
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(url)


# Legacy table name mappings (for backward compatibility with old code)
# These map DuckDB-style schema.table names to Postgres flat names
TABLE_MAP = {
    # Raw layer
    "raw.market_futures_1d": "raw_market_futures",
    "raw.market_futures_1h": "raw_market_futures",
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
    # Features
    "features.driver_scores_1d": "driver_scores",
    # Specialist
    "specialist.drivers": "specialist_drivers",
    # Meta
    "training.meta_ensemble": "meta_ensemble",
}


def translate_table(table_ref: str, backend: str = "postgres") -> str:
    """
    Translate legacy DuckDB table reference to Postgres table name.

    Args:
        table_ref: DuckDB-style table reference (e.g., 'raw.market_futures_1d')
        backend: Always 'postgres' (parameter kept for backward compatibility)

    Returns:
        Postgres table name (e.g., 'raw_market_futures')
    """
    return TABLE_MAP.get(table_ref, table_ref.split(".")[-1].replace("_1d", "").replace("_1h", "").replace("_1w", ""))


def translate_query(query: str, backend: str = "postgres") -> str:
    """
    Translate a query with legacy DuckDB table names to Postgres.

    Args:
        query: SQL query with potential DuckDB-style table references
        backend: Always 'postgres' (parameter kept for backward compatibility)

    Returns:
        Query with Postgres table names
    """
    result = query

    # Replace table references
    for duck_table, pg_table in TABLE_MAP.items():
        result = result.replace(duck_table, pg_table)

    # Replace DuckDB-specific syntax
    result = result.replace("::BIGINT", "::bigint")

    # Column name translations for Postgres schema differences
    if "raw_fx_spot" in result:
        result = result.replace("COUNT(DISTINCT symbol)", "COUNT(DISTINCT pair)")
        result = result.replace("symbol,", "pair,")
        result = result.replace("WHERE symbol", "WHERE pair")

    return result


class QueryBuilder:
    """Helper for building queries (always targets Postgres)."""

    def __init__(self):
        self.backend = "postgres"

    def table(self, table_ref: str) -> str:
        """Get the correct table name (translates legacy DuckDB names)."""
        return translate_table(table_ref, self.backend)

    def query(self, sql: str) -> str:
        """Translate a query (translates legacy DuckDB table names)."""
        return translate_query(sql, self.backend)


def get_query_builder() -> QueryBuilder:
    """Get a query builder."""
    return QueryBuilder()
