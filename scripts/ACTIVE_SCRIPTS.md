# Active Training Scripts (SoT v2)

**Updated:** January 15, 2026  
**Status:** ⚠️ **SoT v2 Implementation Pending**

## Current State

### ✅ Active (Keep Using)
- `populate_core_matrix.py` - Builds training matrix with targets
- `generate_specialist_features.py` - Feature generation for 11 specialists
- `validate_db_state.py` - Pre-training validation
- `register_models.py` - Model registry management

### Core Training Policy (CPU-only, Full Model Zoo)

Core runs **CPU-only** (no MPS, no CUDA). Set guards **before** importing torch/autogluon:

```
TOKENIZERS_PARALLELISM=false
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
AUTOGLUON_DISABLE_RAY=1
PYTORCH_ENABLE_MPS_FALLBACK=1
device = "cpu"
```

Core must try **ALL** AutoGluon-TimeSeries Model Zoo models via an explicit
`hyperparameters={...}` allowlist (model names may omit the “Model” suffix).
The full allowlist is maintained in `Docs/CORE_TRAINING_SPEC_LOCKED.md`.

AutoGluon trains the full allowlist, ranks models on validation/backtests, and
typically selects a **WeightedEnsemble** as best. No time limits are used.

Verification:
- `python -m fusion.core_training.run_pipeline --skip-matrix --horizons 5`
- `python -m fusion.core_training.run_pipeline --skip-matrix`
- Confirm logs show the full allowlist and a WeightedEnsemble selection

### 🏗️ SoT v2 (To Be Built)
**Location:** `scripts/v2_training/`

**Required Scripts (Core + Specialists + Meta):**
- `python -m fusion.core_training.run_pipeline` - L0 core (CPU-only, full Model Zoo allowlist)
- `train_l0_specialist.py` - Specialist signal generators (11 buckets, no horizons)
- `train_l1_meta.py` - L1 meta ensemble (4 horizons = 4 models)

**Output Tables:**
- `training.oof_core_1d` (single table with `horizon_days`)
- `training.specialist_signals_1d` (signal_1/signal_2/confidence)
- `training.meta_inputs_1d` (single table with `horizon_days`)
- `forecasts.production_{5d|21d|63d|126d}_1d` (4 tables)

**Quantile Contract:**
- Core output: `p30`, `p50`, `p70`
- Calibrated envelope: `p10_cal`, `p90_cal` (added by L2 calibration)

### 🗄️ Legacy (Moved)
**Location:** `scripts/legacy/`

See `scripts/legacy/README.md` for details on what was moved and why.

---

## Next Steps

1. **Verify table schemas:**
   ```bash
   python scripts/validate_db_state.py
   ```

2. **Build SoT v2 training scripts** that write to proper tables

3. **Train L0 models** (Core + 11 specialist signal generators)

4. **Train L1 meta** (4 models: one per horizon)

5. **Run L2 calibration** (conformal quantile regression for p10_cal/p90_cal)
