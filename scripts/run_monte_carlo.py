#!/usr/bin/env python3
"""
ZINC-FUSION-V15: L5-A Monte Carlo Risk Engine

Runs Monte Carlo simulation using calibrated quantile distributions from
forecasts.production_1d to generate risk metrics, probability distributions,
and path statistics for visualization.

NON-NEGOTIABLES:
- Monte Carlo consumes L4 distributions ONLY (no point estimates + noise)
- Input is calibrated P10/P50/P90 quantiles from meta_ensemble
- Asymmetric volatility respecting quantile geometry
- Regime-adjusted volatility multipliers
- No user sliders or controls - deterministic from inputs
- Generates VaR, CVaR, full probability distributions

Architecture (L5-A):
- Input: P10/P50/P90 from meta_ensemble + vol_regime
- Process: Asymmetric path simulation with regime adjustment
- Output: monte_carlo_runs, probability_distributions, risk_metrics
- Visuals: Path percentiles for pinball/density rendering

Usage:
    python scripts/run_monte_carlo.py --horizon 63 --dry-run
    python scripts/run_monte_carlo.py --horizon 63
    python scripts/run_monte_carlo.py --horizon all
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json, execute_batch
from scipy import stats

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# GARCH volatility forecasting
from src.fusion.forecasting.volatility import garch_volatility_for_monte_carlo

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv(".env.vercel")

# Horizons
HORIZONS = [5, 21, 63, 126]

# Monte Carlo parameters
N_SIMULATIONS = 10000
VAR_LEVELS = [0.01, 0.05, 0.10]  # 1%, 5%, 10% VaR
PERCENTILES = [1, 5, 10, 25, 50, 75, 90, 95, 99]
RANDOM_SEED = 42

# Regime volatility multipliers (from L5-A spec)
REGIME_MULTIPLIERS = {
    "high": 1.5,
    "elevated": 1.25,
    "normal": 1.0,
    "low": 0.7,
    "suppressed": 0.5,
}


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
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    if database_url.startswith("prisma+postgres://"):
        raise ValueError(
            "DATABASE_URL must be a direct postgres:// or postgresql:// URL"
        )
    return psycopg2.connect(database_url)


def load_production_predictions(conn, horizon: int) -> pd.DataFrame:
    """Load production forecasts for a given horizon from forecasts.production_1d."""
    logger.info(f"Loading production forecasts for horizon={horizon}d")

    with conn.cursor() as cur:
        cur.execute(
            """
                        SELECT
                                as_of_date,
                                current_price,
                                price_p30,
                                price_p50,
                                price_p70,
                                price_p10_cal,
                                price_p90_cal
                        FROM forecasts.production_1d
            WHERE horizon = %s
                            AND current_price IS NOT NULL
                            AND price_p50 IS NOT NULL
            ORDER BY as_of_date DESC
            LIMIT 1000
        """,
            (horizon,),
        )

        rows = cur.fetchall()

    if not rows:
        return None  # Let caller handle gracefully

    df = pd.DataFrame(
        rows,
        columns=[
            "as_of_date",
            "current_price",
            "p30",
            "p50",
            "p70",
            "p10_cal",
            "p90_cal",
        ],
    )

    # Ensure tails are available; fallback to symmetric expansion from p30/p50/p70
    df["p10"] = df["p10_cal"]
    df["p90"] = df["p90_cal"]
    missing_10 = df["p10"].isna()
    missing_90 = df["p90"].isna()
    df.loc[missing_10, "p10"] = df.loc[missing_10, "p30"] - (
        df.loc[missing_10, "p50"] - df.loc[missing_10, "p30"]
    )
    df.loc[missing_90, "p90"] = df.loc[missing_90, "p70"] + (
        df.loc[missing_90, "p70"] - df.loc[missing_90, "p50"]
    )

    logger.info(f"  Loaded {len(df):,} production rows")

    # Staleness guard — reject inputs older than 5 business days, warn after 2
    latest_date = pd.Timestamp(df["as_of_date"].max())
    now = pd.Timestamp.now()
    bdays_stale = len(pd.bdate_range(latest_date, now)) - 1
    if bdays_stale > 5:
        raise ValueError(
            f"Stale production forecasts: latest as_of_date={latest_date.date()}, "
            f"{bdays_stale} business days old. Run generate_production_forecasts.py first."
        )
    if bdays_stale > 2:
        logger.warning(
            f"  Production forecasts are {bdays_stale} business days stale "
            f"(latest={latest_date.date()}). Consider re-running forecast generator."
        )

    return df


def load_historical_returns(conn, lookback_days: int = 500) -> np.ndarray:
    """Load historical ZL returns for GARCH calibration."""
    logger.info(f"Loading {lookback_days} days of ZL returns for GARCH...")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_date, close
            FROM "mkt"."futures_1d"
            WHERE symbol = 'ZL'
            ORDER BY event_date DESC
            LIMIT %s
        """,
            (lookback_days + 1,),
        )

        rows = cur.fetchall()

    if len(rows) < 100:
        logger.warning(f"Only {len(rows)} days of data - GARCH may be unstable")
        return None

    df = pd.DataFrame(rows, columns=["as_of_date", "close"])
    df = df.sort_values("as_of_date")
    returns = df["close"].pct_change().dropna().values

    logger.info(f"  Loaded {len(returns)} daily returns")
    return returns


