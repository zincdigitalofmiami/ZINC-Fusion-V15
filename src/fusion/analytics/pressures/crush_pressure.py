"""
ZINC-FUSION-V15: Crush Pressure Calculator

Domain-specific pressure gauge for soybean processor margin stress.
Uses real board crush economics, not generic percentile scoring.

Board Crush Economics:
- Board crush = value of products (meal + oil) minus soybean cost
- 1 bushel soybeans → ~48 lbs meal + ~11 lbs oil
- Processor profitability depends on this spread

Historical Board Crush Ranges ($/bushel):
- < $0.75: DANGER ZONE - negative processor margins, crush cuts imminent
- $0.75 - $1.00: SEVERE STRESS - marginal/negative economics
- $1.00 - $1.25: TIGHT MARGINS - profitable but stressed
- $1.25 - $1.50: NEUTRAL - typical operating margins
- $1.50 - $1.75: HEALTHY - good processor economics
- $1.75 - $2.00: STRONG - encouraging expansion/higher utilization
- > $2.00: EXCEPTIONAL - usually short-lived, attracts competition

Oil Share Dynamics:
- Oil share = SBO value / (SBO value + SBM value)
- Historical average: 45-48%
- Rising oil share = oil commanding premium (biofuel demand, etc.)
- Falling oil share = meal driving the crush (feed demand)

For Soyoil Traders:
- High Crush Pressure (tight margins) → reduced crush rates → less oil supply
- But also signals weak oil demand relative to meal
- Net effect depends on whether supply cut exceeds demand weakness

@author Claude (ZINC-FUSION-V15)
@date 2026-01-31
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np
from dotenv import load_dotenv

load_dotenv()

# ==============================================================================
# DOMAIN CONSTANTS - Based on actual crush economics
# ==============================================================================

# Board crush thresholds ($/bushel) - empirically calibrated
CRUSH_DANGER_ZONE = 0.75  # Processors lose money
CRUSH_SEVERE_STRESS = 1.00  # Marginal economics
CRUSH_TIGHT = 1.25  # Profitable but squeezed
CRUSH_NEUTRAL = 1.50  # Typical margins
CRUSH_HEALTHY = 1.75  # Good margins
CRUSH_STRONG = 2.00  # Strong margins
CRUSH_EXCEPTIONAL = 2.50  # Exceptional (unsustainable)

# Oil share thresholds (%)
OIL_SHARE_VERY_LOW = 0.42  # Oil severely undervalued
OIL_SHARE_LOW = 0.45  # Oil weak
OIL_SHARE_NEUTRAL_LOW = 0.47  # Slightly below average
OIL_SHARE_NEUTRAL_HIGH = 0.49  # Slightly above average
OIL_SHARE_HIGH = 0.51  # Oil commanding premium
OIL_SHARE_VERY_HIGH = 0.54  # Oil extremely strong

# Rate of change thresholds (% per 5 days)
OIL_SHARE_FALLING_FAST = -0.02  # 2% drop in 5 days
OIL_SHARE_FALLING = -0.005  # 0.5% drop
OIL_SHARE_RISING = 0.005  # 0.5% gain
OIL_SHARE_RISING_FAST = 0.02  # 2% gain


@dataclass
class CrushRegime:
    """Crush margin regime classification."""

    name: str
    description: str
    implications_oil: str  # What this means for soyoil
    implications_meal: str  # What this means for soymeal


CRUSH_REGIMES = {
    "margin_collapse": CrushRegime(
        name="Margin Collapse",
        description="Processors at/below breakeven. Crush cuts imminent. Plants idling.",
        implications_oil="ZL MIXED-BEARISH. Supply cuts coming but reflects weak oil demand. Basis chaotic. Watch for capacity shutdowns.",
        implications_meal="Meal basis firming sharply as supply dries up.",
    ),
    "severe_stress": CrushRegime(
        name="Severe Stress",
        description="Marginal economics. Weaker plants idling. Industry operating defensively.",
        implications_oil="ZL CAUTIOUS. Supply headwinds but demand soft. Oil share critical - if falling, meal driving. Processor discipline key.",
        implications_meal="Meal basis bid as crush rates slow.",
    ),
    "tight_margins": CrushRegime(
        name="Tight Margins",
        description="Profitable but squeezed. Processors running cautiously. No expansion.",
        implications_oil="ZL NEUTRAL. Watch oil share closely - falling = meal driving, stable = balanced. Biofuel demand key.",
        implications_meal="Adequate supplies. Basis stable.",
    ),
    "healthy_margins": CrushRegime(
        name="Healthy Margins",
        description="Normal economics. Steady crush. Industry operating smoothly.",
        implications_oil="ZL NEUTRAL-BULLISH. Balanced fundamentals. Oil share trend is direction. Strong renewable diesel = oil premium.",
        implications_meal="Ample supplies. Feed demand met.",
    ),
    "strong_margins": CrushRegime(
        name="Strong Margins",
        description="Excellent economics. High utilization. Plants running hard.",
        implications_oil="ZL CAUTIOUS-BULLISH. Heavy supply but if demand absorbs (biofuel mandates, exports) = bullish. Watch stocks.",
        implications_meal="Plentiful supplies pressuring meal basis.",
    ),
    "exceptional_margins": CrushRegime(
        name="Exceptional Margins",
        description="Unusually high margins. Maximum crush. Usually unsustainable.",
        implications_oil="ZL WATCH DEMAND. Max supply hitting market. Need robust biofuel/export demand or prices will correct.",
        implications_meal="Heavy supplies. Meal under pressure.",
    ),
}


def score_board_crush_level(crush_value: float) -> Tuple[float, str]:
    """
    Score board crush level using domain-specific thresholds.

    Returns (score, regime_key) where score is 0-100 (high = more pressure/stress).

    This is NOT a generic percentile - it's calibrated to actual processor economics.
    """
    if crush_value < CRUSH_DANGER_ZONE:
        # Below $0.75 - danger zone
        # Score 90-100 based on how far below
        score = 95 + min(5, (CRUSH_DANGER_ZONE - crush_value) * 20)
        return min(100, score), "margin_collapse"

    elif crush_value < CRUSH_SEVERE_STRESS:
        # $0.75 - $1.00 - severe stress
        # Linear interpolation: $0.75 → 85, $1.00 → 75
        pct = (crush_value - CRUSH_DANGER_ZONE) / (
            CRUSH_SEVERE_STRESS - CRUSH_DANGER_ZONE
        )
        score = 85 - (pct * 10)
        return score, "severe_stress"

    elif crush_value < CRUSH_TIGHT:
        # $1.00 - $1.25 - tight margins
        # Linear: $1.00 → 70, $1.25 → 55
        pct = (crush_value - CRUSH_SEVERE_STRESS) / (CRUSH_TIGHT - CRUSH_SEVERE_STRESS)
        score = 70 - (pct * 15)
        return score, "tight_margins"

    elif crush_value < CRUSH_NEUTRAL:
        # $1.25 - $1.50 - approaching neutral
        # Linear: $1.25 → 55, $1.50 → 45
        pct = (crush_value - CRUSH_TIGHT) / (CRUSH_NEUTRAL - CRUSH_TIGHT)
        score = 55 - (pct * 10)
        return score, "tight_margins"

    elif crush_value < CRUSH_HEALTHY:
        # $1.50 - $1.75 - healthy
        # Linear: $1.50 → 45, $1.75 → 30
        pct = (crush_value - CRUSH_NEUTRAL) / (CRUSH_HEALTHY - CRUSH_NEUTRAL)
        score = 45 - (pct * 15)
        return score, "healthy_margins"

    elif crush_value < CRUSH_STRONG:
        # $1.75 - $2.00 - strong
        # Linear: $1.75 → 30, $2.00 → 20
        pct = (crush_value - CRUSH_HEALTHY) / (CRUSH_STRONG - CRUSH_HEALTHY)
        score = 30 - (pct * 10)
        return score, "strong_margins"

    else:
        # > $2.00 - exceptional
        # Asymptote to 5 as crush goes higher
        excess = crush_value - CRUSH_STRONG
        score = 20 - min(15, excess * 15)
        return max(5, score), "exceptional_margins"


def score_oil_share_level(oil_share: float) -> Tuple[float, str]:
    """
    Score oil share level using domain thresholds.

    From a soyoil perspective:
    - Low oil share = bearish (meal driving the crush)
    - High oil share = bullish (oil commanding premium)

    Returns (adjustment, description) where adjustment modifies base score.
    """
    if oil_share < OIL_SHARE_VERY_LOW:
        return 20, "Oil severely undervalued (meal driving crush)"
    elif oil_share < OIL_SHARE_LOW:
        return 12, "Oil weak relative to meal"
    elif oil_share < OIL_SHARE_NEUTRAL_LOW:
        return 5, "Oil slightly below historical average"
    elif oil_share < OIL_SHARE_NEUTRAL_HIGH:
        return 0, "Oil share in normal range"
    elif oil_share < OIL_SHARE_HIGH:
        return -5, "Oil slightly above average"
    elif oil_share < OIL_SHARE_VERY_HIGH:
        return -10, "Oil commanding premium"
    else:
        return -15, "Oil share extremely elevated"


def score_oil_share_trend(
    current: float, prior: float, days: int = 5
) -> Tuple[float, str]:
    """
    Score oil share trend (direction matters for soyoil traders).

    Returns (adjustment, description).
    """
    if prior == 0:
        return 0, "No trend data"

    change = (current - prior) / prior

    if change < OIL_SHARE_FALLING_FAST:
        return 15, "Oil share falling sharply"
    elif change < OIL_SHARE_FALLING:
        return 8, "Oil share declining"
    elif change > OIL_SHARE_RISING_FAST:
        return -12, "Oil share surging"
    elif change > OIL_SHARE_RISING:
        return -6, "Oil share rising"
    else:
        return 0, "Oil share stable"


def generate_crush_narrative(
    crush_value: float,
    oil_share: float,
    oil_share_change: float,
    score: float,
    regime: str,
) -> Tuple[str, str, List[str]]:
    """
    Generate domain-expert narrative for crush pressure.

    Returns (headline, story, key_drivers).
    """
    regime_info = CRUSH_REGIMES.get(regime, CRUSH_REGIMES["healthy_margins"])

    # Headline based on score
    if score >= 80:
        headline = "Crush Margins Collapsing"
    elif score >= 65:
        headline = "Processors Under Severe Stress"
    elif score >= 55:
        headline = "Crush Margins Tightening"
    elif score >= 45:
        headline = "Crush Economics Mixed"
    elif score >= 35:
        headline = "Healthy Processor Margins"
    elif score >= 25:
        headline = "Strong Crush Economics"
    else:
        headline = "Exceptional Crush Margins"

    # Build narrative
    parts = []

    # Crush level context
    parts.append(
        f"Board crush at ${crush_value:.2f}/bu reflects {regime_info.name.lower()} conditions."
    )

    # Oil share context
    if oil_share_change < -0.01:
        parts.append(
            f"Oil share at {oil_share * 100:.1f}% is falling, indicating meal is driving processor economics."
        )
    elif oil_share_change > 0.01:
        parts.append(
            f"Oil share at {oil_share * 100:.1f}% is rising, with oil commanding an increasing premium."
        )
    else:
        parts.append(f"Oil share at {oil_share * 100:.1f}% is stable.")

    # Implication for soyoil
    parts.append(regime_info.implications_oil)

    narrative = " ".join(parts)

    # Key drivers
    drivers = []

    if crush_value < CRUSH_TIGHT:
        drivers.append(f"Tight board crush (${crush_value:.2f}/bu)")
    elif crush_value > CRUSH_HEALTHY:
        drivers.append(f"Strong board crush (${crush_value:.2f}/bu)")

    if oil_share < OIL_SHARE_LOW:
        drivers.append(f"Low oil share ({oil_share * 100:.1f}%)")
    elif oil_share > OIL_SHARE_HIGH:
        drivers.append(f"High oil share ({oil_share * 100:.1f}%)")

    if oil_share_change < OIL_SHARE_FALLING:
        drivers.append("Falling oil share trend")
    elif oil_share_change > OIL_SHARE_RISING:
        drivers.append("Rising oil share trend")

    if not drivers:
        drivers.append("Balanced crush fundamentals")

    return headline, narrative, drivers


def calculate_crush_pressure(conn, as_of_date: Optional[date] = None) -> Dict:
    """
    Calculate Crush Pressure using real board crush economics.

    This is domain-specific scoring, NOT generic percentile-based.

    Components:
    1. Board Crush Level (45%): Absolute margin assessment
    2. Oil Share Level (20%): Relative value of oil vs meal
    3. Oil Share Trend (20%): Direction of oil's share
    4. Specialist Signal (15%): Model-based overlay

    Returns PressureReading-compatible dict.
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()

    # Get board crush data
    cur.execute(
        """
        SELECT trade_date, board_crush, oil_share
        FROM analytics.board_crush_1d
        WHERE trade_date <= %s
        ORDER BY trade_date DESC
        LIMIT 126
    """,
        (as_of_date,),
    )
    crush_data = cur.fetchall()

    # Get crush specialist signal
    cur.execute(
        """
        SELECT signal_1, confidence
        FROM training.specialist_signals_1d
        WHERE bucket = 'crush' AND as_of_date <= %s
        ORDER BY as_of_date DESC
        LIMIT 1
    """,
        (as_of_date,),
    )
    signal_row = cur.fetchone()

    # Handle no data case
    if not crush_data:
        return {
            "name": "Crush Pressure",
            "score": 50.0,
            "level": "Elevated",
            "trend": "Stable",
            "headline": "Crush Data Unavailable",
            "narrative": "Board crush data is not yet available. Analytics require price data to compute processor margins.",
            "key_drivers": ["Awaiting data"],
            "color": "#6B7280",
            "icon": "loader",
            "sparkline": [50] * 10,
            "percentile_30d": 50.0,
            "percentile_1y": 50.0,
            "regime": "unknown",
            "momentum": 0.0,
            "as_of_date": as_of_date.isoformat(),
            "components": {},
        }

    # Current values
    current_crush = float(crush_data[0][1])
    current_oil_share = float(crush_data[0][2])

    # Historical values for trend
    oil_share_5d_ago = (
        float(crush_data[min(5, len(crush_data) - 1)][2])
        if len(crush_data) > 1
        else current_oil_share
    )
    oil_share_change = (
        (current_oil_share - oil_share_5d_ago) / oil_share_5d_ago
        if oil_share_5d_ago > 0
        else 0
    )

    # ==== COMPONENT 1: Board Crush Level (45% weight) ====
    crush_score, regime = score_board_crush_level(current_crush)

    # ==== COMPONENT 2: Oil Share Level (20% weight) ====
    oil_share_adjustment, oil_share_desc = score_oil_share_level(current_oil_share)

    # ==== COMPONENT 3: Oil Share Trend (20% weight) ====
    trend_adjustment, trend_desc = score_oil_share_trend(
        current_oil_share, oil_share_5d_ago
    )

    # ==== COMPONENT 4: Specialist Signal (15% weight) ====
    signal_adjustment = 0
    signal_desc = "No signal"
    if signal_row and signal_row[0] is not None:
        signal_val = float(signal_row[0])
        confidence = float(signal_row[1]) if signal_row[1] else 0.5
        # Negative signal = bearish = more pressure expected
        signal_adjustment = -signal_val * 20 * confidence
        if signal_val < -0.15:
            signal_desc = "Bearish specialist outlook"
        elif signal_val > 0.15:
            signal_desc = "Bullish specialist outlook"
        else:
            signal_desc = "Neutral specialist signal"

    # ==== COMPOSITE SCORE ====
    # Start with crush level score, then add adjustments
    base_score = crush_score

    # Apply oil share adjustments (these modify the crush-based score)
    score = base_score + (oil_share_adjustment * 0.20 / 0.45)  # Scale to 45% base
    score += trend_adjustment * 0.20 / 0.45
    score += signal_adjustment * 0.15 / 0.45

    # Ensure bounds
    score = float(np.clip(score, 0, 100))

    # ==== SPARKLINE: Historical scores ====
    sparkline = []
    for row in reversed(crush_data[:10]):
        hist_crush = float(row[1])
        hist_score, _ = score_board_crush_level(hist_crush)
        sparkline.append(hist_score)

    # ==== MOMENTUM ====
    if len(sparkline) >= 5:
        recent = np.mean(sparkline[-3:])
        earlier = np.mean(sparkline[:3])
        momentum = (recent - earlier) / max(abs(earlier), 1) if earlier != 0 else 0
        momentum = float(np.clip(momentum, -1, 1))
    else:
        momentum = 0.0

    # ==== TREND DIRECTION ====
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
    headline, narrative, drivers = generate_crush_narrative(
        current_crush, current_oil_share, oil_share_change, score, regime
    )

    # Add signal to drivers if significant
    if abs(signal_adjustment) > 5:
        drivers.append(signal_desc)

    return {
        "name": "Crush Pressure",
        "score": round(score, 1),
        "level": level,
        "trend": trend,
        "headline": headline,
        "narrative": narrative,
        "key_drivers": drivers,
        "color": color,
        "icon": "droplet" if score < 50 else "alert-triangle",
        "sparkline": [round(v, 1) for v in sparkline],
        "percentile_30d": round(
            score, 1
        ),  # For this domain-based score, context IS the score
        "percentile_1y": round(score, 1),
        "regime": regime,
        "momentum": round(momentum, 3),
        "as_of_date": as_of_date.isoformat(),
        "components": {
            "board_crush_score": round(crush_score, 1),
            "board_crush_value": round(current_crush, 2),
            "oil_share_level": round(oil_share_adjustment, 1),
            "oil_share_value": round(current_oil_share * 100, 2),
            "oil_share_trend": round(trend_adjustment, 1),
            "oil_share_change_5d": round(oil_share_change * 100, 2),
            "specialist_signal": round(signal_adjustment, 1),
        },
        "domain_context": {
            "regime_name": CRUSH_REGIMES.get(
                regime, CRUSH_REGIMES["healthy_margins"]
            ).name,
            "regime_description": CRUSH_REGIMES.get(
                regime, CRUSH_REGIMES["healthy_margins"]
            ).description,
            "oil_implication": CRUSH_REGIMES.get(
                regime, CRUSH_REGIMES["healthy_margins"]
            ).implications_oil,
            "oil_share_assessment": oil_share_desc,
            "trend_assessment": trend_desc,
        },
    }
