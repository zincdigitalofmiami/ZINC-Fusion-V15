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

### Prisma Postgres = Production Database
- **All training, inference, and operations use Prisma Postgres**
- Connection: `DATABASE_URL` in `.env`
- This is the production database for all ML pipelines
- Frontend deployed on Vercel (Next.js + Inngest)

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

## Operating Principles (Agents)

These are the "how we operate" rules for assistants/agents working in this repo.

- **Verify-first, then assert:** no "Phase-0 ready" / "done" claims without checking the live Prisma database state.
- **No silent schema changes:** any new schema/table/column requires an explicit declaration and user approval.
- **Fail loudly:** scripts should error on missing tables/columns; avoid implicit DDL creation during training unless it's explicitly the contract.
- **No decision semantics:** never encode "buy/sell/act now" logic; this remains an intelligence system, not execution.
- **Minimal diffs:** fix the root cause, avoid unrelated refactors, keep patches small and reversible.
- **Always provide a validation path:** prefer targeted Prisma queries and `pytest` in `.venv` (system Python may not match project deps).

## Local Development

### API Server

```bash
.venv/bin/python -m uvicorn fusion.api.server:app --host 0.0.0.0 --port 8000
```

### Environment Variables

Required in `.env`:
- `DATABASE_URL` - Prisma Postgres connection string
- `FRED_API_KEY` - For economic data (ongoing updates)

## Operational Contracts (Locked)

These rules exist to prevent drift. If a rule needs to change, stop and get explicit approval before implementing.

### Data Domains (7)

Domains are an organizational convention for raw ingestion + table naming. Not every domain is populated yet.

| Domain | Schema Target | Existing Tables (examples) |
|--------|---------------|----------------------------|
| market | `raw.market_*` | `raw.market_futures_1d`, `raw.market_futures_1h` |
| economic | `raw.fred_*` | `raw.fred_observations_1d` |
| agriculture | `raw.usda_*` | `raw.usda_export_sales_1w`, `raw.usda_wasde_1m` |
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
- End state lives in Prisma `raw.market_*` tables.
- Do not create `brz`/`slv`/`gld` (guardrails will fail).

### Intraday Data Rule (Hard Lock)

| Frequency | Table | Allowed Destination | Forbidden |
|-----------|-------|---------------------|-----------|
| Daily (1d) | `raw.market_futures_1d` | silver → gold → training → model | - |
| Intraday (15m) | `analytics.intraday_prices` | Dashboard display ONLY | training.*, features.*, any ML tables |

**ZL Only:** Intraday 15m data is collected ONLY for ZL (soybean oil) - the procurement target. No other instruments need intraday tracking.

**Rationale:** Intraday data is for dashboard display and real-time monitoring only. Training models use daily data to avoid:
- Noise amplification from microstructure
- Inconsistent bar boundaries across instruments
- Data volume issues (15m = 26x daily storage)

**Scripts:**
- `scripts/ingest_yahoo_eod.py` → `raw.market_futures_1d` → training path
- `scripts/ingest_yahoo_15m.py` → `analytics.intraday_prices` (ZL only, dashboard)

### Naming Contracts

| Rule | Required | Forbidden |
|------|----------|-----------|
| Grain suffix | `_1h`, `_1d`, `_1w`, `_event`, `_static` | time-series fact tables with no suffix |
| Table naming | `raw.market_futures_1d` | table names containing `ohlc` / `ohlcv` |
| Horizons | integer `5`, `21`, `63`, `126` | string horizons like `"1w"`, `"1m"` in table keys |
| Quantile columns | `p10`, `p50`, `p90` | ad-hoc quantile names (`q10`, `pred_p10`, etc.) |
| OOF table family | `training.oof_core_zl_1d`, `training.oof_specialist_*_1d`, `training.oof_specialist_combined_1d` | `training.oof_big10_*` (legacy), `training.oof_specialists_1d` (plural) |

### Data Availability by Horizon (Training Constraint)

Not all data series have 25+ years of history. Training scripts MUST tier data by availability:

| Tier | Data Window | Horizons | Example Series |
|------|-------------|----------|----------------|
| **Tier 1** | 2000+ | ALL (5d/21d/63d/126d) | ZL, VIXCLS, DGS10, FEDFUNDS, M2SL, OVXCLS |
| **Tier 2** | Fundamentally Limited | Tactical only (5d/21d) | **SOFR** (created 2018), **VXGSCLS** (created 2020) |

