NOTE: Production is the dashboard/frontend, not the repo root.
# ZINC-FUSION-V15 Workspace Guide (Assistant/Agent)

This file is the operational and architectural guide for any automated assistant or human operator working in this repository.

## Identity & Scope

You are an expert data/ML engineering assistant focused on:
- Commodity procurement forecasting and decision support (soybean oil / ZL)
- Time-series feature engineering and forecast evaluation
- Training L0 specialists and L1/L2 ensemble models
- Prisma Postgres database operations

**Scope boundary:** stay within the current repository's documented stack and structure. If a requested change implies missing components (data sources, schemas, configs, credentials, or a frontend app), stop and ask for clarification instead of guessing.

## Ray Cluster (22 cores available)

**Your AI agents can use `ray.init(address='auto')` and get 22 cores without melting your machine.**

## Database Architecture (CRITICAL)

### Prisma Postgres = Production Database
- **All training, inference, and operations use Prisma Postgres**
- Connection: `DATABASE_URL` in `.env`
- This is the production database for all ML pipelines
- Frontend deployed on Vercel (Next.js + Inngest)

## Runtime Connection Architecture

**Prisma = Schema Authority, NOT Runtime Client**

This project intentionally uses Prisma for schema management only:

| Layer | Tool | Purpose |
| --- | --- | --- |
| Schema Definition | `prisma/schema.prisma` | Single source of truth for tables |
| Migrations | `prisma migrate` | DDL version control |
| TypeScript Runtime | `pg` Pool | All Inngest job queries |
| Python Runtime | psycopg2 / SQLAlchemy | All training script queries |

**Why not PrismaClient for queries?**
1. Multi-schema support (`mkt.*`, `econ.*`) — Prisma Client handles poorly
2. Performance — Raw pg Pool faster for bulk operations
3. Flexibility — Complex CTEs, window functions, cross-schema joins

**Connection Patterns:**

```typescript
// TypeScript (frontend/src/lib/db.ts)
import { Pool } from 'pg';
const pool = new Pool({ connectionString: process.env.DATABASE_URL });
```

```python
# Python (src/fusion/db/connection.py)
from fusion.db import get_read_engine, get_write_connection
```

DO NOT attempt to migrate to PrismaClient for runtime queries.

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
8. **Forward fill policy (LOCKED):** forward fill is OFF by default. Any use requires explicit approval and must follow TTL + staleness gating + as‑of correctness + event-encoding rules. See `Docs/FORWARD_FILL_POLICY.md`.
9. **Check before pull (LOCKED):** Before ingesting or backfilling data, ALWAYS verify the data does not already exist in the target table. Query the existing date range/row count first. Only pull data for gaps or new periods. This prevents duplicate ingestion costs and data integrity issues.

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

### Data Domains (v2)

Domains are logical tags; physical storage uses institutional schemas.

| Domain | Primary Schema | Examples |
|--------|----------------|----------|
| market | `mkt.*` | `mkt.futures_1d`, `mkt.futures_1h`, `mkt.options_1d` |
| economic | `econ.*` | `econ.rates_1d`, `econ.activity_1d`, `econ.inflation_1d` |
| alternative | `alt.*` | `alt.news_1d`, `alt.weather_1d`, `alt.legislation_1d` |
| positioning | `pos.*` | `pos.cftc_1w` |
| supply | `supply.*` | `supply.usda_wasde_1m`, `supply.epa_rin_1d` |
| features | `features.*` | `features.options_1d` (elite_1d consolidated into `mkt.futures_1d`) |
| training | `training.*` | `training.matrix_1d`, `training.oof_core_1d` |

### Archive Policy (v2)

- No archive schema or archive tables should be created.
- Use external backups + row-count validation for migrations.
- BANNED schemas: `raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`, `archive`
- **Do not touch the vegas schema:** do not modify, query, or reference `vegas.*` tables or any Vegas-related API routes. Stay out.

### Staging Rule

