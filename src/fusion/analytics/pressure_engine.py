"""
ZINC-FUSION-V15: Narrative Pressure Engine

Dashboard-ready pressure indicators that tell stories, not just show numbers.
Each pressure gauge generates:
  - Score (0-100)
  - Narrative label (Extreme Pressure, High, Elevated, Normal, Low)
  - Trend (Rising Fast, Rising, Stable, Falling, Falling Fast)
  - Story text (2-3 sentences explaining the pressure)
  - Key drivers (what's causing it)
  - Visual cues (color, icon hint, sparkline data)
  - 3D context (historical percentile, regime, momentum)

ARCHITECTURE (v2 - Domain-Specific Calculators):
  Each pressure has its own domain-expert calculator in pressures/:
  - crush_pressure.py: Board crush economics, oil share dynamics
  - volatility_pressure.py: VIX term structure, realized vol
  - greed_pressure.py: CNN Fear/Greed methodology
  - policy_pressure.py: Baker-Bloom-Davis EPU/TPU
  - trade_pressure.py: Baltic Dry, BRL, China signals
  - news_pressure.py: News velocity, geopolitical risk

  This file orchestrates the calculators and adds visual enhancements.

Pressures:
  1. Crush Pressure - Soybean processor margin stress
  2. Greed Pressure Index - Market sentiment composite
  3. Volatility Pressure - Market fear/uncertainty
  4. Trump Effect Pressure - Policy uncertainty from executive actions
  5. Trade Pressure - Global shipping and trade flow stress
  6. Tariff Pressure - Trade policy uncertainty
  7. Correlation Pressure - Risk-on/off regime detection
  8. Global News Pressure - News velocity and sentiment
  9. Country War Pressure - Geopolitical risk indicators

@author Claude (ZINC-FUSION-V15)
@date 2026-01-31
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

# Import domain-specific calculators
from .pressures.crush_pressure import calculate_crush_pressure as _calc_crush
from .pressures.volatility_pressure import calculate_volatility_pressure as _calc_vol
from .pressures.greed_pressure import calculate_greed_pressure as _calc_greed
from .pressures.policy_pressure import calculate_trump_effect_pressure as _calc_trump
from .pressures.policy_pressure import calculate_tariff_pressure as _calc_tariff
from .pressures.trade_pressure import calculate_trade_pressure as _calc_trade
from .pressures.trade_pressure import calculate_correlation_pressure as _calc_corr
from .pressures.news_pressure import calculate_news_pressure as _calc_news
from .pressures.news_pressure import calculate_geopolitical_pressure as _calc_geo

load_dotenv()


class PressureLevel(Enum):
    """Narrative labels for pressure intensity."""
    EXTREME = "Extreme Pressure"
    HIGH = "High Pressure"
    ELEVATED = "Elevated"
    NORMAL = "Normal"
    LOW = "Low Pressure"
    VERY_LOW = "Very Low"


class TrendDirection(Enum):
    """Trend descriptions."""
    SURGING = "Surging ↑↑"
    RISING = "Rising ↑"
    STABLE = "Stable →"
    FALLING = "Falling ↓"
    PLUNGING = "Plunging ↓↓"


@dataclass
class VisualCue:
    """Rich visual metadata for dashboard rendering."""
    # Gauge styling
    gauge_color: str  # Primary color hex
    gauge_gradient: List[str]  # Gradient stops for 3D effect
    glow_intensity: float  # 0-1 for glow effect
    pulse_speed: str  # "none", "slow", "medium", "fast" for attention

    # Sparkline styling
    sparkline_gradient: List[str]  # Area fill gradient
    sparkline_stroke: str  # Line color
    sparkline_points: bool  # Show data points

    # Alert styling
    alert_level: str  # "none", "watch", "warning", "critical"
    badge_text: Optional[str]  # Optional badge overlay


@dataclass
class ForecastData:
    """Forward-looking projections for each pressure."""
    forecast_1d: float  # Tomorrow's expected score
    forecast_5d: float  # 5-day forward
    forecast_direction: str  # "improving", "stable", "deteriorating"
    confidence: float  # 0-1 forecast confidence
    forward_curve: List[Tuple[str, float]]  # (date_label, value) pairs


@dataclass
class NarrativeGraphic:
    """Rich narrative elements for storytelling."""
    tagline: str  # Ultra-short 3-5 word hook
    story_arc: str  # "escalating", "peak", "resolving", "building", "stable"
    icon_hint: str  # Icon name hint for frontend (no emojis)
    comparison: str  # "vs last week", "vs 3 months ago", etc.
    comparison_delta: float  # Change vs comparison period
    call_to_action: str  # What to watch for


@dataclass
class PressureReading:
    """A single pressure gauge reading with full narrative context."""
    name: str
    score: float  # 0-100
    level: PressureLevel
    trend: TrendDirection

    # The story
    headline: str  # Short punchy headline
    narrative: str  # 2-3 sentence explanation
    key_drivers: List[str]  # What's causing this

    # Visual cues
    color: str  # hex color for gauge
    icon: str  # suggested icon name
    sparkline: List[float]  # last N values for mini-chart

    # 3D context
    percentile_30d: float  # Where are we vs last 30 days
    percentile_1y: float  # Where are we vs last year
    regime: str  # Current regime classification
    momentum: float  # Rate of change (-1 to +1)

    # Rich visuals (new!)
    visual: Optional[VisualCue] = None
    forecast: Optional[ForecastData] = None
    graphic: Optional[NarrativeGraphic] = None

    # Metadata
    as_of_date: date = field(default_factory=date.today)
    components: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dashboard-ready dict with rich visuals."""
        result = {
            "name": self.name,
            "score": round(self.score, 1),
            "level": self.level.value,
            "trend": self.trend.value,
            "headline": self.headline,
            "narrative": self.narrative,
            "key_drivers": self.key_drivers,
            "color": self.color,
            "icon": self.icon,
            "sparkline": [round(v, 1) for v in self.sparkline],
            "percentile_30d": round(self.percentile_30d, 1),
            "percentile_1y": round(self.percentile_1y, 1),
            "regime": self.regime,
            "momentum": round(self.momentum, 3),
            "as_of_date": self.as_of_date.isoformat(),
            "components": {k: (round(v, 3) if isinstance(v, (int, float)) else v) for k, v in self.components.items()},
        }

        # Add rich visual data
        if self.visual:
            result["visual"] = {
                "gauge_color": self.visual.gauge_color,
                "gauge_gradient": self.visual.gauge_gradient,
                "glow_intensity": self.visual.glow_intensity,
                "pulse_speed": self.visual.pulse_speed,
                "sparkline_gradient": self.visual.sparkline_gradient,
                "sparkline_stroke": self.visual.sparkline_stroke,
                "sparkline_points": self.visual.sparkline_points,
                "alert_level": self.visual.alert_level,
                "badge_text": self.visual.badge_text,
            }

        if self.forecast:
            result["forecast"] = {
                "1d": round(self.forecast.forecast_1d, 1),
                "5d": round(self.forecast.forecast_5d, 1),
                "direction": self.forecast.forecast_direction,
                "confidence": round(self.forecast.confidence, 2),
                "forward_curve": [(d, round(v, 1)) for d, v in self.forecast.forward_curve],
            }

        if self.graphic:
            result["graphic"] = {
                "tagline": self.graphic.tagline,
                "story_arc": self.graphic.story_arc,
                "icon_hint": self.graphic.icon_hint,
                "comparison": self.graphic.comparison,
                "comparison_delta": round(self.graphic.comparison_delta, 1),
                "call_to_action": self.graphic.call_to_action,
            }

        return result


def get_connection():
    """Get database connection."""
    return psycopg2.connect(os.environ["DATABASE_URL"])


def score_to_level(score: float) -> PressureLevel:
    """Convert 0-100 score to narrative level."""
    if score >= 80:
        return PressureLevel.EXTREME
    elif score >= 65:
        return PressureLevel.HIGH
    elif score >= 50:
        return PressureLevel.ELEVATED
    elif score >= 35:
        return PressureLevel.NORMAL
    elif score >= 20:
        return PressureLevel.LOW
    else:
        return PressureLevel.VERY_LOW


def momentum_to_trend(momentum: float) -> TrendDirection:
    """Convert momentum (-1 to +1) to trend direction."""
    if momentum >= 0.3:
        return TrendDirection.SURGING
    elif momentum >= 0.1:
        return TrendDirection.RISING
    elif momentum <= -0.3:
        return TrendDirection.PLUNGING
    elif momentum <= -0.1:
        return TrendDirection.FALLING
    else:
        return TrendDirection.STABLE


def score_to_color(score: float) -> str:
    """Get color for gauge based on score."""
    if score >= 80:
        return "#DC2626"  # Red - extreme
    elif score >= 65:
        return "#EA580C"  # Orange - high
    elif score >= 50:
        return "#D97706"  # Amber - elevated
    elif score >= 35:
        return "#65A30D"  # Green - normal
    else:
        return "#0891B2"  # Cyan - low


def calculate_percentile(value: float, historical: List[float]) -> float:
    """Calculate percentile rank of value vs historical distribution."""
    if not historical or len(historical) < 5:
        return 50.0
    return float(np.percentile([value] + historical, (np.searchsorted(sorted(historical), value) / len(historical)) * 100))


def calculate_momentum(values: List[float], window: int = 5) -> float:
    """Calculate momentum as normalized rate of change."""
    if len(values) < window + 1:
        return 0.0
    recent = np.mean(values[-window:])
    earlier = np.mean(values[-(window*2):-window]) if len(values) >= window * 2 else values[0]
    if earlier == 0:
        return 0.0
    raw_momentum = (recent - earlier) / abs(earlier)
    return float(np.clip(raw_momentum, -1, 1))


