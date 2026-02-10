#!/usr/bin/env python3
# sqlref: ignore-file
"""
Auto-generate dashboard metrics + SHAP summaries after training completes.
"""

import os
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

HORIZONS = [5, 21, 63, 126]
SPECIALISTS = [
    "crush",
    "china",
    "fx",
    "fed",
    "tariff",
    "energy",
    "biofuel",
    "palm",
    "volatility",
    "substitutes",
    "trump_effect",
]


def get_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not found")
    return psycopg2.connect(db_url)


def oof_core_ready(conn, since: datetime) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT horizon_days, COUNT(*)
            FROM training.oof_core_1d
            WHERE trained_at >= %s
            GROUP BY horizon_days
            """,
            (since,),
        )
        rows = cur.fetchall()
    seen = {r[0] for r in rows if r[1] > 0}
    return all(h in seen for h in HORIZONS)


def oof_specialists_ready(conn, since: datetime) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'training'
              AND table_name LIKE 'oof_%_1d'
            """
        )
        tables = [r[0] for r in cur.fetchall()]
    for bucket in SPECIALISTS:
        table = f"oof_{bucket}_1d"
        if table not in tables:
            return False
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT horizon_days, COUNT(*)
                FROM training.{table}
                WHERE trained_at >= %s
                GROUP BY horizon_days
                """,
                (since,),
            )
            rows = cur.fetchall()
        seen = {r[0] for r in rows if r[1] > 0}
        if not all(h in seen for h in HORIZONS):
            return False
    return True


def upsert_dashboard_metrics(
    conn, metrics: Dict[str, float], as_of_date: datetime | None = None
):
    with conn.cursor() as cur:
        for name, value in metrics.items():
            cur.execute(
                """
                INSERT INTO analytics.dashboard_metrics (metric_name, metric_value, as_of_date)
                VALUES (%s, %s, %s)
                ON CONFLICT (metric_name, as_of_date)
                DO UPDATE SET metric_value = EXCLUDED.metric_value, updated_at = NOW()
                """,
                (name, value, as_of_date),
            )
    conn.commit()


def compute_core_accuracy(conn) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for horizon in HORIZONS:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p50, target_value
                FROM training.oof_core_1d
                WHERE horizon_days = %s
                  AND target_value IS NOT NULL
                """,
                (horizon,),
            )
            rows = cur.fetchall()
        if not rows:
            continue
        df = pd.DataFrame(rows, columns=["p50", "target"])
        eps = 1e-6
        mape = float(
            np.mean(np.abs((df["target"] - df["p50"]) / (df["target"].abs() + eps)))
        )
        mae = float(np.mean(np.abs(df["target"] - df["p50"])))
        directional = float(np.mean(np.sign(df["target"]) == np.sign(df["p50"])))
        mean_ret = df["target"].mean()
        std_ret = df["target"].std(ddof=1)
        sharpe = (
            float((mean_ret / std_ret) * np.sqrt(252 / horizon))
            if std_ret > 0
            else np.nan
        )
        metrics[f"core_mape_{horizon}d"] = mape
        metrics[f"core_mae_{horizon}d"] = mae
        metrics[f"core_directional_{horizon}d"] = directional
        metrics[f"core_sharpe_{horizon}d"] = sharpe
    return metrics


