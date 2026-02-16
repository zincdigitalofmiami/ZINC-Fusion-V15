# ZINC-FUSION-V15

Commodity procurement forecasting platform for bulk soybean oil (ZL), focused on probabilistic intelligence (no execution logic).

## Canonical Documentation

- `AGENTS.md` is the single source of truth for rules and architecture.
- `CLAUDE.md` is a thin compatibility pointer to `AGENTS.md`.

## Repository Layout

- Root (`/`): Python ML + API code
- `frontend/`: Next.js dashboard + Inngest jobs
- `config/`: Prisma CLI package + Prisma config
- `prisma/schema.prisma`: database schema source of truth

## Package/Tooling Policy

- There is intentionally **no root `package.json`**.
- Frontend npm commands must run with `--prefix frontend`.
- Prisma CLI commands must run with `--prefix config` (or `scripts/prisma.sh`).

## Model Architecture

Multi-level ensemble forecasting system for soybean oil (ZL):

- **L0 Core:** 25-model AutoGluon zoo per horizon (5d/21d/63d/126d), CPU-only, WQL metric, quantiles [0.3, 0.5, 0.7]
- **Specialists:** 11 domain signal generators (GBM, RF, ARDL, Ridge, VAR, GARCH, ECM, event-based) writing to `training.specialist_signals_1d`
- **Integration:** Specialist signals feed into core training matrix (~213+ features) as observed covariates
- **L2/L3:** Quantile calibration + Monte Carlo risk (VaR/CVaR)

See `AGENTS.md` for full model zoo listing and specialist bucket contracts.

## Quick Commands

```bash
# Python checks
.venv/bin/ruff check --select F401,F403,F405,F821,F841 src/ scripts/ tests/
.venv/bin/pytest -q --tb=short

# Frontend checks
npm --prefix frontend run lint
npx --prefix frontend tsc --noEmit

# Prisma validate
npx --prefix config prisma validate --schema prisma/schema.prisma
# or
scripts/prisma.sh validate --schema prisma/schema.prisma
```