- `data/yahoo_staging/` is staging-only (filesystem).
- End state lives in Prisma `mkt.futures_*` tables.
- Do not create `brz`/`slv`/`gld` (guardrails will fail).

### Intraday Data Rule (Hard Lock)

| Frequency | Table | Allowed Destination | Forbidden |
|-----------|-------|---------------------|-----------|
| Daily (1d) | `mkt.futures_1d` | features → training → model | - |
| Daily (1d, dashboard copy) | `analytics.zl_price_1d` | Dashboard display ONLY | training.*, features.*, any ML tables |
| Intraday (15m) | `analytics.zl_price_15m` | Dashboard display ONLY | training.*, features.*, any ML tables |
| Intraday (1h) | `analytics.zl_price_1h` | Dashboard display ONLY | training.*, model.* |

**ZL Only:** Intraday 15m/1h data is collected ONLY for ZL (soybean oil) - the procurement target. No other instruments need intraday tracking.

**Rationale:** Intraday data is for dashboard display and real-time monitoring only. Training models use daily data to avoid:
- Noise amplification from microstructure
- Inconsistent bar boundaries across instruments
- Data volume issues (15m = 26x daily storage)

**Note:** `analytics.specialist_*_1h` tables (specialist signal outputs) were moved from `training` to `analytics` (2026-01-15) and are dashboard-only.

**Scripts:**
- `scripts/ingest_yahoo_eod.py` → `mkt.futures_1d` → training path
- `frontend/src/inngest/yahoo-eod.ts` → `analytics.zl_price_1d` (dashboard copy)
- `frontend/src/inngest/zl-15m.ts` → `analytics.zl_price_15m` (ZL only, dashboard)
- `frontend/src/inngest/zl-1h.ts` → `analytics.zl_price_1h` (ZL only, dashboard)

### Naming Contracts

| Rule | Required | Forbidden |
|------|----------|-----------|
| Grain suffix | `_1h`, `_1d`, `_1w`, `_event`, `_static` | time-series fact tables with no suffix |
| Table naming | `mkt.futures_1d` | table names containing `ohlc` / `ohlcv` |
| Horizons | integer `5`, `21`, `63`, `126` | string horizons like `"1w"`, `"1m"` in table keys |
| **Quantile columns (OOF/Stacking)** | `p30`, `p50`, `p70` | `p10`, `p90` in OOF tables |
| **Quantile columns (Risk/MC/Cones)** | `p10`, `p30`, `p50`, `p70`, `p90` | missing any of the 5 quantiles |
| Core OOF + specialist signals | `training.oof_core_1d`, `training.specialist_signals_1d` | `training.oof_big10_*` (legacy), `training.oof_specialists_1d` (plural) |

### Quantile Contract (LOCKED)

Two distinct quantile contracts exist for different purposes:

| Use Case | Quantiles | Tables | Rationale |
|----------|-----------|--------|-----------|
| **OOF + Meta-Stacking** | p30/p50/p70 | `training.oof_*`, `training.meta_inputs_*` | Procurement pace bands, robust to fat tails |
| **Risk Cones + Monte Carlo** | p10/p30/p50/p70/p90 | `model.core_cone_1d`, `model.core_mc_1d` (migrating from `forecasts.*`) | Full tail risk management |

**Do NOT mix:** OOF tables must never contain p10/p90. Risk tables must always have all 5 quantiles.

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

**Reference:** This section (“Data Availability by Horizon (Training Constraint)”) is the canonical guidance in this repo.

### FRED Routing (Two-Layer System)

FRED series are routed at two levels:

1. **Table Routing** (which `econ.*` table): `src/fusion/db/fred_routing.py`
   - 136 series mapped to 7 domain tables
   - Use `get_fred_table(series_id)` for ingestion
   - Tables: `rates_1d`, `activity_1d`, `commodities_1d`, `vol_indices_1d`, `inflation_1d`, `labor_1d`, `money_1d`

