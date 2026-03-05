#!/usr/bin/env python3
"""
Backfill training.model_runs_event from training.oof_core_1d.

Purpose:
- Populate MAE/pinball/coverage provenance rows required by forecast-target APIs.
- Mark rows as promoted/success without retraining.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

HORIZONS = [5, 21, 63, 126]


@dataclass
class BackfillMetrics:
    horizon_days: int
    run_hash: str
    trained_date: str
    mae: float
    coverage_30_70: float
    pinball_p10: float
    pinball_p50: float
    pinball_p90: float
    oof_count: int


def fail(msg: str) -> None:
    print(f"[backfill-model-runs] BLOCKED: {msg}")
    raise SystemExit(1)


def resolve_db_url(explicit: str | None) -> str:
    url = explicit or os.getenv("DIRECT_DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    if not url:
        fail("No DB URL found. Set DIRECT_DATABASE_URL or POSTGRES_URL or DATABASE_URL.")
    if not (url.startswith("postgres://") or url.startswith("postgresql://")):
        fail("DB URL must be postgres:// or postgresql://")
    if "gssencmode" not in url:
        url += "&gssencmode=disable" if "?" in url else "?gssencmode=disable"
    return url


def pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, q: float) -> float:
    e = y_true - y_pred
    return float(np.mean(np.maximum(q * e, (q - 1.0) * e)))


def load_latest_run_hash(conn, horizon: int) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_hash
            FROM training.oof_core_1d
            WHERE horizon_days = %s
              AND run_hash IS NOT NULL
            ORDER BY trade_date DESC, trained_at DESC
            LIMIT 1
            """,
            (horizon,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def compute_metrics(conn, horizon: int, run_hash: str) -> BackfillMetrics:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              trade_date::text,
              predicted_price::float8,
              target_value::float8
            FROM training.oof_core_1d
            WHERE horizon_days = %s
              AND run_hash = %s
              AND predicted_price IS NOT NULL
              AND target_value IS NOT NULL
            ORDER BY trade_date
            """,
            (horizon, run_hash),
        )
        rows = cur.fetchall()

    if len(rows) < 10:
        fail(f"Insufficient OOF rows for horizon={horizon}, run_hash={run_hash}: {len(rows)}")

    trade_dates = [str(r[0]) for r in rows]
    y_pred = np.array([float(r[1]) for r in rows], dtype=float)
    y_true = np.array([float(r[2]) for r in rows], dtype=float)
    residuals = y_true - y_pred

    mae = float(np.mean(np.abs(residuals)))
    p30_off = float(np.quantile(residuals, 0.30))
    p70_off = float(np.quantile(residuals, 0.70))
    p30 = y_pred + p30_off
    p70 = y_pred + p70_off
    coverage = float(np.mean((y_true >= p30) & (y_true <= p70)))

    return BackfillMetrics(
        horizon_days=horizon,
        run_hash=run_hash,
        trained_date=max(trade_dates),
        mae=mae,
        coverage_30_70=coverage,
        pinball_p10=pinball_loss(y_true, y_pred, 0.10),
        pinball_p50=pinball_loss(y_true, y_pred, 0.50),
        pinball_p90=pinball_loss(y_true, y_pred, 0.90),
        oof_count=len(rows),
    )


def upsert_model_run(conn, m: BackfillMetrics, dry_run: bool) -> None:
    if dry_run:
        print(
            f"  DRY-RUN horizon={m.horizon_days} run_hash={m.run_hash} "
            f"mae={m.mae:.4f} coverage={m.coverage_30_70:.4f} count={m.oof_count}"
        )
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO training.model_runs_event
              (model_name, horizon_days, trained_date, run_hash,
               mae, coverage_30_70, pinball_p10, pinball_p50, pinball_p90,
               oof_count, status, outcome, model_path, notes, created_at)
            VALUES
              (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (run_hash, horizon_days) DO UPDATE SET
              mae = EXCLUDED.mae,
              coverage_30_70 = EXCLUDED.coverage_30_70,
              pinball_p10 = EXCLUDED.pinball_p10,
              pinball_p50 = EXCLUDED.pinball_p50,
              pinball_p90 = EXCLUDED.pinball_p90,
              oof_count = EXCLUDED.oof_count,
              status = EXCLUDED.status,
              outcome = EXCLUDED.outcome,
              model_path = EXCLUDED.model_path,
              notes = EXCLUDED.notes,
              trained_date = EXCLUDED.trained_date
            """,
            (
                "core_v2",
                m.horizon_days,
                m.trained_date,
                m.run_hash,
                m.mae,
                m.coverage_30_70,
                m.pinball_p10,
                m.pinball_p50,
                m.pinball_p90,
                m.oof_count,
                "promoted",
                "success",
                "backfill:oof_core_1d",
                f"backfilled at {datetime.now(timezone.utc).isoformat()} from oof_core_1d",
            ),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill model_runs_event from OOF data")
    parser.add_argument("--db-url", help="Override DB URL")
    parser.add_argument("--horizons", nargs="+", type=int, default=HORIZONS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    horizons = [h for h in args.horizons if h in HORIZONS]
    if not horizons:
        fail(f"No valid horizons requested. Allowed: {HORIZONS}")

    db_url = resolve_db_url(args.db_url)
    conn = psycopg2.connect(db_url)
    try:
        print("[backfill-model-runs] start")
        print(f"  horizons={horizons} dry_run={args.dry_run}")
        metrics_list: list[BackfillMetrics] = []

        for horizon in horizons:
            run_hash = load_latest_run_hash(conn, horizon)
            if not run_hash:
                fail(f"No run_hash found in training.oof_core_1d for horizon={horizon}")
            metrics = compute_metrics(conn, horizon, run_hash)
            metrics_list.append(metrics)
            upsert_model_run(conn, metrics, args.dry_run)

        if not args.dry_run:
            conn.commit()

        for m in metrics_list:
            print(
                f"  OK horizon={m.horizon_days} run_hash={m.run_hash} "
                f"mae={m.mae:.4f} coverage={m.coverage_30_70:.4f} count={m.oof_count}"
            )
        print("[backfill-model-runs] PASS")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"[backfill-model-runs] FAILED: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