def generate_visual_cue(score: float, momentum: float, level: PressureLevel) -> VisualCue:
    """Generate rich visual styling based on pressure state."""

    # Color palettes for each level
    palettes = {
        PressureLevel.EXTREME: {
            "base": "#DC2626",
            "gradient": ["#FEE2E2", "#FECACA", "#FCA5A5", "#F87171", "#EF4444", "#DC2626"],
            "sparkline": ["#FEE2E2", "#DC2626"],
            "glow": 0.9,
            "pulse": "fast",
            "alert": "critical",
        },
        PressureLevel.HIGH: {
            "base": "#EA580C",
            "gradient": ["#FFEDD5", "#FED7AA", "#FDBA74", "#FB923C", "#F97316", "#EA580C"],
            "sparkline": ["#FFEDD5", "#EA580C"],
            "glow": 0.7,
            "pulse": "medium",
            "alert": "warning",
        },
        PressureLevel.ELEVATED: {
            "base": "#D97706",
            "gradient": ["#FEF3C7", "#FDE68A", "#FCD34D", "#FBBF24", "#F59E0B", "#D97706"],
            "sparkline": ["#FEF3C7", "#D97706"],
            "glow": 0.5,
            "pulse": "slow",
            "alert": "watch",
        },
        PressureLevel.NORMAL: {
            "base": "#65A30D",
            "gradient": ["#ECFCCB", "#D9F99D", "#BEF264", "#A3E635", "#84CC16", "#65A30D"],
            "sparkline": ["#ECFCCB", "#65A30D"],
            "glow": 0.2,
            "pulse": "none",
            "alert": "none",
        },
        PressureLevel.LOW: {
            "base": "#0891B2",
            "gradient": ["#CFFAFE", "#A5F3FC", "#67E8F9", "#22D3EE", "#06B6D4", "#0891B2"],
            "sparkline": ["#CFFAFE", "#0891B2"],
            "glow": 0.1,
            "pulse": "none",
            "alert": "none",
        },
        PressureLevel.VERY_LOW: {
            "base": "#0284C7",
            "gradient": ["#E0F2FE", "#BAE6FD", "#7DD3FC", "#38BDF8", "#0EA5E9", "#0284C7"],
            "sparkline": ["#E0F2FE", "#0284C7"],
            "glow": 0.0,
            "pulse": "none",
            "alert": "none",
        },
    }

    p = palettes.get(level, palettes[PressureLevel.NORMAL])

    # Badge text based on momentum and level
    badge = None
    if momentum > 0.25 and score > 60:
        badge = "RISING FAST"
    elif momentum < -0.25 and score < 40:
        badge = "EASING"
    elif score >= 80:
        badge = "EXTREME"
    elif score >= 70:
        badge = "HIGH ALERT"

    return VisualCue(
        gauge_color=p["base"],
        gauge_gradient=p["gradient"],
        glow_intensity=p["glow"],
        pulse_speed=p["pulse"],
        sparkline_gradient=p["sparkline"],
        sparkline_stroke=p["base"],
        sparkline_points=score >= 60,  # Show points for high pressure
        alert_level=p["alert"],
        badge_text=badge,
    )


def generate_forecast(score: float, momentum: float, sparkline: List[float]) -> ForecastData:
    """Generate simple forward projections based on momentum."""

    # Naive forecast: project momentum forward
    forecast_1d = score + (momentum * 5)  # 1 day forward
    forecast_5d = score + (momentum * 15)  # 5 days forward

    # Clamp forecasts
    forecast_1d = float(np.clip(forecast_1d, 0, 100))
    forecast_5d = float(np.clip(forecast_5d, 0, 100))

    # Determine direction
    if momentum > 0.1:
        direction = "deteriorating" if score > 50 else "building"
    elif momentum < -0.1:
        direction = "improving" if score > 50 else "easing"
    else:
        direction = "stable"

    # Build forward curve (next 10 periods)
    forward_curve = []
    current = score
    for i in range(1, 11):
        # Mean reversion + momentum
        mean_reversion = (50 - current) * 0.05
        projected = current + (momentum * 3) + mean_reversion
        projected = float(np.clip(projected, 0, 100))
        forward_curve.append((f"+{i}d", projected))
        current = projected

    # Confidence based on sparkline volatility
    if len(sparkline) > 5:
        vol = np.std(sparkline[-10:]) if len(sparkline) >= 10 else np.std(sparkline)
        confidence = max(0.3, 1.0 - (vol / 30))  # Higher vol = lower confidence
    else:
        confidence = 0.5

    return ForecastData(
        forecast_1d=forecast_1d,
        forecast_5d=forecast_5d,
        forecast_direction=direction,
        confidence=confidence,
        forward_curve=forward_curve,
    )


def generate_narrative_graphic(
    name: str,
    score: float,
    momentum: float,
    level: PressureLevel,
    sparkline: List[float],
) -> NarrativeGraphic:
    """Generate rich narrative elements for storytelling."""

    # Taglines by pressure and level
    taglines = {
        "Crush Pressure": {
            PressureLevel.EXTREME: "Margins Imploding",
            PressureLevel.HIGH: "Crushers Squeezed",
            PressureLevel.ELEVATED: "Margins Tight",
            PressureLevel.NORMAL: "Margins OK",
            PressureLevel.LOW: "Margins Wide",
            PressureLevel.VERY_LOW: "Fat Margins",
        },
        "Greed Pressure Index": {
            PressureLevel.EXTREME: "Peak Greed",
            PressureLevel.HIGH: "Bulls Running",
            PressureLevel.ELEVATED: "Optimism Rising",
            PressureLevel.NORMAL: "Balanced View",
            PressureLevel.LOW: "Fear Building",
            PressureLevel.VERY_LOW: "Peak Fear",
        },
        "Volatility Pressure": {
            PressureLevel.EXTREME: "Markets Panicking",
            PressureLevel.HIGH: "Vol Spiking",
            PressureLevel.ELEVATED: "Nerves Fraying",
            PressureLevel.NORMAL: "Markets Calm",
            PressureLevel.LOW: "Very Calm",
            PressureLevel.VERY_LOW: "Dead Calm",
        },
        "Trump Effect Pressure": {
            PressureLevel.EXTREME: "Policy Chaos",
            PressureLevel.HIGH: "Major Uncertainty",
            PressureLevel.ELEVATED: "Policy Noise",
            PressureLevel.NORMAL: "Stable Policy",
            PressureLevel.LOW: "Policy Clear",
            PressureLevel.VERY_LOW: "Full Clarity",
        },
        "Trade Pressure": {
            PressureLevel.EXTREME: "Trade Blocked",
            PressureLevel.HIGH: "Shipping Stalled",
            PressureLevel.ELEVATED: "Trade Slowing",
            PressureLevel.NORMAL: "Trade Flowing",
            PressureLevel.LOW: "Trade Smooth",
            PressureLevel.VERY_LOW: "Trade Booming",
        },
        "Tariff Pressure": {
            PressureLevel.EXTREME: "Tariff War",
            PressureLevel.HIGH: "Tariffs Rising",
            PressureLevel.ELEVATED: "Tariff Threats",
            PressureLevel.NORMAL: "Tariff Calm",
            PressureLevel.LOW: "Tariff Truce",
            PressureLevel.VERY_LOW: "Free Trade",
        },
        "Correlation Pressure": {
            PressureLevel.EXTREME: "Everything Selling",
            PressureLevel.HIGH: "Risk-Off Mode",
            PressureLevel.ELEVATED: "Correlations High",
            PressureLevel.NORMAL: "Normal Dispersal",
            PressureLevel.LOW: "Risk-On Mode",
            PressureLevel.VERY_LOW: "Full Risk-On",
        },
        "Global News Pressure": {
            PressureLevel.EXTREME: "News Firehose",
            PressureLevel.HIGH: "Heavy Coverage",
            PressureLevel.ELEVATED: "Active News",
            PressureLevel.NORMAL: "Normal Flow",
            PressureLevel.LOW: "Light News",
            PressureLevel.VERY_LOW: "News Quiet",
        },
        "Country War Pressure": {
            PressureLevel.EXTREME: "Conflict Risk",
            PressureLevel.HIGH: "Tensions High",
            PressureLevel.ELEVATED: "Geopolitical Noise",
            PressureLevel.NORMAL: "Stable World",
            PressureLevel.LOW: "Global Calm",
            PressureLevel.VERY_LOW: "Peace Mode",
        },
    }

    # Get tagline
    name_taglines = taglines.get(name, {})
    tagline = name_taglines.get(level, "Monitoring")

    # Story arc based on momentum and level
    if momentum > 0.2:
        if score > 60:
            arc = "escalating"
        else:
            arc = "building"
    elif momentum < -0.2:
        if score > 60:
            arc = "resolving"
        else:
            arc = "easing"
    elif score > 75:
        arc = "peak"
    else:
        arc = "stable"

    # Icon hints by category (for frontend icon rendering)
    icons = {
        "Crush Pressure": "droplet" if score < 50 else "alert-triangle",
        "Greed Pressure Index": "trending-up" if score > 60 else "trending-down" if score < 40 else "minus",
        "Volatility Pressure": "activity" if score > 60 else "check-circle",
        "Trump Effect Pressure": "flag",
        "Trade Pressure": "truck" if score > 50 else "package",
        "Tariff Pressure": "shield" if score > 50 else "handshake",
        "Correlation Pressure": "git-merge",
        "Global News Pressure": "newspaper" if score > 50 else "volume-x",
        "Country War Pressure": "alert-octagon" if score > 60 else "globe",
    }
    icon_hint = icons.get(name, "bar-chart-2")

    # Comparison to previous
    if len(sparkline) >= 7:
        week_ago = sparkline[-7]
        delta = score - week_ago
        comparison = "vs last week"
    elif len(sparkline) >= 2:
        delta = score - sparkline[0]
        comparison = "vs prior"
    else:
        delta = 0
        comparison = "no history"

    # Call to action
    if score >= 75:
        cta = "Monitor closely for reversals"
    elif score >= 60 and momentum > 0.1:
        cta = f"Watch for {name.split()[0].lower()} escalation"
    elif score <= 30 and momentum < -0.1:
        cta = "Conditions improving rapidly"
    else:
        cta = "Continue monitoring"

    return NarrativeGraphic(
        tagline=tagline,
        story_arc=arc,
        icon_hint=icon_hint,
        comparison=comparison,
        comparison_delta=delta,
        call_to_action=cta,
    )