def load_current_regime(conn, as_of_date: datetime | None = None) -> str:
    """Load the current volatility regime from vol_regimes table."""
    with conn.cursor() as cur:
        if as_of_date:
            cur.execute(
                """
                SELECT regime
                FROM "analytics"."vol_regimes"
                WHERE as_of_date <= %s
                ORDER BY as_of_date DESC
                LIMIT 1
            """,
                (as_of_date,),
            )
        else:
            cur.execute("""
                SELECT regime
                FROM "analytics"."vol_regimes"
                ORDER BY as_of_date DESC
                LIMIT 1
            """)

        row = cur.fetchone()

    if row:
        regime = row[0].lower() if row[0] else "normal"
        return regime
    else:
        return "normal"


def simulate_paths_asymmetric(
    p10: float,
    p50: float,
    p90: float,
    start_price: float,
    horizon: int,
    rng: np.random.Generator,
    vol_regime: str = "normal",
    n_sims: int = N_SIMULATIONS,
) -> np.ndarray:
    """
    Simulate price paths using asymmetric diffusion (L5-A spec).

    The quantile spread (P90-P10) defines the uncertainty envelope.
    Asymmetry between upper and lower tails is preserved.

    Args:
        p10: 10th percentile forecast (floor)
        p50: 50th percentile forecast (median)
        p90: 90th percentile forecast (ceiling)
        start_price: Current price level
        horizon: Forecast horizon in days
        rng: Local numpy Generator for reproducible, thread-safe randomness
        vol_regime: Current volatility regime
        n_sims: Number of simulations

    Returns:
        Array of shape (n_sims, horizon+1) with simulated paths
    """
    # Extract implied volatilities from quantile spread
    # Using inverse normal CDF: P10 = mu - 1.28*sigma, P90 = mu + 1.28*sigma
    z_90 = stats.norm.ppf(0.90)  # ≈ 1.28

    # Asymmetric volatilities (total spread over horizon)
    sigma_down = (p50 - p10) / abs(stats.norm.ppf(0.10))  # Downside vol
    sigma_up = (p90 - p50) / z_90  # Upside vol

    # Regime adjustment
    vol_mult = REGIME_MULTIPLIERS.get(vol_regime, 1.0)
    sigma_down *= vol_mult
    sigma_up *= vol_mult

    # Convert to daily volatility
    daily_sigma_down = sigma_down / np.sqrt(horizon)
    daily_sigma_up = sigma_up / np.sqrt(horizon)

    # Initialize paths
    paths = np.zeros((n_sims, horizon + 1))
    paths[:, 0] = start_price

    # Generate shocks (local rng — reproducible regardless of call order)
    shocks = rng.normal(0, 1, (n_sims, horizon))

    # Apply asymmetric diffusion
    for t in range(horizon):
        current_prices = paths[:, t]

        # Asymmetric volatility based on shock direction
        vol = np.where(shocks[:, t] > 0, daily_sigma_up, daily_sigma_down)

        # Price change (multiplicative for returns)
        returns = shocks[:, t] * vol
        paths[:, t + 1] = current_prices * (1 + returns)

    return paths


