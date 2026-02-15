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
