## NOTE: Production is the dashboard/frontend, not the repo root.

description:
alwaysApply: true

---

# ZINC-FUSION-V15 - Claude Instructions (Compatibility Layer)

`AGENTS.md` is the single source of truth for rules, architecture boundaries, and operating policy.

If this file and `AGENTS.md` ever disagree, follow `AGENTS.md`.

## 🚨 MANDATORY SESSION STARTUP — NO EXCEPTIONS

This applies to every Claude session, every task, no matter how small.

1. **Read AGENTS.md completely** before taking any action.
2. **Memory MCP** — Search for prior decisions and corrections: task keywords + "ZINC-FUSION" + "Kirk".
3. **Sequential Thinking MCP** — Plan before acting on any non-trivial task.
4. **Context7 MCP** — Fetch live library docs when writing/reviewing code that calls external APIs.

If you skipped any of these and the task warranted them — stop, acknowledge it, run them, then continue.

## Environment Boundaries

- Root (`/`) is Python/ML (`uv`/`pip`, `pytest`, `ruff`).
- Frontend app is in `frontend/` (`npm --prefix frontend ...`).
- Prisma CLI dependencies are in `config/package.json`.
- There is intentionally no root `package.json`.

## Command Rules

- Frontend commands: `npm --prefix frontend <cmd>`.
- Prisma commands: `scripts/prisma.sh <cmd>` or `npx --prefix config prisma <cmd> --config config/prisma.config.ts`.
- Do not run app npm commands at repo root.

## Completion Gate

Before marking coding work complete, run the project verification gate in `AGENTS.md` / `Makefile`.

## Code Review

Before committing, run `cubic review` to catch bugs and improvements.
Wait 2-3 minutes for the review to complete, then validate the issues found and fix them.
