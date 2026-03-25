#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Standalone GARCH Volatility Producer

Fits GJR-GARCH to historical ZL returns and persists full volatility-path
artifacts into forecasts.garch_forecasts.  Monte Carlo (run_monte_carlo.py)
consumes these artifacts — it must NEVER fit GARCH itself.

Usage:
    python scripts/run_garch.py --horizon 5
    python scripts/run_garch.py --horizon all
    python scripts/run_garch.py --horizon all --history-limit 20
    python scripts/run_garch.py --horizon 63 --dry-run
"""

import argparse
import hashlib
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.fusion.forecasting.volatility import fit_garch, forecast_volatility

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
load_dotenv(".env.vercel")

HORIZONS = [5, 21, 63, 126]

REGIME_MULTIPLIERS = {
    "high": 1.5,
    "elevated": 1.25,
    "normal": 1.0,
    "low": 0.7,
    "suppressed": 0.5,
}


def get_postgres_connection():
    """Get PostgreSQL connection from environment."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("DATABASE_URL or POSTGRES_URL not found in environment")
    return psycopg2.connect(database_url)


def make_model_version(
    horizon: int,
    as_of_date: datetime,
    lookback_days: int,
    regime: str,
    source_start_date: datetime,
    source_end_date: datetime,
) -> str:
    """Deterministic model version string.

    Format: garch_gjr_<horizon>d_<YYYYMMDD>_<hash8>
    """
    date_str = as_of_date.strftime("%Y%m%d") if hasattr(as_of_date, "strftime") else str(as_of_date)[:10].replace("-", "")
    payload = f"ZL|{as_of_date}|{horizon}|gjr-garch|{lookback_days}|{regime}|{source_start_date}|{source_end_date}"
    hash8 = hashlib.sha256(payload.encode()).hexdigest()[:8]
    return f"garch_gjr_{horizon}d_{date_str}_{hash8}"


def load_production_rows(conn, horizon: int, history_limit: int) -> list[dict]:
    """Load production rows that need GARCH artifacts."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT as_of_date, horizon
            FROM forecasts.production_1d
            WHERE horizon = %s
              AND price_p50 IS NOT NULL
            ORDER BY as_of_date DESC
            LIMIT %s
            """,
            (horizon, history_limit),
        )
        rows = cur.fetchall()

    if not rows:
        return []

    return [{"as_of_date": r[0], "horizon": r[1]} for r in rows]


def load_zl_returns(conn, as_of_date: datetime, lookback_days: int) -> tuple[np.ndarray, datetime, datetime]:
    """Load ZL closes up to as_of_date, compute returns.

    Returns (returns_array, source_start_date, source_end_date).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_date, close
            FROM mkt.futures_1d
            WHERE symbol = 'ZL'
              AND event_date <= %s
            ORDER BY event_date DESC
            LIMIT %s
            """,
            (as_of_date, lookback_days + 1),
        )
        rows = cur.fetchall()

    if len(rows) < 100:
        raise ValueError(
            f"Only {len(rows)} ZL closes available (need >=100). "
            f"Cannot fit GARCH for as_of_date={as_of_date}"
        )

    df = pd.DataFrame(rows, columns=["event_date", "close"])
    df = df.sort_values("event_date")
    source_start_date = df["event_date"].iloc[0]
    source_end_date = df["event_date"].iloc[-1]

    returns = df["close"].pct_change().dropna().values
    return returns, source_start_date, source_end_date


def load_regime(conn, as_of_date: datetime) -> str:
    """Load volatility regime as of the given date."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT regime
            FROM analytics.vol_regimes
            WHERE as_of_date <= %s
            ORDER BY as_of_date DESC
            LIMIT 1
            """,
            (as_of_date,),
        )
        row = cur.fetchone()

    if row and row[0]:
        return row[0].lower()
    return "normal"