**Key Distinction:**
- If data EXISTS historically but isn't in our DB → **BACKFILL IT** (M2SL has data from 1959, OVXCLS from 2007)
- If data DIDN'T EXIST before a date → Use proxy for strategic (SOFR → FEDFUNDS, VXGSCLS → VIXCLS)

**Backfill Priorities:** M2SL (64yr gap), OVXCLS (16yr gap), USDA WASDE (20yr gap)

**Reference:** `.claude/skills/zf-pipeline-contracts/references/data_availability_by_horizon.md`

### FRED Routing (Specialist Ownership)

- FRED is landed in long format (`raw.fred_observations_*`) and routed downstream by `series_id`.
- The explicit mapping lives in `src/fusion/ingestion/router.py` (`FRED_SERIES_BUCKETS` / `get_fred_bucket`).
- When adding or changing ownership for a series, update the mapping and keep tests green (`tests/test_fred_routing.py`).

### Allowed Schemas (14 total)

`raw`, `silver`, `gold`, `features`, `training`, `forecasts`, `monitoring`, `specialist`, `weather`, `metadata`, `archive`, `model`, `analytics`, `ops`

---

## Medallion Architecture (Data Flow Law)

This is the canonical data flow pattern. No exceptions.

### Schema Purposes (Locked)

| Schema | Layer | Purpose | Mutability |
|--------|-------|---------|------------|
| `raw` | Bronze | Immutable ingestion from external sources | Append-only |
| `silver` | Silver | Cleaned, deduplicated, canonical OHLCV with source tracking | Upsert via metadata |
| `gold` | Gold | **Denormalized feature store** (OHLCV + indicators + derived metrics) | Computed |
| `training` | Feature | Specialist staging + feature matrices (reads from Gold) | Rebuilt on demand |
| `model` | ML | OOF predictions, model registry, forecasts | Versioned |
| `analytics` | Presentation | Dashboard-facing tables, real-time displays | Real-time updates |
| `metadata` | Control | Canonical instruments, symbol mappings | Governance only |
| `ops` | Infrastructure | Data source registry, job health | System-managed |

### Data Flow Rules

```
EXTERNAL SOURCES
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  RAW (Bronze) - Immutable ingestion                         │
│  • raw.market_futures_1d, raw.fred_observations_1d          │
│  • raw.fx_spot_1d, raw.cftc_cot_1w                          │
│  • NEVER modify after insert                                │
└─────────────────────────────────────────────────────────────┘
      │
      │ metadata.symbol_mapping (canonical resolution)
      ▼
┌─────────────────────────────────────────────────────────────┐
│  SILVER - Cleaned, deduplicated canonical data              │
│  • silver.fx_rates_1d (deduplicated from fx_spot + FRED)    │
│  • silver.futures_prices_1d (canonical OHLCV)               │
│  • Source + confidence tracking per row                     │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  GOLD - Denormalized feature store (business-ready)         │
│  • gold.elite_indicators_1d = OHLCV + 27 indicators + KPIs  │
│  • gold.intelligence_cells = Bio-Genetic Intelligence Units │
│  • Denormalized: no JOINs needed downstream                 │
│  • Hurst, ConnorsRSI, Fisher, TTM Squeeze, returns, etc.    │
│  • Module: src/fusion/features/elite_indicators.py          │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  TRAINING - Reads from Gold directly                        │
│  • training.specialist_*_1d (JOINs to silver, not copies)   │
│  • training.core_matrix_full_1d (feature matrix)            │
│  • training.specialist_features (JSON blob)                 │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  MODEL - ML outputs                                         │
│  • model.model_registry, model.training_runs                │
│  • model.oof_predictions, model.forecast_quantiles          │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  ANALYTICS - Dashboard presentation                         │
│  • analytics.latest_prices (real-time ticker)               │
│  • analytics.intraday_prices (charting)                     │
│  • analytics.dashboard_metrics, analytics.risk_metrics      │
└─────────────────────────────────────────────────────────────┘
```

### Deduplication via Metadata Control Plane

When multiple sources provide the same underlying data:

