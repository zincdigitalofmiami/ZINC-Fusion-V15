#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Monte Carlo Risk Engine

Runs Monte Carlo simulation using calibrated quantile distributions from
the meta-ensemble to generate risk metrics (VaR, CVaR, scenario analysis).

NON-NEGOTIABLES:
- Monte Carlo consumes distributions ONLY (no point estimates + noise)
- Input is calibrated P10/P50/P90 quantiles from meta_ensemble
- Generates value-at-risk (VaR), conditional VaR (CVaR)
- Produces scenario analysis for tail events

Architecture:
- Input: P10, P50, P90 from meta_ensemble (assumed logistic distribution)
- Simulation: 10,000 paths per horizon
- Output: VaR, CVaR, probability metrics, scenario flags

Usage:
    python scripts/run_monte_carlo.py --horizon 63 --dry-run
    python scripts/run_monte_carlo.py --horizon 63
    python scripts/run_monte_carlo.py --horizon all
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv
from scipy import stats

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

# Monte Carlo parameters
N_SIMULATIONS = 10000
VAR_LEVELS = [0.01, 0.05, 0.10]  # 1%, 5%, 10% VaR
RANDOM_SEED = 42


@dataclass
class RiskMetrics:
    """Risk metrics from Monte Carlo simulation."""
    as_of_date: datetime
    horizon: int
    var_01: float  # 1% VaR (99% confidence)
    var_05: float  # 5% VaR (95% confidence)
    var_10: float  # 10% VaR (90% confidence)
    cvar_05: float  # Expected loss beyond 5% VaR
    prob_up: float  # Probability of positive return
    prob_up_5pct: float  # Probability of >5% return
    prob_down_5pct: float  # Probability of <-5% return
    regime: str  # bull, bear, sideways
    tail_risk_flag: bool  # True if extreme downside risk detected


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def load_meta_predictions(conn, horizon: int) -> pd.DataFrame:
    """Load meta-ensemble predictions for a given horizon."""
    logger.info(f"Loading meta-ensemble predictions for horizon={horizon}d")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT as_of_date, p10, p50, p90
            FROM meta_ensemble
            WHERE horizon = %s
            ORDER BY as_of_date DESC
            LIMIT 1000
        """, (horizon,))

        rows = cur.fetchall()

    if not rows:
        raise ValueError(f"No meta-ensemble predictions found for horizon={horizon}")

    df = pd.DataFrame(rows, columns=['as_of_date', 'p10', 'p50', 'p90'])
    logger.info(f"  Loaded {len(df):,} predictions")

    return df


def fit_distribution(p10: float, p50: float, p90: float) -> Tuple[float, float]:
    """Fit a logistic distribution to quantiles.

    Uses P10, P50, P90 to estimate location (mu) and scale (s) parameters
    of a logistic distribution.

    Returns:
    - mu: location parameter (median)
    - s: scale parameter
    """
    # For logistic distribution:
    # P(X < x) = 1 / (1 + exp(-(x - mu) / s))
    #
    # At P10: 0.10 = 1 / (1 + exp(-(p10 - mu) / s))
    # At P50: 0.50 = 1 / (1 + exp(-(p50 - mu) / s)) => p50 = mu
    # At P90: 0.90 = 1 / (1 + exp(-(p90 - mu) / s))
    #
    # From P10 and P90:
    # logit(0.10) = -(p10 - mu) / s
    # logit(0.90) = -(p90 - mu) / s
    #
    # logit(0.10) = ln(0.10/0.90) ≈ -2.197
    # logit(0.90) = ln(0.90/0.10) ≈ +2.197

    mu = p50  # Median is the location

    # Calculate scale from P10 and P90
    logit_10 = np.log(0.10 / 0.90)  # ≈ -2.197
    logit_90 = np.log(0.90 / 0.10)  # ≈ +2.197

    # s = (p90 - mu) / logit_90 or s = (mu - p10) / (-logit_10)
    s_from_p90 = (p90 - mu) / logit_90
    s_from_p10 = (mu - p10) / (-logit_10)

    # Average the two estimates
    s = (s_from_p90 + s_from_p10) / 2

    # Ensure positive scale
    s = max(s, 0.001)

    return mu, s


def run_simulation(
    mu: float,
    s: float,
    n_simulations: int = N_SIMULATIONS
) -> np.ndarray:
    """Run Monte Carlo simulation using logistic distribution.

    Returns array of simulated returns.
    """
    np.random.seed(RANDOM_SEED)

    # Generate random draws from logistic distribution
    simulated_returns = stats.logistic.rvs(loc=mu, scale=s, size=n_simulations)

    return simulated_returns


def calculate_risk_metrics(
    simulated_returns: np.ndarray,
    as_of_date: datetime,
    horizon: int
) -> RiskMetrics:
    """Calculate risk metrics from simulated returns."""

    # Sort returns for VaR calculation
    sorted_returns = np.sort(simulated_returns)

    # VaR at different confidence levels (negative = loss)
    var_01 = np.percentile(sorted_returns, 1)  # 1st percentile
    var_05 = np.percentile(sorted_returns, 5)  # 5th percentile
    var_10 = np.percentile(sorted_returns, 10)  # 10th percentile

    # CVaR (Expected Shortfall) - average of returns below VaR
    cvar_05 = sorted_returns[sorted_returns <= var_05].mean()

    # Probability metrics
    prob_up = (simulated_returns > 0).mean()
    prob_up_5pct = (simulated_returns > 0.05).mean()
    prob_down_5pct = (simulated_returns < -0.05).mean()

    # Regime classification
    if prob_up > 0.55:
        regime = "bull"
    elif prob_up < 0.45:
        regime = "bear"
    else:
        regime = "sideways"

    # Tail risk flag - extreme downside risk
    # Flag if 5% VaR is worse than -10% or CVaR is worse than -15%
    tail_risk_flag = var_05 < -0.10 or cvar_05 < -0.15

    return RiskMetrics(
        as_of_date=as_of_date,
        horizon=horizon,
        var_01=var_01,
        var_05=var_05,
        var_10=var_10,
        cvar_05=cvar_05,
        prob_up=prob_up,
        prob_up_5pct=prob_up_5pct,
        prob_down_5pct=prob_down_5pct,
        regime=regime,
        tail_risk_flag=tail_risk_flag
    )


def save_risk_metrics(conn, metrics: List[RiskMetrics]) -> int:
    """Save risk metrics to Postgres."""

    # First ensure table exists
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS risk_metrics (
                id SERIAL PRIMARY KEY,
                as_of_date TIMESTAMP NOT NULL,
                horizon INTEGER NOT NULL,
                var_01 DOUBLE PRECISION NOT NULL,
                var_05 DOUBLE PRECISION NOT NULL,
                var_10 DOUBLE PRECISION NOT NULL,
                cvar_05 DOUBLE PRECISION NOT NULL,
                prob_up DOUBLE PRECISION NOT NULL,
                prob_up_5pct DOUBLE PRECISION NOT NULL,
                prob_down_5pct DOUBLE PRECISION NOT NULL,
                regime VARCHAR(20) NOT NULL,
                tail_risk_flag BOOLEAN NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(as_of_date, horizon)
            )
        """)
        conn.commit()

    insert_query = """
        INSERT INTO risk_metrics
        (as_of_date, horizon, var_01, var_05, var_10, cvar_05,
         prob_up, prob_up_5pct, prob_down_5pct, regime, tail_risk_flag)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (as_of_date, horizon)
        DO UPDATE SET
            var_01 = EXCLUDED.var_01,
            var_05 = EXCLUDED.var_05,
            var_10 = EXCLUDED.var_10,
            cvar_05 = EXCLUDED.cvar_05,
            prob_up = EXCLUDED.prob_up,
            prob_up_5pct = EXCLUDED.prob_up_5pct,
            prob_down_5pct = EXCLUDED.prob_down_5pct,
            regime = EXCLUDED.regime,
            tail_risk_flag = EXCLUDED.tail_risk_flag
    """

    batch = [
        (m.as_of_date, m.horizon, float(m.var_01), float(m.var_05), float(m.var_10), float(m.cvar_05),
         float(m.prob_up), float(m.prob_up_5pct), float(m.prob_down_5pct), m.regime, bool(m.tail_risk_flag))
        for m in metrics
    ]

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    conn.commit()

    return len(batch)