def run_garch_for_row(
    conn,
    as_of_date: datetime,
    horizon: int,
    lookback_days: int,
    dry_run: bool,
) -> dict:
    """Fit GARCH, apply regime, persist to forecasts.garch_forecasts.

    Returns summary dict of what was computed/written.
    """
    # 1. Load returns
    returns, source_start, source_end = load_zl_returns(conn, as_of_date, lookback_days)
    logger.info(f"  Loaded {len(returns)} daily returns ({source_start} → {source_end})")

    # 2. Load regime
    regime = load_regime(conn, as_of_date)
    regime_mult = REGIME_MULTIPLIERS.get(regime, 1.0)
    logger.info(f"  Regime: {regime} (multiplier: {regime_mult})")

    # 3. Fit GJR-GARCH
    garch_result = fit_garch(returns, model_type="gjr-garch")
    logger.info(
        f"  GARCH fitted: persistence={garch_result.persistence:.4f}, "
        f"gamma={garch_result.gamma}, unconditional_vol={garch_result.unconditional_vol:.4f}"
    )

    # 4. Forecast volatility path
    vol_forecast = forecast_volatility(garch_result, horizon=horizon)

    # 5. Compute asymmetry multipliers (same logic as garch_volatility_for_monte_carlo)
    if garch_result.gamma and garch_result.gamma > 0:
        downside_vol_mult = 1.0 + garch_result.gamma / 2
        upside_vol_mult = 1.0
    else:
        upside_vol_mult = 1.0
        downside_vol_mult = 1.0

    # Validate multipliers
    if not (np.isfinite(upside_vol_mult) and upside_vol_mult > 0):
        raise ValueError(f"upside_vol_mult is not finite positive: {upside_vol_mult}")
    if not (np.isfinite(downside_vol_mult) and downside_vol_mult > 0):
        raise ValueError(f"downside_vol_mult is not finite positive: {downside_vol_mult}")

    # 6. Apply regime multiplier to vol paths INSIDE run_garch (not in Monte Carlo)
    daily_vol_path = vol_forecast.daily_vol * regime_mult
    annualized_vol_path = vol_forecast.annualized_vol * regime_mult

    # Validate path length
    if len(daily_vol_path) != horizon:
        raise ValueError(
            f"daily_vol_path length {len(daily_vol_path)} != horizon {horizon}"
        )

    # 7. Compute summary stats from regime-adjusted paths
    conditional_vol = float(np.mean(daily_vol_path))
    annualized_vol = float(np.mean(annualized_vol_path))
    vol_lower = float(np.min(daily_vol_path))
    vol_upper = float(np.max(daily_vol_path))

    # 8. Model version
    model_version = make_model_version(
        horizon=horizon,
        as_of_date=as_of_date,
        lookback_days=lookback_days,
        regime=regime,
        source_start_date=source_start,
        source_end_date=source_end,
    )

    summary = {
        "as_of_date": as_of_date,
        "horizon": horizon,
        "conditional_vol": conditional_vol,
        "annualized_vol": annualized_vol,
        "vol_lower": vol_lower,
        "vol_upper": vol_upper,
        "daily_vol_path": daily_vol_path.tolist(),
        "annualized_vol_path": annualized_vol_path.tolist(),
        "upside_vol_mult": upside_vol_mult,
        "downside_vol_mult": downside_vol_mult,
        "persistence": float(garch_result.persistence),
        "gamma": float(garch_result.gamma) if garch_result.gamma else None,
        "lookback_days": lookback_days,
        "regime": regime,
        "regime_multiplier": regime_mult,
        "source_start_date": source_start,
        "source_end_date": source_end,
        "model_version": model_version,
    }

    logger.info(
        f"  conditional_vol={conditional_vol:.6f}  annualized_vol={annualized_vol:.4f}  "
        f"upside_mult={upside_vol_mult:.4f}  downside_mult={downside_vol_mult:.4f}"
    )
    logger.info(f"  model_version={model_version}")

    if dry_run:
        logger.info("  [DRY RUN] — would write to forecasts.garch_forecasts")
        return summary

    # 9. Persist — upsert on (symbol, as_of_date, horizon, model_version)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forecasts.garch_forecasts (
                symbol, as_of_date, horizon,
                conditional_vol, annualized_vol,
                vol_lower, vol_upper,
                model_type, model_version,
                daily_vol_path, annualized_vol_path,
                upside_vol_mult, downside_vol_mult,
                persistence, gamma, lookback_days,
                regime, regime_multiplier,
                source_start_date, source_end_date,
                created_at
            ) VALUES (
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                NOW()
            )
            ON CONFLICT (symbol, as_of_date, horizon, model_version)
            DO UPDATE SET
                conditional_vol     = EXCLUDED.conditional_vol,
                annualized_vol      = EXCLUDED.annualized_vol,
                vol_lower           = EXCLUDED.vol_lower,
                vol_upper           = EXCLUDED.vol_upper,
                daily_vol_path      = EXCLUDED.daily_vol_path,
                annualized_vol_path = EXCLUDED.annualized_vol_path,
                upside_vol_mult     = EXCLUDED.upside_vol_mult,
                downside_vol_mult   = EXCLUDED.downside_vol_mult,
                persistence         = EXCLUDED.persistence,
                gamma               = EXCLUDED.gamma,
                lookback_days       = EXCLUDED.lookback_days,
                regime              = EXCLUDED.regime,
                regime_multiplier   = EXCLUDED.regime_multiplier,
                source_start_date   = EXCLUDED.source_start_date,
                source_end_date     = EXCLUDED.source_end_date,
                created_at          = NOW()
            """,
            (
                "ZL", as_of_date, horizon,
                conditional_vol, annualized_vol,
                vol_lower, vol_upper,
                "gjr-garch", model_version,
                Json(daily_vol_path.tolist()), Json(annualized_vol_path.tolist()),
                upside_vol_mult, downside_vol_mult,
                float(garch_result.persistence),
                float(garch_result.gamma) if garch_result.gamma else None,
                lookback_days,
                regime, regime_mult,
                source_start, source_end,
            ),
        )

    return summary


def run_garch(horizon: int, history_limit: int, lookback_days: int, dry_run: bool):
    """Run standalone GARCH stage for one horizon."""
    logger.info("=" * 60)
    logger.info(f"GARCH PRODUCER @ {horizon}d  (history_limit={history_limit}, lookback={lookback_days})")
    logger.info("=" * 60)

    conn = get_postgres_connection()
    try:
        rows = load_production_rows(conn, horizon, history_limit)
        if not rows:
            logger.warning(f"  No production rows for horizon={horizon}. Nothing to do.")
            return

        logger.info(f"  Processing {len(rows)} production row(s)")

        for i, row in enumerate(rows):
            as_of_date = row["as_of_date"]
            logger.info(f"\n--- Row {i+1}/{len(rows)}: as_of_date={as_of_date}, horizon={horizon} ---")

            run_garch_for_row(
                conn=conn,
                as_of_date=as_of_date,
                horizon=horizon,
                lookback_days=lookback_days,
                dry_run=dry_run,
            )

        if not dry_run:
            conn.commit()
            logger.info(f"\n  Committed {len(rows)} GARCH artifact(s) for horizon={horizon}d")
        else:
            logger.info(f"\n  [DRY RUN] Would commit {len(rows)} GARCH artifact(s)")

    finally:
        conn.close()

    logger.info(f"GARCH PRODUCER COMPLETE @ {horizon}d")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Standalone GARCH volatility producer for Monte Carlo"
    )
    parser.add_argument(
        "--horizon",
        type=str,
        required=True,
        help="Horizon in days (5, 21, 63, 126) or 'all'",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=1,
        help="Number of most-recent production rows to process (default: 1)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=500,
        help="Number of historical trading days for GARCH fitting (default: 500)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and compute without persisting",
    )

    args = parser.parse_args()

    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        h = int(args.horizon)
        if h not in HORIZONS:
            logger.error(f"Invalid horizon: {h}. Must be one of {HORIZONS}")
            sys.exit(1)
        horizons = [h]

    for horizon in horizons:
        try:
            run_garch(horizon, args.history_limit, args.lookback_days, args.dry_run)
        except Exception as e:
            logger.error(f"GARCH failed @ {horizon}d: {e}")
            raise

    logger.info("\nALL GARCH STAGES COMPLETE")


if __name__ == "__main__":
    main()
