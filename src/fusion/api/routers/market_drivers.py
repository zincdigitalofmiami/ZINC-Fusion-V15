"""Key market driver API routes."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query

from fusion.analytics.pressures import (
    calculate_china_tension,
    calculate_crush_pressure,
    calculate_tariff_pressure,
    calculate_volatility_pressure,
)
from fusion.db.connection import get_write_connection

router = APIRouter()


def _get_db_connection():
    """Get database connection for pressure calculations."""
    return get_write_connection()


def _parse_as_of_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@router.get("/api/market-drivers")
def market_drivers_all(
    as_of_date: str | None = Query(
        None, description="Date (YYYY-MM-DD), defaults to today"
    ),
) -> dict[str, Any]:
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
    target_date = _parse_as_of_date(as_of_date)
    conn = _get_db_connection()

    try:
        vix = calculate_volatility_pressure(conn, target_date)
        crush = calculate_crush_pressure(conn, target_date)
        china = calculate_china_tension(conn, target_date)
        tariff = calculate_tariff_pressure(conn, target_date)
    finally:
        conn.close()

    return {
        "as_of_date": (target_date or date.today()).isoformat(),
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
                key=lambda item: item[1],
            ),
            "alert_count": sum(
                1 for row in [vix, crush, china, tariff] if row["score"] >= 65
            ),
        },
    }


@router.get("/api/market-drivers/vix-stress")
def market_driver_vix_stress(
    as_of_date: str | None = Query(None, description="Date (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """
    Get VIX Stress indicator.

    Domain expertise:
    - VIX absolute levels (12-15 low, 20 normal, 25+ elevated, 30+ fear, 40+ panic)
    - VIX term structure (contango = orderly, backwardation = stress)
    - OVX (oil volatility) for energy context
    - Realized ZL volatility comparison
    """
    target_date = _parse_as_of_date(as_of_date)
    conn = _get_db_connection()

    try:
        result = calculate_volatility_pressure(conn, target_date)
    finally:
        conn.close()

    return result


@router.get("/api/market-drivers/crush-pressure")
def market_driver_crush_pressure(
    as_of_date: str | None = Query(None, description="Date (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """
    Get Crush Pressure indicator.

    Domain expertise:
    - Board crush economics ($0.75 danger, $1.25 tight, $1.50 neutral, $1.75+ healthy)
    - Oil share dynamics (falling = bearish soyoil)
    - Crush specialist model signal
    - Processor margin regime classification
    """
    target_date = _parse_as_of_date(as_of_date)
    conn = _get_db_connection()

    try:
        result = calculate_crush_pressure(conn, target_date)
    finally:
        conn.close()

    return result


@router.get("/api/market-drivers/china-tension")
def market_driver_china_tension(
    as_of_date: str | None = Query(None, description="Date (YYYY-MM-DD)"),
) -> dict[str, Any]:
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
    target_date = _parse_as_of_date(as_of_date)
    conn = _get_db_connection()

    try:
        result = calculate_china_tension(conn, target_date)
    finally:
        conn.close()

    return result


@router.get("/api/market-drivers/tariff-threat")
def market_driver_tariff_threat(
    as_of_date: str | None = Query(None, description="Date (YYYY-MM-DD)"),
) -> dict[str, Any]:
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
    target_date = _parse_as_of_date(as_of_date)
    conn = _get_db_connection()

    try:
        result = calculate_tariff_pressure(conn, target_date)
    finally:
        conn.close()

    return result
