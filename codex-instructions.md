# ZINC-FUSION-V15 — Codex/GPT Instructions (Repo Rules)

This file exists so editor/agent tooling can reliably pick up project rules.
Primary governance lives in `AGENTS.md` and must be followed.

## What to do first (every session)

- Read `AGENTS.md`.
- Verify reality before claiming “done”: check the repo files on disk and (if relevant) `data/fusion.db`.

## Hard constraints

- No fabricated artifacts: do not invent schemas/tables/columns/paths/credentials.
- No schema mutation without explicit user approval (declare exact tables/columns).
- No destructive edits unless explicitly requested (no deletes/renames/moves).
- No decision/execution semantics (no “buy/sell/act now” logic).
- Avoid new dependencies/services without explicit approval.

## Canonical entrypoints
- DuckDB path: `data/fusion.db` (or `FUSION_DB_PATH`)
- FastAPI app: `fusion.api.server:app`

## Validation defaults

- Prefer the repo venv:
  - `.venv/bin/pytest -q`