# =============================================================================
# CRUSH PRESSURE
# =============================================================================

def calculate_crush_pressure(conn, as_of_date: Optional[date] = None) -> PressureReading:
    """
    Crush Pressure: Soybean processor margin stress indicator.

    Measures the health of crush margins (processor profitability).
    High pressure = tight/negative margins = stress on processors.

    Components:
    - Board crush spread level (inverted - lower spread = higher pressure)
    - Oil share trend (falling oil share = higher pressure for soyoil)
    - Crush specialist signal
    - Historical percentile of margins
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()

    # Get board crush data
    cur.execute("""
        SELECT trade_date, board_crush, oil_share
        FROM analytics.board_crush_1d
        WHERE trade_date <= %s
        ORDER BY trade_date DESC
        LIMIT 252
    """, (as_of_date,))
    crush_data = cur.fetchall()

    # Get crush specialist signal
    cur.execute("""
        SELECT signal_1, confidence
        FROM training.specialist_signals_1d
        WHERE bucket = 'crush' AND as_of_date <= %s
        ORDER BY as_of_date DESC
        LIMIT 1
    """, (as_of_date,))
    signal_row = cur.fetchone()

    if not crush_data:
        # No data - return neutral
        return PressureReading(
            name="Crush Pressure",
            score=50.0,
            level=PressureLevel.ELEVATED,
            trend=TrendDirection.STABLE,
            headline="Crush data unavailable",
            narrative="Board crush data is not yet available. Check back after market close.",
            key_drivers=["Data pending"],
            color="#6B7280",
            icon="loader",
            sparkline=[50] * 10,
            percentile_30d=50.0,
            percentile_1y=50.0,
            regime="unknown",
            momentum=0.0,
        )

    # Current values
    current_crush = float(crush_data[0][1])
    current_oil_share = float(crush_data[0][2])

    # Historical context
    crush_values = [float(r[1]) for r in crush_data if r[1] is not None]
    oil_share_values = [float(r[2]) for r in crush_data if r[2] is not None]

    # Calculate components
    # Board crush z-score (lower crush = more pressure)
    if len(crush_values) > 20:
        crush_mean = np.mean(crush_values)
        crush_std = np.std(crush_values)
        crush_z = (current_crush - crush_mean) / crush_std if crush_std > 0 else 0
        crush_component = 50 - (crush_z * 15)  # Inverted: low crush = high pressure
    else:
        crush_component = 50

    # Oil share trend (falling = more pressure for soyoil)
    if len(oil_share_values) > 5:
        oil_share_5d_ago = oil_share_values[min(5, len(oil_share_values)-1)]
        oil_share_change = (current_oil_share - oil_share_5d_ago) / oil_share_5d_ago if oil_share_5d_ago > 0 else 0
        oil_share_component = 50 - (oil_share_change * 500)  # Falling oil share = pressure
    else:
        oil_share_component = 50

    # Specialist signal component
    signal_component = 50
    if signal_row and signal_row[0] is not None:
        # Negative signal = bearish = more pressure
        signal_component = 50 - (float(signal_row[0]) * 30)

    # Composite score (weighted average)
    score = (crush_component * 0.45) + (oil_share_component * 0.30) + (signal_component * 0.25)
    score = float(np.clip(score, 0, 100))

    # Calculate momentum
    sparkline_values = [50 - ((float(r[1]) - np.mean(crush_values)) / (np.std(crush_values) or 1) * 15)
                        for r in reversed(crush_data[:10])] if len(crush_values) > 5 else [50] * 10
    momentum = calculate_momentum(sparkline_values)

    # Regime classification
    if score >= 70:
        regime = "margin_squeeze"
    elif score >= 55:
        regime = "tight_margins"
    elif score >= 40:
        regime = "healthy_margins"
    else:
        regime = "wide_margins"

    # Generate narrative
    level = score_to_level(score)
    trend = momentum_to_trend(momentum)

    # Build story
    if level in [PressureLevel.EXTREME, PressureLevel.HIGH]:
        headline = "Crush Margins Under Stress"
        narrative = f"Processor margins are compressed with board crush at ${current_crush:.2f}/bu. "
        narrative += f"Oil share at {current_oil_share*100:.1f}% is {'falling' if oil_share_change < -0.01 else 'stable'}. "
        narrative += "This typically pressures soyoil prices as processors struggle."
    elif level == PressureLevel.ELEVATED:
        headline = "Crush Margins Tightening"
        narrative = f"Board crush spread at ${current_crush:.2f}/bu shows margins narrowing. "
        narrative += "Processors may reduce run rates if this continues."
    else:
        headline = "Healthy Crush Margins"
        narrative = f"Board crush at ${current_crush:.2f}/bu indicates profitable processing. "
        narrative += "Strong margins support soybean demand from crushers."

    drivers = []
    if crush_component > 55:
        drivers.append(f"Tight board crush (${current_crush:.2f}/bu)")
    if oil_share_component > 55:
        drivers.append(f"Falling oil share ({current_oil_share*100:.1f}%)")
    if signal_component > 55:
        drivers.append("Bearish crush specialist signal")
    if not drivers:
        drivers.append("All components normal")

    return PressureReading(
        name="Crush Pressure",
        score=score,
        level=level,
        trend=trend,
        headline=headline,
        narrative=narrative,
        key_drivers=drivers,
        color=score_to_color(score),
        icon="trending-down" if score > 60 else "trending-up",
        sparkline=sparkline_values[-10:] if len(sparkline_values) >= 10 else sparkline_values,
        percentile_30d=calculate_percentile(score, sparkline_values[-30:]) if len(sparkline_values) >= 30 else 50.0,
        percentile_1y=calculate_percentile(score, sparkline_values) if len(sparkline_values) >= 60 else 50.0,
        regime=regime,
        momentum=momentum,
        as_of_date=as_of_date,
        components={
            "board_crush": crush_component,
            "oil_share": oil_share_component,
            "specialist_signal": signal_component,
        }
    )


# =============================================================================
# GREED PRESSURE INDEX (Fear/Greed Style Composite)
# =============================================================================

def calculate_greed_pressure(conn, as_of_date: Optional[date] = None) -> PressureReading:
    """
    Greed Pressure Index: Market sentiment composite.

    CNN Fear/Greed style indicator adapted for soyoil markets.
    High score = Extreme Greed, Low score = Extreme Fear

    Components (equally weighted like CNN):
    1. VIX level (fear gauge)
    2. Put/Call ratio proxy (options skew)
    3. Market momentum (SPY trend)
    4. Specialist consensus (aggregate signals)
    5. News sentiment velocity
    6. Safe haven demand (GLD flows)
    7. Junk bond demand (credit spreads)
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}
    component_scores = []

    # 1. VIX Level (inverted - high VIX = fear)
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'VIXCLS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 252
    """, (as_of_date,))
    vix_data = cur.fetchall()

    if vix_data:
        current_vix = float(vix_data[0][1])
        vix_values = [float(r[1]) for r in vix_data if r[1] is not None]
        vix_percentile = calculate_percentile(current_vix, vix_values)
        # Invert: High VIX = low greed (fear)
        vix_score = 100 - vix_percentile
        components["vix_fear"] = vix_score
        component_scores.append(vix_score)

    # 2. Market Momentum (SPY)
    cur.execute("""
        SELECT event_date, close FROM mkt.etf_1d
        WHERE symbol = 'SPY' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 126
    """, (as_of_date,))
    spy_data = cur.fetchall()

    if len(spy_data) > 20:
        spy_values = [float(r[1]) for r in spy_data if r[1] is not None]
        spy_ma20 = np.mean(spy_values[:20])
        spy_ma125 = np.mean(spy_values[:min(125, len(spy_values))])
        current_spy = spy_values[0]

        # Above MAs = greed, below = fear
        ma_score = 50
        if current_spy > spy_ma20:
            ma_score += 15
        if current_spy > spy_ma125:
            ma_score += 15
        if spy_values[0] > spy_values[5] if len(spy_values) > 5 else True:
            ma_score += 10
        ma_score = min(100, max(0, ma_score))
        components["market_momentum"] = ma_score
        component_scores.append(ma_score)

    # 3. Safe Haven Demand (GLD - inverted)
    cur.execute("""
        SELECT event_date, close FROM mkt.etf_1d
        WHERE symbol = 'GLD' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 63
    """, (as_of_date,))
    gld_data = cur.fetchall()

    if len(gld_data) > 20:
        gld_values = [float(r[1]) for r in gld_data if r[1] is not None]
        gld_change = (gld_values[0] - gld_values[20]) / gld_values[20] if gld_values[20] > 0 else 0
        # Rising gold = fear (flight to safety)
        gld_score = 50 - (gld_change * 500)  # 10% gold rally = -50 points
        gld_score = float(np.clip(gld_score, 0, 100))
        components["safe_haven"] = gld_score
        component_scores.append(gld_score)

    # 4. Credit Spreads (HY spreads - inverted)
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'BAMLH0A0HYM2' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 252
    """, (as_of_date,))
    hy_data = cur.fetchall()

    if hy_data:
        current_spread = float(hy_data[0][1])
        spread_values = [float(r[1]) for r in hy_data if r[1] is not None]
        spread_percentile = calculate_percentile(current_spread, spread_values)
        # Wide spreads = fear
        spread_score = 100 - spread_percentile
        components["credit_spreads"] = spread_score
        component_scores.append(spread_score)

    # 5. Specialist Consensus
    cur.execute("""
        SELECT bucket, signal_1, confidence
        FROM (
            SELECT DISTINCT ON (bucket) bucket, signal_1, confidence
            FROM training.specialist_signals_1d
            WHERE as_of_date <= %s
            ORDER BY bucket, as_of_date DESC
        ) latest
    """, (as_of_date,))
    signals = cur.fetchall()

    if signals:
        bullish_count = sum(1 for _, s, _ in signals if s and s > 0.1)
        bearish_count = sum(1 for _, s, _ in signals if s and s < -0.1)
        total = len(signals)
        # Net bullish = greed
        consensus_score = 50 + ((bullish_count - bearish_count) / total * 50) if total > 0 else 50
        consensus_score = float(np.clip(consensus_score, 0, 100))
        components["specialist_consensus"] = consensus_score
        component_scores.append(consensus_score)

    # 6. News Sentiment Velocity
    cur.execute("""
        SELECT COUNT(*) FROM alt.econ_news
        WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s
    """, (as_of_date, as_of_date))
    news_count = cur.fetchone()[0] or 0

    cur.execute("""
        SELECT COUNT(*) FROM alt.econ_news
        WHERE event_date >= %s - INTERVAL '30 days' AND event_date <= %s - INTERVAL '7 days'
    """, (as_of_date, as_of_date))
    news_baseline = cur.fetchone()[0] or 1

    news_velocity = (news_count * 4) / news_baseline if news_baseline > 0 else 1  # Normalize to monthly
    # High news velocity often = fear (crisis coverage)
    news_score = 50 - ((news_velocity - 1) * 30)
    news_score = float(np.clip(news_score, 0, 100))
    components["news_velocity"] = news_score
    component_scores.append(news_score)

    # Calculate final score (equal weighted like CNN)
    score = np.mean(component_scores) if component_scores else 50.0

    # Sparkline from historical calculations
    sparkline = [50] * 10  # Placeholder - would need historical calc
    momentum = 0.0
    if len(vix_data) > 10:
        vix_spark = [100 - calculate_percentile(float(r[1]), [float(x[1]) for x in vix_data])
                     for r in reversed(vix_data[:10])]
        sparkline = vix_spark
        momentum = calculate_momentum(sparkline)

    level = score_to_level(score)
    trend = momentum_to_trend(momentum)

    # Generate narrative
    if score >= 75:
        headline = "Extreme Greed in Markets"
        narrative = "Investors are showing extreme optimism. Historically, this precedes pullbacks. "
        narrative += "Risk assets are stretched and complacency is high."
        regime = "extreme_greed"
    elif score >= 60:
        headline = "Markets Feeling Greedy"
        narrative = "Risk appetite is elevated with investors chasing returns. "
        narrative += "Caution warranted but trend remains constructive."
        regime = "greed"
    elif score >= 40:
        headline = "Neutral Sentiment"
        narrative = "Markets are balanced between fear and greed. "
        narrative += "Neither excessive optimism nor pessimism dominates."
        regime = "neutral"
    elif score >= 25:
        headline = "Fear Creeping In"
        narrative = "Investors are becoming cautious. "
        narrative += "This often precedes buying opportunities for contrarians."
        regime = "fear"
    else:
        headline = "Extreme Fear Grips Markets"
        narrative = "Panic is evident across markets. "
        narrative += "Historically, extreme fear marks major buying opportunities."
        regime = "extreme_fear"

    drivers = []
    if components.get("vix_fear", 50) < 40:
        drivers.append(f"Elevated VIX (fear gauge)")
    if components.get("safe_haven", 50) < 40:
        drivers.append("Flight to gold")
    if components.get("credit_spreads", 50) < 40:
        drivers.append("Widening credit spreads")
    if components.get("market_momentum", 50) > 60:
        drivers.append("Strong market momentum")
    if components.get("specialist_consensus", 50) > 60:
        drivers.append("Bullish specialist consensus")
    if not drivers:
        drivers.append("Mixed signals across indicators")

    return PressureReading(
        name="Greed Pressure Index",
        score=score,
        level=level,
        trend=trend,
        headline=headline,
        narrative=narrative,
        key_drivers=drivers,
        color=score_to_color(score),
        icon="trending-up" if score > 60 else "trending-down" if score < 40 else "minus",
        sparkline=sparkline,
        percentile_30d=calculate_percentile(score, sparkline[-30:]) if len(sparkline) >= 30 else 50.0,
        percentile_1y=50.0,  # Would need more history
        regime=regime,
        momentum=momentum,
        as_of_date=as_of_date,
        components=components,
    )


