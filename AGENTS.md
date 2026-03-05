# ZINC-FUSION-V15 Workspace Guide

---
## 🚨 MANDATORY SESSION STARTUP — NO EXCEPTIONS

Before ANY response, code, or analysis — Claude MUST execute this checklist in order:

1. **Memory MCP** — Search memory for prior decisions, corrections, and architect context relevant to the current task. Query: task keywords + "ZINC-FUSION" + "Kirk".
2. **Plan before acting** — Think through the task step-by-step before making changes.

**If memory MCP is unavailable, explicitly state it and continue with local evidence.**

This is not optional. This is not situational. This runs every session.

---

## What This Project Is

Commodity procurement forecasting system for ZL (soybean oil futures). Core predicts the future ZL futures contract price. L2/L3 calibration layers wrap that price forecast with probability, rendered as **horizontal Target Zones** on the dashboard (e.g. "ZL has an 88% chance of hitting 48.52 by July 7th"). Probability is always derived from three named sources: Monte Carlo (10,000 runs), pinball loss calibration, and MAE/accuracy %. Intelligence only — no execution or trade logic.

**Client:** US Oil Solutions

## Tech Stack

- **Database:** Prisma Postgres (cloud-hosted, 12 schemas)
- **Frontend:** Next.js on Vercel with Inngest serverless functions
- **Backend:** Python 3.11, FastAPI, psycopg2
- **ML:** AutoGluon (CPU-only), custom specialist models
- **Package Manager:** uv (Python), npm (`frontend/` + `config/` for Prisma CLI)
- **Testing:** pytest (Python), npm test (frontend)
- **Tracking:** MLflow (local)

## Repository Layout

- Root (`/`) — Python ML pipeline
- `frontend/` — Next.js dashboard (deployed to Vercel)
- `prisma/schema.prisma` — Database schema (single source of truth)

There is intentionally no root `package.json`.
Prisma CLI dependencies live in `config/package.json`.
All frontend npm commands use `--prefix frontend`; all Prisma CLI commands use `--prefix config` (or `scripts/prisma.sh`).

## Data Sources

Full catalog of all data source URLs (USDA, FRED, EIA, EPA, CFTC, BLS, NOAA, White House, foreign gov, commercial) with V15 integration status and priority fixes:
[docs/data-source-catalog.md](docs/data-source-catalog.md)

## Database

Prisma manages schema and migrations only. Runtime queries use `pg` Pool (TypeScript) and psycopg2 (Python). Do not use PrismaClient for runtime queries.

**12 Schemas:** `mkt`, `econ`, `alt`, `pos`, `supply`, `features`, `training`, `model`, `forecasts`, `analytics`, `ops`, `vegas`

**Banned schemas:** `raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`, `archive`

## Model Architecture

- **L0 Core = PRICE PREDICTOR:** 4 AutoGluon TimeSeriesPredictor ensembles (5d/21d/63d/126d), each training a 19-model zoo. Core predicts ONE number: the future ZL futures contract price. No quantile outputs from core.
- **Specialists:** 11 signal generators (domain-specific, no horizons)
- **L1 Meta:** Core models consume specialist signals as input features (no separate meta-learner)
- **L2/L3 = PROBABILITY ENGINE:** Calibration + Monte Carlo risk (10,000 runs). Takes core's price prediction and wraps it with probability: "ZL has an 88% chance of hitting XX.XX by July 7th." Output rendered as horizontal **Target Zones** on the chart. Probability derived from: Monte Carlo (10k runs) + pinball loss + MAE/accuracy %. Never use: cones, bands, funnels.

### L0 Core Model Zoo (19 active models per horizon, CPU-only)

Defined in `src/fusion/core_training/config.py` → `MODEL_ZOO_FROZEN`. No presets, no time limits, explicit allowlist only.

