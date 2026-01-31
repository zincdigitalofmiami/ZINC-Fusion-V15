"""
ZINC-FUSION-V15: Volatility Pressure Calculator

Domain-specific pressure gauge for market volatility stress.
Uses VIX term structure, realized vs implied dynamics, and cross-asset vol.

VIX Level Thresholds (absolute, not percentile):
- < 12: COMPLACENT - Historically precedes spikes. False calm.
- 12-15: LOW VOL - Benign environment, risk-on
- 15-20: NORMAL - Typical market conditions
- 20-25: ELEVATED - Markets concerned but not panicking
- 25-30: HIGH - Significant fear, hedging demand
- 30-40: FEAR - Panic building, large swings expected
- > 40: EXTREME FEAR - Crisis mode (2008, 2020 COVID)

VIX Term Structure (VIX vs VIX3M):
- Contango (VIX < VIX3M): Normal, orderly markets
- Flat (VIX ≈ VIX3M): Transitioning, watch closely
- Backwardation (VIX > VIX3M): Panic, near-term fear exceeds long-term

OVX (Oil Volatility):
- < 25: Calm energy markets
- 25-35: Normal
- 35-50: Elevated (supply concerns, geopolitical)
- > 50: Crisis (war, embargo, major disruption)

Realized vs Implied Gap:
- VIX >> Realized: Markets pricing in future shock
- VIX << Realized: Complacency, often precedes vol spike
- Gap > 5pts: Significant divergence worth noting

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
# DOMAIN CONSTANTS - VIX Term Structure Expertise
# ==============================================================================

# VIX absolute levels (these are fixed thresholds, not percentiles)
VIX_COMPLACENT = 12.0      # Dangerously low
VIX_LOW = 15.0             # Low but stable
VIX_NORMAL = 20.0          # Normal trading
VIX_ELEVATED = 25.0        # Concerns building
VIX_HIGH = 30.0            # Fear
VIX_EXTREME = 40.0         # Panic

# VIX term structure thresholds (VIX / VIX3M ratio)
TERM_HEALTHY_CONTANGO = 0.85   # Strong contango - very orderly
TERM_NORMAL_CONTANGO = 0.92    # Normal contango
TERM_FLAT = 1.00               # Flat curve
TERM_BACKWARDATION = 1.05      # Mild backwardation - stress
TERM_SEVERE_BACKWARDATION = 1.15  # Severe - panic

# OVX (Oil Volatility Index) thresholds
OVX_LOW = 25.0
OVX_NORMAL = 35.0
OVX_ELEVATED = 50.0
OVX_EXTREME = 70.0

# Realized volatility context (annualized ZL volatility)
ZL_VOL_LOW = 0.18          # 18% - calm
ZL_VOL_NORMAL = 0.28       # 28% - typical
ZL_VOL_ELEVATED = 0.38     # 38% - active
ZL_VOL_HIGH = 0.50         # 50% - volatile
ZL_VOL_EXTREME = 0.70      # 70% - extreme


@dataclass
class VolRegime:
    """Volatility regime classification."""
    name: str
    description: str
    trading_implication: str
    typical_duration: str


VOL_REGIMES = {
    "complacent": VolRegime(
        name="Complacent",
        description="VIX below 12 signals extreme complacency. Historically precedes volatility spikes.",
        trading_implication="Low option premiums but elevated spike risk. Consider tail hedges.",
        typical_duration="Days to weeks before mean reversion"
    ),
    "low_vol": VolRegime(
        name="Low Volatility",
        description="Benign market environment with orderly trading.",
        trading_implication="Risk-on positioning works. Option selling strategies attractive.",
        typical_duration="Can persist for months"
    ),
    "normal": VolRegime(
        name="Normal",
        description="Typical market volatility. Neither complacent nor stressed.",
        trading_implication="Standard trading conditions. Volatility fairly priced.",
        typical_duration="Baseline regime"
    ),
    "elevated": VolRegime(
        name="Elevated",
        description="Markets showing concern but not panicking. Hedging demand rising.",
        trading_implication="Tighten stops. Consider reducing position sizes.",
        typical_duration="Weeks - transitional regime"
    ),
    "high_vol": VolRegime(
        name="High Volatility",
        description="Significant market fear. Large daily swings expected.",
        trading_implication="Reduce leverage. Widen stops or step aside.",
        typical_duration="Days to weeks of elevated activity"
    ),
    "fear": VolRegime(
        name="Fear",
        description="Panic levels. VIX 30-40 indicates crisis mentality.",
        trading_implication="Expect gap moves. Liquidity can evaporate. Cash is a position.",
        typical_duration="Days - acute stress"
    ),
    "extreme_fear": VolRegime(
        name="Extreme Fear",
        description="Crisis mode (VIX > 40). 2008, 2020 COVID-style panic.",
        trading_implication="Survival mode. These levels historically mark bottoms but timing is treacherous.",
        typical_duration="Hours to days at peak"
    )
}


def score_vix_level(vix: float) -> Tuple[float, str]:
    """
    Score VIX using absolute thresholds (not percentiles).

    Returns (score, regime_key).
    Higher score = more volatility pressure.
    """
    if vix < VIX_COMPLACENT:
        # Very low VIX is actually concerning (complacency)
        # Score 15-25: low but with warning
        return 20, "complacent"

    elif vix < VIX_LOW:
        # 12-15: Low vol
        pct = (vix - VIX_COMPLACENT) / (VIX_LOW - VIX_COMPLACENT)
        score = 15 + (pct * 10)  # 15-25
        return score, "low_vol"

    elif vix < VIX_NORMAL:
        # 15-20: Normal
        pct = (vix - VIX_LOW) / (VIX_NORMAL - VIX_LOW)
        score = 25 + (pct * 20)  # 25-45
        return score, "normal"

    elif vix < VIX_ELEVATED:
        # 20-25: Elevated
        pct = (vix - VIX_NORMAL) / (VIX_ELEVATED - VIX_NORMAL)
        score = 45 + (pct * 15)  # 45-60
        return score, "elevated"

    elif vix < VIX_HIGH:
        # 25-30: High
        pct = (vix - VIX_ELEVATED) / (VIX_HIGH - VIX_ELEVATED)
        score = 60 + (pct * 15)  # 60-75
        return score, "high_vol"

    elif vix < VIX_EXTREME:
        # 30-40: Fear
        pct = (vix - VIX_HIGH) / (VIX_EXTREME - VIX_HIGH)
        score = 75 + (pct * 15)  # 75-90
        return score, "fear"

    else:
        # > 40: Extreme
        excess = min(20, vix - VIX_EXTREME)
        score = 90 + (excess / 2)  # 90-100
        return min(100, score), "extreme_fear"


def score_term_structure(vix: float, vix3m: float) -> Tuple[float, str]:
    """
    Score VIX term structure.

    Returns (adjustment, description).
    Backwardation adds pressure; steep contango reduces it.
    """
    if vix3m == 0:
        return 0, "No term structure data"

    ratio = vix / vix3m

    if ratio < TERM_HEALTHY_CONTANGO:
        return -15, "Steep contango - very orderly markets"
    elif ratio < TERM_NORMAL_CONTANGO:
        return -8, "Normal contango"
    elif ratio < TERM_FLAT:
        return -3, "Mild contango"
    elif ratio < TERM_BACKWARDATION:
        return 5, "Flat to slight backwardation"
    elif ratio < TERM_SEVERE_BACKWARDATION:
        return 15, "Backwardation - near-term stress"
    else:
        return 25, "Severe backwardation - panic mode"


def score_ovx(ovx: float) -> Tuple[float, str]:
    """
    Score oil volatility (OVX).

    Energy volatility often leads broad market stress.
    Returns (adjustment, description).
    """
    if ovx < OVX_LOW:
        return -5, "Calm energy markets"
    elif ovx < OVX_NORMAL:
        return 0, "Normal oil volatility"
    elif ovx < OVX_ELEVATED:
        pct = (ovx - OVX_NORMAL) / (OVX_ELEVATED - OVX_NORMAL)
        adj = pct * 12
        return adj, "Elevated oil volatility"
    elif ovx < OVX_EXTREME:
        pct = (ovx - OVX_ELEVATED) / (OVX_EXTREME - OVX_ELEVATED)
        adj = 12 + (pct * 10)
        return adj, "High oil volatility"
    else:
        return 25, "Extreme oil volatility"


def score_realized_vol(realized: float, implied_vix: float) -> Tuple[float, str]:
    """
    Score realized ZL volatility and compare to VIX.

    Returns (adjustment, description).
    """
    # Score realized vol level
    if realized < ZL_VOL_LOW:
        level_adj = -5
        level_desc = "Low realized ZL vol"
    elif realized < ZL_VOL_NORMAL:
        level_adj = 0
        level_desc = "Normal realized ZL vol"
    elif realized < ZL_VOL_ELEVATED:
        level_adj = 8
        level_desc = "Elevated realized ZL vol"
    elif realized < ZL_VOL_HIGH:
        level_adj = 15
        level_desc = "High realized ZL vol"
    else:
        level_adj = 20
        level_desc = "Extreme realized ZL vol"

    # Compare to VIX (rough proxy for implied vs realized)
    # VIX is equity vol, but directionally useful
    vix_as_decimal = implied_vix / 100  # VIX 20 = 20%

    gap = realized - vix_as_decimal
    if gap > 0.15:
        gap_adj = 8  # Realized >> implied: vol underpriced
        gap_desc = f"{level_desc}; realized exceeds implied"
    elif gap < -0.10:
        gap_adj = -3  # Realized << implied: priced for shock
        gap_desc = f"{level_desc}; implied elevated vs realized"
    else:
        gap_adj = 0
        gap_desc = level_desc

    return level_adj + gap_adj, gap_desc


def generate_vol_narrative(
    vix: float,
    vix3m: float,
    ovx: float,
    realized: Optional[float],
    score: float,
    regime: str
) -> Tuple[str, str, List[str]]:
    """
    Generate domain-expert narrative for volatility pressure.

    Returns (headline, story, key_drivers).
    """
    regime_info = VOL_REGIMES.get(regime, VOL_REGIMES["normal"])

    # Headline based on VIX level
    if vix >= 40:
        headline = "Extreme Market Fear"
    elif vix >= 30:
        headline = "Markets in Panic Mode"
    elif vix >= 25:
        headline = "Volatility Spiking"
    elif vix >= 20:
        headline = "Elevated Market Anxiety"
    elif vix >= 15:
        headline = "Normal Volatility Conditions"
    elif vix >= 12:
        headline = "Low Volatility Environment"
    else:
        headline = "Extreme Complacency Warning"

    # Build narrative
    parts = []

    # VIX context
    parts.append(f"VIX at {vix:.1f} indicates {regime_info.name.lower()} conditions.")

    # Term structure
    if vix3m and vix3m > 0:
        ratio = vix / vix3m
        if ratio > 1.05:
            parts.append(f"Term structure is inverted (VIX/VIX3M = {ratio:.2f}), signaling near-term panic.")
        elif ratio < 0.90:
            parts.append(f"Healthy contango (VIX/VIX3M = {ratio:.2f}) indicates orderly markets.")

    # Trading implication
    parts.append(regime_info.trading_implication)

    narrative = " ".join(parts)

    # Key drivers
    drivers = []

    if vix >= 25:
        drivers.append(f"VIX at {vix:.0f}")
    elif vix < 13:
        drivers.append(f"VIX at historic lows ({vix:.1f})")

    if vix3m and vix / vix3m > 1.05:
        drivers.append("Inverted VIX term structure")

    if ovx and ovx >= 40:
        drivers.append(f"OVX elevated ({ovx:.0f})")

    if realized and realized > ZL_VOL_ELEVATED:
        drivers.append(f"High realized ZL vol ({realized*100:.0f}%)")

    if not drivers:
        drivers.append("Volatility in normal range")

    return headline, narrative, drivers


def calculate_volatility_pressure(conn, as_of_date: Optional[date] = None) -> Dict:
    """
    Calculate Volatility Pressure using VIX term structure expertise.

    Components:
    1. VIX Level (45%): Absolute level scoring
    2. Term Structure (25%): VIX vs VIX3M
    3. OVX (15%): Energy volatility
    4. Realized ZL Vol (15%): Actual soyoil volatility

    Returns PressureReading-compatible dict.
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # ==== VIX ====
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'VIXCLS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 252
    """, (as_of_date,))
    vix_data = cur.fetchall()

    current_vix = 20.0  # Default
    vix_values = []
    if vix_data:
        current_vix = float(vix_data[0][1])
        vix_values = [float(r[1]) for r in vix_data if r[1] is not None]

    # ==== VIX3M (term structure) ====
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'VIX3M' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 1
    """, (as_of_date,))
    vix3m_row = cur.fetchone()
    current_vix3m = float(vix3m_row[1]) if vix3m_row else None

    # ==== OVX ====
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'OVXCLS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 1
    """, (as_of_date,))
    ovx_row = cur.fetchone()
    current_ovx = float(ovx_row[1]) if ovx_row else None

    # ==== Realized ZL Volatility ====
    cur.execute("""
        WITH returns AS (
            SELECT event_date, close,
                   (close - LAG(close) OVER (ORDER BY event_date)) /
                   NULLIF(LAG(close) OVER (ORDER BY event_date), 0) as ret
            FROM analytics.zl_price_1d
            WHERE event_date <= %s
            ORDER BY event_date DESC
            LIMIT 63
        )
        SELECT STDDEV(ret) * SQRT(252) as realized_vol FROM returns WHERE ret IS NOT NULL
    """, (as_of_date,))
    rv_result = cur.fetchone()
    realized_vol = float(rv_result[0]) if rv_result and rv_result[0] else None

    # ==== Vol Specialist Signal ====
    cur.execute("""
        SELECT signal_1, confidence
        FROM training.specialist_signals_1d
        WHERE bucket = 'volatility' AND as_of_date <= %s
        ORDER BY as_of_date DESC LIMIT 1
    """, (as_of_date,))
    vol_signal = cur.fetchone()

    # ==== SCORING ====

    # Component 1: VIX Level (45%)
    vix_score, regime = score_vix_level(current_vix)
    components["vix_level"] = round(vix_score, 1)
    components["vix_value"] = round(current_vix, 1)

    # Component 2: Term Structure (25%)
    term_adj, term_desc = (0, "No data")
    if current_vix3m:
        term_adj, term_desc = score_term_structure(current_vix, current_vix3m)
        components["term_structure"] = round(term_adj, 1)
        components["vix3m_value"] = round(current_vix3m, 1)
        components["vix_ratio"] = round(current_vix / current_vix3m, 3)

    # Component 3: OVX (15%)
    ovx_adj, ovx_desc = (0, "No data")
    if current_ovx:
        ovx_adj, ovx_desc = score_ovx(current_ovx)
        components["ovx_adjustment"] = round(ovx_adj, 1)
        components["ovx_value"] = round(current_ovx, 1)

    # Component 4: Realized Vol (15%)
    rv_adj, rv_desc = (0, "No data")
    if realized_vol:
        rv_adj, rv_desc = score_realized_vol(realized_vol, current_vix)
        components["realized_vol"] = round(rv_adj, 1)
        components["realized_vol_value"] = round(realized_vol * 100, 1)

    # Component 5: Specialist overlay
    signal_adj = 0
    if vol_signal and vol_signal[0] is not None:
        signal_val = float(vol_signal[0])
        confidence = float(vol_signal[1]) if vol_signal[1] else 0.5
        # Positive signal = high vol expected = more pressure
        signal_adj = signal_val * 10 * confidence
        components["specialist_signal"] = round(signal_adj, 1)

    # ==== COMPOSITE SCORE ====
    # Weights: VIX 45%, Term 25%, OVX 15%, Realized 15%
    score = vix_score
    score += term_adj * (25/45)
    score += ovx_adj * (15/45)
    score += rv_adj * (15/45)
    score += signal_adj * (10/45)

    score = float(np.clip(score, 0, 100))

    # ==== SPARKLINE ====
    sparkline = []
    for row in reversed(vix_data[:10]):
        hist_vix = float(row[1])
        hist_score, _ = score_vix_level(hist_vix)
        sparkline.append(hist_score)

    # ==== MOMENTUM ====
    if len(sparkline) >= 5:
        recent = np.mean(sparkline[-3:])
        earlier = np.mean(sparkline[:3])
        momentum = (recent - earlier) / max(abs(earlier), 1)
        momentum = float(np.clip(momentum, -1, 1))
    else:
        momentum = 0.0

    # ==== TREND ====
    if momentum > 0.15:
        trend = "Surging"
    elif momentum > 0.05:
        trend = "Rising"
    elif momentum < -0.15:
        trend = "Plunging"
    elif momentum < -0.05:
        trend = "Falling"
    else:
        trend = "Stable"

    # ==== LEVEL CLASSIFICATION ====
    if score >= 80:
        level = "Extreme Pressure"
        color = "#DC2626"
    elif score >= 65:
        level = "High Pressure"
        color = "#EA580C"
    elif score >= 50:
        level = "Elevated"
        color = "#D97706"
    elif score >= 35:
        level = "Normal"
        color = "#65A30D"
    elif score >= 20:
        level = "Low Pressure"
        color = "#0891B2"
    else:
        level = "Very Low"
        color = "#0284C7"

    # ==== NARRATIVE ====
    headline, narrative, drivers = generate_vol_narrative(
        current_vix, current_vix3m, current_ovx, realized_vol, score, regime
    )

    return {
        "name": "Volatility Pressure",
        "score": round(score, 1),
        "level": level,
        "trend": trend,
        "headline": headline,
        "narrative": narrative,
        "key_drivers": drivers,
        "color": color,
        "icon": "activity",
        "sparkline": [round(v, 1) for v in sparkline],
        "percentile_30d": round(score, 1),
        "percentile_1y": round(score, 1),
        "regime": regime,
        "momentum": round(momentum, 3),
        "as_of_date": as_of_date.isoformat(),
        "components": components,
        "domain_context": {
            "regime_name": VOL_REGIMES.get(regime, VOL_REGIMES["normal"]).name,
            "regime_description": VOL_REGIMES.get(regime, VOL_REGIMES["normal"]).description,
            "trading_implication": VOL_REGIMES.get(regime, VOL_REGIMES["normal"]).trading_implication,
            "term_structure_assessment": term_desc if current_vix3m else "No VIX3M data",
            "ovx_assessment": ovx_desc if current_ovx else "No OVX data",
            "realized_assessment": rv_desc if realized_vol else "No realized vol data",
        }
    }
