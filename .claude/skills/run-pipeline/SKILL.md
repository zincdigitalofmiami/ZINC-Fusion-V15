---
name: run-pipeline
description: Run ML training pipeline steps (specialists, core, evaluation, forecasts, monte-carlo). Use when user asks to run or re-run any part of the prediction pipeline.
disable-model-invocation: true
---

Run the ML pipeline step specified in $ARGUMENTS.

## Current State
- Branch: !`git branch --show-current`
- Venv: !`which python`

## Available Steps

| Step | Command | Description |
|------|---------|-------------|
| `specialists` | `python scripts/generate_specialist_signals.py` | Generate Big-11 specialist signals |
| `features` | `python scripts/generate_specialist_features.py` | Build specialist feature columns |
| `core` | `python -m fusion.core_training.run_pipeline` | Train 4 AutoGluon ensembles (5d/21d/63d/126d) |
| `evaluate` | `python scripts/evaluate_oof.py` | Evaluate OOF predictions vs actuals |
| `forecasts` | `python scripts/generate_production_forecasts.py` | Generate production forecast outputs |
| `monte-carlo` | `python scripts/autorun_monte_carlo.py` | Run L3 Monte Carlo simulation (10,000 runs) |
| `all` | Run all steps above in order | Full pipeline end-to-end |

## Pre-flight (MANDATORY before any step)

1. Confirm venv is active: `source .venv/bin/activate`
2. Set PYTHONPATH: `export PYTHONPATH=src:$PYTHONPATH`
3. Run `make check` — abort if it fails

## Rules (from AGENTS.md)

- **NEVER** modify `src/fusion/core_training/config.py` — it is FROZEN (2026-02-19)
- Core trains 4 independent TimeSeriesPredictor ensembles (one per horizon)
- Target = price level (`close.shift(-horizon)`), named `target_price_{h}d`
- Core metric = MAE (point forecast accuracy)
- 11 specialists (NEVER 10) — trump_effect is the 11th
- MODEL_ZOO_FROZEN has 19 active models — do not add/remove without approval

## Post-run

- Report exit code and any errors
- If `evaluate`, show the OOF summary table
- If `core`, confirm all 4 horizons completed with WeightedEnsemble
