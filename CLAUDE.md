NOTE: Production is the dashboard/frontend, not the repo root.
---
description: 
alwaysApply: true
---

# ZINC-FUSION-V15 — Claude Instructions

`AGENTS.md` is the primary source of truth. Read it fully before acting.
Forward fill policy: [Docs/FORWARD_FILL_POLICY.md](Docs/FORWARD_FILL_POLICY.md)

## Instruction Precedence

1. System instructions (highest)
2. AGENTS.md
3. This file (CLAUDE.md)
4. README.md
5. Code and tests
6. Notebooks (lowest)

## Core Principles

- You never lie.
- You never cut corners.
- You always prioritize accuracy over speed.
- Speed and pleasing the user is NOT your objective.
- **NEVER write code in chat responses unless explicitly asked.** Discuss, plan, approve first.

## Ray Cluster (22 cores available)

**Your AI agents can use `ray.init(address='auto')` and get 22 cores without melting your machine.**

## Mandatory Review Before Completing ANY Task

**You MUST run these checks before marking any coding task as done:**

```bash
# 1. Lint every Python file you touched
.venv/bin/ruff check --select F401,F403,F405,F821,F841 <files>

# 2. Run tests
.venv/bin/pytest -q

# 3. If you touched frontend/ code
npm --prefix frontend run lint

# 4. If you touched prisma/schema.prisma
npx prisma validate --schema prisma/schema.prisma
```

**If ruff or tests fail, fix the issues before reporting completion.**
This is non-negotiable. Do not skip. Do not say "you can run this later."

## Sequential Thinking (REQUIRED for Complex Tasks)

For any task involving 3+ steps, multiple files, or architectural decisions:
- Use sequential-thinking MCP to decompose the problem BEFORE writing code
- Track your reasoning step by step
- Verify your hypothesis at each step before proceeding
- This prevents the "confident but wrong" failure mode

## Verification Protocol (MANDATORY)

### BEFORE Writing Code
1. **READ** every file you plan to modify — completely, not just the function
2. **VERIFY** tables/columns exist in `prisma/schema.prisma` or by querying DB
3. **SEARCH** the codebase for existing patterns before writing new code
4. **CITE** evidence: "I see in `file.py:L42` that…" — never "I believe…"
5. **STATE** your plan: one sentence, what file, what change, why

### AFTER Writing Code
1. **LINT** — run ruff on every Python file you modified
2. **TEST** — run pytest or the specific test file
3. **RE-READ** your output. Does every import resolve? Every table exist?
4. **CONFIRM** no phantom symbols — every function/class you referenced must exist
5. **VALIDATE** against the schema if DB-related

### When Uncertain
- Say "I don't know" — never fill gaps with plausible fiction
- Ask for clarification rather than guessing
- Propose options with tradeoffs
- Prefer reversible actions over irreversible ones

## Prisma CLI (CRITICAL — URL NOT IN SCHEMA)

The `prisma/schema.prisma` has **NO `url` field**. The URL is injected via config file.
**Every** Prisma CLI command MUST use the config flag or the wrapper script:

```bash
# Use the wrapper (preferred):
scripts/prisma.sh migrate status
scripts/prisma.sh studio

# Or pass --config explicitly:
npx prisma migrate status --config config/prisma.config.ts
npx prisma validate --schema prisma/schema.prisma
```

**NEVER** run bare `npx prisma migrate`, `npx prisma db pull`, etc. — it will fail.

## Repository Structure (Root ≠ Frontend)

This monorepo has TWO distinct environments. **Do not confuse them.**

| Aspect | Root (`/`) — Python/ML | Frontend (`frontend/`) — Next.js |
|--------|----------------------|--------------------------------|
| Language | Python 3.11 | TypeScript |
| Package mgr | uv / pip | npm |
| DB connection | psycopg2 via `src/fusion/db/connection.py` | `pg` Pool via `frontend/src/lib/db.ts` |
| Deploy target | Local / scripts | Vercel |
| Env file | `.env` | `frontend/.env.local` |
| Tests | `.venv/bin/pytest -q` | `npm --prefix frontend test` |
| Linter | `.venv/bin/ruff check` | `npm --prefix frontend run lint` |

**Root `package.json` exists ONLY for Prisma CLI deps.** There is no `npm run build` at root.
**All `npm` commands for the app** require `--prefix frontend` or `cd frontend`.

## Database Architecture (CRITICAL — DO NOT CHANGE)

**Prisma Postgres is the ONLY database.**

| Layer | Tool | Purpose |
|-------|------|---------|
| Schema | `prisma/schema.prisma` | Single source of truth for tables |
| Migrations | `prisma migrate` | DDL version control (use `--config`!) |
| TypeScript Runtime | `pg` Pool | All Inngest job queries via `frontend/src/lib/db.ts` |
| Python Runtime | psycopg2 | All training scripts via `src/fusion/db/connection.py` |

**Forbidden:** Do NOT suggest PrismaClient for runtime queries. Do NOT modify connection utilities.

## Anti-Hallucination Rules

- **If you didn't read it, don't claim it.** No inventing files, tables, columns, functions, or parameters.
- **No fabrication.** Never invent schemas, API endpoints, credentials, or file paths.
- **Cite evidence.** Reference file:line, not assumptions.
- **Prefer existing patterns.** Search before writing.
- **Say "I don't know"** when you don't.

## Forbidden Patterns

| Pattern | Why |
|---------|-----|
| Inventing helper functions | Causes ImportError — hallucination |
| `PrismaClient` for queries | Architecture violation |
| `raw.*`, `gold.*`, `silver.*`, `bronze.*` schemas | Banned names |
| Buy/sell/execute logic | Intelligence only, not execution |
| Forward-fill without approval | Policy: OFF by default |
| 48 OOF tables / 12 L0 models | Legacy v2 — v3 has 1 OOF table, 4 core models |
| Editing files without reading them | Root cause of most bad edits |
| Bare `npx prisma` without `--config` | Will fail — schema has no URL |
| `npm run` at repo root | Root is Python — use `--prefix frontend` |

## Schema Boundaries (12 schemas)

**Landing:** `mkt`, `econ`, `alt`, `pos`, `supply`
**Derived:** `features`, `training`
**Output:** `model`, `forecasts`, `analytics`
**Governance:** `metadata`, `ops`

**BANNED:** `raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`, `archive`

## Change Authority

- **Code:** Freely modify Python/TS files, add tests, refactor
- **Schemas:** STOP and get explicit approval before ANY database change
- **Config files:** Propose change and wait for approval
- **Destructive ops:** Never delete/rename/move files without explicit consent

## Error Recovery

1. Read the error message completely
2. Query relevant state (file contents, DB schema, test output)
3. Identify root cause, not just symptoms
4. Fix the root cause
5. Validate the fix before claiming success

## MCP Server Usage

| Situation | Server | Action |
|-----------|--------|--------|
| 3+ step tasks | sequential-thinking | Decompose before coding (REQUIRED) |
| Before DB changes | Prisma MCP | Verify schema exists |
| Persist decisions | memory | Save for future sessions |
| Before committing | git MCP | Check status, diff, history |

## Entrypoints

- Prisma schema: `prisma/schema.prisma`
- Prisma CLI: `scripts/prisma.sh <command>`
- FastAPI: `fusion.api.server:app`
- Lint: `.venv/bin/ruff check --select F401,F403,F405,F821,F841 src/`
- Tests: `.venv/bin/pytest -q`
- Full rules: `AGENTS.md`
