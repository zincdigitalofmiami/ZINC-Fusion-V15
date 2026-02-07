NOTE: Production is the dashboard/frontend, not the repo root.
# ZINC-FUSION-V15 – GitHub Copilot Instructions

`AGENTS.md` is the primary source of truth. Read it before acting.

---

## BEFORE You Write Any Code

1. **Read the relevant files.** Do not assume contents — open and inspect them.
2. **Verify schemas/tables exist.** Check `prisma/schema.prisma` or query the DB. Do not invent columns.
3. **Cite your source.** When claiming something exists, state which file and line you saw it in.
4. **State your plan.** One sentence: what you'll change, in which file, and why.

## AFTER You Write Any Code (MANDATORY — EVERY TIME)

1. **Re-read your output.** Does it reference real tables/columns/functions? Cross-check.
2. **Run ruff.** `.venv/bin/ruff check --select F401,F403,F405,F821,F841 <file>` — catches hallucinated imports and undefined names.
3. **Run tests.** `.venv/bin/pytest -q` or the specific test file.
4. **Check imports.** Every import must resolve to a real module in this repo or requirements.txt.
5. **No phantom symbols.** If you referenced a function/class, confirm it exists with a search first.

**Do NOT mark a task complete until ruff and tests pass.**

---

## Grounding Rules (Anti-Hallucination)

- **If you didn't read it, don't claim it.** No asserting files exist, tables have columns, or functions take parameters without inspecting first.
- **No fabrication.** Never invent schemas, tables, columns, API endpoints, credentials, or file paths.
- **No code in chat** unless explicitly asked. Discuss and plan first.
- **Cite evidence.** Use "I see in `file.py:L42` that…" style references, not "I believe…"
- **Say "I don't know"** when you don't. Never fill gaps with plausible-sounding fiction.
- **Prefer existing patterns.** Search the codebase for how something is already done before writing new code.

## Forbidden Patterns

| Pattern | Why It's Banned |
|---------|-----------------|
| Inventing a helper function that doesn't exist | Hallucination — causes ImportError |
| Using `PrismaClient` for runtime queries | Architecture violation — use `pg` Pool (TS) or psycopg2 (Python) |
| Creating `raw.*`, `gold.*`, `silver.*`, `bronze.*` schemas | Banned schema names |
| Adding buy/sell/execute logic | This is intelligence, not execution |
| Forward-filling data without approval | Forward fill is OFF by default |
| Referencing 48 OOF tables or 12 L0 models | Legacy v2 — v3 has 1 OOF table, 4 core models |
| Running bare `npx prisma` without `--config` | Will fail — see Prisma CLI section |
| Running `npm` commands at repo root | Root is Python — frontend is `frontend/` |

---

## Prisma CLI (CRITICAL — URL NOT IN SCHEMA)

The `prisma/schema.prisma` file has NO `url` field. The URL is injected via config.
**Every** Prisma CLI command MUST use the config flag:

```bash
npx prisma migrate status --config config/prisma.config.ts
npx prisma validate --schema prisma/schema.prisma
npx prisma studio --config config/prisma.config.ts
```

**NEVER** run bare `npx prisma migrate` or `npx prisma db pull` — it will fail with a connection error.
Use the wrapper script when available: `scripts/prisma.sh <command>`

---

## Repository Structure (Root ≠ Frontend)

This is a **monorepo with two distinct environments**:

| Aspect | Root (`/`) | Frontend (`frontend/`) |
|--------|-----------|----------------------|
| Language | Python 3.11 | TypeScript / Next.js |
| Package mgr | uv / pip | npm |
| DB connection | psycopg2 via `src/fusion/db/connection.py` | `pg` Pool via `frontend/src/lib/db.ts` |
| Deploy | Local / scripts | Vercel |
| Env file | `.env` | `frontend/.env.local` |
| Tests | `.venv/bin/pytest` | `npm --prefix frontend test` |
| Linter | ruff | ESLint |

**Root `package.json` exists ONLY for Prisma CLI.** Do not run `npm run build` or `npm start` at root.
**`npm` commands for the app** must always use `--prefix frontend` or `cd frontend`.

## Architecture Quick Reference

- **Database:** Prisma Postgres only. Prisma = schema management. Runtime = raw SQL.
- **TypeScript queries:** `pg` Pool via `frontend/src/lib/db.ts`
- **Python queries:** psycopg2 via `src/fusion/db/connection.py`
- **12 schemas:** `mkt`, `econ`, `alt`, `pos`, `supply`, `features`, `training`, `model`, `forecasts`, `analytics`, `metadata`, `ops`
- **v3 stack:** 4 Core (AutoGluon) + 11 Specialists (custom) + 4 Meta = 19 models
- **Specialists produce signals**, not forecasts. Core owns horizons (5d/21d/63d/126d).

## Entrypoints

- Prisma schema: `prisma/schema.prisma`
- Prisma CLI: `scripts/prisma.sh <command>` (wraps `--config`)
- FastAPI: `fusion.api.server:app`
- Validation: `.venv/bin/pytest -q`
- Lint: `.venv/bin/ruff check --select F401,F403,F405,F821,F841 src/`
- Full rules: `AGENTS.md`
