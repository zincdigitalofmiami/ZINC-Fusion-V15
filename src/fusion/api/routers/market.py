"""Market and forecast API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from .common import _fetch_rows, _first_existing_column, _table_exists

router = APIRouter()


@router.get("/api/market/zl")
def market_zl(
    symbol: str = "ZL",
    limit: int = Query(2000, ge=1, le=10000),
) -> dict[str, Any]:
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


@router.get("/api/forecast/quantiles")
def forecast_quantiles(
    symbol: str = "ZL",
    horizon_days: list[int] | None = Query(None),
) -> dict[str, Any]:
    # Schema: forecast_date (not as_of_date), horizon (not horizon_days)
    rows = _fetch_rows(
        """
        SELECT forecast_date AS as_of_date, horizon AS horizon_days, p10, p50, p90
        FROM forecasts.forecast_quantiles
        WHERE symbol = ?
        ORDER BY forecast_date ASC
        """,
        [symbol],
    )

    if horizon_days:
        rows = [row for row in rows if row["horizon_days"] in horizon_days]

    return {"symbol": symbol, "quantiles": rows}


@router.get("/api/forecast/bands")
def forecast_bands(
    symbol: str = "ZL",
    horizon_days: list[int] | None = Query(None),
) -> dict[str, Any]:
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


@router.get("/api/zl/live")
def zl_live() -> dict[str, Any]:
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
        FROM analytics.price_15m
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


@router.get("/api/zl/intraday")
def zl_intraday(
    hours: int = Query(
        24, ge=1, le=168, description="Hours of data to return (max 168 = 7 days)"
    ),
) -> dict[str, Any]:
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
        FROM analytics.price_15m
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


@router.get("/api/zl/intraday/ohlc")
def zl_intraday_ohlc(
    days: int = Query(7, ge=1, le=60, description="Days of data to return"),
) -> dict[str, Any]:
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
        FROM analytics.price_15m
        WHERE timestamp > NOW() - INTERVAL '{days} days'
        ORDER BY timestamp ASC
        """
    )

    bars = []
    for row in rows:
        ts = row["timestamp"]
        # Handle string or datetime
        ts_str = ts if isinstance(ts, str) else ts.isoformat()
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
