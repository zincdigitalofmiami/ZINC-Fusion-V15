# Legacy Training Scripts

**Moved:** January 15, 2026  
**Reason:** Transition to SoT v2 architecture (52-model stack)

## What Was Moved

These scripts used the **unified table architecture** (`model.oof_predictions`) instead of the SoT v2 per-model tables (`training.oof_*_{H}d_1d`).

### Legacy Training Scripts
- `train_core_v15.py` - V15 core model (pre-SoT v2)
- `train_direction_v15.py` - Direction prediction model
- `train_core_poc.py` - Proof of concept
- `train_core_direction.py` - Directional training
- `train_core_tactical.py` - Tactical training (writes to model.oof_predictions)
- `train_core_chronos.py` - Chronos-2 strategic (writes to model.oof_predictions)
- `train_specialist.py` - Specialist training (unified features bug)
- `train_meta_ensemble.py` - Old ensemble approach

### Legacy Utilities
- `mlflow_command_center.py` - MLflow integration (rarely used)
- `mlflow_tracking.py` - MLflow helpers
- Backup files: `*.backup.*`

### Legacy Folders
- `v15_core_training/` - V15 training modules

## Key Differences: Legacy vs SoT v2

| Aspect | Legacy | SoT v2 |
|--------|--------|--------|
| **OOF Storage** | `model.oof_predictions` (1 table) | `training.oof_*_{H}d_1d` (48 tables) |
| **Quantiles** | p10, p50, p90 | **p30, p50, p70** + calibrated p10/p90 |
| **Specialist Field** | Column: `specialist` | **Table name** (oof_crush_5d_1d) |
| **Model Count** | Variable | **52 models** (48 L0 + 4 L1) |
| **Naming** | `zinc-fusion-*` | No version prefixes |

## Why Keep These?

- Reference for feature engineering logic
- Backup for AutoGluon configuration patterns
- Historical model performance baselines
- May contain useful data loading utilities

## Migration Notes

**DO NOT use these for production training.** They will conflict with SoT v2 table contracts.

If you need to reference code:
1. Copy specific functions to SoT v2 scripts
2. Update table targets and quantile levels
3. Test in isolation before deploying

---

**SoT v2 Implementation:** See `scripts/v2_training/` (when built)
