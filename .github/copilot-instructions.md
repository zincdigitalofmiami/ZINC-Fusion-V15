# ZINC-FUSION-V15 — Copilot & Codex Instructions

## 🚨 MANDATORY: Read AGENTS.md and .clinerules Before Acting

`AGENTS.md` is the single source of truth for this project. Every suggestion, completion, or generated code must be consistent with it.

---

## Project Identity

Commodity procurement forecasting system for bulk soybean oil (ZL) futures.
Client: US Oil Solutions.
Intelligence only — no execution or trade logic. Ever.

---

## Hard Rules — Do Not Violate

### Specialists
- There are **11 specialists** (Big-11): crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, trump_effect.
- Never write "10 specialists". trump_effect is real and active.

### Target Variable
- The ML target is the **future price level**: `df["close"].shift(-horizon)` named `target_price_{h}d`.
- Never use `pct_change()`, returns, or `target_ret_*`. Price levels only.

### Quantiles
- P30 / P50 / P70 are the forecast distribution columns. These are PRICE LEVELS in cents/lb.
- P10 / P90 are Monte Carlo outlier bounds only — not OOF columns.
- `QUANTILES = [0.3, 0.5, 0.7]` in config.py. Do not change.

### Visualization Language
- Forecast output = **horizontal Target Zones** on the chart. Discrete price-level lines.
- Probability stated as: "X% probability of this price area in N months"
- Three sources always cited: Monte Carlo (10,000 runs), pinball loss, MAE/accuracy %
- BANNED: "cones", "probability cone", "confidence band", "funnel". Never suggest these.

### Database
- 12 schemas: `mkt`, `econ`, `alt`, `pos`, `supply`, `features`, `training`, `model`, `forecasts`, `analytics`, `ops`, `vegas`
- BANNED schemas: `raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`, `archive`
- Runtime queries use psycopg2 (Python) and `pg` Pool (TypeScript). Never PrismaClient for runtime.

### Code Hygiene
- Python: ruff, pyproject.toml rules. No silent schema changes.
- Frontend: `npm --prefix frontend <cmd>`. No root package.json.
- Prisma CLI: `scripts/prisma.sh` or `npx --prefix config prisma`.
- Before committing: run `cubic review`. Fix all P0/P1 issues.

### MCP Tools (when available)
- Memory MCP: search before starting any task.
- Sequential Thinking MCP: plan before acting on non-trivial tasks.
- Context7 MCP: fetch live library docs for external API usage.

---

## Source of Truth Hierarchy

1. `config.py` — active model list (MODEL_ZOO_FROZEN)
2. `AGENTS.md` — architecture, corrections, hard rules
3. `prisma/schema.prisma` — database schema
4. This file — Copilot/Codex startup enforcement

---

## What This System Is NOT

- Not a trading system. No buy/sell/execute logic.
- Not a returns forecaster. Price levels only.
- Not a cone or band system. Target Zones only.
