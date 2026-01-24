# Core Training Package v1.0
# ===========================
#
# Self-contained training pipeline for Core (L0) models in SoT v2.
#
# This package is ISOLATED from legacy training scripts. Everything
# needed for Core training is contained here with locked configurations.
#
# ## Usage
#
# ```bash
# # Full pipeline (rebuild matrix + train)
# python -m fusion.core_training.run_pipeline
#
# # Train only (use existing matrix)
# python -m fusion.core_training.run_pipeline --skip-matrix
#
# # Train only tactical horizons
# python -m fusion.core_training.run_pipeline --horizons 5 21
# ```
#
# ## Pipeline Modules
#
# | Module | Description |
# |--------|-------------|
# | build_matrix | Assemble ~213 features into training.matrix_1d |
# | train_models | Train AutoGluon models for horizons 5→21→63→126 |
#
# ## Locked Configurations
#
# All configurations are centralized in `config.py`:
# - TARGET_SYMBOL = "ZL"
# - HORIZONS = [5, 21, 63, 126]
# - QUANTILES = [0.3, 0.5, 0.7]
# - Feature guardrails: 120-350 (target ~213)
# - All features as OBSERVED covariates
# - Z-score normalization
#
# ## Output Tables
#
# - `training.matrix_1d` - Feature matrix
# - `training.oof_core_1d` - OOF predictions
#
# ## Model Artifacts
#
# Models saved to `models/core_v1/{horizon}d/`

__version__ = "1.0.0"
__author__ = "ZINC-FUSION"
__locked_date__ = "2026-01-15"

from .config import (
    TARGET_SYMBOL,
    HORIZONS,
    QUANTILES,
    OptionsConfig,
    FeatureMatrixConfig,
    TrainingConfig,
    OOF_COLUMNS,
    L1_CONTRACT,
)

__all__ = [
    "TARGET_SYMBOL",
    "HORIZONS",
    "QUANTILES",
    "OptionsConfig",
    "FeatureMatrixConfig",
    "TrainingConfig",
    "OOF_COLUMNS",
    "L1_CONTRACT",
]
