#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Quant ML Command Center
=========================================

Production MLflow infrastructure for quantitative commodity forecasting
with live metrics, dataset tracking, and automated chart generation.

Features:
- Live metrics streaming during training (step-by-step logging)
- Dataset lineage tracking (MLflow Datasets API)
- Automated chart generation (performance curves, leaderboards)
- Hierarchical experiment taxonomy
- Model Registry with @champion/@staging/@challenger aliases
- Model cards and governance artifacts

Experiment Taxonomy:
    zinc-fusion/
    ├── core/           # L0 Core baseline models
    │   ├── h5d         # 5-day horizon
    │   ├── h21d        # 21-day horizon
    │   ├── h63d        # 63-day horizon
    │   └── h126d       # 126-day horizon
    ├── specialist/     # L1 Domain specialists (10 models)
    ├── ensemble/       # L2 Fusion LASSO
    └── backtest/       # Historical validation

Usage:
    from scripts.mlflow_command_center import QuantMLCommandCenter

    cmd = QuantMLCommandCenter()

    # Start training with live metrics
    with cmd.training_run("core", horizon=5, mode="full") as tracker:
        # Log dataset
        tracker.log_dataset(train_df, "training")

        # Training with live metrics callback
        predictor = train_with_callback(tracker.metrics_callback)

        # Log results with charts
        tracker.log_model_complete(predictor, training_time=3600)
