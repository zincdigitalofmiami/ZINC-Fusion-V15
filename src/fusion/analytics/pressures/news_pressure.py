"""
ZINC-FUSION-V15: News and Geopolitical Pressure Calculators

Domain-specific gauges for news flow and geopolitical risk.

News Pressure:
Measures intensity and composition of market-moving news flow.
High velocity + negative tone = elevated uncertainty.

Key Indicators:
- Total news velocity (all sources)
- Trump/tariff news concentration
- Executive action pace
- Source-weighted velocity

Geopolitical Pressure:
Measures tail risk from geopolitical events.
Uses EPU spikes, energy volatility, EM stress, safe haven demand.

Key Indicators:
- EPU spike detection (vs recent baseline)
- OVX (oil volatility) - geopolitical often hits energy first
- EM FX stress (first casualty of geopolitical risk)
- Gold bid (fear proxy)

@author Claude (ZINC-FUSION-V15)
@date 2026-01-31
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# ==============================================================================
# NEWS PRESSURE THRESHOLDS
# ==============================================================================

# Weekly news velocity thresholds (relative to baseline)
NEWS_QUIET = 0.5          # 50% of baseline
NEWS_LIGHT = 0.75
NEWS_NORMAL = 1.0
NEWS_ACTIVE = 1.5         # 50% above baseline
NEWS_HEAVY = 2.0          # 2x baseline
NEWS_FIREHOSE = 3.0       # 3x baseline

# Executive action thresholds (per week)
EXEC_QUIET = 0
EXEC_LIGHT = 2
EXEC_NORMAL = 5
EXEC_HEAVY = 10
EXEC_EXTREME = 20


@dataclass
class NewsRegime:
    """News flow regime classification."""
    name: str
    description: str
    implication: str


NEWS_REGIMES = {
    "quiet": NewsRegime(
        name="Quiet News",
        description="Light news flow. Markets focused on fundamentals.",
        implication="Technical and seasonal factors may dominate."
    ),
    "normal": NewsRegime(
        name="Normal News",
        description="Standard news velocity. No unusual concentration.",
        implication="Markets digesting information normally."
    ),
    "active": NewsRegime(
        name="Active News",
        description="Above-average news velocity. Multiple narratives in play.",
        implication="Watch for sentiment shifts. Headlines may drive."
    ),
    "heavy": NewsRegime(
        name="Heavy News",
        description="High news velocity. Markets processing heavy information flow.",
        implication="Volatility likely elevated. Information overload risk."
    ),
    "storm": NewsRegime(
        name="News Storm",
        description="Extreme news velocity. Crisis-level coverage.",
        implication="Expect large moves. Liquidity may thin. Headlines drive."
    )
}

# ==============================================================================
# GEOPOLITICAL THRESHOLDS
# ==============================================================================

# EPU spike detection (recent vs baseline ratio)
EPU_SPIKE_MILD = 1.2      # 20% above baseline
EPU_SPIKE_MODERATE = 1.5  # 50% above
EPU_SPIKE_SEVERE = 2.0    # 2x baseline
EPU_SPIKE_CRISIS = 3.0    # 3x baseline

# Gold momentum thresholds (20-day change)
GOLD_CALM = -0.02
GOLD_BID = 0.02
GOLD_STRONG_BID = 0.05
GOLD_FEAR_BID = 0.10


@dataclass
class GeopoliticalRegime:
    """Geopolitical risk regime."""
    name: str
    description: str
    commodity_impact: str


GEOPOLITICAL_REGIMES = {
    "stable": GeopoliticalRegime(
        name="Stable World",
        description="No major geopolitical flashpoints. Risk appetite normal.",
        commodity_impact="Fundamentals drive. Supply/demand in focus."
    ),
    "tension": GeopoliticalRegime(
        name="Rising Tensions",
        description="Geopolitical noise increasing. Markets watching headlines.",
        commodity_impact="Risk premium building. Supply disruption fears."
    ),
    "elevated": GeopoliticalRegime(
        name="Elevated Risk",
        description="Significant geopolitical uncertainty. Multiple hotspots.",
        commodity_impact="Supply premium elevated. Safe havens bid."
    ),
    "crisis": GeopoliticalRegime(
        name="Geopolitical Crisis",
        description="Crisis mode. Active conflict risk or major standoff.",
        commodity_impact="Major supply disruption risk. Energy spiking."
    )
}


def score_news_velocity(velocity_ratio: float) -> Tuple[float, str]:
    """
    Score news velocity relative to baseline.

    Returns (score, description).
    """
    if velocity_ratio < NEWS_QUIET:
        return 15, "Very quiet news flow"
    elif velocity_ratio < NEWS_LIGHT:
        return 25, "Light news flow"
    elif velocity_ratio < NEWS_NORMAL:
        pct = (velocity_ratio - NEWS_LIGHT) / (NEWS_NORMAL - NEWS_LIGHT)
        score = 25 + (pct * 15)  # 25-40
        return score, "Below-average news"
    elif velocity_ratio < NEWS_ACTIVE:
        pct = (velocity_ratio - NEWS_NORMAL) / (NEWS_ACTIVE - NEWS_NORMAL)
        score = 40 + (pct * 15)  # 40-55
        return score, "Normal news flow"
    elif velocity_ratio < NEWS_HEAVY:
        pct = (velocity_ratio - NEWS_ACTIVE) / (NEWS_HEAVY - NEWS_ACTIVE)
        score = 55 + (pct * 15)  # 55-70
        return score, "Active news cycle"
    elif velocity_ratio < NEWS_FIREHOSE:
        pct = (velocity_ratio - NEWS_HEAVY) / (NEWS_FIREHOSE - NEWS_HEAVY)
        score = 70 + (pct * 15)  # 70-85
        return score, "Heavy news flow"
    else:
        return 90, "News firehose"


def score_executive_velocity(exec_count: int) -> Tuple[float, str]:
    """
    Score executive action velocity.

    Returns (score, description).
    """
    if exec_count <= EXEC_QUIET:
        return 20, "No executive actions"
    elif exec_count <= EXEC_LIGHT:
        return 30, "Light executive activity"
    elif exec_count <= EXEC_NORMAL:
        return 45, "Normal executive activity"
    elif exec_count <= EXEC_HEAVY:
        pct = (exec_count - EXEC_NORMAL) / (EXEC_HEAVY - EXEC_NORMAL)
        score = 45 + (pct * 20)  # 45-65
        return score, "Heavy executive activity"
    elif exec_count <= EXEC_EXTREME:
        pct = (exec_count - EXEC_HEAVY) / (EXEC_EXTREME - EXEC_HEAVY)
        score = 65 + (pct * 20)  # 65-85
        return score, "Very heavy executive activity"
    else:
        return 90, "Extreme executive activity"


def score_epu_spike(recent_avg: float, baseline_avg: float) -> Tuple[float, str]:
    """
    Score EPU spike relative to baseline.

    Returns (score, description).
    """
    if baseline_avg == 0:
        return 50, "No baseline"

    ratio = recent_avg / baseline_avg

    if ratio < 1.0:
        return 30, "EPU below baseline"
    elif ratio < EPU_SPIKE_MILD:
        return 40, "EPU near baseline"
    elif ratio < EPU_SPIKE_MODERATE:
        pct = (ratio - EPU_SPIKE_MILD) / (EPU_SPIKE_MODERATE - EPU_SPIKE_MILD)
        score = 50 + (pct * 15)  # 50-65
        return score, "EPU mildly elevated"
    elif ratio < EPU_SPIKE_SEVERE:
        pct = (ratio - EPU_SPIKE_MODERATE) / (EPU_SPIKE_SEVERE - EPU_SPIKE_MODERATE)
        score = 65 + (pct * 15)  # 65-80
        return score, "EPU spiking"
    elif ratio < EPU_SPIKE_CRISIS:
        pct = (ratio - EPU_SPIKE_SEVERE) / (EPU_SPIKE_CRISIS - EPU_SPIKE_SEVERE)
        score = 80 + (pct * 12)  # 80-92
        return score, "EPU crisis spike"
    else:
        return 95, "EPU extreme spike"


def score_gold_fear(gold_change_20d: float) -> Tuple[float, str]:
    """
    Score gold as fear proxy.

    Returns (score, description).
    """
    if gold_change_20d < GOLD_CALM:
        return 25, "Gold selling off - risk-on"
    elif gold_change_20d < 0:
        return 35, "Gold slightly weak"
    elif gold_change_20d < GOLD_BID:
        return 45, "Gold stable"
    elif gold_change_20d < GOLD_STRONG_BID:
        return 60, "Gold catching bids"
    elif gold_change_20d < GOLD_FEAR_BID:
        return 75, "Strong gold bid - fear"
    else:
        return 90, "Gold surging - flight to safety"


def calculate_news_pressure(conn, as_of_date: Optional[date] = None) -> Dict:
    """
    Calculate Global News Pressure.

    Components:
    1. Total News Velocity 45%: All sources combined
    2. Trump/Policy Concentration 25%: Policy-related news
    3. Executive Velocity 15%: Executive action pace
    4. Source Mix 15%: Diversity of coverage

    Returns PressureReading-compatible dict.
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # ==== 1. TOTAL NEWS VELOCITY ====
    # This week
    cur.execute("""
        SELECT
            (SELECT COUNT(*) FROM alt.econ_news WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s) +
            (SELECT COUNT(*) FROM alt.profarmer_news WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s) +
            (SELECT COUNT(*) FROM alt.executive_actions WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s) +
            (SELECT COUNT(*) FROM alt.legislation_1d WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s)
        as total_week
    """, (as_of_date, as_of_date, as_of_date, as_of_date, as_of_date, as_of_date, as_of_date, as_of_date))
    total_week = cur.fetchone()[0] or 0

    # Baseline (previous month weekly average)
    cur.execute("""
        SELECT
            (SELECT COUNT(*) FROM alt.econ_news WHERE event_date >= %s - INTERVAL '35 days' AND event_date <= %s - INTERVAL '7 days') +
            (SELECT COUNT(*) FROM alt.profarmer_news WHERE event_date >= %s - INTERVAL '35 days' AND event_date <= %s - INTERVAL '7 days') +
            (SELECT COUNT(*) FROM alt.executive_actions WHERE event_date >= %s - INTERVAL '35 days' AND event_date <= %s - INTERVAL '7 days') +
            (SELECT COUNT(*) FROM alt.legislation_1d WHERE event_date >= %s - INTERVAL '35 days' AND event_date <= %s - INTERVAL '7 days')
        as total_month
    """, (as_of_date, as_of_date, as_of_date, as_of_date, as_of_date, as_of_date, as_of_date, as_of_date))
    total_month = cur.fetchone()[0] or 1
    baseline_weekly = total_month / 4

    velocity_ratio = total_week / baseline_weekly if baseline_weekly > 0 else 1.0
    velocity_score, velocity_desc = score_news_velocity(velocity_ratio)
    components["velocity_score"] = round(velocity_score, 1)
    components["news_this_week"] = total_week
    components["velocity_ratio"] = round(velocity_ratio, 2)

    # ==== 2. TRUMP/POLICY CONCENTRATION ====
    try:
        cur.execute("""
            SELECT COUNT(*) FROM alt.profarmer_news
            WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s
            AND (headline ILIKE '%%trump%%' OR headline ILIKE '%%tariff%%' OR
                 headline ILIKE '%%policy%%' OR content ILIKE '%%trump%%')
        """, (as_of_date, as_of_date))
        trump_count = cur.fetchone()[0] or 0
    except Exception:
        trump_count = 0

    trump_concentration = trump_count / max(total_week, 1)
    trump_score = min(100, 30 + (trump_concentration * 200) + (trump_count * 3))
    components["trump_score"] = round(trump_score, 1)
    components["trump_news_count"] = trump_count

    # ==== 3. EXECUTIVE VELOCITY ====
    cur.execute("""
        SELECT COUNT(*) FROM alt.executive_actions
        WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s
    """, (as_of_date, as_of_date))
    exec_count = cur.fetchone()[0] or 0

    exec_score, exec_desc = score_executive_velocity(exec_count)
    components["executive_score"] = round(exec_score, 1)
    components["executive_count"] = exec_count

    # ==== COMPOSITE ====
    score = (velocity_score * 0.45) + (trump_score * 0.30) + (exec_score * 0.25)
    score = float(np.clip(score, 0, 100))

    # ==== REGIME ====
    if score >= 75:
        regime = "storm"
    elif score >= 60:
        regime = "heavy"
    elif score >= 45:
        regime = "active"
    elif score >= 30:
        regime = "normal"
    else:
        regime = "quiet"

    regime_info = NEWS_REGIMES.get(regime, NEWS_REGIMES["normal"])

    # ==== NARRATIVE ====
    if score >= 75:
        headline = "News Flow Surging"
    elif score >= 60:
        headline = "Heavy News Coverage"
    elif score >= 45:
        headline = "Active News Cycle"
    elif score >= 30:
        headline = "Normal News Flow"
    else:
        headline = "Quiet News Environment"

    narrative = f"{total_week} articles this week ({velocity_ratio:.1f}x baseline). {regime_info.description} {regime_info.implication}"

    drivers = []
    if velocity_score >= 55:
        drivers.append(f"{total_week} articles ({velocity_ratio:.1f}x normal)")
    if trump_score >= 55:
        drivers.append(f"{trump_count} policy-related articles")
    if exec_score >= 55:
        drivers.append(f"{exec_count} executive actions")
    if not drivers:
        drivers.append("Light news flow")

    # ==== LEVEL/COLOR ====
    if score >= 80:
        level, color = "Extreme Pressure", "#DC2626"
    elif score >= 65:
        level, color = "High Pressure", "#EA580C"
    elif score >= 50:
        level, color = "Elevated", "#D97706"
    elif score >= 35:
        level, color = "Normal", "#65A30D"
    else:
        level, color = "Low Pressure", "#0891B2"

    return {
        "name": "Global News Pressure",
        "score": round(score, 1),
        "level": level,
        "trend": "Stable",
        "headline": headline,
        "narrative": narrative,
        "key_drivers": drivers,
        "color": color,
        "icon": "newspaper",
        "sparkline": [50] * 10,
        "percentile_30d": round(score, 1),
        "percentile_1y": round(score, 1),
        "regime": regime,
        "momentum": 0.0,
        "as_of_date": as_of_date.isoformat(),
        "components": components,
        "domain_context": {
            "regime_name": regime_info.name,
            "regime_description": regime_info.description,
            "implication": regime_info.implication,
        }
    }


