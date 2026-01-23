#!/usr/bin/env python3
"""
ZINC-FUSION-V15: L5-D Historical Analogs Engine

Finds historical periods with similar market characteristics to the current state.
Uses a weighted similarity score combining forecast geometry, regime, and driver rankings.

NON-NEGOTIABLES:
- All similarity is mathematical - no subjective interpretation
- Historical outcomes are facts, not predictions
- Analogs provide context, not forecasts
- Similarity score is transparent and reproducible

Architecture (L5-D):
- Input: Current P50, spread, regime, driver rankings from L4
- Process: Multi-component similarity scoring against historical states
- Output: Top N analog periods with similarity scores and actual outcomes
- Storage: analytics.historical_analogs

Similarity Components:
- p50_sim: How close is the forecast level? (30% weight)
- spread_sim: How similar is the uncertainty envelope? (25% weight)
- regime_match: Same volatility regime? (25% weight)
- driver_corr: Similar driver importance rankings? (20% weight)

Usage:
    python scripts/find_analogs.py --horizon 63 --dry-run
    python scripts/find_analogs.py --horizon 63 --top-n 5
    python scripts/find_analogs.py --horizon all
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from scipy import stats
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv('.env.vercel')

# Horizons
HORIZONS = [5, 21, 63, 126]

# Similarity weights (from architecture spec)
SIMILARITY_WEIGHTS = {
    'p50_sim': 0.30,
    'spread_sim': 0.25,
    'regime_match': 0.25,
    'driver_corr': 0.20,
}

# Minimum lookback for historical analogs (days)
MIN_LOOKBACK_DAYS = 252  # At least 1 year of history

# Exclude recent periods to avoid data leakage
EXCLUSION_WINDOW_DAYS = 63  # Don't match recent periods


@dataclass
class MarketState:
    """Snapshot of market state at a point in time."""
    as_of_date: datetime
    horizon: int
    p50: float
    spread: float  # P90 - P10
    regime: str
    driver_ranks: Dict[str, int]  # Feature -> rank by importance


@dataclass
class AnalogResult:
    """Historical analog match result."""
    period: str  # Human-readable period label
    as_of_date: datetime
    similarity: float  # 0-1 overall score
    actual_outcome: Optional[float]  # Forward return if available
    components: Dict[str, float]  # Individual similarity components


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def load_current_state(conn, horizon: int) -> MarketState:
    """Load the current (latest) market state for comparison."""
    logger.info(f"Loading current market state for horizon={horizon}d")

    # Get latest meta-ensemble forecast
    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, p10, p50, p90
            FROM "model"."meta_ensemble"
            WHERE horizon = %s
            ORDER BY as_of_date DESC
            LIMIT 1
        """, (horizon,))
        row = cur.fetchone()

    if not row:
        raise ValueError(f"No meta-ensemble data for horizon={horizon}")

    as_of_date = row[0]
    p10, p50, p90 = float(row[1]), float(row[2]), float(row[3])
    spread = p90 - p10

    # Get current regime
    with conn.cursor() as cur:
        cur.execute("""
            SELECT regime
            FROM "analytics"."vol_regimes"
            WHERE as_of_date <= %s
            ORDER BY as_of_date DESC
            LIMIT 1
        """, (as_of_date,))
        row = cur.fetchone()

    regime = row[0] if row else 'normal'

    # Get driver rankings from SHAP
    driver_ranks = load_driver_ranks(conn, horizon, as_of_date)

    logger.info(f"  Current state: {as_of_date.date()}")
    logger.info(f"    P50: {p50:.2f}, Spread: {spread:.2f}")
    logger.info(f"    Regime: {regime}")
    logger.info(f"    Top drivers: {list(driver_ranks.keys())[:3]}")

    return MarketState(
        as_of_date=as_of_date,
        horizon=horizon,
        p50=p50,
        spread=spread,
        regime=regime,
        driver_ranks=driver_ranks,
    )


