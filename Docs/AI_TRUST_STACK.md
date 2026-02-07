# AI Trust Stack (No-Hallucination Guardrails)

This document defines the enforced controls to reduce fabricated code, invalid SQL/table references, and unsafe AI-assisted changes.

## Why This Exists

Observed failures in this repo include:
- Hallucinated imports/symbols
- Incorrect or fabricated table references
- Drift between local checks and CI checks
- Plain-text API keys in AI tooling config
- Overly permissive local AI command permissions

## Guardrail Layers

### Layer 1: Fast local quality gates (pre-commit)

Configured in `.pre-commit-config.yaml`:
- `ruff-check` (`F401,F403,F405,F821,F841`) for unresolved/undefined Python symbols
- `ruff-format` for stable formatting
- `gitleaks-system` for secret scanning
- `sql-table-contract` (custom) to validate `schema.table` refs against `prisma/schema.prisma`
- `eslint-frontend`
- `prisma-validate`

Install once:

```bash
.venv/bin/pre-commit install
```

Run full local gate:

```bash
.venv/bin/pre-commit run --all-files
```

### Layer 2: CI parity gates

Configured in `.github/workflows/quality-gates.yml`:
- Ruff on changed Python files
- SQL table contract on changed code files
- Pytest
- TypeScript typecheck (`tsc --noEmit`)
- Prisma schema validate

This catches changes that bypass local hooks.

### Layer 3: SQL truth contract

`scripts/check_sql_table_references.py` enforces:
- Only allowed schemas may appear in code
- Banned schemas fail immediately
- Referenced tables in allowed schemas must exist in `prisma/schema.prisma`

Usage:

```bash
python3 scripts/check_sql_table_references.py src scripts frontend/src tests sql
```

### Layer 4: MCP secret hygiene

`.vscode/mcp.json` must not contain hardcoded API keys.

Use environment variables:

```json
"args": ["-y", "@upstash/context7-mcp", "--api-key", "${env:CONTEXT7_API_KEY}"]
```

## Operating Rules (Human + AI)

1. Never claim table/function existence without file evidence.
2. Run local gates before commit.
3. Treat CI failure as a hard block, not advisory.
4. Never embed credentials in tracked config.
5. Keep schema authority in `prisma/schema.prisma`; runtime SQL stays raw (`pg` / psycopg2).

## Known Residual Risk

No static checker can fully prove semantic correctness of SQL logic. This stack eliminates a large class of fabrication errors, but DB-integrated tests remain necessary for behavioral validation.
