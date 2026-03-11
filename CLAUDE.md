# CLAUDE.md — ZINC-FUSION-V15

Read and follow `AGENTS.md` at the repository root. It is the single source of truth for all AI agents.

## Vegas Guardrail (UPDATED 2026-03-11)

- Vegas is cloud-only operationally.
- Do not run local Vegas syncs or local Vegas migrations.
- Do not change Vegas schema placement or Glide App ID without explicit approval.

## Client Business Model (ADDED 2026-03-03)

**Chris** (owner, US Oil Solutions) **BUYS raw soybean oil by the trainload** — millions of gallons. He delivers fresh cooking oil to 100+ Las Vegas restaurant kitchens (Caesars, Boyd, Resorts World). When he services restaurants, he collects used cooking oil (UCO) and sells it (likely to biodiesel). Primary exposure = BUYER (ZL up = bad for his costs). Secondary revenue = UCO sales (ZL up = good, but smaller). Net: he's a buyer. Strategy posture language is correct for him.

**Kevin** (sales director) uses Vegas Intel to pitch restaurants on service upgrades, pre-schedule extra oil for big events, and prospect new accounts.

Full details in `AGENTS.md` → "Client Business Model" section.

## State Persistence (UPDATED 2026-03-06)

> Full MCP setup, validation, and troubleshooting: [`Docs/MCP_SETUP_REFERENCE.md`](Docs/MCP_SETUP_REFERENCE.md)

### MCP Servers — FIX BEFORE WORKING

**If memory MCP or any required MCP server is offline or returning empty, STOP and fix it before doing any work.**

How to fix:
1. Open VS Code Command Palette → "MCP: List Servers" — verify `memory`, `sequentialthinking`, `context7`, and `puppeteer` show as connected
2. If offline: Command Palette → "MCP: Restart Server" for each offline server
3. Memory file path is `/Users/zincdigital/.claude/memory/memory.jsonl` — if empty, seed immediately from `AGENTS.md` and current session facts
4. Verify memory tools are graph API (`search_nodes`, `create_entities`, `add_observations`, `read_graph`); if only `search_memory/list_memories` appear, fix MCP config before coding
5. Do NOT proceed with code changes until MCP tools respond correctly

### Secret Artifact Hygiene (MANDATORY)

1. Never leave generated env artifacts in workspace (examples: `frontend/.env.vercel.*`, temporary env pulls, token dump files).
2. If such a file is created for diagnostics, delete it immediately after use.
3. Ensure `.gitignore` covers the artifact pattern before continuing.
4. Never commit `.env*` or token-bearing files.

### Dual-Track State (BOTH required)

**Memory MCP** — MUST be searched at session start, MUST be written to after every decision:
- Query: task keywords + "ZINC-FUSION" + "Kirk"
- Store: architectural decisions, bug fixes, corrections, pipeline status

**Markdown files** — permanent record, source of truth when memory is empty:
- `AGENTS.md` — Architecture, corrections, data source audit, pipeline status
- `CLAUDE.md` (this file) — Session-specific state and quick reference
- `.claude/plans/*.md` — Implementation plans

If memory MCP returns empty but markdown files have context → load from markdown, then seed memory MCP immediately with that context before proceeding.

## Quick Reference — What Actually Works

### Core Pipeline (the REAL training)
```bash
.venv/bin/python -m fusion.core_training.run_pipeline          # Full: matrix + train + promote
.venv/bin/python -m fusion.core_training.run_pipeline --skip-matrix  # Train only
```

### Specialist Signal Generation (NOT training — just feature engineering)
```bash
.venv/bin/python scripts/generate_specialist_features.py --bucket all --start-date 2025-01-01
.venv/bin/python scripts/generate_specialist_signals.py --bucket all --start-date 2025-01-01
```

### DO NOT USE
- `scripts/populate_core_matrix.py` — wrong column names, 25-col lightweight script (real builder = 1,487 features)

### Dev Server
```bash
npm --prefix frontend run dev  # port 3000
```