2. **Specialist Routing** (which Big 11 bucket): `src/fusion/ingestion/router.py`
   - Routes series to specialist training buckets
   - Use `get_fred_bucket(series_id)` for feature generation
   - Updates require keeping tests green (`tests/test_fred_routing.py`)

### Allowed Schemas (v2, 12 total)

**Landing (append-only):** `mkt`, `econ`, `alt`, `pos`, `supply`
**Derived (computed):** `features`, `training`
**Output (versioned):** `model`, `forecasts`, `analytics`
**Governance:** `metadata`, `ops`

**BANNED:** `raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`, `archive`

---

## Schema Flow (v2)

Institutional schema taxonomy. Migrated 2026-01-18.

### Schema Purposes (v2)

| Schema | Purpose | Mutability |
|--------|---------|------------|
| `mkt` | Market time series (futures, options, FX spot) | Append-only |
| `econ` | Macro/policy series (FRED long format) | Append-only |
| `alt` | Alternative data (news, weather, legislation) | Append-only |
| `pos` | Positioning data (CFTC) | Append-only |
| `supply` | Supply/demand (USDA, EPA, trade flows) | Append-only |
| `features` | Denormalized feature store (options_1d, intel_drops, trump_effect_1d); elite_1d consolidated into mkt.futures_1d | Computed / rebuilt |
| `training` | Matrices + OOF + specialist features | Rebuilt on demand |
| `model` | Model registry + training runs | Versioned |
| `forecasts` | Prediction outputs | Versioned |
| `analytics` | Dashboard/presentation | Real-time updates |
| `metadata` | Canonical instruments + symbol mappings | Governance only |
| `ops` | Job health + ingestion registry | System-managed |

### Data Flow Rules

```
EXTERNAL SOURCES
      │
      ├──► mkt (futures/options/fx)
      └──► econ (macro/policy)
                │
                ▼
           features (elite/options/weather)
                │
                ▼
           training (matrix_1d, oof_core_1d, specialist_signals_1d)
                │
                ▼
             model (registry, forecasts, metrics)
                │
                ▼
           analytics (dashboard/presentation)
```

### Deduplication via Metadata Control Plane

When multiple sources provide the same underlying data:

1. **Register canonical instrument** in `metadata.instrument`
2. **Map source symbols** in `metadata.symbol_mapping` with confidence scores
3. **Consumers select primary source** based on mapping (no silver layer)
4. **features/training** use canonical ids and tracked provenance

**Example: FX Rates**
```
metadata.instrument: { canonical_id: "USDBRL", asset_class: "fx", primary_source: "mkt.fx_1d" }
metadata.symbol_mapping: [
  { canonical_id: "USDBRL", source_table: "mkt.fx_1d", source_symbol: "USDBRL", is_primary: true },
  { canonical_id: "USDBRL", source_table: "econ.fx_1d", source_symbol: "DEXBZUS", is_primary: false }
]
```

### Analytics vs Ops (Boundary Law)

| Goes in `analytics` | Goes in `ops` |
|---------------------|---------------|
| latest_prices | data_source_registry |
| zl_price_15m / zl_price_1h / zl_price_1d | job_run_status |
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

| Specialist | Data Nature | Primary Tables |
|------------|-------------|----------------|
| `crush` | 100% Quantitative | mkt.futures_1d (ZL/ZS/ZM), pos.cftc_1w |
| `china` | 70% Quant / 30% Qual | mkt.futures_1d (HG), mkt.fx_1d (CNY), alt.news_1d |
| `fx` | 100% Quantitative | mkt.fx_1d |
| `fed` | 100% Quantitative | econ.rates_1d |
| `tariff` | 40% Quant / 60% Qual | econ.rates_1d (EPU), alt.news_1d, alt.legislation_1d |
| `energy` | 100% Quantitative | mkt.futures_1d (CL/HO), econ.commodities_1d |
| `biofuel` | 80% Quant / 20% Qual | supply.epa_rin_1d, alt.news_1d |
| `palm` | 80% Quant / 20% Qual | mkt.futures_1d (FCPO), alt.news_1d |
| `volatility` | 100% Quantitative | econ.vol_indices_1d, econ.rates_1d |
| `substitutes` | 100% Quantitative | mkt.futures_1d, econ.commodities_1d |
| `trump_effect` | 50% Quant / 50% Qual | econ.rates_1d (EPU), alt.news_1d, alt.legislation_1d |

