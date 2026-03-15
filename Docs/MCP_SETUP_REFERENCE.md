# MCP Setup Reference — ZINC-FUSION-V15

> Single source of truth for MCP server configuration, validation, and troubleshooting.
> All AI agents (Claude, Kilo Code) must consult this document when MCP tools are missing, returning errors, or behaving unexpectedly.

---

## Active MCP Stack

All servers run via **npx** (no Docker). There is no `MCP_DOCKER` server — it was removed on 2026-03-06.

| Server | Package | Purpose |
|--------|---------|---------|
| `memory` | `@modelcontextprotocol/server-memory` | Knowledge graph for persistent agent memory |
| `sequentialthinking` | `@modelcontextprotocol/server-sequential-thinking` | Step-by-step reasoning for complex tasks |
| `context7` | `@upstash/context7-mcp` | Live library/framework documentation lookup |
| `puppeteer` | `@modelcontextprotocol/server-puppeteer` | Browser automation (scraping, screenshots) |

Additional servers (not part of Kilo stack):

| Server | Type | Purpose |
|--------|------|---------|
| `Prisma-Local` | stdio | Local Prisma MCP via `scripts/prisma.sh mcp` |
| `Prisma-Remote` | http | `https://mcp.prisma.io/mcp` |
| `macbook-air-mes` | stdio | SSH tunnel to MacBook Air filesystem (external project workspace) |

---

## Configuration File Locations

### Claude Code (`~/.claude.json`)

MCP servers are defined in two places within this file:

1. **Global scope** — `$.mcpServers` (applies to all projects)
2. **Project scope** — `$.projects["/Volumes/Satechi Hub/ZINC-FUSION-V15"].mcpServers` (overrides for this workspace)

Both scopes should have identical npx MCP entries for `memory`, `sequentialthinking`, `context7`, and `puppeteer`.

```jsonc
// Project-scoped example (global is identical)
"memory": {
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-memory"],
  "env": {
    "MEMORY_FILE_PATH": "/Users/zincdigital/.claude/memory/memory.jsonl"
  }
},
"sequentialthinking": {
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
},
"context7": {
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "@upstash/context7-mcp"],
  "env": { "DEFAULT_MINIMUM_TOKENS": "" }
},
"puppeteer": {
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-puppeteer"]
}
```

### Kilo Code (`mcp_settings.json`)

Path: `~/Library/Application Support/Code/User/globalStorage/kilocode.kilo-code/settings/mcp_settings.json`

Same four npx servers. Kilo also sets `alwaysAllow` for each server's tools:

- **memory:** `create_relations`, `add_observations`, `delete_entities`, `delete_observations`, `delete_relations`, `read_graph`, `search_nodes`, `open_nodes`
- **sequentialthinking:** `sequentialthinking`
- **context7:** `resolve-library-id`, `query-docs`
- **puppeteer:** (no alwaysAllow — requires approval per call)

### Claude Project Permissions (`.claude/settings.local.json`)

Path: `/Volumes/Satechi Hub/ZINC-FUSION-V15/.claude/settings.local.json`

Pre-approves graph-memory tools so Claude doesn't prompt for each call:

```json
{
  "permissions": {
    "allow": [
      "mcp__memory__search_nodes",
      "mcp__memory__read_graph",
      "mcp__memory__open_nodes",
      "mcp__memory__create_entities",
      "mcp__memory__create_relations",
      "mcp__memory__add_observations",
      "mcp__memory__delete_entities",
      "mcp__memory__delete_relations",
      "mcp__memory__delete_observations",
      "mcp__sequentialthinking__sequentialthinking",
      "mcp__context7__resolve-library-id",
      "mcp__context7__query-docs"
    ]
  }
}
```

### Claude Project Hooks (`.claude/settings.json`)

Path: `/Volumes/Satechi Hub/ZINC-FUSION-V15/.claude/settings.json`

Three hooks are active:

| Hook | Trigger | What it does |
|------|---------|--------------|
| PostToolUse: `Write\|Edit\|MultiEdit` | After any file write to `*.py` | Runs `ruff format` + `ruff check --fix` |
| PreToolUse: `Write\|Edit\|MultiEdit` | Before any file write | Blocks edits to `.env*` and `migration_lock.toml` |
| PreToolUse: `Bash` | Before any shell command | Blocks destructive commands (`git reset --hard`, `rm -rf`, `dropdb`, etc.) and commands targeting spillover worktrees |

---

## Memory Server Details

### API: Knowledge Graph (NOT Simple Memory)

`@modelcontextprotocol/server-memory` implements a **knowledge graph** with entities, relations, and observations.

**Valid tools (graph API):**

| Tool | Purpose |
|------|---------|
| `search_nodes` | Search entities by keyword |
| `create_entities` | Create new entity nodes |
| `create_relations` | Link entities together |
| `add_observations` | Attach facts to existing entities |
| `read_graph` | Read the entire knowledge graph |
| `open_nodes` | Open specific nodes by name |
| `delete_entities` | Remove entities |
| `delete_relations` | Remove relations |
| `delete_observations` | Remove observations from entities |

**Invalid tools (simple-memory API — WRONG PACKAGE):**

| Tool | Why it's wrong |
|------|---------------|
| `add_memories` | From a different `server-memory` variant |
| `search_memory` | Will error with dimension mismatch or wrong results |
| `list_memories` | Returns empty even when graph has data |
| `delete_all_memories` | Destructive and targets wrong data store |

If you see the simple-memory tools in your session, the MCP registry is stale. **Restart the session.**

### Memory File

- Path: `/Users/zincdigital/.claude/memory/memory.jsonl`
- Format: JSON Lines (one JSON object per line)
- Starts empty on fresh setup — seed from `AGENTS.md` and `memory/AGENT_GUARDRAIL_SEED_2026_03_06.md`

### Memory Seeding Procedure

When `search_nodes` returns empty results on a fresh session:

1. Read `memory/AGENT_GUARDRAIL_SEED_2026_03_06.md` for workspace anchor, MCP contract, session order, and guardrails
2. Read `AGENTS.md` for architecture, corrections, and hard-coded rules
3. Create entities in the knowledge graph for key facts (workspace config, specialist count, model architecture, etc.)
4. Verify with `read_graph` that entities were stored

---

## First-Time Setup

### Prerequisites

- Node.js with `npx` available on PATH
- VS Code with Claude Code extension and/or Kilo Code extension

### Steps

1. **Verify npx works:**
   ```bash
   npx --version
   ```

2. **Ensure `~/.claude.json` has the correct mcpServers** (see Configuration section above). Both global and project scope should have the four npx servers.

3. **Ensure Kilo `mcp_settings.json` matches** (see Configuration section above).

4. **Create the memory file if it doesn't exist:**
   ```bash
   mkdir -p ~/.claude/memory
   touch ~/.claude/memory/memory.jsonl
   ```

5. **Set up project permissions:**
   - `.claude/settings.local.json` must list graph-memory tools in `permissions.allow` (see Configuration section above)
   - `.claude/settings.json` must have the hooks defined (see Configuration section above)

6. **Restart VS Code / Claude Code session** to load the MCP registry fresh.

7. **Validate** (see Validation section below).

---

## Validation Checklist

Run these checks after setup or after any MCP config change. **All must pass.**

### 1. Correct tools are loaded

In a Claude session, the following tool prefixes should appear:

| Prefix | Expected |
|--------|----------|
| `mcp__memory__search_nodes` | Yes |
| `mcp__memory__create_entities` | Yes |
| `mcp__memory__read_graph` | Yes |
| `mcp__sequentialthinking__sequentialthinking` | Yes |
| `mcp__context7__resolve-library-id` | Yes |
| `mcp__context7__query-docs` | Yes (Kilo: `get-library-docs`) |
| `mcp__puppeteer__*` | Yes (browser tools) |