# =============================================================================
# VOLATILITY PRESSURE
# =============================================================================

def calculate_volatility_pressure(conn, as_of_date: Optional[date] = None) -> PressureReading:
    """
    Volatility Pressure: Market fear and uncertainty gauge.

    Measures realized and implied volatility stress.
    High pressure = high vol = uncertainty/fear in markets.

    Components:
    - VIX level and percentile
    - VIX term structure (VIX vs VIX3M)
    - Realized ZL volatility
    - Vol specialist signal
    - OVX (oil volatility) for energy context
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # VIX
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'VIXCLS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 252
    """, (as_of_date,))
    vix_data = cur.fetchall()

    vix_score = 50
    current_vix = 20  # Default
    if vix_data:
        current_vix = float(vix_data[0][1])
        vix_values = [float(r[1]) for r in vix_data if r[1] is not None]
        vix_score = calculate_percentile(current_vix, vix_values)
        components["vix_percentile"] = vix_score

    # OVX (oil volatility)
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'OVXCLS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 252
    """, (as_of_date,))
    ovx_data = cur.fetchall()

    ovx_score = 50
    if ovx_data:
        current_ovx = float(ovx_data[0][1])
        ovx_values = [float(r[1]) for r in ovx_data if r[1] is not None]
        ovx_score = calculate_percentile(current_ovx, ovx_values)
        components["ovx_percentile"] = ovx_score

    # Volatility specialist signal
    cur.execute("""
        SELECT signal_1, confidence
        FROM training.specialist_signals_1d
        WHERE bucket = 'volatility' AND as_of_date <= %s
        ORDER BY as_of_date DESC LIMIT 1
    """, (as_of_date,))
    vol_signal = cur.fetchone()

    signal_score = 50
    if vol_signal and vol_signal[0] is not None:
        # Positive signal = high vol expected = more pressure
        signal_score = 50 + (float(vol_signal[0]) * 30)
        signal_score = float(np.clip(signal_score, 0, 100))
        components["vol_specialist"] = signal_score

    # Realized ZL volatility
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

    rv_score = 50
    if rv_result and rv_result[0]:
        realized_vol = float(rv_result[0])
        # Typical ZL vol is 20-40%, so normalize
        if realized_vol < 0.20:
            rv_score = 20
        elif realized_vol < 0.30:
            rv_score = 40
        elif realized_vol < 0.40:
            rv_score = 60
        elif realized_vol < 0.50:
            rv_score = 80
        else:
            rv_score = 95
        components["realized_vol"] = rv_score

    # Composite score
    weights = {"vix_percentile": 0.35, "ovx_percentile": 0.20, "vol_specialist": 0.25, "realized_vol": 0.20}
    score = float(np.clip(sum(components.get(k, 50) * w for k, w in weights.items()), 0, 100))

    # Sparkline from VIX
    sparkline = [calculate_percentile(float(r[1]), [float(x[1]) for x in vix_data])
                 for r in reversed(vix_data[:10])] if len(vix_data) >= 10 else [50] * 10
    momentum = calculate_momentum(sparkline)

    level = score_to_level(score)
    trend = momentum_to_trend(momentum)

    # Regime
    if score >= 70:
        regime = "high_vol_regime"
    elif score >= 50:
        regime = "elevated_vol"
    elif score >= 30:
        regime = "normal_vol"
    else:
        regime = "low_vol_regime"

    # Narrative
    if score >= 75:
        headline = "Volatility Spiking"
        narrative = f"VIX at {current_vix:.1f} signals extreme market stress. "
        narrative += "Expect large price swings and elevated uncertainty."
    elif score >= 60:
        headline = "Elevated Volatility"
        narrative = f"VIX at {current_vix:.1f} shows heightened anxiety. "
        narrative += "Markets are nervous but not panicking."
    elif score >= 40:
        headline = "Normal Volatility"
        narrative = "Volatility is within typical ranges. "
        narrative += "Markets are functioning normally."
    else:
        headline = "Unusually Calm Markets"
        narrative = f"VIX at {current_vix:.1f} is historically low. "
        narrative += "Complacency can precede volatility spikes."

    drivers = []
    if components.get("vix_percentile", 50) > 65:
        drivers.append(f"VIX at {current_vix:.0f}")
    if components.get("ovx_percentile", 50) > 65:
        drivers.append("Oil volatility elevated")
    if components.get("vol_specialist", 50) > 65:
        drivers.append("Vol specialist signals high")
    if components.get("realized_vol", 50) > 65:
        drivers.append("High realized ZL volatility")
    if not drivers:
        drivers.append("All vol metrics normal")

    return PressureReading(
        name="Volatility Pressure",
        score=score,
        level=level,
        trend=trend,
        headline=headline,
        narrative=narrative,
        key_drivers=drivers,
        color=score_to_color(score),
        icon="activity",
        sparkline=sparkline,
        percentile_30d=calculate_percentile(score, sparkline[-30:]) if len(sparkline) >= 30 else 50.0,
        percentile_1y=calculate_percentile(score, sparkline),
        regime=regime,
        momentum=momentum,
        as_of_date=as_of_date,
        components=components,
    )


# =============================================================================
# TRUMP EFFECT PRESSURE
# =============================================================================

def calculate_trump_effect_pressure(conn, as_of_date: Optional[date] = None) -> PressureReading:
    """
    Trump Effect Pressure: Policy uncertainty from executive actions.

    Measures the impact of presidential policy changes on markets.
    High pressure = high policy uncertainty = market stress.

    Components:
    - Economic Policy Uncertainty Index
    - Trade Policy Uncertainty Index
    - Executive action news velocity
    - China ETF stress (FXI, KWEB)
    - Trump effect specialist signal
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # EPU Index
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'USEPUINDXD' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 252
    """, (as_of_date,))
    epu_data = cur.fetchall()

    epu_score = 50
    current_epu = 100
    if epu_data:
        current_epu = float(epu_data[0][1])
        epu_values = [float(r[1]) for r in epu_data if r[1] is not None]
        epu_score = calculate_percentile(current_epu, epu_values)
        components["epu_percentile"] = epu_score

    # Trade Policy Uncertainty
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'EPUTRADE' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 60
    """, (as_of_date,))
    tpu_data = cur.fetchall()

    tpu_score = 50
    if tpu_data:
        current_tpu = float(tpu_data[0][1])
        tpu_values = [float(r[1]) for r in tpu_data if r[1] is not None]
        tpu_score = calculate_percentile(current_tpu, tpu_values)
        components["tpu_percentile"] = tpu_score

    # Executive actions velocity
    cur.execute("""
        SELECT COUNT(*) FROM alt.executive_actions
        WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s
    """, (as_of_date, as_of_date))
    exec_count = cur.fetchone()[0] or 0

    # More than 5 executive actions in a week = high activity
    exec_score = min(100, 30 + (exec_count * 10))
    components["executive_velocity"] = exec_score

    # China ETF stress (FXI)
    cur.execute("""
        SELECT event_date, close FROM mkt.etf_1d
        WHERE symbol = 'FXI' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 63
    """, (as_of_date,))
    fxi_data = cur.fetchall()

    china_score = 50
    if len(fxi_data) > 20:
        fxi_values = [float(r[1]) for r in fxi_data if r[1] is not None]
        fxi_change_20d = (fxi_values[0] - fxi_values[20]) / fxi_values[20] if fxi_values[20] > 0 else 0
        # China selling off = high trump effect pressure
        china_score = 50 - (fxi_change_20d * 300)  # -10% = +30 points
        china_score = float(np.clip(china_score, 0, 100))
        components["china_stress"] = china_score

    # Trump effect specialist signal
    cur.execute("""
        SELECT signal_1, confidence
        FROM training.specialist_signals_1d
        WHERE bucket = 'trump_effect' AND as_of_date <= %s
        ORDER BY as_of_date DESC LIMIT 1
    """, (as_of_date,))
    trump_signal = cur.fetchone()

    signal_score = 50
    if trump_signal and trump_signal[0] is not None:
        # Negative signal = bearish from trump effect = more pressure
        signal_score = 50 - (float(trump_signal[0]) * 30)
        signal_score = float(np.clip(signal_score, 0, 100))
        components["trump_specialist"] = signal_score

    # Composite score
    weights = {"epu_percentile": 0.25, "tpu_percentile": 0.25, "executive_velocity": 0.20,
               "china_stress": 0.15, "trump_specialist": 0.15}
    score = float(np.clip(sum(components.get(k, 50) * w for k, w in weights.items()), 0, 100))

    # Sparkline
    sparkline = [calculate_percentile(float(r[1]), [float(x[1]) for x in epu_data])
                 for r in reversed(epu_data[:10])] if len(epu_data) >= 10 else [50] * 10
    momentum = calculate_momentum(sparkline)

    level = score_to_level(score)
    trend = momentum_to_trend(momentum)

    # Regime
    if score >= 70:
        regime = "high_uncertainty"
    elif score >= 50:
        regime = "elevated_uncertainty"
    else:
        regime = "stable_policy"

    # Narrative
    if score >= 75:
        headline = "Major Policy Uncertainty"
        narrative = f"Policy uncertainty index at {current_epu:.0f} signals high market stress. "
        narrative += f"{exec_count} executive actions in the past week are moving markets."
    elif score >= 60:
        headline = "Policy Shifts Unsettling Markets"
        narrative = "Trade and policy uncertainty is elevated. "
        narrative += "Markets are pricing in potential disruptions."
    elif score >= 40:
        headline = "Moderate Policy Noise"
        narrative = "Some policy uncertainty but markets are digesting changes. "
        narrative += "Watch for escalation signals."
    else:
        headline = "Policy Environment Stable"
        narrative = "Low policy uncertainty supporting risk assets. "
        narrative += "Markets have clarity on near-term policy direction."

    drivers = []
    if components.get("epu_percentile", 50) > 65:
        drivers.append(f"EPU Index at {current_epu:.0f}")
    if components.get("tpu_percentile", 50) > 65:
        drivers.append("Trade policy uncertainty high")
    if components.get("executive_velocity", 50) > 65:
        drivers.append(f"{exec_count} executive actions this week")
    if components.get("china_stress", 50) > 65:
        drivers.append("China equities under pressure")
    if not drivers:
        drivers.append("Policy environment stable")

    return PressureReading(
        name="Trump Effect Pressure",
        score=score,
        level=level,
        trend=trend,
        headline=headline,
        narrative=narrative,
        key_drivers=drivers,
        color=score_to_color(score),
        icon="flag",
        sparkline=sparkline,
        percentile_30d=calculate_percentile(score, sparkline[-30:]) if len(sparkline) >= 30 else 50.0,
        percentile_1y=50.0,
        regime=regime,
        momentum=momentum,
        as_of_date=as_of_date,
        components=components,
    )


