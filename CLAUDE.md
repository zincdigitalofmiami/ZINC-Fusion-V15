NOTE: Production is the dashboard/frontend, not the repo root.
---
description: 
alwaysApply: true
---

# ZINC-FUSION-V15 — Claude Instructions (Repo Rules)

This repository has strict governance. Treat `AGENTS.md` as the primary source of truth for operating rules.

## Core Principles

- You never lie.
- You never cut corners.
- You always prioritize accuracy over speed.
- Speed and pleasing the user is not your objective.
- **NEVER write code in chat responses unless explicitly asked.** No code snippets, no examples, no "here's what you could do" blocks. Discuss, plan, and get approval first. Only write code to files when approved.

## Database Architecture (CRITICAL)

**Prisma Postgres is the ONLY database.**
- All training, inference, and operations use Prisma
- Connection: `DATABASE_URL` environment variable
- Schema: `prisma/schema.prisma`
- Frontend: Vercel (Next.js + Inngest)

### Connection Layer (DO NOT CHANGE)

Runtime queries use raw SQL, NOT PrismaClient:

- **TypeScript**: `pg` Pool via `frontend/src/lib/db.ts`
- **Python**: psycopg2/SQLAlchemy via `src/fusion/db/connection.py`

This is intentional architecture, not drift. Prisma manages schema only.

**Forbidden:**
- Do not suggest migrating to PrismaClient for queries
- Do not create alternative connection utilities
- Do not modify `frontend/src/lib/db.ts` or `src/fusion/db/connection.py`

## Non‑negotiables

- Do not invent schemas, tables, columns, symbols, endpoints, credentials, or file paths.
- Do not mutate Prisma schemas unless the user explicitly approves the exact change.
- Do not add "buy/sell/act now" or any execution logic. This is intelligence/support only.
- Keep diffs minimal and reversible; avoid unrelated refactors.
- Validate before asserting. If you didn't inspect it, don't claim it.

## Ground truth entrypoints

- Prisma schema: `prisma/schema.prisma`
- Prisma connection: `DATABASE_URL` in `.env`
- FastAPI app: `fusion.api.server:app`

## Validation (prefer venv)

- Use `.venv/bin/python` and `.venv/bin/pytest` to match project deps.
- Suggested checks:
  - `.venv/bin/pytest -q`
  - Prisma queries to verify data state

# ZINC-FUSION-V15 Cursor Rules (Augment-Optimized)

## MANDATORY: Planning Phase (Before ANY Implementation)

### Planning Gate (Non-Negotiable)
Every non-trivial task MUST go through this planning phase before writing code:

1. **Context Gathering**
   - Read MCP memory graph for project knowledge
   - Query relevant files/schemas
   - Check git status for current state

2. **Scope Definition**
   - State the goal in one sentence
   - List files that will be modified (max 5 per change)
   - Identify dependencies and prerequisites
   - Estimate number of atomic steps

3. **Risk Assessment**
   - Is this reversible? (Y/N)
   - Does it touch database schema? (requires explicit approval)
   - Does it cross schema boundaries? (mkt → training, etc.)
   - What could break?

4. **Plan Output (Required Format)**
   ```
   ## Task: [one-line goal]
   ## Scope: [files to modify]
   ## Steps:
   1. [atomic step 1]
   2. [atomic step 2]
   ...
   ## Validation: [how to verify success]
   ## Risks: [what could go wrong]
   ```

5. **Approval Gate**
   - For schema changes: STOP and get explicit user approval
   - For multi-file changes: present plan and confirm
   - For single-file edits: proceed with validation

### Skip Planning Only If:
- Single line fix (typo, obvious bug)
- User explicitly says "just do it"
- Pure research/exploration task

## Augment-Style Reliability Principles

### 1. Codebase Awareness (Index Everything)
- Use @codebase to search before implementing
- Check existing patterns before writing new code
- Understand file relationships and imports
- Never guess at function signatures - look them up

### 2. Stepwise Verification
- Break complex tasks into atomic steps
- Verify each step before proceeding
- If a step fails, stop and diagnose before continuing
- Never batch multiple changes without intermediate validation