### 2. Wrong tools are NOT loaded

| Prefix | Should NOT appear |
|--------|-------------------|
| `mcp__memory__add_memories` | Stale simple-memory binding |
| `mcp__memory__search_memory` | Stale simple-memory binding |
| `mcp__memory__list_memories` | Stale simple-memory binding |
| `mcp__MCP_DOCKER__*` | Old Docker MCP — removed |

If any "should not appear" tools are present, restart the session.

### 3. Memory read/write roundtrip

```
1. Call search_nodes with "test" — should return empty or prior results (no error)
2. Call create_entities with a test entity
3. Call search_nodes with test entity name — should find it
4. Call delete_entities to clean up test entity
```

If `search_nodes` returns a dimension mismatch error, the memory file has stale vector data. Delete `memory.jsonl`, recreate it empty, and restart the session.

### 4. Sequential thinking works

Call `sequentialthinking` with a simple test thought. Should return without error.

### 5. Context7 works

Call `resolve-library-id` with `"next.js"`. Should return library matches.

---

## Troubleshooting

### "Vector dimension error: expected dim: 1536, got 768"

**Cause:** Memory file contains data indexed with a different embedding model dimension than the current one.

**Fix:**
```bash
# Back up existing data
cp ~/.claude/memory/memory.jsonl ~/.claude/memory/memory.jsonl.bak

# Clear and recreate
echo -n > ~/.claude/memory/memory.jsonl
```
Then restart the session and re-seed memory from `AGENTS.md` / `AGENT_GUARDRAIL_SEED_2026_03_06.md`.

### Simple-memory tools appear instead of graph tools

**Cause:** Session loaded before config was updated, or a cached MCP registry.

**Fix:** Restart the VS Code window or Claude Code session. The config in `~/.claude.json` is already correct — the session just needs to reload it.

### MCP server shows "offline" in VS Code

**Fix:**
1. Command Palette → "MCP: List Servers" — check status
2. Command Palette → "MCP: Restart Server" for the offline server
3. If it keeps failing, check that `npx` is on PATH and the package installs correctly:
   ```bash
   npx -y @modelcontextprotocol/server-memory --help
   ```

### Memory returns empty on every session

**Cause:** `memory.jsonl` is empty or was cleared.

**Fix:** Re-seed from the guardrail seed file:
1. Read `memory/AGENT_GUARDRAIL_SEED_2026_03_06.md`
2. Create entities for workspace anchor, MCP contract, session rules
3. Verify with `read_graph`

### Hooks block a legitimate operation

**Cause:** The PreToolUse hooks in `.claude/settings.json` block destructive commands and spillover worktree paths.

**Fix:** If the operation is genuinely needed, the user must explicitly approve it in chat. The agent should state intent and wait — the hook enforces this.

Blocked patterns:
- `.env*` and `migration_lock.toml` file edits
- `git reset --hard`, `git checkout --`, `git clean -fd`, `git push --force`, `rm -rf /`, `rm -rf ~`, `docker compose down -v`, `prisma migrate reset`, `dropdb`
- Any command referencing spillover worktree paths (`ZINC-FUSION-V15-recovery-dirty`, `-deploy-fix`, `-integration`, `-integration-clean`, `_RECOVERED`)

---

## Change Log

| Date | Change |
|------|--------|
| 2026-03-06 | Removed `MCP_DOCKER` from Claude config. Migrated all servers to npx stack. Created this document. |
| 2026-03-06 | Added agent hooks in `.claude/settings.json` (ruff format, .env block, destructive command block, worktree block). |
| 2026-03-06 | Updated `.claude/settings.local.json` to pre-approve graph-memory tools instead of simple-memory tools. |
| 2026-03-06 | Created `memory/AGENT_GUARDRAIL_SEED_2026_03_06.md` as reseed source of truth. |