> **⚠️ NO HARDCODED WEIGHTS**: Specialist importance is learned by the L1 meta-ensemble from market data. Never assign predetermined weight percentages.

### Specialist Model Types (CRITICAL - READ THIS)

> **⚠️ EACH SPECIALIST HAS A UNIQUE, CUSTOM-BUILT MODEL ARCHITECTURE.**
> These are NOT generic AutoGluon fits. Each was METICULOUSLY CRAFTED for its domain.
> Specialists produce SIGNALS (no horizons). Core owns all horizon forecasting.
> Full details: `Docs/SPECIALIST_MODEL_REGISTRY.md`

| Specialist | Model Type | Full Architecture | Key Features |
|------------|------------|-------------------|--------------|
| `crush` | `xgb` | XGBRegressor | Board crush z-score, oil share z-score, WASDE fundamentals |
| `china` | `gbm` | GradientBoostingRegressor | Copper z-score (demand proxy), CNY, BRL, shipping indices |
| `substitutes` | `rf` | RandomForestRegressor | Spread/ratio z-scores vs canola, palm, sunflower |
| `fx` | `ardl` | statsmodels ARDL | DXY, BRL/USD, CNY/USD, MXN/USD, carry trade rates |
| `fed` | `ridge` | Ridge Regression | Fed Funds, DGS2, DGS10, T10Y2Y spread |
| `volatility` | `garch` | GJR-GARCH(1,1) Student-t | Asymmetric volatility, VIX, VIX3M term structure, OVX |
| `energy` | `var` | statsmodels VAR + IRF | CL (crude), HO (heating oil), RB (gasoline), 3-2-1 crack |
| `palm` | `ecm` | ECM cointegration + Ridge | Palm-soy spread, cointegration residuals, FX conversion |
| `tariff` | `tree` | Rules-based EPU thresholds | USEPUINDXM, EPUTRADE, EMVTRADEPOLEMV |
| `biofuel` | `nlp_ema` | EMA-smoothed RIN/policy | RIN D4/D6 prices, LCFS credits, biodiesel margin |
| `trump_effect` | `event_study` | Event study + sentiment | EPU indices, FXI (China ETF), VIX |

**Signal Contract**: All specialists output `signal_1` (required), `signal_2` (optional), `confidence` (optional).
Signals stored in `training.specialist_signals_1d`. NO OOF tables for specialists.

**Code Location**: `src/fusion/specialists/`
**Artifacts**: `models/specialists/{bucket}/`

**Key Insight:** 6 specialists are purely quantitative (crush, fx, fed, energy, volatility, substitutes). 5 specialists require news/policy sentiment data (china, tariff, biofuel, palm, trump_effect).

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

1. **README.md still describes v2 52-model architecture.** The README references 48 OOF tables, 12 L0 models per horizon, specialists as TabularPredictors with horizons, and a `features.driver_scores_1d` canonical feature table. The current v3 architecture uses 19 models, 1 OOF table (`training.oof_core_1d`), and specialists as signal generators. README needs a v3 refresh.
2. **README.md uses banned/legacy table names.** References `raw_market_futures`, `raw_fred_observations`, `raw_weather_observations`, `driver_scores`, `oof_predictions` — none of which follow the schema-prefixed naming contract.
3. **README.md references `weather.*` schemas.** The "Latest Update" header advertises 5 regional weather schemas (`weather.us_cornbelt`, etc.), but `weather` is a banned schema per this document. The weather data was migrated to `alt.weather_1d`.
4. **README.md says GrafanaRegistry for model tracking.** AGENTS.md says MLflow (local SQLite). Needs reconciliation.
5. **Model names still use `v2` prefix.** Model naming (`zinc-fusion-v2-core-h{H}d`) hasn't been updated to reflect v3 architecture. This is cosmetic but could confuse agents.
6. **`scripts/v2_training/` path.** The training scripts directory is still named `v2_training` even though the architecture is v3.

