"""
Grafana Model Registry - Live Training Integration
===================================================
Writes training runs, model metrics, and OOF predictions to Prisma Postgres
for Grafana dashboard visualization.

Usage:
    from fusion.grafana_registry import GrafanaRegistry

    registry = GrafanaRegistry()

    # Start a training run
    run_id = registry.start_training_run(
        model_type="specialist",
        model_name="crush",
        horizon=21,
        training_mode="full"
    )

    # Update with results
    registry.complete_training_run(
        run_id=run_id,
        status="completed",
        mase=0.85,
        best_model="DirectTabular",
        training_time_seconds=1234.5,
        oof_predictions=df_oof  # Optional DataFrame with p10, p50, p90
    )
"""

import os
import uuid
from datetime import datetime
from typing import Optional, Literal
from dataclasses import dataclass

import psycopg2
import psycopg2.extras
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TrainingMetrics:
    """Metrics from a training run."""
    mase: Optional[float] = None
    rmse: Optional[float] = None
    mae: Optional[float] = None
    mape: Optional[float] = None
    pinball_loss_p10: Optional[float] = None
    pinball_loss_p50: Optional[float] = None
    pinball_loss_p90: Optional[float] = None
    coverage_80: Optional[float] = None
    best_model: Optional[str] = None
    models_trained: Optional[int] = None


