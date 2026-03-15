"""
Database connection utilities for ZINC-FUSION-V15.

Architecture:
    - SQLAlchemy engine for pandas read operations (pd.read_sql)
    - psycopg2 connection for bulk writes (execute_batch)

This dual approach gives:
    - No pandas warnings on reads
    - Maximum performance on bulk inserts (execute_batch is 10-100x faster)

Usage:
    from fusion.db import get_read_engine, get_write_connection, DatabaseConnections

    # For reads only:
    engine = get_read_engine()
    df = pd.read_sql("SELECT * FROM mkt.futures_1d", engine)

    # For writes only:
    conn = get_write_connection()
    with conn.cursor() as cur:
        execute_batch(cur, "INSERT ...", data)
    conn.commit()
    conn.close()

    # For mixed read/write:
    with DatabaseConnections() as (engine, conn):
        df = pd.read_sql("SELECT ...", engine)
        with conn.cursor() as cur:
            execute_batch(cur, "INSERT ...", data)
        conn.commit()
"""

import atexit
import os
from contextlib import contextmanager
from typing import Generator, Tuple, Optional

from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_batch  # noqa: F401 - re-export
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# Load .env file from project root (works regardless of cwd)
# override=False ensures real env vars (CI/prod) take precedence over .env
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

# Module-level engine cache (disposed on exit)
_engine_cache: Optional[Engine] = None


def normalize_database_url(url: str) -> str:
    """
    Validate and normalize a direct Postgres connection URL.

    Rejects Prisma Accelerate proxy URLs (prisma+postgres://) because
    psycopg2 / SQLAlchemy direct DB operations require postgres://.

    Ensures gssencmode=disable is present — psycopg2-binary ships libpq 17
    which tries GSSAPI encryption before SSL, and the Prisma Postgres proxy
    drops the connection when it receives a GSSENCRequest it doesn't understand.

    Args:
        url: Candidate database URL

    Returns:
        Normalized connection URL string

    Raises:
        ValueError: If URL is missing or incompatible
    """
    if not url:
        raise ValueError(
            "Database URL not set. Configure DATABASE_URL."
        )
    if url.startswith("prisma+postgres://"):
        raise ValueError(
            "Direct DB URL required for psycopg2/SQLAlchemy. Set DATABASE_URL to postgres://..."
        )
    if not (url.startswith("postgres://") or url.startswith("postgresql://")):
        raise ValueError(
            "Unsupported database URL scheme. Expected postgres:// or postgresql://"
        )
    if "gssencmode" not in url:
        url += "&gssencmode=disable" if "?" in url else "?gssencmode=disable"
    return url


def get_database_url() -> str:
    """
    Get Prisma Postgres connection URL from environment.

    Priority:
      1) DATABASE_URL

    Returns:
        Normalized connection URL string

    Raises:
        ValueError: If no direct URL is configured or URL is incompatible
    """
    url = os.getenv("DATABASE_URL")
    return normalize_database_url(url)


def _normalize_url_for_sqlalchemy(url: str) -> str:
    """Convert postgres:// to postgresql:// for SQLAlchemy 2.0+."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def get_read_engine() -> Engine:
    """
    Get SQLAlchemy engine for pandas read operations.

    Uses connection pooling. Engine is cached at module level
    and disposed on process exit.

    Returns:
        SQLAlchemy Engine instance

    Usage:
        engine = get_read_engine()
        df = pd.read_sql("SELECT * FROM mkt.futures_1d", engine)
    """
    global _engine_cache

    if _engine_cache is None:
        url = _normalize_url_for_sqlalchemy(get_database_url())
        _engine_cache = create_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine_cache


def get_write_connection(
    database_url: str | None = None,
) -> "psycopg2.extensions.connection":
    """
    Get psycopg2 connection for bulk write operations.

    Use with execute_batch for high-performance inserts.
    Caller is responsible for closing the connection.

    Args:
        database_url: Optional explicit URL. If omitted, resolves using
            DATABASE_URL.

    Returns:
        psycopg2 connection object

    Usage:
        conn = get_write_connection()
        try:
            with conn.cursor() as cur:
                execute_batch(cur, "INSERT ...", data, page_size=1000)
            conn.commit()
        finally:
            conn.close()
    """
    return psycopg2.connect(
        normalize_database_url(database_url) if database_url else get_database_url()
    )


@contextmanager
def DatabaseConnections() -> Generator[
    Tuple[Engine, "psycopg2.extensions.connection"], None, None
]:
    """
    Context manager providing both read engine and write connection.

    Yields:
        Tuple of (SQLAlchemy Engine, psycopg2 connection)

    Usage:
        with DatabaseConnections() as (engine, conn):
            # Read with pandas (no warnings)
            df = pd.read_sql("SELECT ...", engine)

            # Write with execute_batch (fast)
            with conn.cursor() as cur:
                execute_batch(cur, "INSERT ...", data)
            conn.commit()
    """
    engine = get_read_engine()
    conn = get_write_connection()
    try:
        yield engine, conn
    finally:
        conn.close()


def _cleanup_engine():
    """Dispose SQLAlchemy engine on exit."""
    global _engine_cache
    if _engine_cache is not None:
        _engine_cache.dispose()
        _engine_cache = None


atexit.register(_cleanup_engine)
