"""FastAPI server exposing read-only endpoints for Fusion."""

from __future__ import annotations

import os
import re
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import duckdb
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from fusion.config import FUSION_DB_PATH
from fusion.api.news_sentiment import analyze_articles, get_policy_sentiment

app = FastAPI(title="Fusion API", version="0.1.0")

cors_origins = [o.strip() for o in os.environ.get("FUSION_CORS_ORIGINS", "").split(",") if o.strip()]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

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


def _fetch_rows(query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    conn = duckdb.connect(FUSION_DB_PATH, read_only=True)
    try:
        cursor = conn.execute(query, params or [])
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
    finally:
        conn.close()

    return [
        {columns[idx]: _serialize_value(value) for idx, value in enumerate(row)}
        for row in rows
    ]


def _require_db_token(x_api_token: Optional[str] = Header(default=None)) -> None:
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
        raise HTTPException(status_code=400, detail="Only SELECT/WITH queries are allowed.")
    if _SQL_WRITE_VERBS.search(lowered):
        raise HTTPException(status_code=400, detail="Query contains a forbidden keyword.")
    return normalized


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dashboard/summary")
def dashboard_summary(symbol: str = "ZL") -> Dict[str, Any]:
    price_rows = _fetch_rows(
        """
        SELECT as_of_date, close
        FROM (
            SELECT as_of_date, close
            FROM raw.market_futures_1d
            WHERE symbol = ?
            ORDER BY as_of_date DESC
            LIMIT 2
        ) t
        ORDER BY as_of_date ASC
        """,
        [symbol],
    )
    latest = price_rows[-1] if price_rows else None
    previous = price_rows[-2] if len(price_rows) > 1 else None

    price = latest["close"] if latest else None
    prev_price = previous["close"] if previous else None
    abs_change = (price - prev_price) if (price is not None and prev_price is not None) else None
    pct_change = (abs_change / prev_price) if (abs_change is not None and prev_price) else None

    action_rows = _fetch_rows(
        """
        SELECT as_of_date, action, confidence, rationale
        FROM forecasts.procurement_actions_1d
        WHERE symbol = ?
        ORDER BY as_of_date DESC
        LIMIT 1
        """,
        [symbol],
    )

    return {
        "symbol": symbol,
        "as_of_date": latest["as_of_date"] if latest else None,
        "price": price,
        "previous_price": prev_price,
        "abs_change": abs_change,
        "pct_change": pct_change,
        "procurement_action": action_rows[0] if action_rows else None,
    }


def _table_exists(schema: str, table: str) -> bool:
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


def _first_existing_column(schema: str, table: str, candidates: list[str]) -> str | None:
    cols = _fetch_rows(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = ? AND table_name = ?
        """,
        [schema, table],
    )
    existing = {c["column_name"] for c in cols}
    for c in candidates:
        if c in existing:
            return c
    return None


def _log_tail(path: str, max_bytes: int = 8192) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes), os.SEEK_SET)
            data = f.read().decode("utf-8", errors="replace")
        lines = [ln.strip() for ln in data.splitlines() if ln.strip()]
        return lines[-1] if lines else ""
    except Exception:
        return ""


def _recent_files(glob_path: str, limit: int = 5) -> list[dict[str, Any]]:
    import glob

    out: list[dict[str, Any]] = []
    for path in glob.glob(glob_path):
        try:
            st = os.stat(path)
        except Exception:
            continue
        out.append(
            {
                "path": path,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
                "size_bytes": int(st.st_size),
                "tail": _log_tail(path),
            }
        )
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out[:limit]


@app.get("/api/overview/models")
def overview_models() -> Dict[str, Any]:
    """
    Read-only operational snapshot for the /overview dashboard.

    This endpoint is intentionally limited to safe summary queries and does not expose
    arbitrary SQL execution.
    """
    specialists = [
        "crush",
        "china",
        "fx",
        "fed",
        "tariff",
        "energy",
        "biofuel",
        "palm",
        "volatility",
        "substitutes",
    ]

    # Core OOF
    core = {"exists": False, "by_horizon": []}
    if _table_exists("training", "oof_core_zl_1d"):
        core["exists"] = True
        horizon_col = _first_existing_column(
            "training", "oof_core_zl_1d", ["horizon_steps", "horizon_days"]
        )
        if horizon_col:
            core["by_horizon"] = _fetch_rows(
                f"""
                SELECT {horizon_col} as horizon, COUNT(*)::BIGINT as rows,
                       MIN(as_of_date) as start_date, MAX(as_of_date) as end_date
                FROM training.oof_core_zl_1d
                GROUP BY 1
                ORDER BY 1
                """
            )
        else:
            core["by_horizon"] = _fetch_rows(
                """
                SELECT NULL as horizon, COUNT(*)::BIGINT as rows,
                       MIN(as_of_date) as start_date, MAX(as_of_date) as end_date
                FROM training.oof_core_zl_1d
                """
            )

    # Specialist OOF evidence tables
    specialist_rows = []
    for s in specialists:
        table = f"oof_specialist_{s}_1d"
        if _table_exists("training", table):
            row = _fetch_rows(
                f"""
                SELECT '{s}' as specialist, COUNT(*)::BIGINT as rows,
                       MIN(as_of_date) as start_date, MAX(as_of_date) as end_date
                FROM training.{table}
                """
            )[0]
        else:
            row = {"specialist": s, "rows": 0, "start_date": None, "end_date": None}
        specialist_rows.append(row)

    combined = {"exists": False, "rows": 0, "start_date": None, "end_date": None}
    if _table_exists("training", "oof_specialist_combined_1d"):
        combined["exists"] = True
        combined.update(
            _fetch_rows(
                """
                SELECT COUNT(*)::BIGINT as rows,
                       MIN(as_of_date) as start_date, MAX(as_of_date) as end_date
                FROM training.oof_specialist_combined_1d
                """
            )[0]
        )

    market_1h = {"rows": 0, "start_date": None, "end_date": None, "symbols": 0}
    if _table_exists("raw", "market_futures_1h"):
        market_1h_date_col = _first_existing_column("raw", "market_futures_1h", ["as_of_date", "ts_event", "timestamp"])
        if market_1h_date_col:
            market_1h = _fetch_rows(
                f"""
                SELECT COUNT(*)::BIGINT as rows,
                       MIN({market_1h_date_col}) as start_date, MAX({market_1h_date_col}) as end_date,
                       COUNT(DISTINCT symbol)::BIGINT as symbols
                FROM raw.market_futures_1h
                """
            )[0]
        else:
            market_1h = _fetch_rows(
                """
                SELECT COUNT(*)::BIGINT as rows,
                       NULL as start_date, NULL as end_date,
                       COUNT(DISTINCT symbol)::BIGINT as symbols
                FROM raw.market_futures_1h
                """
            )[0]

    raw_data: dict[str, Any] = {
        "fred": _fetch_rows(
            """
            SELECT COUNT(*)::BIGINT as rows,
                   MIN(as_of_date) as start_date, MAX(as_of_date) as end_date,
                   COUNT(DISTINCT series_id)::BIGINT as series
            FROM raw.fred_observations_1d
            """
        )[0]
        if _table_exists("raw", "fred_observations_1d")
        else {"rows": 0, "start_date": None, "end_date": None, "series": 0},
        "fx_spot": _fetch_rows(
            """
            SELECT COUNT(*)::BIGINT as rows,
                   MIN(as_of_date) as start_date, MAX(as_of_date) as end_date,
                   COUNT(DISTINCT symbol)::BIGINT as symbols
            FROM raw.fx_spot_1d
            """
        )[0]
        if _table_exists("raw", "fx_spot_1d")
        else {"rows": 0, "start_date": None, "end_date": None, "symbols": 0},
        "market_futures_1d": _fetch_rows(
            """
            SELECT COUNT(*)::BIGINT as rows,
                   MIN(as_of_date) as start_date, MAX(as_of_date) as end_date,
                   COUNT(DISTINCT symbol)::BIGINT as symbols
            FROM raw.market_futures_1d
            """
        )[0]
        if _table_exists("raw", "market_futures_1d")
        else {"rows": 0, "start_date": None, "end_date": None, "symbols": 0},
        "market_futures_1h": market_1h,
        "epa_rin_prices_1d": _fetch_rows(
            """
            SELECT COUNT(*)::BIGINT as rows,
                   MIN(as_of_date) as start_date, MAX(as_of_date) as end_date,
                   COUNT(DISTINCT rin_type)::BIGINT as rin_types
            FROM raw.epa_rin_prices_1d
            """
        )[0]
        if _table_exists("raw", "epa_rin_prices_1d")
        else {"rows": 0, "start_date": None, "end_date": None, "rin_types": 0},
        "weather_observations_1d": _fetch_rows(
            """
            SELECT COUNT(*)::BIGINT as rows,
                   MIN(as_of_date) as start_date, MAX(as_of_date) as end_date,
                   COUNT(DISTINCT station_id)::BIGINT as stations,
                   COUNT(DISTINCT variable_id)::BIGINT as variables
            FROM raw.weather_observations_1d
            """
        )[0]
        if _table_exists("raw", "weather_observations_1d")
        else {"rows": 0, "start_date": None, "end_date": None, "stations": 0, "variables": 0},
    }

    archive_snapshot: list[dict[str, Any]] = []
    if _table_exists("archive", "fred_economic_1d"):
        tables = _fetch_rows(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='archive'
            ORDER BY table_name
            """
        )
        for t in tables:
            table = t["table_name"]
            # Best-effort: count + min/max using common date column names
            date_col = _first_existing_column("archive", table, ["as_of_date", "date", "report_date", "published_at"])
            if date_col:
                row = _fetch_rows(
                    f"""
                    SELECT 'archive.{table}' as table_name,
                           COUNT(*)::BIGINT as rows,
                           MIN({date_col}) as start_date,
                           MAX({date_col}) as end_date
                    FROM archive.{table}
                    """
                )[0]
            else:
                row = _fetch_rows(
                    f"""
                    SELECT 'archive.{table}' as table_name,
                           COUNT(*)::BIGINT as rows,
                           NULL as start_date,
                           NULL as end_date
                    FROM archive.{table}
                    """
                )[0]
            archive_snapshot.append(row)

    return {
        "models_contract": {
            "count": 11,
            "core_asset_key": "ag_train_core_model",
            "specialist_asset_keys": [f"ag_train_{s}_specialist" for s in specialists],
        },
        "raw_data": raw_data,
        "archive": {"tables": archive_snapshot},
        "core_oof": core,
        "specialist_oof": specialist_rows,
        "specialist_oof_combined": combined,
        "training_logs": {
            "core_oof": _recent_files("logs/core_oof*.log", limit=5),
        },
    }


@app.get("/api/market/zl")
def market_zl(
    symbol: str = "ZL",
    limit: int = Query(2000, ge=1, le=10000),
) -> Dict[str, Any]:
    rows = _fetch_rows(
        """
        SELECT as_of_date, close
        FROM (
            SELECT as_of_date, close
            FROM raw.market_futures_1d
            WHERE symbol = ?
            ORDER BY as_of_date DESC
            LIMIT ?
        ) t
        ORDER BY as_of_date ASC
        """,
        [symbol, limit],
    )

    series = [
        {"time": row["as_of_date"], "value": row["close"]}
        for row in rows
        if row.get("close") is not None
    ]

    return {"symbol": symbol, "series": series}


@app.get("/api/forecast/quantiles")
def forecast_quantiles(
    symbol: str = "ZL",
    horizon_days: Optional[List[int]] = Query(None),
) -> Dict[str, Any]:
    rows = _fetch_rows(
        """
        SELECT as_of_date, horizon_days, p10, p50, p90
        FROM forecasts.forecast_quantiles_1d
        WHERE symbol = ?
        ORDER BY as_of_date ASC
        """,
        [symbol],
    )

    if horizon_days:
        rows = [row for row in rows if row["horizon_days"] in horizon_days]

    return {"symbol": symbol, "quantiles": rows}


@app.get("/api/forecast/bands")
def forecast_bands(
    symbol: str = "ZL",
    horizon_days: Optional[List[int]] = Query(None),
) -> Dict[str, Any]:
    rows = _fetch_rows(
        """
        SELECT as_of_date, horizon_days, p10, p50, p90
        FROM forecasts.probability_bands_1d
        WHERE symbol = ?
        ORDER BY as_of_date ASC
        """,
        [symbol],
    )

    if horizon_days:
        rows = [row for row in rows if row["horizon_days"] in horizon_days]

    return {"symbol": symbol, "bands": rows}


@app.get("/api/sentiment/news")
def sentiment_news(
    limit: int = Query(200, ge=1, le=2000),
) -> Dict[str, Any]:
    articles = _fetch_rows(
        """
        SELECT article_id, published_at, source, title, content
        FROM raw.news_articles
        ORDER BY published_at DESC
        LIMIT ?
        """,
        [limit],
    )

    mapped = [
        {
            "id": row.get("article_id"),
            "title": row.get("title"),
            "body": row.get("content"),
            "source": row.get("source"),
            "published_at": row.get("published_at"),
        }
        for row in articles
    ]

    return analyze_articles(mapped)


@app.get("/db")
def db_explorer() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Fusion DuckDB Explorer (Read-only)</title>
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
  <h2>Fusion DuckDB Explorer (Read-only)</h2>
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


@app.get("/api/db/info")
def db_info(_: None = Depends(_require_db_token)) -> Dict[str, Any]:
    return {
        "db_path": FUSION_DB_PATH,
        "duckdb_version": duckdb.__version__,
    }


@app.get("/api/db/schemas")
def db_schemas(_: None = Depends(_require_db_token)) -> Dict[str, Any]:
    rows = _fetch_rows(
        """
        SELECT schema_name
        FROM information_schema.schemata
        ORDER BY schema_name
        """
    )
    # DuckDB returns internal schemas too (and some versions can repeat "main").
    schemas = sorted({r["schema_name"] for r in rows})
    internal = {"information_schema", "pg_catalog", "main"}
    canonical = set(os.environ.get("FUSION_CANONICAL_SCHEMAS", "").split(",")) if os.environ.get("FUSION_CANONICAL_SCHEMAS") else None

    if canonical:
        filtered = [s for s in schemas if s in canonical]
    else:
        filtered = [s for s in schemas if s not in internal]

    return {"schemas": filtered}


@app.get("/api/db/tables")
def db_tables(
    schema: Optional[str] = None,
    _: None = Depends(_require_db_token),
) -> Dict[str, Any]:
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
        return {"schema": schema, "tables": [r["table_name"] for r in rows]}

    rows = _fetch_rows(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        ORDER BY table_schema, table_name
        """
    )
    return {"tables": rows}


@app.get("/api/db/columns")
def db_columns(
    schema: str,
    table: str,
    _: None = Depends(_require_db_token),
) -> Dict[str, Any]:
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


@app.post("/api/db/query")
def db_query(
    payload: Dict[str, Any],
    _: None = Depends(_require_db_token),
) -> Dict[str, Any]:
    sql = _validate_readonly_sql(str(payload.get("sql", "")))
    limit = int(payload.get("limit", 200))
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > 5000:
        raise HTTPException(status_code=400, detail="limit must be <= 5000")

    started = time.perf_counter()
    conn = duckdb.connect(FUSION_DB_PATH, read_only=True)
    try:
        cursor = conn.execute(f"SELECT * FROM ({sql}) AS q LIMIT ?", [limit])
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
    finally:
        conn.close()
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return {
        "columns": columns,
        "rows": [
            {columns[idx]: _serialize_value(value) for idx, value in enumerate(row)}
            for row in rows
        ],
        "row_count": len(rows),
        "limit": limit,
        "elapsed_ms": elapsed_ms,
    }


@app.get("/api/sentiment/series")
def sentiment_series(limit: int = Query(365, ge=1, le=5000)) -> Dict[str, Any]:
    rows = _fetch_rows(
        """
        SELECT
            CAST(published_at AS DATE) AS as_of_date,
            AVG(sentiment_score) AS sentiment_score,
            COUNT(*) AS article_count
        FROM raw.news_articles
        WHERE sentiment_score IS NOT NULL
        GROUP BY 1
        ORDER BY as_of_date DESC
        LIMIT ?
        """,
        [limit],
    )
    rows = list(reversed(rows))
    series = [
        {
            "time": row["as_of_date"],
            "value": row["sentiment_score"],
            "article_count": row["article_count"],
        }
        for row in rows
        if row.get("sentiment_score") is not None
    ]
    return {"series": series}


@app.get("/api/legislation/news")
def legislation_news(limit: int = Query(200, ge=1, le=2000)) -> Dict[str, Any]:
    analyzed = sentiment_news(limit=limit)
    keep = {"US Regulatory Filings", "Legislation Changes", "Biofuel Mandates", "Tariff Updates"}
    articles = []
    for article in analyzed.get("articles", []):
        buckets = set(article.get("alert_buckets") or [])
        if buckets & keep:
            articles.append(article)
    summary = analyzed.get("summary") or {}
    summary["filtered_alert_buckets"] = sorted(keep)
    summary["filtered_articles"] = len(articles)
    return {"articles": articles, "summary": summary}


@app.get("/api/strategy/posture")
def strategy_posture(symbol: str = "ZL") -> Dict[str, Any]:
    actions = _fetch_rows(
        """
        SELECT as_of_date, action, confidence, rationale
        FROM forecasts.procurement_actions_1d
        WHERE symbol = ?
        ORDER BY as_of_date DESC
        LIMIT 30
        """,
        [symbol],
    )
    latest_action = actions[0] if actions else None

    windows = _fetch_rows(
        """
        SELECT as_of_date, horizon_days, tail_proximity, probability_lift, confidence_adjusted_lift,
               regime_dampening, window_start_week, window_end_week
        FROM forecasts.value_timing_windows_1d
        WHERE symbol = ?
        ORDER BY as_of_date DESC, horizon_days ASC
        LIMIT 200
        """,
        [symbol],
    )

    return {
        "symbol": symbol,
        "latest_action": latest_action,
        "recent_actions": actions,
        "value_windows": windows,
    }


@app.get("/api/strategy/risk")
def strategy_risk(symbol: str = "ZL", horizon: Optional[str] = None) -> Dict[str, Any]:
    rows = _fetch_rows(
        """
        SELECT as_of_date, horizon, var_95, var_99, cvar_95, cvar_99
        FROM forecasts.risk_metrics
        WHERE symbol = ?
        ORDER BY as_of_date DESC
        LIMIT 1000
        """,
        [symbol],
    )
    if horizon:
        rows = [row for row in rows if row.get("horizon") == horizon]
    return {"symbol": symbol, "risk_metrics": rows}


@app.get("/api/vegas-intel/status")
def vegas_intel_status() -> Dict[str, Any]:
    return {
        "status": "not_implemented",
        "reason": "No vegas-intel tables are present in this DuckDB file.",
    }


@app.get("/api/sentiment/policy")
def sentiment_policy(limit: int = Query(90, ge=1, le=2000)) -> Dict[str, Any]:
    return {"rows": get_policy_sentiment(limit=limit)}


@app.get("/api/drivers/latest")
def drivers_latest(symbol: str = "ZL") -> Dict[str, Any]:
    rows = _fetch_rows(
        """
        WITH latest AS (
            SELECT MAX(as_of_date) AS as_of_date
            FROM features.driver_scores_1d
            WHERE symbol = ?
        )
        SELECT
            s.as_of_date,
            s.symbol,
            s.driver_id,
            d.description,
            s.score
        FROM features.driver_scores_1d s
        JOIN latest l ON s.as_of_date = l.as_of_date
        LEFT JOIN specialist.drivers d ON d.driver_id = s.driver_id
        WHERE s.symbol = ?
        ORDER BY s.driver_id
        """,
        [symbol, symbol],
    )
    as_of_date = rows[0]["as_of_date"] if rows else None
    return {"symbol": symbol, "as_of_date": as_of_date, "drivers": rows}


@app.get("/api/drivers/series")
def drivers_series(
    symbol: str = "ZL",
    driver_id: str = Query(..., min_length=1),
    limit: int = Query(2000, ge=1, le=10000),
) -> Dict[str, Any]:
    rows = _fetch_rows(
        """
        SELECT as_of_date, score
        FROM (
            SELECT as_of_date, score
            FROM features.driver_scores_1d
            WHERE symbol = ? AND driver_id = ?
            ORDER BY as_of_date DESC
            LIMIT ?
        ) t
        ORDER BY as_of_date ASC
        """,
        [symbol, driver_id, limit],
    )
    series = [
        {"time": row["as_of_date"], "value": row["score"]}
        for row in rows
        if row.get("score") is not None
    ]
    return {"symbol": symbol, "driver_id": driver_id, "series": series}
