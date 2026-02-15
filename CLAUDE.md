## NOTE: Production is the dashboard/frontend, not the repo root.

description:
alwaysApply: true

---

# ZINC-FUSION-V15 - Claude Instructions (Compatibility Layer)

`AGENTS.md` is the single source of truth for rules, architecture boundaries, and operating policy.

If this file and `AGENTS.md` ever disagree, follow `AGENTS.md`.

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
