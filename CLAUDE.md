# ZINC-FUSION-V15 — Claude Instructions (Repo Rules)

This repository has strict governance. Treat `AGENTS.md` as the primary source of truth for operating rules.

## Database Architecture (CRITICAL)

**Prisma Postgres is the ONLY authoritative database.**
- All training, inference, and operations use Prisma
- Connection: `DATABASE_URL` environment variable
- Schema: `prisma/schema.prisma`

**DuckDB is ARCHIVE ONLY.**
- `data/fusion.db` is read-only historical archive
- Do NOT write to DuckDB
- Do NOT train against DuckDB
- Use only for one-time historical data extraction

## Non‑negotiables

- Do not invent schemas, tables, columns, symbols, endpoints, credentials, or file paths.
- Do not mutate Prisma schemas unless the user explicitly approves the exact change.
- Do not add "buy/sell/act now" or any execution logic. This is intelligence/support only.
- Keep diffs minimal and reversible; avoid unrelated refactors.
- Validate before asserting. If you didn't inspect it, don't claim it.
- All new data operations target Prisma, never DuckDB.

## Ground truth entrypoints
- Prisma schema: `prisma/schema.prisma`
- Prisma connection: `DATABASE_URL` in `.env`
- FastAPI app: `fusion.api.server:app`
- DuckDB archive (read-only): `data/fusion.db`

## Validation (prefer venv)
- Use `.venv/bin/python` and `.venv/bin/pytest` to match project deps.
- Suggested checks:
  - `.venv/bin/pytest -q`
  - Prisma queries to verify data state

