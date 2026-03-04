"""
ZINC-FUSION-V15: China Soy Export Demand Pressure

SOY-CENTRIC pressure gauge for China trade war and import demand risk.
Everything centers on ZL and soybean/soybean oil prices.

KEY PRINCIPLE: China is THE demand driver for US soybeans.
- China imports ~60% of globally traded soybeans
- US competes with Brazil for China market share
- Trade war = immediate soy export demand cliff risk
- CNY weakness = Brazil more competitive vs US

This is primarily a TRADE WAR indicator mixed with China import/export dynamics.

Priority Components (Soy-Centric Weighting):

1. SHIPPING COSTS (BDIY, FRED) - 30% weight
   - Baltic Dry Index = direct soy trade flow proxy
   - Falling rates = weak China commodity demand
   - Soy ships from US Gulf/PNW to China ports
   - Most direct indicator of physical trade activity

2. CNY/USD - 25% weight
   - Yuan weakness makes US soy expensive vs Brazil
   - 7.0 = psychological level
   - 7.2 = PBOC defense line
   - 7.3+ = competitive disadvantage for US soy

3. COPPER (HG futures) - 20% weight
   - China industrial demand proxy
   - Useful for gauging China growth stress

4. Soy Export News (ProFarmer) - 15% weight
   - "China soy", "export sales", "import demand", "trade war"
   - Real-time sentiment from soy-focused news
   - Captures cancellations, buying pace, policy shifts

5. China Specialist Signal - 10% weight
   - ML model signal for China demand

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
# DOMAIN CONSTANTS - China Market Expertise
# ==============================================================================

# Copper (HG) performance thresholds (20-day % change)
HG_CRISIS = -0.15  # 15% drop = crisis
HG_SEVERE = -0.10  # 10% drop = severe stress
HG_STRESS = -0.05  # 5% drop = stress
HG_WEAK = -0.02  # 2% drop = weak
HG_NEUTRAL = 0.02  # +/- 2% = neutral
HG_STRONG = 0.05  # 5% gain = strong
HG_RALLY = 0.10  # 10% gain = rally

# CNY thresholds (USD/CNY rate - higher = weaker yuan)
CNY_STRONG = 7.00  # Below 7 = strong yuan
CNY_STABLE = 7.15  # 7.00-7.15 = stable
CNY_WEAK = 7.30  # 7.15-7.30 = weak
CNY_STRESS = 7.45  # 7.30-7.45 = stress
CNY_CRISIS = 7.60  # Above 7.45 = crisis

# CNY rate of change thresholds (positive = yuan weakening)
CNY_DEVALUING_FAST = 0.02  # 2% weaker in 20 days
CNY_DEVALUING = 0.01  # 1% weaker
CNY_STRENGTHENING = -0.01  # 1% stronger
CNY_STRENGTHENING_FAST = -0.02  # 2% stronger

# Shipping cost (BDIY) thresholds - 20 day change
SHIP_COLLAPSE = -0.25  # 25% drop - soy trade frozen
SHIP_WEAK = -0.10  # 10% drop - demand concerns
SHIP_STABLE = 0.10  # +/- 10% = normal trade flow
SHIP_STRONG = 0.20  # 20% gain - robust demand

# Soy-specific news keywords for China trade war monitoring
SOY_CHINA_KEYWORDS = [
    "china soy",
    "chinese soy",
    "soybean export",
    "soy export",
    "export sales",
    "import demand",
    "trade war",
    "tariff",
    "retaliatory",
    "brazil soy",
    "us soy",
    "soybean import",
    "china buying",
    "china purchase",
    "cancellation",
    "cancelled",
]


@dataclass
class ChinaRegime:
    """China tension regime classification."""

    name: str
    description: str
    soy_impact: str
    trading_action: str


CHINA_REGIMES = {
    "crisis": ChinaRegime(
        name="Soy Export Crisis",
        description="Trade war escalation. Tariffs active, retaliatory duties on US soy.",
        soy_impact="ZL BEARISH. Export demand cliff. China buying Brazil instead. Cancellations likely. Gulf basis collapsing.",
        trading_action="Sell rallies. Watch USDA export sales for cancellations. Brazil FOB premiums.",
    ),
    "high_tension": ChinaRegime(
        name="High Trade War Risk",
        description="Active tariff threats. China demand uncertain. Shipping weak.",
        soy_impact="ZL CAUTIOUS. Export pace slowing. Brazil gaining market share. Basis under pressure.",
        trading_action="Reduce long exposure. Hedge new crop sales. Watch weekly export inspections.",
    ),
    "elevated": ChinaRegime(
        name="Elevated Trade Tension",
        description="Headlines active. Trade negotiations uncertain. Some demand concerns.",
        soy_impact="ZL NEUTRAL-CAUTIOUS. Export sales pace needs monitoring. Some basis volatility.",
        trading_action="Watch export sales reports closely. Position for volatility.",
    ),
    "normal": ChinaRegime(
        name="Normal Trade Flow",
        description="Standard US-China soy trade dynamics. No acute tension.",
        soy_impact="ZL trading on fundamentals. Normal export pace. Basis stable.",
        trading_action="Trade fundamentals - weather, crush margins, WASDE.",
    ),
    "constructive": ChinaRegime(
        name="Constructive Demand",
        description="Trade relations stable/improving. China actively buying US soy.",
        soy_impact="ZL SUPPORTIVE. Strong export sales. Good shipping pace. Basis firm.",
        trading_action="Bullish demand backdrop. Look for buying opportunities on dips.",
    ),
}


def score_hg_performance(change_20d: float, change_5d: float) -> Tuple[float, str]:
    """
    Score HG (copper) performance as China demand proxy.

    Returns (score, description) where higher = more tension.
    """
    # 20-day trend is primary
    if change_20d <= HG_CRISIS:
        base = 90
        desc = "Copper in freefall"
    elif change_20d <= HG_SEVERE:
        pct = (change_20d - HG_CRISIS) / (HG_SEVERE - HG_CRISIS)
        base = 80 + (1 - pct) * 10
        desc = "Copper severely weak"
    elif change_20d <= HG_STRESS:
        pct = (change_20d - HG_SEVERE) / (HG_STRESS - HG_SEVERE)
        base = 65 + (1 - pct) * 15
        desc = "Copper under pressure"
    elif change_20d <= HG_WEAK:
        pct = (change_20d - HG_STRESS) / (HG_WEAK - HG_STRESS)
        base = 55 + (1 - pct) * 10
        desc = "Copper soft"
    elif change_20d <= HG_NEUTRAL:
        base = 45
        desc = "Copper stable"
    elif change_20d <= HG_STRONG:
        pct = (change_20d - HG_NEUTRAL) / (HG_STRONG - HG_NEUTRAL)
        base = 45 - (pct * 10)
        desc = "Copper firming"
    elif change_20d <= HG_RALLY:
        pct = (change_20d - HG_STRONG) / (HG_RALLY - HG_STRONG)
        base = 35 - (pct * 10)
        desc = "Copper rallying"
    else:
        base = 20
        desc = "Copper surging"

    # Short-term momentum modifier
    if change_5d < -0.05:
        base = min(100, base + 10)
        desc += " (accelerating weakness)"
    elif change_5d > 0.05:
        base = max(0, base - 5)
        desc += " (near-term bounce)"

    return float(np.clip(base, 0, 100)), desc


def score_cny_level(rate: float, change_20d: float) -> Tuple[float, str]:
    """
    Score CNY stress level.

    Returns (score, description) where higher = more tension.
    """
    # Absolute level
    if rate < CNY_STRONG:
        level_score = 25
        level_desc = "Yuan strong"
    elif rate < CNY_STABLE:
        level_score = 35
        level_desc = "Yuan stable"
    elif rate < CNY_WEAK:
        level_score = 50
        level_desc = "Yuan slightly weak"
    elif rate < CNY_STRESS:
        level_score = 65
        level_desc = "Yuan weak"
    elif rate < CNY_CRISIS:
        level_score = 80
        level_desc = "Yuan under pressure"
    else:
        level_score = 90
        level_desc = "Yuan crisis level"

    # Rate of change modifier
    if change_20d >= CNY_DEVALUING_FAST:
        roc_adj = 15
        roc_desc = ", devaluing rapidly"
    elif change_20d >= CNY_DEVALUING:
        roc_adj = 8
        roc_desc = ", weakening"
    elif change_20d <= CNY_STRENGTHENING_FAST:
        roc_adj = -15
        roc_desc = ", strengthening rapidly"
    elif change_20d <= CNY_STRENGTHENING:
        roc_adj = -8
        roc_desc = ", firming"
    else:
        roc_adj = 0
        roc_desc = ""

    score = float(np.clip(level_score + roc_adj, 0, 100))
    return score, level_desc + roc_desc


def score_shipping(change_20d: float) -> Tuple[float, str]:
    """
    Score shipping costs (BDIY) as trade flow indicator.

    Returns (score, description) where higher = more tension.
    """
    if change_20d <= SHIP_COLLAPSE:
        return 85, "Shipping rates collapsed"
    elif change_20d <= SHIP_WEAK:
        pct = (change_20d - SHIP_COLLAPSE) / (SHIP_WEAK - SHIP_COLLAPSE)
        score = 70 + (1 - pct) * 15
        return score, "Shipping rates weak"
    elif change_20d <= SHIP_STABLE:
        return 45, "Shipping rates stable"
    elif change_20d <= SHIP_STRONG:
        pct = (change_20d - SHIP_STABLE) / (SHIP_STRONG - SHIP_STABLE)
        score = 45 - (pct * 15)
        return score, "Shipping rates firm"
    else:
        return 25, "Shipping rates surging"


def score_china_news(china_articles: int, total_articles: int) -> Tuple[float, str]:
    """
    Score China news concentration.

    High China coverage often signals tension/disputes.
    Returns (score, description).
    """
    if total_articles == 0:
        return 50, "No news data"

    concentration = china_articles / total_articles

    if china_articles >= 50:  # Raw count also matters
        count_boost = min(20, (china_articles - 30) / 2)
    else:
        count_boost = 0

    if concentration > 0.30:
        return min(
            100, 80 + count_boost
        ), f"Heavy China focus ({china_articles} articles)"
    elif concentration > 0.20:
        return min(
            100, 65 + count_boost
        ), f"Elevated China coverage ({china_articles} articles)"
    elif concentration > 0.10:
        return 50, f"Normal China coverage ({china_articles} articles)"
    else:
        return 35, f"Light China coverage ({china_articles} articles)"


def generate_china_narrative(
    hg_score: float,
    cny_score: float,
    ship_score: float,
    news_score: float,
    specialist_signal: float,
    score: float,
    regime: str,
) -> Tuple[str, str, List[str]]:
    """Generate domain-expert narrative for China tension."""
    regime_info = CHINA_REGIMES.get(regime, CHINA_REGIMES["normal"])

    # Headline
    if score >= 80:
        headline = "China Tension Critical"
    elif score >= 65:
        headline = "High China Tension"
    elif score >= 50:
        headline = "Elevated China Risk"
    elif score >= 35:
        headline = "China Relations Normal"
    else:
        headline = "Constructive China Outlook"

    # Narrative
    parts = [regime_info.description]
    parts.append(regime_info.soy_impact)

    narrative = " ".join(parts)

    # Drivers
    drivers = []

    if hg_score >= 60:
        drivers.append("Copper weak")
    elif hg_score <= 35:
        drivers.append("Copper strong")

    if cny_score >= 60:
        drivers.append("Yuan under pressure")
    elif cny_score <= 35:
        drivers.append("Yuan stable")

    if ship_score >= 60:
        drivers.append("Shipping rates soft")

    if news_score >= 60:
        drivers.append("Heavy China news flow")

    if specialist_signal and specialist_signal < -0.2:
        drivers.append("Bearish China specialist signal")
    elif specialist_signal and specialist_signal > 0.2:
        drivers.append("Bullish China specialist signal")

    if not drivers:
        drivers.append("Balanced China indicators")

    return headline, narrative, drivers


def calculate_china_tension(conn, as_of_date: Optional[date] = None) -> Dict:
    """
    Calculate China Tension pressure.

    Components:
    1. Copper Performance (20%): China demand proxy
    2. CNY Level/Trend (25%): Currency stress
    3. Shipping Costs (30%): Trade flow health
    4. China Specialist (15%): Model signal
    5. News Concentration (10%): Headlines

    Returns PressureReading-compatible dict.
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}

    # ==== 1. COPPER PERFORMANCE (HG futures) ====
    cur.execute(
        """
        SELECT event_date, close FROM mkt.futures_1d
        WHERE symbol = 'HG' AND event_date <= %s AND close IS NOT NULL
        ORDER BY event_date DESC LIMIT 30
    """,
        (as_of_date,),
    )
    hg_data = cur.fetchall()
    if len(hg_data) < 21:
        raise ValueError("Insufficient HG data to compute China tension")

    current_hg = float(hg_data[0][1])
    hg_5d = float(hg_data[5][1]) if len(hg_data) > 5 else None
    hg_20d = float(hg_data[20][1])

    change_20d = (current_hg - hg_20d) / hg_20d if hg_20d > 0 else 0
    change_5d = (current_hg - hg_5d) / hg_5d if hg_5d and hg_5d > 0 else 0

    hg_score, hg_desc = score_hg_performance(change_20d, change_5d)
    components["hg_score"] = round(hg_score, 1)
    components["hg_change_20d"] = round(change_20d * 100, 2)
    components["hg_change_5d"] = round(change_5d * 100, 2)

    # ==== 2. CNY LEVEL/TREND ====
    cur.execute(
        """
        SELECT event_date, value FROM econ.rates_1d
        WHERE series_id = 'DEXCHUS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 25
    """,
        (as_of_date,),
    )
    cny_data = cur.fetchall()

    cny_score = 50
    cny_desc = "No CNY data"
    if len(cny_data) >= 20:
        cny_values = [float(r[1]) for r in cny_data if r[1] is not None]
        current_rate = cny_values[0]
        d20_ago = cny_values[min(20, len(cny_values) - 1)]

        change_20d = (current_rate - d20_ago) / d20_ago if d20_ago > 0 else 0

        cny_score, cny_desc = score_cny_level(current_rate, change_20d)
        components["cny_score"] = round(cny_score, 1)
        components["cny_rate"] = round(current_rate, 4)
        components["cny_change_20d"] = round(change_20d * 100, 2)

    # ==== 3. SHIPPING COSTS (BDIY from FRED) ====
    cur.execute(
        """
        SELECT event_date, value FROM econ.commodities_1d
        WHERE series_id = 'BDIY' AND event_date <= %s AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 30
    """,
        (as_of_date,),
    )
    ship_data = cur.fetchall()
    if len(ship_data) < 21:
        raise ValueError("Insufficient BDIY data to compute shipping stress")

    current_bdiy = float(ship_data[0][1])
    bdiy_20d = float(ship_data[20][1])
    bdiy_change_20d = (current_bdiy - bdiy_20d) / bdiy_20d if bdiy_20d > 0 else 0

    ship_score, ship_desc = score_shipping(bdiy_change_20d)
    components["ship_score"] = round(ship_score, 1)
    components["bdiy_change_20d"] = round(bdiy_change_20d * 100, 2)

    # ==== 4. CHINA SPECIALIST ====
    cur.execute(
        """
        SELECT signal_1, confidence
        FROM training.specialist_signals_1d
        WHERE bucket = 'china' AND as_of_date <= %s
        ORDER BY as_of_date DESC LIMIT 1
    """,
        (as_of_date,),
    )
    signal_row = cur.fetchone()

    specialist_score = 50
    specialist_signal = None
    if signal_row and signal_row[0] is not None:
        specialist_signal = float(signal_row[0])
        confidence = float(signal_row[1]) if signal_row[1] else 0.5

        # Negative signal = bearish China = more tension
        specialist_score = 50 - (specialist_signal * 25 * confidence)
        specialist_score = float(np.clip(specialist_score, 0, 100))
        components["specialist_score"] = round(specialist_score, 1)
        components["specialist_signal"] = round(specialist_signal, 3)

    # ==== 5. SOY-SPECIFIC CHINA NEWS (Trade War Focus) ====
    cur.execute(
        """
        SELECT COUNT(*) FROM alt.profarmer_news_event
        WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s
    """,
        (as_of_date, as_of_date),
    )
    total_news = cur.fetchone()[0] or 1

    # Soy-specific China/trade war keywords
    cur.execute(
        """
        SELECT COUNT(*) FROM alt.profarmer_news_event
        WHERE event_date >= %s - INTERVAL '7 days' AND event_date <= %s
        AND (
            (headline ILIKE '%%china%%' AND (headline ILIKE '%%soy%%' OR headline ILIKE '%%bean%%' OR headline ILIKE '%%export%%'))
            OR headline ILIKE '%%trade war%%'
            OR headline ILIKE '%%tariff%%'
            OR headline ILIKE '%%export sales%%'
            OR content ILIKE '%%china soy%%'
            OR content ILIKE '%%soybean export%%'
            OR content ILIKE '%%chinese import%%'
        )
    """,
        (as_of_date, as_of_date),
    )
    soy_china_news = cur.fetchone()[0] or 0

    news_score, news_desc = score_china_news(soy_china_news, total_news)
    components["news_score"] = round(news_score, 1)
    components["soy_china_news_count"] = soy_china_news
    components["total_news_count"] = total_news
    components["news_assessment"] = news_desc

    # ==== COMPOSITE SCORE ====
    # SOY-CENTRIC WEIGHTS:
    # Shipping (BDIY) 30% - direct trade flow proxy
    # CNY 25% - currency competitiveness
    # Copper (HG) 20% - China demand proxy
    # Soy News 15% - ProFarmer trade war coverage
    # Specialist 10% - ML signal
    score = (
        (ship_score * 0.30)
        + (cny_score * 0.25)
        + (hg_score * 0.20)
        + (news_score * 0.15)
        + (specialist_score * 0.10)
    )
    score = float(np.clip(score, 0, 100))

    # ==== REGIME ====
    if score >= 75:
        regime = "crisis"
    elif score >= 60:
        regime = "high_tension"
    elif score >= 45:
        regime = "elevated"
    elif score >= 30:
        regime = "normal"
    else:
        regime = "constructive"

    # ==== SPARKLINE (HG-based) ====
    sparkline = []
    if len(hg_data) >= 10:
        for i in range(min(10, len(hg_data))):
            if i + 20 < len(hg_data):
                d20_val = hg_data[i + 20][1]
                curr_val = hg_data[i][1]
                if d20_val and d20_val > 0:
                    chg = (curr_val - d20_val) / d20_val
                    hist_score, _ = score_hg_performance(chg, 0)
                    sparkline.insert(0, hist_score)
    if len(sparkline) < 10:
        sparkline = [50] * 10

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
        trend = "Tension Rising"
    elif momentum > 0.03:
        trend = "Slight Increase"
    elif momentum < -0.10:
        trend = "Tension Easing"
    elif momentum < -0.03:
        trend = "Slight Decrease"
    else:
        trend = "Stable"

    # ==== LEVEL/COLOR ====
    if score >= 80:
        level, color = "Extreme", "#DC2626"
    elif score >= 65:
        level, color = "High", "#EA580C"
    elif score >= 50:
        level, color = "Elevated", "#D97706"
    elif score >= 35:
        level, color = "Normal", "#65A30D"
    else:
        level, color = "Low", "#0891B2"

    # ==== NARRATIVE ====
    headline, narrative, drivers = generate_china_narrative(
        hg_score, cny_score, ship_score, news_score, specialist_signal, score, regime
    )

    return {
        "name": "China Tension",
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
            "regime_name": CHINA_REGIMES.get(regime, CHINA_REGIMES["normal"]).name,
            "regime_description": CHINA_REGIMES.get(
                regime, CHINA_REGIMES["normal"]
            ).description,
            "soy_impact": CHINA_REGIMES.get(regime, CHINA_REGIMES["normal"]).soy_impact,
            "trading_action": CHINA_REGIMES.get(
                regime, CHINA_REGIMES["normal"]
            ).trading_action,
            "hg_assessment": hg_desc,
            "cny_assessment": cny_desc,
            "ship_assessment": ship_desc,
            "news_assessment": news_desc,
        },
    }
