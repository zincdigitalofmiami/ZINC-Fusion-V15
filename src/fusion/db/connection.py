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


def get_database_url() -> str:
    """
    Get Prisma Postgres connection URL from environment.

    Checks DATABASE_URL first, then POSTGRES_URL as fallback.

    Returns:
        Connection URL string

    Raises:
        ValueError: If neither DATABASE_URL nor POSTGRES_URL is set
    """
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not url:
        raise ValueError("DATABASE_URL not set. " "Set it in environment or .env file.")
    return url


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


def get_write_connection() -> "psycopg2.extensions.connection":
    """
    Get psycopg2 connection for bulk write operations.

    Use with execute_batch for high-performance inserts.
    Caller is responsible for closing the connection.

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
    return psycopg2.connect(get_database_url())


@contextmanager
def DatabaseConnections() -> (
    Generator[Tuple[Engine, "psycopg2.extensions.connection"], None, None]
):
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
