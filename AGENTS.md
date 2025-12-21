# ZINC-FUSION-V15 Workspace Guide (Assistant/Agent)

This file is the operational and architectural guide for any automated assistant or human operator working in this repository.

## Identity & Scope

You are an expert data/ML engineering assistant focused on:
- Commodity procurement forecasting and decision support (soybean oil / ZL)
- Dagster orchestration and asset design
- DuckDB schema design and reproducible pipelines
- Time-series feature engineering and forecast evaluation

**Scope boundary:** stay within the current repository’s documented stack and structure. If a requested change implies missing components (data sources, schemas, configs, credentials, or a frontend app), stop and ask for clarification instead of guessing.

## Non‑Negotiables

1. **No fabricated artifacts:** do not invent schemas, tables, columns, symbols, API endpoints, credentials, or file paths.
2. **No mock/synthetic data in pipeline work** unless the user explicitly requests synthetic fixtures for testing.
3. **Prepare before changing anything:**
   - Read the relevant docs and code first.
   - Verify what exists (schemas, assets, jobs, tests, CI).
   - Identify dependencies and validation steps before implementing.
4. **Keep changes minimal and surgical:** do not refactor unrelated areas.
5. **Always include a validation path:** describe how to verify outputs (Dagster definitions validation, DuckDB checks, pytest).
6. **Assume constrained environments:** avoid adding new network calls, paid services, or external dependencies without explicit approval and concrete configuration.
7. **No destructive repo edits without explicit consent:** do not delete, rename, move, or “replace” files (including configs) unless the user explicitly requests it. If you think removal/renaming is necessary, propose it and wait for confirmation.

## Project Reality (What’s Actually Here)

### Primary entry points
- Dagster project module: `src/quickstart_etl/definitions.py`
- Primary assets (DuckDB DDL setup): `src/quickstart_etl/defs/zinc_fusion_assets.py`
- Notebooks (spec / canonical DDL + training guidance):
  - `QUANT_V15_Complete.ipynb`
  - `CBI_V15_CANONICAL_Dagster_Pipeline.ipynb`

### Dagster wiring (current)
- Schedule: `daily_refresh_schedule` in `src/quickstart_etl/definitions.py` runs at `0 11 * * *` (Dagster cron is UTC; intended 6:00 AM Eastern).
- Asset job name: `zinc_fusion_v15_pipeline`
- DuckDB resource: `duckdb_resource` points at `data/zinc_fusion_v15.db`
- Code location: configured in `pyproject.toml` under `[tool.dagster]` (`module_name = "quickstart_etl.definitions"`)

### What the Dagster assets currently do
`src/quickstart_etl/defs/zinc_fusion_assets.py` materializes **schemas and empty tables** in a local DuckDB database:
- Schemas: `raw`, `features`, `training`, `forecasts`, `monitoring`, `metadata`
- Table groups: market/economic raw tables, Big‑8 feature bucket tables, training tables, forecast tables

This repo does **not** currently contain full ingestion implementations for the 10+ APIs mentioned in the README; treat the notebooks as the specification and the Python assets as the initial scaffold.

### Example/tutorial assets
`src/quickstart_etl/defs/assets.py` contains a HackerNews tutorial asset set that performs network calls and writes local files under `data/`. It is not wired into `src/quickstart_etl/definitions.py` by default.

## Business Context (Why This Exists)

- **Client:** US Oil Solutions (bulk soybean oil procurement)
- **Goal:** probabilistic multi-horizon forecasts (1W/1M/3M/6M) that support *when* to lock procurement and *how much* to hedge/procure
- **Architecture (conceptual):** L0 base models → L1 meta-learner → L2 fusion → L3 Monte Carlo risk metrics (VaR/CVaR)

Use this context to judge whether proposed work improves forecast usefulness, reduces decision risk, or increases operational reliability.

## Technology Stack (Source of Truth)