"""

import os
import io
import json
import shutil
import tempfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Callable
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging
import time

import numpy as np
import pandas as pd
import mlflow
import mlflow.data
from mlflow.tracking import MlflowClient
from mlflow.entities.model_registry import ModelVersion
from mlflow.exceptions import MlflowException
from mlflow.data.pandas_dataset import PandasDataset

# Chart generation
try:
    import matplotlib

    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    plt = None

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
LOCAL_MLRUNS = PROJECT_ROOT / "mlruns"
MODELS_DIR = PROJECT_ROOT / "models"
CHARTS_DIR = PROJECT_ROOT / "charts"

# Railway MLflow server
RAILWAY_MLFLOW_URI = "https://mlflow-tracking-production-1916.up.railway.app"
LOCAL_MLFLOW_URI = f"sqlite:///{LOCAL_MLRUNS / 'mlflow.db'}"

# Naming conventions
REGISTRY_PREFIX = "zinc-fusion"
QUANTILE_LEVELS = [0.1, 0.5, 0.9]
HORIZONS = [5, 21, 63, 126]


class ModelStage(str, Enum):
    """Model lifecycle stages."""

    NONE = "None"
    STAGING = "Staging"
    PRODUCTION = "Production"
    ARCHIVED = "Archived"


class ModelAlias(str, Enum):
    """Model deployment aliases."""

    CHAMPION = "champion"
    STAGING = "staging"
    CHALLENGER = "challenger"


# Hierarchical experiment taxonomy
EXPERIMENT_TAXONOMY = {
    # L0 Core models
    "core-h5d": f"{REGISTRY_PREFIX}/core/h5d",
    "core-h21d": f"{REGISTRY_PREFIX}/core/h21d",
    "core-h63d": f"{REGISTRY_PREFIX}/core/h63d",
    "core-h126d": f"{REGISTRY_PREFIX}/core/h126d",
    # L1 Specialists
    "specialist-china": f"{REGISTRY_PREFIX}/specialist/china-demand",
    "specialist-brazil": f"{REGISTRY_PREFIX}/specialist/brazil-weather",
    "specialist-argentina": f"{REGISTRY_PREFIX}/specialist/argentina-fx",
    "specialist-energy": f"{REGISTRY_PREFIX}/specialist/energy-complex",
    "specialist-crush": f"{REGISTRY_PREFIX}/specialist/crush-spread",
    "specialist-palm": f"{REGISTRY_PREFIX}/specialist/palm-substitute",
    "specialist-biofuel": f"{REGISTRY_PREFIX}/specialist/biofuel-mandate",
    "specialist-macro": f"{REGISTRY_PREFIX}/specialist/macro-rates",
    "specialist-positioning": f"{REGISTRY_PREFIX}/specialist/cot-positioning",
    "specialist-seasonality": f"{REGISTRY_PREFIX}/specialist/seasonality",
    # L2 Ensemble
    "ensemble": f"{REGISTRY_PREFIX}/ensemble/fusion-lasso",
    # Backtest
    "backtest": f"{REGISTRY_PREFIX}/backtest/validation",
}

REGISTERED_MODELS = {
    "core-h5d": f"{REGISTRY_PREFIX}-core-h5d",
    "core-h21d": f"{REGISTRY_PREFIX}-core-h21d",
    "core-h63d": f"{REGISTRY_PREFIX}-core-h63d",
    "core-h126d": f"{REGISTRY_PREFIX}-core-h126d",
    "ensemble": f"{REGISTRY_PREFIX}-ensemble",
}


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class DatasetInfo:
    """Dataset metadata for lineage tracking."""

    name: str
    rows: int
    columns: int
    symbols: int
    date_start: str
    date_end: str
    source: str
    digest: str = ""
    nan_fraction: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LiveMetrics:
    """Container for live training metrics."""

    step: int = 0
    epoch: int = 0
    loss: float = 0.0
    val_loss: float = 0.0
    mase: float = 0.0
    learning_rate: float = 0.0
    elapsed_seconds: float = 0.0
    models_trained: int = 0
    current_model: str = ""

    def to_dict(self) -> Dict[str, float]:
        return {k: v for k, v in asdict(self).items() if isinstance(v, (int, float))}


@dataclass
class ModelCard:
    """Model documentation artifact."""

    name: str
    version: int
    horizon_days: int
    training_mode: str
    created_at: str
    created_by: str = "zinc-fusion-pipeline"

    # Data lineage
    dataset_name: str = ""
    dataset_rows: int = 0
    dataset_digest: str = ""

    # Model info
    model_type: str = "AutoGluon-TimeSeriesPredictor"
    best_model: str = ""
    quantile_levels: List[float] = field(default_factory=lambda: QUANTILE_LEVELS)

    # Performance
    mase: float = 0.0
    training_time_sec: float = 0.0
    inference_time_sec: float = 0.0

    # Governance
    stage: str = "None"
    alias: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)


# =============================================================================
# CONNECTION MANAGEMENT
# =============================================================================


def get_tracking_uri() -> str:
    """Get MLflow tracking URI with Railway preference."""
    try:
        import requests

        resp = requests.get(f"{RAILWAY_MLFLOW_URI}/health", timeout=5)
        if resp.status_code == 200:
            logger.info(f"Connected to Railway MLflow: {RAILWAY_MLFLOW_URI}")
            return RAILWAY_MLFLOW_URI
    except Exception as e:
        logger.warning(f"Railway MLflow unreachable: {e}")

    LOCAL_MLRUNS.mkdir(exist_ok=True)
    logger.info(f"Using local MLflow: {LOCAL_MLFLOW_URI}")
    return LOCAL_MLFLOW_URI


# =============================================================================
# CHART GENERATION
# =============================================================================


class ChartGenerator:
    """Generate MLflow artifact charts for model analysis."""

    def __init__(self, style: str = "dark_background"):
        if HAS_MATPLOTLIB:
            plt.style.use(style)
        self.colors = {
            "primary": "#00D4AA",  # Teal
            "secondary": "#FF6B6B",  # Coral
            "tertiary": "#4ECDC4",  # Light teal
            "warning": "#FFE66D",  # Yellow
            "background": "#1a1a2e",  # Dark
        }

    def create_training_progress_chart(
        self, metrics_history: List[Dict], title: str = "Training Progress"
    ) -> Optional[str]:
        """Create training loss/metric curve."""
        if not HAS_MATPLOTLIB or not metrics_history:
            return None

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        fig.patch.set_facecolor(self.colors["background"])

        steps = [m.get("step", i) for i, m in enumerate(metrics_history)]

        # Loss curve
        if any("loss" in m for m in metrics_history):
            losses = [m.get("loss", np.nan) for m in metrics_history]
            val_losses = [m.get("val_loss", np.nan) for m in metrics_history]

            axes[0].plot(
                steps,
                losses,
                color=self.colors["primary"],
                label="Train Loss",
                linewidth=2,
            )
            axes[0].plot(
                steps,
                val_losses,
                color=self.colors["secondary"],
                label="Val Loss",
                linewidth=2,
                linestyle="--",
            )
            axes[0].set_xlabel("Step", color="white")
            axes[0].set_ylabel("Loss", color="white")
            axes[0].set_title("Loss Curve", color="white", fontsize=12)
            axes[0].legend(facecolor=self.colors["background"])
            axes[0].tick_params(colors="white")
            axes[0].set_facecolor(self.colors["background"])

        # MASE curve
        if any("mase" in m for m in metrics_history):
            mase_vals = [m.get("mase", np.nan) for m in metrics_history]

            axes[1].plot(
                steps,
                mase_vals,
                color=self.colors["tertiary"],
                linewidth=2,
                marker="o",
                markersize=4,
            )
            axes[1].set_xlabel("Step", color="white")
            axes[1].set_ylabel("MASE", color="white")
            axes[1].set_title("MASE (Validation)", color="white", fontsize=12)
            axes[1].tick_params(colors="white")
            axes[1].set_facecolor(self.colors["background"])

        plt.suptitle(title, color="white", fontsize=14, fontweight="bold")
        plt.tight_layout()

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            plt.savefig(
                f.name,
                dpi=150,
                facecolor=self.colors["background"],
                edgecolor="none",
                bbox_inches="tight",
            )
            plt.close(fig)
            return f.name

    def create_leaderboard_chart(
        self, leaderboard: pd.DataFrame, title: str = "Model Leaderboard"
    ) -> Optional[str]:
        """Create horizontal bar chart of model scores."""
        if not HAS_MATPLOTLIB or leaderboard is None or len(leaderboard) == 0:
            return None

        fig, ax = plt.subplots(figsize=(12, max(4, len(leaderboard) * 0.5)))
        fig.patch.set_facecolor(self.colors["background"])
        ax.set_facecolor(self.colors["background"])

        models = leaderboard["model"].head(10).tolist()[::-1]
        scores = leaderboard["score_val"].head(10).abs().tolist()[::-1]

        # Color gradient
        colors = plt.cm.viridis(np.linspace(0.3, 0.9, len(models)))

        bars = ax.barh(models, scores, color=colors, edgecolor="white", linewidth=0.5)

        # Add value labels
        for bar, score in zip(bars, scores):
            ax.text(
                bar.get_width() + 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{score:.4f}",
                va="center",
                color="white",
                fontsize=9,
            )

        ax.set_xlabel("MASE Score (lower is better)", color="white")
        ax.set_title(title, color="white", fontsize=14, fontweight="bold")
        ax.tick_params(colors="white")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color("white")
        ax.spines["left"].set_color("white")

        plt.tight_layout()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            plt.savefig(
                f.name,
                dpi=150,
                facecolor=self.colors["background"],
                edgecolor="none",
                bbox_inches="tight",
            )
            plt.close(fig)
            return f.name

    def create_prediction_chart(
        self,
        actuals: pd.Series,
        predictions: pd.DataFrame,
        symbol: str = "ZL",
        title: str = None,
    ) -> Optional[str]:
        """Create prediction vs actuals chart with quantile bands."""
        if not HAS_MATPLOTLIB:
            return None

        fig, ax = plt.subplots(figsize=(14, 6))
        fig.patch.set_facecolor(self.colors["background"])
        ax.set_facecolor(self.colors["background"])

        # Plot actuals
        ax.plot(
            actuals.index,
            actuals.values,
            color="white",
            label="Actual",
            linewidth=1.5,
            alpha=0.9,
        )

        # Plot prediction median
        if "0.5" in predictions.columns:
            ax.plot(
                predictions.index,
                predictions["0.5"],
                color=self.colors["primary"],
                label="Prediction (P50)",
                linewidth=2,
            )

        # Plot confidence band
        if "0.1" in predictions.columns and "0.9" in predictions.columns:
            ax.fill_between(
                predictions.index,
                predictions["0.1"],
                predictions["0.9"],
                color=self.colors["primary"],
                alpha=0.2,
                label="80% Confidence",
            )

        ax.set_xlabel("Date", color="white")
        ax.set_ylabel("Price", color="white")
        ax.set_title(
            title or f"{symbol} Forecast", color="white", fontsize=14, fontweight="bold"
        )
        ax.legend(facecolor=self.colors["background"], labelcolor="white")
        ax.tick_params(colors="white")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        plt.xticks(rotation=45)

        plt.tight_layout()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            plt.savefig(
                f.name,
                dpi=150,
                facecolor=self.colors["background"],
                edgecolor="none",
                bbox_inches="tight",
            )
            plt.close(fig)
            return f.name

    def create_horizon_comparison_chart(
        self, horizon_metrics: Dict[int, float], metric_name: str = "MASE"
    ) -> Optional[str]:
        """Create bar chart comparing metrics across horizons."""
        if not HAS_MATPLOTLIB or not horizon_metrics:
            return None

        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor(self.colors["background"])
        ax.set_facecolor(self.colors["background"])

        horizons = list(horizon_metrics.keys())
        values = list(horizon_metrics.values())

        colors = [
            self.colors["primary"],
            self.colors["tertiary"],
            self.colors["warning"],
            self.colors["secondary"],
        ]

        bars = ax.bar(
            [f"{h}d" for h in horizons],
            values,
            color=colors[: len(horizons)],
            edgecolor="white",
        )

        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.02,
                f"{val:.4f}",
                ha="center",
                color="white",
                fontsize=11,
            )

        ax.set_xlabel("Forecast Horizon", color="white", fontsize=12)
        ax.set_ylabel(metric_name, color="white", fontsize=12)
        ax.set_title(
            f"{metric_name} by Horizon", color="white", fontsize=14, fontweight="bold"
        )
        ax.tick_params(colors="white")

        plt.tight_layout()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            plt.savefig(
                f.name,
                dpi=150,
                facecolor=self.colors["background"],
                edgecolor="none",
                bbox_inches="tight",
            )
            plt.close(fig)
            return f.name


# =============================================================================
# LIVE METRICS CALLBACK
# =============================================================================


class LiveMetricsCallback:
    """
    Callback for streaming live metrics to MLflow during training.

    Usage with AutoGluon:
        callback = LiveMetricsCallback(mlflow_run_id)
        # AutoGluon doesn't have native callbacks, so we poll/log periodically

    Usage pattern:
        callback.on_step(step=100, loss=0.5, val_loss=0.6)
        callback.on_model_trained("Chronos2", mase=0.85)
    """

    def __init__(self, run_id: Optional[str] = None, log_interval: int = 10):
        self.run_id = run_id
        self.log_interval = log_interval
        self.step = 0
        self.start_time = time.time()
        self.metrics_history: List[Dict] = []
        self.models_trained: List[str] = []

    def on_step(
        self,
        step: Optional[int] = None,
        loss: Optional[float] = None,
        val_loss: Optional[float] = None,
        mase: Optional[float] = None,
        **kwargs,
    ):
        """Log metrics at each step."""
        self.step = step or self.step + 1
        elapsed = time.time() - self.start_time

        metrics = {
            "step": self.step,
            "elapsed_seconds": elapsed,
        }

        if loss is not None:
            metrics["loss"] = loss
        if val_loss is not None:
            metrics["val_loss"] = val_loss
        if mase is not None:
            metrics["mase"] = mase
        metrics.update(kwargs)

        self.metrics_history.append(metrics)

        # Log to MLflow
        if self.step % self.log_interval == 0:
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    mlflow.log_metric(f"live/{key}", value, step=self.step)

    def on_model_trained(self, model_name: str, mase: float, fit_time: float = 0):
        """Log when a model finishes training."""
        self.models_trained.append(model_name)

        mlflow.log_metric("models_trained", len(self.models_trained))
        mlflow.log_metric(f"model/{model_name}/mase", mase)
        if fit_time > 0:
            mlflow.log_metric(f"model/{model_name}/fit_time", fit_time)

        logger.info(f"Model trained: {model_name} (MASE={mase:.4f})")

    def on_validation(self, window: int, mase: float):
        """Log validation window results."""
        mlflow.log_metric(f"val/window_{window}/mase", mase)

    def get_history(self) -> List[Dict]:
        """Get full metrics history."""
        return self.metrics_history


# =============================================================================
# QUANT ML COMMAND CENTER
# =============================================================================


class QuantMLCommandCenter:
    """
    Central hub for ML experiment tracking with live metrics,
    dataset lineage, and automated visualization.
    """

    def __init__(self, tracking_uri: Optional[str] = None):
        self.tracking_uri = tracking_uri or get_tracking_uri()
        mlflow.set_tracking_uri(self.tracking_uri)
        self.client = MlflowClient(self.tracking_uri)
        self.chart_gen = ChartGenerator()
        self.active_run = None
        self._metrics_callback = None
        self._datasets_logged: List[str] = []

        logger.info(f"QuantMLCommandCenter initialized @ {self.tracking_uri}")

    def _get_experiment_name(
        self, component: str, horizon: Optional[int] = None
    ) -> str:
        """Get hierarchical experiment name."""
        if component == "core" and horizon:
            key = f"core-h{horizon}d"
        else:
            key = component
        return EXPERIMENT_TAXONOMY.get(key, f"{REGISTRY_PREFIX}/{component}")

    def _ensure_experiment(self, experiment_name: str) -> str:
        """Ensure experiment exists, create if not."""
        try:
            exp = mlflow.get_experiment_by_name(experiment_name)
            if exp is None:
                exp_id = mlflow.create_experiment(experiment_name)
                logger.info(f"Created experiment: {experiment_name}")
                return exp_id
            return exp.experiment_id
        except Exception as e:
            logger.warning(f"Error creating experiment: {e}")
            return mlflow.create_experiment(experiment_name)

    @contextmanager
    def training_run(
        self,
        component: str,
        horizon: int,
        mode: str,
        tags: Optional[Dict[str, str]] = None,
    ):
        """
        Context manager for training runs with live metrics.

        Yields a RunTracker object with methods for:
        - log_dataset(): Log training data with lineage
        - log_live_metric(): Stream metrics during training
        - log_model_complete(): Log final model with charts
        """
        experiment_name = self._get_experiment_name(component, horizon)
        self._ensure_experiment(experiment_name)
        mlflow.set_experiment(experiment_name)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_name = f"{component}_h{horizon}d_{mode}_{timestamp}"

        run_tags = {
            "mlflow.runName": run_name,
            "project": "zinc-fusion-v15",
            "component": component,
            "horizon_days": str(horizon),
            "training_mode": mode,
            "pipeline_version": "2.0.0",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        if tags:
            run_tags.update(tags)

        self.active_run = mlflow.start_run(run_name=run_name, tags=run_tags)
        self._metrics_callback = LiveMetricsCallback(self.active_run.info.run_id)
        self._datasets_logged = []

        # Log base parameters
        mlflow.log_params(
            {
                "horizon_days": horizon,
                "training_mode": mode,
                "component": component,
                "quantile_levels": str(QUANTILE_LEVELS),
            }
        )

        tracker = RunTracker(
            run=self.active_run,
            client=self.client,
            chart_gen=self.chart_gen,
            metrics_callback=self._metrics_callback,
            component=component,
            horizon=horizon,
            mode=mode,
        )

        try:
            logger.info(f"Started run: {run_name} (experiment: {experiment_name})")
            yield tracker

            mlflow.set_tag("status", "COMPLETED")
            mlflow.set_tag("ended_at", datetime.now(timezone.utc).isoformat())

        except Exception as e:
            mlflow.set_tag("status", "FAILED")
            mlflow.set_tag("error", str(e)[:500])
            logger.error(f"Run failed: {e}")
            raise

        finally:
            # Log training progress chart
            if self._metrics_callback.metrics_history:
                chart_path = self.chart_gen.create_training_progress_chart(
                    self._metrics_callback.metrics_history,
                    title=f"{component} h{horizon}d Training Progress",
                )
                if chart_path:
                    mlflow.log_artifact(chart_path, "charts")
                    os.unlink(chart_path)

            mlflow.end_run()
            run_id = self.active_run.info.run_id
            self.active_run = None
            self._metrics_callback = None
            logger.info(f"Ended run: {run_id}")

    def create_all_experiments(self):
        """Create all experiments in the taxonomy."""
        for key, name in EXPERIMENT_TAXONOMY.items():
            self._ensure_experiment(name)
        logger.info(f"Created {len(EXPERIMENT_TAXONOMY)} experiments")

    def get_dashboard_url(self) -> str:
        """Get MLflow UI URL."""
        return self.tracking_uri

    def compare_horizons(self) -> Dict[int, Optional[float]]:
        """Get best MASE for each horizon."""
        results = {}
        for horizon in HORIZONS:
            exp_name = self._get_experiment_name("core", horizon)
            try:
                exp = mlflow.get_experiment_by_name(exp_name)
                if exp:
                    runs = self.client.search_runs(
                        experiment_ids=[exp.experiment_id],
                        order_by=["metrics.mase ASC"],
                        max_results=1,
                    )
                    if runs:
                        results[horizon] = runs[0].data.metrics.get("mase")
                    else:
                        results[horizon] = None
                else:
                    results[horizon] = None
            except Exception:
                results[horizon] = None
        return results


class RunTracker:
    """
    Helper class for tracking a single training run.
    Provides methods for dataset logging, live metrics, and model artifacts.
    """

    def __init__(
        self,
        run,
        client: MlflowClient,
        chart_gen: ChartGenerator,
        metrics_callback: LiveMetricsCallback,
        component: str,
        horizon: int,
        mode: str,
    ):
        self.run = run
        self.client = client
        self.chart_gen = chart_gen
        self.metrics_callback = metrics_callback
        self.component = component
        self.horizon = horizon
        self.mode = mode
        self._start_time = time.time()

    def log_dataset(
        self,
        df: pd.DataFrame,
        context: str = "training",
        name: Optional[str] = None,
        source: Optional[str] = None,
    ) -> DatasetInfo:
        """
        Log a dataset with full lineage tracking.

        Args:
            df: DataFrame to log
            context: "training", "validation", or "test"
            name: Dataset name
            source: Data source URL or path
        """
        # Create MLflow dataset
        dataset_name = name or f"{self.component}_h{self.horizon}d_{context}"

        # Compute digest
        digest = hashlib.md5(
            pd.util.hash_pandas_object(df.head(1000)).values.tobytes()
        ).hexdigest()[:12]

        # Get date range
        date_col = None
        for col in ["timestamp", "as_of_date", "date", "trade_date"]:
            if col in df.columns:
                date_col = col
                break

        if date_col:
            date_start = str(df[date_col].min())
            date_end = str(df[date_col].max())
        else:
            date_start = date_end = "unknown"

        # Symbol count
        symbol_col = "item_id" if "item_id" in df.columns else "symbol"
        symbols = df[symbol_col].nunique() if symbol_col in df.columns else 1

        # Create dataset info
        info = DatasetInfo(
            name=dataset_name,
            rows=len(df),
            columns=len(df.columns),
            symbols=symbols,
            date_start=date_start,
            date_end=date_end,
            source=source or "prisma-postgres",
            digest=digest,
            nan_fraction=df.isna().sum().sum() / (len(df) * len(df.columns)),
        )

        # Log to MLflow
        try:
            mlflow_dataset = mlflow.data.from_pandas(
                df.head(10000),  # Sample for large datasets
                name=dataset_name,
            )
            mlflow.log_input(mlflow_dataset, context=context)
        except Exception as e:
            logger.warning(f"Could not log MLflow dataset: {e}")

        # Log dataset params
        mlflow.log_params(
            {
                f"dataset_{context}_name": dataset_name,
                f"dataset_{context}_rows": info.rows,
                f"dataset_{context}_symbols": info.symbols,
                f"dataset_{context}_features": info.columns,
                f"dataset_{context}_digest": digest,
            }
        )

        # Log dataset info as artifact
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(info.to_dict(), f, indent=2)
            mlflow.log_artifact(f.name, f"datasets/{context}")
            os.unlink(f.name)

        logger.info(f"Logged {context} dataset: {dataset_name} ({info.rows:,} rows)")
        return info

    def log_live_metric(self, key: str, value: float, step: Optional[int] = None):
        """Log a live metric during training."""
        self.metrics_callback.on_step(**{key: value})
        mlflow.log_metric(f"live/{key}", value, step=step)

    def on_model_trained(self, model_name: str, mase: float, fit_time: float = 0):
        """Notify that a model finished training."""
        self.metrics_callback.on_model_trained(model_name, mase, fit_time)

    def log_model_complete(
        self,
        predictor,
        training_time: Optional[float] = None,
        generate_charts: bool = True,
    ):
        """
        Log completed model with all artifacts and charts.

        Args:
            predictor: Trained AutoGluon TimeSeriesPredictor
            training_time: Training duration in seconds
            generate_charts: Whether to generate visualization charts
        """
        if training_time is None:
            training_time = time.time() - self._start_time

        # Log timing
        mlflow.log_metric("training_time_seconds", training_time)
        mlflow.log_metric("training_time_minutes", training_time / 60)

        # Get leaderboard
        leaderboard = None
        try:
            leaderboard = predictor.leaderboard()

            # Log as CSV artifact
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False
            ) as f:
                leaderboard.to_csv(f.name, index=False)
                mlflow.log_artifact(f.name, "leaderboard")
                os.unlink(f.name)

            # Log as JSON
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json.dump(
                    {
                        "leaderboard": leaderboard.to_dict("records"),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    f,
                    indent=2,
                    default=str,
                )
                mlflow.log_artifact(f.name, "leaderboard")
                os.unlink(f.name)

            # Generate leaderboard chart
            if generate_charts:
                chart_path = self.chart_gen.create_leaderboard_chart(
                    leaderboard,
                    title=f"{self.component} h{self.horizon}d Model Leaderboard",
                )
                if chart_path:
                    mlflow.log_artifact(chart_path, "charts")
                    os.unlink(chart_path)

            # Log individual model scores
            for _, row in leaderboard.iterrows():
                model = row["model"]
                score = abs(float(row["score_val"]))
                safe_name = model.replace("/", "_").replace(" ", "_")[:40]
                mlflow.log_metric(f"model/{safe_name}/mase", score)

            mlflow.log_metric("total_models_trained", len(leaderboard))

        except Exception as e:
            logger.warning(f"Could not get leaderboard: {e}")

        # Log best model
        try:
            best_model = predictor.model_best
            mlflow.log_param("best_model", best_model)

            if leaderboard is not None and len(leaderboard) > 0:
                best_score = abs(float(leaderboard.iloc[0]["score_val"]))
                mlflow.log_metric("mase", best_score)
                mlflow.log_metric("best_score", best_score)

                if "pred_time_val" in leaderboard.columns:
                    mlflow.log_metric(
                        "inference_time_seconds",
                        float(leaderboard.iloc[0]["pred_time_val"]),
                    )
        except Exception as e:
            logger.warning(f"Could not log best model: {e}")

        # Log predictor info
        try:
            info = {
                "path": str(predictor.path),
                "model_best": predictor.model_best,
                "prediction_length": predictor.prediction_length,
                "quantile_levels": list(
                    getattr(predictor, "quantile_levels", QUANTILE_LEVELS)
                ),
                "freq": getattr(predictor, "freq", None),
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json.dump(info, f, indent=2, default=str)
                mlflow.log_artifact(f.name, "predictor")
                os.unlink(f.name)
        except Exception as e:
            logger.warning(f"Could not log predictor info: {e}")

        # Log model artifact (zipped)
        model_path = Path(predictor.path)
        if model_path.exists():
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    zip_path = Path(tmp_dir) / "model"
                    shutil.make_archive(str(zip_path), "zip", model_path)
                    mlflow.log_artifact(f"{zip_path}.zip", "models")
                    logger.info(f"Logged model artifact: {model_path}")
            except Exception as e:
                logger.warning(f"Could not zip model: {e}")

        # Log model card
        card = ModelCard(
            name=f"{REGISTRY_PREFIX}-{self.component}-h{self.horizon}d",
            version=1,
            horizon_days=self.horizon,
            training_mode=self.mode,
            created_at=datetime.now(timezone.utc).isoformat(),
            best_model=predictor.model_best if hasattr(predictor, "model_best") else "",
            training_time_sec=training_time,
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(card.to_json())
            mlflow.log_artifact(f.name, "model_card")
            os.unlink(f.name)

        logger.info(
            f"Logged complete model: {predictor.model_best} (MASE={leaderboard.iloc[0]['score_val']:.4f})"
            if leaderboard is not None and len(leaderboard) > 0
            else "Logged complete model"
        )

    def log_predictions(
        self,
        predictions: pd.DataFrame,
        actuals: Optional[pd.Series] = None,
        symbol: str = "ZL",
        generate_chart: bool = True,
    ):
        """Log predictions with optional visualization."""
        # Log predictions CSV
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            predictions.to_csv(f.name, index=True)
            mlflow.log_artifact(f.name, "predictions")
            os.unlink(f.name)

        mlflow.log_metric("predictions/total_rows", len(predictions))

        # Generate chart if actuals provided
        if generate_chart and actuals is not None:
            chart_path = self.chart_gen.create_prediction_chart(
                actuals, predictions, symbol, title=f"{symbol} {self.horizon}d Forecast"
            )
            if chart_path:
                mlflow.log_artifact(chart_path, "charts")
                os.unlink(chart_path)


# =============================================================================
# MODEL REGISTRY
# =============================================================================


class ModelRegistry:
    """Model Registry with lifecycle management (None → Staging → Production → Archived)."""

    def __init__(self, tracking_uri: Optional[str] = None):
        self.tracking_uri = tracking_uri or get_tracking_uri()
        mlflow.set_tracking_uri(self.tracking_uri)
        self.client = MlflowClient(self.tracking_uri)
        logger.info(f"ModelRegistry initialized @ {self.tracking_uri}")

    def register_model(
        self,
        run_id: str,
        component: str,
        horizon: Optional[int] = None,
        description: Optional[str] = None,
    ) -> ModelVersion:
        """Register a model from a training run."""
        if component == "core" and horizon:
            model_name = f"{REGISTRY_PREFIX}-core-h{horizon}d"
        else:
            model_name = f"{REGISTRY_PREFIX}-{component}"

        model_uri = f"runs:/{run_id}/models"

        try:
            self.client.get_registered_model(model_name)
        except MlflowException:
            self.client.create_registered_model(
                model_name, description=description or f"ZINC-FUSION {component} model"
            )

        mv = self.client.create_model_version(
            name=model_name,
            source=model_uri,
            run_id=run_id,
            description=description or f"Registered from run {run_id}",
        )

        self.client.set_model_version_tag(
            model_name,
            mv.version,
            "registered_at",
            datetime.now(timezone.utc).isoformat(),
        )

        logger.info(f"Registered: {model_name} v{mv.version}")
        return mv

    def promote_to_champion(
        self, model_name: str, version: Union[int, str]
    ) -> ModelVersion:
        """Promote a model to champion (production)."""
        # Archive current production
        try:
            for v in self.client.get_latest_versions(model_name, stages=["Production"]):
                self.client.transition_model_version_stage(
                    model_name, v.version, "Archived"
                )
        except Exception:
            pass

        mv = self.client.transition_model_version_stage(
            model_name, str(version), "Production"
        )

        try:
            self.client.set_registered_model_alias(
                model_name, ModelAlias.CHAMPION.value, str(version)
            )
        except Exception:
            pass

        logger.info(f"Promoted {model_name} v{version} to champion")
        return mv

    def get_champion(self, model_name: str) -> Optional[ModelVersion]:
        """Get current champion model."""
        try:
            return self.client.get_model_version_by_alias(
                model_name, ModelAlias.CHAMPION.value
            )
        except Exception:
            try:
                versions = self.client.get_latest_versions(model_name, ["Production"])
                return versions[0] if versions else None
            except Exception:
                return None

    def list_models(self) -> List[Dict]:
        """List all registered models."""
        models = []
        try:
            for rm in self.client.search_registered_models(
                f"name LIKE '{REGISTRY_PREFIX}%'"
            ):
                champion = self.get_champion(rm.name)
                models.append(
                    {
                        "name": rm.name,
                        "latest_version": (
                            rm.latest_versions[0].version
                            if rm.latest_versions
                            else None
                        ),
                        "champion_version": champion.version if champion else None,
                    }
                )
        except Exception as e:
            logger.warning(f"Error listing models: {e}")
        return models


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================

# Import the old class name for compatibility
AutoGluonMLflowTracker = QuantMLCommandCenter


# =============================================================================
# CLI
# =============================================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ZINC-FUSION Quant ML Command Center")
    parser.add_argument("--test", action="store_true", help="Test connection")
    parser.add_argument(
        "--create-experiments",
        action="store_true",
        help="Create all experiments in taxonomy",
    )
    parser.add_argument(
        "--list-experiments", action="store_true", help="List all experiments"
    )
    parser.add_argument(
        "--list-models", action="store_true", help="List registered models"
    )
    parser.add_argument(
        "--compare-horizons",
        action="store_true",
        help="Compare best MASE across horizons",
    )
    parser.add_argument("--dashboard", action="store_true", help="Print dashboard URL")

    args = parser.parse_args()

    if args.test:
        print("Testing MLflow connection...")
        uri = get_tracking_uri()
        print(f"Tracking URI: {uri}")
        cmd = QuantMLCommandCenter()
        print("Command Center: OK")
        registry = ModelRegistry()
        print("Model Registry: OK")
        print("\n✅ Connection test PASSED!")

    elif args.create_experiments:
        cmd = QuantMLCommandCenter()
        cmd.create_all_experiments()
        print(f"\n✅ Created {len(EXPERIMENT_TAXONOMY)} experiments")
        for key, name in EXPERIMENT_TAXONOMY.items():
            print(f"  {name}")

    elif args.list_experiments:
        cmd = QuantMLCommandCenter()
        print("\n" + "=" * 60)
        print("EXPERIMENT TAXONOMY")
        print("=" * 60)
        for key, name in EXPERIMENT_TAXONOMY.items():
            exp = mlflow.get_experiment_by_name(name)
            status = "✓" if exp else "✗"
            print(f"  {status} {name}")

    elif args.list_models:
        registry = ModelRegistry()
        models = registry.list_models()
        print("\n" + "=" * 60)
        print("REGISTERED MODELS")
        print("=" * 60)
        for m in models:
            champion = f"v{m['champion_version']}" if m["champion_version"] else "none"
            print(
                f"  {m['name']:<40} | latest: v{m['latest_version']} | champion: {champion}"
            )
        if not models:
            print("  No models registered yet.")

    elif args.compare_horizons:
        cmd = QuantMLCommandCenter()
        results = cmd.compare_horizons()
        print("\n" + "=" * 60)
        print("HORIZON COMPARISON (Best MASE)")
        print("=" * 60)
        for horizon, mase in results.items():
            if mase:
                print(f"  {horizon}d: {mase:.4f}")
            else:
                print(f"  {horizon}d: No runs yet")

        # Generate chart if we have data
        if any(v is not None for v in results.values()) and HAS_MATPLOTLIB:
            chart_gen = ChartGenerator()
            chart_path = chart_gen.create_horizon_comparison_chart(
                {k: v for k, v in results.items() if v is not None}
            )
            if chart_path:
                CHARTS_DIR.mkdir(exist_ok=True)
                dest = CHARTS_DIR / "horizon_comparison.png"
                shutil.move(chart_path, dest)
                print(f"\n📊 Chart saved: {dest}")

    elif args.dashboard:
        uri = get_tracking_uri()
        print(f"\n🔗 MLflow Dashboard: {uri}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