# =============================================================================
# TRADE PRESSURE
# =============================================================================

def calculate_trade_pressure(conn, as_of_date: Optional[date] = None) -> PressureReading:
    """
    Trade Pressure: Global shipping and trade flow stress.

    Measures disruptions to global commodity trade.
    High pressure = trade disruptions = supply chain stress.

    Components:
    - Shipping ETFs (BDRY, SBLK) as Baltic Dry proxy
    - China specialist signal
    - Brazil FX stress (BRL weakness)
    - Trade news velocity
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # Shipping ETFs (BDRY = Baltic Dry proxy)
    cur.execute("""
        SELECT event_date, close FROM mkt.etf_1d
        WHERE symbol = 'BDRY' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 63
    """, (as_of_date,))
    bdry_data = cur.fetchall()

    shipping_score = 50
    if len(bdry_data) > 20:
        bdry_values = [float(r[1]) for r in bdry_data if r[1] is not None]
        bdry_ma = np.mean(bdry_values[:20])
        bdry_current = bdry_values[0]
        # Below average = weak shipping = trade stress
        shipping_deviation = (bdry_current - bdry_ma) / bdry_ma if bdry_ma > 0 else 0
        shipping_score = 50 - (shipping_deviation * 200)  # 25% below = +50 points
        shipping_score = float(np.clip(shipping_score, 0, 100))
        components["shipping_stress"] = shipping_score

    # China specialist signal
    cur.execute("""
        SELECT signal_1, confidence
        FROM training.specialist_signals_1d
        WHERE bucket = 'china' AND as_of_date <= %s
        ORDER BY as_of_date DESC LIMIT 1
    """, (as_of_date,))
    china_signal = cur.fetchone()

    china_score = 50
    if china_signal and china_signal[0] is not None:
        china_score = 50 - (float(china_signal[0]) * 30)
        china_score = float(np.clip(china_score, 0, 100))
        components["china_specialist"] = china_score

    # Brazil FX (BRL weakness = trade stress)
    cur.execute("""
        SELECT event_date, value FROM econ.rates_1d
        WHERE series_id = 'DEXBZUS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 63
    """, (as_of_date,))
    brl_data = cur.fetchall()

    brl_score = 50
    if len(brl_data) > 20:
        brl_values = [float(r[1]) for r in brl_data if r[1] is not None]
        if len(brl_values) > 20:
            brl_change = (brl_values[0] - brl_values[20]) / brl_values[20] if brl_values[20] > 0 else 0
        else:
            brl_change = 0
        # BRL weakening (rising USD/BRL) = stress
        brl_score = 50 + (brl_change * 300)
        brl_score = float(np.clip(brl_score, 0, 100))
        components["brazil_fx"] = brl_score

    # Trade news velocity
    try:
        cur.execute("""
            SELECT COUNT(*) FROM alt.profarmer_news
            WHERE event_date >= %s - INTERVAL '7 days'
            AND event_date <= %s
            AND (headline ILIKE '%%trade%%' OR headline ILIKE '%%export%%' OR headline ILIKE '%%china%%')
        """, (as_of_date, as_of_date))
        result = cur.fetchone()
        trade_news = result[0] if result else 0
    except Exception:
        trade_news = 0

    news_score = min(100, 30 + (trade_news * 5))
    components["trade_news"] = news_score

    # Composite
    weights = {"shipping_stress": 0.30, "china_specialist": 0.30, "brazil_fx": 0.25, "trade_news": 0.15}
    score = float(np.clip(sum(components.get(k, 50) * w for k, w in weights.items()), 0, 100))

    sparkline = [50] * 10  # Would need historical shipping data
    momentum = 0.0

    level = score_to_level(score)
    trend = momentum_to_trend(momentum)

    regime = "disrupted" if score >= 65 else "stressed" if score >= 50 else "flowing"

    if score >= 70:
        headline = "Trade Flows Disrupted"
        narrative = "Shipping and trade indicators signal significant stress. "
        narrative += "Expect supply chain disruptions and delivery delays."
    elif score >= 55:
        headline = "Trade Showing Strain"
        narrative = "Global trade flows are under pressure. "
        narrative += "Monitor China demand and shipping rates closely."
    else:
        headline = "Trade Flows Normal"
        narrative = "Global commodity trade is moving smoothly. "
        narrative += "No major bottlenecks detected."

    drivers = []
    if components.get("shipping_stress", 50) > 60:
        drivers.append("Weak shipping rates")
    if components.get("china_specialist", 50) > 60:
        drivers.append("Bearish China signals")
    if components.get("brazil_fx", 50) > 60:
        drivers.append("BRL weakness")
    if components.get("trade_news", 50) > 60:
        drivers.append("Heavy trade news flow")
    if not drivers:
        drivers.append("Trade flows stable")

    return PressureReading(
        name="Trade Pressure",
        score=score,
        level=level,
        trend=trend,
        headline=headline,
        narrative=narrative,
        key_drivers=drivers,
        color=score_to_color(score),
        icon="truck",
        sparkline=sparkline,
        percentile_30d=50.0,
        percentile_1y=50.0,
        regime=regime,
        momentum=momentum,
        as_of_date=as_of_date,
        components=components,
    )


# =============================================================================
# TARIFF PRESSURE
# =============================================================================

def calculate_tariff_pressure(conn, as_of_date: Optional[date] = None) -> PressureReading:
    """
    Tariff Pressure: Trade policy and tariff uncertainty.

    Measures the threat and impact of tariff actions.
    High pressure = tariff threats/actions = market uncertainty.

    Components:
    - Trade Policy Uncertainty Index
    - Tariff-related EMV Index
    - Tariff specialist signal
    - Legislation velocity (tariff-related)
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # Trade Policy Uncertainty
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'EPUTRADE' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 60
    """, (as_of_date,))
    tpu_data = cur.fetchall()

    tpu_score = 50
    current_tpu = 100
    if tpu_data:
        current_tpu = float(tpu_data[0][1])
        tpu_values = [float(r[1]) for r in tpu_data if r[1] is not None]
        tpu_score = calculate_percentile(current_tpu, tpu_values)
        components["tpu_index"] = tpu_score

    # Trade Policy EMV
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'EMVTRADEPOLEMV' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 60
    """, (as_of_date,))
    emv_data = cur.fetchall()

    emv_score = 50
    if emv_data:
        current_emv = float(emv_data[0][1])
        emv_values = [float(r[1]) for r in emv_data if r[1] is not None]
        emv_score = calculate_percentile(current_emv, emv_values)
        components["emv_trade"] = emv_score

    # Tariff specialist
    cur.execute("""
        SELECT signal_1, confidence
        FROM training.specialist_signals_1d
        WHERE bucket = 'tariff' AND as_of_date <= %s
        ORDER BY as_of_date DESC LIMIT 1
    """, (as_of_date,))
    tariff_signal = cur.fetchone()

    signal_score = 50
    if tariff_signal and tariff_signal[0] is not None:
        signal_score = 50 - (float(tariff_signal[0]) * 30)
        signal_score = float(np.clip(signal_score, 0, 100))
        components["tariff_specialist"] = signal_score

    # Legislation velocity
    cur.execute("""
        SELECT COUNT(*) FROM alt.legislation_1d
        WHERE event_date >= %s - INTERVAL '14 days' AND event_date <= %s
    """, (as_of_date, as_of_date))
    legis_count = cur.fetchone()[0] or 0

    legis_score = min(100, 20 + (legis_count * 2))
    components["legislation"] = legis_score

    # Composite
    weights = {"tpu_index": 0.35, "emv_trade": 0.25, "tariff_specialist": 0.25, "legislation": 0.15}
    score = float(np.clip(sum(components.get(k, 50) * w for k, w in weights.items()), 0, 100))

    sparkline = [calculate_percentile(float(r[1]), [float(x[1]) for x in tpu_data])
                 for r in reversed(tpu_data[:10])] if len(tpu_data) >= 10 else [50] * 10
    momentum = calculate_momentum(sparkline)

    level = score_to_level(score)
    trend = momentum_to_trend(momentum)

    regime = "tariff_war" if score >= 70 else "tariff_risk" if score >= 50 else "tariff_truce"

    if score >= 75:
        headline = "Tariff Threats Escalating"
        narrative = f"Trade policy uncertainty at {current_tpu:.0f} signals active tariff risk. "
        narrative += "Markets pricing in potential trade disruptions."
    elif score >= 55:
        headline = "Tariff Uncertainty Elevated"
        narrative = "Tariff rhetoric is impacting market sentiment. "
        narrative += "Watch for escalation or de-escalation signals."
    else:
        headline = "Tariff Environment Stable"
        narrative = "No imminent tariff threats detected. "
        narrative += "Trade policy relatively predictable."

    drivers = []
    if components.get("tpu_index", 50) > 65:
        drivers.append(f"TPU Index at {current_tpu:.0f}")
    if components.get("emv_trade", 50) > 65:
        drivers.append("Trade EMV elevated")
    if components.get("tariff_specialist", 50) > 60:
        drivers.append("Tariff specialist bearish")
    if components.get("legislation", 50) > 60:
        drivers.append(f"{legis_count} trade bills this month")
    if not drivers:
        drivers.append("Tariff environment calm")

    return PressureReading(
        name="Tariff Pressure",
        score=score,
        level=level,
        trend=trend,
        headline=headline,
        narrative=narrative,
        key_drivers=drivers,
        color=score_to_color(score),
        icon="shield",
        sparkline=sparkline,
        percentile_30d=calculate_percentile(score, sparkline[-30:]) if len(sparkline) >= 30 else 50.0,
        percentile_1y=50.0,
        regime=regime,
        momentum=momentum,
        as_of_date=as_of_date,
        components=components,
    )