| Category | Models | Status |
|----------|--------|--------|
| Baselines (5) | Naive, SeasonalNaive, Average, SeasonalAverage, Zero | Active |
| Statistical (10) | ETS, AutoETS, AutoARIMA, AutoCES, Theta, DynamicOptimizedTheta, NPTS, ADIDA, Croston, IMAPA | Active |
| Tabular TS (3) | DirectTabular, PerStepTabular, RecursiveTabular | Active |
| Foundation (1) | Chronos2 (120M-param, zero-shot, covariate-aware) | Active (in MODEL_ZOO_FROZEN — see Correction #5) |
| Deep/ML (7) | DeepAR, TFT, DLinear, PatchTST, SimpleFeedForward, TiDE, WaveNet | Disabled (macOS ARM) |
| Pretrained (2) | Chronos (original), Toto | Disabled |

AutoGluon trains all active models and selects a WeightedEnsemble. Artifacts in `models/core_v2/{horizon}d/`.
Source of truth: `config.py` → `MODEL_ZOO_FROZEN` (frozenset, currently 19 models).

- **Target:** Future ZL futures contract price (`close.shift(-horizon)`), NOT returns. Columns named `target_price_{h}d`.
- **Metric:** MAE (point forecast accuracy). Core optimizes for predicting the price, not a distribution.
- **Output:** Single `predicted_price` per horizon — the core model's price forecast. No quantile columns (p30/p50/p70) from core.
- **Covariates:** All OBSERVED (no known future values)
- **Validation:** 4 expanding windows
- **Frequency:** Business day (`B`)

### Specialist Buckets (Big-11)

Each specialist outputs `(signal_1, signal_2, confidence)` per date to `training.specialist_signals_1d`. These are merged into `training.matrix_1d` as core input features.

| Bucket | Model Type | Implementation | Signal Contract |
|--------|-----------|----------------|-----------------|
| crush | `gbm` | sklearn GradientBoostingRegressor | Crush margin z-score + momentum |
| china | `gbm` | sklearn GradientBoostingRegressor | Demand outlook + Brazil competition |
| substitutes | `rf` | sklearn RandomForestRegressor | Substitution pressure + richness |
| fx | `ardl` | statsmodels ARDL | FX pressure index + carry |
| fed | `ridge` | sklearn Ridge | Rates regime + change |
| tariff | `tree` | Rule-based + EPU analysis | Tariff risk + EPU spike |
| energy | `var` | statsmodels VAR + IRF | Energy spillover + momentum |
| biofuel | `nlp_ema` | NLP sentiment + EMA | Policy pressure + trend |
| palm | `ecm_ridge` | statsmodels ECM + sklearn Ridge | Cointegration + mean reversion |
| volatility | `garch` | arch GJR-GARCH(1,1) | Conditional variance z-score + regime |
| trump_effect | `event_study` | Event intensity scoring | Intensity + volatility impact |

### Data Pipeline

1. **Feature Matrix:** ~213+ features in `training.matrix_1d` (FRED macro, FX, commodity, weather, supply, positioning, specialist signals)
2. **Specialist Signals:** 33 columns (11 buckets x 3: signal_1, signal_2, confidence)
3. **Core Training:** AutoGluon trains on full matrix including specialist signals
4. **OOF Predictions:** Written to `training.oof_core_1d` (`predicted_price` per horizon). These are ZL futures contract prices — not returns. L2/L3 calibration layers then wrap these with probability to produce Target Zones on the dashboard.

### Country-Level Export Data = Geopolitical Signal Layer

USDA FAS Export Sales reports (`supply.usda_exports_1w`) contain **country-level** purchase data for soybeans, soybean oil, and soybean meal. This is NOT just aggregate demand — it is a granular geopolitical intelligence feed.

**Why country-level matters for the model:**
- **Demand shifts by country** are early signals of policy changes. When a country's purchases collapse or spike YoY, it often precedes or coincides with tariffs, sanctions, trade agreements, or domestic regulation.
- **China specialist** directly consumes China's share of soy complex purchases — outstanding sales, accumulated exports, YoY comparison.
- **Trump_effect specialist** can correlate country-level purchase anomalies with lobbying, sanctions, executive orders, and "regulations that don't make sense" — e.g., a country whose imports drop despite no economic reason points to political interference.
- **Crush specialist** uses oil/meal destination flows to understand global crush economics — where is oil going vs. meal vs. beans? Country ratios reveal processing capacity shifts.
- **Tariff specialist** uses bilateral trade flow disruptions as direct signal — when purchases reroute (e.g., China drops, Pakistan/Egypt surge 4x), that's trade diversion from tariff impact.

**Ingestion depth:** Every country in the report is captured with 6 columns: outstanding sales (this week + YoY), accumulated exports (this week + YoY), and next marketing year outstanding. Region subtotals and individual country rows are both stored. Abbreviated country names are resolved to full names via lookup table.

**Source reports:** Soybeans, Soybean Oil, Soybean Meal pages at `apps.fas.usda.gov/export-sales/`

## Claude Hard-Coded Corrections (DO NOT REPEAT THESE ERRORS)

<!-- LAST UPDATED: 2026-02-19 by Kirk (architect) -->

These are verified facts burned in from architect corrections. Claude must never contradict these.

### 1. Specialist Count: ALWAYS 11, NEVER 10
The Big-11 specialists are: crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, **trump_effect**.
`trump_effect` (event_study model) is the 11th. It is real, it is active, it matters — especially in current tariff/trade environment.
Any code, doc, or statement that says "10 specialists" is WRONG.
Source of truth: `src/fusion/specialists/base.py` → `SPECIALIST_BUCKETS` list (11 items).

### 2. Core = Price Predictor, Probability = L2/L3 (FIXED 2026-02-19)

**Core Architecture (locked):**
- Core outputs a single `predicted_price` per horizon — the ZL futures contract price forecast.
- Core metric: **MAE** (point forecast accuracy). NOT WQL.
- Core does NOT produce quantiles. No p30/p50/p70 from core. No `quantile_levels` in core config.
- OOF table (`training.oof_core_1d`) stores `predicted_price` and `target_value` — both are ZL futures prices.

**Probability comes from L2/L3 calibration layers:**
- Takes core's `predicted_price` as input.
- Monte Carlo (10,000 runs) + pinball loss + MAE/accuracy % produce probability ranges.
- These become the **Target Zones** on the dashboard.

**Banned words (never use these):**
- **"cones"** — banned. Do not use. Ever. For anything.
- **"probability cone"** — banned.
- **"confidence band"** — banned.
- **"cents/lb"** — banned. Use "ZL futures contract price" or just "price."

**Correct visualization language:**
- The forecast output renders as **horizontal "Target Zones"** on the chart — price levels, not shapes or bands.
- These are implemented as horizontal lines at key price levels, visually similar to support/resistance levels on a trading chart (see: MES1 15m chart reference with orange/gray horizontal lines).
- NOT a wedge, NOT a funnel, NOT a cone. Flat horizontal zones at discrete price levels.

**Correct probability language (for chart UI and stakeholder-facing copy):**
- "ZL has an 88% chance of hitting XX.XX by July 7th" — this is the approved phrasing.
- Probability is derived from: Monte Carlo simulation + pinball loss calibration + MAE/accuracy %.
- The three sources of that probability statement are always: (1) Monte Carlo (10,000 runs), (2) pinball loss score, (3) MAE/accuracy %.
- These three terms — **Monte Carlo, pinball, MAE/accuracy %** — are the approved chart/app language.

**Correct language summary:**
- ✅ "Target Zones"
- ✅ "predicted_price" (core output)
- ✅ "ZL futures contract price"
- ✅ "ZL has an X% chance of hitting XX.XX by [date]"
- ✅ "Monte Carlo", "pinball", "MAE/accuracy %"
- ❌ "cones", "probability cone", "confidence band", "funnel", "cents/lb"

### 3. Target Is ZL Futures Price, NOT Returns (FIXED 2026-02-19)
- `create_target_columns()` in `build_matrix.py` uses `close.shift(-horizon)` — the actual future ZL futures contract price.
- Target columns are named `target_price_{h}d` (NOT `target_ret_*`).
- The core model predicts the ZL futures price. L2/L3 wraps it with probability for Target Zones.
- Never revert to `pct_change()` returns — price targets align with Chronos2 pretraining, procurement use case, and Target Zone visualization.
- **Why this matters:** Core output `predicted_price=48.52` means "ZL will be at 48.52." L2/L3 adds "88% chance by July 7th." If the target were returns, the core output would be a meaningless percentage.

### 4. Raw Crush Features ≠ Crush Specialist Output
- `board_crush`, `soy_oil_share`, `zl_cl_ratio`, etc. in the matrix come from `analytics.board_crush_1d` via `load_spread_features()` in `build_matrix.py`. These are RAW inputs.
- The crush specialist's GBM output — `sig_crush_1`, `sig_crush_2`, `sig_crush_conf` — is a separate processed signal written to `training.specialist_signals_1d`.
- The dry run matrix had raw crush features but NO specialist signals (table was empty).
- Never conflate the two.

### 5. Chronos2 Is in MODEL_ZOO_FROZEN and IS Active (Table Above Has Been Corrected)
- `config.py` `MODEL_ZOO_FROZEN` includes Chronos2 — it ran in the dry run.
- The model zoo table above now correctly lists Chronos2 as Active. The previous version of this table was wrong — that error is fixed.
- The `config.py` frozen set is the source of truth for what actually trains.
- Chronos2 underperforms on this system because: (a) all covariates are OBSERVED not KNOWN, (b) single item_id = no cross-learning, (c) CPU-only on macOS ARM. Note: target is ZL futures price (not returns), which better aligns with Chronos2 pretraining.

### 6. The Dry Run Context
- The leaderboard results shared were a DRY RUN with NO specialist signals and a dropped/fresh matrix.
- It was a mechanics validation, not a performance benchmark for the full system.
- The dry run used the OLD config (WQL metric, returns target, quantile outputs). All three are now fixed: MAE metric, price target, single predicted_price output.
- Do not compare dry run numbers to the full system's expected performance.

## Workspace Environment Notes

- **Python interpreter**: `.vscode/settings.json` uses the absolute path `/Volumes/Satechi Hub/ZINC-FUSION-V15/.venv/bin/python` — NOT `${workspaceFolder}/.venv/bin/python`. The `${workspaceFolder}` variable fails to expand when the path contains spaces (`Satechi Hub`). Never revert to the variable form.

## Inngest Hardening — 3-Layer Defense (2026-03-04)

A rogue AI changed the RR Inngest `serveHost` to `https://rabid-raccoon.vercel.app`, causing all 25 RR cron jobs to 500 with `"Expected server kind cloud, got dev"`. This triggered cascading retries, 9 duplicate function versions, and an avalanche of queue failures. V15 functions on port 3000 were unaffected (correct sync URL). Three layers now prevent this from ever happening again.

### Port Assignments (LOCKED — do not change)

| Port | App | Purpose |
|------|-----|---------|
| 3000 | ZINC-FUSION-V15 (fusion-jobs) | Next.js dev + Inngest serve |
| 3001 | rabid-raccoon | Next.js dev + Inngest serve |
| 8288 | inngest-dev (Docker) | Inngest dev server |

### Layer 1 — Config Lockdown

Both apps hardened so `serveHost` is only set in actual Vercel production:

- **RR** [`route.ts`] — `serveHost` only when `VERCEL === "1"` AND `VERCEL_ENV === "production"`. `VERCEL_URL` is **never** used. `INNGEST_SERVE_HOST` validated as `http://` or `https://` URL; invalid/missing values silently ignored (no throw).
- **V15** [`frontend/src/app/api/inngest/route.ts`](frontend/src/app/api/inngest/route.ts) — same strict production-only gate with unsafe-host rejection.
- **RR config tests** [`inngest-config.test.ts`] — regression tests covering serveHost logic, env leak scenarios.

### Layer 2 — Guard ([`scripts/inngest_guard.sh`](scripts/inngest_guard.sh))

Static analysis + runtime health checks. Runs before Inngest starts.

| Flag | What it checks |
|------|---------------|
| `--static` | Blocks Vercel URLs in sync config, validates env files |
| `--health` | Confirms correct processes on 3000/3001, `/api/inngest` endpoints return 200 |

Integrated into: `make inngest-guard`, [`scripts/verify.sh`](scripts/verify.sh), [`docker-compose.inngest.yml`](docker-compose.inngest.yml) (comments).

### Layer 3 — Self-Healing ([`scripts/inngest_heal.sh`](scripts/inngest_heal.sh))

Active recovery — detects drift and fixes it automatically.

| Flag | Behavior |
|------|----------|
| `--once` | Single heal pass with retries |
| `--loop` | Continuous monitoring loop |

Capabilities:
- Detects wrong process on 3000/3001 and kills port squatters (`AUTO_KILL_PORT_SQUATTERS=1`)
- Restarts V15/RR dev servers if down or unhealthy
- Verifies inngest-dev container can reach both endpoints
- Retries automatically until all checks pass

### Make Targets

| Target | Action |
|--------|--------|
| `make inngest-guard` | Run static + health guard checks |
| `make inngest-health` | Health-only check |
| `make inngest-up` | Start Inngest with guard pre-check |
| `make inngest-heal` | Single heal pass |
| `make inngest-heal-loop` | Continuous self-healing loop |

### Rules (MANDATORY)

1. **NEVER** let `VERCEL_URL` leak into Inngest serve host for local dev
2. **NEVER** sync an app to a `*.vercel.app` URL from the dev server
3. **NEVER** change port assignments (3000/3001/8288) — they are hardcoded across both projects
4. Run `make inngest-guard` before any Inngest work
5. If jobs start 500ing, run `make inngest-heal` before investigating code

## Vercel Connection & Protected Preview Access (LOCKED — 2026-03-05)

Canonical deployment connection for this repo:
- Vercel project: `zinc-fusion-v15`
- Root directory: `frontend`
- Production source branch: `main`

Use Vercel CLI for protected preview diagnostics (not localhost app ports):
- Connectivity check: `vercel curl /api/auth/check --deployment <preview-url>`
- API check pattern: `vercel curl /api/<route> --deployment <preview-url>`

There are two independent gates on preview deployments:
1. Vercel Deployment Protection
2. App auth gate (`/api/auth/login`)

Deployment Protection bypass contract:
- Header/query key: `x-vercel-protection-bypass`
- Value source: `VERCEL_AUTOMATION_BYPASS_SECRET`
- Never commit or print raw bypass secret values in repo files

If CLI requests fail with `No automation bypass token found in protection bypass settings`:
1. Open Vercel project settings for `zinc-fusion-v15`
2. Create/confirm "Protection Bypass for Automation"
3. Confirm automation secret is available to the calling environment

API endpoint method contract for smoke checks:
- `GET`: `/api/zl/forecast-targets`, `/api/market-drivers`, `/api/zl/brief`, `/api/sentiment/*`, `/api/vegas`
- `POST` only: `/api/policy/briefing`, `/api/policy/section-brief`

Rules:
1. **NEVER** use `localhost:3000` as a stand-in for Vercel preview validation
2. **NEVER** commit bypass secrets or temporary auth passwords
3. Always pass explicit `--deployment <preview-url>` to prevent cross-project confusion

## Core Rules

1. No fabrication — never invent schemas, tables, files, or endpoints
2. No execution logic — intelligence only, no buy/sell/act
3. No silent schema changes — declare and get approval
4. Read before editing — always read files before modifying
5. Verify before claiming done — lint, test, re-read
6. Minimal changes — fix root causes, avoid unrelated refactors
7. Forward fill is OFF by default — requires explicit approval
8. Say "I don't know" when uncertain
9. Before pushing, open a PR and run the `run-review` skill (CodeScene) — fix any flagged issues before merging

## MCP Server Rules (Workspace-Only — `.vscode/mcp.json`)

Three MCP servers run via Docker SSE (see `docker-compose.mcp.yml`), shared by all agents (Copilot, Roo, Claude):
- **memory** → `http://localhost:18100/sse`
- **sequential-thinking** → `http://localhost:18101/sse`
- **context7** → `http://localhost:18102/sse`

Start/stop with `make mcp-up` / `make mcp-down`. All agents must follow these rules without exception.

### Banned MCP Servers
- **Serena** (`serena start-mcp-server`, port 24282) — was auto-started by an AI agent on 2026-03-04 with no authorization. Killed. Not used. Not wired into any config. Do NOT reinstall, re-enable, or reference it.

### 8 Non-Negotiable Rules

1. **THINK FIRST** — Must plan before writing any code. No exceptions.
2. **MEMORY FIRST** — Must check memory at conversation start, must store decisions immediately during conversation.
3. **SOURCE CHECK FOR DOCS** — No relying on stale assumptions for external APIs; verify against current primary docs when needed.
4. **NO GOING ROGUE** — No unrequested changes, no surprise refactors, no "while I'm here" improvements.
5. **CONFIRM DESTRUCTIVE ACTIONS** — Must state intent and wait before deleting, overwriting, migrating, etc.
6. **ONE TASK AT A TIME** — Finish what was asked before touching anything else.
7. **REPORT** — State every file touched and every change made.
8. **NO GUESSING** — Don't know? Say so. Check memory and ask Kirk.

### Mandatory Execution Order

Every task follows this sequence:

```
Memory(search) → Plan → Execute → Memory(store) → Report
```

- **Memory search** — Check the knowledge graph for prior decisions, corrections, and context before doing anything.
- **Plan** — Work the approach step-by-step. No cowboying.
- **Execute** — Implement the plan. One task at a time.
- **Memory store** — Persist any new decisions, corrections, or architectural facts to the knowledge graph immediately.
- **Report** — List every file touched, every change made, every decision taken.
