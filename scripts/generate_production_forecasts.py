"""
Generate Production Forecasts from OOF Predictions
==================================================

Reads latest OOF predictions from training.oof_core_1d, converts return
quantiles to price levels, calibrates p10/p90 tails from realized OOF
residuals, and upserts into forecasts.production_1d.
"""

import logging
import sys

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
    """Get the most recent OOF predictions for a given horizon.

    For production forecasts, we want the latest trade_date's median
    prediction across all CV windows (ensemble by averaging windows).

    Returns:
        DataFrame with columns: trade_date, p30, p50, p70, run_hash
    """
    query = """
        SELECT
            trade_date,
            AVG(p30) as p30,
            AVG(p50) as p50,
            AVG(p70) as p70,
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


def compute_tail_offsets(engine, horizon: int) -> tuple[float, float]:
    """Compute p10/p90 residual offsets from historical OOF rows.

    Residuals are measured against the median forecast (target_value - p50).
    """
    query = """
        SELECT target_value, p50
        FROM training.oof_core_1d
        WHERE horizon_days = %s
          AND symbol = %s
          AND target_value IS NOT NULL
          AND p50 IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT 5000
    """
    df = pd.read_sql(query, engine, params=(horizon, SYMBOL))

    if len(df) < 30:
        logger.warning(
            f"  {horizon}d: insufficient OOF residuals ({len(df)}) for calibration"
        )
        return 0.0, 0.0

    residuals = (df["target_value"] - df["p50"]).astype(float)
    low_off = float(residuals.quantile(0.10))
    high_off = float(residuals.quantile(0.90))
    return low_off, high_off


def upsert_production_forecast(conn, horizon: int, row: dict) -> bool:
    """Upsert a single forecast row into the production table.

    Returns:
        True if inserted/updated, False if skipped.
    """
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


def generate_forecasts():
    """Main entry point: generate production forecasts from OOF predictions."""
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

        # Step 2: Process each horizon
        total_written = 0
        for horizon in HORIZONS:
            df_oof = get_latest_oof_by_horizon(engine, horizon)

            if len(df_oof) == 0:
                logger.warning(f"  {horizon}d: No OOF predictions found — skipping")
                continue

            row = df_oof.iloc[0]
            as_of_date = row["trade_date"]
            p30 = float(row["p30"])
            p50 = float(row["p50"])
            p70 = float(row["p70"])

            # Calibrate tails from empirical OOF residuals
            low_off, high_off = compute_tail_offsets(engine, horizon)
            p10_cal = p50 + low_off
            p90_cal = p50 + high_off

            # Fallback when calibration unavailable
            if low_off == 0.0 and high_off == 0.0:
                p10_cal = p30 - (p50 - p30)
                p90_cal = p70 + (p70 - p50)

            run_hash = row["run_hash"]
            run_id = row.get("run_id")

            # Convert return quantiles to price levels
            price_p30 = round(current_price * (1 + p30), 4)
            price_p50 = round(current_price * (1 + p50), 4)
            price_p70 = round(current_price * (1 + p70), 4)
            price_p10_cal = round(current_price * (1 + p10_cal), 4)
            price_p90_cal = round(current_price * (1 + p90_cal), 4)

            # Forecast date = as_of_date + horizon trading days (~1.4x calendar days)
            forecast_date = pd.Timestamp(as_of_date) + pd.tseries.offsets.BDay(horizon)

            forecast_row = {
                "horizon": horizon,
                "as_of_date": as_of_date,
                "forecast_date": forecast_date.date(),
                "p30": p30,
                "p50": p50,
                "p70": p70,
                "p10_cal": p10_cal,
                "p90_cal": p90_cal,
                "price_p30": price_p30,
                "price_p50": price_p50,
                "price_p70": price_p70,
                "price_p10_cal": price_p10_cal,
                "price_p90_cal": price_p90_cal,
                "current_price": current_price,
                "model_version": run_hash,
                "run_id": run_id,
            }

            upsert_production_forecast(conn, horizon, forecast_row)
            total_written += 1

            logger.info(
                f"  {horizon:>3}d: as_of={as_of_date} | "
                f"p30={price_p30:.2f} p50={price_p50:.2f} p70={price_p70:.2f} "
                f"p10={price_p10_cal:.2f} p90={price_p90_cal:.2f} | "
                f"return=[{p30:+.4f}, {p50:+.4f}, {p70:+.4f}] "
                f"cal=[{p10_cal:+.4f}, {p90_cal:+.4f}]"
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