### 3. Schema-First Development
- Query the database to confirm table/column existence
- Check Prisma schema before writing queries
- Validate INSERT columns match target table
- Use MCP postgres server for live schema inspection

### 4. Context Preservation
- Use MCP memory server to persist decisions across sessions
- Document assumptions explicitly
- Track what was verified vs assumed
- Reference prior conversations when relevant

## Core Operating Principles

### Accuracy Over Speed
- Never prioritize speed over correctness
- Verify before asserting - if you didn't inspect it, don't claim it exists
- Read files before modifying them
- Query database state before making claims about data

### Atomic Changes
- Make small, focused changes (one logical change per edit)
- Keep diffs minimal and reversible
- Avoid unrelated refactors in the same change
- Complete one task fully before starting another

### Validation-First Workflow
1. **Read** the relevant files/schemas first
2. **Verify** current state matches expectations
3. **Plan** the minimal change needed
4. **Implement** one atomic change
5. **Validate** the change worked (run tests, query DB)

## Project-Specific Constraints

### Database Architecture (CRITICAL)
- **Prisma Postgres is the ONLY database**
- Connection: `DATABASE_URL` in `.env`
- Schema: `prisma/schema.prisma`
- Always use `.venv/bin/python` for Python scripts

### Forbidden Actions
- Do NOT invent schemas, tables, columns, symbols, endpoints, or file paths
- Do NOT mutate Prisma schemas without explicit user approval
- Do NOT add "buy/sell/act now" or execution logic
- Do NOT create schemas named: `raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`
- Do NOT write code in chat responses unless explicitly asked

### Schema Boundaries (v2 Architecture)
**Landing (append-only):** `mkt`, `econ`, `alt`, `pos`, `supply`
**Derived (computed):** `features`, `training`
**Output (versioned):** `model`, `forecasts`, `analytics`
**Governance:** `metadata`, `ops`

### Before ANY Database Change
1. State intent: "I am going to modify X for reason Y"
2. Define scope: Files affected, tables touched
3. Declare reversibility: Can this be reverted cleanly?
4. Wait for explicit approval

## Reliability Patterns

### File Operations
- Always read a file before editing it
- Use absolute paths, not relative paths
- Verify parent directories exist before creating files
- Never assume file contents - always inspect first

### Code Changes
- Prefer editing existing files over creating new ones
- Check for existing patterns in the codebase before implementing
- Match existing code style (indentation, naming, structure)
- Add validation/assertions but avoid over-engineering

### Testing & Validation
- Run `.venv/bin/pytest -q` after Python changes
- Use Prisma queries to verify database state
- Check that changes don't break existing functionality
- Validate outputs match expected schema

### Error Handling
- Fail loudly on missing tables/columns
- No implicit DDL creation during training
- Scripts should error on validation failure, not silently continue

## Context Management

### When to Stop and Ask
- Required file/config is missing
- Schema contradicts documentation
- Request implies external systems without concrete paths
- Ambiguous requirements that could go multiple ways

### What to Verify Before Acting
- Table/column exists in Prisma schema
- File path exists and is readable
- Environment variables are set
- Dependencies are installed

## Specialist Taxonomy (Big 11)
When tagging or routing data, use these canonical bucket names:

`crush`, `china`, `fx`, `fed`, `tariff`, `energy`, `biofuel`, `palm`, `volatility`, `substitutes`, `trump_effect`

### Specialist Model Types (v3 Architecture)

> **CRITICAL**: Each specialist has a UNIQUE, CUSTOM-BUILT model architecture.
> These are NOT generic AutoGluon fits. Each was meticulously crafted for its domain.
> Specialists produce SIGNALS (no horizons) that feed into Core as input features.
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

**Code**: `src/fusion/specialists/` | **Artifacts**: `models/specialists/{bucket}/`

### Specialist Signal Contract
- Specialists are **signal generators**, NOT forecasters
- Output: `signal_1` (required), `signal_2` (optional), `confidence` (optional)
- NO horizons - Core owns all horizon forecasting (5d, 21d, 63d, 126d)
- Signals stored in `training.specialist_signals_1d`

## SoT v2 Training Architecture (Primary)

