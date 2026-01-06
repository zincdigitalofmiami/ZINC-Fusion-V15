# ZINC-FUSION-V15 – GitHub Copilot Instructions

Copilot must follow repo governance. Treat `AGENTS.md` as the primary source of truth.

## Non‑negotiables

- Do not invent schemas, tables, columns, symbols, endpoints, credentials, or file paths.
- Do not mutate Prisma schemas/tables without explicit user approval (declare exact tables/columns).
- Do not add decision/execution semantics (no "buy/sell/act now" logic).
- Keep diffs minimal and reversible; avoid unrelated refactors.
- Validate before asserting. If you didn't inspect it, don't claim it.

## Canonical entrypoints
- Database: Prisma Postgres via `DATABASE_URL`
- FastAPI app: `fusion.api.server:app`

## Validation defaults (prefer venv)
- `.venv/bin/pytest -q`
