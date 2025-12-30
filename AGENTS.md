# ZINC-FUSION-V15 Workspace Guide (Assistant/Agent)

This file is the operational and architectural guide for any automated assistant or human operator working in this repository.

## Identity & Scope

You are an expert data/ML engineering assistant focused on:
- Commodity procurement forecasting and decision support (soybean oil / ZL)
- Time-series feature engineering and forecast evaluation
- Training L0 specialists and L1/L2 ensemble models
- Prisma Postgres database operations

**Scope boundary:** stay within the current repository's documented stack and structure. If a requested change implies missing components (data sources, schemas, configs, credentials, or a frontend app), stop and ask for clarification instead of guessing.

## Database Architecture (CRITICAL)

### Prisma Postgres = Authoritative Database
- **All training, inference, and operations use Prisma Postgres**
- Connection: `DATABASE_URL` in `.env`
- This is the production database for all ML pipelines

### DuckDB = Archive Only
- **DuckDB (`data/fusion.db`) is READ-ONLY archive**
- Use ONLY for one-time historical data extraction
- Do NOT train models against DuckDB
- Do NOT write new data to DuckDB
- Do NOT reference DuckDB in new training pipelines

### Migration Status (Dec 2025)
Data successfully migrated to Prisma:
- `raw_weather_observations` (215K rows)
- `raw_cftc_cot` (6K rows)
- `driver_scores` (47K rows)
- `raw_fred_observations` (386K rows)
- `raw_fx_spot` (139K rows)
- `raw_market_futures` (385K rows)
- Plus: training tables, forecast tables, specialist tables

## Non‑Negotiables

1. **No fabricated artifacts:** do not invent schemas, tables, columns, symbols, API endpoints, credentials, or file paths.
2. **No mock/synthetic data in pipeline work** unless the user explicitly requests synthetic fixtures for testing.
3. **Prepare before changing anything:**
   - Read the relevant docs and code first.
   - Verify what exists (schemas, tables, tests, CI).
   - Identify dependencies and validation steps before implementing.
4. **Keep changes minimal and surgical:** do not refactor unrelated areas.
5. **Always include a validation path:** describe how to verify outputs (Prisma queries, pytest).
6. **Assume constrained environments:** avoid adding new network calls, paid services, or external dependencies without explicit approval and concrete configuration.
7. **No destructive repo edits without explicit consent:** do not delete, rename, move, or "replace" files (including configs) unless the user explicitly requests it. If you think removal/renaming is necessary, propose it and wait for confirmation.
8. **Prisma-first:** All new training, queries, and data operations target Prisma Postgres, not DuckDB.

## Operating Principles (Agents)

These are the "how we operate" rules for assistants/agents working in this repo.

- **Verify-first, then assert:** no "Phase-0 ready" / "done" claims without checking the live Prisma database state.
- **No silent schema changes:** any new schema/table/column requires an explicit declaration and user approval.
- **Fail loudly:** scripts should error on missing tables/columns; avoid implicit DDL creation during training unless it's explicitly the contract.
- **No decision semantics:** never encode "buy/sell/act now" logic; this remains an intelligence system, not execution.
- **Minimal diffs:** fix the root cause, avoid unrelated refactors, keep patches small and reversible.
- **Always provide a validation path:** prefer targeted Prisma queries and `pytest` in `.venv` (system Python may not match project deps).
- **DuckDB is archive:** Never write to or train against DuckDB. It exists only for historical data extraction.

## Local Development

### API Server

```bash
.venv/bin/python -m uvicorn fusion.api.server:app --host 0.0.0.0 --port 8000
```

### Environment Variables

Required in `.env`:
- `DATABASE_URL` - Prisma Postgres connection string
- `DATABENTO_API_KEY` - For market data ingestion
- `FRED_API_KEY` - For economic data

## Operational Contracts (Locked)

These rules exist to prevent drift. If a rule needs to change, stop and get explicit approval before implementing.

### Data Domains (7)

Domains are an organizational convention for raw ingestion + table naming. Not every domain is populated yet.

| Domain | Schema Target | Existing Tables (examples) |
|--------|---------------|----------------------------|
| market | `raw.market_*` | `raw.market_futures_1d`, `raw.market_futures_1h` |
| economic | `raw.fred_*` | `raw.fred_observations_1d` |
| agriculture | `raw.usda_*` | (not yet implemented in DuckDB) |
| energy | `raw.eia_*` / `raw.epa_*` | `raw.eia_observations_1d`, `raw.epa_rin_prices_1d` |
| weather | `raw.weather_*` | `raw.weather_observations_1d`, `raw.weather_observations_1h` |
| positioning | `raw.cftc_*` | `raw.cftc_cot_1w` |
| news | `raw.news_*` | `raw.news_articles_event` |

### Archive Policy

- Archive during migration only.
- Delete after 14 days only after row-count validation confirms the migrated table is correct.
- Archive tables live in `archive.*` (no extra schemas).

