"""
Database abstraction layer for ZINC-FUSION-V15.

Prisma Postgres is the ONLY production database.
All training, inference, and operations use Prisma Postgres.
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

    Returns 'postgres' - Prisma Postgres is the only supported database.
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
        return value.decode("utf-8", errors="replace")
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

    def execute(
        self, query: str, params: Optional[List[Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dicts."""
        return self._execute_postgres(query, params)

    def _execute_postgres(
        self, query: str, params: Optional[List[Any]] = None
    ) -> List[Dict[str, Any]]:
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
# NOTE: TABLE_MAP is used by translate_query(), which performs literal string replacement.
# Targets MUST stay schema-qualified to avoid relying on Postgres search_path.
TABLE_MAP = {
    # Raw layer (canonical tables) - fully quoted to preserve schema
    "raw.market_futures_1d": '"raw"."market_futures_1d"',
    "raw.market_futures_1h": '"raw"."market_futures_1h"',  # FIXED: never map 1h -> 1d
    "raw.fred_observations_1d": '"raw"."fred_observations_1d"',
    "raw.fred_series_metadata": '"raw"."fred_series_metadata"',
    "raw.fx_spot_1d": '"raw"."fx_spot_1d"',
    # Weather: preserve legacy alias
    "raw.weather_observations_1d": '"raw"."weather_noaa_1d"',  # legacy alias
    "raw.weather_noaa_1d": '"raw"."weather_noaa_1d"',  # canonical
    "raw.epa_rin_prices_1d": '"raw"."epa_rin_prices_1d"',
    "raw.cftc_cot_1w": '"raw"."cftc_cot_1w"',
    "raw.news_articles_1d": '"raw"."news_articles_1d"',
    "raw.usda_export_sales_1w": '"raw"."usda_export_sales_1w"',
    "raw.usda_wasde_1m": '"raw"."usda_wasde_1m"',
    "raw.options_futures_1d": '"raw"."options_futures_1d"',
    # REMOVED: raw.news_articles_event (table does not exist)
    # REMOVED: raw.fred_economic_wide_1d (deprecated; migrate call sites first)
    # Training / Model layer
    "training.oof_core_zl_1d": '"model"."oof_predictions"',
    "training.oof_specialist_combined_1d": '"model"."oof_predictions"',
    "training.core_matrix_full_1d": '"training"."core_features"',
    "training.cv_folds": '"model"."cv_folds"',
    "training.specialist_features": '"training"."specialist_features"',
    "training.meta_ensemble": '"model"."meta_ensemble"',
    # Analytics layer
    "features.driver_scores_1d": '"analytics"."driver_scores"',
    "specialist.drivers": '"analytics"."specialist_drivers"',
}


def translate_table(table_ref: str, backend: str = "postgres") -> str:
    """
    Translate table reference to Postgres schema-qualified name.

    Args:
        table_ref: Table reference (e.g., 'raw.market_futures_1d')
        backend: Always 'postgres' (parameter kept for backward compatibility)

    Returns:
        Schema-qualified Postgres table name (e.g., '"raw"."market_futures_1d"')
    """
    if table_ref in TABLE_MAP:
        return TABLE_MAP[table_ref]
    # Fallback: convert schema.table to "schema"."table"
    if "." in table_ref:
        schema, table = table_ref.split(".", 1)
        return f'"{schema}"."{table}"'
    return f'"{table_ref}"'


def translate_query(query: str, backend: str = "postgres") -> str:
    """
    Translate a query with table references to Postgres format.

    Args:
        query: SQL query with table references
        backend: Always 'postgres' (parameter kept for backward compatibility)

    Returns:
        Query with Postgres table names
    """
    result = query

    # Replace table references
    for duck_table, pg_table in TABLE_MAP.items():
        result = result.replace(duck_table, pg_table)

    # Replace syntax variations
    result = result.replace("::BIGINT", "::bigint")

    # Column name translations for Postgres schema differences
    if "fx_spot_1d" in result:
        result = result.replace("COUNT(DISTINCT symbol)", "COUNT(DISTINCT pair)")
        result = result.replace("symbol,", "pair,")
        result = result.replace("WHERE symbol", "WHERE pair")

    return result


class QueryBuilder:
    """Helper for building queries (always targets Postgres)."""

    def __init__(self):
        self.backend = "postgres"

    def table(self, table_ref: str) -> str:
        """Get the correct Postgres table name."""
        return translate_table(table_ref, self.backend)

    def query(self, sql: str) -> str:
        """Translate a query to Postgres format."""
        return translate_query(sql, self.backend)


def get_query_builder() -> QueryBuilder:
    """Get a query builder."""
    return QueryBuilder()