def simulate_paths_garch(
    p10: float,
    p50: float,
    p90: float,
    start_price: float,
    horizon: int,
    historical_returns: np.ndarray,
    rng: np.random.Generator,
    vol_regime: str = "normal",
    n_sims: int = N_SIMULATIONS,
) -> np.ndarray:
    """
    Simulate price paths using GARCH volatility forecasting.

    This is the ENHANCED simulation method that uses GJR-GARCH to forecast
    volatility with proper clustering and asymmetry (leverage effect).

    Raises RuntimeError if GARCH fitting fails — caller handles fallback
    with explicit model labeling.

    Args:
        p10: 10th percentile forecast (floor)
        p50: 50th percentile forecast (median)
        p90: 90th percentile forecast (ceiling)
        start_price: Current price level
        horizon: Forecast horizon in days
        historical_returns: Historical return series for GARCH calibration
        rng: Local numpy Generator for reproducible, thread-safe randomness
        vol_regime: Current volatility regime
        n_sims: Number of simulations

    Returns:
        Array of shape (n_sims, horizon+1) with simulated paths
    """
    # Fit GARCH model — let failures propagate to caller for honest labeling
    garch_vol, upside_mult, downside_mult = garch_volatility_for_monte_carlo(
        historical_returns, horizon=horizon, model_type="gjr-garch"
    )
    logger.info(
        f"  GARCH volatility forecast: mean={np.mean(garch_vol):.4f}, terminal={garch_vol[-1]:.4f}"
    )

    # Regime adjustment on top of GARCH
    vol_mult = REGIME_MULTIPLIERS.get(vol_regime, 1.0)

    # Initialize paths
    paths = np.zeros((n_sims, horizon + 1))
    paths[:, 0] = start_price

    # Generate shocks (local rng — reproducible regardless of call order)
    shocks = rng.standard_t(df=5, size=(n_sims, horizon))  # Fat-tailed shocks
    shocks = shocks / np.std(shocks)  # Normalize to unit variance

    # Apply GARCH-based diffusion
    for t in range(horizon):
        current_prices = paths[:, t]

        # Daily volatility from GARCH forecast + regime adjustment
        daily_vol = garch_vol[t] * vol_mult

        # Asymmetric adjustment based on shock direction
        vol = np.where(
            shocks[:, t] > 0, daily_vol * upside_mult, daily_vol * downside_mult
        )

        # Price change (multiplicative)
        returns = shocks[:, t] * vol
        paths[:, t + 1] = current_prices * (1 + returns)

    return paths


def compute_path_percentiles(paths: np.ndarray) -> dict:
    """Compute percentiles at each timestep for visualization."""
    n_sims, n_steps = paths.shape

    path_percentiles = {}
    for p in PERCENTILES:
        path_percentiles[p] = [
            float(np.percentile(paths[:, t], p)) for t in range(n_steps)
        ]

    return path_percentiles


def fit_distribution(p10: float, p50: float, p90: float) -> tuple[float, float]:
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
    mu: float, s: float, rng: np.random.Generator, n_simulations: int = N_SIMULATIONS
) -> np.ndarray:
    """Run Monte Carlo simulation using logistic distribution.

    Returns array of simulated returns.
    """
    # Use local rng for reproducibility (scipy accepts numpy Generator)
    simulated_returns = stats.logistic.rvs(
        loc=mu, scale=s, size=n_simulations, random_state=rng
    )

    return simulated_returns


def calculate_risk_metrics(
    simulated_returns: np.ndarray, as_of_date: datetime, horizon: int
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
        tail_risk_flag=tail_risk_flag,
    )


def save_risk_metrics(conn, metrics: list[RiskMetrics]) -> int:
    """Save risk metrics to Postgres."""

    insert_query = """
        INSERT INTO analytics.risk_metrics
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
        (
            m.as_of_date,
            m.horizon,
            float(m.var_01),
            float(m.var_05),
            float(m.var_10),
            float(m.cvar_05),
            float(m.prob_up),
            float(m.prob_up_5pct),
            float(m.prob_down_5pct),
            m.regime,
            bool(m.tail_risk_flag),
        )
        for m in metrics
    ]

    with conn.cursor() as cur:
        execute_batch(cur, insert_query, batch, page_size=1000)
    # No commit here — caller owns the transaction boundary

    return len(batch)


def save_path_percentiles(
    conn, as_of_date: datetime, horizon: int, path_percentiles: dict, model_version: str
):
    """Save path percentiles to probability_distributions table (atomic upsert)."""
    batch = []
    for percentile, values in path_percentiles.items():
        batch.append(
            (
                "ZL",
                as_of_date,
                horizon,
                float(percentile),
                values[-1],  # Terminal value
                model_version,
                datetime.now(),
            )
        )

    with conn.cursor() as cur:
        execute_batch(
            cur,
            """
            INSERT INTO forecasts.probability_distributions
            (symbol, as_of_date, horizon, percentile, value, model_version, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, as_of_date, horizon, percentile)
            DO UPDATE SET
                value = EXCLUDED.value,
                model_version = EXCLUDED.model_version,
                created_at = EXCLUDED.created_at
        """,
            batch,
        )
    # No commit here — caller owns the transaction boundary


def save_monte_carlo_run(
    conn,
    as_of_date: datetime,
    horizon: int,
    path_percentiles: dict,
    n_sims: int,
    model_version: str,
):
    """Save Monte Carlo run summary to monte_carlo_runs table."""
    with conn.cursor() as cur:
        # Clear existing
        cur.execute(
            """
            DELETE FROM forecasts.monte_carlo_runs
            WHERE symbol = 'ZL' AND as_of_date = %s AND horizon = %s
        """,
            (as_of_date, horizon),
        )

        # Insert summary with full path data for visualization
        cur.execute(
            """
            INSERT INTO forecasts.monte_carlo_runs
            (symbol, as_of_date, horizon, num_sims, percentiles, model_version, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
            (
                "ZL",
                as_of_date,
                horizon,
                n_sims,
                Json(path_percentiles),
                model_version,
                datetime.now(),
            ),
        )
    # No commit here — caller owns the transaction boundary


