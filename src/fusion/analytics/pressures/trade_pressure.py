"""
ZINC-FUSION-V15: Trade and Correlation Pressure Calculators

Domain-specific gauges for global trade flows and cross-asset dynamics.

Trade Pressure:
Uses shipping indices, FX stress, and China demand signals to gauge
global commodity trade health. Critical for soybean export demand.

Key Indicators:
- Baltic Dry Index (BDIY FRED): Dry bulk shipping rates
- Brazil Real (BRL): Key soybean exporter currency
- China demand signals: copper + specialist signals

Correlation Pressure:
Measures risk-on/risk-off regime via cross-asset correlations.
High correlation = risk-off (everything moves together).

Key Metrics:
- ES-ZN correlation: Equity-bond correlation proxy via futures
- ES-GC correlation: Equity-gold correlation proxy via futures
- DXY strength: USD strength = risk-off

@author Claude (ZINC-FUSION-V15)
@date 2026-01-31
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Optional, Tuple

import numpy as np
from dotenv import load_dotenv

load_dotenv()

# ==============================================================================
# TRADE PRESSURE THRESHOLDS
# ==============================================================================

# Baltic Dry momentum thresholds (% change)
BDI_COLLAPSE = -0.30  # 30% drop - shipping crisis
BDI_WEAK = -0.15  # 15% drop - weak trade
BDI_NORMAL_LOW = -0.05  # 5% drop - slight weakness
BDI_NORMAL_HIGH = 0.05  # 5% gain - slight strength
BDI_STRONG = 0.15  # 15% gain - strong trade
BDI_BOOM = 0.30  # 30% gain - trade boom

# Brazil Real thresholds (USD/BRL % change - POSITIVE = BRL weakness)
BRL_CRISIS = 0.15  # 15% BRL weakening = crisis
BRL_STRESS = 0.08  # 8% weakening = stress
BRL_WEAK = 0.03  # 3% weakening = mild stress
BRL_STRONG = -0.03  # 3% strengthening = positive
BRL_BOOM = -0.08  # 8% strengthening = very positive


@dataclass
class TradeRegime:
    """Trade flow regime classification."""

    name: str
    description: str
    ag_impact: str


TRADE_REGIMES = {
    "disrupted": TradeRegime(
        name="Trade Disrupted",
        description="Global trade flows severely impacted. Shipping rates collapsed.",
        ag_impact="Export demand at risk. Basis may blow out. Logistics challenged.",
    ),
    "stressed": TradeRegime(
        name="Trade Stressed",
        description="Trade under pressure. Shipping weak, demand concerns.",
        ag_impact="Export pace may slow. Watch for cancellations.",
    ),
    "normal": TradeRegime(
        name="Normal Trade",
        description="Global trade flowing normally. No major disruptions.",
        ag_impact="Standard export operations. Fundamentals driving.",
    ),
    "strong": TradeRegime(
        name="Strong Trade",
        description="Robust global demand. Shipping rates firm.",
        ag_impact="Export demand supportive. Logistics efficient.",
    ),
    "booming": TradeRegime(
        name="Trade Booming",
        description="Exceptional trade activity. Strong global demand.",
        ag_impact="Export pace accelerating. Strong basis support.",
    ),
}

# ==============================================================================
# CORRELATION PRESSURE THRESHOLDS
# ==============================================================================

# ES-ZN correlation thresholds (typically negative)
ES_ZN_PANIC = 0.30  # Highly positive = stress
ES_ZN_STRESS = 0.10  # Slightly positive = concerning
ES_ZN_NORMAL = -0.15  # Typical negative correlation
ES_ZN_HEALTHY = -0.35  # Strong negative = diversification works

# DXY change thresholds
DXY_RALLY = 0.03  # 3% USD rally = risk-off
DXY_SELLOFF = -0.03  # 3% USD selloff = risk-on


@dataclass
class CorrelationRegime:
    """Correlation/risk regime classification."""

    name: str
    description: str
    positioning: str


CORRELATION_REGIMES = {
    "risk_off": CorrelationRegime(
        name="Risk-Off",
        description="Assets moving in lockstep. Diversification not working.",
        positioning="Defensive positioning. Cash, quality assets. Reduce leverage.",
    ),
    "transitioning": CorrelationRegime(
        name="Transitioning",
        description="Market in transition. Correlations elevated but not extreme.",
        positioning="Monitor closely. Consider reducing risk.",
    ),
    "normal": CorrelationRegime(
        name="Normal",
        description="Standard market correlation structure. Diversification effective.",
        positioning="Normal positioning. Risk-reward balanced.",
    ),
    "risk_on": CorrelationRegime(
        name="Risk-On",
        description="Low correlations. Investors differentiating. Risk appetite strong.",
        positioning="Growth assets favored. Higher risk tolerance.",
    ),
}


def score_shipping(bdiy_change_20d: float) -> Tuple[float, str]:
    """
    Score shipping stress from BDIY change.

    Returns (score, description) where higher = more trade stress.
    """
    if bdiy_change_20d <= BDI_COLLAPSE:
        return 90, "Shipping rates collapsed"
    elif bdiy_change_20d <= BDI_WEAK:
        pct = (bdiy_change_20d - BDI_COLLAPSE) / (BDI_WEAK - BDI_COLLAPSE)
        score = 90 - (pct * 20)  # 70-90
        return score, "Shipping very weak"
    elif bdiy_change_20d <= BDI_NORMAL_LOW:
        pct = (bdiy_change_20d - BDI_WEAK) / (BDI_NORMAL_LOW - BDI_WEAK)
        score = 70 - (pct * 20)  # 50-70
        return score, "Shipping soft"
    elif bdiy_change_20d <= BDI_NORMAL_HIGH:
        return 45, "Shipping stable"
    elif bdiy_change_20d <= BDI_STRONG:
        pct = (bdiy_change_20d - BDI_NORMAL_HIGH) / (BDI_STRONG - BDI_NORMAL_HIGH)
        score = 45 - (pct * 15)  # 30-45
        return score, "Shipping firm"
    elif bdiy_change_20d <= BDI_BOOM:
        pct = (bdiy_change_20d - BDI_STRONG) / (BDI_BOOM - BDI_STRONG)
        score = 30 - (pct * 15)  # 15-30
        return score, "Shipping strong"
    else:
        return 10, "Shipping booming"


def score_brl_stress(brl_change_20d: float) -> Tuple[float, str]:
    """
    Score Brazil Real stress.

    BRL weakness is stress for soy exports (Brazil is competitor).
    Returns (score, description).
    """
    if brl_change_20d >= BRL_CRISIS:
        return 85, "BRL in crisis"
    elif brl_change_20d >= BRL_STRESS:
        pct = (brl_change_20d - BRL_STRESS) / (BRL_CRISIS - BRL_STRESS)
        score = 70 + (pct * 15)  # 70-85
        return score, "BRL under severe pressure"
    elif brl_change_20d >= BRL_WEAK:
        pct = (brl_change_20d - BRL_WEAK) / (BRL_STRESS - BRL_WEAK)
        score = 55 + (pct * 15)  # 55-70
        return score, "BRL weakening"
    elif brl_change_20d >= BRL_STRONG:
        return 45, "BRL stable"
    elif brl_change_20d >= BRL_BOOM:
        pct = (BRL_STRONG - brl_change_20d) / (BRL_STRONG - BRL_BOOM)
        score = 45 - (pct * 15)  # 30-45
        return score, "BRL firming"
    else:
        return 25, "BRL very strong"


def score_es_zn_corr(correlation: float) -> Tuple[float, str]:
    """
    Score ES-ZN correlation.

    Normally negative. Positive = stress (both selling).
    Returns (score, description).
    """
    if correlation >= ES_ZN_PANIC:
        return 90, "Extreme correlation - panic selling"
    elif correlation >= ES_ZN_STRESS:
        pct = (correlation - ES_ZN_STRESS) / (ES_ZN_PANIC - ES_ZN_STRESS)
        score = 70 + (pct * 20)  # 70-90
        return score, "Correlation elevated - stress"
    elif correlation >= 0:
        return 60, "Correlation flattening - transitioning"
    elif correlation >= ES_ZN_NORMAL:
        return 45, "Normal diversification"
    elif correlation >= ES_ZN_HEALTHY:
        return 30, "Healthy diversification"
    else:
        return 20, "Strong diversification - risk-on"


def score_es_gc_corr(correlation: float) -> Tuple[float, str]:
    """
    Score ES-GC correlation.

    Negative correlation = flight to safety (risk-off).
    Positive correlation = risk-on.
    """
    if correlation <= -0.30:
        return 80, "Gold acting as strong safe haven"
    elif correlation <= -0.15:
        return 65, "Gold hedging equity risk"
    elif correlation <= 0.05:
        return 50, "Gold neutral vs equities"
    elif correlation <= 0.20:
        return 35, "Gold moving with equities"
    else:
        return 25, "Risk-on correlation (gold not hedging)"


def score_dxy_strength(change_20d: float) -> Tuple[float, str]:
    """
    Score DXY strength.

    USD rally = risk-off (higher score).
    USD selloff = risk-on (lower score).
    """
    if change_20d >= DXY_RALLY:
        return 80, "USD rallying (risk-off)"
    elif change_20d >= 0.01:
        return 65, "USD firming"
    elif change_20d > -0.01:
        return 50, "USD stable"
    elif change_20d > DXY_SELLOFF:
        return 35, "USD softening"
    else:
        return 20, "USD weakening (risk-on)"


def calculate_trade_pressure(conn, as_of_date: Optional[date] = None) -> Dict:
    """
    Calculate Trade Pressure.

    Components:
    1. Shipping (BDIY) 35%: Global trade proxy
    2. Brazil FX (BRL) 25%: Competitor currency
    3. China Specialist 25%: China demand
    4. Trade News 15%: Headlines

    Returns PressureReading-compatible dict.
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # ==== 1. SHIPPING (BDIY from FRED) ====
    cur.execute(
        """
        SELECT event_date, value FROM econ.commodities_1d
        WHERE series_id = 'BDIY' AND event_date <= %s AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 25
    """,
        (as_of_date,),
    )
    bdiy_data = cur.fetchall()
    if len(bdiy_data) < 21:
        raise ValueError("Insufficient BDIY data to compute shipping stress")

    current_bdiy = float(bdiy_data[0][1])
    bdiy_20d = float(bdiy_data[20][1])
    bdiy_change_20d = (current_bdiy - bdiy_20d) / bdiy_20d if bdiy_20d > 0 else 0

    shipping_score, shipping_desc = score_shipping(bdiy_change_20d)
    components["shipping_score"] = round(shipping_score, 1)
    components["bdiy_change_20d"] = round(bdiy_change_20d * 100, 2)

    # ==== 2. BRAZIL FX ====
    cur.execute(
        """
        SELECT event_date, value FROM econ.rates_1d
        WHERE series_id = 'DEXBZUS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 21
    """,
        (as_of_date,),
    )
    brl_data = cur.fetchall()

    brl_score = 50
    if len(brl_data) >= 20:
        brl_values = [float(r[1]) for r in brl_data if r[1] is not None]
        brl_change = (
            (brl_values[0] - brl_values[-1]) / brl_values[-1]
            if brl_values[-1] > 0
            else 0
        )
        brl_score, brl_desc = score_brl_stress(brl_change)
        components["brl_score"] = round(brl_score, 1)
        components["brl_change_20d"] = round(brl_change * 100, 2)

    # ==== 3. CHINA SPECIALIST ====
    cur.execute(
        """
        SELECT signal_1, confidence
        FROM training.specialist_signals_1d
        WHERE bucket = 'china' AND as_of_date <= %s
        ORDER BY as_of_date DESC LIMIT 1
    """,
        (as_of_date,),
    )
    china_signal = cur.fetchone()

    china_score = 50
    if china_signal and china_signal[0] is not None:
        signal_val = float(china_signal[0])
        confidence = float(china_signal[1]) if china_signal[1] else 0.5
        # Negative signal = bearish China = trade stress
        china_score = 50 - (signal_val * 40 * confidence)
        china_score = float(np.clip(china_score, 0, 100))
        components["china_score"] = round(china_score, 1)

    # ==== 4. TRADE NEWS ====
    try:
        cur.execute(
            """
            SELECT COUNT(*) FROM alt.profarmer_news_event
            WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s
            AND (headline ILIKE '%%trade%%' OR headline ILIKE '%%export%%' OR
                 headline ILIKE '%%china%%' OR headline ILIKE '%%brazil%%')
        """,
            (as_of_date, as_of_date),
        )
        news_count = cur.fetchone()[0] or 0
    except Exception:
        news_count = 0

    news_score = min(100, 30 + (news_count * 5))
    components["news_score"] = round(news_score, 1)
    components["trade_news_count"] = news_count

    # ==== COMPOSITE ====
    score = (
        (shipping_score * 0.35)
        + (brl_score * 0.25)
        + (china_score * 0.25)
        + (news_score * 0.15)
    )
    score = float(np.clip(score, 0, 100))

    # ==== REGIME ====
    if score >= 70:
        regime = "disrupted"
    elif score >= 55:
        regime = "stressed"
    elif score >= 40:
        regime = "normal"
    elif score >= 25:
        regime = "strong"
    else:
        regime = "booming"

    regime_info = TRADE_REGIMES.get(regime, TRADE_REGIMES["normal"])

    # ==== NARRATIVE ====
    if score >= 70:
        headline = "Trade Flows Disrupted"
    elif score >= 55:
        headline = "Trade Showing Strain"
    elif score >= 40:
        headline = "Normal Trade Flows"
    else:
        headline = "Strong Trade Activity"

    narrative = f"{regime_info.description} {regime_info.ag_impact}"

    drivers = []
    if shipping_score >= 60:
        drivers.append("Weak shipping rates")
    if brl_score >= 60:
        drivers.append("BRL weakness")
    if china_score >= 60:
        drivers.append("Bearish China signals")
    if not drivers:
        drivers.append("Trade flows stable")

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
        "name": "Trade Pressure",
        "score": round(score, 1),
        "level": level,
        "trend": "Stable",  # Would need more data for momentum
        "headline": headline,
        "narrative": narrative,
        "key_drivers": drivers,
        "color": color,
        "icon": "truck",
        "sparkline": [50] * 10,  # Placeholder
        "percentile_30d": round(score, 1),
        "percentile_1y": round(score, 1),
        "regime": regime,
        "momentum": 0.0,
        "as_of_date": as_of_date.isoformat(),
        "components": components,
        "domain_context": {
            "regime_name": regime_info.name,
            "regime_description": regime_info.description,
            "ag_impact": regime_info.ag_impact,
        },
    }