def run_monte_carlo(horizon: int, dry_run: bool = False) -> List[RiskMetrics]:
    """Run Monte Carlo simulation for a given horizon."""
    logger.info("=" * 60)
    logger.info(f"MONTE CARLO SIMULATION @ {horizon}d")
    logger.info("=" * 60)
    logger.info(f"  N_SIMULATIONS: {N_SIMULATIONS:,}")
    logger.info(f"  VAR_LEVELS: {VAR_LEVELS}")

    conn = get_postgres_connection()

    try:
        # Load meta-ensemble predictions
        predictions_df = load_meta_predictions(conn, horizon)

        all_metrics = []

        for _, row in predictions_df.iterrows():
            as_of_date = row['as_of_date']
            p10, p50, p90 = row['p10'], row['p50'], row['p90']

            # Fit distribution to quantiles
            mu, s = fit_distribution(p10, p50, p90)

            # Run simulation
            simulated_returns = run_simulation(mu, s)

            # Calculate risk metrics
            metrics = calculate_risk_metrics(simulated_returns, as_of_date, horizon)
            all_metrics.append(metrics)

        # Log summary
        latest_metrics = all_metrics[0]
        logger.info(f"\nLatest risk metrics ({latest_metrics.as_of_date.date()}):")
        logger.info(f"  VaR 1%:  {latest_metrics.var_01:+.2%}")
        logger.info(f"  VaR 5%:  {latest_metrics.var_05:+.2%}")
        logger.info(f"  VaR 10%: {latest_metrics.var_10:+.2%}")
        logger.info(f"  CVaR 5%: {latest_metrics.cvar_05:+.2%}")
        logger.info(f"  Prob Up: {latest_metrics.prob_up:.1%}")
        logger.info(f"  Prob >5%: {latest_metrics.prob_up_5pct:.1%}")
        logger.info(f"  Prob <-5%: {latest_metrics.prob_down_5pct:.1%}")
        logger.info(f"  Regime: {latest_metrics.regime}")
        logger.info(f"  Tail Risk: {latest_metrics.tail_risk_flag}")

        if dry_run:
            logger.info(f"\n[DRY RUN] Would save {len(all_metrics):,} risk metrics")
            return all_metrics

        # Save to database
        saved = save_risk_metrics(conn, all_metrics)
        logger.info(f"\n  Saved {saved:,} risk metrics")

        logger.info(f"\n✅ Completed Monte Carlo @ {horizon}d")

        return all_metrics

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Run Monte Carlo risk simulation")
    parser.add_argument("--horizon", type=str, required=True,
                       help="Horizon in days (5, 21, 63, 126) or 'all'")
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
            run_monte_carlo(horizon, args.dry_run)
        except Exception as e:
            logger.error(f"Failed Monte Carlo @ {horizon}d: {e}")
            raise

    logger.info("\n" + "=" * 60)
    logger.info("MONTE CARLO SIMULATION COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
