# ZINC FUSION EOD Drift Lock — 2026-03-05 (America/Chicago)

## Purpose
This file is a hard checkpoint to prevent loss after the recovery/debug/deploy sequence.
It records canonical workspace identity, branch/worktree state, deployment state, drift counts,
recovered docs, and exact next actions.

## Canonical Workspace (Now Correct)
- Path: `/Volumes/Satechi Hub/ZINC-FUSION-V15`
- Branch: `main`
- HEAD: `5d149fb1` (ahead of `origin/main` by 1 commit)
- `origin/main`: `eeb2ee8a`
- Working tree: clean (tracked files)

### Main branch local-only commit (not yet pushed)
- `5d149fb1` — `docs: restore recovered audit and planning markdown files`

## VSCode / Python Environment Lock
- Canonical workspace now has `.venv` available via symlink:
  - `.venv -> /Volumes/Satechi Hub/ZINC-FUSION-V15-recovery-dirty/.venv`
- Verified:
  - Python: `3.12.8`
  - pre-commit: `4.5.1`
- VSCode settings pinned to absolute path (space-safe):
  - `python.defaultInterpreterPath`: `/Volumes/Satechi Hub/ZINC-FUSION-V15/.venv/bin/python`
  - `python.analysis.extraPaths`: `/Volumes/Satechi Hub/ZINC-FUSION-V15/src`

## Worktree Map (authoritative)
- `/Volumes/Satechi Hub/ZINC-FUSION-V15-recovery-dirty`
  - `recovery/forensic-20260305-ui` @ `8682fdd3`
  - Massive dirty state preserved (forensics/recovery source)
- `/Volumes/Satechi Hub/ZINC-FUSION-V15`
  - `main` @ `5d149fb1` (local ahead, clean)
- `/Volumes/Satechi Hub/ZINC-FUSION-V15-deploy-fix`
  - `hotfix/recovery-get-ingest-pool` @ `8d2a0d86`
- `/Volumes/Satechi Hub/ZINC-FUSION-V15-integration`
  - `integration/recovery-20260305-safe` @ `a5f2f385`
- `/Volumes/Satechi Hub/ZINC-FUSION-V15-integration-clean`
  - `integration/recovery-20260305-safe-clean` @ `466dfe76`
- `/Volumes/Satechi Hub/ZINC-FUSION-V15_RECOVERED`
  - detached @ `cda83bc9`
- `git worktree repair` has been run after folder moves.

## Drift Snapshot (recovery-dirty)
- Total changed entries: `2112`
- Branch is behind remote by 2 commits:
  - local `recovery/forensic-20260305-ui`: `8682fdd3`
  - remote `origin/recovery/forensic-20260305-ui`: `8d2a0d86`
- Top-level distribution (count):
  - `models`: 1977
  - `frontend`: 66
  - `src`: 23
  - `scripts`: 17
  - plus docs/config/infra and helper files

## Deploy / Vercel Lock
- Project: `zinc-fusion-v15`
- Root Directory: `frontend`
- Production branch: `main`
- Node version: `22.x` (aligned)
- Preview deploys: enabled
- Latest preview: `zinc-fusion-v15-7i2nkzezd-zincdigitalofmiamis-projects.vercel.app` (`READY`)

## Recovery Work Completed Today (critical)
1. Fixed deploy blockers on recovery branch:
   - Restored `getIngestPool` export contract
   - Fixed market driver `MarketData` contract mismatch
2. Removed dead Plotly deps from recovery branch and validated build
3. Locked Vercel protection workflow in `AGENTS.md`
4. Restored missing untracked markdown artifacts from preserved recovery state
5. Canonicalized workspace path so `/ZINC-FUSION-V15` now maps to `main`

## Restored Docs/Planning Artifacts committed to main
Commit: `5d149fb1`
- `CLAUDE.md`
- `PRE_REBUILD_FORECAST_AUDIT.md`
- `PRE_REBUILD_FORECAST_AUDIT_2026-03-04.md`
- `Docs/data-source-catalog.md`
- `Docs/audit/PRE_REBUILD_FORECAST_AUDIT_2026-03-04.md`
- `Docs/audit/README.md`
- `Docs/audit/REPORT_INDEX.md`
- `Docs/audit/pre_rebuild_forecast_audit_2026_03_04.md`
- `Docs/audit/pre_rebuild_forecast_audit_summary.md`
- `memory/ZINC_FUSION_SESSION_2026_03_05.md`
- `plans/ARCHITECTURE_FORENSIC_ANALYSIS.md`
- `plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md`
- `plans/LOCAL_DB_SETUP_FOR_AUDIT.md`
- `plans/SPECIALIST_DATA_SOURCE_EXPANSION.md`

## Important Path/Casing Note
- Historical tracked docs path in git is `Docs/...` (uppercase D).
- On this macOS filesystem, opening `docs/...` resolves, but git history tracks `Docs/...`.
- Do not bulk-rename case-only paths without a controlled migration commit.

## Immediate Next Steps (do in order)
1. Push `main` (commit `5d149fb1`) to remote so restored docs are not local-only.
2. Decide promotion path from recovery to main (cherry-pick batches, not full merge).
3. Keep `recovery-dirty` untouched as forensic source until promotion completes.
4. After promotion, run final endpoint + UI acceptance on preview before production merge.

## Non-Goals / Guardrails
- No model retraining was run.
- No port assignment changes were made (3000/3001/8288 unchanged).
- No destructive history rewrite/reset was used.
