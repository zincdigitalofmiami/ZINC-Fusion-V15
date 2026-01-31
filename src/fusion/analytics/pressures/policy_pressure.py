"""
ZINC-FUSION-V15: Policy Pressure Calculators

Domain-specific gauges for policy-related uncertainty.
Uses Baker-Bloom-Davis EPU/TPU indices with proper calibration.

EPU (Economic Policy Uncertainty Index):
- Created by Baker, Bloom, Davis (Stanford/Chicago)
- Based on newspaper coverage of policy-related economic uncertainty
- Base = 100 (historical average)
- Components: news coverage, tax code expiration, forecaster disagreement

EPU Absolute Thresholds (not percentiles):
- < 80: Unusually calm policy environment
- 80-120: Low uncertainty - stable policy outlook
- 120-180: Normal policy uncertainty
- 180-300: Elevated - significant policy debates
- 300-500: High - major policy upheaval
- > 500: Crisis-level (COVID, major elections, wars)

TPU (Trade Policy Uncertainty):
- Subset of EPU focused on trade/tariff news
- More volatile, spikes during trade negotiations/disputes

TPU Thresholds:
- < 40: Trade policy calm
- 40-100: Normal trade uncertainty
- 100-200: Elevated tariff risk
- 200-400: High uncertainty (active tariff threats)
- > 400: Trade war mode (2018-2019 US-China peak)

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
# EPU THRESHOLDS (Baker-Bloom-Davis calibration)
# ==============================================================================

EPU_VERY_LOW = 80       # Unusually calm
EPU_LOW = 120           # Stable policy
EPU_NORMAL = 180        # Typical
EPU_ELEVATED = 300      # Significant debates
EPU_HIGH = 500          # Major upheaval
EPU_CRISIS = 700        # Crisis mode

# ==============================================================================
# TPU (Trade Policy Uncertainty) THRESHOLDS
# ==============================================================================

TPU_CALM = 40           # Trade calm
TPU_NORMAL = 100        # Normal uncertainty
TPU_ELEVATED = 200      # Tariff threats
TPU_HIGH = 400          # Active tariff war
TPU_EXTREME = 700       # 2018-2019 peak levels


@dataclass
class PolicyRegime:
    """Policy uncertainty regime."""
    name: str
    description: str
    market_impact: str
    typical_triggers: str


TRUMP_EFFECT_REGIMES = {
    "stable_policy": PolicyRegime(
        name="Stable Policy Environment",
        description="Low policy uncertainty. Markets have clarity on regulatory direction.",
        market_impact="Risk assets favored. Low volatility premiums.",
        typical_triggers="Consistent messaging, bipartisan consensus, minimal executive actions."
    ),
    "normal_noise": PolicyRegime(
        name="Normal Policy Noise",
        description="Typical policy uncertainty. Some debates but no major disruptions.",
        market_impact="Standard pricing of policy risk. Watch for catalyst events.",
        typical_triggers="Ongoing legislative debates, routine executive actions."
    ),
    "elevated_uncertainty": PolicyRegime(
        name="Elevated Uncertainty",
        description="Significant policy-driven market concern. Headlines impacting positioning.",
        market_impact="Risk premiums rising. Hedging activity increasing.",
        typical_triggers="Major executive orders, regulatory proposals, international disputes."
    ),
    "high_uncertainty": PolicyRegime(
        name="High Policy Uncertainty",
        description="Major policy uncertainty. Markets struggling to price outcomes.",
        market_impact="Elevated vol across assets. Flight to quality. Reduced risk-taking.",
        typical_triggers="Trade war escalation, major tariff announcements, regulatory overhauls."
    ),
    "policy_crisis": PolicyRegime(
        name="Policy Crisis Mode",
        description="Crisis-level uncertainty. Policy outcomes highly unpredictable.",
        market_impact="Extreme volatility. Liquidity concerns. Risk-off dominates.",
        typical_triggers="Constitutional crises, major international conflicts, pandemic response."
    )
}

TARIFF_REGIMES = {
    "trade_calm": PolicyRegime(
        name="Trade Calm",
        description="No active tariff threats. Trade policy predictable.",
        market_impact="Global trade flows normal. Supply chains stable.",
        typical_triggers="Existing trade agreements stable, no new disputes."
    ),
    "normal_uncertainty": PolicyRegime(
        name="Normal Trade Uncertainty",
        description="Some trade policy noise but no imminent threats.",
        market_impact="Manageable trade risk. Pricing stable.",
        typical_triggers="Ongoing negotiations, routine trade reviews."
    ),
    "tariff_threats": PolicyRegime(
        name="Active Tariff Threats",
        description="Tariff threats being made. Markets pricing potential action.",
        market_impact="Ag commodities volatile. Supply chain concerns rising.",
        typical_triggers="Trade war rhetoric, specific tariff proposals."
    ),
    "tariff_war": PolicyRegime(
        name="Tariff War Mode",
        description="Active tariff implementation. Retaliatory measures in place.",
        market_impact="Major trade disruption. Export demand at risk.",
        typical_triggers="Implemented tariffs, retaliatory duties, trade barriers."
    ),
    "extreme_disruption": PolicyRegime(
        name="Extreme Trade Disruption",
        description="Maximum tariff uncertainty. Trade flows severely impacted.",
        market_impact="Critical supply chain issues. Ag exports collapsed.",
        typical_triggers="Full-scale trade war, embargo-level actions."
    )
}


def score_epu(epu_value: float) -> Tuple[float, str]:
    """
    Score EPU using Baker-Bloom-Davis calibrated thresholds.

    Returns (score, regime_key) where higher = more uncertainty pressure.
    """
    if epu_value < EPU_VERY_LOW:
        # Below 80 - unusually calm (actually somewhat concerning - complacency)
        return 15, "stable_policy"

    elif epu_value < EPU_LOW:
        # 80-120 - low uncertainty
        pct = (epu_value - EPU_VERY_LOW) / (EPU_LOW - EPU_VERY_LOW)
        score = 15 + (pct * 15)  # 15-30
        return score, "stable_policy"

    elif epu_value < EPU_NORMAL:
        # 120-180 - normal
        pct = (epu_value - EPU_LOW) / (EPU_NORMAL - EPU_LOW)
        score = 30 + (pct * 20)  # 30-50
        return score, "normal_noise"

    elif epu_value < EPU_ELEVATED:
        # 180-300 - elevated
        pct = (epu_value - EPU_NORMAL) / (EPU_ELEVATED - EPU_NORMAL)
        score = 50 + (pct * 15)  # 50-65
        return score, "elevated_uncertainty"

    elif epu_value < EPU_HIGH:
        # 300-500 - high
        pct = (epu_value - EPU_ELEVATED) / (EPU_HIGH - EPU_ELEVATED)
        score = 65 + (pct * 15)  # 65-80
        return score, "high_uncertainty"

    elif epu_value < EPU_CRISIS:
        # 500-700 - crisis building
        pct = (epu_value - EPU_HIGH) / (EPU_CRISIS - EPU_HIGH)
        score = 80 + (pct * 12)  # 80-92
        return score, "policy_crisis"

    else:
        # > 700 - full crisis
        excess = min(300, epu_value - EPU_CRISIS)
        score = 92 + (excess / 300) * 8  # 92-100
        return min(100, score), "policy_crisis"


def score_tpu(tpu_value: float) -> Tuple[float, str]:
    """
    Score TPU (Trade Policy Uncertainty) using calibrated thresholds.

    Returns (score, regime_key) where higher = more tariff pressure.
    """
    if tpu_value < TPU_CALM:
        # Below 40 - trade calm
        return 15, "trade_calm"

    elif tpu_value < TPU_NORMAL:
        # 40-100 - normal
        pct = (tpu_value - TPU_CALM) / (TPU_NORMAL - TPU_CALM)
        score = 15 + (pct * 25)  # 15-40
        return score, "normal_uncertainty"

    elif tpu_value < TPU_ELEVATED:
        # 100-200 - elevated
        pct = (tpu_value - TPU_NORMAL) / (TPU_ELEVATED - TPU_NORMAL)
        score = 40 + (pct * 20)  # 40-60
        return score, "tariff_threats"

    elif tpu_value < TPU_HIGH:
        # 200-400 - high
        pct = (tpu_value - TPU_ELEVATED) / (TPU_HIGH - TPU_ELEVATED)
        score = 60 + (pct * 20)  # 60-80
        return score, "tariff_war"

    elif tpu_value < TPU_EXTREME:
        # 400-700 - extreme
        pct = (tpu_value - TPU_HIGH) / (TPU_EXTREME - TPU_HIGH)
        score = 80 + (pct * 12)  # 80-92
        return score, "extreme_disruption"

    else:
        # > 700 - historic levels
        return 95, "extreme_disruption"


def score_executive_velocity(exec_count_7d: int) -> Tuple[float, str]:
    """
    Score executive action velocity.

    Returns (adjustment, description).
    """
    if exec_count_7d == 0:
        return -5, "No executive actions this week"
    elif exec_count_7d <= 2:
        return 0, "Light executive action"
    elif exec_count_7d <= 5:
        return 8, "Moderate executive activity"
    elif exec_count_7d <= 10:
        return 15, "Heavy executive action flow"
    elif exec_count_7d <= 20:
        return 22, "Extremely high executive activity"
    else:
        return 30, "Historic executive action pace"


def score_china_stress(fxi_change_20d: float) -> Tuple[float, str]:
    """
    Score China equity stress via FXI ETF.

    FXI decline often indicates US-China tension or tariff fears.
    Returns (adjustment, description).
    """
    if fxi_change_20d > 0.05:
        return -10, "China equities rallying"
    elif fxi_change_20d > 0:
        return -3, "China equities stable to up"
    elif fxi_change_20d > -0.05:
        return 5, "China equities slightly weak"
    elif fxi_change_20d > -0.10:
        return 12, "China equities under pressure"
    elif fxi_change_20d > -0.15:
        return 18, "China equities selling off"
    else:
        return 25, "China equities in crisis"


def generate_trump_effect_narrative(
    epu_value: float,
    exec_count: int,
    score: float,
    regime: str
) -> Tuple[str, str, List[str]]:
    """Generate narrative for Trump Effect Pressure."""
    regime_info = TRUMP_EFFECT_REGIMES.get(regime, TRUMP_EFFECT_REGIMES["normal_noise"])

    if score >= 80:
        headline = "Major Policy Uncertainty"
    elif score >= 65:
        headline = "Policy Shifts Unsettling Markets"
    elif score >= 50:
        headline = "Elevated Policy Noise"
    elif score >= 35:
        headline = "Moderate Policy Uncertainty"
    else:
        headline = "Stable Policy Environment"

    parts = [
        f"Economic Policy Uncertainty Index at {epu_value:.0f}.",
        regime_info.description,
        regime_info.market_impact
    ]
    narrative = " ".join(parts)

    drivers = []
    if epu_value >= EPU_ELEVATED:
        drivers.append(f"EPU at {epu_value:.0f} (elevated)")
    if exec_count >= 5:
        drivers.append(f"{exec_count} executive actions this week")
    if not drivers:
        drivers.append("Policy environment stable")

    return headline, narrative, drivers


def generate_tariff_narrative(
    tpu_value: float,
    score: float,
    regime: str
) -> Tuple[str, str, List[str]]:
    """Generate narrative for Tariff Pressure."""
    regime_info = TARIFF_REGIMES.get(regime, TARIFF_REGIMES["normal_uncertainty"])

    if score >= 80:
        headline = "Trade War Escalating"
    elif score >= 65:
        headline = "Tariff Threats Active"
    elif score >= 50:
        headline = "Tariff Uncertainty Elevated"
    elif score >= 35:
        headline = "Moderate Trade Policy Noise"
    else:
        headline = "Trade Policy Calm"

    parts = [
        f"Trade Policy Uncertainty Index at {tpu_value:.0f}.",
        regime_info.description,
        regime_info.market_impact
    ]
    narrative = " ".join(parts)

    drivers = []
    if tpu_value >= TPU_ELEVATED:
        drivers.append(f"TPU at {tpu_value:.0f} (elevated)")
    if not drivers:
        drivers.append("Tariff environment calm")

    return headline, narrative, drivers


def calculate_trump_effect_pressure(conn, as_of_date: Optional[date] = None) -> Dict:
    """
    Calculate Trump Effect Pressure using EPU methodology.

    Components:
    1. EPU Index (40%): Baker-Bloom-Davis index
    2. TPU Index (25%): Trade Policy Uncertainty
    3. Executive Velocity (20%): Recent executive actions
    4. China Stress (15%): FXI as proxy for US-China tension

    Returns PressureReading-compatible dict.
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # ==== 1. EPU INDEX ====
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'USEPUINDXD' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 60
    """, (as_of_date,))
    epu_data = cur.fetchall()

    current_epu = 150  # Default
    epu_score = 50
    regime = "normal_noise"

    if epu_data:
        current_epu = float(epu_data[0][1])
        epu_score, regime = score_epu(current_epu)
        components["epu_score"] = round(epu_score, 1)
        components["epu_value"] = round(current_epu, 0)

    # ==== 2. TPU INDEX ====
    cur.execute("""
        SELECT value FROM econ.vol_indices_1d
        WHERE series_id = 'EPUTRADE' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 1
    """, (as_of_date,))
    tpu_row = cur.fetchone()

    tpu_score = 50
    current_tpu = 100
    if tpu_row:
        current_tpu = float(tpu_row[0])
        tpu_score, _ = score_tpu(current_tpu)
        components["tpu_score"] = round(tpu_score, 1)
        components["tpu_value"] = round(current_tpu, 0)

    # ==== 3. EXECUTIVE VELOCITY ====
    cur.execute("""
        SELECT COUNT(*) FROM alt.executive_actions
        WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s
    """, (as_of_date, as_of_date))
    exec_count = cur.fetchone()[0] or 0

    exec_adj, exec_desc = score_executive_velocity(exec_count)
    components["executive_velocity"] = round(exec_adj, 1)
    components["executive_count_7d"] = exec_count

    # ==== 4. CHINA STRESS (FXI) ====
    cur.execute("""
        SELECT event_date, close FROM mkt.etf_1d
        WHERE symbol = 'FXI' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 21
    """, (as_of_date,))
    fxi_data = cur.fetchall()

    china_adj = 0
    if len(fxi_data) >= 20:
        fxi_values = [float(r[1]) for r in fxi_data if r[1] is not None]
        fxi_change = (fxi_values[0] - fxi_values[-1]) / fxi_values[-1] if fxi_values[-1] > 0 else 0
        china_adj, china_desc = score_china_stress(fxi_change)
        components["china_stress"] = round(china_adj, 1)
        components["fxi_change_20d"] = round(fxi_change * 100, 2)

    # ==== 5. SPECIALIST SIGNAL ====
    cur.execute("""
        SELECT signal_1, confidence
        FROM training.specialist_signals_1d
        WHERE bucket = 'trump_effect' AND as_of_date <= %s
        ORDER BY as_of_date DESC LIMIT 1
    """, (as_of_date,))
    signal_row = cur.fetchone()

    signal_adj = 0
    if signal_row and signal_row[0] is not None:
        signal_val = float(signal_row[0])
        confidence = float(signal_row[1]) if signal_row[1] else 0.5
        # Negative signal = bearish = more pressure
        signal_adj = -signal_val * 15 * confidence
        components["specialist_signal"] = round(signal_adj, 1)

    # ==== COMPOSITE SCORE ====
    # Weights: EPU 40%, TPU 25%, Executive 20%, China 15%
    score = (epu_score * 0.40) + (tpu_score * 0.25) + (50 + exec_adj) * 0.20 + (50 + china_adj) * 0.15
    score += signal_adj * 0.10
    score = float(np.clip(score, 0, 100))

    # ==== SPARKLINE ====
    sparkline = []
    for row in reversed(epu_data[:10]):
        hist_epu = float(row[1])
        hist_score, _ = score_epu(hist_epu)
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
    if momentum > 0.10:
        trend = "Uncertainty Rising"
    elif momentum > 0.03:
        trend = "Slight Increase"
    elif momentum < -0.10:
        trend = "Uncertainty Falling"
    elif momentum < -0.03:
        trend = "Slight Decrease"
    else:
        trend = "Stable"

    # ==== LEVEL ====
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
    else:
        level = "Low Pressure"
        color = "#0891B2"

    # ==== NARRATIVE ====
    headline, narrative, drivers = generate_trump_effect_narrative(
        current_epu, exec_count, score, regime
    )

    return {
        "name": "Trump Effect Pressure",
        "score": round(score, 1),
        "level": level,
        "trend": trend,
        "headline": headline,
        "narrative": narrative,
        "key_drivers": drivers,
        "color": color,
        "icon": "flag",
        "sparkline": [round(v, 1) for v in sparkline],
        "percentile_30d": round(score, 1),
        "percentile_1y": round(score, 1),
        "regime": regime,
        "momentum": round(momentum, 3),
        "as_of_date": as_of_date.isoformat(),
        "components": components,
        "domain_context": {
            "regime_name": TRUMP_EFFECT_REGIMES.get(regime, TRUMP_EFFECT_REGIMES["normal_noise"]).name,
            "regime_description": TRUMP_EFFECT_REGIMES.get(regime, TRUMP_EFFECT_REGIMES["normal_noise"]).description,
            "market_impact": TRUMP_EFFECT_REGIMES.get(regime, TRUMP_EFFECT_REGIMES["normal_noise"]).market_impact,
        }
    }


def calculate_tariff_pressure(conn, as_of_date: Optional[date] = None) -> Dict:
    """
    Calculate Tariff Pressure using TPU methodology.

    Components:
    1. TPU Index (45%): Trade Policy Uncertainty
    2. Trade EMV (25%): Equity Market Volatility from trade
    3. Legislation Velocity (15%): Trade-related bills
    4. Specialist Signal (15%): Tariff specialist

    Returns PressureReading-compatible dict.
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # ==== 1. TPU INDEX ====
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'EPUTRADE' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 60
    """, (as_of_date,))
    tpu_data = cur.fetchall()

    current_tpu = 100
    tpu_score = 50
    regime = "normal_uncertainty"

    if tpu_data:
        current_tpu = float(tpu_data[0][1])
        tpu_score, regime = score_tpu(current_tpu)
        components["tpu_score"] = round(tpu_score, 1)
        components["tpu_value"] = round(current_tpu, 0)

    # ==== 2. TRADE EMV ====
    cur.execute("""
        SELECT value FROM econ.vol_indices_1d
        WHERE series_id = 'EMVTRADEPOLEMV' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 1
    """, (as_of_date,))
    emv_row = cur.fetchone()

    emv_score = 50
    if emv_row:
        current_emv = float(emv_row[0])
        # EMV is similar scale to TPU
        emv_score, _ = score_tpu(current_emv)  # Reuse TPU thresholds
        components["emv_score"] = round(emv_score, 1)
        components["emv_value"] = round(current_emv, 0)

    # ==== 3. LEGISLATION VELOCITY ====
    cur.execute("""
        SELECT COUNT(*) FROM alt.legislation_1d
        WHERE event_date >= %s - INTERVAL '14 days' AND event_date <= %s
    """, (as_of_date, as_of_date))
    legis_count = cur.fetchone()[0] or 0

    if legis_count == 0:
        legis_adj = -5
    elif legis_count <= 5:
        legis_adj = 0
    elif legis_count <= 15:
        legis_adj = 10
    elif legis_count <= 30:
        legis_adj = 18
    else:
        legis_adj = 25

    components["legislation"] = round(legis_adj, 1)
    components["legislation_count_14d"] = legis_count

    # ==== 4. TARIFF SPECIALIST ====
    cur.execute("""
        SELECT signal_1, confidence
        FROM training.specialist_signals_1d
        WHERE bucket = 'tariff' AND as_of_date <= %s
        ORDER BY as_of_date DESC LIMIT 1
    """, (as_of_date,))
    signal_row = cur.fetchone()

    signal_adj = 0
    if signal_row and signal_row[0] is not None:
        signal_val = float(signal_row[0])
        confidence = float(signal_row[1]) if signal_row[1] else 0.5
        signal_adj = -signal_val * 20 * confidence
        components["specialist_signal"] = round(signal_adj, 1)

    # ==== COMPOSITE ====
    score = (tpu_score * 0.45) + (emv_score * 0.25) + (50 + legis_adj) * 0.15 + (50 + signal_adj) * 0.15
    score = float(np.clip(score, 0, 100))

    # ==== SPARKLINE ====
    sparkline = []
    for row in reversed(tpu_data[:10]):
        hist_tpu = float(row[1])
        hist_score, _ = score_tpu(hist_tpu)
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
    if momentum > 0.10:
        trend = "Tariff Risk Rising"
    elif momentum > 0.03:
        trend = "Slight Increase"
    elif momentum < -0.10:
        trend = "Tariff Risk Falling"
    elif momentum < -0.03:
        trend = "Slight Decrease"
    else:
        trend = "Stable"

    # ==== LEVEL ====
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
    else:
        level = "Low Pressure"
        color = "#0891B2"

    # ==== NARRATIVE ====
    headline, narrative, drivers = generate_tariff_narrative(current_tpu, score, regime)

    return {
        "name": "Tariff Pressure",
        "score": round(score, 1),
        "level": level,
        "trend": trend,
        "headline": headline,
        "narrative": narrative,
        "key_drivers": drivers,
        "color": color,
        "icon": "shield",
        "sparkline": [round(v, 1) for v in sparkline],
        "percentile_30d": round(score, 1),
        "percentile_1y": round(score, 1),
        "regime": regime,
        "momentum": round(momentum, 3),
        "as_of_date": as_of_date.isoformat(),
        "components": components,
        "domain_context": {
            "regime_name": TARIFF_REGIMES.get(regime, TARIFF_REGIMES["normal_uncertainty"]).name,
            "regime_description": TARIFF_REGIMES.get(regime, TARIFF_REGIMES["normal_uncertainty"]).description,
            "market_impact": TARIFF_REGIMES.get(regime, TARIFF_REGIMES["normal_uncertainty"]).market_impact,
        }
    }