def calculate_correlation_pressure(conn, as_of_date: Optional[date] = None) -> Dict:
    """
    Calculate Correlation Pressure (risk-on/risk-off).

    Components:
    1. ES-ZN Correlation 45%: Equity-bond correlation
    2. ES-GC Correlation 30%: Safe haven demand
    3. DXY Strength 25%: USD as risk barometer

    Returns PressureReading-compatible dict.
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # ==== 1. ES-ZN + ES-GC CORRELATIONS (futures) ====
    cur.execute(
        """
        SELECT event_date,
               MAX(CASE WHEN symbol = 'ES' THEN close END) AS es_close,
               MAX(CASE WHEN symbol = 'ZN' THEN close END) AS zn_close,
               MAX(CASE WHEN symbol = 'GC' THEN close END) AS gc_close
        FROM mkt.futures_1d
        WHERE symbol IN ('ES', 'ZN', 'GC') AND event_date <= %s AND close IS NOT NULL
        GROUP BY event_date
        ORDER BY event_date DESC LIMIT 100
    """,
        (as_of_date,),
    )
    corr_rows = cur.fetchall()
    if len(corr_rows) < 30:
        raise ValueError("Insufficient futures data for correlation pressure")

    corr_rows = list(reversed(corr_rows))
    aligned = [
        (r[1], r[2], r[3])
        for r in corr_rows
        if r[1] is not None and r[2] is not None and r[3] is not None
    ]
    if len(aligned) < 30:
        raise ValueError("Insufficient aligned futures data for correlation pressure")

    es = np.array([r[0] for r in aligned], dtype=float)
    zn = np.array([r[1] for r in aligned], dtype=float)
    gc = np.array([r[2] for r in aligned], dtype=float)

    # Returns
    es_ret = np.diff(es) / es[:-1]
    zn_ret = np.diff(zn) / zn[:-1]
    gc_ret = np.diff(gc) / gc[:-1]

    window = min(63, len(es_ret), len(zn_ret), len(gc_ret))
    if window < 30:
        raise ValueError("Insufficient futures return history for correlation pressure")

    es_zn_corr = float(np.corrcoef(es_ret[-window:], zn_ret[-window:])[0, 1])
    es_gc_corr = float(np.corrcoef(es_ret[-window:], gc_ret[-window:])[0, 1])

    es_zn_score, es_zn_desc = score_es_zn_corr(es_zn_corr)
    es_gc_score, es_gc_desc = score_es_gc_corr(es_gc_corr)

    components["es_zn_score"] = round(es_zn_score, 1)
    components["es_zn_corr"] = round(es_zn_corr, 3)
    components["es_gc_score"] = round(es_gc_score, 1)
    components["es_gc_corr"] = round(es_gc_corr, 3)

    # ==== 3. DXY STRENGTH (FRED DXY index) ====
    cur.execute(
        """
        SELECT event_date, value FROM econ.activity_1d
        WHERE series_id = 'DXY' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 25
    """,
        (as_of_date,),
    )
    dxy_data = cur.fetchall()
    if len(dxy_data) < 21:
        raise ValueError("Insufficient DXY data for correlation pressure")

    current_dxy = float(dxy_data[0][1])
    dxy_20d = float(dxy_data[20][1])
    dxy_change_20d = (current_dxy - dxy_20d) / dxy_20d if dxy_20d > 0 else 0
    dxy_score, dxy_desc = score_dxy_strength(dxy_change_20d)
    components["dxy_score"] = round(dxy_score, 1)
    components["dxy_change_20d"] = round(dxy_change_20d * 100, 2)

    # ==== COMPOSITE ====
    score = (es_zn_score * 0.45) + (es_gc_score * 0.30) + (dxy_score * 0.25)
    score = float(np.clip(score, 0, 100))

    # ==== REGIME ====
    if score >= 70:
        regime = "risk_off"
    elif score >= 55:
        regime = "transitioning"
    elif score >= 40:
        regime = "normal"
    else:
        regime = "risk_on"

    regime_info = CORRELATION_REGIMES.get(regime, CORRELATION_REGIMES["normal"])

    # ==== NARRATIVE ====
    if score >= 70:
        headline = "Risk-Off Regime Active"
    elif score >= 55:
        headline = "Correlations Rising"
    elif score >= 40:
        headline = "Normal Market Structure"
    else:
        headline = "Risk-On Environment"

    narrative = f"{regime_info.description} {regime_info.positioning}"

    drivers = []
    if es_zn_score >= 60:
        drivers.append(f"ES-ZN correlation elevated ({es_zn_corr:.2f})")
    if es_gc_score >= 60:
        drivers.append("Gold acting as safe haven")
    if dxy_score >= 60:
        drivers.append("Dollar strengthening")
    if not drivers:
        drivers.append("Normal diversification")

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
        "name": "Correlation Pressure",
        "score": round(score, 1),
        "level": level,
        "trend": "Stable",
        "headline": headline,
        "narrative": narrative,
        "key_drivers": drivers,
        "color": color,
        "icon": "git-merge",
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
            "positioning": regime_info.positioning,
        },
    }
