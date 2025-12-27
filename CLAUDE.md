# ZINC-FUSION-V15 — Claude Instructions (Repo Rules)

This repository has strict governance. Treat `AGENTS.md` as the primary source of truth for operating rules.

## Non‑negotiables

- Do not invent schemas, tables, columns, symbols, endpoints, credentials, or file paths.
- Do not mutate DuckDB schemas/tables unless the user explicitly approves the exact change.
- Do not add “buy/sell/act now” or any execution logic. This is intelligence/support only.
- Keep diffs minimal and reversible; avoid unrelated refactors.
- Validate before asserting. If you didn’t inspect it, don’t claim it.

## Ground truth entrypoints
- DuckDB default path: `data/fusion.db` (override with `FUSION_DB_PATH`).
- FastAPI app: `fusion.api.server:app`

## Validation (prefer venv)
- Use `.venv/bin/python` and `.venv/bin/pytest` to match project deps.
- Suggested checks:
  - `.venv/bin/pytest -q`