def write_shap_summary(conn, horizon: int, rows: List[Dict]):
    if not rows:
        return
    from psycopg2.extras import execute_values

    values = [
        (
            horizon,
            r["feature_name"],
            float(r["mean_abs_shap"]),
            float(r.get("std_shap") or 0.0),
            r.get("rank"),
            r.get("model_version"),
            r.get("trained_at"),
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM model.shap_summary WHERE horizon = %s", (horizon,)
        )  # sqlref: ignore
        execute_values(
            cur,
            """
            INSERT INTO model.shap_summary  -- sqlref: ignore
            (horizon, feature_name, mean_abs_shap, std_shap, rank, model_version, trained_at)
            VALUES %s
            """,
            values,
        )
    conn.commit()


def compute_shap_summary_for_horizon(horizon: int, run_label: str) -> List[Dict]:
    try:
        from autogluon.tabular import TabularPredictor
    except Exception:
        return []

    # Use one specialist model as proxy (crush) for SHAP summary
    model_dir = (
        PROJECT_ROOT
        / "models"
        / "specialists"
        / "crush"
        / f"horizon_{horizon}d"
        / f"run_{run_label}"
        / "window_4"
    )
    if not model_dir.exists():
        return []

    try:
        predictor = TabularPredictor.load(str(model_dir))
    except Exception:
        return []

    # Load recent data for SHAP calculation
    conn = get_connection()
    try:
        df = pd.read_sql(
            f"""
            SELECT *
            FROM training.matrix_1d
            WHERE symbol = 'ZL'
              AND trade_date >= %s
            ORDER BY trade_date DESC
            LIMIT 500
            """,
            conn,
            params=("2020-01-01" if horizon in [5, 21] else "2000-01-01",),
        )
    finally:
        conn.close()

    drop_cols = {"symbol", "matrix_version", "created_at"} | {
        f"target_ret_{h}d" for h in HORIZONS
    }
    df = df.drop(columns=[c for c in df.columns if c in drop_cols], errors="ignore")
    df = df.rename(columns={"trade_date": "as_of_date"})
    df["target"] = (
        df[f"target_ret_{horizon}d"]
        if f"target_ret_{horizon}d" in df.columns
        else np.nan
    )
    df = df.dropna(subset=["target"])

    try:
        fi = predictor.feature_importance(df, method="shap")
        model_version = f"shap_crush_{run_label}"
    except Exception:
        fi = predictor.feature_importance(df)
        model_version = f"perm_crush_{run_label}"

    fi = fi.sort_values("importance", ascending=False).head(50)
    rows = []
    for rank, (feature, row) in enumerate(fi.iterrows(), start=1):
        rows.append(
            {
                "feature_name": feature,
                "mean_abs_shap": float(row["importance"]),
                "std_shap": float(row.get("stddev", 0.0)),
                "rank": rank,
                "model_version": model_version,
                "trained_at": datetime.now(timezone.utc),
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description="Autorun dashboard reports")
    parser.add_argument("--since", required=True, help="ISO timestamp to wait for")
    parser.add_argument("--poll-seconds", type=int, default=300)
    args = parser.parse_args()

    since = datetime.fromisoformat(args.since)
    print(f"[REPORTS] Waiting for core OOF since {since.isoformat()} ...")
    while True:
        conn = get_connection()
        try:
            if oof_core_ready(conn, since):
                break
        finally:
            conn.close()
        time.sleep(args.poll_seconds)

    conn = get_connection()
    try:
        metrics = compute_core_accuracy(conn)
        # Greedy/ensemble settings for dashboard visibility
        metrics["autogluon_core_num_val_windows"] = 4
        metrics["autogluon_core_time_limit_s"] = 3600
        metrics["autogluon_specialist_bag_folds"] = 10
        metrics["autogluon_specialist_stack_levels"] = 2
        upsert_dashboard_metrics(conn, metrics)
        print(f"[REPORTS] Wrote {len(metrics)} dashboard metrics")
    finally:
        conn.close()

    print(f"[REPORTS] Waiting for specialist OOF since {since.isoformat()} ...")
    while True:
        conn = get_connection()
        try:
            if oof_specialists_ready(conn, since):
                break
        finally:
            conn.close()
        time.sleep(args.poll_seconds)

    run_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for horizon in HORIZONS:
        rows = compute_shap_summary_for_horizon(horizon, run_label)
        conn = get_connection()
        try:
            write_shap_summary(conn, horizon, rows)
        finally:
            conn.close()
    print("[REPORTS] SHAP summary updated")


if __name__ == "__main__":
    main()
