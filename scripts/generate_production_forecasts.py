"""
Generate Production Forecasts from OOF Predictions
==================================================

Reads latest OOF predicted_price from training.oof_core_1d (core = price predictor),
then calibrates probability ranges (p10/p30/p70/p90) from historical OOF residuals.
Upserts results into forecasts.production_1d.

Core outputs a single predicted_price per horizon. ALL quantile ranges in the
production table come from L2/L3 residual calibration — not from core.
"""

import logging
import sys
from datetime import date

import pandas as pd

# Ensure project root is on path for imports
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fusion.db.connection import DatabaseConnections

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

HORIZONS = [5, 21, 63, 126]
SYMBOL = "ZL"

# OOF freshness SLAs: maximum business-day lag allowed per horizon.
# Gates on trained_at (model-run recency), NOT trade_date which is naturally
# horizon-lagged due to shift(-horizon) target construction in build_matrix.py.
OOF_FRESHNESS_SLA: dict[int, int] = {
    5: 3,  # 5d horizon: max 3 business days since last training run
    21: 5,  # 21d horizon: max 5 business days
    63: 10,  # 63d horizon: max 10 business days
    126: 15,  # 126d horizon: max 15 business days
}


def get_latest_zl_close(engine) -> tuple:
    """Get the most recent ZL close price and its date.

    Returns:
        Tuple of (close_price, event_date) or (None, None) if no data.
    """
    query = """
        SELECT close, event_date
        FROM mkt.futures_1d
        WHERE symbol = 'ZL' AND close IS NOT NULL
        ORDER BY event_date DESC
        LIMIT 1
    """
    df = pd.read_sql(query, engine)
    if len(df) == 0:
        return None, None
    return float(df.iloc[0]["close"]), df.iloc[0]["event_date"]


def get_latest_oof_by_horizon(engine, horizon: int) -> pd.DataFrame:
    """Get the most recent OOF predicted_price for a given horizon.

    Core outputs a single predicted_price (point forecast). We average across
    CV windows to get the ensemble prediction for the latest trade_date.

    Returns:
        DataFrame with columns: trade_date, predicted_price, run_hash
    """
    query = """
        SELECT
            trade_date,
            AVG(predicted_price) as predicted_price,
            MAX(run_hash) as run_hash,
            MAX(run_id::text) as run_id
        FROM training.oof_core_1d
        WHERE horizon_days = %s
          AND symbol = %s
          AND trade_date = (
              SELECT MAX(trade_date)
              FROM training.oof_core_1d
              WHERE horizon_days = %s AND symbol = %s
          )
        GROUP BY trade_date
    """
    return pd.read_sql(query, engine, params=(horizon, SYMBOL, horizon, SYMBOL))


def check_oof_freshness(
    engine,
    horizon: int,
    as_of_date: date | None = None,
) -> tuple[bool, int, str]:
    """
    Check if OOF predictions are fresh enough for production forecasts.

    Gates on trained_at (when the model was actually run), NOT trade_date
    which is naturally horizon-lagged by shift(-horizon) in build_matrix.py.
    Uses business-day counting to avoid penalizing weekends/holidays.

    Returns:
        (passed, staleness_bdays, message)
    """
    if as_of_date is None:
        as_of_date = date.today()

    max_lag_bdays = OOF_FRESHNESS_SLA.get(horizon, 5)

    query = """
        SELECT MAX(trained_at) as max_trained_at
        FROM training.oof_core_1d
        WHERE horizon_days = %s AND symbol = %s
    """
    df = pd.read_sql(query, engine, params=(horizon, SYMBOL))

    if df.empty or pd.isna(df.iloc[0]["max_trained_at"]):
        return False, 999, f"{horizon}d: NO OOF data"

    max_trained = df.iloc[0]["max_trained_at"]
    if hasattr(max_trained, "date"):
        max_trained = max_trained.date()

    # Count business days between max_trained and as_of_date
    bday_range = pd.bdate_range(start=max_trained, end=as_of_date)
    staleness_bdays = max(0, len(bday_range) - 1)  # -1 because range is inclusive

    if staleness_bdays <= max_lag_bdays:
        return (
            True,
            staleness_bdays,
            f"{horizon}d: OK ({staleness_bdays} bdays since training, SLA={max_lag_bdays})",
        )
    else:
        return (
            False,
            staleness_bdays,
            f"{horizon}d: STALE ({staleness_bdays} bdays > SLA={max_lag_bdays})",
        )


def compute_residual_offsets(engine, horizon: int) -> dict[str, float]:
    """Compute calibration offsets from historical OOF residuals.

    Residuals = target_value - predicted_price. We take quantiles of the
    residual distribution to produce p10/p30/p70/p90 ranges around the
    core price prediction.

    Returns dict with keys: p10_off, p30_off, p70_off, p90_off
    """
    query = """
        SELECT target_value, predicted_price
        FROM training.oof_core_1d
        WHERE horizon_days = %s
          AND symbol = %s
          AND target_value IS NOT NULL
          AND predicted_price IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT 5000
    """
    df = pd.read_sql(query, engine, params=(horizon, SYMBOL))

    if len(df) < 30:
        logger.warning(
            f"  {horizon}d: insufficient OOF residuals ({len(df)}) for calibration"
        )
        return {"p10_off": 0.0, "p30_off": 0.0, "p70_off": 0.0, "p90_off": 0.0}

    residuals = (df["target_value"] - df["predicted_price"]).astype(float)
    return {
        "p10_off": float(residuals.quantile(0.10)),
        "p30_off": float(residuals.quantile(0.30)),
        "p70_off": float(residuals.quantile(0.70)),
        "p90_off": float(residuals.quantile(0.90)),
    }


