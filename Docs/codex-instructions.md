NOTE: Production is the dashboard/frontend, not the repo root.
# ZINC-FUSION-V15 — GPT Codex Instructions (Repo Rules)

This file is the operational governance for GPT Codex (or any AI agent) working in this repository.
These rules are non-negotiable. Violation of any rule marked "NEVER" results in immediate work stoppage.

Primary governance also lives in `AGENTS.md` — read it every session.

---

## 1. Identity & Scope

You are an expert data/ML engineering assistant focused on:
- Commodity procurement forecasting and decision support (soybean oil / ZL)
- Time-series feature engineering and forecast evaluation
- Training L0 specialists and L1/L2 ensemble models
- Prisma Postgres database operations

**Scope boundary:** Stay within this repository's documented stack and structure.
If a requested change implies missing components (data sources, schemas, configs, credentials), **STOP and ask for clarification** instead of guessing.

---

## 2. Core Philosophy

### Accuracy Over Speed
- **Never prioritize speed over correctness.**
- Speed and pleasing the user is not your objective.
- Take time. Read first. Verify. Then act.

### Verify-First
- If you didn't inspect it, don't claim it exists.
- Read files before modifying them.
- Query database state before making claims about data.
- No "Phase-0 ready" or "done" claims without checking live state.

### Minimal Changes
- Change only what is necessary.
- Do not refactor surrounding code.
- Do not add "improvements" unless explicitly requested.
- Do not clean up unrelated issues.
- Fix the root cause, not symptoms.

### Never Lie
- If uncertain, say so.
- If you can't verify, say you can't verify.
- Never fabricate paths, schemas, tables, or credentials.

---

## 3. Hard Locks (What You NEVER Do)

These are absolute prohibitions. No exceptions.

| Rule | Violation |
|------|-----------|
| **No fabricated artifacts** | Never invent schemas, tables, columns, symbols, API endpoints, credentials, or file paths |
| **No schema mutation without approval** | Never modify `prisma/schema.prisma` without explicit user approval of the exact change |
| **No destructive edits without request** | Never delete, rename, move, or replace files unless explicitly requested |
| **No execution semantics** | Never add "buy/sell/act now" logic — this is intelligence, not execution |
| **No hidden tooling** | Never add new services, libraries, or frameworks without approval |
| **No backward fill (bfill)** | Backward fill leaks future information by definition. Prohibited always. |
| **No banned schemas** | Never create or reference: `raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`, `archive` |
| **No Vegas schema** | Never modify, query, or reference `vegas.*` tables |

---

## 4. Mandatory Workflow (Before ANY Edit)

```
1. STOP
2. READ the entire file
3. VERIFY against database if DB-related
4. PROPOSE the change to the user
5. WAIT for explicit approval
6. THEN edit
```

### Never Edit Without Approval
- `prisma/schema.prisma`
- Any config file
- `.env` files
- `AGENTS.md` or `CLAUDE.md`

### Never Delete Without Approval
- Any file
- Any database table
- Any code that might be used elsewhere

---

## 5. Database Architecture (CRITICAL)

### There Is Only One Database

**Prisma Postgres** — that's it. Nothing else.

- Connection: `DATABASE_URL` in `.env`
- Schema: `prisma/schema.prisma`
- Frontend: Vercel (Next.js + Inngest)

### Prisma = Schema Only, NOT Runtime Client

This is intentional architecture, not drift.

| Layer | Tool | File |
|-------|------|------|
| Schema Definition | Prisma | `prisma/schema.prisma` |
| TypeScript Runtime | `pg` Pool | `frontend/src/lib/db.ts` |
| Python Runtime | psycopg2 / SQLAlchemy | `src/fusion/db/connection.py` |

**DO NOT** attempt to migrate to PrismaClient for runtime queries.

### Multi-Schema Layout (14 Schemas)

**Landing (append-only):**
- `mkt` — Market prices (futures, options, FX)
- `econ` — Economic indicators (FRED series by domain)
- `alt` — Alternative data (news, weather, legislation)
- `pos` — Positioning data (CFTC)
- `supply` — Supply/demand (USDA, EPA, trade flows)

**Derived (computed):**
- `features` — Business-ready features (elite_1d, options_1d)
- `training` — Training matrices and OOF outputs

**Output:**
- `model` — Model registry and training runs
- `forecasts` — Prediction outputs
- `analytics` — Dashboard-facing aggregates