# =============================================================================
# CORRELATION PRESSURE
# =============================================================================

def calculate_correlation_pressure(conn, as_of_date: Optional[date] = None) -> PressureReading:
    """
    Correlation Pressure: Cross-asset correlation regimes.

    Measures whether assets are moving together (risk-off) or diverging.
    High pressure = high correlations = risk-off regime.

    Components:
    - SPY-TLT correlation (negative = risk-on, positive = stress)
    - Commodity correlation clustering
    - FX correlation (DXY rallies with risk-off)
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # Get SPY and TLT for correlation
    cur.execute("""
        SELECT e1.event_date, e1.close as spy, e2.close as tlt
        FROM mkt.etf_1d e1
        JOIN mkt.etf_1d e2 ON e1.event_date = e2.event_date AND e2.symbol = 'TLT'
        WHERE e1.symbol = 'SPY' AND e1.event_date <= %s
        ORDER BY e1.event_date DESC
        LIMIT 63
    """, (as_of_date,))
    spy_tlt = cur.fetchall()

    corr_score = 50
    if len(spy_tlt) > 20:
        spy_rets = []
        tlt_rets = []
        for i in range(len(spy_tlt) - 1):
            spy_ret = (spy_tlt[i][1] - spy_tlt[i+1][1]) / spy_tlt[i+1][1]
            tlt_ret = (spy_tlt[i][2] - spy_tlt[i+1][2]) / spy_tlt[i+1][2]
            spy_rets.append(spy_ret)
            tlt_rets.append(tlt_ret)

        if len(spy_rets) > 10:
            correlation = np.corrcoef(spy_rets[:20], tlt_rets[:20])[0, 1]
            # Typically negative (-0.3 to -0.5). Positive = stress
            corr_score = 50 + (correlation * 50)  # +1 corr = 100, -1 corr = 0
            corr_score = float(np.clip(corr_score, 0, 100))
            components["spy_tlt_corr"] = corr_score

    # Get GLD for safe haven flows
    cur.execute("""
        SELECT e1.event_date, e1.close as spy, e2.close as gld
        FROM mkt.etf_1d e1
        JOIN mkt.etf_1d e2 ON e1.event_date = e2.event_date AND e2.symbol = 'GLD'
        WHERE e1.symbol = 'SPY' AND e1.event_date <= %s
        ORDER BY e1.event_date DESC
        LIMIT 63
    """, (as_of_date,))
    spy_gld = cur.fetchall()

    gold_corr_score = 50
    if len(spy_gld) > 20:
        spy_rets = []
        gld_rets = []
        for i in range(len(spy_gld) - 1):
            spy_ret = (spy_gld[i][1] - spy_gld[i+1][1]) / spy_gld[i+1][1]
            gld_ret = (spy_gld[i][2] - spy_gld[i+1][2]) / spy_gld[i+1][2]
            spy_rets.append(spy_ret)
            gld_rets.append(gld_ret)

        if len(spy_rets) > 10:
            gold_corr = np.corrcoef(spy_rets[:20], gld_rets[:20])[0, 1]
            # Negative SPY-GLD = flight to safety = stress
            gold_corr_score = 50 - (gold_corr * 40)
            gold_corr_score = float(np.clip(gold_corr_score, 0, 100))
            components["spy_gld_corr"] = gold_corr_score

    # FX stress (UUP strength)
    cur.execute("""
        SELECT event_date, close FROM mkt.etf_1d
        WHERE symbol = 'UUP' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 21
    """, (as_of_date,))
    uup_data = cur.fetchall()

    uup_score = 50
    if len(uup_data) > 10:
        uup_values = [float(r[1]) for r in uup_data if r[1] is not None]
        uup_change = (uup_values[0] - uup_values[-1]) / uup_values[-1] if uup_values[-1] > 0 else 0
        # DXY strength = risk-off
        uup_score = 50 + (uup_change * 500)
        uup_score = float(np.clip(uup_score, 0, 100))
        components["dxy_strength"] = uup_score

    # Composite
    weights = {"spy_tlt_corr": 0.40, "spy_gld_corr": 0.35, "dxy_strength": 0.25}
    score = float(np.clip(sum(components.get(k, 50) * w for k, w in weights.items()), 0, 100))

    sparkline = [50] * 10
    momentum = 0.0

    level = score_to_level(score)
    trend = momentum_to_trend(momentum)

    regime = "risk_off" if score >= 65 else "transitioning" if score >= 45 else "risk_on"

    if score >= 70:
        headline = "Risk-Off Regime Active"
        narrative = "Assets are moving in lockstep. Typical risk-off behavior. "
        narrative += "Expect defensive positioning to dominate."
    elif score >= 55:
        headline = "Correlations Elevated"
        narrative = "Cross-asset correlations are rising. "
        narrative += "Market may be transitioning to risk-off."
    else:
        headline = "Risk-On Environment"
        narrative = "Assets are differentiating normally. "
        narrative += "Investors are comfortable with risk."

    drivers = []
    if components.get("spy_tlt_corr", 50) > 60:
        drivers.append("SPY-TLT correlation rising")
    if components.get("spy_gld_corr", 50) > 60:
        drivers.append("Gold acting as safe haven")
    if components.get("dxy_strength", 50) > 60:
        drivers.append("Dollar strengthening")
    if not drivers:
        drivers.append("Normal diversification")

    return PressureReading(
        name="Correlation Pressure",
        score=score,
        level=level,
        trend=trend,
        headline=headline,
        narrative=narrative,
        key_drivers=drivers,
        color=score_to_color(score),
        icon="git-merge",
        sparkline=sparkline,
        percentile_30d=50.0,
        percentile_1y=50.0,
        regime=regime,
        momentum=momentum,
        as_of_date=as_of_date,
        components=components,
    )


# =============================================================================
# GLOBAL NEWS PRESSURE
# =============================================================================

def calculate_news_pressure(conn, as_of_date: Optional[date] = None) -> PressureReading:
    """
    Global News Pressure: News velocity and sentiment.

    Measures the intensity and tone of news flow.
    High pressure = high news velocity = market uncertainty.

    Components:
    - Total news velocity across all sources
    - Trump-related news concentration
    - FRED blog velocity (Fed communications)
    - ProFarmer velocity (ag-specific)
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # Total news this week vs baseline
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

    velocity_ratio = total_week / baseline_weekly if baseline_weekly > 0 else 1
    velocity_score = 30 + (velocity_ratio - 1) * 35  # 2x velocity = 65
    velocity_score = float(np.clip(velocity_score, 0, 100))
    components["news_velocity"] = velocity_score

    # Trump-related concentration (search headline/content for keywords)
    try:
        cur.execute("""
            SELECT COUNT(*) FROM alt.profarmer_news
            WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s
            AND (headline ILIKE '%%trump%%' OR headline ILIKE '%%tariff%%' OR content ILIKE '%%trump%%')
        """, (as_of_date, as_of_date))
        result = cur.fetchone()
        trump_count = result[0] if result else 0
    except Exception:
        trump_count = 0

    trump_score = min(100, 30 + (trump_count * 8))
    components["trump_concentration"] = trump_score

    # Executive action intensity
    cur.execute("""
        SELECT COUNT(*) FROM alt.executive_actions
        WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s
    """, (as_of_date, as_of_date))
    exec_count = cur.fetchone()[0] or 0

    exec_score = min(100, 30 + (exec_count * 10))
    components["executive_velocity"] = exec_score

    # Composite
    weights = {"news_velocity": 0.40, "trump_concentration": 0.35, "executive_velocity": 0.25}
    score = float(np.clip(sum(components.get(k, 50) * w for k, w in weights.items()), 0, 100))

    sparkline = [50] * 10
    momentum = 0.0

    level = score_to_level(score)
    trend = momentum_to_trend(momentum)

    regime = "news_storm" if score >= 70 else "active_news" if score >= 50 else "quiet_news"

    if score >= 75:
        headline = "News Flow Surging"
        narrative = f"{total_week} articles this week, {velocity_ratio:.1f}x normal velocity. "
        narrative += "Heavy news flow often precedes market moves."
    elif score >= 55:
        headline = "Active News Cycle"
        narrative = "Above-average news velocity. "
        narrative += "Markets processing multiple narratives."
    else:
        headline = "Quiet News Environment"
        narrative = "Normal news flow. "
        narrative += "No major narratives dominating coverage."

    drivers = []
    if components.get("news_velocity", 50) > 60:
        drivers.append(f"{total_week} articles this week")
    if components.get("trump_concentration", 50) > 60:
        drivers.append(f"{trump_count} Trump-related articles")
    if components.get("executive_velocity", 50) > 60:
        drivers.append(f"{exec_count} executive actions")
    if not drivers:
        drivers.append("Light news flow")

    return PressureReading(
        name="Global News Pressure",
        score=score,
        level=level,
        trend=trend,
        headline=headline,
        narrative=narrative,
        key_drivers=drivers,
        color=score_to_color(score),
        icon="newspaper",
        sparkline=sparkline,
        percentile_30d=50.0,
        percentile_1y=50.0,
        regime=regime,
        momentum=momentum,
        as_of_date=as_of_date,
        components=components,
    )


