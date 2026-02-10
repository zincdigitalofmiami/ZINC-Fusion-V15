#!/usr/bin/env python3
"""
Generate dashboard metrics, accuracy, and SHAP summaries.
"""

import os
import argparse
from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

HORIZONS = [5, 21, 63, 126]


def get_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not found")
    return psycopg2.connect(db_url)


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
        coverage = float(np.mean((df["target"] >= df["p50"])))  # rough proxy
        # Sharpe on realized target returns (annualized)
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
        metrics[f"core_coverage_{horizon}d"] = coverage
    return metrics


def insert_shap_summary(conn, horizon: int, shap_rows: List[Dict]):
    if not shap_rows:
        return
    with conn.cursor() as cur:
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
            for r in shap_rows
        ]
        cur.execute("DELETE FROM model.shap_summary WHERE horizon = %s", (horizon,))
        execute_sql = """
            INSERT INTO model.shap_summary
            (horizon, feature_name, mean_abs_shap, std_shap, rank, model_version, trained_at)
            VALUES %s
        """
        from psycopg2.extras import execute_values

        execute_values(cur, execute_sql, values)
    conn.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Generate dashboard metrics + SHAP summary"
    )
    parser.parse_args()

    conn = get_connection()
    try:
        metrics = compute_core_accuracy(conn)
        upsert_dashboard_metrics(conn, metrics)
        print(f"Wrote {len(metrics)} dashboard metrics")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