### Staging Rule

- `data/yahoo_staging/` is staging-only (filesystem).
- End state lives in DuckDB `raw.market_*` tables.
- Do not create `brz`/`slv`/`gld` (guardrails will fail).

### Naming Contracts

| Rule | Required | Forbidden |
|------|----------|-----------|
| Grain suffix | `_1h`, `_1d`, `_1w`, `_event`, `_static` | time-series fact tables with no suffix |
| Table naming | `raw.market_futures_1d` | table names containing `ohlc` / `ohlcv` |
| Horizons (DuckDB keys) | integer `5`, `21`, `63`, `126` | string horizons like `"1w"`, `"1m"` in table keys |
| Quantile columns | `p10`, `p50`, `p90` | ad-hoc quantile names (`q10`, `pred_p10`, etc.) |
| OOF table family | `training.oof_core_zl_1d`, `training.oof_specialist_*_1d`, `training.oof_specialist_combined_1d` | `training.oof_big10_*` (legacy), `training.oof_specialists_1d` (plural) |

### FRED Routing (Specialist Ownership)

- FRED is landed in long format (`raw.fred_observations_*`) and routed downstream by `series_id`.
- The explicit mapping lives in `src/fusion/ingestion/router.py` (`FRED_SERIES_BUCKETS` / `get_fred_bucket`).
- When adding or changing ownership for a series, update the mapping and keep tests green (`tests/test_fred_routing.py`).

### Allowed Schemas (11 only)

`raw`, `silver`, `gold`, `features`, `training`, `forecasts`, `monitoring`, `specialist`, `weather`, `metadata`, `archive`

### MLflow/DuckDB Linkage

Every training run must persist these fields back to DuckDB (either in OOF tables or a `metadata.*` table):

- `run_id`
- `model_version`
- `trained_at`

### Artifact Location (Locked)

- All model artifacts must be written under `models/`.
- Do not write new artifacts to `AutogluonModels/` (legacy only).

## Agent Change Authority & Governance

**Core Principle:** *"Build aggressively. Never redefine reality."*

### ✅ What Agents ARE Allowed to Change

#### Code (Primary Authority)
Agents may freely:
- Add new Python files
- Modify existing Python modules
- Refactor functions and classes
- Improve performance
- Add logging, validation, and assertions
- Implement training configurations
- Add tests
- Remove dead or unused code

**Rule:** Code is mutable by default, unless explicitly frozen.

#### Scripts & Glue Logic
Agents may:
- Add training scripts
- Add evaluation scripts
- Add export utilities
- Add parsing and summarization layers
- Add CLI helpers

**Constraints:** Must not invent business logic. Must not cross schema boundaries.

#### Documentation
Agents may:
- Create README files
- Update architecture documentation
- Generate governance documents
- Explain model behavior
- Add inline comments

**Rule:** Documentation is always safe to modify.

---

### ⚠️ What Agents MAY Change — Only With Declaration

These surfaces are high-risk. Agents may touch them only after stating intent and receiving approval.

#### Database Schemas
Agents must:
1. Declare exactly what table or column changes are proposed
2. Explain why the change is required
3. Obtain explicit approval before execution

**Rule:** No silent schema changes. Ever.

#### Feature Definitions
Agents must not:
- Invent new features
- Rename drivers
- Collapse or merge categories

Unless:
- The change is explicitly requested
- The feature contract is updated

**Rule:** Features represent domain truth, not AI discretion.

#### Training Targets & Horizons
Agents may not:
- Change labels
- Change forecast horizons
- Change problem framing

Unless explicitly authorized by the user.

---

### ❌ What Agents Are NEVER Allowed to Change (Hard Locks)

#### Decision Semantics
Agents must never:
- Add "buy / sell / act now" logic
- Encode recommendations
- Introduce execution logic
- Convert probabilities into commands

**Rule:** This system provides procurement intelligence, not trading or execution.

#### Business Meaning
Agents do not decide:
- What a feature means
- Why a driver matters
- Which regime is "correct"

They may explain, never redefine.

#### Hidden Tooling
Agents may not:
- Add new services
- Introduce new infrastructure
- Add libraries or frameworks without approval
- Change orchestration tools

**Rule:** All work remains inside the approved stack.

---

### Required Behavior When Mutating Anything

Before changing anything beyond internal code, the agent must:

1. **State intent:** "I am going to modify X for reason Y"
2. **Define scope:** Files affected, tables touched, outputs impacted
3. **Declare reversibility:** Can this change be reverted cleanly?
4. **Pause if boundary-crossing:** Schemas, Features, Targets, Decisions

**Rule:** No declaration → no change.

---
## Project Reality (What's Actually Here)

### Primary entry points
- FastAPI server: `src/fusion/api/server.py`
- Prisma schema: `prisma/schema.prisma`
- Training scripts: `scripts/train_*.py`
- Ingestion scripts: `scripts/ingest_*.py`

