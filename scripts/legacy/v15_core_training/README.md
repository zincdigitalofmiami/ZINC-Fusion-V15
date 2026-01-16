# Core Training with OOF Generation - V15 Enhanced

## What This Does

This enhanced training script implements **8-fold cross-validation** with **out-of-fold (OOF) prediction generation** for the Core model.

### Key Enhancements Over Original train_core_v15.py:

1. **8-Fold Cross-Validation**: Uses `TimeSeriesSplit` to create proper time-based folds
2. **OOF Predictions**: Generates predictions for validation sets across all folds
3. **Database Integration**: Saves OOF predictions to `model.oof_predictions` table
4. **Metrics Calculation**: Computes MASE, RMSE, MAE, MAPE and saves to `model.model_registry`
5. **get_oof_pred() Pattern**: Implements the required OOF generation pattern

## Usage

### Train Single Horizon (5-day)
```bash
cd /Volumes/Satechi\ Hub/ZINC-FUSION-V15
python scripts/v15_core_training/train_core_with_oof.py --horizon 5
```

### Train All Horizons
```bash
python scripts/v15_core_training/train_core_with_oof.py --horizon all
```

### Dry Run (Test Without Training)
```bash
python scripts/v15_core_training/train_core_with_oof.py --horizon 5 --dry-run
```

## What Gets Saved

### 1. OOF Predictions (`model.oof_predictions`)
```
specialist = 'core'
horizon = 5 (or 21, 63, 126)
as_of_date = validation date
pred_p10, pred_p50, pred_p90 = quantile predictions
actual = actual value
fold_id = 0-7 (8 folds)
model_version = 'v15-oof-YYYYMMDD'
```

**Expected Row Count Per Horizon:**
- Approximately `(dataset_size / 8) * 8 = dataset_size` predictions
- For 6,381 core features → ~6,381 OOF predictions

### 2. Model Registry (`model.model_registry`)
```
model_id = 'zinc-fusion-core-5d-oof' (or 21d, 63d, 126d)
model_type = 'core'
horizon = 5 (or 21, 63, 126)
status = 'trained'
mase, rmse, mae, mape = calculated metrics
best_model = 'TimeSeriesPredictor'
models_trained = 8 (one per fold)
artifact_path = 'models/core_v15/5d_oof'
```

### 3. Model Artifacts
```
models/core_v15/
├── 5d_oof/
│   ├── fold_0/
│   ├── fold_1/
│   ├── ...
│   └── fold_7/
├── 21d_oof/
│   └── ...
└── ...
```

## Architecture

### 8-Fold Time Series Cross-Validation

```
Fold 0: [Train=====================>][Val]
Fold 1: [Train=======================>][Val]
Fold 2: [Train=========================>][Val]
Fold 3: [Train===========================>][Val]
Fold 4: [Train=============================>][Val]
Fold 5: [Train================================>][Val]
Fold 6: [Train==================================>][Val]
Fold 7: [Train=====================================>][Val]
```

Each fold:
1. Trains on earlier data
2. Validates on later data
3. Generates predictions for validation set
4. Stores predictions with `fold_id`

### OOF Prediction Flow

```
Load Data → Prepare Time Series → Generate Folds
                                         ↓
For each fold:
    Train model on train_data
    Predict on validation_data
    Store predictions with fold_id
                                         ↓
Combine all fold predictions → Calculate Metrics → Save to DB
```

## Performance Expectations

### Training Time (per horizon, M4 Pro Mac)
- 5d (Tactical): ~15-20 minutes (8 folds × ~2 min/fold)
- 21d (Tactical): ~20-25 minutes
- 63d (Strategic): ~25-30 minutes
- 126d (Strategic): ~30-35 minutes

### Disk Space
- ~500MB per horizon (8 fold models)
- Total for all 4 horizons: ~2GB

## Verification After Training

### Check OOF Predictions
```sql
SELECT 
    horizon,
    COUNT(*) as predictions,
    COUNT(DISTINCT fold_id) as folds,
    MIN(as_of_date) as first_date,
    MAX(as_of_date) as last_date
FROM model.oof_predictions
WHERE specialist = 'core'
GROUP BY horizon;
```

**Expected:**
```
horizon | predictions | folds | first_date | last_date
--------|-------------|-------|------------|------------
5       | ~6381       | 8     | 2018-XX-XX | 2026-01-XX
21      | ~6381       | 8     | 2018-XX-XX | 2026-01-XX
63      | ~6381       | 8     | 2018-XX-XX | 2026-01-XX
126     | ~6381       | 8     | 2018-XX-XX | 2026-01-XX
```

### Check Model Registry
```sql
SELECT 
    model_id,
    horizon,
    status,
    mase,
    rmse,
    mae,
    mape,
    models_trained,
    trained_at
FROM model.model_registry
WHERE model_id LIKE '%oof%'
ORDER BY trained_at DESC;
```

**Expected:**
- 4 entries (one per horizon)
- All with `status = 'trained'`
- All with `models_trained = 8`
- Metrics (MASE, RMSE, MAE, MAPE) populated

## Next Steps After This Training

1. **Validate OOF Quality**: Check predictions make sense
2. **Train L1 Meta-Learner**: Use these OOF predictions as inputs
3. **Implement Refit Full**: Train on entire dataset for deployment
4. **Generate Live Forecasts**: Use refitted models for production

## Differences from Original train_core_v15.py

| Feature | Original | Enhanced |
|---------|----------|----------|
| Cross-Validation | num_val_windows (3-4) | 8-fold TimeSeriesSplit |
| OOF Generation | ❌ None | ✅ Full implementation |
| Database Save | ❌ None | ✅ Saves to oof_predictions |
| Metrics | ❌ Not calculated | ✅ MASE, RMSE, MAE, MAPE |
| Model Registry | ❌ Not updated | ✅ Full metadata saved |
| Fold Artifacts | ❌ One model | ✅ 8 models per horizon |

## Troubleshooting

### Out of Memory
- Reduce `page_size` in `execute_batch` from 1000 to 100
- Train horizons sequentially instead of all at once

### Training Too Slow
- Already using `hyperparameters="light"` for fast training
- Reduce `time_limit` from 300s to 180s per fold

### Predictions Look Wrong
- Check `ZL_close` is in core_features
- Verify timestamps are sorted correctly
- Inspect fold splits (should be time-based, not random)

## Contact

Created by Claude for ZINC-FUSION-V15 (January 2026)
