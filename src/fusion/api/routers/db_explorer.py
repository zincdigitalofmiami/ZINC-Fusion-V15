"""Database explorer API routes."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from fusion.api.db import fetch_rows, get_query_builder

from .common import _fetch_rows, _require_db_token, _validate_readonly_sql

router = APIRouter()


@router.get("/db")
def db_explorer() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Fusion Database Explorer (Read-only)</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; }
    code, pre, textarea { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; }
    .row { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
    textarea { width: 100%; height: 180px; }
    table { border-collapse: collapse; width: 100%; margin-top: 16px; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; font-size: 13px; }
    th { background: #f5f5f5; text-align: left; }
    .muted { color: #666; font-size: 13px; }
    .error { color: #b00020; white-space: pre-wrap; }
  </style>
</head>
<body>
  <h2>Fusion Database Explorer (Read-only)</h2>
  <p class="muted">This UI only allows <code>SELECT</code>/<code>WITH</code> queries and enforces a row limit.</p>

  <div class="row">
    <label>Token: <input id="token" type="password" size="40" placeholder="FUSION_API_TOKEN"/></label>
    <label>Limit: <input id="limit" type="number" min="1" max="5000" value="200"/></label>
    <button id="loadSchemas">Schemas</button>
    <button id="run">Run</button>
  </div>

  <p id="status" class="muted"></p>
  <p id="error" class="error"></p>

  <h3>SQL</h3>
  <textarea id="sql">SELECT * FROM information_schema.tables ORDER BY table_schema, table_name</textarea>

  <h3>Result</h3>
  <div id="result"></div>

  <script>
    const statusEl = document.getElementById('status');
    const errorEl = document.getElementById('error');
    const resultEl = document.getElementById('result');

    function setStatus(msg) { statusEl.textContent = msg; }
    function setError(msg) { errorEl.textContent = msg || ''; }
    function tokenHeaders() {
      const token = document.getElementById('token').value;
      return { 'Content-Type': 'application/json', 'X-API-Token': token };
    }
    function renderTable(columns, rows) {
      if (!rows || rows.length === 0) { resultEl.innerHTML = '<p class="muted">No rows.</p>'; return; }
      const header = '<tr>' + columns.map(c => `<th>${c}</th>`).join('') + '</tr>';
      const body = rows.map(r => '<tr>' + columns.map(c => `<td>${r[c] ?? ''}</td>`).join('') + '</tr>').join('');
      resultEl.innerHTML = `<table><thead>${header}</thead><tbody>${body}</tbody></table>`;
    }
    async function runQuery(sql) {
      setError('');
      setStatus('Running query...');
      resultEl.innerHTML = '';
      const limit = Number(document.getElementById('limit').value || 200);
      const res = await fetch('/api/db/query', { method: 'POST', headers: tokenHeaders(), body: JSON.stringify({ sql, limit }) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { throw new Error(data.detail || `HTTP ${res.status}`); }
      setStatus(`OK: ${data.row_count} rows (limit=${data.limit}) in ${data.elapsed_ms}ms`);
      renderTable(data.columns, data.rows);
    }

    document.getElementById('run').addEventListener('click', async () => {
      try { await runQuery(document.getElementById('sql').value); } catch (e) { setStatus(''); setError(String(e)); }
    });

    document.getElementById('loadSchemas').addEventListener('click', async () => {
      try {
        setError('');
        setStatus('Loading schemas...');
        const res = await fetch('/api/db/schemas', { headers: tokenHeaders() });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) { throw new Error(data.detail || `HTTP ${res.status}`); }
        document.getElementById('sql').value = 'SELECT table_schema, table_name FROM information_schema.tables\\nWHERE table_schema IN (' + data.schemas.map(s => `'${s}'`).join(', ') + ')\\nORDER BY table_schema, table_name';
        setStatus('Loaded schemas into SQL.');
      } catch (e) { setStatus(''); setError(String(e)); }
    });
  </script>
</body>
</html>
"""


@router.get("/api/db/info")
def db_info(_: None = Depends(_require_db_token)) -> dict[str, Any]:
    return {"backend": "postgres", "database": "Prisma Postgres"}


@router.get("/api/db/schemas")
def db_schemas(_: None = Depends(_require_db_token)) -> dict[str, Any]:
    # Return canonical schema list for Prisma Postgres
    return {
        "schemas": [
            "alt",
            "analytics",
            "econ",
            "features",
            "forecasts",
            "mkt",
            "model",
            "ops",
            "pos",
            "supply",
            "training",
            "vegas",
        ]
    }


@router.get("/api/db/tables")
def db_tables(
    schema: str | None = None,
    _: None = Depends(_require_db_token),
) -> dict[str, Any]:
    if schema:
        rows = _fetch_rows(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = ?
            ORDER BY table_name
            """,
            [schema],
        )
        return {"schema": schema, "tables": [row["table_name"] for row in rows]}

    rows = _fetch_rows(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        ORDER BY table_schema, table_name
        """
    )
    return {"tables": rows}


@router.get("/api/db/columns")
def db_columns(
    schema: str,
    table: str,
    _: None = Depends(_require_db_token),
) -> dict[str, Any]:
    rows = _fetch_rows(
        """
        SELECT column_name, data_type, is_nullable, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = ?
          AND table_name = ?
        ORDER BY ordinal_position
        """,
        [schema, table],
    )
    return {"schema": schema, "table": table, "columns": rows}


@router.post("/api/db/query")
def db_query(
    payload: dict[str, Any],
    _: None = Depends(_require_db_token),
) -> dict[str, Any]:
    sql = _validate_readonly_sql(str(payload.get("sql", "")))
    limit = int(payload.get("limit", 200))
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > 5000:
        raise HTTPException(status_code=400, detail="limit must be <= 5000")

    started = time.perf_counter()

    # Translate the query for Prisma Postgres
    qb = get_query_builder()
    translated_sql = qb.query(sql)

    # Execute query against Prisma Postgres
    limited_sql = f"SELECT * FROM ({translated_sql}) AS q LIMIT %s"
    rows = fetch_rows(limited_sql, [limit])
    columns = list(rows[0].keys()) if rows else []

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "limit": limit,
        "elapsed_ms": elapsed_ms,
    }