def load_driver_ranks(conn, horizon: int, as_of_date: datetime) -> Dict[str, int]:
    """Load driver importance rankings from SHAP summary."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT feature_name, mean_abs_shap
                FROM "model"."shap_summary"
                WHERE horizon = %s
                ORDER BY mean_abs_shap DESC
                LIMIT 10
            """, (horizon,))
            rows = cur.fetchall()

        if not rows:
            # Return default rankings if no SHAP data
            return {f"feature_{i}": i for i in range(10)}

        return {row[0]: i for i, row in enumerate(rows)}
    except Exception:
        # Table may not exist yet - rollback and return defaults
        conn.rollback()
        return {f"feature_{i}": i for i in range(10)}


def load_historical_states(
    conn,
    horizon: int,
    current_date: datetime,
    min_lookback: int = MIN_LOOKBACK_DAYS
) -> List[MarketState]:
    """Load historical market states for comparison."""
    logger.info(f"Loading historical states (lookback: {min_lookback}+ days)")

    # Calculate date range
    # Exclude recent periods to avoid data leakage
    end_date = current_date - timedelta(days=EXCLUSION_WINDOW_DAYS)
    start_date = end_date - timedelta(days=min_lookback * 3)  # Extra buffer

    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, p10, p50, p90
            FROM "model"."meta_ensemble"
            WHERE horizon = %s
              AND as_of_date BETWEEN %s AND %s
            ORDER BY as_of_date
        """, (horizon, start_date, end_date))
        rows = cur.fetchall()

    if not rows:
        logger.warning(f"  No historical data found in date range")
        return []

    logger.info(f"  Found {len(rows)} historical snapshots")

    # Load regime history
    regime_history = load_regime_history(conn, start_date, end_date)

    # Build historical states
    states = []
    for row in rows:
        as_of_date = row[0]
        p10, p50, p90 = float(row[1]), float(row[2]), float(row[3])
        spread = p90 - p10

        regime = regime_history.get(as_of_date.date(), 'normal')
        driver_ranks = load_driver_ranks(conn, horizon, as_of_date)

        states.append(MarketState(
            as_of_date=as_of_date,
            horizon=horizon,
            p50=p50,
            spread=spread,
            regime=regime,
            driver_ranks=driver_ranks,
        ))

    return states


def load_regime_history(conn, start_date: datetime, end_date: datetime) -> Dict:
    """Load volatility regime history."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, regime
            FROM "analytics"."vol_regimes"
            WHERE as_of_date BETWEEN %s AND %s
        """, (start_date, end_date))
        rows = cur.fetchall()

    return {row[0].date() if hasattr(row[0], 'date') else row[0]: row[1] for row in rows}


def load_actual_outcomes(conn, horizon: int) -> Dict[datetime, float]:
    """Load actual forward returns for historical periods."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT event_date, close
                FROM "mkt"."futures_1d"
                WHERE symbol = 'ZL'
                ORDER BY event_date
            """)
            rows = cur.fetchall()

        if not rows:
            return {}

        df = pd.DataFrame(rows, columns=['as_of_date', 'close'])
        df['forward_return'] = df['close'].shift(-horizon) / df['close'] - 1

        return dict(zip(df['as_of_date'], df['forward_return']))
    except Exception:
        # Table may not exist
        conn.rollback()
        return {}


def calculate_p50_similarity(current: float, historical: float) -> float:
    """Calculate similarity based on forecast level.

    Uses relative difference with diminishing returns for larger differences.
    """
    if abs(current) < 1e-6:
        return 0.0

    rel_diff = abs(current - historical) / abs(current)

    # Similarity decreases exponentially with difference
    # 10% difference -> ~0.9 similarity
    # 50% difference -> ~0.6 similarity
    similarity = np.exp(-rel_diff)

    return float(np.clip(similarity, 0, 1))


def calculate_spread_similarity(current: float, historical: float) -> float:
    """Calculate similarity based on uncertainty envelope width."""
    if current < 1e-6:
        return 0.0

    rel_diff = abs(current - historical) / current

    # Penalize large spread differences more heavily
    similarity = 1 - min(rel_diff, 1.0)

    return float(similarity)


def calculate_regime_match(current: str, historical: str) -> float:
    """Calculate regime similarity.

    Exact match = 1.0, adjacent = 0.5, distant = 0.0
    """
    # Regime adjacency map
    regime_order = ['suppressed', 'low', 'normal', 'elevated', 'high']

    if current == historical:
        return 1.0

    try:
        current_idx = regime_order.index(current.lower())
        hist_idx = regime_order.index(historical.lower())
        distance = abs(current_idx - hist_idx)

        # Adjacent regimes get partial credit
        if distance == 1:
            return 0.5
        elif distance == 2:
            return 0.25
        else:
            return 0.0
    except ValueError:
        # Unknown regime
        return 0.5 if current.lower() == historical.lower() else 0.0


def calculate_driver_correlation(
    current_ranks: Dict[str, int],
    historical_ranks: Dict[str, int]
) -> float:
    """Calculate Spearman correlation of driver importance rankings."""
    # Find common features
    common_features = set(current_ranks.keys()) & set(historical_ranks.keys())

    if len(common_features) < 3:
        return 0.5  # Not enough overlap

    # Build rank vectors
    current_vec = [current_ranks[f] for f in common_features]
    historical_vec = [historical_ranks[f] for f in common_features]

    # Calculate Spearman correlation
    try:
        corr, _ = stats.spearmanr(current_vec, historical_vec)
        # Convert correlation (-1 to 1) to similarity (0 to 1)
        similarity = (corr + 1) / 2
        return float(similarity)
    except Exception:
        return 0.5


def calculate_similarity(
    current: MarketState,
    historical: MarketState
) -> Tuple[float, Dict[str, float]]:
    """Calculate overall similarity score with component breakdown."""
    components = {
        'p50_sim': calculate_p50_similarity(current.p50, historical.p50),
        'spread_sim': calculate_spread_similarity(current.spread, historical.spread),
        'regime_match': calculate_regime_match(current.regime, historical.regime),
        'driver_corr': calculate_driver_correlation(
            current.driver_ranks, historical.driver_ranks
        ),
    }

    # Weighted sum
    overall = sum(
        components[key] * SIMILARITY_WEIGHTS[key]
        for key in SIMILARITY_WEIGHTS
    )

    return overall, components


def format_period_label(dt: datetime) -> str:
    """Format datetime as human-readable period label."""
    return dt.strftime("%b %Y")


def find_analogs(
    current: MarketState,
    historical_states: List[MarketState],
    actual_outcomes: Dict[datetime, float],
    top_n: int = 5
) -> List[AnalogResult]:
    """Find top N historical analogs for current state."""
    logger.info(f"Finding top {top_n} analogs from {len(historical_states)} candidates")

    results = []
    for hist_state in historical_states:
        similarity, components = calculate_similarity(current, hist_state)

        # Get actual outcome if available
        actual = actual_outcomes.get(hist_state.as_of_date)

        results.append(AnalogResult(
            period=format_period_label(hist_state.as_of_date),
            as_of_date=hist_state.as_of_date,
            similarity=similarity,
            actual_outcome=actual,
            components=components,
        ))

    # Sort by similarity (descending)
    results.sort(key=lambda x: x.similarity, reverse=True)

    # Return top N
    return results[:top_n]


def save_analogs(
    conn,
    current_date: datetime,
    horizon: int,
    analogs: List[AnalogResult]
) -> int:
    """Save analog results to analytics.historical_analogs."""
    logger.info(f"Saving {len(analogs)} analogs to analytics.historical_analogs")

    # Ensure table exists
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS "analytics"."historical_analogs" (
                id SERIAL PRIMARY KEY,
                as_of_date DATE NOT NULL,
                horizon INTEGER NOT NULL,
                analog_period VARCHAR(50) NOT NULL,
                analog_date DATE NOT NULL,
                similarity_score NUMERIC(5,4) NOT NULL,
                actual_outcome NUMERIC(8,4),
                p50_sim NUMERIC(5,4),
                spread_sim NUMERIC(5,4),
                regime_match NUMERIC(5,4),
                driver_corr NUMERIC(5,4),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(as_of_date, horizon, analog_date)
            )
        """)
        conn.commit()

    # Clear existing analogs for this date/horizon
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM "analytics"."historical_analogs"
            WHERE as_of_date = %s AND horizon = %s
        """, (current_date, horizon))

    batch = []
    for analog in analogs:
        batch.append((
            current_date,
            horizon,
            analog.period,
            analog.as_of_date,
            float(analog.similarity),
            float(analog.actual_outcome) if analog.actual_outcome is not None else None,
            float(analog.components.get('p50_sim', 0)),
            float(analog.components.get('spread_sim', 0)),
            float(analog.components.get('regime_match', 0)),
            float(analog.components.get('driver_corr', 0)),
            datetime.now(),
        ))

    insert_query = """
        INSERT INTO "analytics"."historical_analogs"
        (as_of_date, horizon, analog_period, analog_date, similarity_score,
         actual_outcome, p50_sim, spread_sim, regime_match, driver_corr, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=100)
    conn.commit()

    return len(batch)


