"""
MLflow Model Registry - ZINC Fusion V15
=========================================
Production-grade model registry with full tracking for all Big-10 specialists.

This module creates and manages MLflow experiments and registered models for:
- Each Big-10 specialist bucket (Crush, China, FX, Fed, Tariff, Energy, Biofuel, Palm, Volatility, Weather)
- Meta-learner ensemble models (L1, L2)
- Risk engine models (L3)
- Complete lineage tracking from data → features → training → model → forecasts
"""

import mlflow
from mlflow.tracking import MlflowClient
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
import json
import pickle
from pathlib import Path


# MLflow Configuration
MLFLOW_TRACKING_URI = "file:///Volumes/Satechi Hub/ZINC-FUSION-V15/mlruns"
MLFLOW_REGISTRY_URI = "file:///Volumes/Satechi Hub/ZINC-FUSION-V15/mlruns"


class ZincFusionModelRegistry:
    """
    Production MLflow Model Registry for ZINC-FUSION-V15

    Manages all Big-10 specialist models, meta-learners, and risk models
    with complete experiment tracking and model versioning.
    """

    # Big-10 Bucket Definitions
    BIG10_BUCKETS = {
        "crush": {
            "name": "Crush Specialist",
            "description": "Soybean crush margin forecasting and processing economics",
            "emoji": "🌾",
            "features": ["crush_margin", "capacity_utilization", "processing_spread"],
            "horizons": ["1W", "1M", "3M", "6M"],
            "data_sources": ["ZL", "ZS", "ZM", "crush_capacity"],
        },
        "china": {
            "name": "China Specialist",
            "description": "Chinese demand dynamics and import policy forecasting",
            "emoji": "🇨🇳",
            "features": ["import_demand", "domestic_production", "policy_indicators"],
            "horizons": ["1W", "1M", "3M", "6M"],
            "data_sources": ["china_imports", "cny_rates", "domestic_crush"],
        },
        "fx": {
            "name": "FX Specialist",
            "description": "Currency impact modeling on commodity pricing and flows",
            "emoji": "💱",
            "features": ["usd_index", "brl_usd", "cny_usd", "eur_usd"],
            "horizons": ["1W", "1M", "3M", "6M"],
            "data_sources": ["DX", "USDBRL", "USDCNY", "EURUSD"],
        },
        "fed": {
            "name": "Fed Specialist",
            "description": "Federal Reserve policy impacts on commodity markets",
            "emoji": "🏦",
            "features": ["fed_funds_rate", "yield_curve", "qe_balance"],
            "horizons": ["1W", "1M", "3M", "6M"],
            "data_sources": ["DFF", "DGS10", "WALCL"],
        },
        "tariff": {
            "name": "Tariff Specialist",
            "description": "Trade policy and tariff impacts on agricultural flows",
            "emoji": "🛡️",
            "features": ["tariff_rates", "trade_flows", "policy_regime"],
            "horizons": ["1W", "1M", "3M", "6M"],
            "data_sources": ["usda_exports", "tariff_schedules", "trade_policy"],
        },
        "energy": {
            "name": "Energy Specialist",
            "description": "Energy price impacts on agricultural production",
            "emoji": "⚡",
            "features": ["crude_oil", "natural_gas", "diesel_prices"],
            "horizons": ["1W", "1M", "3M", "6M"],
            "data_sources": ["CL", "NG", "HO", "RB"],
        },
        "biofuel": {
            "name": "Biofuel Specialist",
            "description": "Biofuel demand and regulatory impacts on oilseed demand",
            "emoji": "🌽",
            "features": ["biodiesel_demand", "rin_prices", "rfs_mandates"],
            "horizons": ["1W", "1M", "3M", "6M"],
            "data_sources": ["eia_biofuels", "epa_rin", "rfs_volumes"],
        },
        "palm": {
            "name": "Palm Specialist",
            "description": "Palm oil competition and substitution dynamics",
            "emoji": "🌴",
            "features": ["palm_price_spread", "production_cycles", "export_policy"],
            "horizons": ["1W", "1M", "3M", "6M"],
            "data_sources": ["CPO", "palm_exports", "indonesia_policy"],
        },
        "volatility": {
            "name": "Volatility Specialist",
            "description": "Market structure and volatility regime modeling",
            "emoji": "📊",
            "features": ["realized_vol", "implied_vol", "vol_regime", "liquidity"],
            "horizons": ["1D", "1W", "1M", "3M"],
            "data_sources": ["intraday_data", "options_data", "order_book"],
        },
        "weather": {
            "name": "Weather Specialist",
            "description": "Agricultural weather impacts and production forecasting",
            "emoji": "🌦️",
            "features": ["precipitation", "temperature", "drought_index", "gdd"],
            "horizons": ["7D", "14D", "1M", "Season"],
            "data_sources": ["noaa", "open_meteo", "crop_conditions"],
        },
    }

    # Model Architecture Phases
    MODEL_PHASES = {
        "L0_specialist": {
            "name": "L0 - Specialist Models",
            "description": "Base specialist models for each Big-10 bucket",
            "model_types": ["XGBoost", "LightGBM", "CatBoost", "ElasticNet"],
        },
        "L1_meta": {
            "name": "L1 - Meta-Learner",
            "description": "Ensemble meta-learner combining specialist outputs",
            "model_types": ["Stacking", "Blending", "BayesianAveraging"],
        },
        "L2_fusion": {
            "name": "L2 - Fusion Engine",
            "description": "Final forecast fusion with uncertainty quantification",
            "model_types": ["QuantileRegression", "ConformalPrediction", "BayesianNN"],
        },
        "L3_risk": {
            "name": "L3 - Risk Engine",
            "description": "Monte Carlo simulation and VaR/CVaR calculation",
            "model_types": ["MonteCarlo", "CopulaSimulation", "HistoricalBootstrap"],
        },
    }

    def __init__(self, tracking_uri: str = MLFLOW_TRACKING_URI):
        """Initialize MLflow Model Registry"""
        self.tracking_uri = tracking_uri
        mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient(tracking_uri=tracking_uri)

        # Initialize experiments directory
        os.makedirs(tracking_uri.replace("file://", ""), exist_ok=True)

    def setup_experiments(self) -> Dict[str, str]:
        """Create MLflow experiments for all buckets and phases"""

        experiments = {}

        # Create master experiment
        master_exp = self._create_experiment(
            "zinc-fusion-v15-master",
            "Master experiment for ZINC-FUSION-V15 forecasting system",
        )
        experiments["master"] = master_exp

        # Create experiments for each Big-10 bucket
        for bucket_id, bucket_info in self.BIG10_BUCKETS.items():
            exp_name = f"zinc-{bucket_id}-specialist"
            exp_id = self._create_experiment(
                exp_name,
                f"{bucket_info['emoji']} {bucket_info['name']}: {bucket_info['description']}",
            )
            experiments[bucket_id] = exp_id

        # Create experiments for model phases
        for phase_id, phase_info in self.MODEL_PHASES.items():
            exp_name = f"zinc-{phase_id}"
            exp_id = self._create_experiment(
                exp_name, f"{phase_info['name']}: {phase_info['description']}"
            )
            experiments[phase_id] = exp_id

        return experiments

    def _create_experiment(self, name: str, description: str) -> str:
        """Create or get MLflow experiment"""
        try:
            experiment = mlflow.get_experiment_by_name(name)
            if experiment:
                return experiment.experiment_id
            else:
                return mlflow.create_experiment(
                    name,
                    tags={"description": description, "project": "zinc-fusion-v15"},
                )
        except Exception as e:
            # Experiment already exists, get it
            experiment = mlflow.get_experiment_by_name(name)
            return experiment.experiment_id if experiment else None

    def register_specialist_model(
        self,
        bucket_id: str,
        model_name: str,
        model_type: str,
        metrics: Dict[str, float],
        params: Dict[str, Any],
        artifacts: Optional[Dict[str, str]] = None,
        model_object: Optional[Any] = None,
    ) -> str:
        """
        Register a specialist model for a Big-10 bucket

        Args:
            bucket_id: One of the Big-10 bucket identifiers
            model_name: Name of the model
            model_type: Type of model (XGBoost, LightGBM, etc.)
            metrics: Model performance metrics
            params: Model hyperparameters
            artifacts: Optional dict of artifact paths
            model_object: Optional sklearn-compatible model object

        Returns:
            Run ID of the registered model
        """

        if bucket_id not in self.BIG10_BUCKETS:
            raise ValueError(
                f"Unknown bucket: {bucket_id}. Must be one of {list(self.BIG10_BUCKETS.keys())}"
            )

        bucket_info = self.BIG10_BUCKETS[bucket_id]
        experiment_name = f"zinc-{bucket_id}-specialist"

        mlflow.set_experiment(experiment_name)

        with mlflow.start_run(run_name=f"{bucket_info['emoji']} {model_name}") as run:
            # Log parameters
            mlflow.log_params(params)
            mlflow.log_param("bucket", bucket_id)
            mlflow.log_param("model_type", model_type)
            mlflow.log_param("specialist_name", bucket_info["name"])

            # Log metrics
            mlflow.log_metrics(metrics)

            # Log tags
            mlflow.set_tags(
                {
                    "bucket": bucket_id,
                    "model_phase": "L0_specialist",
                    "model_type": model_type,
                    "specialist": bucket_info["name"],
                    "emoji": bucket_info["emoji"],
                    "horizons": ",".join(bucket_info["horizons"]),
                    "data_sources": ",".join(bucket_info["data_sources"]),
                }
            )

            # Log model if provided
            if model_object is not None:
                try:
                    mlflow.sklearn.log_model(
                        model_object,
                        artifact_path="model",
                        registered_model_name=f"zinc_{bucket_id}_specialist",
                    )
                except:
                    # Fallback to pickle
                    model_path = f"/tmp/model_{bucket_id}.pkl"
                    with open(model_path, "wb") as f:
                        pickle.dump(model_object, f)
                    mlflow.log_artifact(model_path, "model")

            # Log additional artifacts
            if artifacts:
                for name, path in artifacts.items():
                    if os.path.exists(path):
                        mlflow.log_artifact(path, name)

            return run.info.run_id

    def register_meta_learner(
        self,
        phase: str,
        model_name: str,
        specialist_inputs: List[str],
        metrics: Dict[str, float],
        params: Dict[str, Any],
    ) -> str:
        """Register a meta-learner or fusion model"""

        if phase not in self.MODEL_PHASES:
            raise ValueError(f"Unknown phase: {phase}")

        phase_info = self.MODEL_PHASES[phase]
        experiment_name = f"zinc-{phase}"

        mlflow.set_experiment(experiment_name)

        with mlflow.start_run(run_name=f"🧠 {model_name}") as run:
            mlflow.log_params(params)
            mlflow.log_param("phase", phase)
            mlflow.log_param("specialist_inputs", ",".join(specialist_inputs))

            mlflow.log_metrics(metrics)

            mlflow.set_tags(
                {
                    "model_phase": phase,
                    "phase_name": phase_info["name"],
                    "specialist_inputs": ",".join(specialist_inputs),
                }
            )

            return run.info.run_id

    def get_bucket_models(self, bucket_id: str) -> List[Dict[str, Any]]:
        """Get all registered models for a bucket"""

        experiment_name = f"zinc-{bucket_id}-specialist"
        experiment = mlflow.get_experiment_by_name(experiment_name)

        if not experiment:
            return []

        runs = mlflow.search_runs(
            experiment_ids=[experiment.experiment_id], order_by=["metrics.rmse ASC"]
        )

        return runs.to_dict("records") if not runs.empty else []

    def get_production_models(self) -> Dict[str, Dict[str, Any]]:
        """Get the best model for each bucket (production candidates)"""

        production_models = {}

        for bucket_id in self.BIG10_BUCKETS.keys():
            models = self.get_bucket_models(bucket_id)
            if models:
                # Get best model by RMSE
                production_models[bucket_id] = models[0]

        return production_models

    def get_model_lineage(self, bucket_id: str) -> Dict[str, Any]:
        """Get full lineage for a bucket's models"""

        bucket_info = self.BIG10_BUCKETS.get(bucket_id, {})

        return {
            "bucket": bucket_id,
            "specialist_name": bucket_info.get("name", "Unknown"),
            "emoji": bucket_info.get("emoji", ""),
            "lineage": {
                "data_sources": bucket_info.get("data_sources", []),
                "features": bucket_info.get("features", []),
                "training_phase": "L0_specialist",
                "meta_phase": "L1_meta",
                "fusion_phase": "L2_fusion",
                "risk_phase": "L3_risk",
            },
            "horizons": bucket_info.get("horizons", []),
        }


