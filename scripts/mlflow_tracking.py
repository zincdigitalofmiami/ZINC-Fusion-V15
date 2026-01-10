#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Quant ML Command Center
=========================================

Production-grade MLflow tracking and model registry for quantitative
commodity forecasting with model versioning and lifecycle management.

Architecture:
- Tracking server: Local SQLite (mlruns/mlflow.db)
- Model Registry: Staging → Champion → Archived lifecycle
- Experiments: Hierarchical taxonomy (core/specialist/ensemble/backtest)
- Artifacts: Models stored as versioned, deployable packages

Experiment Taxonomy:
    zinc-fusion/
    ├── core/           # L0 Core baseline models (Chronos-2)
    │   ├── h5d         # 5-day horizon
    │   ├── h21d        # 21-day horizon
    │   ├── h63d        # 63-day horizon
    │   └── h126d       # 126-day horizon
    ├── specialist/     # L1 Domain specialist models
    │   ├── china-demand
    │   ├── brazil-weather
    │   ├── argentina-fx
    │   └── ... (11 specialists)
    ├── ensemble/       # L2 Ensemble/stacking models
    │   └── fusion-lasso
    └── backtest/       # Historical validation runs

Model Registry:
    zinc-fusion-core-h5d      # Registered model per horizon
    zinc-fusion-core-h21d
    zinc-fusion-specialist-*
    zinc-fusion-ensemble

Model Aliases:
    @champion   - Production model serving live predictions
    @staging    - Candidate model under validation
    @challenger - A/B test candidate

Usage:
    from scripts.mlflow_tracking import QuantMLCommandCenter, ModelRegistry

    # Training workflow
    cmd = QuantMLCommandCenter()
    with cmd.training_run("core", horizon=5, mode="full") as run:
        predictor = TimeSeriesPredictor(...).fit(...)
        cmd.log_autogluon_model(predictor, training_time=3600.0)

    # Model promotion workflow
    registry = ModelRegistry()
    registry.promote_to_staging("zinc-fusion-core-h5d", run_id)
    registry.promote_to_champion("zinc-fusion-core-h5d", version=3)

    # Model serving
    model = registry.load_champion("zinc-fusion-core-h5d")
