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
# # Full pipeline
# python -m fusion.core_training.run_pipeline
#
# # Start from specific phase
# python -m fusion.core_training.run_pipeline --start-phase 3
#
# # Train only tactical horizons
# python -m fusion.core_training.run_pipeline --horizons 5 21
# ```
#
# ## Pipeline Phases
#
# | Phase | Module | Description | Blocking |
# |-------|--------|-------------|----------|
# | 1 | phase1_options_features | Compute IV/Greeks from raw options | ✅ YES |
# | 2 | phase2_validate_gold_elite | Verify elite indicators | No |
# | 3 | phase3_build_core_matrix | Assemble ~213 features | No |
# | 4 | phase4_create_oof_schema | Define OOF table | No |
# | 5 | phase5_audit_preflight | Mandatory validation gate | ✅ YES |
# | 6 | phase6_train_core_seq | Train 5→21→63→126 | No |
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
# - `gold.options_features_1d` - IV/Greeks
# - `training.core_matrix_curated_1d` - Feature matrix
# - `training.oof_core_zl_1d` - OOF predictions
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
