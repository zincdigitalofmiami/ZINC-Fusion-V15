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

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from fusion.db.connection import get_write_connection

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
    badge_text: Optional[str]  # Badge overlay text


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
            "components": {
                k: (round(v, 3) if isinstance(v, (int, float)) else v)
                for k, v in self.components.items()
            },
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
                "forward_curve": [
                    (d, round(v, 1)) for d, v in self.forecast.forward_curve
                ],
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
    return get_write_connection()


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
    return float(
        np.percentile(
            [value] + historical,
            (np.searchsorted(sorted(historical), value) / len(historical)) * 100,
        )
    )


def calculate_momentum(values: List[float], window: int = 5) -> float:
    """Calculate momentum as normalized rate of change."""
    if len(values) < window + 1:
        return 0.0
    recent = np.mean(values[-window:])
    earlier = (
        np.mean(values[-(window * 2) : -window])
        if len(values) >= window * 2
        else values[0]
    )
    if earlier == 0:
        return 0.0
    raw_momentum = (recent - earlier) / abs(earlier)
    return float(np.clip(raw_momentum, -1, 1))


def generate_visual_cue(
    score: float, momentum: float, level: PressureLevel
) -> VisualCue:
    """Generate rich visual styling based on pressure state."""

    # Color palettes for each level
    palettes = {
        PressureLevel.EXTREME: {
            "base": "#DC2626",
            "gradient": [
                "#FEE2E2",
                "#FECACA",
                "#FCA5A5",
                "#F87171",
                "#EF4444",
                "#DC2626",
            ],
            "sparkline": ["#FEE2E2", "#DC2626"],
            "glow": 0.9,
            "pulse": "fast",
            "alert": "critical",
        },
        PressureLevel.HIGH: {
            "base": "#EA580C",
            "gradient": [
                "#FFEDD5",
                "#FED7AA",
                "#FDBA74",
                "#FB923C",
                "#F97316",
                "#EA580C",
            ],
            "sparkline": ["#FFEDD5", "#EA580C"],
            "glow": 0.7,
            "pulse": "medium",
            "alert": "warning",
        },
        PressureLevel.ELEVATED: {
            "base": "#D97706",
            "gradient": [
                "#FEF3C7",
                "#FDE68A",
                "#FCD34D",
                "#FBBF24",
                "#F59E0B",
                "#D97706",
            ],
            "sparkline": ["#FEF3C7", "#D97706"],
            "glow": 0.5,
            "pulse": "slow",
            "alert": "watch",
        },
        PressureLevel.NORMAL: {
            "base": "#65A30D",
            "gradient": [
                "#ECFCCB",
                "#D9F99D",
                "#BEF264",
                "#A3E635",
                "#84CC16",
                "#65A30D",
            ],
            "sparkline": ["#ECFCCB", "#65A30D"],
            "glow": 0.2,
            "pulse": "none",
            "alert": "none",
        },
        PressureLevel.LOW: {
            "base": "#0891B2",
            "gradient": [
                "#CFFAFE",
                "#A5F3FC",
                "#67E8F9",
                "#22D3EE",
                "#06B6D4",
                "#0891B2",
            ],
            "sparkline": ["#CFFAFE", "#0891B2"],
            "glow": 0.1,
            "pulse": "none",
            "alert": "none",
        },
        PressureLevel.VERY_LOW: {
            "base": "#0284C7",
            "gradient": [
                "#E0F2FE",
                "#BAE6FD",
                "#7DD3FC",
                "#38BDF8",
                "#0EA5E9",
                "#0284C7",
            ],
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


def generate_forecast(
    score: float, momentum: float, sparkline: List[float]
) -> ForecastData:
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
        "Greed Pressure Index": "trending-up"
        if score > 60
        else "trending-down"
        if score < 40
        else "minus",
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
# DOMAIN CALCULATOR ADAPTERS
# =============================================================================


def _from_domain_calculator(
    calculator: Callable[[object, Optional[date]], Dict],
    conn,
    as_of_date: Optional[date] = None,
) -> PressureReading:
    """Convert a domain calculator dict payload into PressureReading."""
    return dict_to_pressure_reading(calculator(conn, as_of_date))


def calculate_crush_pressure(
    conn, as_of_date: Optional[date] = None
) -> PressureReading:
    """Compatibility wrapper for crush pressure calculation."""
    return _from_domain_calculator(_calc_crush, conn, as_of_date)


def calculate_greed_pressure(
    conn, as_of_date: Optional[date] = None
) -> PressureReading:
    """Compatibility wrapper for greed pressure calculation."""
    return _from_domain_calculator(_calc_greed, conn, as_of_date)


def calculate_volatility_pressure(
    conn, as_of_date: Optional[date] = None
) -> PressureReading:
    """Compatibility wrapper for volatility pressure calculation."""
    return _from_domain_calculator(_calc_vol, conn, as_of_date)


def calculate_trump_effect_pressure(
    conn, as_of_date: Optional[date] = None
) -> PressureReading:
    """Compatibility wrapper for policy pressure calculation."""
    return _from_domain_calculator(_calc_trump, conn, as_of_date)


def calculate_trade_pressure(
    conn, as_of_date: Optional[date] = None
) -> PressureReading:
    """Compatibility wrapper for trade pressure calculation."""
    return _from_domain_calculator(_calc_trade, conn, as_of_date)


def calculate_tariff_pressure(
    conn, as_of_date: Optional[date] = None
) -> PressureReading:
    """Compatibility wrapper for tariff pressure calculation."""
    return _from_domain_calculator(_calc_tariff, conn, as_of_date)


def calculate_correlation_pressure(
    conn, as_of_date: Optional[date] = None
) -> PressureReading:
    """Compatibility wrapper for correlation pressure calculation."""
    return _from_domain_calculator(_calc_corr, conn, as_of_date)


def calculate_news_pressure(conn, as_of_date: Optional[date] = None) -> PressureReading:
    """Compatibility wrapper for news pressure calculation."""
    return _from_domain_calculator(_calc_news, conn, as_of_date)


def calculate_geopolitical_pressure(
    conn, as_of_date: Optional[date] = None
) -> PressureReading:
    """Compatibility wrapper for geopolitical pressure calculation."""
    return _from_domain_calculator(_calc_geo, conn, as_of_date)


# =============================================================================
# VISUAL ENHANCEMENT
# =============================================================================


def enhance_with_visuals(reading: PressureReading) -> PressureReading:
    """Add rich visual elements to a pressure reading."""
    reading.visual = generate_visual_cue(reading.score, reading.momentum, reading.level)
    reading.forecast = generate_forecast(
        reading.score, reading.momentum, reading.sparkline
    )
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
        as_of_date=date.fromisoformat(data["as_of_date"])
        if "as_of_date" in data
        else date.today(),
        components=data.get("components", {}),
    )


def get_all_pressures(
    as_of_date: Optional[date] = None, with_visuals: bool = True
) -> Dict[str, PressureReading]:
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
        pressures["crush"].components["_domain_context"] = crush_data.get(
            "domain_context", {}
        )
        pressures["volatility"].components["_domain_context"] = vol_data.get(
            "domain_context", {}
        )
        pressures["greed"].components["_domain_context"] = greed_data.get(
            "domain_context", {}
        )
        pressures["trump_effect"].components["_domain_context"] = trump_data.get(
            "domain_context", {}
        )
        pressures["tariff"].components["_domain_context"] = tariff_data.get(
            "domain_context", {}
        )
        pressures["trade"].components["_domain_context"] = trade_data.get(
            "domain_context", {}
        )
        pressures["correlation"].components["_domain_context"] = corr_data.get(
            "domain_context", {}
        )
        pressures["news"].components["_domain_context"] = news_data.get(
            "domain_context", {}
        )
        pressures["geopolitical"].components["_domain_context"] = geo_data.get(
            "domain_context", {}
        )

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