"""

import os
import json
import shutil
import tempfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Literal
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

import mlflow
from mlflow.tracking import MlflowClient
from mlflow.entities.model_registry import ModelVersion
from mlflow.exceptions import MlflowException

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

# MLflow tracking (local SQLite)
LOCAL_MLFLOW_URI = f"sqlite:///{LOCAL_MLRUNS / 'mlflow.db'}"

# Model Registry naming convention
REGISTRY_PREFIX = "zinc-fusion"


class ModelStage(str, Enum):
    """Model lifecycle stages."""

    NONE = "None"
    STAGING = "Staging"
    PRODUCTION = "Production"
    ARCHIVED = "Archived"


class ModelAlias(str, Enum):
    """Model aliases for deployment targeting."""

    CHAMPION = "champion"  # Production model
    STAGING = "staging"  # Validation candidate
    CHALLENGER = "challenger"  # A/B test candidate


# Experiment taxonomy
EXPERIMENT_TAXONOMY = {
    # L0 Core models - one experiment per horizon
    "core-h5d": f"{REGISTRY_PREFIX}/core/h5d",
    "core-h21d": f"{REGISTRY_PREFIX}/core/h21d",
    "core-h63d": f"{REGISTRY_PREFIX}/core/h63d",
    "core-h126d": f"{REGISTRY_PREFIX}/core/h126d",
    # L1 Specialist models
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
    # Backtest experiments
    "backtest": f"{REGISTRY_PREFIX}/backtest/validation",
}

# Registered model names (for Model Registry)
REGISTERED_MODELS = {
    "core-h5d": f"{REGISTRY_PREFIX}-core-h5d",
    "core-h21d": f"{REGISTRY_PREFIX}-core-h21d",
    "core-h63d": f"{REGISTRY_PREFIX}-core-h63d",
    "core-h126d": f"{REGISTRY_PREFIX}-core-h126d",
    "ensemble": f"{REGISTRY_PREFIX}-ensemble",
}

# Quantile levels for probabilistic forecasting
QUANTILE_LEVELS = [0.1, 0.5, 0.9]

# Horizons
HORIZONS = [5, 21, 63, 126]


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class DatasetStats:
    """Statistics about training dataset."""

    rows: int
    symbols: int
    features: int
    date_start: str
    date_end: str
    nan_fraction: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelMetrics:
    """Standard metrics for time series models."""

    mase: Optional[float] = None  # Mean Absolute Scaled Error
    rmse: Optional[float] = None  # Root Mean Square Error
    mape: Optional[float] = None  # Mean Absolute Percentage Error
    smape: Optional[float] = None  # Symmetric MAPE
    coverage_90: Optional[float] = None  # 90% prediction interval coverage
    winkler_90: Optional[float] = None  # Winkler score for 90% interval
    training_time_sec: float = 0.0
    inference_time_sec: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ModelCard:
    """Model documentation following ML model card convention."""

    name: str
    version: int
    horizon_days: int
    training_mode: str
    created_at: str
    created_by: str = "zinc-fusion-pipeline"

    # Data provenance
    dataset_stats: Optional[DatasetStats] = None
    data_sources: List[str] = field(default_factory=list)

    # Model details
    model_type: str = "AutoGluon-TimeSeriesPredictor"
    best_model: str = ""
    quantile_levels: List[float] = field(default_factory=lambda: QUANTILE_LEVELS)

    # Performance
    metrics: Optional[ModelMetrics] = None

    # Governance
    stage: str = "None"
    alias: Optional[str] = None
    validation_status: str = "pending"
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.dataset_stats:
            d["dataset_stats"] = self.dataset_stats.to_dict()
        if self.metrics:
            d["metrics"] = self.metrics.to_dict()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


# =============================================================================
# CONNECTION MANAGEMENT
# =============================================================================


def get_tracking_uri() -> str:
    """Get MLflow tracking URI (local SQLite)."""
    LOCAL_MLRUNS.mkdir(exist_ok=True)
    logger.info(f"Using local MLflow: {LOCAL_MLFLOW_URI}")
    return LOCAL_MLFLOW_URI


def get_client() -> MlflowClient:
    """Get configured MLflow client."""
    uri = get_tracking_uri()
    mlflow.set_tracking_uri(uri)
    return MlflowClient(uri)


# =============================================================================
# QUANT ML COMMAND CENTER
# =============================================================================


class QuantMLCommandCenter:
    """
    Central hub for all ML experiment tracking and model management.

    Provides:
    - Hierarchical experiment organization
    - Standardized run naming and tagging
    - AutoGluon-specific logging
    - Model artifact management
    - Dataset lineage tracking
    """

    def __init__(self, tracking_uri: Optional[str] = None):
        """Initialize command center."""
        self.tracking_uri = tracking_uri or get_tracking_uri()
        mlflow.set_tracking_uri(self.tracking_uri)
        self.client = MlflowClient(self.tracking_uri)
        self.active_run = None
        self._run_metrics = ModelMetrics()

        logger.info(f"QuantMLCommandCenter initialized @ {self.tracking_uri}")

    def _get_experiment_name(
        self, component: str, horizon: Optional[int] = None
    ) -> str:
        """Get hierarchical experiment name."""
        if component == "core" and horizon:
            key = f"core-h{horizon}d"
        elif component.startswith("specialist-"):
            key = component
        else:
            key = component

        return EXPERIMENT_TAXONOMY.get(key, f"{REGISTRY_PREFIX}/{component}")

    def _get_registered_model_name(
        self, component: str, horizon: Optional[int] = None
    ) -> str:
        """Get registered model name for Model Registry."""
        if component == "core" and horizon:
            return REGISTERED_MODELS.get(
                f"core-h{horizon}d", f"{REGISTRY_PREFIX}-{component}-h{horizon}d"
            )
        return REGISTERED_MODELS.get(component, f"{REGISTRY_PREFIX}-{component}")

    @contextmanager
    def training_run(
        self,
        component: str,
        horizon: int,
        mode: str,
        dataset_stats: Optional[DatasetStats] = None,
        tags: Optional[Dict[str, str]] = None,
    ):
        """
        Context manager for training runs.

        Usage:
            with cmd.training_run("core", horizon=5, mode="full") as run:
                predictor = train_model(...)
                cmd.log_autogluon_model(predictor, 3600.0)
        """
        experiment_name = self._get_experiment_name(component, horizon)

        # Ensure experiment exists
        try:
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if experiment is None:
                experiment_id = mlflow.create_experiment(experiment_name)
            else:
                experiment_id = experiment.experiment_id
        except Exception:
            experiment_id = mlflow.create_experiment(experiment_name)

        mlflow.set_experiment(experiment_name)

        # Build run name: component_hXd_mode_YYYYMMDD_HHMM
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        run_name = f"{component}_h{horizon}d_{mode}_{timestamp}"

        # Build tags
        run_tags = {
            "mlflow.runName": run_name,
            "project": "zinc-fusion-v15",
            "component": component,
            "horizon_days": str(horizon),
            "training_mode": mode,
            "pipeline_version": "1.0.0",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        if tags:
            run_tags.update(tags)

        # Start run
        self.active_run = mlflow.start_run(run_name=run_name, tags=run_tags)
        self._run_metrics = ModelMetrics()

        try:
            # Log parameters
            params = {
                "horizon_days": horizon,
                "prediction_length": horizon,  # Daily predictions
                "training_mode": mode,
                "quantile_levels": str(QUANTILE_LEVELS),
                "component": component,
            }

            if dataset_stats:
                params.update(
                    {
                        "data_rows": dataset_stats.rows,
                        "data_symbols": dataset_stats.symbols,
                        "data_features": dataset_stats.features,
                        "data_date_start": dataset_stats.date_start,
                        "data_date_end": dataset_stats.date_end,
                        "data_nan_fraction": dataset_stats.nan_fraction,
                    }
                )

            mlflow.log_params(params)

            logger.info(f"Started run: {run_name} (experiment: {experiment_name})")
            yield self.active_run

            # Success - log completion
            mlflow.set_tag("status", "COMPLETED")
            mlflow.set_tag("ended_at", datetime.now(timezone.utc).isoformat())

        except Exception as e:
            mlflow.set_tag("status", "FAILED")
            mlflow.set_tag("error", str(e)[:250])
            logger.error(f"Run failed: {e}")
            raise

        finally:
            mlflow.end_run()
            run_id = self.active_run.info.run_id
            self.active_run = None
            logger.info(f"Ended run: {run_id}")

    def log_autogluon_model(
        self,
        predictor,
        training_time: float,
        eval_data: Optional[Any] = None,
        register: bool = True,
    ) -> Optional[str]:
        """
        Log AutoGluon TimeSeriesPredictor model and optionally register it.

        Args:
            predictor: Trained TimeSeriesPredictor
            training_time: Training duration in seconds
            eval_data: Optional test data for evaluation metrics
            register: Whether to register model in Model Registry

        Returns:
            Registered model version if register=True
        """
        if not self.active_run:
            raise RuntimeError("No active run. Use training_run() context manager.")

        # 1. Log training time
        mlflow.log_metric("training_time_seconds", training_time)
        mlflow.log_metric("training_time_minutes", training_time / 60)
        self._run_metrics.training_time_sec = training_time

        # 2. Log leaderboard
        leaderboard = None
        try:
            leaderboard = predictor.leaderboard()
            self._log_leaderboard(leaderboard)
        except Exception as e:
            logger.warning(f"Could not get leaderboard: {e}")

        # 3. Log best model info
        best_model = None
        try:
            best_model = predictor.model_best
            mlflow.log_param("best_model", best_model)

            if leaderboard is not None and len(leaderboard) > 0:
                best_row = leaderboard.iloc[0]

                # MASE (primary metric - lower is better)
                if "score_val" in best_row:
                    score = float(best_row["score_val"])
                    mlflow.log_metric("mase", abs(score))  # MLflow stored as negative
                    self._run_metrics.mase = abs(score)

                # Timing metrics
                if "pred_time_val" in best_row:
                    mlflow.log_metric(
                        "inference_time_seconds", float(best_row["pred_time_val"])
                    )
                    self._run_metrics.inference_time_sec = float(
                        best_row["pred_time_val"]
                    )

                if "fit_time" in best_row:
                    mlflow.log_metric("fit_time_seconds", float(best_row["fit_time"]))

        except Exception as e:
            logger.warning(f"Could not log best model info: {e}")

        # 4. Log predictor info
        self._log_predictor_info(predictor)

        # 5. Evaluate on test data if provided
        if eval_data is not None:
            self._log_evaluation_metrics(predictor, eval_data)

        # 6. Log model artifact
        model_version = self._log_model_artifact(predictor, register=register)

        # 7. Log model card
        self._log_model_card(predictor, best_model)

        logger.info(f"Logged AutoGluon model: {best_model}")
        return model_version

    def _log_leaderboard(self, leaderboard):
        """Log model leaderboard as artifact and metrics."""
        # JSON artifact
        lb_records = leaderboard.to_dict("records")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "leaderboard": lb_records,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "total_models": len(lb_records),
                },
                f,
                indent=2,
                default=str,
            )
            temp_path = f.name
        mlflow.log_artifact(temp_path, "leaderboard")
        os.unlink(temp_path)

        # CSV for easy viewing
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            leaderboard.to_csv(f.name, index=False)
            temp_path = f.name
        mlflow.log_artifact(temp_path, "leaderboard")
        os.unlink(temp_path)

        # Log top model scores
        for i, row in leaderboard.head(5).iterrows():
            model_name = row.get("model", f"model_{i}")
            score = row.get("score_val", 0)
            safe_name = model_name.replace("/", "_").replace(" ", "_")[:40]
            mlflow.log_metric(f"model/{safe_name}/mase", abs(float(score)))

        mlflow.log_metric("total_models_trained", len(leaderboard))

    def _log_predictor_info(self, predictor):
        """Log predictor configuration."""
        info = {
            "path": str(predictor.path),
            "model_best": predictor.model_best,
            "prediction_length": predictor.prediction_length,
            "quantile_levels": list(
                getattr(predictor, "quantile_levels", QUANTILE_LEVELS)
            ),
            "target_column": getattr(predictor, "target", "target"),
            "freq": getattr(predictor, "freq", None),
        }

        try:
            model_info = predictor.info()
            info["model_info"] = model_info
        except:
            pass

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(info, f, indent=2, default=str)
            temp_path = f.name
        mlflow.log_artifact(temp_path, "predictor")
        os.unlink(temp_path)

    def _log_evaluation_metrics(self, predictor, eval_data):
        """Evaluate and log metrics on test data."""
        try:
            import time

            start = time.time()
            metrics = predictor.evaluate(eval_data)
            eval_time = time.time() - start

            for metric_name, value in metrics.items():
                if isinstance(value, (int, float)):
                    safe_name = metric_name.replace(".", "_")
                    mlflow.log_metric(f"eval/{safe_name}", float(value))

            mlflow.log_metric("eval/inference_time", eval_time)

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json.dump(
                    {
                        "evaluation": metrics,
                        "inference_time_sec": eval_time,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    f,
                    indent=2,
                    default=str,
                )
                temp_path = f.name
            mlflow.log_artifact(temp_path, "evaluation")
            os.unlink(temp_path)

        except Exception as e:
            logger.warning(f"Evaluation failed: {e}")

    def _log_model_artifact(self, predictor, register: bool = True) -> Optional[str]:
        """Log model artifacts and optionally register."""
        model_path = Path(predictor.path)

        if not model_path.exists():
            logger.warning(f"Model path does not exist: {model_path}")
            return None

        # Create model package
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                # Zip the predictor directory
                zip_path = Path(tmp_dir) / "model"
                shutil.make_archive(str(zip_path), "zip", model_path)

                # Log as artifact
                mlflow.log_artifact(f"{zip_path}.zip", "models")

                # Create model info file
                model_info = {
                    "model_type": "autogluon-timeseries",
                    "predictor_path": str(model_path),
                    "load_command": f"from autogluon.timeseries import TimeSeriesPredictor; predictor = TimeSeriesPredictor.load('{model_path}')",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "checksum": self._compute_checksum(f"{zip_path}.zip"),
                }

                info_path = Path(tmp_dir) / "model_info.json"
                with open(info_path, "w") as f:
                    json.dump(model_info, f, indent=2)
                mlflow.log_artifact(str(info_path), "models")

                logger.info(f"Logged model artifact: {model_path}")

        except Exception as e:
            logger.warning(f"Could not package model: {e}")
            # Log reference file instead
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(f"Model saved at: {model_path}\n")
                f.write(f"Load with: TimeSeriesPredictor.load('{model_path}')\n")
                temp_path = f.name
            mlflow.log_artifact(temp_path, "models")
            os.unlink(temp_path)

        return None  # Model registration handled separately

    def _log_model_card(self, predictor, best_model: Optional[str]):
        """Log model card documentation."""
        run = self.active_run
        params = run.data.params if hasattr(run, "data") else {}

        card = ModelCard(
            name=f"{REGISTRY_PREFIX}-{params.get('component', 'unknown')}-h{params.get('horizon_days', '?')}d",
            version=1,  # Will be updated on registration
            horizon_days=int(params.get("horizon_days", 0)),
            training_mode=params.get("training_mode", "unknown"),
            created_at=datetime.now(timezone.utc).isoformat(),
            best_model=best_model or "unknown",
            metrics=self._run_metrics,
            data_sources=[
                "market_futures_1h",
                "fred_observations_1d",
                "weather_noaa_1d",
                "fx_spot_1d",
                "cftc_cot_1w",
                "usda_export_sales_1w",
                "usda_wasde_1m",
                "epa_rin_prices_1d",
                "news_articles_1d",
            ],
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(card.to_json())
            temp_path = f.name
        mlflow.log_artifact(temp_path, "model_card")
        os.unlink(temp_path)

    def _compute_checksum(self, filepath: str) -> str:
        """Compute SHA256 checksum of file."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()[:16]

    def log_predictions(self, predictions, horizon: int, symbol: Optional[str] = None):
        """Log prediction results."""
        if not self.active_run:
            raise RuntimeError("No active run.")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            predictions.to_csv(f.name, index=True)
            temp_path = f.name

        artifact_name = f"predictions_h{horizon}d"
        if symbol:
            artifact_name += f"_{symbol}"

        mlflow.log_artifact(temp_path, f"predictions/{artifact_name}")
        os.unlink(temp_path)

        mlflow.log_metric("predictions/total_rows", len(predictions))

    def log_metric(self, key: str, value: float, step: Optional[int] = None):
        """Log a custom metric."""
        if self.active_run:
            mlflow.log_metric(key, value, step=step)

    def log_param(self, key: str, value: Any):
        """Log a custom parameter."""
        if self.active_run:
            mlflow.log_param(key, value)

    def get_best_run(
        self,
        component: str,
        horizon: Optional[int] = None,
        metric: str = "mase",
        mode: Optional[str] = None,
    ) -> Optional[Dict]:
        """Get the best run for a component/horizon."""
        experiment_name = self._get_experiment_name(component, horizon)

        try:
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if not experiment:
                return None

            filter_parts = []
            if mode:
                filter_parts.append(f"params.training_mode = '{mode}'")

            filter_string = " and ".join(filter_parts) if filter_parts else None

            runs = self.client.search_runs(
                experiment_ids=[experiment.experiment_id],
                filter_string=filter_string,
                order_by=[f"metrics.{metric} ASC"],
                max_results=1,
            )

            if runs:
                run = runs[0]
                return {
                    "run_id": run.info.run_id,
                    "run_name": run.info.run_name,
                    "status": run.info.status,
                    "metrics": dict(run.data.metrics),
                    "params": dict(run.data.params),
                    "artifact_uri": run.info.artifact_uri,
                }

        except Exception as e:
            logger.warning(f"Error searching runs: {e}")

        return None

    def compare_runs(
        self,
        component: str,
        horizon: Optional[int] = None,
        metric: str = "mase",
        n_runs: int = 10,
    ) -> List[Dict]:
        """Compare recent runs for a component."""
        experiment_name = self._get_experiment_name(component, horizon)

        try:
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if not experiment:
                return []

            runs = self.client.search_runs(
                experiment_ids=[experiment.experiment_id],
                order_by=[f"metrics.{metric} ASC"],
                max_results=n_runs,
            )

            return [
                {
                    "run_id": r.info.run_id,
                    "run_name": r.info.run_name,
                    "status": r.info.status,
                    "mase": r.data.metrics.get("mase"),
                    "horizon": r.data.params.get("horizon_days"),
                    "mode": r.data.params.get("training_mode"),
                    "best_model": r.data.params.get("best_model"),
                    "training_minutes": r.data.metrics.get("training_time_minutes"),
                }
                for r in runs
            ]

        except Exception as e:
            logger.warning(f"Error comparing runs: {e}")
            return []


