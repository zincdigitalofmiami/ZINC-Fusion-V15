"""Overview and dashboard API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from fusion.api.db import get_backend

from .common import _fetch_rows, _first_existing_column, _recent_files, _table_exists

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/dashboard/summary")
def dashboard_summary(symbol: str = "ZL") -> dict[str, Any]:
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


@router.get("/api/overview/models")
def overview_models() -> dict[str, Any]:
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
        "trump_effect",
    ]

    # Core OOF — query training.oof_core_1d (v3: single core table, no 'source' column)
    core = {"exists": False, "by_horizon": []}
    if _table_exists("training", "oof_core_1d"):
        core["exists"] = True
        core["by_horizon"] = _fetch_rows(
            """
            SELECT horizon_days as horizon, COUNT(*)::BIGINT as rows,
                   MIN(trade_date) as start_date, MAX(trade_date) as end_date
            FROM training.oof_core_1d
            GROUP BY horizon_days
            ORDER BY horizon_days
            """
        )

    # Specialist OOF — v3 has no specialist OOF tables (legacy v2 concept).
    # Check for individual training.oof_specialist_*_1d tables if they exist.
    specialist_rows = []
    for specialist in specialists:
        table = f"oof_specialist_{specialist}_1d"
        if _table_exists("training", table):
            row = _fetch_rows(
                f"""
                SELECT '{specialist}' as specialist, COUNT(*)::BIGINT as rows,
                       MIN(trade_date) as start_date, MAX(trade_date) as end_date
                FROM training.{table}
                """
            )[0]
        else:
            row = {
                "specialist": specialist,
                "rows": 0,
                "start_date": None,
                "end_date": None,
            }
        specialist_rows.append(row)

    # Combined specialist signals — check for specialist_signals_1d table
    combined = {"exists": False, "rows": 0, "start_date": None, "end_date": None}
    if _table_exists("training", "specialist_signals_1d"):
        combined_data = _fetch_rows(
            """
            SELECT COUNT(*)::BIGINT as rows,
                   MIN(as_of_date) as start_date, MAX(as_of_date) as end_date
            FROM training.specialist_signals_1d
            """
        )
        if combined_data and combined_data[0]["rows"] > 0:
            combined["exists"] = True
            combined.update(combined_data[0])

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
            "specialist_asset_keys": [
                f"ag_train_{specialist}_specialist" for specialist in specialists
            ],
        },
        "raw_data": raw_data,
        "core_oof": core,
        "specialist_oof": specialist_rows,
        "specialist_oof_combined": combined,
        "training_logs": {
            "core_oof": _recent_files("logs/core_oof*.log", limit=5),
        },
    }