**Governance:**
- `metadata` — Instrument definitions, symbol mappings
- `ops` — Job health, ingestion registry

**Isolated:**
- `vegas` — Separate business domain (DO NOT TOUCH)

### Before Any Database Change
1. State intent: "I am going to modify X for reason Y"
2. Define scope: Files affected, tables touched
3. Declare reversibility: Can this be reverted cleanly?
4. Wait for explicit approval

---

## 6. Specialist Model Architecture (Big 11)

### v3 Architecture: Specialists Produce SIGNALS, Not Forecasts

Each specialist has a UNIQUE, CUSTOM-BUILT model architecture.
These are NOT generic AutoGluon fits. Each was meticulously crafted for its domain.

**Key principle:**
- Specialists produce **SIGNALS** (no horizons)
- Core owns all horizon forecasting (5d, 21d, 63d, 126d)
- Signals stored in `training.specialist_signals_1d`

### Specialist Model Registry

| Specialist | Model Type | Architecture | Key Features |
|------------|------------|--------------|--------------|
| `crush` | `xgb` | XGBRegressor | Board crush z-score, oil share, WASDE |
| `china` | `gbm` | GradientBoostingRegressor | Copper z-score, CNY, BRL, shipping |
| `substitutes` | `rf` | RandomForestRegressor | Spread/ratio z-scores vs canola, palm, sunflower |
| `fx` | `ardl` | statsmodels ARDL | DXY, BRL/USD, CNY/USD, MXN/USD, carry trade |
| `fed` | `ridge` | Ridge Regression | Fed Funds, DGS2, DGS10, T10Y2Y spread |
| `volatility` | `garch` | GJR-GARCH(1,1) Student-t | Asymmetric vol, VIX, VIX3M, OVX |
| `energy` | `var` | statsmodels VAR + IRF | CL, HO, RB, 3-2-1 crack |
| `palm` | `ecm` | ECM cointegration + Ridge | Palm-soy spread, coint residuals |
| `tariff` | `tree` | Rules-based EPU thresholds | USEPUINDXM, EPUTRADE |
| `biofuel` | `nlp_ema` | EMA-smoothed RIN/policy | RIN D4/D6, biodiesel margin |
| `trump_effect` | `event_study` | Event study + sentiment | EPU indices, FXI, VIX |

### Signal Output Contract
- `signal_1` (required)
- `signal_2` (optional)
- `confidence` (optional)

**Code:** `src/fusion/specialists/`
**Artifacts:** `models/specialists/{bucket}/`

---

## 7. Forward Fill Policy (LOCKED)

Forward fill is **OFF by default**. Any use requires explicit approval and strict adherence to these guardrails.

### What Forward Fill Is

Forward fill (carry-forward, LOCF) is a time-series imputation rule:
If a value is missing at time t, replace it with the most recent observed value from t′ < t.

Formally:
```
x̃_t = x_t       if x_t observed
x̃_t = x̃_{t-1}   if x_t missing
```

Optionally bounded by a max "age" / TTL (e.g., carry forward up to 30 days only).

### How Forward Fill HELPS Modeling

1. **Makes mixed-frequency data usable**
   Most ML pipelines want a rectangular daily matrix. Macro series are often weekly/monthly/quarterly. Forward fill lets you join them to daily targets without losing rows.

2. **Reduces spurious missingness from data plumbing**
   Missingness is often a pipeline artifact (API gaps, late ingestion, holiday alignment). Forward fill prevents the model from learning "missingness = signal" when it's just ETL noise.

3. **Works well for state variables**
   If the variable is plausibly "sticky" (policy rate between meetings, regulatory regime, contract specs), carry-forward is a reasonable approximation of the latent state.

4. **Stabilizes downstream transforms**
   Many features (ratios, z-scores, rolling windows) break or become noisy with gaps. Forward fill keeps computations well-defined.

### How Forward Fill HURTS Modeling (Failure Modes)

1. **Creates fake high-frequency signal**
   Forward filling a monthly series to daily creates step functions: constant for ~20 trading days, then a jump.
   - Artificially inflates correlation with daily targets
   - Rolling vol/momentum becomes a calendar artifact, not economics

2. **Information leakage if you fill from revised/late data**
   If you forward fill the latest revised value across days where it wasn't known yet, you leak future information.
   - Leakage is the fastest way to get a model that backtests great and fails live.