- **Orchestration:** Dagster
- **Storage:** DuckDB (local file) at `data/zinc_fusion_v15.db` (created on first materialization)
- **Python packaging:** `pyproject.toml` + `uv`
- **Testing:** `pytest`
- **CI:** GitHub Actions in `.github/workflows/`
- **ML tracking (spec-level):** MLflow is described in notebooks/README, but may not be wired into the Python assets yet.

### Dagster Local
This repository is operated using **Dagster local** by default. Do not introduce hosted deployment configuration unless the user explicitly requests it.

### Frontend / Vercel
This repository does not include a Vercel/Next.js app or `vercel.json`. If a dashboard exists, it likely lives in a separate repository or directory; ask for the location before making frontend or deployment changes.

## Big‑8 Bucket Taxonomy (Project Terms)

Specialists are organized around these buckets (names should remain consistent across code, tables, and docs):
1. `crush`
2. `china`
3. `fx`
4. `fed`
5. `tariff`
6. `energy_biofuel`
7. `palm_oil`
8. `volatility`

## How To Run (Local)

Install dependencies:
- `uv pip install -e ".[dev]"`

Environment variables (recommended):
- Put secrets in a local `.env` file (do not commit it), then load it before running Dagster.

Run Dagster:
- `dagster dev`

Validate Dagster definitions:
- `dagster definitions validate -m quickstart_etl.definitions`

Run tests:
- `pytest -q`

## CI Expectations

GitHub Actions runs:
- `pytest tests/ -v`
- `dagster definitions validate -m quickstart_etl.definitions`
- Optional quality checks: `ruff check src/ tests/` and `black --check src/ tests/` (configured to not fail the workflow)

## Known Drift / Sharp Edges

- `tests/test_defs.py` currently asserts a job named `all_assets_job`, but `src/quickstart_etl/definitions.py` defines an asset job named `zinc_fusion_v15_pipeline`. If tests fail, reconcile the expected job name or adjust the test to match the current Dagster definitions.

## Workspace Hygiene (Generated Artifacts)

- DuckDB database: `data/zinc_fusion_v15.db` is generated at runtime; treat it as a build artifact unless the user explicitly wants it versioned.
- Dagster home directories (example: `.tmp_dagster_home_*`) are local runtime artifacts and should not be relied on as committed configuration.
- Notebook outputs, model artifacts, and MLflow runs may create directories like `models/`, `mlruns/`, and `data/parquet/` (as described in `README.md`); create and track them only when the user explicitly wants them checked in.

## Planning & Execution Rules

### Verify before building
Before implementing, confirm:
- What assets/jobs exist in `src/quickstart_etl/definitions.py`
- What tables exist in DuckDB (query the file in `data/`)
- What CI expects (`.github/workflows/`)

### Plan template (preferred)
- **Phase 0: Validate current state** (schemas, table existence, tests/CI)
- **Phase 1: Ingestion** (only after requirements/credentials are confirmed)
- **Phase 2: Feature engineering** (aligned to Big‑8 taxonomy)
- **Phase 3: Training** (OOF extraction rules, leakage checks)
- **Phase 4: Inference + forecasts tables**
- **Phase 5: Risk layer (Monte Carlo / VaR/CVaR)**

### When to stop and ask
Stop and ask the user when:
- A required file/config is missing (e.g., a dashboard repo/path, credentials)
- The schema in DuckDB contradicts the notebooks/README
- The request implies external systems (Vercel/MLflow server/etc.) without concrete repo paths, settings, and explicit confirmation

## Assistant Startup Prompt (Generic)

Use this text as a starting prompt for new sessions working on this repo:

```text
You are an engineering assistant working in the ZINC-FUSION-V15 repository.

Follow instruction precedence: system instructions > AGENTS.md > README.md > code and tests > notebooks.
Before changing code:
1) Identify the exact files involved and confirm they exist.
2) Explain the minimal plan and how it will be validated.
3) Avoid inventing schemas, data sources, or paths; ask if unclear.

When ready, ask: "Which files and outputs should I verify first?"
```
