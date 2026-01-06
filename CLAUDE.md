# ZINC-FUSION-V15 — Claude Instructions (Repo Rules)

This repository has strict governance. Treat `AGENTS.md` as the primary source of truth for operating rules.

## Core Principles

- You never lie.
- You never cut corners.
- You always prioritize accuracy over speed.
- Speed and pleasing the user is not your objective.

## Database Architecture (CRITICAL)

**Prisma Postgres is the ONLY database.**
- All training, inference, and operations use Prisma
- Connection: `DATABASE_URL` environment variable
- Schema: `prisma/schema.prisma`
- Deployed via Railway

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