## Core OOF Training (Troubleshooting Notes)

These notes exist to help agents/operators quickly unblock the L0→L1 pipeline by generating core out-of-fold (OOF) quantile predictions.

### What "Core OOF" means here

- **Target table:** `training.oof_core_1d` (Prisma)
- **Expected columns:** `trade_date`, `symbol`, `horizon_days`, `window_id`, `cutoff_date`, `p30`, `p50`, `p70`, `target_value`, `trained_at`, `run_hash`, `matrix_version`
- **Source features:** `training.matrix_1d`
- **Target columns (current DB reality):** `target_ret_5d`, `target_ret_21d`, `target_ret_63d`, `target_ret_126d`

### Run core OOF (standalone, recommended for iteration)

- Script: `python -m fusion.core_training.run_pipeline`
- Example (single horizon): `python -m fusion.core_training.run_pipeline --skip-matrix --horizons 5`
- Example (all horizons): `python -m fusion.core_training.run_pipeline --skip-matrix`

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

### Common issues and fixes

- **Ray/GCS failures on macOS:** core script defaults to disabling Ray (sets `AUTOGLUON_DISABLE_RAY=1`). If you see Ray-related errors, ensure your run environment isn’t overriding this.
- **Quantile crossing (p30 > p50 or p50 > p70):** can happen with independent quantile models. The core script now enforces monotonic quantiles per row before insert. If legacy rows already exist, fix in-place with:
  - `python3 scripts/enforce_monotonic_quantiles.py --horizons 5 21 63 126`
- **MAPE for returns:** raw MAPE can explode when actual returns are near 0. Prefer MAE + quantile coverage diagnostics for early sanity checks.

### Validate after training

- Validator: `scripts/validate_core_oof.py`
- Run: `python3 scripts/validate_core_oof.py`
- Checks: row counts + date coverage, null counts, quantile ordering violations, recent model metadata, MAE/MAPE (with epsilon), empirical P30/P70 coverage.

## Active Model Architecture (SoT v2)

### Data Sources (LOCKED)
| Source | Role | Cadence | Status |
|--------|------|---------|--------|
| **Historical Backfill** | 1990 → 2025-12-29 | One-time | ✅ Complete, LOCKED |
| **Yahoo Finance** | Daily topfill (2025-12-30 → future) | Daily | ✅ Active |
| **FRED API** | Macro indicators | Daily/Weekly/Monthly | ✅ Active |

**Note:** Historical backfill was completed 2025-12-29. No additional historical data sources are required or planned.

### January 2026 Data Enhancements

| New Table/Function | Purpose | Cadence |
|--------------------|---------|---------|
| `analytics.board_crush_1d` | CME board crush + oil share calculations | Daily (6 PM CT) |
| `alt.tariff_deadlines` | Policy expiration countdown (Section 301, China ag) | Daily update |
| `supply.eia_biodiesel_1m` | EIA biodiesel/RD production | Monthly (18th) |
| `board-crush-daily.ts` | Inngest function for crush calculations | Daily cron |
| `eia-biodiesel-monthly.ts` | Inngest function for EIA API | Monthly cron |

**Specialist Feature Enhancements (Jan 2026):**
- **Crush**: Added `crush_margin_regime` (categorical -2 to +2)
- **Tariff**: Added `deadline_risk_score` (sigmoid urgency) + `deadline_vol_multiplier`
- **Volatility**: Added `vix_term_slope_normalized` for backwardation detection
- **Federal Register**: Added 45Z tax credit tracking patterns

