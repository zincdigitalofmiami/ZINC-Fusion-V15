"""FastAPI server exposing read-only endpoints for Fusion."""

from __future__ import annotations

import os
import re
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from fusion.api.news_sentiment import analyze_articles, get_policy_sentiment
from fusion.api.db import fetch_rows, get_backend, get_query_builder

# Import domain-specific pressure calculators for Key Market Drivers
from fusion.analytics.pressures import (
    calculate_volatility_pressure,
    calculate_crush_pressure,
    calculate_china_tension,
    calculate_tariff_pressure,
)

app = FastAPI(title="Fusion API", version="0.1.0")

cors_origins = [
    o.strip() for o in os.environ.get("FUSION_CORS_ORIGINS", "").split(",") if o.strip()
]
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


# Use the unified database abstraction layer
def _fetch_rows(query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    """Fetch rows using the unified database abstraction layer."""
    qb = get_query_builder()
    translated_query = qb.query(query)
    return fetch_rows(translated_query, params)


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
        raise HTTPException(
            status_code=400, detail="Only SELECT/WITH queries are allowed."
        )
    if _SQL_WRITE_VERBS.search(lowered):
        raise HTTPException(
            status_code=400, detail="Query contains a forbidden keyword."
        )
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
            SELECT event_date AS as_of_date, close
            FROM mkt.futures_1d
            WHERE symbol = ?
            ORDER BY event_date DESC
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
    abs_change = (
        (price - prev_price) if (price is not None and prev_price is not None) else None
    )
    pct_change = (
        (abs_change / prev_price) if (abs_change is not None and prev_price) else None
    )

    action_rows = _fetch_rows(
        """
        SELECT as_of_date, action, confidence, rationale
        FROM analytics.procurement_actions
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
    for c in candidates:
        if c in existing:
            return c
    return None


def _to_datetime(value: Any) -> datetime:
    """Best-effort conversion of DB values to datetime for sorting."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
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

    if _table_exists("alt", "econ_news"):
        rows.extend(
            _fetch_rows(
                """
                SELECT
                    article_id,
                    COALESCE(published_at, event_date) AS published_at,
                    COALESCE(source, 'econ_news') AS source,
                    headline AS title,
                    content
                FROM alt.econ_news
                ORDER BY COALESCE(published_at, event_date) DESC
                LIMIT ?
                """,
                [per_table_limit],
            )
        )

    if _table_exists("alt", "policy_news"):
        rows.extend(
            _fetch_rows(
                """
                SELECT
                    article_id,
                    COALESCE(published_at, event_date) AS published_at,
                    COALESCE(source, 'policy_news') AS source,
                    headline AS title,
                    content
                FROM alt.policy_news
                ORDER BY COALESCE(published_at, event_date) DESC
                LIMIT ?
                """,
                [per_table_limit],
            )
        )

    if _table_exists("alt", "profarmer_news"):
        rows.extend(
            _fetch_rows(
                """
                SELECT
                    COALESCE(url, CAST(id AS TEXT)) AS article_id,
                    event_date AS published_at,
                    'profarmer_news' AS source,
                    headline AS title,
                    content
                FROM alt.profarmer_news
                ORDER BY event_date DESC
                LIMIT ?
                """,
                [per_table_limit],
            )
        )

    rows.sort(key=lambda r: _to_datetime(r.get("published_at")), reverse=True)
    return rows[:limit]


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
    backend = get_backend()
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

    # Core OOF - Postgres uses unified oof_predictions table
    core = {"exists": False, "by_horizon": []}
    if backend == "postgres":
        core["exists"] = True
        core["by_horizon"] = _fetch_rows(
            """
            SELECT horizon, COUNT(*)::bigint as rows,
                   MIN(as_of_date) as start_date, MAX(as_of_date) as end_date
            FROM oof_predictions
            WHERE source = 'core'
            GROUP BY horizon
            ORDER BY horizon
            """
        )
    elif _table_exists("training", "oof_core_1d"):
        core["exists"] = True
        horizon_col = _first_existing_column(
            "training", "oof_core_1d", ["horizon_steps", "horizon_days"]
        )
        if horizon_col:
            core["by_horizon"] = _fetch_rows(
                f"""
                SELECT {horizon_col} as horizon, COUNT(*)::BIGINT as rows,
                       MIN(as_of_date) as start_date, MAX(as_of_date) as end_date
                FROM training.oof_core_1d
                GROUP BY 1
                ORDER BY 1
                """
            )
        else:
            core["by_horizon"] = _fetch_rows(
                """
                SELECT NULL as horizon, COUNT(*)::BIGINT as rows,
                       MIN(as_of_date) as start_date, MAX(as_of_date) as end_date
                FROM training.oof_core_1d
                """
            )

    # Specialist OOF evidence tables - Postgres uses unified oof_predictions with source column
    specialist_rows = []
    if backend == "postgres":
        # Query unified table for all specialists at once
        specialist_data = _fetch_rows(
            """
            SELECT source as specialist, COUNT(*)::bigint as rows,
                   MIN(as_of_date) as start_date, MAX(as_of_date) as end_date
            FROM oof_predictions
            WHERE source != 'core'
            GROUP BY source
            """
        )
        specialist_map = {r["specialist"]: r for r in specialist_data}
        for s in specialists:
            if s in specialist_map:
                specialist_rows.append(specialist_map[s])
            else:
                specialist_rows.append(
                    {"specialist": s, "rows": 0, "start_date": None, "end_date": None}
                )
    else:
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
    if backend == "postgres":
        # In Postgres, "combined" is just the total of all specialists in oof_predictions
        combined_data = _fetch_rows(
            """
            SELECT COUNT(*)::bigint as rows,
                   MIN(as_of_date) as start_date, MAX(as_of_date) as end_date
            FROM oof_predictions
            WHERE source != 'core'
            """
        )
        if combined_data and combined_data[0]["rows"] > 0:
            combined["exists"] = True
            combined.update(combined_data[0])
    elif _table_exists("training", "specialist_signals_1d"):
        combined["exists"] = True
        combined.update(
            _fetch_rows(
                """
                SELECT COUNT(*)::BIGINT as rows,
                       MIN(as_of_date) as start_date, MAX(as_of_date) as end_date
                FROM training.specialist_signals_1d
                """
            )[0]
        )

    # Raw data statistics - handle Postgres table structure
    market_1h = {"rows": 0, "start_date": None, "end_date": None, "symbols": 0}
    if _table_exists("mkt", "futures_1h"):
        market_1h_date_col = _first_existing_column(
            "mkt", "futures_1h", ["event_time", "ts_event", "timestamp", "as_of_date"]
        )
        if market_1h_date_col:
            market_1h = _fetch_rows(
                f"""
                SELECT COUNT(*)::BIGINT as rows,
                       MIN({market_1h_date_col}) as start_date, MAX({market_1h_date_col}) as end_date,
                       COUNT(DISTINCT symbol)::BIGINT as symbols
                FROM mkt.futures_1h
                """
            )[0]
        else:
            market_1h = _fetch_rows(
                """
                SELECT COUNT(*)::BIGINT as rows,
                       NULL as start_date, NULL as end_date,
                       COUNT(DISTINCT symbol)::BIGINT as symbols
                FROM mkt.futures_1h
                """
            )[0]

    if backend == "postgres":
        raw_data: dict[str, Any] = {
            "fred": _fetch_rows(
                """
                WITH all_econ AS (
                    SELECT series_id, event_date FROM econ.rates_1d
                    UNION ALL
                    SELECT series_id, event_date FROM econ.inflation_1d
                    UNION ALL
                    SELECT series_id, event_date FROM econ.labor_1d
                    UNION ALL
                    SELECT series_id, event_date FROM econ.activity_1d
                    UNION ALL
                    SELECT series_id, event_date FROM econ.vol_indices_1d
                    UNION ALL
                    SELECT series_id, event_date FROM econ.commodities_1d
                    UNION ALL
                    -- FX consolidated to mkt.fx_1d, map pair to series_id
                    SELECT pair as series_id, event_date FROM mkt.fx_1d WHERE source = 'FRED'
                    UNION ALL
                    SELECT series_id, event_date FROM econ.money_1d
                )
                SELECT COUNT(*)::bigint as rows,
                       MIN(event_date) as start_date, MAX(event_date) as end_date,
                       COUNT(DISTINCT series_id)::bigint as series
                FROM all_econ
                """
            )[0],
            "fx_spot": _fetch_rows(
                """
                SELECT COUNT(*)::bigint as rows,
                       MIN(event_date) as start_date, MAX(event_date) as end_date,
                       COUNT(DISTINCT pair)::bigint as symbols
                FROM mkt.fx_1d
                """
            )[0],
            "market_futures_1d": _fetch_rows(
                """
                SELECT COUNT(*)::bigint as rows,
                       MIN(event_date) as start_date, MAX(event_date) as end_date,
                       COUNT(DISTINCT symbol)::bigint as symbols
                FROM mkt.futures_1d
                """
            )[0],
            "market_futures_1h": market_1h,
            "epa_rin_prices_1d": _fetch_rows(
                """
                SELECT COUNT(*)::bigint as rows,
                       MIN(event_date) as start_date, MAX(event_date) as end_date,
                       COUNT(DISTINCT rin_type)::bigint as rin_types
                FROM supply.epa_rin_1d
                """
            )[0],
            "weather_observations_1d": (
                _fetch_rows(
                    """
                SELECT COUNT(*)::bigint as rows,
                       MIN(event_date) as start_date, MAX(event_date) as end_date,
                       COUNT(DISTINCT station_id)::bigint as stations
                FROM alt.weather_1d
                """
                )[0]
                if _table_exists("alt", "weather_1d")
                else {"rows": 0, "start_date": None, "end_date": None, "stations": 0}
            ),
        }
    else:
        raw_data = {
            "fred": (
                _fetch_rows(
                    """
                WITH all_econ AS (
                    SELECT series_id, event_date FROM econ.rates_1d
                    UNION ALL
                    SELECT series_id, event_date FROM econ.inflation_1d
                    UNION ALL
                    SELECT series_id, event_date FROM econ.labor_1d
                    UNION ALL
                    SELECT series_id, event_date FROM econ.activity_1d
                    UNION ALL
                    SELECT series_id, event_date FROM econ.vol_indices_1d
                    UNION ALL
                    SELECT series_id, event_date FROM econ.commodities_1d
                    UNION ALL
                    -- FX consolidated to mkt.fx_1d, map pair to series_id
                    SELECT pair as series_id, event_date FROM mkt.fx_1d WHERE source = 'FRED'
                    UNION ALL
                    SELECT series_id, event_date FROM econ.money_1d
                )
                SELECT COUNT(*)::BIGINT as rows,
                       MIN(event_date) as start_date, MAX(event_date) as end_date,
                       COUNT(DISTINCT series_id)::BIGINT as series
                FROM all_econ
                """
                )[0]
                if _table_exists("econ", "rates_1d")
                else {"rows": 0, "start_date": None, "end_date": None, "series": 0}
            ),
            "fx_spot": (
                _fetch_rows(
                    """
                SELECT COUNT(*)::BIGINT as rows,
                       MIN(event_date) as start_date, MAX(event_date) as end_date,
                       COUNT(DISTINCT pair)::BIGINT as symbols
                FROM mkt.fx_1d
                """
                )[0]
                if _table_exists("mkt", "fx_1d")
                else {"rows": 0, "start_date": None, "end_date": None, "symbols": 0}
            ),
            "market_futures_1d": (
                _fetch_rows(
                    """
                SELECT COUNT(*)::BIGINT as rows,
                       MIN(event_date) as start_date, MAX(event_date) as end_date,
                       COUNT(DISTINCT symbol)::BIGINT as symbols
                FROM mkt.futures_1d
                """
                )[0]
                if _table_exists("mkt", "futures_1d")
                else {"rows": 0, "start_date": None, "end_date": None, "symbols": 0}
            ),
            "market_futures_1h": market_1h,
            "epa_rin_prices_1d": (
                _fetch_rows(
                    """
	                SELECT COUNT(*)::BIGINT as rows,
	                       MIN(event_date) as start_date, MAX(event_date) as end_date,
	                       COUNT(DISTINCT rin_type)::BIGINT as rin_types
	                FROM supply.epa_rin_1d
	                """
                )[0]
                if _table_exists("supply", "epa_rin_1d")
                else {"rows": 0, "start_date": None, "end_date": None, "rin_types": 0}
            ),
            "weather_observations_1d": (
                _fetch_rows(
                    """
	                SELECT COUNT(*)::BIGINT as rows,
	                       MIN(event_date) as start_date, MAX(event_date) as end_date,
	                       COUNT(DISTINCT station_id)::BIGINT as stations
	                FROM alt.weather_1d
	                """
                )[0]
                if _table_exists("alt", "weather_1d")
                else {"rows": 0, "start_date": None, "end_date": None, "stations": 0}
            ),
        }

    return {
        "models_contract": {
            "count": 11,
            "core_asset_key": "ag_train_core_model",
            "specialist_asset_keys": [f"ag_train_{s}_specialist" for s in specialists],
        },
        "raw_data": raw_data,
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
            SELECT event_date AS as_of_date, close
            FROM mkt.futures_1d
            WHERE symbol = ?
            ORDER BY event_date DESC
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
    backend = get_backend()
    if backend == "postgres":
        # Use forecasts.forecast_quantiles table
        rows = _fetch_rows(
            """
            SELECT as_of_date, horizon as horizon_days, p10, p50, p90
            FROM forecasts.forecast_quantiles
            WHERE symbol = ?
            ORDER BY as_of_date ASC
            """,
            [symbol],
        )
    else:
        rows = _fetch_rows(
            """
            SELECT as_of_date, horizon_days, p10, p50, p90
            FROM forecasts.forecast_quantiles
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
    if _table_exists("forecasts", "forecast_quantiles"):
        horizon_col = _first_existing_column(
            "forecasts", "forecast_quantiles", ["horizon", "horizon_days"]
        )
        date_col = _first_existing_column(
            "forecasts", "forecast_quantiles", ["forecast_date", "as_of_date"]
        )
        if not horizon_col or not date_col:
            rows = []
        else:
            rows = _fetch_rows(
                f"""
                SELECT {date_col} as as_of_date, {horizon_col} as horizon_days, p10, p50, p90
                FROM forecasts.forecast_quantiles
                WHERE symbol = ?
                ORDER BY {date_col} ASC
                """,
                [symbol],
            )
    else:
        # Long-form fallback if only probability_distributions is present.
        rows = _fetch_rows(
            """
            SELECT
                as_of_date,
                horizon as horizon_days,
                MAX(CASE WHEN percentile IN (10, 0.10) THEN value END) AS p10,
                MAX(CASE WHEN percentile IN (50, 0.50) THEN value END) AS p50,
                MAX(CASE WHEN percentile IN (90, 0.90) THEN value END) AS p90
            FROM forecasts.probability_distributions
            WHERE symbol = ?
            GROUP BY as_of_date, horizon
            ORDER BY as_of_date ASC, horizon
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
    articles = _fetch_recent_news_rows(limit)

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


@app.get("/api/db/info")
def db_info(_: None = Depends(_require_db_token)) -> Dict[str, Any]:
    return {"backend": "postgres", "database": "Prisma Postgres"}


@app.get("/api/db/schemas")
def db_schemas(_: None = Depends(_require_db_token)) -> Dict[str, Any]:
    # Return canonical schema list for Prisma Postgres
    return {"schemas": ["raw", "training", "forecasts", "features", "specialist"]}


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


@app.get("/api/sentiment/series")
def sentiment_series(limit: int = Query(365, ge=1, le=5000)) -> Dict[str, Any]:
    scan_limit = min(max(limit * 25, 500), 5000)
    articles = _fetch_recent_news_rows(scan_limit)
    analyzed = analyze_articles(
        [
            {
                "id": row.get("article_id"),
                "title": row.get("title"),
                "body": row.get("content"),
                "source": row.get("source"),
                "published_at": row.get("published_at"),
            }
            for row in articles
        ]
    ).get("articles", [])

    by_day: Dict[date, Dict[str, Any]] = {}
    for article in analyzed:
        published_at = article.get("published_at")
        ts = _to_datetime(published_at)
        day = ts.date() if ts != datetime.min else None
        score = article.get("impact_score")
        if day is None or score is None:
            continue
        if day not in by_day:
            by_day[day] = {"sum": 0.0, "count": 0}
        by_day[day]["sum"] += float(score)
        by_day[day]["count"] += 1

    rows = [
        {
            "as_of_date": as_of_date,
            "sentiment_score": agg["sum"] / agg["count"] if agg["count"] else None,
            "article_count": agg["count"],
        }
        for as_of_date, agg in by_day.items()
    ]
    rows.sort(key=lambda row: row["as_of_date"])
    rows = rows[-limit:]

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
    keep = {
        "US Regulatory Filings",
        "Legislation Changes",
        "Biofuel Mandates",
        "Tariff Updates",
    }
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
        FROM analytics.procurement_actions
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
        FROM analytics.value_timing_windows
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
        FROM analytics.risk_metrics
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
        "reason": "Vegas-intel tables not available.",
    }


@app.get("/api/sentiment/policy")
def sentiment_policy(limit: int = Query(90, ge=1, le=2000)) -> Dict[str, Any]:
    return {"rows": get_policy_sentiment(limit=limit)}


@app.get("/api/drivers/latest")
def drivers_latest(symbol: str = "ZL") -> Dict[str, Any]:
    backend = get_backend()
    if backend == "postgres":
        # Use analytics.driver_scores table (corrected schema)
        rows = _fetch_rows(
            """
            WITH latest AS (
                SELECT MAX(as_of_date) AS as_of_date
                FROM analytics.driver_scores
                WHERE symbol = ?
            )
            SELECT
                s.as_of_date,
                s.symbol,
                s.bucket as specialist,
                s.direction,
                s.score,
                s.weight
            FROM analytics.driver_scores s
            JOIN latest l ON s.as_of_date = l.as_of_date
            WHERE s.symbol = ?
            ORDER BY s.bucket
            """,
            [symbol, symbol],
        )
    else:
        rows = _fetch_rows(
            """
            WITH latest AS (
                SELECT MAX(as_of_date) AS as_of_date
                FROM analytics.driver_scores
                WHERE symbol = ?
            )
            SELECT
                s.as_of_date,
                s.symbol,
                s.bucket as specialist,
                s.direction,
                s.score,
                s.weight
            FROM analytics.driver_scores s
            JOIN latest l ON s.as_of_date = l.as_of_date
            WHERE s.symbol = ?
            ORDER BY s.bucket
            """,
            [symbol, symbol],
        )
    as_of_date = rows[0]["as_of_date"] if rows else None
    return {"symbol": symbol, "as_of_date": as_of_date, "signals": rows}


@app.get("/api/drivers/series")
def drivers_series(
    symbol: str = "ZL",
    driver_id: str = Query(..., min_length=1),
    limit: int = Query(2000, ge=1, le=10000),
) -> Dict[str, Any]:
    backend = get_backend()
    if backend == "postgres":
        # Use analytics.driver_scores (corrected schema)
        rows = _fetch_rows(
            """
            SELECT as_of_date, score
            FROM (
                SELECT as_of_date, score
                FROM analytics.driver_scores
                WHERE symbol = ? AND bucket = ?
                ORDER BY as_of_date DESC
                LIMIT ?
            ) t
            ORDER BY as_of_date ASC
            """,
            [symbol, driver_id, limit],
        )
    else:
        rows = _fetch_rows(
            """
            SELECT as_of_date, score
            FROM (
                SELECT as_of_date, score
                FROM analytics.driver_scores
                WHERE symbol = ? AND bucket = ?
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


# =============================================================================
# ZL Intraday 15m Endpoint (Dashboard Only)
# =============================================================================


@app.get("/api/zl/live")
def zl_live() -> Dict[str, Any]:
    """
    Get the latest ZL price for the header widget.
    Returns the most recent 15m bar with change from previous close.
    """
    rows = _fetch_rows(
        """
        SELECT
            timestamp,
            open,
            high,
            low,
            close,
            volume,
            previous_close,
            change,
            change_percent,
            day_high,
            day_low
        FROM analytics.zl_price_15m
        ORDER BY timestamp DESC
        LIMIT 1
        """
    )

    if not rows:
        # Fallback to daily data if no intraday available
        daily_rows = _fetch_rows(
            """
            SELECT event_date AS as_of_date, close
            FROM mkt.futures_1d
            WHERE symbol = 'ZL'
            ORDER BY event_date DESC
            LIMIT 2
            """
        )
        if daily_rows:
            latest = daily_rows[0]
            prev = daily_rows[1] if len(daily_rows) > 1 else None
            prev_close = prev["close"] if prev else None
            change = (latest["close"] - prev_close) if prev_close else None
            change_pct = (
                (change / prev_close * 100) if (change and prev_close) else None
            )
            return {
                "symbol": "ZL",
                "timestamp": latest["as_of_date"],
                "price": latest["close"],
                "previous_close": prev_close,
                "change": change,
                "change_percent": change_pct,
                "source": "daily",
            }
        return {"symbol": "ZL", "error": "No price data available"}

    row = rows[0]
    return {
        "symbol": "ZL",
        "timestamp": row["timestamp"],
        "price": row["close"],
        "open": row["open"],
        "high": row["high"],
        "low": row["low"],
        "volume": row["volume"],
        "previous_close": row["previous_close"],
        "change": row["change"],
        "change_percent": row["change_percent"],
        "day_high": row["day_high"],
        "day_low": row["day_low"],
        "source": "intraday",
    }


@app.get("/api/zl/intraday")
def zl_intraday(
    hours: int = Query(
        24, ge=1, le=168, description="Hours of data to return (max 168 = 7 days)"
    ),
) -> Dict[str, Any]:
    """
    Get ZL 15-minute bars for charting.
    Returns data for the specified number of hours.
    """
    rows = _fetch_rows(
        f"""
        SELECT
            timestamp,
            open,
            high,
            low,
            close,
            volume
        FROM analytics.zl_price_15m
        WHERE timestamp > NOW() - INTERVAL '{hours} hours'
        ORDER BY timestamp ASC
        """
    )

    # Format for charting libraries (TradingView lightweight-charts format)
    bars = []
    for row in rows:
        ts = row["timestamp"]
        # Handle string or datetime
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        bars.append(
            {
                "time": int(ts.timestamp()),  # Unix timestamp
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
        )

    return {
        "symbol": "ZL",
        "interval": "15m",
        "bars": bars,
        "count": len(bars),
    }


@app.get("/api/zl/intraday/ohlc")
def zl_intraday_ohlc(
    days: int = Query(7, ge=1, le=60, description="Days of data to return"),
) -> Dict[str, Any]:
    """
    Get ZL 15-minute bars with full OHLC data.
    Returns ISO timestamps for broader compatibility.
    """
    rows = _fetch_rows(
        f"""
        SELECT
            timestamp,
            open,
            high,
            low,
            close,
            volume,
            day_high,
            day_low
        FROM analytics.zl_price_15m
        WHERE timestamp > NOW() - INTERVAL '{days} days'
        ORDER BY timestamp ASC
        """
    )

    bars = []
    for row in rows:
        ts = row["timestamp"]
        # Handle string or datetime
        if isinstance(ts, str):
            ts_str = ts
        else:
            ts_str = ts.isoformat()
        bars.append(
            {
                "timestamp": ts_str,
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
                "day_high": row["day_high"],
                "day_low": row["day_low"],
            }
        )

    return {
        "symbol": "ZL",
        "interval": "15m",
        "bars": bars,
        "count": len(bars),
    }


# =============================================================================
# Intel Drops / Pulse Engine Endpoints
# =============================================================================


@app.get("/api/pulse/domains")
def pulse_domains() -> Dict[str, Any]:
    """
    Get list of supported specialist domains and horizons.
    """
    return {
        "domains": [
            "CRUSH",
            "CHINA",
            "FX",
            "FED",
            "TARIFF",
            "ENERGY",
            "BIOFUEL",
            "PALM",
            "VOLATILITY",
            "SUBSTITUTES",
            "TRUMP_EFFECT",
        ],
        "horizons": ["1W", "1M", "3M", "6M"],
        "domain_descriptions": {
            "CRUSH": "Soybean Complex Fundamentals",
            "CHINA": "Trade Flows",
            "FX": "Currency Competitiveness",
            "FED": "Monetary Policy",
            "TARIFF": "Trade Policy",
            "ENERGY": "Crude Oil & Energy Complex",
            "BIOFUEL": "Biodiesel & Renewable Fuel",
            "PALM": "Palm Oil Substitution",
            "VOLATILITY": "Financial Stress",
            "SUBSTITUTES": "Vegetable Oil Competition",
            "TRUMP_EFFECT": "Political & Policy Volatility",
        },
    }


@app.get("/api/pulse/latest")
def pulse_latest(
    domain: Optional[str] = None,
    horizon: Optional[str] = None,
    limit: int = Query(10, ge=1, le=100),
) -> Dict[str, Any]:
    """
    Get the most recent Intel Drops.

    Args:
        domain: Filter by specialist domain (e.g., CRUSH, CHINA)
        horizon: Filter by time horizon (1W, 1M, 3M, 6M)
        limit: Maximum number of results (default 10)
    """
    params = []
    where_clauses = []

    if domain:
        where_clauses.append("domain = ?")
        params.append(domain.upper())

    if horizon:
        where_clauses.append("horizon = ?")
        params.append(horizon.upper())

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    rows = _fetch_rows(
        f"""
        SELECT
            id, as_of_ts, domain, horizon, direction, pressure_cents, edge,
            driver_weights, top_drivers, regime_tags, quality_flags, data_gaps,
            source_model, created_at
        FROM features.intel_drops
        WHERE {where_sql}
        ORDER BY as_of_ts DESC, domain, horizon
        LIMIT ?
        """,
        params + [limit],
    )

    return {
        "drops": rows,
        "count": len(rows),
        "filters": {"domain": domain, "horizon": horizon},
    }


@app.get("/api/pulse/drop/{drop_id}")
def pulse_drop_by_id(drop_id: int) -> Dict[str, Any]:
    """
    Get a single Intel Drop by ID, including full narrative.
    """
    rows = _fetch_rows(
        """
        SELECT
            id, as_of_ts, domain, horizon, direction, pressure_cents, edge,
            driver_weights, top_drivers, regime_tags, quality_flags, data_gaps,
            receipts, narrative, quant_payload, source_model, created_at
        FROM features.intel_drops
        WHERE id = ?
        """,
        [drop_id],
    )

    if not rows:
        raise HTTPException(status_code=404, detail=f"Intel Drop {drop_id} not found")

    return {"drop": rows[0]}


@app.get("/api/pulse/consensus")
def pulse_consensus(
    horizon: str = Query("1W", description="Time horizon (1W, 1M, 3M, 6M)"),
) -> Dict[str, Any]:
    """
    Get consensus view across all domains for the latest timestamp.

    Aggregates signals from all 11 specialist domains.
    """
    # Get latest timestamp for this horizon
    latest_rows = _fetch_rows(
        """
        SELECT MAX(as_of_ts) as latest_ts
        FROM features.intel_drops
        WHERE horizon = ?
        """,
        [horizon.upper()],
    )

    latest_ts = (
        latest_rows[0]["latest_ts"]
        if latest_rows and latest_rows[0]["latest_ts"]
        else None
    )

    if not latest_ts:
        return {
            "horizon": horizon,
            "as_of_ts": None,
            "message": "No intel drops found for this horizon",
            "domains": {},
        }

    # Get all domains for this timestamp/horizon
    rows = _fetch_rows(
        """
        SELECT
            domain, direction, pressure_cents, edge, top_drivers, regime_tags
        FROM features.intel_drops
        WHERE as_of_ts = ? AND horizon = ?
        ORDER BY domain
        """,
        [latest_ts, horizon.upper()],
    )

    domains = {}
    total_direction = 0
    total_pressure = 0.0
    total_edge = 0.0

    for row in rows:
        domains[row["domain"]] = {
            "direction": row["direction"],
            "pressure_cents": row["pressure_cents"],
            "edge": row["edge"],
            "top_drivers": row["top_drivers"],
            "regime_tags": row["regime_tags"],
        }
        total_direction += row["direction"]
        total_pressure += row["pressure_cents"]
        total_edge += row["edge"]

    n = len(rows)

    return {
        "horizon": horizon,
        "as_of_ts": latest_ts,
        "num_domains": n,
        "consensus": {
            "direction": total_direction / n if n > 0 else 0,
            "pressure_cents": total_pressure / n if n > 0 else 0,
            "average_edge": total_edge / n if n > 0 else 0,
            "signal": (
                "BULLISH"
                if total_direction > 3
                else "BEARISH"
                if total_direction < -3
                else "NEUTRAL"
            ),
        },
        "domains": domains,
    }


@app.get("/api/pulse/domain/{domain}/history")
def pulse_domain_history(
    domain: str,
    horizon: str = Query("1W", description="Time horizon"),
    days: int = Query(30, ge=1, le=365, description="Days of history"),
) -> Dict[str, Any]:
    """
    Get historical Intel Drops for a specific domain.
    """
    rows = _fetch_rows(
        f"""
        SELECT
            id, as_of_ts, domain, horizon, direction, pressure_cents, edge,
            driver_weights, top_drivers, regime_tags, created_at
        FROM features.intel_drops
        WHERE domain = ?
          AND horizon = ?
          AND as_of_ts >= NOW() - INTERVAL '{days} days'
        ORDER BY as_of_ts ASC
        """,
        [domain.upper(), horizon.upper()],
    )

    return {
        "domain": domain.upper(),
        "horizon": horizon.upper(),
        "days": days,
        "history": rows,
        "count": len(rows),
    }


@app.get("/api/pulse/signals")
def pulse_signals(
    direction: Optional[int] = Query(
        None, ge=-1, le=1, description="Filter by direction (-1, 0, 1)"
    ),
    min_edge: Optional[float] = Query(
        None, ge=0, le=1, description="Minimum edge threshold"
    ),
    horizon: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get actionable signals from Intel Drops.

    Filter by direction (bearish=-1, neutral=0, bullish=1) and minimum edge.
    """
    params = []
    where_clauses = []

    if direction is not None:
        where_clauses.append("direction = ?")
        params.append(direction)

    if min_edge is not None:
        where_clauses.append("edge >= ?")
        params.append(min_edge)

    if horizon:
        where_clauses.append("horizon = ?")
        params.append(horizon.upper())

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    rows = _fetch_rows(
        f"""
        SELECT
            id, as_of_ts, domain, horizon, direction, pressure_cents, edge,
            top_drivers, regime_tags, source_model
        FROM features.intel_drops
        WHERE {where_sql}
        ORDER BY edge DESC, as_of_ts DESC
        LIMIT 50
        """,
        params,
    )

    # Categorize by signal strength
    strong_signals = [r for r in rows if r["edge"] >= 0.7]
    moderate_signals = [r for r in rows if 0.5 <= r["edge"] < 0.7]
    weak_signals = [r for r in rows if r["edge"] < 0.5]

    return {
        "filters": {"direction": direction, "min_edge": min_edge, "horizon": horizon},
        "signals": {
            "strong": strong_signals,
            "moderate": moderate_signals,
            "weak": weak_signals,
        },
        "total_count": len(rows),
    }


# =============================================================================
# KEY MARKET DRIVERS - Dashboard Cards
# =============================================================================
# These endpoints power the 4 Key Market Driver cards on the dashboard:
# 1. VIX Stress - Volatility pressure from VIX term structure
# 2. Crush Pressure - Soybean processor margin stress
# 3. China Tension - Trade flow and geopolitical risk from China
# 4. Tariff Threat - Trade policy uncertainty
# =============================================================================


def _get_db_connection():
    """Get database connection for pressure calculations."""
    import psycopg2

    return psycopg2.connect(os.environ.get("DATABASE_URL", ""))


@app.get("/api/market-drivers")
def market_drivers_all(
    as_of_date: Optional[str] = Query(
        None, description="Date (YYYY-MM-DD), defaults to today"
    ),
) -> Dict[str, Any]:
    """
    Get all 4 Key Market Drivers for dashboard cards.

    Returns real-time domain-specific pressure indicators:
    - VIX Stress: Volatility regime from VIX term structure
    - Crush Pressure: Soybean processor margin health
    - China Tension: Trade flow and political risk
    - Tariff Threat: Trade policy uncertainty

    Each driver includes:
    - score (0-100)
    - level (text classification)
    - headline (short summary)
    - narrative (explanation)
    - key_drivers (what's causing it)
    - regime (current market regime)
    - components (detailed breakdown)
    - domain_context (expert interpretation)
    """
    from datetime import date as dt_date

    target_date = dt_date.fromisoformat(as_of_date) if as_of_date else None
    conn = _get_db_connection()

    try:
        vix = calculate_volatility_pressure(conn, target_date)
        crush = calculate_crush_pressure(conn, target_date)
        china = calculate_china_tension(conn, target_date)
        tariff = calculate_tariff_pressure(conn, target_date)
    finally:
        conn.close()

    return {
        "as_of_date": (target_date or dt_date.today()).isoformat(),
        "drivers": {
            "vix_stress": vix,
            "crush_pressure": crush,
            "china_tension": china,
            "tariff_threat": tariff,
        },
        "summary": {
            "average_pressure": round(
                (vix["score"] + crush["score"] + china["score"] + tariff["score"]) / 4,
                1,
            ),
            "highest_pressure": max(
                [
                    (vix["name"], vix["score"]),
                    (crush["name"], crush["score"]),
                    (china["name"], china["score"]),
                    (tariff["name"], tariff["score"]),
                ],
                key=lambda x: x[1],
            ),
            "alert_count": sum(
                1 for d in [vix, crush, china, tariff] if d["score"] >= 65
            ),
        },
    }


@app.get("/api/market-drivers/vix-stress")
def market_driver_vix_stress(
    as_of_date: Optional[str] = Query(None, description="Date (YYYY-MM-DD)"),
) -> Dict[str, Any]:
    """
    Get VIX Stress indicator.

    Domain expertise:
    - VIX absolute levels (12-15 low, 20 normal, 25+ elevated, 30+ fear, 40+ panic)
    - VIX term structure (contango = orderly, backwardation = stress)
    - OVX (oil volatility) for energy context
    - Realized ZL volatility comparison
    """
    from datetime import date as dt_date

    target_date = dt_date.fromisoformat(as_of_date) if as_of_date else None
    conn = _get_db_connection()

    try:
        result = calculate_volatility_pressure(conn, target_date)
    finally:
        conn.close()

    return result


@app.get("/api/market-drivers/crush-pressure")
def market_driver_crush_pressure(
    as_of_date: Optional[str] = Query(None, description="Date (YYYY-MM-DD)"),
) -> Dict[str, Any]:
    """
    Get Crush Pressure indicator.

    Domain expertise:
    - Board crush economics ($0.75 danger, $1.25 tight, $1.50 neutral, $1.75+ healthy)
    - Oil share dynamics (falling = bearish soyoil)
    - Crush specialist model signal
    - Processor margin regime classification
    """
    from datetime import date as dt_date

    target_date = dt_date.fromisoformat(as_of_date) if as_of_date else None
    conn = _get_db_connection()

    try:
        result = calculate_crush_pressure(conn, target_date)
    finally:
        conn.close()

    return result


@app.get("/api/market-drivers/china-tension")
def market_driver_china_tension(
    as_of_date: Optional[str] = Query(None, description="Date (YYYY-MM-DD)"),
) -> Dict[str, Any]:
    """
    Get China Tension indicator.

    Domain expertise:
    - FXI (China Large-Cap ETF) performance
    - CNY/USD level and trend (7.0 psychologically important)
    - BDRY (Baltic Dry shipping) as trade flow proxy
    - China specialist model signal
    - China-related news concentration

    Critical for soybean markets:
    - China is largest soybean importer (~60% of global trade)
    - CNY weakness makes US beans less competitive vs Brazil
    - Political tension can lead to sudden demand shifts
    """
    from datetime import date as dt_date

    target_date = dt_date.fromisoformat(as_of_date) if as_of_date else None
    conn = _get_db_connection()

    try:
        result = calculate_china_tension(conn, target_date)
    finally:
        conn.close()

    return result


@app.get("/api/market-drivers/tariff-threat")
def market_driver_tariff_threat(
    as_of_date: Optional[str] = Query(None, description="Date (YYYY-MM-DD)"),
) -> Dict[str, Any]:
    """
    Get Tariff Threat indicator.

    Domain expertise:
    - TPU (Trade Policy Uncertainty) Index - Baker-Bloom-Davis
    - Trade EMV (Equity Market Volatility from trade policy)
    - Legislation velocity
    - Tariff specialist model signal

    Calibrated thresholds:
    - TPU < 40: Trade calm
    - TPU 40-100: Normal uncertainty
    - TPU 100-200: Elevated (tariff threats)
    - TPU 200-400: High (active tariff war)
    - TPU > 400: Extreme (2018-2019 peak levels)
    """
    from datetime import date as dt_date

    target_date = dt_date.fromisoformat(as_of_date) if as_of_date else None
    conn = _get_db_connection()

    try:
        result = calculate_tariff_pressure(conn, target_date)
    finally:
        conn.close()

    return result