# =============================================================================
# COUNTRY WAR PRESSURE (Geopolitical Risk)
# =============================================================================

def calculate_geopolitical_pressure(conn, as_of_date: Optional[date] = None) -> PressureReading:
    """
    Country War Pressure: Geopolitical risk indicators.

    Measures geopolitical tensions affecting commodity markets.
    High pressure = high geopolitical risk = supply disruption potential.

    Components:
    - Policy uncertainty spikes
    - Energy volatility (conflict often hits oil first)
    - FX volatility in affected regions
    - Defense-related news velocity
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # EPU spikes (geopolitical often causes EPU jumps)
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'USEPUINDXD' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 30
    """, (as_of_date,))
    epu_data = cur.fetchall()

    epu_spike_score = 50
    if len(epu_data) > 5:
        epu_values = [float(r[1]) for r in epu_data if r[1] is not None]
        recent_avg = np.mean(epu_values[:5])
        month_avg = np.mean(epu_values)
        spike_ratio = recent_avg / month_avg if month_avg > 0 else 1
        epu_spike_score = 30 + ((spike_ratio - 1) * 80)
        epu_spike_score = float(np.clip(epu_spike_score, 0, 100))
        components["epu_spike"] = epu_spike_score

    # OVX (oil volatility - geopolitical often hits energy)
    cur.execute("""
        SELECT event_date, value FROM econ.vol_indices_1d
        WHERE series_id = 'OVXCLS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 63
    """, (as_of_date,))
    ovx_data = cur.fetchall()

    ovx_score = 50
    if ovx_data:
        current_ovx = float(ovx_data[0][1])
        ovx_values = [float(r[1]) for r in ovx_data if r[1] is not None]
        ovx_score = calculate_percentile(current_ovx, ovx_values)
        components["oil_volatility"] = ovx_score

    # EM FX stress (often first casualty of geopolitical risk)
    cur.execute("""
        SELECT event_date, value FROM econ.rates_1d
        WHERE series_id = 'DTWEXEMEGS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 21
    """, (as_of_date,))
    em_fx = cur.fetchall()

    em_score = 50
    if len(em_fx) > 10:
        em_values = [float(r[1]) for r in em_fx if r[1] is not None]
        em_change = (em_values[0] - em_values[-1]) / em_values[-1] if em_values[-1] > 0 else 0
        # EM weakness = geopolitical stress
        em_score = 50 + (em_change * 500)
        em_score = float(np.clip(em_score, 0, 100))
        components["em_fx_stress"] = em_score

    # Gold as fear proxy
    cur.execute("""
        SELECT event_date, close FROM mkt.etf_1d
        WHERE symbol = 'GLD' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 21
    """, (as_of_date,))
    gld_data = cur.fetchall()

    gold_score = 50
    if len(gld_data) > 10:
        gld_values = [float(r[1]) for r in gld_data if r[1] is not None]
        gld_change = (gld_values[0] - gld_values[-1]) / gld_values[-1] if gld_values[-1] > 0 else 0
        # Gold surge = fear/geopolitical risk
        gold_score = 50 + (gld_change * 300)
        gold_score = float(np.clip(gold_score, 0, 100))
        components["gold_fear"] = gold_score

    # Composite
    weights = {"epu_spike": 0.30, "oil_volatility": 0.25, "em_fx_stress": 0.25, "gold_fear": 0.20}
    score = float(np.clip(sum(components.get(k, 50) * w for k, w in weights.items()), 0, 100))

    sparkline = [50] * 10
    momentum = 0.0

    level = score_to_level(score)
    trend = momentum_to_trend(momentum)

    regime = "conflict_risk" if score >= 70 else "tension" if score >= 50 else "stable"

    if score >= 75:
        headline = "Geopolitical Risk Elevated"
        narrative = "Multiple indicators signal heightened geopolitical tensions. "
        narrative += "Expect supply disruption fears to support commodity prices."
    elif score >= 55:
        headline = "Geopolitical Tensions Rising"
        narrative = "Markets are pricing in some geopolitical risk. "
        narrative += "Watch for escalation signals."
    else:
        headline = "Geopolitical Environment Stable"
        narrative = "No major geopolitical flashpoints detected. "
        narrative += "Markets focused on fundamentals."

    drivers = []
    if components.get("epu_spike", 50) > 60:
        drivers.append("Policy uncertainty spiking")
    if components.get("oil_volatility", 50) > 60:
        drivers.append("Oil volatility elevated")
    if components.get("em_fx_stress", 50) > 60:
        drivers.append("EM currencies under pressure")
    if components.get("gold_fear", 50) > 60:
        drivers.append("Gold catching bids")
    if not drivers:
        drivers.append("Geopolitical calm")

    return PressureReading(
        name="Country War Pressure",
        score=score,
        level=level,
        trend=trend,
        headline=headline,
        narrative=narrative,
        key_drivers=drivers,
        color=score_to_color(score),
        icon="globe",
        sparkline=sparkline,
        percentile_30d=50.0,
        percentile_1y=50.0,
        regime=regime,
        momentum=momentum,
        as_of_date=as_of_date,
        components=components,
    )