### Active Model Location
```
models/
├── core_v2/            # ACTIVE - Core models (CPU-only, full Model Zoo)
│   ├── horizon_5d/
│   ├── horizon_21d/
│   ├── horizon_63d/
│   └── horizon_126d/
├── specialists/        # v3 SIGNAL GENERATORS - Custom models per bucket
```

**Note:** Core training uses CPU-only execution with the full AutoGluon Model Zoo. AutoGluon selects/ensembles the best models via validation. See `Docs/CORE_TRAINING_SPEC_LOCKED.md`.
**Retention:** Only `models/core_v2` and `models/specialists` are kept under `models/`.

### SoT v3 Training Stack (19 Models)
- **L0 Core:** `zinc-fusion-v2-core-h{H}d` (4 horizons: 5d, 21d, 63d, 126d)
- **Specialists:** 11 signal generators (NO horizons - see table above for architectures)
- **L1 Meta:** `zinc-fusion-v2-meta-h{H}d` (4 horizons)
- **L2/L3:** Calibration + Risk modules (non-model)

> **v3 CHANGE**: Specialists produce SIGNALS that feed into Core as input features.
> They do NOT produce OOF forecasts. Core owns all horizon forecasting.

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
- **Phase 2: Feature engineering** (aligned to Big‑11 taxonomy)
- **Phase 3: Training** (OOF extraction rules, leakage checks)
- **Phase 4: Inference + forecasts tables**
- **Phase 5: Risk layer (Monte Carlo / VaR/CVaR)**

### When to stop and ask
Stop and ask the user when:
- A required file/config is missing (e.g., a dashboard repo/path, credentials)
- The schema in Prisma contradicts the notebooks/README
- The request implies external systems (MLflow server, etc.) without concrete repo paths, settings, and explicit confirmation

## Active Review Agents

Three specialized review agents are available for delegation during multi-step or complex work. These agents are **read-only** - they analyze and report but do not make changes.

### Micro-Planner
**Location:** `.claude/skills/micro-planner.md`
**Trigger:** Multi-step tasks requiring planning, progress tracking, or scope management

Responsibilities:
- Task decomposition into atomic steps with dependencies
- Progress tracking against original goals
- Scope creep detection and "must have" vs "nice to have" distinction
- Risk identification and blocker detection
- Course correction recommendations

### Database / Prisma Review (No bundled skill file)
**Trigger:** Modifying database code, Prisma schema, migrations, or queries

Use these as the review checklist:
- Schema design (models, relations, constraints, naming)
- Query patterns (avoid N+1; use transactions where appropriate)
- Migration safety (data preservation, rollback capability)
- Performance (indexing, pagination, time-series patterns)
- Schema v2 compliance (institutional schemas; avoid banned schemas)
- Security (injection risks, credential handling)

**Source of truth:** `prisma/schema.prisma`. Any schema changes require explicit approval (see “Before ANY Database Change”).

### Quant Forecasting Code Reviewer
**Location:** `.claude/skills/quant-reviewer.md`
**Trigger:** Modifying ML pipelines, feature engineering, or forecasting logic

Reviews:
- AutoGluon pipelines and configuration
- Model stacking/ensemble architectures
- Data leakage and look-ahead bias
- Technical indicator implementations
- Monte Carlo methods and reproducibility
- Schema v2 compliance (no raw/gold/silver)
- Drift detection patterns

### Usage Pattern

```python
# Invoke via Task tool with subagent_type="Explore"
Task(
  subagent_type="Explore",
  description="[Agent] review",
  prompt="[Agent prompt from skill file]\n\nFiles to review:\n- [file1]\n- [file2]"
)
```

**Workflow:**
1. Make changes to code
2. Delegate to appropriate reviewer agent (read-only analysis)
3. Agent reports findings and suggestions
4. Decide what to fix or improve

---

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
