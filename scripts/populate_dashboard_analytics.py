#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Populate Dashboard Analytics

Transforms raw specialist signals and price data into dashboard-ready analytics.
Run this after specialist models generate signals, or on a schedule.

Target tables:
  - analytics.driver_scores: Latest specialist signals with direction
  - analytics.vol_regimes: Volatility regime classification
  - analytics.dashboard_metrics: Key KPIs for dashboard display
  - analytics.event_probabilities_{H}d_1d: Historical probability distributions

Usage:
    python scripts/populate_dashboard_analytics.py
    python scripts/populate_dashboard_analytics.py --table driver_scores
    python scripts/populate_dashboard_analytics.py --all
"""

import argparse
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_connection():
    """Get database connection."""
    return psycopg2.connect(os.environ["DATABASE_URL"])


# =============================================================================
# DRIVER SCORES - Specialist signal aggregation for dashboard
# =============================================================================

def populate_driver_scores(conn, as_of_date: Optional[date] = None) -> int:
    """
    Populate analytics.driver_scores from training.specialist_signals_1d.

    Maps the latest signal per specialist bucket into the driver_scores table
    for dashboard consumption.
    """
    if as_of_date is None:
        as_of_date = date.today()

    cur = conn.cursor()

    # Get latest signal per bucket
    cur.execute("""
        SELECT DISTINCT ON (bucket)
            bucket,
            as_of_date,
            signal_1,
            signal_2,
            confidence,
            model_type
        FROM training.specialist_signals_1d
        WHERE as_of_date <= %s
        ORDER BY bucket, as_of_date DESC
    """, (as_of_date,))

    signals = cur.fetchall()

    if not signals:
        logger.warning("No specialist signals found")
        return 0

    # Map to driver_scores format
    rows = []
    for bucket, sig_date, sig1, sig2, conf, model_type in signals:
        # Determine direction from signal
        if sig1 is None:
            sig1 = 0
        direction = "bullish" if sig1 > 0.1 else "bearish" if sig1 < -0.1 else "neutral"

        # SHAP contribution placeholder (would come from model explainability)
        shap_contrib = abs(sig1) * (conf or 0.5)  # Proxy: signal magnitude * confidence

        rows.append((
            sig_date,
            bucket,
            sig1,
            direction,
            conf,
            shap_contrib
        ))

    # Upsert into driver_scores
    cur.execute("DELETE FROM analytics.driver_scores WHERE as_of_date = %s", (as_of_date,))

    insert_sql = """
        INSERT INTO analytics.driver_scores
            (as_of_date, specialist, signal, direction, confidence, shap_contribution)
        VALUES %s
        ON CONFLICT (as_of_date, specialist) DO UPDATE SET
            signal = EXCLUDED.signal,
            direction = EXCLUDED.direction,
            confidence = EXCLUDED.confidence,
            shap_contribution = EXCLUDED.shap_contribution
    """
    execute_values(cur, insert_sql, rows)
    conn.commit()

    logger.info(f"Populated analytics.driver_scores: {len(rows)} specialists for {as_of_date}")
    return len(rows)


# =============================================================================
# VOL REGIMES - Volatility regime classification
# =============================================================================

def populate_vol_regimes(conn, lookback_days: int = 252) -> int:
    """
    Populate analytics.vol_regimes from ZL price data.

    Classifies volatility into regimes:
    - low_vol: < 20% annualized
    - normal_vol: 20-30% annualized
    - high_vol: > 30% annualized
    """
    cur = conn.cursor()

    # Calculate rolling volatility
    cur.execute("""
        WITH returns AS (
            SELECT
                event_date,
                close,
                (close - LAG(close) OVER (ORDER BY event_date)) /
                    NULLIF(LAG(close) OVER (ORDER BY event_date), 0) as ret
            FROM analytics.zl_price_1d
            WHERE event_date >= CURRENT_DATE - INTERVAL '%s days'
        ),
        vol_windows AS (
            SELECT
                event_date,
                ret,
                STDDEV(ret) OVER (ORDER BY event_date ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) * SQRT(252) as vol_21d
            FROM returns
            WHERE ret IS NOT NULL
        )
        SELECT event_date, vol_21d
        FROM vol_windows
        WHERE vol_21d IS NOT NULL
        ORDER BY event_date DESC
        LIMIT %s
    """, (lookback_days + 30, lookback_days))

    vol_data = cur.fetchall()

    if not vol_data:
        logger.warning("No volatility data calculated")
        return 0

    rows = []
    for event_date, vol in vol_data:
        # Classify regime
        if vol < 0.20:
            regime = "low_vol"
            regime_prob = 1.0 - (vol / 0.20)  # Higher prob when deeper in regime
        elif vol < 0.30:
            regime = "normal_vol"
            regime_prob = 0.7  # Moderate certainty
        else:
            regime = "high_vol"
            regime_prob = min(1.0, (vol - 0.30) / 0.20 + 0.7)

        # Transition probabilities (empirical estimates)
        if regime == "low_vol":
            trans = {"stay": 0.85, "to_normal": 0.12, "to_high": 0.03}
        elif regime == "normal_vol":
            trans = {"to_low": 0.15, "stay": 0.70, "to_high": 0.15}
        else:
            trans = {"to_low": 0.05, "to_normal": 0.25, "stay": 0.70}

        rows.append((
            "ZL",
            event_date,
            regime,
            regime_prob,
            trans,
            regime_prob,
            "rolling_21d",
            "v1.0"
        ))

    # Upsert
    cur.execute("""
        DELETE FROM analytics.vol_regimes
        WHERE symbol = 'ZL' AND as_of_date >= CURRENT_DATE - INTERVAL '%s days'
    """, (lookback_days,))

    insert_sql = """
        INSERT INTO analytics.vol_regimes
            (symbol, as_of_date, regime, regime_prob, transition_probs, smoothed_prob, model_type, model_version)
        VALUES %s
        ON CONFLICT (symbol, as_of_date, model_version) DO UPDATE SET
            regime = EXCLUDED.regime,
            regime_prob = EXCLUDED.regime_prob,
            transition_probs = EXCLUDED.transition_probs,
            smoothed_prob = EXCLUDED.smoothed_prob
    """

    # Convert dicts to JSON strings for psycopg2
    import json
    rows_json = [(r[0], r[1], r[2], r[3], json.dumps(r[4]), r[5], r[6], r[7]) for r in rows]
    execute_values(cur, insert_sql, rows_json)
    conn.commit()

    logger.info(f"Populated analytics.vol_regimes: {len(rows)} days")
    return len(rows)


# =============================================================================
# EVENT PROBABILITIES - Historical probability distributions by horizon
# =============================================================================

def populate_event_probabilities(conn, horizon: int, lookback_years: int = 10) -> int:
    """
    Populate analytics.event_probabilities_{H}d_1d from historical returns.

    Computes empirical probabilities of various price moves.
    """
    cur = conn.cursor()
    table_name = f"analytics.event_probabilities_{horizon}d_1d"

    # Check if table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'analytics'
            AND table_name = %s
        )
    """, (f"event_probabilities_{horizon}d_1d",))

    if not cur.fetchone()[0]:
        logger.warning(f"Table {table_name} does not exist")
        return 0

    # Get column info to understand table structure
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'analytics' AND table_name = %s
        ORDER BY ordinal_position
    """, (f"event_probabilities_{horizon}d_1d",))
    cols = [r[0] for r in cur.fetchall()]
    logger.info(f"Table {table_name} columns: {cols}")

    # Calculate historical probabilities
    start_date = date.today() - timedelta(days=lookback_years * 365)

    cur.execute(f"""
        WITH returns AS (
            SELECT
                event_date,
                close,
                (close - LAG(close, {horizon}) OVER (ORDER BY event_date)) /
                    NULLIF(LAG(close, {horizon}) OVER (ORDER BY event_date), 0) as ret
            FROM analytics.zl_price_1d
            WHERE event_date >= %s
        )
        SELECT
            CURRENT_DATE as as_of_date,
            {horizon} as horizon_days,
            COUNT(*) as sample_size,
            AVG(CASE WHEN ret > 0 THEN 1 ELSE 0 END) as p_up,
            AVG(CASE WHEN ret < 0 THEN 1 ELSE 0 END) as p_down,
            AVG(CASE WHEN ret > 0.02 THEN 1 ELSE 0 END) as p_up_2pct,
            AVG(CASE WHEN ret > 0.05 THEN 1 ELSE 0 END) as p_up_5pct,
            AVG(CASE WHEN ret < -0.02 THEN 1 ELSE 0 END) as p_down_2pct,
            AVG(CASE WHEN ret < -0.05 THEN 1 ELSE 0 END) as p_down_5pct,
            STDDEV(ret) as volatility,
            AVG(ret) as expected_return
        FROM returns
        WHERE ret IS NOT NULL
    """, (start_date,))

    result = cur.fetchone()

    if not result or result[2] == 0:
        logger.warning(f"No data for {horizon}d horizon")
        return 0

    # Insert with available columns
    cur.execute(f"""
        DELETE FROM {table_name} WHERE as_of_date = CURRENT_DATE
    """)

    # Construct INSERT based on actual table columns
    # Common columns we expect
    insert_cols = []
    insert_vals = []

    col_mapping = {
        'as_of_date': result[0],
        'horizon_days': result[1],
        'sample_size': result[2],
        'p_up': result[3],
        'p_down': result[4],
        'p_up_2pct': result[5],
        'p_up_5pct': result[6],
        'p_down_2pct': result[7],
        'p_down_5pct': result[8],
        'volatility': result[9],
        'expected_return': result[10],
    }

    for col in cols:
        if col in col_mapping:
            insert_cols.append(col)
            insert_vals.append(col_mapping[col])

    if insert_cols:
        placeholders = ", ".join(["%s"] * len(insert_cols))
        col_names = ", ".join(insert_cols)
        cur.execute(f"""
            INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})
        """, insert_vals)
        conn.commit()
        logger.info(f"Populated {table_name}: 1 row with {len(insert_cols)} columns")
        return 1

    return 0


# =============================================================================
# DASHBOARD METRICS - Key KPIs
# =============================================================================

def populate_dashboard_metrics(conn) -> int:
    """
    Populate analytics.dashboard_metrics with key KPIs.
    """
    cur = conn.cursor()

    # Get current ZL price and changes
    cur.execute("""
        WITH latest AS (
            SELECT close, event_date
            FROM analytics.zl_price_1d
            ORDER BY event_date DESC
            LIMIT 1
        ),
        prev AS (
            SELECT close
            FROM analytics.zl_price_1d
            ORDER BY event_date DESC
            OFFSET 1 LIMIT 1
        )
        SELECT latest.close, latest.event_date, prev.close,
               (latest.close - prev.close) / NULLIF(prev.close, 0) as daily_change
        FROM latest, prev
    """)
    price_data = cur.fetchone()

    if not price_data:
        logger.warning("No price data for dashboard metrics")
        return 0

    current_price, price_date, prev_price, daily_change = price_data

    # Get aggregate specialist signal
    cur.execute("""
        SELECT
            AVG(signal_1) as avg_signal,
            AVG(confidence) as avg_conf,
            SUM(CASE WHEN signal_1 > 0.1 THEN 1
                     WHEN signal_1 < -0.1 THEN -1
                     ELSE 0 END) as net_direction
        FROM (
            SELECT DISTINCT ON (bucket) signal_1, confidence
            FROM training.specialist_signals_1d
            ORDER BY bucket, as_of_date DESC
        ) latest_signals
    """)
    signal_data = cur.fetchone()
    avg_signal = signal_data[0] or 0
    avg_conf = signal_data[1] or 0
    net_direction = signal_data[2] or 0

    # Determine overall stance
    if net_direction >= 3:
        stance = "strongly_bullish"
    elif net_direction >= 1:
        stance = "bullish"
    elif net_direction <= -3:
        stance = "strongly_bearish"
    elif net_direction <= -1:
        stance = "bearish"
    else:
        stance = "neutral"

    # Get current vol regime
    cur.execute("""
        SELECT regime FROM analytics.vol_regimes
        WHERE symbol = 'ZL'
        ORDER BY as_of_date DESC
        LIMIT 1
    """)
    vol_result = cur.fetchone()
    vol_regime = vol_result[0] if vol_result else "unknown"

    # Build metrics JSON
    import json
    metrics = {
        "zl_price": float(current_price),
        "zl_date": str(price_date),
        "daily_change_pct": float(daily_change * 100) if daily_change else 0,
        "specialist_avg_signal": float(avg_signal),
        "specialist_avg_conf": float(avg_conf),
        "specialist_net_direction": int(net_direction),
        "market_stance": stance,
        "vol_regime": vol_regime,
        "updated_at": datetime.utcnow().isoformat()
    }

    # Upsert (assuming dashboard_metrics has id, name, value, updated_at, json_value)
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'analytics' AND table_name = 'dashboard_metrics'")
    cols = [r[0] for r in cur.fetchall()]
    logger.info(f"dashboard_metrics columns: {cols}")

    # Try a simple approach - delete and insert
    cur.execute("DELETE FROM analytics.dashboard_metrics")

    # Insert each metric as a row if schema supports it
    if 'metric_name' in cols and 'metric_value' in cols:
        for name, value in metrics.items():
            cur.execute("""
                INSERT INTO analytics.dashboard_metrics (metric_name, metric_value)
                VALUES (%s, %s)
            """, (name, json.dumps(value)))
    elif 'name' in cols and 'value' in cols:
        for name, value in metrics.items():
            cur.execute("""
                INSERT INTO analytics.dashboard_metrics (name, value)
                VALUES (%s, %s)
            """, (name, str(value)))
    else:
        logger.warning(f"Unknown dashboard_metrics schema: {cols}")
        return 0

    conn.commit()
    logger.info(f"Populated analytics.dashboard_metrics: {len(metrics)} metrics")
    return len(metrics)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Populate dashboard analytics tables")
    parser.add_argument("--table", choices=["driver_scores", "vol_regimes", "event_probs", "dashboard_metrics", "all"],
                       default="all", help="Which table to populate")
    parser.add_argument("--date", type=str, help="As-of date (YYYY-MM-DD)")
    args = parser.parse_args()

    conn = get_connection()

    as_of = date.fromisoformat(args.date) if args.date else None

    if args.table in ["driver_scores", "all"]:
        populate_driver_scores(conn, as_of)

    if args.table in ["vol_regimes", "all"]:
        populate_vol_regimes(conn)

    if args.table in ["event_probs", "all"]:
        for horizon in [5, 21, 63, 126]:
            populate_event_probabilities(conn, horizon)

    if args.table in ["dashboard_metrics", "all"]:
        populate_dashboard_metrics(conn)

    conn.close()
    logger.info("Done!")


if __name__ == "__main__":
    main()