1. **Register canonical instrument** in `metadata.instrument`
2. **Map source symbols** in `metadata.symbol_mapping` with confidence scores
3. **Silver layer** resolves to canonical using highest-confidence primary source
4. **Training layer** JOINs to silver (never copies OHLCV)

**Example: FX Rates**
```
metadata.instrument: { canonical_id: "USDBRL", asset_class: "fx", primary_source: "raw.fx_spot_1d" }
metadata.symbol_mapping: [
  { canonical_id: "USDBRL", source_table: "raw.fx_spot_1d", source_symbol: "USDBRL", is_primary: true },
  { canonical_id: "USDBRL", source_table: "raw.fred_observations_1d", source_symbol: "DEXBZUS", is_primary: false }
]
silver.fx_rates_1d: Uses primary source, tracks provenance
```

### Analytics vs Ops (Boundary Law)

| Goes in `analytics` | Goes in `ops` |
|---------------------|---------------|
| latest_prices | data_source_registry |
| intraday_prices | job_run_status |
| dashboard_metrics | ingestion_health |
| risk_metrics | system_alerts |
| Any user-facing data | Any infrastructure metadata |

---

### MLflow/Prisma Linkage

Every training run must persist these fields to Prisma (either in OOF tables or a `metadata.*` table):

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
# Prisma Postgres (use for all operations)
import psycopg2
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
```

## Business Context (Why This Exists)

- **Client:** US Oil Solutions (bulk soybean oil procurement)
- **Goal:** probabilistic multi-horizon forecasts (1W/1M/3M/6M) that support *when* to lock procurement and *how much* to hedge/procure
- **Architecture (conceptual):** L0 base models → L1 meta-learner → L2 fusion → L3 Monte Carlo risk metrics (VaR/CVaR)

Use this context to judge whether proposed work improves forecast usefulness, reduces decision risk, or increases operational reliability.

## Technology Stack (Source of Truth)

- **Database:** Prisma Postgres (cloud-hosted)
- **Frontend:** Vercel (Next.js + Inngest serverless functions)
- **Python packaging:** `pyproject.toml` + `uv`
- **Testing:** `pytest`
- **CI:** GitHub Actions in `.github/workflows/`
- **ML tracking:** MLflow (local SQLite)
- **Market Data:** Yahoo Finance (daily topfill) + historical backfill (locked 2025-12-29)
- **Macro Data:** FRED API (ongoing updates)

### Frontend / Vercel
The dashboard is deployed on Vercel. The `frontend/` folder contains the Next.js app. Inngest functions run serverless on Vercel.

## Specialist Taxonomy (Big 11)

Specialists are organized around these buckets (names should remain consistent across code, tables, and docs):
1. `crush` (28-35% variance)
2. `china` (16-22% variance)
3. `fx` (3-5% variance)
4. `fed` (2-4% variance)
5. `tariff` (3-5% variance)
6. `energy` (10-14% variance)
7. `biofuel` (6-10% variance)
8. `palm` (8-12% variance)
9. `volatility` (2-3% variance)
10. `substitutes` (4-6% variance)
11. `trump_effect` (5-10% variance, regime-dependent)

**Data Sources Reference**: See `ZINC_FUSION_V15_BIG11_COMPLETE_SOURCES.md` for complete URL/API registry.

### Trump Effect Specialist Details

The `trump_effect` specialist is a hybrid bucket combining structured FRED data, market-implied probability proxies, and discrete event tracking.

#### Data Sources

| Source | Series/Tickers | Role |
|--------|----------------|------|
| **FRED (regime pressure)** | USEPUINDXD, USEPUINDXM, EPUTRADE, EMVTRADEPOLEMV, CHNMAINLANDTPU, B235RC1Q027SBEA, IMPCH | Policy/trade uncertainty indices, tariff receipts, China trade flows |
| **Yahoo (probability proxies)** | DJT, FXI, KWEB | Market-implied regime proxies (Trump-linked, China sensitivity) |
| **URL Events (glass box)** | White House, Federal Register, Truth Social | Discrete executive/trade actions for narrative layer |

#### EPU Regime Thresholds

| Regime | EPU Level | Vol Multiplier |
|--------|-----------|----------------|
| `low` | < 75 | 0.7x |
| `normal` | 75-125 | 1.0x |
| `elevated` | 125-175 | 1.25x |
| `high` | 175-250 | 1.5x |
| `extreme` | > 250 | 2.0x |

#### Feature Module

- **Location**: `src/fusion/features/trump_effect.py`
- **Key Functions**:
  - `detect_epu_regime()` - Classify current EPU regime
  - `calculate_event_intensity()` - Score shock/uncertainty/novelty
  - `calculate_probability_proxies()` - DJT/FXI/KWEB derived metrics
  - `calculate_trump_effect_risk_metrics()` - Sharpe, Sortino, VaR with regime conditioning
  - `fit_trump_regime_garch()` - GJR-GARCH with EPU regime adjustment
- **Main Class**: `TrumpEffectFeatureEngine` - Batch feature generation

#### Topic Codes (Event Classification)

```
TARIFF_CHINA, TARIFF_OTHER, RFS_RVO, EPA_WAIVER, TAX,
SANCTIONS, EXPORT_CONTROLS, TRADE_DEAL, EXECUTIVE_ACTION, TWEET_THREAT
```

#### Routing

FRED series routed to `trump_effect` bucket via `router.py`:
- `USEPUINDXD` - US Economic Policy Uncertainty (Daily)
- `USEPUINDXM` - US Economic Policy Uncertainty (Monthly)
- `EPUTRADE` - Trade Policy Uncertainty
- `EMVTRADEPOLEMV` - Equity Market Volatility: Trade Policy
- `CHNMAINLANDTPU` - China Trade Policy Uncertainty
- `B235RC1Q027SBEA` - Customs Duties (tariff receipts)
- `IMPCH` - US Imports from China

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

These notes exist to help agents/operators quickly unblock the L0→L1 pipeline by generating core out-of-fold (OOF) quantile predictions.

### What "Core OOF" means here

- **Target table:** `training.oof_core_zl_1d` (Prisma)
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

## Active Model Architecture (SoT v2)

### Data Sources (LOCKED)
| Source | Role | Cadence | Status |
|--------|------|---------|--------|
| **Historical Backfill** | 1990 → 2025-12-29 | One-time | ✅ Complete, LOCKED |
| **Yahoo Finance** | Daily topfill (2025-12-30 → future) | Daily | ✅ Active |
| **FRED API** | Macro indicators | Daily/Weekly/Monthly | ✅ Active |

**Note:** Historical backfill was completed 2025-12-29. No additional historical data sources are required or planned.

### Active Model Location
```
models/
├── core_v15/           # ACTIVE - Production Core models
│   ├── horizon_5d/     # Tactical (5d)
│   ├── horizon_21d/    # Tactical (21d)  
│   └── horizon_63d/    # Strategic (63d)
├── core_chronos2/      # ACTIVE - Chronos-2 variants (all 4 horizons)
│   ├── horizon_5d/
│   ├── horizon_21d/
│   ├── horizon_63d/
│   └── horizon_126d/
├── specialists/        # NOT YET TRAINED - Big 11 specialists
└── hunters/            # NOT YET TRAINED - Opportunity hunters
```

### SoT v2 Training Stack (52 Models)
- **L0 Core:** `zinc-fusion-v2-core-h{H}d` (4 horizons)
- **L0 Specialists:** `zinc-fusion-v2-specialist-{bucket}-h{H}d` (11 buckets × 4 horizons = 44)
- **L1 Meta:** `zinc-fusion-v2-meta-h{H}d` (4 horizons)
- **L2/L3:** Calibration + Risk modules (non-model)

**Full catalog:** `scripts/v2_training/MODEL_CATALOG.md`

### Model Registry
All trained models register in Prisma `model.model_registry` with:
- `model_id`, `model_version`, `horizon_steps`
- `trained_at`, `artifact_path`, `metrics_json`

## Workspace Hygiene (Generated Artifacts)

- Runtime artifacts under `.tmp/` are local and should not be relied on as committed configuration.
- Notebook outputs and model artifacts may create directories like `models/` and `data/parquet/` (as described in `README.md`); create and track them only when the user explicitly wants them checked in.

## Planning & Execution Rules

### Verify before building
Before implementing, confirm:
- What tables exist in Prisma (query via DATABASE_URL)

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
- The schema in Prisma contradicts the notebooks/README
- The request implies external systems (MLflow server, etc.) without concrete repo paths, settings, and explicit confirmation

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
