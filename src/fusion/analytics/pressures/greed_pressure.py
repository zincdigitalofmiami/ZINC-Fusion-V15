"""
ZINC-FUSION-V15: Greed Pressure Index Calculator

CNN Fear/Greed style composite sentiment indicator.
Adapted for commodity/soyoil market context.

CNN Fear & Greed Methodology (7 equally-weighted indicators):
1. Stock Price Momentum - S&P 500 vs 125-day MA
2. Stock Price Breadth - NYSE Advance/Decline
3. Put/Call Ratio - Options skew
4. Market Volatility - VIX level (inverted)
5. Safe Haven Demand - Stocks vs Bonds performance
6. Junk Bond Demand - HY vs IG spreads
7. Stock Price Strength - 52-week highs vs lows

Our Adaptation for Soyoil Markets:
1. Market Momentum - SPY vs 125-day MA
2. Commodity Momentum - DBA (ag ETF) trend
3. VIX Fear Gauge - VIX level (inverted: low VIX = greed)
4. Safe Haven Flows - GLD performance (inverted: rising gold = fear)
5. Credit Spreads - HY spreads (inverted: tight = greed)
6. Specialist Consensus - Net bullish/bearish signals
7. ZL Momentum - Soyoil vs its own moving averages

Scale:
- 0-25: Extreme Fear
- 25-45: Fear
- 45-55: Neutral
- 55-75: Greed
- 75-100: Extreme Greed

Note: HIGH score = HIGH greed (bullish sentiment, potential top)
      LOW score = HIGH fear (bearish sentiment, potential bottom)

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
# DOMAIN CONSTANTS - Sentiment Thresholds
# ==============================================================================

# Final index thresholds
EXTREME_FEAR = 25
FEAR = 45
NEUTRAL_LOW = 45
NEUTRAL_HIGH = 55
GREED = 75
EXTREME_GREED = 75

# VIX thresholds for sentiment (inverted from volatility pressure)
VIX_EXTREME_FEAR = 35.0    # VIX > 35 = extreme fear (score 0-15)
VIX_FEAR = 25.0            # VIX 25-35 = fear (score 15-35)
VIX_NEUTRAL = 18.0         # VIX 18-25 = neutral (score 35-65)
VIX_GREED = 14.0           # VIX 14-18 = greed (score 65-85)
VIX_EXTREME_GREED = 12.0   # VIX < 12 = extreme greed (score 85-100)

# Credit spread thresholds (HY OAS in bps)
SPREAD_EXTREME_FEAR = 700  # > 700 bps = extreme fear
SPREAD_FEAR = 500          # 500-700 = fear
SPREAD_NEUTRAL = 400       # 350-500 = neutral
SPREAD_GREED = 300         # 300-350 = greed
SPREAD_EXTREME_GREED = 250 # < 250 = extreme greed


@dataclass
class SentimentRegime:
    """Sentiment regime classification."""
    name: str
    description: str
    contrarian_signal: str
    historical_precedent: str


SENTIMENT_REGIMES = {
    "extreme_fear": SentimentRegime(
        name="Extreme Fear",
        description="Panic dominates. Investors liquidating regardless of fundamentals.",
        contrarian_signal="Historically a buying opportunity. Capitulation marks bottoms.",
        historical_precedent="Similar to March 2020 COVID crash, Q4 2018 selloff."
    ),
    "fear": SentimentRegime(
        name="Fear",
        description="Risk aversion elevated. Defensive positioning prevails.",
        contrarian_signal="Approaching potential value zone. Smart money begins accumulating.",
        historical_precedent="Typical correction or early bear market phase."
    ),
    "neutral": SentimentRegime(
        name="Neutral",
        description="Balanced sentiment. Neither excessive fear nor complacency.",
        contrarian_signal="No clear contrarian signal. Trade with fundamentals.",
        historical_precedent="Normal market conditions."
    ),
    "greed": SentimentRegime(
        name="Greed",
        description="Risk appetite elevated. Optimism building.",
        contrarian_signal="Caution warranted. Complacency building.",
        historical_precedent="Late bull market phase. Consider reducing exposure."
    ),
    "extreme_greed": SentimentRegime(
        name="Extreme Greed",
        description="Euphoria. FOMO driving decisions, fundamentals ignored.",
        contrarian_signal="Major warning sign. Historically precedes pullbacks.",
        historical_precedent="Similar to late 2021 meme stock mania, 1999 dot-com."
    )
}


def score_vix_sentiment(vix: float) -> Tuple[float, str]:
    """
    Score VIX as sentiment indicator (inverted: low VIX = greed).

    Returns (score, description) where score 0-100 (high = greed).
    """
    if vix >= VIX_EXTREME_FEAR:
        pct = min(1, (vix - VIX_EXTREME_FEAR) / 15)
        score = 15 - (pct * 15)
        return max(0, score), "Extreme fear in VIX"

    elif vix >= VIX_FEAR:
        pct = (vix - VIX_FEAR) / (VIX_EXTREME_FEAR - VIX_FEAR)
        score = 35 - (pct * 20)
        return score, "Fear elevated in VIX"

    elif vix >= VIX_NEUTRAL:
        pct = (vix - VIX_NEUTRAL) / (VIX_FEAR - VIX_NEUTRAL)
        score = 50 - (pct * 15)
        return score, "VIX in neutral range"

    elif vix >= VIX_GREED:
        pct = (vix - VIX_GREED) / (VIX_NEUTRAL - VIX_GREED)
        score = 75 - (pct * 25)
        return score, "Low VIX signals complacency"

    elif vix >= VIX_EXTREME_GREED:
        pct = (vix - VIX_EXTREME_GREED) / (VIX_GREED - VIX_EXTREME_GREED)
        score = 90 - (pct * 15)
        return score, "Very low VIX - extreme complacency"

    else:
        return 95, "Extreme greed - VIX at historic lows"


def score_momentum(current: float, ma_short: float, ma_long: float) -> Tuple[float, str]:
    """
    Score momentum vs moving averages.

    Returns (score, description) where score 0-100 (high = greed/bullish).
    """
    if ma_short == 0 or ma_long == 0:
        return 50, "Insufficient data"

    # Calculate deviations from MAs
    short_dev = (current - ma_short) / ma_short * 100  # % above/below 20d MA
    long_dev = (current - ma_long) / ma_long * 100     # % above/below 125d MA

    # Base score on long-term MA position
    if long_dev > 10:
        base = 80  # Well above long MA
    elif long_dev > 5:
        base = 70
    elif long_dev > 0:
        base = 55
    elif long_dev > -5:
        base = 45
    elif long_dev > -10:
        base = 30
    else:
        base = 15

    # Adjust for short-term momentum
    if short_dev > 3:
        adj = 10  # Short-term overbought
        desc = "Strong upward momentum"
    elif short_dev > 0:
        adj = 5
        desc = "Positive momentum"
    elif short_dev > -3:
        adj = -5
        desc = "Momentum weakening"
    else:
        adj = -10
        desc = "Negative momentum"

    score = float(np.clip(base + adj, 0, 100))
    return score, desc


def score_credit_spreads(spread: float) -> Tuple[float, str]:
    """
    Score HY credit spreads as sentiment indicator.

    Tight spreads = greed (complacency about risk)
    Wide spreads = fear (risk aversion)

    Returns (score, description) where score 0-100 (high = greed).
    """
    # Spread in basis points
    if spread >= SPREAD_EXTREME_FEAR:
        return 10, "Credit spreads blown out - extreme fear"

    elif spread >= SPREAD_FEAR:
        pct = (spread - SPREAD_FEAR) / (SPREAD_EXTREME_FEAR - SPREAD_FEAR)
        score = 30 - (pct * 20)
        return score, "Wide credit spreads signal fear"

    elif spread >= SPREAD_NEUTRAL:
        pct = (spread - SPREAD_NEUTRAL) / (SPREAD_FEAR - SPREAD_NEUTRAL)
        score = 50 - (pct * 20)
        return score, "Credit spreads in normal range"

    elif spread >= SPREAD_GREED:
        pct = (spread - SPREAD_GREED) / (SPREAD_NEUTRAL - SPREAD_GREED)
        score = 70 - (pct * 20)
        return score, "Tight spreads - risk appetite strong"

    elif spread >= SPREAD_EXTREME_GREED:
        pct = (spread - SPREAD_EXTREME_GREED) / (SPREAD_GREED - SPREAD_EXTREME_GREED)
        score = 85 - (pct * 15)
        return score, "Very tight spreads - complacency"

    else:
        return 95, "Extreme spread compression - peak greed"


def score_safe_haven(gold_change_20d: float) -> Tuple[float, str]:
    """
    Score gold as safe haven indicator.

    Rising gold = fear (flight to safety)
    Falling gold = greed (risk-on)

    Returns (score, description) where score 0-100 (high = greed).
    """
    # gold_change_20d is % change over 20 days
    if gold_change_20d > 0.08:
        return 15, "Gold surging - flight to safety"
    elif gold_change_20d > 0.04:
        return 30, "Gold rising - some safe haven demand"
    elif gold_change_20d > 0.01:
        return 45, "Gold slightly bid"
    elif gold_change_20d > -0.02:
        return 55, "Gold stable"
    elif gold_change_20d > -0.05:
        return 70, "Gold softening - risk appetite returning"
    else:
        return 85, "Gold selling off - full risk-on"


def determine_sentiment_regime(score: float) -> str:
    """Determine sentiment regime from composite score."""
    if score <= EXTREME_FEAR:
        return "extreme_fear"
    elif score <= FEAR:
        return "fear"
    elif score <= NEUTRAL_HIGH:
        return "neutral"
    elif score <= GREED:
        return "greed"
    else:
        return "extreme_greed"


def generate_greed_narrative(
    score: float,
    regime: str,
    components: Dict[str, float]
) -> Tuple[str, str, List[str]]:
    """
    Generate domain-expert narrative for sentiment.

    Returns (headline, story, key_drivers).
    """
    regime_info = SENTIMENT_REGIMES.get(regime, SENTIMENT_REGIMES["neutral"])

    # Headline based on score
    if score >= 80:
        headline = "Extreme Greed Dominates"
    elif score >= 65:
        headline = "Markets Feeling Greedy"
    elif score >= 55:
        headline = "Cautious Optimism"
    elif score >= 45:
        headline = "Balanced Sentiment"
    elif score >= 35:
        headline = "Fear Creeping In"
    elif score >= 20:
        headline = "Fear Building"
    else:
        headline = "Extreme Fear Grips Markets"

    # Build narrative
    parts = [regime_info.description]
    parts.append(regime_info.contrarian_signal)

    narrative = " ".join(parts)

    # Key drivers (identify what's moving the needle)
    drivers = []

    vix_score = components.get("vix_sentiment", 50)
    if vix_score < 30:
        drivers.append("High VIX signals fear")
    elif vix_score > 75:
        drivers.append("Low VIX shows complacency")

    credit_score = components.get("credit_spreads", 50)
    if credit_score < 30:
        drivers.append("Wide credit spreads")
    elif credit_score > 75:
        drivers.append("Tight credit spreads")

    gold_score = components.get("safe_haven", 50)
    if gold_score < 35:
        drivers.append("Gold catching bids")
    elif gold_score > 70:
        drivers.append("No safe haven demand")

    momentum_score = components.get("market_momentum", 50)
    if momentum_score < 30:
        drivers.append("Weak market momentum")
    elif momentum_score > 70:
        drivers.append("Strong market momentum")

    consensus_score = components.get("specialist_consensus", 50)
    if consensus_score < 35:
        drivers.append("Bearish specialist signals")
    elif consensus_score > 65:
        drivers.append("Bullish specialist consensus")

    if not drivers:
        drivers.append("Mixed signals across indicators")

    return headline, narrative, drivers


def calculate_greed_pressure(conn, as_of_date: Optional[date] = None) -> Dict:
    """
    Calculate Greed Pressure Index (CNN Fear/Greed style).

    Components (equally weighted like CNN):
    1. VIX Sentiment (inverted)
    2. Market Momentum (SPY)
    3. Credit Spreads (HY)
    4. Safe Haven Demand (Gold)
    5. Specialist Consensus
    6. ZL Momentum
    7. Commodity Momentum (DBA)

    Returns PressureReading-compatible dict.

    Note: HIGH score = GREED, LOW score = FEAR
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()
    components = {}
    all_scores = []

    # ==== 1. VIX SENTIMENT ====
    cur.execute("""
        SELECT value FROM econ.vol_indices_1d
        WHERE series_id = 'VIXCLS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 1
    """, (as_of_date,))
    vix_row = cur.fetchone()

    if vix_row:
        current_vix = float(vix_row[0])
        vix_score, vix_desc = score_vix_sentiment(current_vix)
        components["vix_sentiment"] = round(vix_score, 1)
        components["vix_value"] = round(current_vix, 1)
        all_scores.append(vix_score)

    # ==== 2. MARKET MOMENTUM (SPY) - Databento ETF ====
    cur.execute("""
        SELECT event_date, close FROM mkt.etf_1d
        WHERE symbol = 'SPY' AND event_date <= %s AND close IS NOT NULL
        ORDER BY event_date DESC LIMIT 150
    """, (as_of_date,))
    spy_data = cur.fetchall()
    if len(spy_data) < 125:
        raise ValueError("Insufficient SPY data for market momentum")

    spy_values = [float(r[1]) for r in spy_data if r[1] is not None]
    current_spy = spy_values[0]
    spy_ma20 = np.mean(spy_values[:20])
    spy_ma125 = np.mean(spy_values[:125])

    spy_score, spy_desc = score_momentum(current_spy, spy_ma20, spy_ma125)
    components["market_momentum"] = round(spy_score, 1)
    components["spy_vs_ma125"] = round((current_spy / spy_ma125 - 1) * 100, 2)
    all_scores.append(spy_score)

    # ==== 3. CREDIT SPREADS ====
    cur.execute("""
        SELECT value FROM econ.vol_indices_1d
        WHERE series_id = 'BAMLH0A0HYM2' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 1
    """, (as_of_date,))
    spread_row = cur.fetchone()

    if spread_row:
        current_spread = float(spread_row[0]) * 100  # Convert to bps
        spread_score, spread_desc = score_credit_spreads(current_spread)
        components["credit_spreads"] = round(spread_score, 1)
        components["hy_spread_bps"] = round(current_spread, 0)
        all_scores.append(spread_score)

    # ==== 4. SAFE HAVEN DEMAND (Gold) - RE-ENABLED with Databento GLD data ====
    # Rising gold = fear (flight to safety), falling gold = greed (risk-on)
    cur.execute("""
        SELECT
            close,
            returns_21d,
            momentum_21d,
            zl_corr_63d
        FROM mkt.etf_1d
        WHERE symbol = 'GLD' AND event_date <= %s AND close IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
    """, (as_of_date,))
    gld_row = cur.fetchone()

    if gld_row and gld_row[1] is not None:
        gld_ret_21d = float(gld_row[1])  # 21-day log return
        gld_momentum = float(gld_row[2]) if gld_row[2] else 0.0
        gld_zl_corr = float(gld_row[3]) if gld_row[3] else 0.0

        # Score using the existing score_safe_haven logic (inverted: gold up = fear)
        gold_score, gold_desc = score_safe_haven(gld_ret_21d)
        components["safe_haven"] = float(gold_score)
        components["gld_ret_21d"] = gld_ret_21d
        components["gld_zl_corr"] = gld_zl_corr
        all_scores.append(gold_score)
    else:
        components["safe_haven"] = 50.0
        all_scores.append(50.0)

    # ==== 5. SPECIALIST CONSENSUS ====
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
        if total > 0:
            consensus_score = 50 + ((bullish_count - bearish_count) / total * 50)
            consensus_score = float(np.clip(consensus_score, 0, 100))
            components["specialist_consensus"] = round(consensus_score, 1)
            components["bullish_specialists"] = bullish_count
            components["bearish_specialists"] = bearish_count
            all_scores.append(consensus_score)

    # ==== 6. ZL MOMENTUM ====
    cur.execute("""
        SELECT event_date, close FROM analytics.zl_price_1d
        WHERE event_date <= %s
        ORDER BY event_date DESC LIMIT 63
    """, (as_of_date,))
    zl_data = cur.fetchall()

    if len(zl_data) > 20:
        zl_values = [float(r[1]) for r in zl_data if r[1] is not None]
        current_zl = zl_values[0]
        zl_ma20 = np.mean(zl_values[:20])
        zl_ma50 = np.mean(zl_values[:min(50, len(zl_values))])

        zl_score, zl_desc = score_momentum(current_zl, zl_ma20, zl_ma50)
        components["zl_momentum"] = round(zl_score, 1)
        components["zl_vs_ma50"] = round((current_zl / zl_ma50 - 1) * 100, 2)
        all_scores.append(zl_score)

    # ==== 7. COMMODITY MOMENTUM (DBA) - RE-ENABLED with Databento data ====
    # DBA = Invesco DB Agriculture Fund - broad ag commodity momentum
    cur.execute("""
        SELECT
            close,
            returns_21d,
            momentum_21d,
            zl_corr_63d
        FROM mkt.etf_1d
        WHERE symbol = 'DBA' AND event_date <= %s AND close IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
    """, (as_of_date,))
    dba_row = cur.fetchone()

    if dba_row and dba_row[2] is not None:
        dba_momentum = float(dba_row[2])  # Price vs 21d SMA in %

        # Score: positive momentum = greed, negative = fear
        if dba_momentum > 5:
            dba_score = 80  # Strong greed
        elif dba_momentum > 2:
            dba_score = 65  # Moderate greed
        elif dba_momentum > 0:
            dba_score = 55  # Slight greed
        elif dba_momentum > -2:
            dba_score = 45  # Slight fear
        elif dba_momentum > -5:
            dba_score = 35  # Moderate fear
        else:
            dba_score = 20  # Extreme fear

        components["commodity_momentum"] = float(dba_score)
        components["dba_momentum_pct"] = dba_momentum
        all_scores.append(dba_score)
    else:
        components["commodity_momentum"] = 50.0
        all_scores.append(50.0)

    # ==== COMPOSITE SCORE (EQUALLY WEIGHTED) ====
    if all_scores:
        score = np.mean(all_scores)
    else:
        score = 50.0

    score = float(np.clip(score, 0, 100))

    # ==== REGIME ====
    regime = determine_sentiment_regime(score)

    # ==== SPARKLINE (historical approximation via VIX) ====
    cur.execute("""
        SELECT value FROM econ.vol_indices_1d
        WHERE series_id = 'VIXCLS' AND event_date <= %s
        ORDER BY event_date DESC LIMIT 10
    """, (as_of_date,))
    vix_hist = cur.fetchall()

    sparkline = []
    for row in reversed(vix_hist):
        hist_vix = float(row[0])
        hist_score, _ = score_vix_sentiment(hist_vix)
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
        trend = "Greed Rising"
    elif momentum > 0.03:
        trend = "Sentiment Improving"
    elif momentum < -0.10:
        trend = "Fear Building"
    elif momentum < -0.03:
        trend = "Sentiment Weakening"
    else:
        trend = "Stable"

    # ==== LEVEL (note: different from other pressures - this is sentiment) ====
    if score >= 80:
        level = "Extreme Greed"
        color = "#DC2626"  # Red = danger (extreme greed)
    elif score >= 65:
        level = "Greed"
        color = "#EA580C"
    elif score >= 55:
        level = "Cautious Optimism"
        color = "#D97706"
    elif score >= 45:
        level = "Neutral"
        color = "#65A30D"
    elif score >= 35:
        level = "Fear"
        color = "#0891B2"
    elif score >= 20:
        level = "High Fear"
        color = "#0284C7"
    else:
        level = "Extreme Fear"
        color = "#1E40AF"

    # ==== NARRATIVE ====
    headline, narrative, drivers = generate_greed_narrative(score, regime, components)

    return {
        "name": "Greed Pressure Index",
        "score": round(score, 1),
        "level": level,
        "trend": trend,
        "headline": headline,
        "narrative": narrative,
        "key_drivers": drivers,
        "color": color,
        "icon": "trending-up" if score > 60 else "trending-down" if score < 40 else "minus",
        "sparkline": [round(v, 1) for v in sparkline],
        "percentile_30d": round(score, 1),
        "percentile_1y": round(score, 1),
        "regime": regime,
        "momentum": round(momentum, 3),
        "as_of_date": as_of_date.isoformat(),
        "components": components,
        "domain_context": {
            "regime_name": SENTIMENT_REGIMES.get(regime, SENTIMENT_REGIMES["neutral"]).name,
            "regime_description": SENTIMENT_REGIMES.get(regime, SENTIMENT_REGIMES["neutral"]).description,
            "contrarian_signal": SENTIMENT_REGIMES.get(regime, SENTIMENT_REGIMES["neutral"]).contrarian_signal,
            "historical_precedent": SENTIMENT_REGIMES.get(regime, SENTIMENT_REGIMES["neutral"]).historical_precedent,
            "indicator_count": len(all_scores),
        }
    }