def run_analog_search(horizon: int, top_n: int = 5, dry_run: bool = False) -> List[AnalogResult]:
    """Run historical analog search for a given horizon."""
    logger.info("=" * 60)
    logger.info(f"L5-D HISTORICAL ANALOG SEARCH @ {horizon}d")
    logger.info("=" * 60)
    logger.info(f"  Top N: {top_n}")
    logger.info(f"  Similarity weights: {SIMILARITY_WEIGHTS}")

    conn = get_postgres_connection()

    try:
        # Load current state
        current = load_current_state(conn, horizon)

        # Load historical states
        historical_states = load_historical_states(conn, horizon, current.as_of_date)

        if not historical_states:
            logger.warning("  No historical states available for comparison")
            return []

        # Load actual outcomes
        actual_outcomes = load_actual_outcomes(conn, horizon)

        # Find analogs
        analogs = find_analogs(current, historical_states, actual_outcomes, top_n)

        # Log results
        logger.info(f"\n{'='*40}")
        logger.info("TOP HISTORICAL ANALOGS")
        logger.info(f"{'='*40}")
        for i, analog in enumerate(analogs, 1):
            outcome_str = f"{analog.actual_outcome:+.1%}" if analog.actual_outcome else "N/A"
            logger.info(f"  {i}. {analog.period} ({analog.as_of_date.date()})")
            logger.info(f"     Similarity: {analog.similarity:.1%}")
            logger.info(f"     Outcome: {outcome_str}")
            logger.info(f"     Components: p50={analog.components['p50_sim']:.2f}, "
                       f"spread={analog.components['spread_sim']:.2f}, "
                       f"regime={analog.components['regime_match']:.2f}, "
                       f"drivers={analog.components['driver_corr']:.2f}")

        if dry_run:
            logger.info(f"\n[DRY RUN] Would save {len(analogs)} analogs")
            return analogs

        # Save to database
        saved = save_analogs(conn, current.as_of_date, horizon, analogs)
        logger.info(f"\n  Saved {saved} analogs to analytics.historical_analogs")

        logger.info(f"\n{'='*60}")
        logger.info(f"L5-D ANALOG SEARCH COMPLETE @ {horizon}d")
        logger.info(f"{'='*60}")

        return analogs

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Find historical market analogs")
    parser.add_argument("--horizon", type=str, required=True,
                       help="Horizon in days (5, 21, 63, 126) or 'all'")
    parser.add_argument("--top-n", type=int, default=5,
                       help="Number of analogs to return (default: 5)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview without saving")

    args = parser.parse_args()

    # Determine horizons to process
    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        horizon = int(args.horizon)
        if horizon not in HORIZONS:
            logger.error(f"Invalid horizon: {horizon}. Must be one of {HORIZONS}")
            sys.exit(1)
        horizons = [horizon]

    # Run for each horizon
    for horizon in horizons:
        try:
            run_analog_search(horizon, args.top_n, args.dry_run)
        except Exception as e:
            logger.error(f"Failed analog search @ {horizon}d: {e}")
            if not args.dry_run:
                raise

    logger.info("\n" + "=" * 60)
    logger.info("HISTORICAL ANALOG SEARCH COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