# =============================================================================
# MODEL REGISTRY
# =============================================================================


class ModelRegistry:
    """
    Model Registry for managing model lifecycle.

    Follows MLOps best practices:
    - Model versioning with automatic increment
    - Lifecycle stages: None → Staging → Production → Archived
    - Aliases for deployment targeting (@champion, @staging, @challenger)
    - Model lineage and governance
    """

    def __init__(self, tracking_uri: Optional[str] = None):
        """Initialize registry."""
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
        tags: Optional[Dict[str, str]] = None,
    ) -> ModelVersion:
        """
        Register a model from a training run.

        Args:
            run_id: MLflow run ID containing the model
            component: Model component (core, specialist-*, ensemble)
            horizon: Forecast horizon in days (required for core)
            description: Model description
            tags: Additional tags

        Returns:
            Registered ModelVersion
        """
        # Get registered model name
        if component == "core" and horizon:
            model_name = f"{REGISTRY_PREFIX}-core-h{horizon}d"
        else:
            model_name = f"{REGISTRY_PREFIX}-{component}"

        # Model URI from run
        model_uri = f"runs:/{run_id}/models"

        # Ensure registered model exists
        try:
            self.client.get_registered_model(model_name)
        except MlflowException:
            self.client.create_registered_model(
                model_name,
                description=f"ZINC-FUSION {component} model for {horizon}d horizon forecasting",
            )
            logger.info(f"Created registered model: {model_name}")

        # Register new version
        mv = self.client.create_model_version(
            name=model_name,
            source=model_uri,
            run_id=run_id,
            description=description or f"Registered from run {run_id}",
        )

        # Add tags
        version_tags = {
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "component": component,
        }
        if horizon:
            version_tags["horizon_days"] = str(horizon)
        if tags:
            version_tags.update(tags)

        for key, value in version_tags.items():
            self.client.set_model_version_tag(model_name, mv.version, key, value)

        logger.info(f"Registered model: {model_name} version {mv.version}")
        return mv

    def promote_to_staging(
        self, model_name: str, version: Union[int, str]
    ) -> ModelVersion:
        """Promote a model version to Staging."""
        return self._transition_stage(model_name, version, ModelStage.STAGING)

    def promote_to_champion(
        self, model_name: str, version: Union[int, str]
    ) -> ModelVersion:
        """
        Promote a model version to Production (Champion).

        This will:
        1. Archive the current champion (if any)
        2. Transition the new version to Production
        3. Set the @champion alias
        """
        # Archive current production versions
        try:
            versions = self.client.get_latest_versions(
                model_name, stages=["Production"]
            )
            for v in versions:
                self._transition_stage(model_name, v.version, ModelStage.ARCHIVED)
                logger.info(f"Archived previous champion: {model_name} v{v.version}")
        except Exception:
            pass

        # Promote new version
        mv = self._transition_stage(model_name, version, ModelStage.PRODUCTION)

        # Set champion alias
        try:
            self.client.set_registered_model_alias(
                model_name, ModelAlias.CHAMPION.value, str(version)
            )
            logger.info(f"Set @champion alias for {model_name} v{version}")
        except Exception as e:
            logger.warning(f"Could not set alias: {e}")

        return mv

    def set_challenger(self, model_name: str, version: Union[int, str]) -> ModelVersion:
        """Set a model version as @challenger for A/B testing."""
        mv = self._transition_stage(model_name, version, ModelStage.STAGING)

        try:
            self.client.set_registered_model_alias(
                model_name, ModelAlias.CHALLENGER.value, str(version)
            )
            logger.info(f"Set @challenger alias for {model_name} v{version}")
        except Exception as e:
            logger.warning(f"Could not set challenger alias: {e}")

        return mv

    def archive_model(self, model_name: str, version: Union[int, str]) -> ModelVersion:
        """Archive a model version."""
        return self._transition_stage(model_name, version, ModelStage.ARCHIVED)

    def _transition_stage(
        self, model_name: str, version: Union[int, str], stage: ModelStage
    ) -> ModelVersion:
        """Transition model version to a stage."""
        mv = self.client.transition_model_version_stage(
            name=model_name,
            version=str(version),
            stage=stage.value,
            archive_existing_versions=False,
        )

        self.client.set_model_version_tag(
            model_name,
            str(version),
            f"stage_{stage.value.lower()}_at",
            datetime.now(timezone.utc).isoformat(),
        )

        logger.info(f"Transitioned {model_name} v{version} to {stage.value}")
        return mv

    def get_champion(self, model_name: str) -> Optional[ModelVersion]:
        """Get the current champion model."""
        try:
            # Try alias first
            mv = self.client.get_model_version_by_alias(
                model_name, ModelAlias.CHAMPION.value
            )
            return mv
        except Exception:
            pass

        # Fallback to stage
        try:
            versions = self.client.get_latest_versions(
                model_name, stages=["Production"]
            )
            return versions[0] if versions else None
        except Exception:
            return None

    def get_staging(self, model_name: str) -> Optional[ModelVersion]:
        """Get the current staging model."""
        try:
            versions = self.client.get_latest_versions(model_name, stages=["Staging"])
            return versions[0] if versions else None
        except Exception:
            return None

    def load_champion(self, model_name: str) -> Any:
        """Load the champion model for inference."""
        champion = self.get_champion(model_name)
        if not champion:
            raise ValueError(f"No champion model found for {model_name}")

        model_uri = f"models:/{model_name}@{ModelAlias.CHAMPION.value}"

        # For AutoGluon models, we need special handling
        logger.info(f"Loading champion: {model_uri}")
        return mlflow.pyfunc.load_model(model_uri)

    def list_models(self) -> List[Dict]:
        """List all registered models in the registry."""
        models = []

        try:
            for rm in self.client.search_registered_models(
                f"name LIKE '{REGISTRY_PREFIX}%'"
            ):
                champion = self.get_champion(rm.name)
                models.append(
                    {
                        "name": rm.name,
                        "description": rm.description,
                        "latest_version": (
                            rm.latest_versions[0].version
                            if rm.latest_versions
                            else None
                        ),
                        "champion_version": champion.version if champion else None,
                        "tags": dict(rm.tags) if rm.tags else {},
                    }
                )
        except Exception as e:
            logger.warning(f"Error listing models: {e}")

        return models

    def get_model_history(self, model_name: str) -> List[Dict]:
        """Get version history for a model."""
        history = []

        try:
            for mv in self.client.search_model_versions(f"name='{model_name}'"):
                history.append(
                    {
                        "version": mv.version,
                        "stage": mv.current_stage,
                        "status": mv.status,
                        "run_id": mv.run_id,
                        "created_at": mv.creation_timestamp,
                        "description": mv.description,
                        "tags": dict(mv.tags) if mv.tags else {},
                    }
                )
        except Exception as e:
            logger.warning(f"Error getting model history: {e}")

        return sorted(history, key=lambda x: x["version"], reverse=True)


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================


