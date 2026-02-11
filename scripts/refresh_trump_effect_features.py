#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Refresh Trump Effect Features with NEURAL-ENHANCED SCORING

This script creates institution-grade trump effect signals by combining:
1. WhiteHouse actions data (EOs, memos, proclamations, nominations)
2. FRED Policy Uncertainty Indexes (USEPUINDXD, CHNMAINLANDTPU)
3. VIX volatility for market stress context
4. ZL price momentum for signal calibration

SIGNAL ARCHITECTURE:
--------------------
Base Signal = weighted_action_score (action-based, 0-1 scale)
Neural Enhancers:
  - policy_uncertainty_boost: High EPU amplifies trump effect on markets
  - vix_stress_factor: Market stress increases policy sensitivity
  - momentum_alignment: Price trend alignment with expected direction

Final Signal = base_signal * neural_factor * confidence_multiplier

Calculates:
- eo_count_7d/30d: Executive Orders
- proclamation_count_7d/30d: Proclamations
- memorandum_count_7d/30d: Presidential Memoranda
- nomination_count_7d/30d: Nominations
- total_actions_7d/30d: Sum of all types
- action_velocity: total_actions_7d / 7
- action_acceleration: velocity change
- weighted_action_score: Weighted sum (EO=3, Memo=2, Proc=1.5, Nom=1)
- policy_uncertainty_7d/30d: FRED EPU index averages
- vix_7d/30d: VIX volatility averages
- zl_momentum_7d: ZL price momentum (close[t] - close[t-7]) / close[t-7]
- neural_signal: Enhanced signal with uncertainty/volatility factors
- neural_confidence: Data-driven confidence score
"""

import os
import json
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# =============================================================================
# NEURAL SIGNAL CONFIGURATION
# =============================================================================

# Action type weights (higher = more market-moving)
ACTION_WEIGHTS = {
    "executive_order": 3.0,  # Most impactful - direct policy changes
    "memorandum": 2.5,  # Policy directives
    "presidential_document": 2.0,  # General presidential actions
    "proclamation": 1.5,  # Ceremonial but can have trade implications
    "nomination": 1.0,  # Personnel changes, indirect effect
}

# Policy uncertainty thresholds (based on FRED EPU historical distribution)
EPU_THRESHOLDS = {
    "low": 80,  # Below 80 = calm policy environment
    "normal": 120,  # 80-120 = typical uncertainty
    "elevated": 160,  # 120-160 = elevated uncertainty (amplifies signal)
    "crisis": 200,  # Above 200 = crisis-level uncertainty
}

# VIX thresholds for market stress
VIX_THRESHOLDS = {
    "calm": 15,  # Below 15 = low volatility
    "normal": 20,  # 15-20 = typical
    "elevated": 25,  # 20-25 = elevated (increases sensitivity)
    "stress": 35,  # Above 35 = market stress (high sensitivity)
}

# Era multipliers (Trump eras have higher policy impact on commodities)
ERA_MULTIPLIERS = {
    "pre_trump": 0.3,  # Pre-Trump baseline
    "trump1": 1.0,  # First term - active trade wars
    "gap": 0.4,  # Biden era - less tariff volatility
    "trump2": 1.2,  # Second term - anticipated high activity
}


def get_connection():
    return psycopg2.connect(DATABASE_URL)


# =============================================================================
# NEURAL SIGNAL HELPER FUNCTIONS
# =============================================================================


def calculate_epu_factor(epu_value):
    """
    Calculate policy uncertainty amplification factor.
    Higher EPU = markets more sensitive to presidential actions.

    Returns factor in range [0.8, 1.5]
    """
    if epu_value is None:
        return 1.0  # Neutral if no data

    if epu_value < EPU_THRESHOLDS["low"]:
        return 0.8  # Low uncertainty = dampened effect
    elif epu_value < EPU_THRESHOLDS["normal"]:
        return 1.0  # Normal
    elif epu_value < EPU_THRESHOLDS["elevated"]:
        # Linear interpolation between 1.0 and 1.3
        pct = (epu_value - EPU_THRESHOLDS["normal"]) / (
            EPU_THRESHOLDS["elevated"] - EPU_THRESHOLDS["normal"]
        )
        return 1.0 + (0.3 * pct)
    elif epu_value < EPU_THRESHOLDS["crisis"]:
        # Linear interpolation between 1.3 and 1.5
        pct = (epu_value - EPU_THRESHOLDS["elevated"]) / (
            EPU_THRESHOLDS["crisis"] - EPU_THRESHOLDS["elevated"]
        )
        return 1.3 + (0.2 * pct)
    else:
        return 1.5  # Crisis level - maximum amplification


def calculate_vix_factor(vix_value):
    """
    Calculate VIX stress factor.
    Higher VIX = markets more reactive to any news including policy.

    Returns factor in range [0.9, 1.4]
    """
    if vix_value is None:
        return 1.0  # Neutral if no data

    if vix_value < VIX_THRESHOLDS["calm"]:
        return 0.9  # Calm markets = less reactive
    elif vix_value < VIX_THRESHOLDS["normal"]:
        return 1.0  # Normal
    elif vix_value < VIX_THRESHOLDS["elevated"]:
        # Linear interpolation between 1.0 and 1.2
        pct = (vix_value - VIX_THRESHOLDS["normal"]) / (
            VIX_THRESHOLDS["elevated"] - VIX_THRESHOLDS["normal"]
        )
        return 1.0 + (0.2 * pct)
    elif vix_value < VIX_THRESHOLDS["stress"]:
        # Linear interpolation between 1.2 and 1.4
        pct = (vix_value - VIX_THRESHOLDS["elevated"]) / (
            VIX_THRESHOLDS["stress"] - VIX_THRESHOLDS["elevated"]
        )
        return 1.2 + (0.2 * pct)
    else:
        return 1.4  # High stress - maximum sensitivity


def calculate_momentum_alignment(momentum, expected_direction):
    """
    Calculate alignment between ZL price momentum and expected policy impact.

    If policy is bullish (tariffs on imports) and ZL is trending up, signal is confirmed.
    If policy is bullish but ZL is trending down, reduce confidence.

    Args:
        momentum: ZL 7-day momentum (% change)
        expected_direction: 'bullish' or 'bearish' based on policy type

    Returns alignment factor in range [0.7, 1.2]
    """
    if momentum is None:
        return 1.0  # Neutral if no data

    # Trump tariff policies generally bullish for domestic ZL
    # (Import tariffs = less foreign oil = higher domestic prices)
    expected_bullish = expected_direction == "bullish"
    actual_bullish = momentum > 0

    aligned = expected_bullish == actual_bullish

    if aligned:
        # Signal confirmed by price action
        strength = min(abs(momentum) / 0.05, 1.0)  # Cap at 5% move
        return 1.0 + (0.2 * strength)  # Up to 1.2x
    else:
        # Signal not confirmed - reduce confidence
        strength = min(abs(momentum) / 0.05, 1.0)
        return 1.0 - (0.3 * strength)  # Down to 0.7x


def calculate_confidence_score(total_actions, era, has_epu, has_vix, has_momentum):
    """
    Calculate data-driven confidence score.

    Higher confidence when:
    - More data sources available
    - Active Trump era (policy matters more)
    - More actions to analyze

    Returns confidence in range [0.3, 0.95]
    """
    # Base confidence from data availability
    data_sources_available = sum([has_epu, has_vix, has_momentum])
    base_confidence = 0.4 + (0.1 * data_sources_available)  # 0.4 to 0.7

    # Era adjustment
    era_mult = ERA_MULTIPLIERS.get(era, 0.5)
    era_confidence = base_confidence * (0.7 + 0.3 * era_mult)  # Scale by era

    # Action count boost
    if total_actions > 10:
        action_boost = 0.15
    elif total_actions > 5:
        action_boost = 0.10
    elif total_actions > 0:
        action_boost = 0.05
    else:
        action_boost = -0.1  # Lower confidence when no actions

    final_confidence = min(0.95, max(0.3, era_confidence + action_boost))
    return final_confidence


def calculate_neural_signal(
    base_signal, epu_factor, vix_factor, momentum_factor, era_multiplier
):
    """
    Combine all factors into final neural-enhanced signal.

    Formula:
    neural_signal = base_signal * epu_factor * vix_factor * momentum_factor * era_multiplier

    Clamped to [-1.0, 1.0] range
    """
    if base_signal == 0:
        return 0.0

    raw_signal = (
        base_signal * epu_factor * vix_factor * momentum_factor * era_multiplier
    )

    # Apply sigmoid-like compression to keep in reasonable range
    # This prevents extreme values while preserving directionality
    if abs(raw_signal) > 1.0:
        sign = 1 if raw_signal > 0 else -1
        compressed = sign * (1.0 - 1.0 / (1.0 + abs(raw_signal)))
        return round(compressed, 4)

    return round(raw_signal, 4)


def main():
    print("\n" + "=" * 70)
    print("ZINC-FUSION-V15: REFRESH TRUMP EFFECT WITH NEURAL-ENHANCED SCORING")
    print("=" * 70)

    conn = get_connection()
    cur = conn.cursor()
    print("✅ Connected to database")

    # =========================================================================
    # STEP 1: Load all WhiteHouse actions
    # =========================================================================
    print("\n" + "=" * 60)
    print("STEP 1: Loading WhiteHouse actions data")
    print("=" * 60)

    cur.execute("""
        SELECT event_date as action_date,
               specialist_tags[1] as action_type,
               headline as title
        FROM alt.executive_actions_event
        WHERE source LIKE 'whitehouse%'
          AND event_date IS NOT NULL
        ORDER BY event_date
    """)
    wh_actions = cur.fetchall()
    print(f"  WhiteHouse actions: {len(wh_actions)} rows")

    # Also load Federal Register presidential documents
    cur.execute("""
        SELECT event_date as action_date,
               CASE
                   WHEN title ILIKE '%executive order%' THEN 'executive_order'
                   WHEN title ILIKE '%proclamation%' THEN 'proclamation'
                   WHEN title ILIKE '%memorandum%' THEN 'memorandum'
                   WHEN title ILIKE '%nomination%' OR title ILIKE '%appoint%' THEN 'nomination'
                   ELSE 'presidential_document'
               END as action_type,
               title
        FROM alt.legislation_1d
        WHERE document_type = 'Presidential Document'
        ORDER BY event_date
    """)
    fed_reg_actions = cur.fetchall()
    print(f"  Federal Register presidential docs: {len(fed_reg_actions)} rows")

    # Combine all actions
    all_actions = list(wh_actions) + list(fed_reg_actions)
    print(f"  Total actions: {len(all_actions)} rows")

    # Build action index by date and type
    actions_by_date = {}
    for action_date, action_type, title in all_actions:
        if action_date not in actions_by_date:
            actions_by_date[action_date] = []
        actions_by_date[action_date].append({"type": action_type, "title": title})

    # =========================================================================
    # STEP 2: Load NEURAL ENHANCERS (EPU, VIX, ZL prices)
    # =========================================================================
    print("\n" + "=" * 60)
    print("STEP 2: Loading Neural Enhancer Data")
    print("=" * 60)

    # Load FRED Economic Policy Uncertainty Index (USEPUINDXD - daily)
    cur.execute("""
        SELECT event_date, value
        FROM econ.activity_1d
        WHERE series_id = 'USEPUINDXD'
        ORDER BY event_date
    """)
    epu_data = {row[0]: float(row[1]) for row in cur.fetchall()}
    print(f"  US Policy Uncertainty (EPU): {len(epu_data)} days")

    # Also load China Trade Policy Uncertainty for trade-related signal boost
    cur.execute("""
        SELECT event_date, value
        FROM econ.activity_1d
        WHERE series_id = 'CHNMAINLANDTPU'
        ORDER BY event_date
    """)
    china_tpu_data = {row[0]: float(row[1]) for row in cur.fetchall()}
    print(f"  China Trade Policy Uncertainty: {len(china_tpu_data)} days")

    # Load VIX volatility index
    cur.execute("""
        SELECT event_date, value
        FROM econ.vol_indices_1d
        WHERE series_id = 'VIXCLS'
        ORDER BY event_date
    """)
    vix_data = {row[0]: float(row[1]) for row in cur.fetchall()}
    print(f"  VIX volatility: {len(vix_data)} days")

    # Load ZL prices for momentum calculation
    cur.execute("""
        SELECT event_date, close
        FROM mkt.futures_1d
        WHERE symbol = 'ZL' AND event_date >= '2017-01-01'
        AND close IS NOT NULL
        ORDER BY event_date
    """)
    zl_prices = {row[0]: float(row[1]) for row in cur.fetchall()}
    print(f"  ZL prices: {len(zl_prices)} days")

    # =========================================================================
    # STEP 3: Get date range from ZL prices (training window)
    # =========================================================================
    print("\n" + "=" * 60)
    print("STEP 3: Determining date range")
    print("=" * 60)

    cur.execute("""
        SELECT MIN(event_date), MAX(event_date)
        FROM mkt.futures_1d
        WHERE symbol = 'ZL' AND event_date >= '2017-01-01'
    """)
    min_date, max_date = cur.fetchone()
    print(f"  Training window: {min_date} to {max_date}")

    # News sentiment aggregation (union of all alt news tables)
    # Note: sentiment_score field no longer exists; using article counts only
    cur.execute("""
        WITH all_news AS (
            SELECT event_date FROM alt.policy_news_event WHERE event_date >= '2017-01-01'
            UNION ALL
            SELECT event_date FROM alt.executive_actions_event WHERE event_date >= '2017-01-01'
            UNION ALL
            SELECT event_date FROM alt.econ_news_event WHERE event_date >= '2017-01-01'
            UNION ALL
            SELECT event_date FROM alt.profarmer_news_event WHERE event_date >= '2017-01-01'
        )
        SELECT event_date as pub_date,
               COUNT(*) as article_count
        FROM all_news
        GROUP BY event_date
    """)
    news_sentiment = {
        row[0]: {
            "sentiment": 0.0,  # sentiment_score no longer available
            "count": int(row[1]),
        }
        for row in cur.fetchall()
    }
    print(f"  News article count days: {len(news_sentiment)}")

    # =========================================================================
    # STEP 4: Calculate features for each date with NEURAL ENHANCEMENT
    # =========================================================================
    print("\n" + "=" * 60)
    print("STEP 4: Calculating Trump Effect features with Neural Enhancement")
    print("=" * 60)

    def count_actions_in_window(target_date, days, action_type=None):
        """Count actions in the N days ending on target_date."""
        count = 0
        for d in range(days):
            check_date = target_date - timedelta(days=d)
            if check_date in actions_by_date:
                for action in actions_by_date[check_date]:
                    if action_type is None or action["type"] == action_type:
                        count += 1
        return count

    def get_avg_in_window(data_dict, target_date, days):
        """Get average value from dict for N days ending on target_date."""
        values = []
        for d in range(days):
            check_date = target_date - timedelta(days=d)
            if check_date in data_dict:
                values.append(data_dict[check_date])
        return sum(values) / len(values) if values else None

    def get_momentum(prices_dict, target_date, days=7):
        """Calculate price momentum: (current - past) / past."""
        current_price = prices_dict.get(target_date)
        past_date = target_date - timedelta(days=days)
        past_price = prices_dict.get(past_date)

        if current_price and past_price and past_price != 0:
            return (current_price - past_price) / past_price
        return None

    # Generate dates
    current_date = min_date
    features_rows = []
    neural_features = {}  # Store neural enhancements separately

    trump1_start = datetime(2017, 1, 20).date()
    trump1_end = datetime(2021, 1, 20).date()
    trump2_start = datetime(2025, 1, 20).date()

    while current_date <= max_date:
        # Determine era
        if current_date < trump1_start:
            era = "pre_trump"
        elif current_date <= trump1_end:
            era = "trump1"
        elif current_date < trump2_start:
            era = "gap"
        else:
            era = "trump2"

        # Count actions by type
        eo_7d = count_actions_in_window(current_date, 7, "executive_order")
        eo_30d = count_actions_in_window(current_date, 30, "executive_order")
        proc_7d = count_actions_in_window(current_date, 7, "proclamation")
        proc_30d = count_actions_in_window(current_date, 30, "proclamation")
        memo_7d = count_actions_in_window(current_date, 7, "memorandum")
        memo_30d = count_actions_in_window(current_date, 30, "memorandum")
        nom_7d = count_actions_in_window(current_date, 7, "nomination")
        nom_30d = count_actions_in_window(current_date, 30, "nomination")

        # Presidential documents that don't fit other categories
        pres_doc_7d = count_actions_in_window(current_date, 7, "presidential_document")
        pres_doc_30d = count_actions_in_window(
            current_date, 30, "presidential_document"
        )

        # Totals
        total_7d = eo_7d + proc_7d + memo_7d + nom_7d + pres_doc_7d
        total_30d = eo_30d + proc_30d + memo_30d + nom_30d + pres_doc_30d

        # Velocity and acceleration
        action_velocity = total_7d / 7.0
        prev_week_velocity = (
            count_actions_in_window(current_date - timedelta(days=7), 7) / 7.0
        )
        action_acceleration = action_velocity - prev_week_velocity

        # Weighted score using ACTION_WEIGHTS config
        weighted_score = (
            eo_7d * ACTION_WEIGHTS["executive_order"]
            + memo_7d * ACTION_WEIGHTS["memorandum"]
            + proc_7d * ACTION_WEIGHTS["proclamation"]
            + pres_doc_7d * ACTION_WEIGHTS["presidential_document"]
            + nom_7d * ACTION_WEIGHTS["nomination"]
        ) / 10.0

        # Sentiment from news (if available)
        news_record = news_sentiment.get(current_date, {"sentiment": 0.0, "count": 0})
        avg_sentiment_7d = (
            news_record["sentiment"] if era in ["trump1", "trump2"] else None
        )
        avg_sentiment_30d = (
            news_record["sentiment"] * 0.8 if era in ["trump1", "trump2"] else None
        )

        # =====================================================================
        # NEURAL ENHANCERS
        # =====================================================================

        # Policy Uncertainty (EPU) - 7d and 30d averages
        epu_7d = get_avg_in_window(epu_data, current_date, 7)
        epu_30d = get_avg_in_window(epu_data, current_date, 30)

        # China Trade Policy Uncertainty
        china_tpu_7d = get_avg_in_window(china_tpu_data, current_date, 7)

        # VIX volatility - 7d and 30d averages
        vix_7d = get_avg_in_window(vix_data, current_date, 7)
        vix_30d = get_avg_in_window(vix_data, current_date, 30)

        # ZL momentum
        zl_momentum_7d = get_momentum(zl_prices, current_date, 7)

        # Calculate neural factors
        epu_factor = calculate_epu_factor(epu_7d)
        vix_factor = calculate_vix_factor(vix_7d)
        era_multiplier = ERA_MULTIPLIERS.get(era, 0.5)

        # Trump policies generally bullish for domestic ZL (tariffs reduce imports)
        expected_direction = "bullish" if era in ["trump1", "trump2"] else "neutral"
        momentum_factor = calculate_momentum_alignment(
            zl_momentum_7d, expected_direction
        )

        # Base signal (0 to 1 scale)
        base_signal = min(1.0, weighted_score / 2.0) if total_7d > 0 else 0.0

        # Neural-enhanced signal
        neural_signal = calculate_neural_signal(
            base_signal, epu_factor, vix_factor, momentum_factor, era_multiplier
        )

        # Neural confidence score
        has_epu = epu_7d is not None
        has_vix = vix_7d is not None
        has_momentum = zl_momentum_7d is not None
        neural_confidence = calculate_confidence_score(
            total_7d, era, has_epu, has_vix, has_momentum
        )

        # Store neural features for training sync
        neural_features[current_date] = {
            "epu_7d": round(epu_7d, 2) if epu_7d else None,
            "epu_30d": round(epu_30d, 2) if epu_30d else None,
            "china_tpu_7d": round(china_tpu_7d, 2) if china_tpu_7d else None,
            "vix_7d": round(vix_7d, 2) if vix_7d else None,
            "vix_30d": round(vix_30d, 2) if vix_30d else None,
            "zl_momentum_7d": round(zl_momentum_7d, 4) if zl_momentum_7d else None,
            "epu_factor": round(epu_factor, 3),
            "vix_factor": round(vix_factor, 3),
            "momentum_factor": round(momentum_factor, 3),
            "era_multiplier": era_multiplier,
            "base_signal": round(base_signal, 4),
            "neural_signal": neural_signal,
            "neural_confidence": round(neural_confidence, 3),
        }

        features_rows.append(
            (
                current_date,
                eo_7d,
                eo_30d,
                proc_7d,
                proc_30d,
                nom_7d,
                nom_30d,
                memo_7d,
                memo_30d,
                total_7d,
                total_30d,
                avg_sentiment_7d,
                avg_sentiment_30d,
                action_velocity,
                action_acceleration,
                weighted_score,
            )
        )

        current_date += timedelta(days=1)

    print(f"  Generated {len(features_rows)} feature rows")
    print(f"  Generated {len(neural_features)} neural enhancement records")

    # Show sample of calculated features with neural enhancements
    print("\n  Sample NEURAL-ENHANCED features (last 10 days with actions):")
    recent_with_actions = [r for r in features_rows if r[9] > 0][-10:]  # total_7d > 0
    for row in recent_with_actions:
        nf = neural_features.get(row[0], {})
        print(
            f"    {row[0]}: EO_7d={row[1]}, Total_7d={row[9]}, base={nf.get('base_signal', 0):.3f}, "
            f"neural={nf.get('neural_signal', 0):.3f}, conf={nf.get('neural_confidence', 0):.2f}, "
            f"EPU={nf.get('epu_7d') or 'N/A'}, VIX={nf.get('vix_7d') or 'N/A'}"
        )

    # =========================================================================
    # STEP 5: Update features.trump_effect_1d
    # =========================================================================
    print("\n" + "=" * 60)
    print("STEP 5: Updating features.trump_effect_1d")
    print("=" * 60)

    # Clear existing data
    cur.execute("DELETE FROM features.trump_effect_1d")
    conn.commit()
    print("  Cleared existing data")

    # Insert new data
    insert_count = 0
    for row in features_rows:
        cur.execute(
            """
            INSERT INTO features.trump_effect_1d
            (as_of_date, eo_count_7d, eo_count_30d,
             proclamation_count_7d, proclamation_count_30d,
             nomination_count_7d, nomination_count_30d,
             memorandum_count_7d, memorandum_count_30d,
             total_actions_7d, total_actions_30d,
             avg_sentiment_7d, avg_sentiment_30d,
             action_velocity, action_acceleration,
             weighted_action_score, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (as_of_date) DO UPDATE SET
                eo_count_7d = EXCLUDED.eo_count_7d,
                eo_count_30d = EXCLUDED.eo_count_30d,
                proclamation_count_7d = EXCLUDED.proclamation_count_7d,
                proclamation_count_30d = EXCLUDED.proclamation_count_30d,
                nomination_count_7d = EXCLUDED.nomination_count_7d,
                nomination_count_30d = EXCLUDED.nomination_count_30d,
                memorandum_count_7d = EXCLUDED.memorandum_count_7d,
                memorandum_count_30d = EXCLUDED.memorandum_count_30d,
                total_actions_7d = EXCLUDED.total_actions_7d,
                total_actions_30d = EXCLUDED.total_actions_30d,
                avg_sentiment_7d = EXCLUDED.avg_sentiment_7d,
                avg_sentiment_30d = EXCLUDED.avg_sentiment_30d,
                action_velocity = EXCLUDED.action_velocity,
                action_acceleration = EXCLUDED.action_acceleration,
                weighted_action_score = EXCLUDED.weighted_action_score
        """,
            row,
        )
        insert_count += 1

        if insert_count % 500 == 0:
            conn.commit()
            print(f"    Inserted {insert_count} rows...")

    conn.commit()
    print(f"  ✅ Inserted {insert_count} rows into features.trump_effect_1d")

    # =========================================================================
    # STEP 6: Sync to training.specialist_trump_effect_1d with NEURAL SIGNALS
    # =========================================================================
    print("\n" + "=" * 60)
    print("STEP 6: Syncing NEURAL-ENHANCED signals to training table")
    print("=" * 60)

    # Use neural-enhanced signal/confidence instead of simple weighted score
    cur.execute("DELETE FROM training.specialist_trump_effect_1d WHERE symbol = 'ZL'")
    conn.commit()
    print("  Cleared existing training data")

    sync_count = 0
    for row in features_rows:
        as_of_date = row[0]
        eo_count_7d = row[1]
        eo_count_30d = row[2]
        total_actions_7d = row[9]
        total_actions_30d = row[10]
        action_velocity = row[13]
        action_acceleration = row[14]
        weighted_score = row[15]

        # Determine era
        if as_of_date < trump1_start:
            era = "pre_trump"
        elif as_of_date <= trump1_end:
            era = "trump1"
        elif as_of_date < trump2_start:
            era = "gap"
        else:
            era = "trump2"

        # Get neural-enhanced signal and confidence
        nf = neural_features.get(as_of_date, {})
        neural_signal = nf.get("neural_signal", 0.0)
        neural_confidence = nf.get("neural_confidence", 0.3)

        # Build comprehensive features JSON with all neural components
        features_json = json.dumps(
            {
                # Era and basic counts
                "era": era,
                "eo_count_7d": eo_count_7d,
                "eo_count_30d": eo_count_30d,
                "total_actions_7d": total_actions_7d,
                "total_actions_30d": total_actions_30d,
                # Action dynamics
                "action_velocity": round(action_velocity, 4) if action_velocity else 0,
                "action_acceleration": round(action_acceleration, 4)
                if action_acceleration
                else 0,
                "weighted_action_score": round(weighted_score, 4)
                if weighted_score
                else 0,
                # Neural enhancers
                "epu_7d": nf.get("epu_7d"),
                "epu_30d": nf.get("epu_30d"),
                "china_tpu_7d": nf.get("china_tpu_7d"),
                "vix_7d": nf.get("vix_7d"),
                "vix_30d": nf.get("vix_30d"),
                "zl_momentum_7d": nf.get("zl_momentum_7d"),
                # Neural factors
                "epu_factor": nf.get("epu_factor", 1.0),
                "vix_factor": nf.get("vix_factor", 1.0),
                "momentum_factor": nf.get("momentum_factor", 1.0),
                "era_multiplier": nf.get("era_multiplier", 1.0),
                # Signal components
                "base_signal": nf.get("base_signal", 0.0),
                "neural_signal": neural_signal,
                "neural_confidence": neural_confidence,
                # Metadata
                "scoring_version": "neural-v2",
            }
        )

        cur.execute(
            """
            INSERT INTO training.specialist_trump_effect_1d
            (as_of_date, symbol, signal, confidence, features, created_at)
            VALUES (%s, 'ZL', %s, %s, %s::jsonb, NOW())
            ON CONFLICT (as_of_date, symbol) DO UPDATE SET
                signal = EXCLUDED.signal,
                confidence = EXCLUDED.confidence,
                features = EXCLUDED.features
        """,
            (
                as_of_date,
                round(neural_signal, 4),
                round(neural_confidence, 3),
                features_json,
            ),
        )
        sync_count += 1

        if sync_count % 500 == 0:
            conn.commit()
            print(f"    Synced {sync_count} rows...")

    conn.commit()
    print(
        f"  ✅ Synced {sync_count} NEURAL-ENHANCED rows to training.specialist_trump_effect_1d"
    )

    # =========================================================================
    # STEP 7: Verification with Neural Signal Analysis
    # =========================================================================
    print("\n" + "=" * 60)
    print("STEP 7: Verification & Neural Signal Analysis")
    print("=" * 60)

    cur.execute("""
        SELECT COUNT(*), MIN(as_of_date), MAX(as_of_date)
        FROM features.trump_effect_1d
    """)
    result = cur.fetchone()
    print(f"  Total rows: {result[0]}")
    print(f"  Date range: {result[1]} to {result[2]}")

    # Show non-zero action days
    cur.execute("""
        SELECT COUNT(*)
        FROM features.trump_effect_1d
        WHERE total_actions_7d > 0
    """)
    active_days = cur.fetchone()[0]
    print(f"  Days with actions (7d window): {active_days}")

    # Sample recent data from features table
    cur.execute("""
        SELECT as_of_date, eo_count_7d, eo_count_30d, total_actions_7d, action_velocity
        FROM features.trump_effect_1d
        WHERE total_actions_7d > 0
        ORDER BY as_of_date DESC
        LIMIT 10
    """)
    print("\n  Recent days with actions (features table):")
    for row in cur.fetchall():
        print(
            f"    {row[0]}: EO_7d={row[1]}, EO_30d={row[2]}, Total_7d={row[3]}, velocity={row[4]:.2f}"
        )

    # Verify training table with NEURAL signal details
    cur.execute("""
        SELECT COUNT(*), MIN(as_of_date), MAX(as_of_date)
        FROM training.specialist_trump_effect_1d
    """)
    result = cur.fetchone()
    print(f"\n  Training table rows: {result[0]}")
    print(f"  Training date range: {result[1]} to {result[2]}")

    # Signal distribution analysis
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE signal > 0.5) as high_signal,
            COUNT(*) FILTER (WHERE signal > 0.3 AND signal <= 0.5) as medium_signal,
            COUNT(*) FILTER (WHERE signal > 0 AND signal <= 0.3) as low_signal,
            COUNT(*) FILTER (WHERE signal = 0) as zero_signal,
            AVG(signal) FILTER (WHERE signal > 0) as avg_active_signal,
            AVG(confidence) as avg_confidence
        FROM training.specialist_trump_effect_1d
    """)
    dist = cur.fetchone()
    print(f"\n  Signal distribution:")
    print(f"    High (>0.5):   {dist[1]} rows")
    print(f"    Medium (0.3-0.5): {dist[2]} rows")
    print(f"    Low (0-0.3):   {dist[3]} rows")
    print(f"    Zero:          {dist[4]} rows")
    print(
        f"    Avg active signal: {dist[5]:.4f}"
        if dist[5]
        else "    Avg active signal: N/A"
    )
    print(
        f"    Avg confidence:    {dist[6]:.3f}"
        if dist[6]
        else "    Avg confidence: N/A"
    )

    # Sample neural-enhanced training signals
    cur.execute("""
        SELECT as_of_date, signal, confidence,
               features->>'era' as era,
               features->>'epu_7d' as epu,
               features->>'vix_7d' as vix,
               features->>'base_signal' as base,
               features->>'scoring_version' as version
        FROM training.specialist_trump_effect_1d
        WHERE signal > 0
        ORDER BY as_of_date DESC
        LIMIT 10
    """)
    print("\n  Recent NEURAL-ENHANCED signals (training table):")
    for row in cur.fetchall():
        epu_str = f"EPU={row[4]}" if row[4] else "EPU=N/A"
        vix_str = f"VIX={row[5]}" if row[5] else "VIX=N/A"
        print(
            f"    {row[0]}: signal={float(row[1]):.4f}, conf={float(row[2]):.3f}, "
            f"era={row[3]}, {epu_str}, {vix_str}"
        )

    # Show top 5 highest signals ever
    cur.execute("""
        SELECT as_of_date, signal, confidence,
               features->>'era' as era,
               features->>'total_actions_7d' as actions
        FROM training.specialist_trump_effect_1d
        WHERE signal > 0
        ORDER BY signal DESC
        LIMIT 5
    """)
    print("\n  Top 5 strongest signals (all time):")
    for row in cur.fetchall():
        print(
            f"    {row[0]}: signal={float(row[1]):.4f}, conf={float(row[2]):.3f}, "
            f"era={row[3]}, actions_7d={row[4]}"
        )

    cur.close()
    conn.close()

    print("\n" + "=" * 70)
    print("🧠 NEURAL-ENHANCED TRUMP EFFECT FEATURES COMPLETE")
    print("=" * 70)
    print("\nKey improvements over baseline:")
    print(
        "  ✅ Policy Uncertainty (EPU) factor amplifies signals during high uncertainty"
    )
    print(
        "  ✅ VIX stress factor increases signal sensitivity during market volatility"
    )
    print("  ✅ ZL momentum alignment confirms/dampens signals based on price action")
    print("  ✅ Era multipliers weight Trump terms higher for trade policy impact")
    print("  ✅ Data-driven confidence scoring based on available sources")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