### Verification Gate (ALL must pass)
```bash
make lint && make lint-frontend && make tsc && make prisma-validate && make git-integrity && make test
```

## Data Source Gaps (as of 2026-02-27)

5 tables exist with data but are NOT wired into `build_matrix.py`:
- `mkt.etf_1d` (46K rows, stale Feb 2)
- `alt.legislation_1d` (2,944 rows, current)
- `supply.eia_biodiesel_1m` (179 rows, at source limit Nov 2025)
- `supply.eia_biodiesel_1w` (0 rows, never run)
- `supply.uco_prices_1w` (0 rows, never run)

2 Inngest functions registered with NO DB table:
- `fedSpeechesDaily` → no `alt.fed_speeches_event` table
- `congressBillsDaily` → no `alt.congress_bills_event` table

ProFarmer is in the matrix ONLY as article count/day. Content/sentiment NOT used by matrix builder (but IS used by specialist feature generators).

## Bugs Fixed This Session (2026-02-27)

1. **Biofuel min_periods** — `min_periods=42` on weekly EPA data (18 obs/126d) always NaN → changed to 12
2. **ETF cursor poisoning** — Added `AND close IS NOT NULL` to prevent NULL rows advancing cursor
3. **Yahoo ETF fallback** — Created `yahoo-etf-fallback.ts` as safety net for Databento failures
4. **ProFarmer crash** — `Cannot find module 'is-plain-object'` since Feb 15. Full fix chain: `serverExternalPackages` + `outputFileTracingIncludes` in `next.config.ts` for Vercel module resolution, PLUS `resolveChromePath()` in `profarmer-daily.ts` for Docker Inngest local execution. ✅ FIXED 2026-03-03.
5. **Wired 3 data sources** — ETF, legislation, EIA biodiesel added to `build_matrix.py` (were previously orphaned)

## ProFarmer Status (FIXED 2026-03-03)

- **8,535 total articles** in `alt.profarmer_news_event` (coverage: 2021-05-25 → 2026-03-04)
- **Daily scraper WORKING** — runs via Docker Inngest (NOT Vercel serverless)
- Fix: `resolveChromePath()` in `profarmer-daily.ts` detects runtime environment:
  1. `PUPPETEER_EXECUTABLE_PATH` env var (explicit override)
  2. System Chrome probing (macOS `/Applications/Google Chrome.app/...`, Linux `/usr/bin/chromium-browser`)
  3. Falls back to `@sparticuz/chromium` only on Vercel
- Root cause of Feb 15 – Mar 3 outage: Turbopack tree-shaking broke `is-plain-object` → `kind-of` → `fs-extra` chain. `serverExternalPackages` + `outputFileTracingIncludes` in `next.config.ts` fixed module resolution, but Vercel serverless still times out (browser too heavy). Docker Inngest has no timeout limit.
- Cron: weekdays 7 AM CT. Weekly auto-backfill: Sunday 2 AM CT.
- **To run manually:** `curl -X POST http://localhost:8288/e/test -H "Content-Type: application/json" -d '{"name": "profarmer/daily", "data": {}}'`

## Pending Plans (Not Yet Implemented)

1. **Specialist re-engineering** (`foamy-spinning-steele.md`) — 5-fold CV, purge/embargo, IC dedup, calibration
2. **Core training beefing** (`dynamic-crunching-barto.md`) — 12 model configs, 8-fold bagging, RealMLP/TabM
3. **Data gap filling** (`rustling-stargazing-hoare.md`) — UCO prices, Congress bills, Fed speeches, FOMC calendar
4. ~~**Wire missing data sources**~~ ✅ Done: ETF, legislation, EIA biodiesel wired into `build_matrix.py`
5. ~~**ProFarmer fix**~~ ✅ Done: Docker Inngest + `resolveChromePath()` — 44 articles recovered, 17-day gap filled
6. **Empty data sources** — `eia_biodiesel_1w` and `uco_prices_1w` have Inngest functions but 0 rows (never triggered)
7. **Missing DB tables** — `fedSpeechesDaily` and `congressBillsDaily` registered but no tables created