### Database Access
```python
# Prisma Postgres (AUTHORITATIVE - use for all operations)
import psycopg2
conn = psycopg2.connect(os.getenv("DATABASE_URL"))

# DuckDB (ARCHIVE ONLY - read-only historical extraction)
import duckdb
conn = duckdb.connect("data/fusion.db", read_only=True)
```

## Business Context (Why This Exists)

- **Client:** US Oil Solutions (bulk soybean oil procurement)
- **Goal:** probabilistic multi-horizon forecasts (1W/1M/3M/6M) that support *when* to lock procurement and *how much* to hedge/procure
- **Architecture (conceptual):** L0 base models → L1 meta-learner → L2 fusion → L3 Monte Carlo risk metrics (VaR/CVaR)

Use this context to judge whether proposed work improves forecast usefulness, reduces decision risk, or increases operational reliability.

## Technology Stack (Source of Truth)

- **Primary Database:** Prisma Postgres (cloud-hosted, authoritative)
- **Archive Database:** DuckDB (local file at `data/fusion.db`, read-only historical)
- **Python packaging:** `pyproject.toml` + `uv`
- **Testing:** `pytest`
- **CI:** GitHub Actions in `.github/workflows/`
- **ML tracking:** MLflow (optional, for experiment tracking)
- **Market Data:** Databento API (GLBX.MDP3 dataset)

### Frontend / Vercel
This repository does not include a Vercel/Next.js app or `vercel.json`. If a dashboard exists, it likely lives in a separate repository or directory; ask for the location before making frontend or deployment changes.

## Specialist Taxonomy (Canonical 10)

Specialists are organized around these buckets (names should remain consistent across code, tables, and docs):
1. `crush`
2. `china`
3. `fx`
4. `fed`
5. `tariff`
6. `energy`
7. `biofuel`
8. `palm`
9. `volatility`
10. `substitutes`

## How To Run (Local)

Install dependencies:
- `uv pip install -e ".[dev]"`

Environment variables (recommended):
- Put secrets in a local `.env` file (do not commit it), then load it before running the API.

Run API:
- `.venv/bin/python -m uvicorn fusion.api.server:app --host 0.0.0.0 --port 8000`

Run tests:
- `pytest -q`

## CI Expectations

CI is repo-specific; keep checks aligned to the current codebase.

## Known Drift / Sharp Edges


## Core OOF Training (Troubleshooting Notes)

These notes exist to help agents/operators quickly unblock the L0→L1 pipeline by generating core out-of-fold (OOF) quantile predictions in DuckDB.

### What “Core OOF” means here

- **Target table:** `training.oof_core_zl_1d` (DuckDB)
- **Expected columns:** `as_of_date`, `horizon_steps`, `p10`, `p50`, `p90`, `model_version`, `run_id`, `trained_at`
- **Source features:** `training.core_matrix_full_1d`
- **Target columns (current DB reality):** `target_ret_5d`, `target_ret_21d`, `target_ret_63d`, `target_ret_126d`

### Run core OOF (standalone, recommended for iteration)

- Script: `scripts/train_core_oof.py`
- Example (single horizon): `python3 scripts/train_core_oof.py --horizons 5 --presets medium_quality --time-limit 3600 --num-bag-folds 8 --num-stack-levels 0`
- Example (tiny smoke run): `python3 scripts/train_core_oof.py --horizons 126 --time-limit 120 --num-bag-folds 2 --num-stack-levels 0 --max-rows 300`

### Common issues and fixes

- **Ray/GCS failures on macOS:** core script defaults to disabling Ray (sets `AUTOGLUON_DISABLE_RAY=1`). If you see Ray-related errors, ensure your run environment isn’t overriding this.
- **Quantile crossing (p10 > p50 or p50 > p90):** can happen with independent quantile models. The core script now enforces monotonic quantiles per row before insert. If legacy rows already exist, fix in-place with:
  - `python3 scripts/enforce_monotonic_quantiles.py --horizons 5 21 63 126`
- **MAPE for returns:** raw MAPE can explode when actual returns are near 0. Prefer MAE + quantile coverage diagnostics for early sanity checks.

### Validate after training

- Validator: `scripts/validate_core_oof.py`
- Run: `python3 scripts/validate_core_oof.py`
- Checks: row counts + date coverage, null counts, quantile ordering violations, recent model metadata, MAE/MAPE (with epsilon), empirical P10/P90 coverage.

## Workspace Hygiene (Generated Artifacts)

- DuckDB database: `data/fusion.db` is generated at runtime; treat it as a build artifact unless the user explicitly wants it versioned.
- Runtime artifacts under `.tmp/` are local and should not be relied on as committed configuration.
- Notebook outputs and model artifacts may create directories like `models/` and `data/parquet/` (as described in `README.md`); create and track them only when the user explicitly wants them checked in.

## Planning & Execution Rules

### Verify before building
Before implementing, confirm:
- What tables exist in DuckDB (query the file in `data/`)

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