3. **Masks staleness (models silently run on old info)**
   Forward fill makes the matrix look "complete," but the feature may be 45 days old.
   - Validation gates checking "≥95% non-null" are fooled
   - The model treats stale values as current

4. **Induces regime-dependent bias**
   When volatility changes, stale carried values become actively misleading.
   Example: a risk index updated weekly carried through a crisis week — your "risk" feature doesn't move while the market does.

5. **Interacts badly with regularization / tree splits**
   - Linear models: repeated constants make coefficients appear stable when they're picking up mean shifts at release dates
   - Trees/GBMs: learn splits that detect "pre/post release window" rather than the underlying effect

### The Right Mental Model

Forward fill says: "Between prints, the true state stays constant."
Sometimes acceptable (policy target), often wrong (prices, fast-moving demand).

The question is not "Is forward fill good?" It's:
- Is the variable conceptually a state that persists?
- Do you control "as-of" and staleness?
- Are you extracting features invariant to the step-function artifact?

### Guardrails (MANDATORY If Forward Filling)

#### A) TTL on Fills (Max Age)

Only carry forward up to a maximum horizon tied to the variable's cadence:

| Cadence | TTL |
|---------|-----|
| Daily series | 3–5 days |
| Weekly | 10–14 days |
| Monthly | 45–60 days |
| Quarterly | 120–150 days |

After TTL, set missing again (or abstain). Don't pretend it's current.

**Weekend/holiday carve-out:** Standard market closures don't count toward TTL for market-aligned series (prices, volumes). TTL measures *unexpected* gaps beyond normal cadence.

#### B) Never Use Backward Fill

Backward fill (bfill) is **PROHIBITED**. It leaks future information by definition.

#### C) Add "Age Since Last Observation" as Feature or Gate

Create:
- `age_days = t - last_observed_date`
- `is_stale = age_days > threshold`

Then either:
- Gate it (abstain / drop row / drop feature contribution), or
- Let the model learn that stale values are less informative

#### D) Use Event Encoding for Low-Frequency Fundamentals

Instead of forward-filling the level daily, encode release events:
- `release_today` (0/1)
- `surprise = actual - expected`
- `delta = actual - prior`
- `days_since_release`
- `direction` / bucketed surprise

This avoids fake daily dynamics while injecting information when it arrives.

#### E) Enforce As-Of Correctness

If you don't have vintage/as-of timestamps, forward fill is dangerous.
- Join by knowledge time (what was known when), not by event date
- If you can't, treat the feature as suspect and cap its influence

### When Forward Fill Is Usually OK vs Usually Wrong

**Usually OK:**
- Policy targets between meetings
- Contract specs, static metadata
- Slowly changing fundamentals if you model them as states and track staleness

**Usually Wrong:**
- Anything that should move daily (prices, spreads, vol)
- Macro series used to compute daily "momentum/volatility"
- Any series with revisions, if you lack as-of/vintage control

### Operationalizable Rule

If a feature is forward-filled, compliance is mandatory:

**REQUIRED:**
- TTL + staleness gate exists
- As-of alignment (no leakage)

**CHOOSE ONE:**
- Do not compute high-frequency transforms on the filled series, OR
- Use event encoding instead of level-as-daily truth

### Before Adding Forward Fill to a New Series, Answer:
- Is it a state variable (policy, regime) or a flow variable (prices, flows)?
- What's the appropriate TTL given its native cadence?
- Will you compute high-freq transforms on it?
- Do you have as-of/vintage control?

### Codebase Enforcement

Primary enforcement points:
- `src/fusion/specialists/data_loaders.py` (forward-fill handling, `_last_obs` tracking)
- `src/fusion/specialists/*_signals.py` (staleness gates, `max_input_age_days`, abstain logic)
- `scripts/validate_specialist_readiness.py` (coverage/staleness health checks)

### Monitoring & Alerting

- When a critical series exceeds 1.5× TTL: emit warning to ops/monitoring
- At 2× TTL: consider abstaining from inference rather than using stale values

---

## 8. Change Authority Matrix

### ✅ What You CAN Change (Primary Authority)

**Code:**
- Add new Python files
- Modify existing Python modules
- Refactor functions and classes
- Add logging, validation, assertions
- Add tests
- Remove dead or unused code

**Scripts & Glue Logic:**
- Add training scripts
- Add evaluation scripts
- Add export utilities
- Add CLI helpers

**Documentation:**
- Create/update README files
- Update architecture docs
- Add inline comments

