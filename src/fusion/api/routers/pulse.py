"""Intel pulse API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .common import _fetch_rows

router = APIRouter()


@router.get("/api/pulse/domains")
def pulse_domains() -> dict[str, Any]:
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


@router.get("/api/pulse/latest")
def pulse_latest(
    domain: str | None = None,
    horizon: str | None = None,
    limit: int = Query(10, ge=1, le=100),
) -> dict[str, Any]:
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
        FROM features.intel_drops_event
        WHERE {where_sql}
        ORDER BY as_of_ts DESC, domain, horizon
        LIMIT ?
        """,
        [*params, limit],
    )

    return {
        "drops": rows,
        "count": len(rows),
        "filters": {"domain": domain, "horizon": horizon},
    }


@router.get("/api/pulse/drop/{drop_id}")
def pulse_drop_by_id(drop_id: int) -> dict[str, Any]:
    """
    Get a single Intel Drop by ID, including full narrative.
    """
    rows = _fetch_rows(
        """
        SELECT
            id, as_of_ts, domain, horizon, direction, pressure_cents, edge,
            driver_weights, top_drivers, regime_tags, quality_flags, data_gaps,
            receipts, narrative, quant_payload, source_model, created_at
        FROM features.intel_drops_event
        WHERE id = ?
        """,
        [drop_id],
    )

    if not rows:
        raise HTTPException(status_code=404, detail=f"Intel Drop {drop_id} not found")

    return {"drop": rows[0]}


@router.get("/api/pulse/consensus")
def pulse_consensus(
    horizon: str = Query("1W", description="Time horizon (1W, 1M, 3M, 6M)"),
) -> dict[str, Any]:
    """
    Get consensus view across all domains for the latest timestamp.

    Aggregates signals from all 11 specialist domains.
    """
    # Get latest timestamp for this horizon
    latest_rows = _fetch_rows(
        """
        SELECT MAX(as_of_ts) as latest_ts
        FROM features.intel_drops_event
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
        FROM features.intel_drops_event
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

    count = len(rows)

    return {
        "horizon": horizon,
        "as_of_ts": latest_ts,
        "num_domains": count,
        "consensus": {
            "direction": total_direction / count if count > 0 else 0,
            "pressure_cents": total_pressure / count if count > 0 else 0,
            "average_edge": total_edge / count if count > 0 else 0,
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


@router.get("/api/pulse/domain/{domain}/history")
def pulse_domain_history(
    domain: str,
    horizon: str = Query("1W", description="Time horizon"),
    days: int = Query(30, ge=1, le=365, description="Days of history"),
) -> dict[str, Any]:
    """
    Get historical Intel Drops for a specific domain.
    """
    rows = _fetch_rows(
        f"""
        SELECT
            id, as_of_ts, domain, horizon, direction, pressure_cents, edge,
            driver_weights, top_drivers, regime_tags, created_at
        FROM features.intel_drops_event
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


@router.get("/api/pulse/signals")
def pulse_signals(
    direction: int | None = Query(
        None, ge=-1, le=1, description="Filter by direction (-1, 0, 1)"
    ),
    min_edge: float | None = Query(
        None, ge=0, le=1, description="Minimum edge threshold"
    ),
    horizon: str | None = None,
) -> dict[str, Any]:
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
        FROM features.intel_drops_event
        WHERE {where_sql}
        ORDER BY edge DESC, as_of_ts DESC
        LIMIT 50
        """,
        params,
    )

    # Categorize by signal strength
    strong_signals = [row for row in rows if row["edge"] >= 0.7]
    moderate_signals = [row for row in rows if 0.5 <= row["edge"] < 0.7]
    weak_signals = [row for row in rows if row["edge"] < 0.5]

    return {
        "filters": {"direction": direction, "min_edge": min_edge, "horizon": horizon},
        "signals": {
            "strong": strong_signals,
            "moderate": moderate_signals,
            "weak": weak_signals,
        },
        "total_count": len(rows),
    }