class GrafanaRegistry:
    """
    Writes training metadata to Prisma Postgres for Grafana dashboards.

    Tables populated:
    - model.training_runs: Live training progress
    - model.model_registry: Model metadata and metrics
    - model.oof_predictions: Out-of-fold predictions for accuracy tracking
    """

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL not found in environment")

    def _get_conn(self):
        return psycopg2.connect(self.database_url)

    def start_training_run(
        self,
        model_type: Literal["core", "specialist", "meta"],
        specialist_name: str,
        horizon: int,
        training_mode: str = "full",
        experiment_name: Optional[str] = None
    ) -> str:
        """
        Register start of a training run. Returns run_id for tracking.

        Args:
            model_type: 'core', 'specialist', or 'meta'
            specialist_name: e.g., 'crush', 'trump_effect', 'core'
            horizon: Forecast horizon in days (5, 21, 63, 126)
            training_mode: 'quick', 'medium', 'full', 'best'
            experiment_name: Optional experiment grouping

        Returns:
            run_id: UUID for this training run
        """
        run_id = str(uuid.uuid4())
        run_name = f"{model_type}-{specialist_name}-h{horizon}d-{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        conn = self._get_conn()
        cur = conn.cursor()

        try:
            cur.execute('''
                INSERT INTO model.training_runs
                (run_id, run_name, model_type, specialist_name, horizon,
                 training_mode, status, started_at, experiment_name)
                VALUES (%s, %s, %s, %s, %s, %s, 'running', NOW(), %s)
            ''', (run_id, run_name, model_type, specialist_name, horizon, training_mode, experiment_name))

            conn.commit()
            print(f"[Grafana] Training run started: {run_name}")
            return run_id

        finally:
            conn.close()

    def update_training_progress(
        self,
        run_id: str,
        current_model: Optional[str] = None,
        models_completed: Optional[int] = None,
        total_models: Optional[int] = None
    ):
        """Update progress of a running training job."""
        conn = self._get_conn()
        cur = conn.cursor()

        try:
            updates = []
            params = []

            if current_model:
                updates.append("current_model = %s")
                params.append(current_model)
            if models_completed is not None:
                updates.append("models_completed = %s")
                params.append(models_completed)
            if total_models is not None:
                updates.append("total_models = %s")
                params.append(total_models)

            if updates:
                params.append(run_id)
                cur.execute(f'''
                    UPDATE model.training_runs
                    SET {", ".join(updates)}
                    WHERE run_id = %s
                ''', params)
                conn.commit()

        finally:
            conn.close()

    def complete_training_run(
        self,
        run_id: str,
        status: Literal["completed", "failed", "cancelled"] = "completed",
        metrics: Optional[TrainingMetrics] = None,
        artifact_path: Optional[str] = None,
        oof_predictions: Optional[pd.DataFrame] = None,
        error_message: Optional[str] = None
    ):
        """
        Complete a training run and update model registry.

        Args:
            run_id: UUID from start_training_run
            status: Final status
            metrics: TrainingMetrics dataclass with MASE, etc.
            artifact_path: Path to saved model artifacts
            oof_predictions: DataFrame with columns [as_of_date, p10, p50, p90]
            error_message: Error details if failed
        """
        conn = self._get_conn()
        cur = conn.cursor()

        try:
            # Get run info
            cur.execute('''
                SELECT model_type, specialist_name, horizon, started_at
                FROM model.training_runs
                WHERE run_id = %s
            ''', (run_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Run {run_id} not found")

            model_type, specialist_name, horizon, started_at = row

            # Calculate duration (handle timezone-aware datetimes)
            if started_at:
                now = datetime.now(started_at.tzinfo) if started_at.tzinfo else datetime.now()
                duration = (now - started_at).total_seconds()
            else:
                duration = None

            # Update training_runs (best_model goes in metrics jsonb)
            metrics_json = None
            if metrics:
                metrics_json = {
                    'best_model': metrics.best_model,
                    'models_trained': metrics.models_trained,
                    'rmse': metrics.rmse,
                    'mae': metrics.mae,
                    'mape': metrics.mape,
                    'coverage_80': metrics.coverage_80,
                }
                # Remove None values
                metrics_json = {k: v for k, v in metrics_json.items() if v is not None}

            cur.execute('''
                UPDATE model.training_runs
                SET status = %s,
                    completed_at = NOW(),
                    duration_seconds = %s,
                    mase = %s,
                    metrics = %s,
                    error_message = %s
                WHERE run_id = %s
            ''', (
                status,
                duration,
                metrics.mase if metrics else None,
                psycopg2.extras.Json(metrics_json) if metrics_json else None,
                error_message,
                run_id
            ))

            # Update model_registry if successful
            if status == "completed" and metrics:
                # Try both model_id patterns (with and without horizon suffix)
                model_id_with_horizon = f"zinc-fusion-specialist-{specialist_name}-h{horizon}d"
                model_id_without_horizon = f"zinc-fusion-specialist-{specialist_name}"
                if model_type != "specialist":
                    model_id_with_horizon = f"zinc-fusion-{model_type}-{specialist_name}-h{horizon}d"
                    model_id_without_horizon = f"zinc-fusion-{model_type}-{specialist_name}"

                # Check which pattern exists
                cur.execute('SELECT model_id FROM model.model_registry WHERE model_id = %s', (model_id_with_horizon,))
                if cur.fetchone():
                    model_id = model_id_with_horizon
                else:
                    cur.execute('SELECT model_id FROM model.model_registry WHERE model_id = %s AND horizon = %s',
                               (model_id_without_horizon, horizon))
                    if cur.fetchone():
                        model_id = model_id_without_horizon
                    else:
                        # Neither exists, use with-horizon pattern (will be an insert candidate)
                        model_id = model_id_with_horizon

                cur.execute('''
                    UPDATE model.model_registry
                    SET trained_at = NOW(),
                        training_time_seconds = %s,
                        mase = %s,
                        rmse = %s,
                        mae = %s,
                        mape = %s,
                        pinball_loss_p10 = %s,
                        pinball_loss_p50 = %s,
                        pinball_loss_p90 = %s,
                        coverage_80 = %s,
                        best_model = %s,
                        models_trained = %s,
                        status = 'production',
                        artifact_path = %s,
                        updated_at = NOW()
                    WHERE model_id = %s
                ''', (
                    duration,
                    metrics.mase,
                    metrics.rmse,
                    metrics.mae,
                    metrics.mape,
                    metrics.pinball_loss_p10,
                    metrics.pinball_loss_p50,
                    metrics.pinball_loss_p90,
                    metrics.coverage_80,
                    metrics.best_model,
                    metrics.models_trained,
                    artifact_path,
                    model_id
                ))

                # Insert OOF predictions if provided
                if oof_predictions is not None and len(oof_predictions) > 0:
                    self._insert_oof_predictions(
                        cur, specialist_name, horizon, oof_predictions, run_id
                    )

            conn.commit()
            print(f"[Grafana] Training run {status}: {specialist_name} h{horizon}d")

        finally:
            conn.close()

    def _insert_oof_predictions(
        self,
        cur,
        specialist: str,
        horizon: int,
        df: pd.DataFrame,
        run_id: str
    ):
        """Insert OOF predictions for accuracy tracking."""
        required_cols = {'as_of_date', 'p10', 'p50', 'p90'}
        if not required_cols.issubset(df.columns):
            print(f"[Grafana] Warning: OOF DataFrame missing columns {required_cols - set(df.columns)}")
            return

        for _, row in df.iterrows():
            cur.execute('''
                INSERT INTO model.oof_predictions
                (specialist, horizon, as_of_date, pred_p10, pred_p50, pred_p90, run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (specialist, horizon, as_of_date)
                DO UPDATE SET pred_p10 = EXCLUDED.pred_p10,
                              pred_p50 = EXCLUDED.pred_p50,
                              pred_p90 = EXCLUDED.pred_p90,
                              run_id = EXCLUDED.run_id
            ''', (
                specialist, horizon,
                row['as_of_date'],
                row['p10'], row['p50'], row['p90'],
                run_id
            ))

    def promote_to_champion(self, model_id: str):
        """Promote a model to champion status for its horizon."""
        conn = self._get_conn()
        cur = conn.cursor()

        try:
            # Get horizon for this model
            cur.execute('SELECT horizon FROM model.model_registry WHERE model_id = %s', (model_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Model {model_id} not found")
            horizon = row[0]

            # Demote current champion at this horizon
            cur.execute('''
                UPDATE model.model_registry
                SET is_champion = FALSE
                WHERE horizon = %s AND is_champion = TRUE
            ''', (horizon,))

            # Promote new champion
            cur.execute('''
                UPDATE model.model_registry
                SET is_champion = TRUE, promoted_at = NOW()
                WHERE model_id = %s
            ''', (model_id,))

            conn.commit()
            print(f"[Grafana] Promoted {model_id} to champion for h{horizon}d")

        finally:
            conn.close()

    def refresh_data_quality(self):
        """Refresh data_quality_metrics from raw tables."""
        from datetime import date

        sources = [
            ('Market Futures (1D)', 'raw.market_futures_1d', 'as_of_date'),
            ('FRED Economic', 'raw.fred_observations_1d', 'as_of_date'),
            ('FX Spot', 'raw.fx_spot_1d', 'as_of_date'),
            ('CFTC COT', 'raw.cftc_cot_1w', 'report_date'),
            ('Weather NOAA', 'raw.weather_noaa_1d', 'as_of_date'),
            ('EPA RIN', 'raw.epa_rin_prices_1d', 'as_of_date'),
            ('USDA Exports', 'raw.usda_export_sales_1w', 'report_date'),
            ('USDA WASDE', 'raw.usda_wasde_1m', 'report_date'),
            ('News Articles', 'raw.news_articles_1d', 'published_at'),
        ]

        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now()
        today = date.today()

        try:
            for source_name, table, date_col in sources:
                try:
                    cur.execute(f'SELECT COUNT(*), MAX({date_col}) FROM {table}')
                    count, latest = cur.fetchone()

                    if latest:
                        if isinstance(latest, date) and not isinstance(latest, datetime):
                            hours = (today - latest).days * 24
                            latest_ts = datetime.combine(latest, datetime.min.time())
                        else:
                            hours = (now - latest.replace(tzinfo=None)).total_seconds() / 3600 if latest else 999
                            latest_ts = latest
                        is_stale = hours > 48
                    else:
                        hours, is_stale, latest_ts = 999, True, None

                    cur.execute('''
                        UPDATE model.data_quality_metrics
                        SET total_rows = %s, last_update = %s,
                            hours_since_update = %s, is_stale = %s, as_of_date = CURRENT_DATE
                        WHERE source = %s
                    ''', (count, latest_ts, hours, is_stale, source_name))

                except Exception as e:
                    print(f"[Grafana] Error refreshing {source_name}: {e}")
                    conn.rollback()

            conn.commit()
            print("[Grafana] Data quality metrics refreshed")

        finally:
            conn.close()


# Convenience functions for training scripts
def register_training_start(model_type: str, specialist_name: str, horizon: int, **kwargs) -> str:
    """Quick helper to start tracking a training run."""
    return GrafanaRegistry().start_training_run(model_type, specialist_name, horizon, **kwargs)


def register_training_complete(run_id: str, mase: float, best_model: str, **kwargs):
    """Quick helper to complete a training run."""
    metrics = TrainingMetrics(mase=mase, best_model=best_model, **kwargs)
    GrafanaRegistry().complete_training_run(run_id, status="completed", metrics=metrics)


def register_training_failed(run_id: str, error_message: str):
    """Quick helper to mark a training run as failed."""
    GrafanaRegistry().complete_training_run(run_id, status="failed", error_message=error_message)