def validate_quantile_ordering(p10: float, p50: float, p90: float, as_of_date) -> None:
    """Ensure strict quantile ordering p10 < p50 < p90.

    Raises ValueError on crossing — prevents nonsensical simulation paths.
    """
    if p10 >= p50:
        raise ValueError(
            f"Quantile crossing at {as_of_date}: p10={p10:.6f} >= p50={p50:.6f}"
        )
    if p50 >= p90:
        raise ValueError(
            f"Quantile crossing at {as_of_date}: p50={p50:.6f} >= p90={p90:.6f}"
        )


def compute_zone_probabilities(
    paths: np.ndarray,
    zone_low: float,
    zone_high: float,
    p10_floor: float,
    p90_ceiling: float,
) -> tuple[float, float, float]:
    """Compute path-based probabilities for entering/touching forecast zones."""
    path_slice = paths[:, 1:] if paths.shape[1] > 1 else paths
    enter_zone = ((path_slice >= zone_low) & (path_slice <= zone_high)).any(axis=1)
    touch_p10 = (path_slice <= p10_floor).any(axis=1)
    touch_p90 = (path_slice >= p90_ceiling).any(axis=1)
    return float(enter_zone.mean()), float(touch_p10.mean()), float(touch_p90.mean())


def write_zone_probabilities(
    conn,
    as_of_date: datetime,
    horizon: int,
    prob_enter_zone: float,
    prob_touch_p10: float,
    prob_touch_p90: float,
    mc_runs: int,
):
    """Write Monte Carlo zone probabilities back to forecasts.production_1d."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE forecasts.production_1d
            SET
                prob_enter_zone = %s,
                prob_touch_p10 = %s,
                prob_touch_p90 = %s,
                mc_runs = %s
            WHERE horizon = %s
              AND as_of_date = %s
            """,
            (
                prob_enter_zone,
                prob_touch_p10,
                prob_touch_p90,
                mc_runs,
                horizon,
                as_of_date,
            ),
        )
    # No commit here — caller owns the transaction boundary


