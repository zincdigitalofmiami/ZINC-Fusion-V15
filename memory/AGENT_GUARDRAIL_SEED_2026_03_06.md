# Agent Guardrail Seed (2026-03-06)

Use this file to reseed Memory MCP when search returns empty for this workspace.

## Workspace Anchor

- Canonical repo path: `/Volumes/Satechi Hub/ZINC-FUSION-V15`
- Active branch target for canonical work: `main`
- Ignore spillover worktrees unless user explicitly redirects:
  - `ZINC-FUSION-V15-recovery-dirty`
  - `ZINC-FUSION-V15-deploy-fix`
  - `ZINC-FUSION-V15-integration`
  - `ZINC-FUSION-V15-integration-clean`
  - `ZINC-FUSION-V15_RECOVERED`

## MCP Contract

- Active memory server: `@modelcontextprotocol/server-memory` (knowledge graph API)
- Required memory tools: `search_nodes`, `create_entities`, `create_relations`, `add_observations`, `read_graph`, `open_nodes`
- If only `search_memory/list_memories/add_memories` appear, MCP stack is wrong and must be fixed before coding
- Memory file path: `/Users/zincdigital/.claude/memory/memory.jsonl`

## Session Order (Hard Rule)

1. `Memory(search)` — query by task keywords + `ZINC-FUSION` + `Kirk`
2. `Plan` — explicit step-by-step plan before edits
3. `Execute` — one task at a time
4. `Memory(store)` — persist decisions/corrections immediately
5. `Report` — touched files, changes, verification, blockers

## Completion Claim Guardrails

- Never claim "done" or "good to go" without verification output
- Before any completion claim, check and report:
  - `git status -sb`
  - local `HEAD` hash
  - remote `origin/main` hash (if push/sync is in scope)
- If hooks/env block push, say so explicitly and provide exact blocker

## Data and Schema Integrity Guardrails

- No schema/migration/destructive DB actions without explicit user confirmation
- Do not edit `.env*` files directly
- Do not edit `migration_lock.toml` directly
- Prefer root-cause fixes over temporary patches when drift is present
