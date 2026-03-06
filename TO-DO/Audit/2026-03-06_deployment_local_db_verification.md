# Deployment + Local/Cloud DB Verification (2026-03-06)

## Scope

Read-only verification of:

1. Vercel production deployment status for `zinc-fusion-v15`
2. Local DB identity/parity state
3. Cloud DB identity/parity state (via Vercel production env lookup)

## Git/Branch State

- Branch: `main`
- Commit: `c2afa31d0a51df645cc779667d70c123fa2adbf1`
- Sync: `main...origin/main` (in sync)

## Deployment Check

Deployment inspected from Vercel:

- Project: `zinc-fusion-v15`
- Deployment ID: `dpl_7QEYCVL5skL8rdBmufXRMBiHAHQt`
- Target: `production`
- Status: `Ready`
- URL: `https://zinc-fusion-v15-c4o784mx6-zincdigitalofmiamis-projects.vercel.app`
- Aliases:
  - `https://zinc-fusion-v15.vercel.app`
  - `https://zinc-fusion-v15-zincdigitalofmiamis-projects.vercel.app`
  - `https://zinc-fusion-v15-git-main-zincdigitalofmiamis-projects.vercel.app`

## Local DB Verification

Identity guards:

- `db_identity_guard.py --mode local`: **PASS**
  - endpoint: `localhost:5432/zinc_fusion_v15_local`
- `db_identity_guard.py --mode shadow`: **PASS**
  - endpoint: `localhost:5432/zinc_fusion_v15_shadow`

Parity check:

- `scripts/check_local_v15_parity.sql`: **PASS**

Row counts (local):

- `forecasts.production_1d`: `24`
- `training.matrix_1d`: `7,982`
- `training.specialist_signals_1d`: `85,411`
- `training.oof_core_1d`: `964`
- `training.model_runs_event`: `14`

Specialist coverage notice:

- `distinct_buckets = 11` (expected Big-11)

## Cloud DB Verification

Cloud DB URL was resolved from Vercel production environment (read-only pull in temporary directory, no repo env file writes).

Identity guard:

- `db_identity_guard.py --mode cloud`: **PASS**
  - endpoint: `db.prisma.io:5432/postgres`

Row counts (cloud):

- `forecasts.production_1d`: `24`
- `training.matrix_1d`: `7,982`
- `training.specialist_signals_1d`: `85,411`
- `training.oof_core_1d`: `964`
- `training.model_runs_event`: `0`

## Result

Overall verification: **PASS with one concrete parity mismatch**.

Confirmed mismatch:

- `training.model_runs_event`
  - local: `14`
  - cloud: `0`

This is the only observed divergence in the audited table set. All other audited counts match local vs cloud.