def calculate_geopolitical_pressure(conn, as_of_date: Optional[date] = None) -> Dict:
    """
    Calculate Country War / Geopolitical Pressure.

    Components:
    1. EPU Spike Detection 35%: Policy uncertainty spike
    2. OVX (Oil Vol) 25%: Energy volatility
    3. Gold Fear 25%: Safe haven demand
    4. EM FX Stress 15%: Emerging market stress

    Returns PressureReading-compatible dict.
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # ==== 1. EPU SPIKE ====
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'USEPUINDXD' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 30
    """, (as_of_date,))
    epu_data = cur.fetchall()

    epu_score = 50
    if len(epu_data) >= 10:
        epu_values = [float(r[1]) for r in epu_data if r[1] is not None]
        recent_avg = np.mean(epu_values[:5]) if len(epu_values) >= 5 else epu_values[0]
        baseline_avg = np.mean(epu_values[5:]) if len(epu_values) > 5 else recent_avg

        epu_score, epu_desc = score_epu_spike(recent_avg, baseline_avg)
        components["epu_spike_score"] = round(epu_score, 1)
        components["epu_recent_avg"] = round(recent_avg, 0)
        components["epu_baseline_avg"] = round(baseline_avg, 0)

    # ==== 2. OVX (Oil Volatility) ====
    cur.execute("""
        SELECT value FROM econ.vol_indices_1d
        WHERE series_id = 'OVXCLS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 1
    """, (as_of_date,))
    ovx_row = cur.fetchone()

    ovx_score = 50
    if ovx_row:
        current_ovx = float(ovx_row[0])
        # OVX thresholds
        if current_ovx < 25:
            ovx_score = 25
        elif current_ovx < 35:
            ovx_score = 40
        elif current_ovx < 50:
            ovx_score = 55 + ((current_ovx - 35) / 15 * 15)
        elif current_ovx < 70:
            ovx_score = 70 + ((current_ovx - 50) / 20 * 15)
        else:
            ovx_score = 90

        components["ovx_score"] = round(ovx_score, 1)
        components["ovx_value"] = round(current_ovx, 1)

    # ==== 3. GOLD FEAR ====
    cur.execute("""
        SELECT event_date, close FROM mkt.etf_1d
        WHERE symbol = 'GLD' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 21
    """, (as_of_date,))
    gld_data = cur.fetchall()

    gold_score = 50
    if len(gld_data) >= 20:
        gld_values = [float(r[1]) for r in gld_data if r[1] is not None]
        gold_change = (gld_values[0] - gld_values[-1]) / gld_values[-1] if gld_values[-1] > 0 else 0

        gold_score, gold_desc = score_gold_fear(gold_change)
        components["gold_score"] = round(gold_score, 1)
        components["gold_change_20d"] = round(gold_change * 100, 2)

    # ==== 4. EM FX STRESS ====
    cur.execute("""
        SELECT event_date, value FROM econ.rates_1d
        WHERE series_id = 'DTWEXEMEGS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 21
    """, (as_of_date,))
    em_data = cur.fetchall()

    em_score = 50
    if len(em_data) >= 20:
        em_values = [float(r[1]) for r in em_data if r[1] is not None]
        em_change = (em_values[0] - em_values[-1]) / em_values[-1] if em_values[-1] > 0 else 0

        # EM weakness (rising index) = stress
        if em_change > 0.05:
            em_score = 85
        elif em_change > 0.02:
            em_score = 65
        elif em_change > 0:
            em_score = 50
        elif em_change > -0.02:
            em_score = 40
        else:
            em_score = 25

        components["em_score"] = round(em_score, 1)
        components["em_change_20d"] = round(em_change * 100, 2)

    # ==== COMPOSITE ====
    score = (epu_score * 0.35) + (ovx_score * 0.25) + (gold_score * 0.25) + (em_score * 0.15)
    score = float(np.clip(score, 0, 100))

    # ==== REGIME ====
    if score >= 75:
        regime = "crisis"
    elif score >= 60:
        regime = "elevated"
    elif score >= 45:
        regime = "tension"
    else:
        regime = "stable"

    regime_info = GEOPOLITICAL_REGIMES.get(regime, GEOPOLITICAL_REGIMES["stable"])

    # ==== NARRATIVE ====
    if score >= 75:
        headline = "Geopolitical Risk Elevated"
    elif score >= 60:
        headline = "Geopolitical Tensions Rising"
    elif score >= 45:
        headline = "Moderate Geopolitical Noise"
    else:
        headline = "Geopolitical Environment Stable"

    narrative = f"{regime_info.description} {regime_info.commodity_impact}"

    drivers = []
    if epu_score >= 60:
        drivers.append("Policy uncertainty spiking")
    if ovx_score >= 60:
        drivers.append("Oil volatility elevated")
    if gold_score >= 60:
        drivers.append("Gold catching bids")
    if em_score >= 60:
        drivers.append("EM currencies weak")
    if not drivers:
        drivers.append("Geopolitical calm")

    # ==== LEVEL/COLOR ====
    if score >= 80:
        level, color = "Extreme Pressure", "#DC2626"
    elif score >= 65:
        level, color = "High Pressure", "#EA580C"
    elif score >= 50:
        level, color = "Elevated", "#D97706"
    elif score >= 35:
        level, color = "Normal", "#65A30D"
    else:
        level, color = "Low Pressure", "#0891B2"

    return {
        "name": "Country War Pressure",
        "score": round(score, 1),
        "level": level,
        "trend": "Stable",
        "headline": headline,
        "narrative": narrative,
        "key_drivers": drivers,
        "color": color,
        "icon": "globe",
        "sparkline": [50] * 10,
        "percentile_30d": round(score, 1),
        "percentile_1y": round(score, 1),
        "regime": regime,
        "momentum": 0.0,
        "as_of_date": as_of_date.isoformat(),
        "components": components,
        "domain_context": {
            "regime_name": regime_info.name,
            "regime_description": regime_info.description,
            "commodity_impact": regime_info.commodity_impact,
        }
    }