# =============================================================================
# VISUAL ENHANCEMENT
# =============================================================================

def enhance_with_visuals(reading: PressureReading) -> PressureReading:
    """Add rich visual elements to a pressure reading."""
    reading.visual = generate_visual_cue(reading.score, reading.momentum, reading.level)
    reading.forecast = generate_forecast(reading.score, reading.momentum, reading.sparkline)
    reading.graphic = generate_narrative_graphic(
        reading.name, reading.score, reading.momentum, reading.level, reading.sparkline
    )
    return reading


# =============================================================================
# MAIN INTERFACE
# =============================================================================

def dict_to_pressure_reading(data: Dict) -> PressureReading:
    """Convert dict from domain calculator to PressureReading object."""
    # Map level string to enum
    level_map = {
        "Extreme Pressure": PressureLevel.EXTREME,
        "High Pressure": PressureLevel.HIGH,
        "Elevated": PressureLevel.ELEVATED,
        "Normal": PressureLevel.NORMAL,
        "Low Pressure": PressureLevel.LOW,
        "Very Low": PressureLevel.VERY_LOW,
        # Greed-specific levels
        "Extreme Greed": PressureLevel.EXTREME,
        "Greed": PressureLevel.HIGH,
        "Cautious Optimism": PressureLevel.ELEVATED,
        "Neutral": PressureLevel.NORMAL,
        "Fear": PressureLevel.LOW,
        "High Fear": PressureLevel.LOW,
        "Extreme Fear": PressureLevel.VERY_LOW,
    }

    # Map trend string to enum
    trend_map = {
        "Surging": TrendDirection.SURGING,
        "Rising": TrendDirection.RISING,
        "Stable": TrendDirection.STABLE,
        "Falling": TrendDirection.FALLING,
        "Plunging": TrendDirection.PLUNGING,
        # Policy-specific
        "Uncertainty Rising": TrendDirection.SURGING,
        "Slight Increase": TrendDirection.RISING,
        "Uncertainty Falling": TrendDirection.FALLING,
        "Slight Decrease": TrendDirection.FALLING,
        # Tariff-specific
        "Tariff Risk Rising": TrendDirection.SURGING,
        "Tariff Risk Falling": TrendDirection.FALLING,
        # Greed-specific
        "Greed Rising": TrendDirection.SURGING,
        "Sentiment Improving": TrendDirection.RISING,
        "Fear Building": TrendDirection.PLUNGING,
        "Sentiment Weakening": TrendDirection.FALLING,
    }

    level = level_map.get(data.get("level", "Normal"), PressureLevel.NORMAL)
    trend = trend_map.get(data.get("trend", "Stable"), TrendDirection.STABLE)

    return PressureReading(
        name=data.get("name", "Unknown"),
        score=data.get("score", 50.0),
        level=level,
        trend=trend,
        headline=data.get("headline", ""),
        narrative=data.get("narrative", ""),
        key_drivers=data.get("key_drivers", []),
        color=data.get("color", "#6B7280"),
        icon=data.get("icon", "bar-chart-2"),
        sparkline=data.get("sparkline", [50] * 10),
        percentile_30d=data.get("percentile_30d", 50.0),
        percentile_1y=data.get("percentile_1y", 50.0),
        regime=data.get("regime", "unknown"),
        momentum=data.get("momentum", 0.0),
        as_of_date=date.fromisoformat(data["as_of_date"]) if "as_of_date" in data else date.today(),
        components=data.get("components", {}),
    )


def get_all_pressures(as_of_date: Optional[date] = None, with_visuals: bool = True) -> Dict[str, PressureReading]:
    """
    Get all pressure readings for the dashboard.

    Uses domain-specific calculators from pressures/ directory.
    Each calculator uses real domain expertise, not generic percentile scoring.

    Returns dict keyed by pressure name with full PressureReading objects.

    Args:
        as_of_date: Date for calculations (default: today)
        with_visuals: Include rich visual elements (default: True)
    """
    conn = get_connection()

    pressures = {}

    try:
        # Call domain-specific calculators (they return dicts)
        crush_data = _calc_crush(conn, as_of_date)
        vol_data = _calc_vol(conn, as_of_date)
        greed_data = _calc_greed(conn, as_of_date)
        trump_data = _calc_trump(conn, as_of_date)
        tariff_data = _calc_tariff(conn, as_of_date)
        trade_data = _calc_trade(conn, as_of_date)
        corr_data = _calc_corr(conn, as_of_date)
        news_data = _calc_news(conn, as_of_date)
        geo_data = _calc_geo(conn, as_of_date)

        # Convert dicts to PressureReading objects
        pressures["crush"] = dict_to_pressure_reading(crush_data)
        pressures["volatility"] = dict_to_pressure_reading(vol_data)
        pressures["greed"] = dict_to_pressure_reading(greed_data)
        pressures["trump_effect"] = dict_to_pressure_reading(trump_data)
        pressures["tariff"] = dict_to_pressure_reading(tariff_data)
        pressures["trade"] = dict_to_pressure_reading(trade_data)
        pressures["correlation"] = dict_to_pressure_reading(corr_data)
        pressures["news"] = dict_to_pressure_reading(news_data)
        pressures["geopolitical"] = dict_to_pressure_reading(geo_data)

        # Store domain context for richer output
        pressures["crush"].components["_domain_context"] = crush_data.get("domain_context", {})
        pressures["volatility"].components["_domain_context"] = vol_data.get("domain_context", {})
        pressures["greed"].components["_domain_context"] = greed_data.get("domain_context", {})
        pressures["trump_effect"].components["_domain_context"] = trump_data.get("domain_context", {})
        pressures["tariff"].components["_domain_context"] = tariff_data.get("domain_context", {})
        pressures["trade"].components["_domain_context"] = trade_data.get("domain_context", {})
        pressures["correlation"].components["_domain_context"] = corr_data.get("domain_context", {})
        pressures["news"].components["_domain_context"] = news_data.get("domain_context", {})
        pressures["geopolitical"].components["_domain_context"] = geo_data.get("domain_context", {})

    finally:
        conn.close()

    # Enhance with rich visuals
    if with_visuals:
        for key in pressures:
            pressures[key] = enhance_with_visuals(pressures[key])

    return pressures


def get_pressure_summary(as_of_date: Optional[date] = None) -> Dict:
    """
    Get a dashboard-ready summary of all pressures.

    Returns dict with all pressures formatted for JSON/frontend consumption.
    """
    pressures = get_all_pressures(as_of_date)

    return {
        "as_of_date": (as_of_date or date.today()).isoformat(),
        "generated_at": datetime.utcnow().isoformat(),
        "pressures": {k: v.to_dict() for k, v in pressures.items()},
        "overall_stress": np.mean([p.score for p in pressures.values()]),
    }


if __name__ == "__main__":
    import json

    print("=" * 60)
    print("ZINC-FUSION-V15: Narrative Pressure Engine")
    print("=" * 60)

    summary = get_pressure_summary()

    print(f"\nAs of: {summary['as_of_date']}")
    print(f"Overall Stress: {summary['overall_stress']:.1f}/100")
    print("\n" + "-" * 60)

    for name, pressure in summary["pressures"].items():
        print(f"\n{pressure['name']}")
        print(f"  Score: {pressure['score']}/100 ({pressure['level']})")
        print(f"  Trend: {pressure['trend']}")
        print(f"  Headline: {pressure['headline']}")
        print(f"  Narrative: {pressure['narrative']}")
        print(f"  Drivers: {', '.join(pressure['key_drivers'])}")
        print(f"  Regime: {pressure['regime']}")