def upsert_production_forecast(conn, horizon: int, row: dict) -> bool:
    """Upsert a single forecast row into the production table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forecasts.production_1d (
                horizon,
                as_of_date, forecast_date,
                p30, p50, p70,
                p10_cal, p90_cal,
                price_p30, price_p50, price_p70,
                price_p10_cal, price_p90_cal,
                current_price, model_version, run_id, created_at
            ) VALUES (
                %(horizon)s,
                %(as_of_date)s, %(forecast_date)s,
                %(p30)s, %(p50)s, %(p70)s,
                %(p10_cal)s, %(p90_cal)s,
                %(price_p30)s, %(price_p50)s, %(price_p70)s,
                %(price_p10_cal)s, %(price_p90_cal)s,
                %(current_price)s, %(model_version)s, %(run_id)s, NOW()
            )
            ON CONFLICT (horizon, as_of_date) DO UPDATE SET
                forecast_date = EXCLUDED.forecast_date,
                p30 = EXCLUDED.p30,
                p50 = EXCLUDED.p50,
                p70 = EXCLUDED.p70,
                p10_cal = EXCLUDED.p10_cal,
                p90_cal = EXCLUDED.p90_cal,
                price_p30 = EXCLUDED.price_p30,
                price_p50 = EXCLUDED.price_p50,
                price_p70 = EXCLUDED.price_p70,
                price_p10_cal = EXCLUDED.price_p10_cal,
                price_p90_cal = EXCLUDED.price_p90_cal,
                current_price = EXCLUDED.current_price,
                model_version = EXCLUDED.model_version,
                run_id = EXCLUDED.run_id,
                created_at = NOW()
            """,
            row,
        )

    return True


def _gate_oof_freshness(engine) -> bool:
    """Check OOF freshness for all horizons. Returns True if all pass."""
    logger.info("Checking OOF prediction freshness...")
    stale_horizons = []
    for horizon in HORIZONS:
        passed, staleness, msg = check_oof_freshness(engine, horizon)
        if passed:
            logger.info(f"  OOF freshness: {msg}")
        else:
            logger.error(f"  OOF freshness: {msg}")
            stale_horizons.append(horizon)

    if stale_horizons:
        logger.error(
            f"OOF FRESHNESS GATE FAILED: horizons {stale_horizons} exceed SLA. "
            f"Re-train core models before generating production forecasts."
        )
        return False

    logger.info("OOF freshness gate PASSED for all horizons")
    return True


def generate_forecasts():
    """Main entry point: generate production forecasts from OOF predictions.

    Core outputs a single predicted_price. This script calibrates probability
    ranges (p10/p30/p70/p90) from historical OOF residuals and writes
    everything to forecasts.production_1d.
    """
    logger.info("=" * 60)
    logger.info("Generating production forecasts from OOF predictions")
    logger.info("=" * 60)

    with DatabaseConnections() as (engine, conn):
        # Step 1: Get current ZL price
        current_price, price_date = get_latest_zl_close(engine)
        if current_price is None:
            logger.error(
                "No ZL close price found in mkt.futures_1d — cannot generate forecasts"
            )
            return False

        logger.info(f"Current ZL close: {current_price:.4f} (as of {price_date})")

        # Step 1.5: OOF freshness gate (HARD GATE on trained_at recency)
        if not _gate_oof_freshness(engine):
            return False

        # Step 2: Process each horizon
        total_written = 0
        for horizon in HORIZONS:
            df_oof = get_latest_oof_by_horizon(engine, horizon)

            if len(df_oof) == 0:
                logger.warning(f"  {horizon}d: No OOF predictions found — skipping")
                continue

            row = df_oof.iloc[0]
            as_of_date = row["trade_date"]
            predicted_price = float(row["predicted_price"])

            # Calibrate ALL quantile ranges from historical residuals
            offsets = compute_residual_offsets(engine, horizon)
            p30 = predicted_price + offsets["p30_off"]
            p70 = predicted_price + offsets["p70_off"]
            p10_cal = predicted_price + offsets["p10_off"]
            p90_cal = predicted_price + offsets["p90_off"]

            run_hash = row["run_hash"]
            run_id = row.get("run_id")

            # All values are already ZL futures prices — no conversion needed
            forecast_date = pd.Timestamp(as_of_date) + pd.tseries.offsets.BDay(horizon)

            forecast_row = {
                "horizon": horizon,
                "as_of_date": as_of_date,
                "forecast_date": forecast_date.date(),
                "p30": round(p30, 4),
                "p50": round(predicted_price, 4),
                "p70": round(p70, 4),
                "p10_cal": round(p10_cal, 4),
                "p90_cal": round(p90_cal, 4),
                "price_p30": round(p30, 4),
                "price_p50": round(predicted_price, 4),
                "price_p70": round(p70, 4),
                "price_p10_cal": round(p10_cal, 4),
                "price_p90_cal": round(p90_cal, 4),
                "current_price": current_price,
                "model_version": run_hash,
                "run_id": run_id,
            }

            upsert_production_forecast(conn, horizon, forecast_row)
            total_written += 1

            logger.info(
                f"  {horizon:>3}d: as_of={as_of_date} | "
                f"predicted={predicted_price:.2f} | "
                f"p30={p30:.2f} p70={p70:.2f} | "
                f"p10={p10_cal:.2f} p90={p90_cal:.2f}"
            )

        # Commit all writes
        conn.commit()
        logger.info(f"Wrote {total_written} / {len(HORIZONS)} horizon forecasts")

        if total_written == 0:
            logger.error("No forecasts written — OOF table may be empty")
            return False

        return True


if __name__ == "__main__":
    success = generate_forecasts()
    sys.exit(0 if success else 1)
