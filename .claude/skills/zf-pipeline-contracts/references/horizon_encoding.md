# Horizon Encoding

Single source of truth for time horizon representation in ZINC-Fusion-V15.

## The Rule

**Database: INTEGER only. UI/Display: String aliases allowed.**

## Canonical Mapping (Daily Grain)

| horizon_steps | Label | Trading Days | Calendar Approx |
|---------------|-------|--------------|-----------------|
| 5 | 1W | 5 | ~1 week |
| 21 | 1M | 21 | ~1 month |
| 63 | 3M | 63 | ~3 months |
| 126 | 6M | 126 | ~6 months |

## Hourly Grain

Hourly data (`_1h` tables) does NOT use `horizon_steps`. Hourly features are aggregated to daily before training.

```sql
-- Hourly tables have NO horizon_steps column
-- They use ts_event as the grain
SELECT ts_event, symbol, close FROM raw.market_futures_1h;

-- Features derived from hourly are stored at daily grain
SELECT as_of_date, realized_vol_1h FROM features.intraday_volatility;
```

## Storage Rules

### In DuckDB (fusion.db)

Always INTEGER for daily OOF/forecasts:

```sql
-- Correct
INSERT INTO training.oof_core_1d (as_of_date, horizon_steps, p10, p50, p90)
VALUES ('2025-01-15', 21, 0.02, 0.05, 0.08);

-- Wrong
INSERT INTO training.oof_core_1d (as_of_date, horizon_steps, p10, p50, p90)
VALUES ('2025-01-15', '1M', 0.02, 0.05, 0.08);  -- string not allowed
```

### In Python Code

Use integer constants from taxonomy:

```python
# Correct - from fusion.taxonomy
from fusion.taxonomy import HORIZON_STEPS

HORIZON_STEPS = {
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
}

for label, steps in HORIZON_STEPS.items():
    train_specialist(horizon_steps=steps)

# Wrong
HORIZONS = ['1w', '1m', '3m', '6m']  # strings cause drift
```

### In DataFrames

Column must be integer dtype:

```python
# Correct
df['horizon_steps'] = df['horizon_steps'].astype(int)

# Check before write
assert df['horizon_steps'].dtype in [np.int32, np.int64, int]
```

## Display Conversion

When displaying to users, convert to human-readable:

```python
HORIZON_LABELS = {
    5: '1W',
    21: '1M',
    63: '3M',
    126: '6M'
}

def format_horizon(steps: int) -> str:
    return HORIZON_LABELS.get(steps, f'{steps}d')
```

## Validation Query

Detect invalid horizon values:

```sql
SELECT DISTINCT horizon_steps
FROM training.oof_core_1d
WHERE horizon_steps NOT IN (5, 21, 63, 126);
```

If this returns rows, you have encoding drift.

## Common Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| `horizon = "5d"` | String instead of int | Use `horizon_steps = 5` |
| `horizon = "1w"` | Alias stored in DB | Convert to `5` before insert |
| `horizon = 7` | Calendar days not trading days | Use 5 (trading week) |
| Mixed types in column | Join failures | Cast to INTEGER |
| Adding hourly horizons | Not supported | Aggregate 1h → 1d first |

## AutoGluon Integration

When training with multiple horizons:

```python
from fusion.taxonomy import HORIZON_STEPS, TARGET_COLUMNS

for horizon_steps in HORIZON_STEPS.values():  # [5, 21, 63, 126]
    target_col = TARGET_COLUMNS[horizon_steps]  # 'target_return_5d', etc.
    
    predictor = TabularPredictor(
        label=target_col,
        problem_type='quantile',
        quantile_levels=[0.1, 0.5, 0.9],
    )
    
    # Store OOF with integer horizon
    oof_df['horizon_steps'] = horizon_steps  # integer, not string
```

## Join Safety

All L0 tables join on `(as_of_date, horizon_steps)`. Inconsistent encoding breaks the meta-ensemble:

```sql
-- This fails silently if horizon_steps types mismatch
SELECT *
FROM training.oof_core_1d c
JOIN training.oof_crush_1d r 
  ON c.as_of_date = r.as_of_date 
  AND c.horizon_steps = r.horizon_steps;
```

Always verify homogeneous types before joins.