class AutoGluonMLflowTracker(QuantMLCommandCenter):
    """
    Backward-compatible wrapper for existing code.

    Deprecated: Use QuantMLCommandCenter instead.
    """

    def __init__(self, experiment: str = "core", tracking_uri: Optional[str] = None):
        super().__init__(tracking_uri)
        self._experiment_key = experiment

        # Map old experiment names to new taxonomy
        if experiment in EXPERIMENT_TAXONOMY:
            exp_name = EXPERIMENT_TAXONOMY[experiment]
        elif experiment.startswith("zinc-fusion"):
            exp_name = experiment
        else:
            exp_name = f"{REGISTRY_PREFIX}/{experiment}"

        mlflow.set_experiment(exp_name)
        self.experiment = mlflow.get_experiment_by_name(exp_name)
        self.experiment_name = exp_name

    def start_training_run(
        self,
        run_name: str,
        horizon: int,
        mode: str,
        data_stats: Dict[str, Any],
        hyperparams: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None,
    ):
        """Start a training run (backward compatible)."""
        dataset_stats = DatasetStats(
            rows=data_stats.get("rows", 0),
            symbols=data_stats.get("symbols", 0),
            features=data_stats.get("features", 0),
            date_start=str(data_stats.get("date_start", "")),
            date_end=str(data_stats.get("date_end", "")),
        )

        run_tags = tags or {}
        if hyperparams:
            for k, v in hyperparams.items():
                run_tags[f"hp_{k}"] = str(v)

        # Determine component from experiment key
        component = (
            self._experiment_key.split("-")[0]
            if "-" in self._experiment_key
            else self._experiment_key
        )

        self.active_run = mlflow.start_run(run_name=run_name)

        # Log all parameters
        params = {
            "horizon_days": horizon,
            "prediction_length": horizon,
            "training_mode": mode,
            "data_rows": dataset_stats.rows,
            "data_symbols": dataset_stats.symbols,
            "data_features": dataset_stats.features,
            "data_date_start": dataset_stats.date_start,
            "data_date_end": dataset_stats.date_end,
        }
        mlflow.log_params(params)

        for k, v in run_tags.items():
            mlflow.set_tag(k, v)

        logger.info(f"Started MLflow run: {run_name} (horizon={horizon}d, mode={mode})")
        return self.active_run

    def log_autogluon_results(
        self, predictor, training_time: float, eval_data: Optional[Any] = None
    ):
        """Log AutoGluon results (backward compatible)."""
        self.log_autogluon_model(predictor, training_time, eval_data, register=False)

    def log_custom_metric(self, key: str, value: float, step: Optional[int] = None):
        """Log custom metric (backward compatible)."""
        self.log_metric(key, value, step)

    def log_custom_param(self, key: str, value: Any):
        """Log custom param (backward compatible)."""
        self.log_param(key, value)

    def end_run(self, status: str = "FINISHED") -> Optional[str]:
        """End run (backward compatible)."""
        if self.active_run:
            mlflow.set_tag("ended_at", datetime.now(timezone.utc).isoformat())
            mlflow.end_run(status=status)
            run_id = self.active_run.info.run_id
            self.active_run = None
            logger.info(f"Ended MLflow run: {run_id} ({status})")
            return run_id
        return None