def initialize_mlflow_registry():
    """Initialize the MLflow registry with experiments and sample models"""

    print("🚀 Initializing ZINC-FUSION-V15 MLflow Model Registry...")

    registry = ZincFusionModelRegistry()

    # Setup experiments
    experiments = registry.setup_experiments()
    print(f"✅ Created {len(experiments)} MLflow experiments")

    # Register sample models for each bucket
    for bucket_id, bucket_info in registry.BIG10_BUCKETS.items():
        print(f"  {bucket_info['emoji']} Registering {bucket_info['name']} models...")

        # Register XGBoost model
        registry.register_specialist_model(
            bucket_id=bucket_id,
            model_name=f"{bucket_info['name']} XGBoost v1",
            model_type="XGBoost",
            metrics={
                "rmse": 0.045 + (hash(bucket_id) % 10) * 0.002,
                "mae": 0.032 + (hash(bucket_id) % 10) * 0.001,
                "r2": 0.85 + (hash(bucket_id) % 10) * 0.01,
                "mape": 3.2 + (hash(bucket_id) % 10) * 0.1,
                "directional_accuracy": 0.68 + (hash(bucket_id) % 10) * 0.01,
            },
            params={
                "n_estimators": 500,
                "max_depth": 6,
                "learning_rate": 0.05,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "horizon": "1M",
                "feature_count": len(bucket_info["features"]) * 10,
            },
        )

        # Register LightGBM model
        registry.register_specialist_model(
            bucket_id=bucket_id,
            model_name=f"{bucket_info['name']} LightGBM v1",
            model_type="LightGBM",
            metrics={
                "rmse": 0.043 + (hash(bucket_id) % 10) * 0.002,
                "mae": 0.030 + (hash(bucket_id) % 10) * 0.001,
                "r2": 0.86 + (hash(bucket_id) % 10) * 0.01,
                "mape": 3.0 + (hash(bucket_id) % 10) * 0.1,
                "directional_accuracy": 0.70 + (hash(bucket_id) % 10) * 0.01,
            },
            params={
                "n_estimators": 600,
                "num_leaves": 31,
                "learning_rate": 0.03,
                "feature_fraction": 0.8,
                "bagging_fraction": 0.8,
                "horizon": "1M",
                "feature_count": len(bucket_info["features"]) * 10,
            },
        )

    # Register meta-learner models
    print("  🧠 Registering Meta-Learner models...")
    registry.register_meta_learner(
        phase="L1_meta",
        model_name="Stacking Ensemble v1",
        specialist_inputs=list(registry.BIG10_BUCKETS.keys()),
        metrics={"rmse": 0.038, "mae": 0.026, "r2": 0.89, "ensemble_improvement": 0.12},
        params={"base_learners": 10, "meta_model": "Ridge", "cv_folds": 5},
    )

    registry.register_meta_learner(
        phase="L2_fusion",
        model_name="Quantile Fusion v1",
        specialist_inputs=["L1_meta"],
        metrics={"coverage_90": 0.91, "interval_width": 0.082, "pinball_loss": 0.023},
        params={
            "quantiles": [0.05, 0.25, 0.5, 0.75, 0.95],
            "model_type": "QuantileRegression",
        },
    )

    registry.register_meta_learner(
        phase="L3_risk",
        model_name="Monte Carlo Risk Engine v1",
        specialist_inputs=["L2_fusion"],
        metrics={
            "var_95_accuracy": 0.94,
            "cvar_accuracy": 0.92,
            "backtest_exceedances": 0.048,
        },
        params={
            "simulations": 10000,
            "confidence_levels": [0.95, 0.99],
            "risk_metrics": ["VaR", "CVaR", "MaxDrawdown"],
        },
    )

    print("✅ MLflow Model Registry initialized successfully!")
    print(f"📊 View at: mlflow ui --backend-store-uri {MLFLOW_TRACKING_URI}")

    return registry


if __name__ == "__main__":
    initialize_mlflow_registry()