**SoT v3** is the canonical training model architecture for this project.

### Model Stack (19 Models)
- **L0 Core:** 4 models (`zinc-fusion-v2-core-h{5,21,63,126}d`)
- **Specialists:** 11 signal generators (NO horizons - see architecture table above)
- **L1 Meta:** 4 models (stacked ensemble per horizon)
- **L2/L3:** Calibration (CQR) + Risk Engine (Monte Carlo)

> **v3 CHANGE**: Specialists produce SIGNALS that feed into Core as input features.
> They do NOT produce OOF forecasts. Core owns all horizon forecasting.

### Table Layout (Schema-Aligned)
| Phase | Tables | Pattern |
|-------|--------|---------|
| Training OOF | 1 table | `training.oof_core_1d` with `horizon_days` column |
| Specialist Signals | 1 table | `training.specialist_signals_1d` (signal_1, signal_2, confidence) |
| Meta Inputs | 1 table | `training.meta_inputs_1d` with `horizon_days` column |
| Production | 4 tables | `forecasts.production_{H}d_1d` (separate per horizon) |

### Key Principle
19 models write to ~7 tables. Specialists produce horizon-agnostic signals; Core and Meta handle all horizon forecasting.

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
`hyperparameters={...}` allowlist (model names may omit the “Model” suffix). The
full allowlist is maintained in `Docs/CORE_TRAINING_SPEC_LOCKED.md`.

AutoGluon trains the full allowlist, ranks models on internal
validation/backtests, and typically selects a **WeightedEnsemble** as best.

Verification:
- `python -m fusion.core_training.run_pipeline --skip-matrix --horizons 5`
- `python -m fusion.core_training.run_pipeline --skip-matrix`
- Confirm logs show the full allowlist and a WeightedEnsemble selection

### References
- Full catalog: `scripts/v2_training/MODEL_CATALOG.md`
- Training code: `scripts/v2_training/`
- Architecture details: `AGENTS.md` (section: "Active Model Architecture")

## Ground Truth Entrypoints
- Prisma schema: `prisma/schema.prisma`
- Prisma connection: `DATABASE_URL` in `.env`
- FastAPI app: `fusion.api.server:app`
- Primary instructions: `AGENTS.md`

## Instruction Precedence
1. System instructions (highest)
2. AGENTS.md
3. CLAUDE.md
4. README.md
5. Code and tests
6. Notebooks (lowest)

## MCP Server Usage

### Available Servers (Configured)
- **sequential-thinking**: Multi-step reasoning, problem decomposition, hypothesis verification
- **memory**: Knowledge graph for project facts, decisions, architecture (persists across sessions)
- **filesystem**: Sandboxed file operations for `/Volumes/Satechi Hub/ZINC-FUSION-V15`
- **git**: Repository operations, history analysis, branch management
- **Prisma-Local/Remote**: Database schema inspection and Prisma operations

### When to Use MCP (Required)
| Situation | MCP Tool | Action |
|-----------|----------|--------|
| Starting a session | `memory.read_graph` | Load project context |
| Complex multi-step task | `sequential-thinking` | Break down and track reasoning |
| Before database changes | `Prisma` MCP | Verify schema exists |
| Learning something new | `memory.create_entities` | Persist for future sessions |
| Before committing | `git` MCP | Check status, diff, history |

### Memory Graph Bootstrap
At session start, always check: `mcp__memory__read_graph`
This contains: Project architecture, schema contracts, specialist taxonomy, non-negotiables

## Error Recovery Patterns

### If a Change Fails
1. Read the error message completely
2. Query relevant state (file contents, DB schema, test output)
3. Identify the root cause, not just symptoms
4. Propose a fix that addresses the root cause
5. Validate the fix works before claiming success

### If Uncertain
- Ask clarifying questions rather than guessing
- Propose multiple options with tradeoffs
- State assumptions explicitly
- Prefer reversible actions over irreversible ones

### Common Failure Modes to Avoid
- Editing files without reading them first
- Assuming column/table exists without checking
- Using deprecated schema names (raw/gold/silver)
- Making multiple unrelated changes in one edit
- Claiming success without running validation