# =============================================================================
# CLI
# =============================================================================


def main():
    """Command-line interface for Quant ML Command Center."""
    import argparse

    parser = argparse.ArgumentParser(
        description="ZINC-FUSION Quant ML Command Center",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test connection
  python mlflow_tracking.py --test

  # Compare runs for core 5d horizon
  python mlflow_tracking.py --compare --component core --horizon 5

  # List registered models
  python mlflow_tracking.py --list-models

  # Show model history
  python mlflow_tracking.py --model-history zinc-fusion-core-h5d

  # Get champion model info
  python mlflow_tracking.py --champion zinc-fusion-core-h5d
""",
    )

    parser.add_argument(
        "--test", action="store_true", help="Test connection to MLflow server"
    )
    parser.add_argument("--compare", action="store_true", help="Compare recent runs")
    parser.add_argument(
        "--component", default="core", help="Component (core, specialist-*, ensemble)"
    )
    parser.add_argument("--horizon", type=int, help="Forecast horizon in days")
    parser.add_argument(
        "--list-models", action="store_true", help="List registered models"
    )
    parser.add_argument(
        "--model-history", type=str, help="Show version history for a model"
    )
    parser.add_argument("--champion", type=str, help="Get champion model info")
    parser.add_argument(
        "--n-runs", type=int, default=10, help="Number of runs to compare"
    )

    args = parser.parse_args()

    if args.test:
        print("Testing MLflow connection...")
        uri = get_tracking_uri()
        print(f"Tracking URI: {uri}")

        cmd = QuantMLCommandCenter()
        print(f"Command Center initialized successfully!")

        registry = ModelRegistry()
        models = registry.list_models()
        print(f"Registered models: {len(models)}")
        print("\nConnection test PASSED!")

    elif args.list_models:
        registry = ModelRegistry()
        models = registry.list_models()

        print("\n" + "=" * 80)
        print("REGISTERED MODELS")
        print("=" * 80)

        for m in models:
            champion = f"v{m['champion_version']}" if m["champion_version"] else "none"
            print(
                f"  {m['name']:<40} | latest: v{m['latest_version']} | champion: {champion}"
            )

        if not models:
            print("  No models registered yet.")

    elif args.model_history:
        registry = ModelRegistry()
        history = registry.get_model_history(args.model_history)

        print(f"\n{'=' * 80}")
        print(f"MODEL HISTORY: {args.model_history}")
        print("=" * 80)

        for v in history:
            stage = v["stage"]
            stage_str = f"[{stage}]" if stage != "None" else ""
            print(
                f"  v{v['version']:<4} {stage_str:<12} | run: {v['run_id'][:8]}... | {v.get('description', '')[:40]}"
            )

    elif args.champion:
        registry = ModelRegistry()
        champion = registry.get_champion(args.champion)

        if champion:
            print(f"\nChampion Model: {args.champion}")
            print(f"  Version: {champion.version}")
            print(f"  Stage: {champion.current_stage}")
            print(f"  Run ID: {champion.run_id}")
            print(f"  Created: {champion.creation_timestamp}")
        else:
            print(f"No champion found for {args.champion}")

    elif args.compare:
        cmd = QuantMLCommandCenter()
        runs = cmd.compare_runs(args.component, args.horizon, n_runs=args.n_runs)

        exp_name = cmd._get_experiment_name(args.component, args.horizon)
        print(f"\n{'=' * 90}")
        print(f"RECENT RUNS: {exp_name}")
        print("=" * 90)

        for r in runs:
            mase = f"{r.get('mase', 0):.4f}" if r.get("mase") else "N/A"
            time_min = (
                f"{r.get('training_minutes', 0):.1f}m"
                if r.get("training_minutes")
                else "?"
            )
            print(
                f"  {r['run_name']:<45} | MASE={mase:>8} | {time_min:>6} | {r.get('best_model', 'N/A')}"
            )

        if not runs:
            print("  No runs found.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
