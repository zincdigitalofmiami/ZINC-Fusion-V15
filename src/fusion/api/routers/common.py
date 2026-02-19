"""Shared FastAPI router helpers for Fusion read-only endpoints."""

from __future__ import annotations

import glob
import os
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import Header, HTTPException

from fusion.api.db import fetch_rows, get_backend, get_query_builder

_SQL_WRITE_VERBS = re.compile(
    r"\b("
    r"alter|attach|call|copy|create|delete|detach|drop|export|import|insert|install|load|pragma|replace|set|update|vacuum"
    r")\b",
    re.IGNORECASE,
)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _fetch_rows(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """Fetch rows using the unified database abstraction layer."""
    qb = get_query_builder()
    translated_query = qb.query(query)
    return fetch_rows(translated_query, params)


def _require_db_token(x_api_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("FUSION_API_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=500,
            detail="FUSION_API_TOKEN is not set on the server; refusing to serve DB explorer endpoints.",
        )
    if not x_api_token or x_api_token.strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Token.")


def _validate_readonly_sql(sql: str) -> str:
    normalized = (sql or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="SQL is required.")

    lowered = normalized.lower()
    if ";" in lowered:
        raise HTTPException(status_code=400, detail="Semicolons are not allowed.")
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise HTTPException(
            status_code=400, detail="Only SELECT/WITH queries are allowed."
        )
    if _SQL_WRITE_VERBS.search(lowered):
        raise HTTPException(
            status_code=400, detail="Query contains a forbidden keyword."
        )
    return normalized


def _table_exists(schema: str, table: str) -> bool:
    """Check if a table exists in Postgres."""
    rows = _fetch_rows(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = ? AND table_name = ?
        LIMIT 1
        """,
        [schema, table],
    )
    return bool(rows)


def _first_existing_column(
    schema: str, table: str, candidates: list[str]
) -> str | None:
    """Find first existing column from candidates in Postgres."""
    backend = get_backend()
    if backend == "postgres":
        cols = _fetch_rows(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            """,
            [schema, table],
        )
    else:
        cols = _fetch_rows(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            """,
            [schema, table],
        )

    existing = {c["column_name"] for c in cols}
    for column in candidates:
        if column in existing:
            return column
    return None


def _to_datetime(value: Any) -> datetime:
    """Best-effort conversion of DB values to datetime for sorting."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt_value = datetime.fromisoformat(text)
            return dt_value.replace(tzinfo=None)
        except ValueError:
            return datetime.min
    return datetime.min


def _fetch_recent_news_rows(limit: int) -> list[dict[str, Any]]:
    """
    Fetch normalized recent news rows from canonical alt.* news tables.

    Legacy single news table names are intentionally not used here.
    """
    rows: list[dict[str, Any]] = []
    per_table_limit = max(limit, 200)

    if _table_exists("alt", "econ_news_event"):
        rows.extend(
            _fetch_rows(
                """
                SELECT
                    article_id,
                    COALESCE(published_at, event_date) AS published_at,
                    COALESCE(source, 'econ_news') AS source,
                    headline AS title,
                    content
                FROM alt.econ_news_event
                ORDER BY COALESCE(published_at, event_date) DESC
                LIMIT ?
                """,
                [per_table_limit],
            )
        )

    if _table_exists("alt", "policy_news_event"):
        rows.extend(
            _fetch_rows(
                """
                SELECT
                    article_id,
                    COALESCE(published_at, event_date) AS published_at,
                    COALESCE(source, 'policy_news') AS source,
                    headline AS title,
                    content
                FROM alt.policy_news_event
                ORDER BY COALESCE(published_at, event_date) DESC
                LIMIT ?
                """,
                [per_table_limit],
            )
        )

    if _table_exists("alt", "profarmer_news_event"):
        rows.extend(
            _fetch_rows(
                """
                SELECT
                    COALESCE(url, CAST(id AS TEXT)) AS article_id,
                    event_date AS published_at,
                    'profarmer_news' AS source,
                    headline AS title,
                    content
                FROM alt.profarmer_news_event
                ORDER BY event_date DESC
                LIMIT ?
                """,
                [per_table_limit],
            )
        )

    rows.sort(key=lambda row: _to_datetime(row.get("published_at")), reverse=True)
    return rows[:limit]


def _log_tail(path: str, max_bytes: int = 8192) -> str:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes), os.SEEK_SET)
            data = handle.read().decode("utf-8", errors="replace")
        lines = [line.strip() for line in data.splitlines() if line.strip()]
        return lines[-1] if lines else ""
    except Exception:
        return ""


def _recent_files(glob_path: str, limit: int = 5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in glob.glob(glob_path):
        try:
            stat = os.stat(path)
        except Exception:
            continue
        out.append(
            {
                "path": path,
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size_bytes": int(stat.st_size),
                "tail": _log_tail(path),
            }
        )

    out.sort(key=lambda item: item["mtime"], reverse=True)
    return out[:limit]