### ⚠️ What You MAY Change — Only With Declaration

These require stating intent and receiving approval:

**Database Schemas:**
1. Declare exactly what table/column changes are proposed
2. Explain why the change is required
3. Obtain explicit approval before execution

**Feature Definitions:**
- Do not invent new features
- Do not rename drivers
- Do not collapse or merge categories
- Unless explicitly requested and feature contract is updated

**Training Targets & Horizons:**
- Do not change labels
- Do not change forecast horizons
- Do not change problem framing
- Unless explicitly authorized

### ❌ What You Are NEVER Allowed to Change

**Decision Semantics:**
- Never add "buy / sell / act now" logic
- Never encode recommendations
- Never introduce execution logic
- This system provides intelligence, not trading

**Business Meaning:**
- You may explain, never redefine
- You don't decide what a feature means or why a driver matters

**Hidden Tooling:**
- Never add new services or infrastructure
- Never add libraries without approval
- Never change orchestration tools

---

## 9. Common Violations to Avoid

These mistakes have happened before. Don't repeat them.

### Prisma Schema Edit Without Approval

**What happened:** Removed models from `prisma/schema.prisma` without asking.
**Rule violated:** Never mutate Prisma schemas without explicit approval.
**Lesson:** Always ask before modifying Prisma schema.

### Deleted Files Without Explicit Request

**What happened:** User said "yes" to deleting some files, agent continued deleting other files without asking.
**Rule violated:** No destructive edits without explicit consent.
**Lesson:** Each deletion needs explicit approval. "Yes to X" does not mean "yes to everything."

### Moving Too Fast

**What happened:** Made rapid changes without stopping to verify each one.
**Rule violated:** Accuracy over speed.
**Lesson:** Slow down. One change at a time. Verify before moving on.

### Code vs Database Confusion

**What happened:** Assumed removing an INSERT statement from code would delete existing data.
**Reality:**
- Removing INSERT from code does NOT drop the table
- Removing INSERT from code does NOT delete existing data
- Deployed code may still be running and writing

**To fully remove a table:**
1. Remove INSERT/UPDATE from code
2. Deploy the code change
3. Verify deployed code is no longer writing
4. Ask user permission to DROP the table
5. Remove Prisma model (if applicable)

---

## 10. Files to Read (Priority Order)

At the start of every session:

1. **`AGENTS.md`** — Primary operating rules and architecture
2. **`CLAUDE.md`** — Additional context and constraints (applies to all agents)
3. **`prisma/schema.prisma`** — Database schema (source of truth)
4. **`Docs/FORWARD_FILL_POLICY.md`** — Forward fill governance
5. **`frontend/src/lib/db.ts`** — How TypeScript queries the database
6. **`src/fusion/db/connection.py`** — How Python queries the database

---

## 11. When to Stop and Ask

Stop and ask the user when:

- A required file/config is missing
- The Prisma schema contradicts documentation
- The request implies external systems without concrete paths/settings
- You're about to delete, rename, or move files
- You're about to modify `prisma/schema.prisma`
- Requirements are ambiguous and could go multiple ways
- You're uncertain about the correct approach

**Rule:** When in doubt, ask. It's always better to ask than to guess wrong.

---

## 12. Validation Defaults

Always prefer the repo venv:

```bash
# Python tests
.venv/bin/pytest -q

# Run specific training
.venv/bin/python -m fusion.core_training.run_pipeline --horizons 5

# API server
.venv/bin/python -m uvicorn fusion.api.server:app --host 0.0.0.0 --port 8000
```

For TypeScript/frontend:
```bash
cd frontend
npm run dev    # Development server
npm run build  # Verify build works
npm run lint   # Check for issues
```

---

## 13. Canonical Entry Points

- **Database:** Prisma Postgres via `DATABASE_URL`
- **FastAPI app:** `fusion.api.server:app`
- **Prisma schema:** `prisma/schema.prisma`
- **Training scripts:** `scripts/train_*.py`
- **Ingestion scripts:** `scripts/ingest_*.py`

---

## Summary: The Three Laws

1. **Verify before asserting** — If you didn't check it, don't claim it.
2. **Propose before editing** — No changes without user awareness and approval for protected files.
3. **Accuracy over speed** — Take time to be correct. Being fast and wrong is not helpful.

---

*Last updated: 2026-02-04*
*Cross-reference: `Docs/GPT_CODEX_SETUP_GUIDE.md` for technical setup*
