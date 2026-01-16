# Active Training Scripts (SoT v2)

**Updated:** January 15, 2026  
**Status:** ⚠️ **SoT v2 Implementation Pending**

## Current State

### ✅ Active (Keep Using)
- `populate_core_matrix.py` - Builds training matrix with targets
- `generate_specialist_features.py` - Feature generation for 11 specialists
- `pretrain_readiness_audit.py` - Pre-training validation
- `register_models.py` - Model registry management

### 🏗️ SoT v2 (To Be Built)
**Location:** `scripts/v2_training/`

**Required Scripts (52 models):**
- `train_l0_core.py` - L0 core base model (4 horizons = 4 models)
- `train_l0_specialist_crush.py` - Crush specialist (4 horizons = 4 models)
- `train_l0_specialist_china.py` - China specialist (4 horizons = 4 models)
- ... [9 more specialist scripts]
- `train_l1_meta.py` - L1 meta ensemble (4 horizons = 4 models)

**Output Tables:**
- `training.oof_core_{5d|21d|63d|126d}_1d` (4 tables)
- `training.oof_{bucket}_{5d|21d|63d|126d}_1d` (44 tables: 11 specialists × 4 horizons)
- `training.meta_inputs_{5d|21d|63d|126d}_1d` (4 tables)
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
   python scripts/pretrain_readiness_audit.py --strict
   ```

2. **Build SoT v2 training scripts** that write to proper tables

3. **Train L0 models** (48 models: 1 core + 11 specialists × 4 horizons each)

4. **Train L1 meta** (4 models: one per horizon)

5. **Run L2 calibration** (conformal quantile regression for p10_cal/p90_cal)