def run_monte_carlo(
    horizon: int, dry_run: bool = False, use_garch: bool = True
) -> list[RiskMetrics]:
    """Run Monte Carlo simulation for a given horizon (L5-A).

    Transaction safety: ALL writes for a horizon are committed atomically.
    Model labeling: Tracks which simulation model actually ran (GARCH vs asymmetric).

    Args:
        horizon: Forecast horizon in days
        dry_run: If True, validate without running
        use_garch: If True, use GARCH volatility (recommended). Falls back to asymmetric if fails.
    """
    logger.info("=" * 60)
    logger.info(f"L5-A MONTE CARLO SIMULATION @ {horizon}d")
    logger.info("=" * 60)
    logger.info(f"  N_SIMULATIONS: {N_SIMULATIONS:,}")
    logger.info(f"  GARCH volatility: {'ENABLED' if use_garch else 'DISABLED'}")
    logger.info("  Asymmetric diffusion: ENABLED")
    logger.info("  Regime adjustment: ENABLED")

    # Local RNG — reproducible regardless of call order or thread context
    rng = np.random.default_rng(RANDOM_SEED)

    conn = get_postgres_connection()

    try:
        # Load production forecast predictions (includes staleness guard)
        predictions_df = load_production_predictions(conn, horizon)

        if predictions_df is None:
            if dry_run:
                logger.info(
                    "[DRY RUN] No upstream production predictions available yet"
                )
                return []
            raise ValueError(f"No production predictions found for horizon={horizon}")

        # Load current regime
        regime = load_current_regime(conn)
        logger.info(
            f"  Current regime: {regime} (multiplier: {REGIME_MULTIPLIERS.get(regime, 1.0)})"
        )

        # Load historical returns for GARCH (if enabled)
        historical_returns = None
        if use_garch:
            historical_returns = load_historical_returns(conn, lookback_days=500)
            if historical_returns is None:
                logger.warning(
                    "  Insufficient historical data, falling back to asymmetric diffusion"
                )
                use_garch = False

        all_metrics = []
        # actual_model tracks what REALLY ran (not what was requested)
        actual_model = "asym"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for idx, row in predictions_df.iterrows():
            as_of_date = row["as_of_date"]
            p10, p50, p90 = float(row["p10"]), float(row["p50"]), float(row["p90"])
            current_price = float(row["current_price"])
            zone_low, zone_high = float(row["p30"]), float(row["p70"])

            # Quantile crossing guard — reject nonsensical inputs
            validate_quantile_ordering(p10, p50, p90, as_of_date)

            # L5-A: Path simulation with honest fallback
            if use_garch and idx == 0:  # Only fit GARCH once for latest prediction
                try:
                    paths = simulate_paths_garch(
                        p10=p10,
                        p50=p50,
                        p90=p90,
                        start_price=current_price,
                        horizon=horizon,
                        historical_returns=historical_returns,
                        rng=rng,
                        vol_regime=regime,
                        n_sims=N_SIMULATIONS,
                    )
                    actual_model = "garch"
                except Exception as e:
                    logger.warning(f"  GARCH failed, falling back to asymmetric: {e}")
                    paths = simulate_paths_asymmetric(
                        p10=p10,
                        p50=p50,
                        p90=p90,
                        start_price=current_price,
                        horizon=horizon,
                        rng=rng,
                        vol_regime=regime,
                        n_sims=N_SIMULATIONS,
                    )
                    actual_model = "asym_fallback"
            else:
                paths = simulate_paths_asymmetric(
                    p10=p10,
                    p50=p50,
                    p90=p90,
                    start_price=current_price,
                    horizon=horizon,
                    rng=rng,
                    vol_regime=regime,
                    n_sims=N_SIMULATIONS,
                )

            # Compute terminal returns for risk metrics
            terminal_returns = (paths[:, -1] - paths[:, 0]) / paths[:, 0]

            # Calculate risk metrics
            metrics = calculate_risk_metrics(terminal_returns, as_of_date, horizon)
            all_metrics.append(metrics)

            # Compute path percentiles for visualization (only for latest)
            if idx == 0:
                # Model version reflects what ACTUALLY ran
                model_version = f"mc_l5a_{horizon}d_{actual_model}_{timestamp}"

                path_percentiles = compute_path_percentiles(paths)
                prob_enter_zone, prob_touch_p10, prob_touch_p90 = (
                    compute_zone_probabilities(
                        paths=paths,
                        zone_low=zone_low,
                        zone_high=zone_high,
                        p10_floor=p10,
                        p90_ceiling=p90,
                    )
                )

                if not dry_run:
                    save_path_percentiles(
                        conn, as_of_date, horizon, path_percentiles, model_version
                    )
                    save_monte_carlo_run(
                        conn,
                        as_of_date,
                        horizon,
                        path_percentiles,
                        N_SIMULATIONS,
                        model_version,
                    )
                    write_zone_probabilities(
                        conn=conn,
                        as_of_date=as_of_date,
                        horizon=horizon,
                        prob_enter_zone=prob_enter_zone,
                        prob_touch_p10=prob_touch_p10,
                        prob_touch_p90=prob_touch_p90,
                        mc_runs=N_SIMULATIONS,
                    )
                logger.info(
                    "  Zone probs: enter_zone=%.1f%% touch_p10=%.1f%% touch_p90=%.1f%%",
                    prob_enter_zone * 100,
                    prob_touch_p10 * 100,
                    prob_touch_p90 * 100,
                )

        # Log summary
        latest_metrics = all_metrics[0]
        logger.info(f"\n{'=' * 40}")
        logger.info(f"LATEST RISK METRICS ({latest_metrics.as_of_date.date()})")
        logger.info(f"{'=' * 40}")
        logger.info(f"  Model used: {actual_model}")
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

        # Save risk metrics
        saved = save_risk_metrics(conn, all_metrics)

        # SINGLE COMMIT — all writes for this horizon are atomic
        conn.commit()
        logger.info(f"\n  Committed {saved:,} risk metrics + path data atomically")

        logger.info(f"\n{'=' * 60}")
        logger.info(f"L5-A MONTE CARLO COMPLETE @ {horizon}d (model={actual_model})")
        logger.info(f"{'=' * 60}")

        return all_metrics

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Run Monte Carlo risk simulation")
    parser.add_argument(
        "--horizon",
        type=str,
        required=True,
        help="Horizon in days (5, 21, 63, 126) or 'all'",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")

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
