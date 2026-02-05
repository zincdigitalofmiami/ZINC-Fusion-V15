"""
Ray-safe connection pool for parallel tasks.

Uses psycopg2.pool with per-worker singleton pattern.
Each Ray worker process gets its own small pool (1-2 connections),
preventing connection exhaustion when running 20+ workers.

Usage in @ray.remote functions:
    from fusion.db.ray_pool import get_connection, release_connection

    @ray.remote
    def my_task(database_url):
        conn = get_connection(database_url)
        try:
            # ... do work ...
        finally:
            release_connection(conn)
"""
import os
import atexit
from psycopg2 import pool

# Worker-local pool (one per Ray worker process)
_worker_pool = None
_pool_dsn = None


def get_worker_pool(database_url: str, minconn: int = 1, maxconn: int = 2):
    """
    Get or create connection pool for this worker process.

    Args:
        database_url: Postgres connection string
        minconn: Minimum connections to keep open (default 1)
        maxconn: Maximum connections per worker (default 2)

    Returns:
        ThreadedConnectionPool instance
    """
    global _worker_pool, _pool_dsn

    if _worker_pool is None or _pool_dsn != database_url:
        # Close existing pool if DSN changed
        if _worker_pool is not None:
            try:
                _worker_pool.closeall()
            except Exception:
                pass

        _worker_pool = pool.ThreadedConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            dsn=database_url
        )
        _pool_dsn = database_url

        # Register cleanup on process exit
        atexit.register(close_worker_pool)

    return _worker_pool


def get_connection(database_url: str):
    """
    Get a connection from the worker's pool.

    Args:
        database_url: Postgres connection string

    Returns:
        psycopg2 connection object
    """
    return get_worker_pool(database_url).getconn()


def release_connection(conn):
    """
    Return connection to pool (does NOT close it).

    Args:
        conn: psycopg2 connection to return
    """
    global _worker_pool
    if _worker_pool and conn:
        try:
            # Rollback any uncommitted transaction before returning to pool
            conn.rollback()
            _worker_pool.putconn(conn)
        except Exception:
            # Connection is dead, remove it from pool
            try:
                _worker_pool.putconn(conn, close=True)
            except Exception:
                pass


def close_worker_pool():
    """Close all connections in worker pool (called at process exit)."""
    global _worker_pool, _pool_dsn
    if _worker_pool:
        try:
            _worker_pool.closeall()
        except Exception:
            pass
        _worker_pool = None
        _pool_dsn = None
