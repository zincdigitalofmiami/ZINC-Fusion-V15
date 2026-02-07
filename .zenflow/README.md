# Zenflow IDE Integration

This project is configured for **Zenflow Desktop App** with Spec-Driven Development workflows.

## Quick Start with Zenflow IDE

### 1. Open in Zenflow

```bash
# Launch Zenflow app
open /Applications/Zenflow.app
```

### 2. Add This Project

In Zenflow:
1. Click **"Add Project"**
2. Select this repository root (`ZINC-FUSION-V15`)
3. Zenflow reads `.zenflow/settings.json` automatically

### 3. Create a Task

1. Click **"New Task"**
2. Enter task description
3. Select workflow:
   - **Full SDD** - Complex tasks (3+ steps) - ENFORCES checkpoints
   - **Quick Change** - Simple edits
   - **Fix Bug** - Debugging with root cause analysis

## What Zenflow Does Differently

| Without Zenflow | With Zenflow |
|-----------------|--------------|
| AI can skip verification | Checkpoints BLOCK until you approve |
| AI invents imports | Cross-model review catches errors |
| "Done" without proof | configured verification command must exit 0 |
| No audit trail | Artifacts saved per task |

## Manual Usage (Without Zenflow IDE)

```bash
# Create a task manually
scripts/zenflow-task.sh "Add user authentication" full-sdd
```

## Configuration

### settings.json

| Setting | Purpose |
|---------|---------|
| `scripts.setup` | Runs when task starts |
| `scripts.verification` | Runs pre-commit checks for changed files |
| `copy_files` | `.env` files copied to worktrees |
| `rules.always_include` | `CLAUDE.md`, `AGENTS.md` loaded |
| `append_prompt` | Project rules injected into prompts |
| `checkpoints` | Forces STOP at each phase |
| `agents.cross_model_review` | Opus reviews Sonnet's work |

### Rule Files (`.zenflow/rules/`)

| File | Purpose |
|------|---------|
| `verification.md` | Pre/post edit checks |
| `anti-hallucination.md` | Banned behaviors, required evidence |
| `schema-boundaries.md` | Allowed/banned database schemas |
| `workflow-checkpoints.md` | Phase gates and approval process |

## Workflow Enforcement

```
┌─────────────────────────────────────────────────────┐
│  Phase 1: REQUIREMENTS                              │
│  ═══════════════════════════════════════════════   │
│  ██ CHECKPOINT: Zenflow PAUSES here ██             │
│  You must click "Approve" to continue               │
│                                                     │
│  Phase 2: SPECIFICATION                             │
│  ═══════════════════════════════════════════════   │
│  ██ CHECKPOINT: Zenflow PAUSES here ██             │
│                                                     │
│  Phase 3: PLAN                                      │
│  ═══════════════════════════════════════════════   │
│  ██ CHECKPOINT: Zenflow PAUSES here ██             │
│                                                     │
│  Phase 4: IMPLEMENTATION                            │
│  → configured verification command runs automatically│
│  → Must exit 0 to complete                          │
└─────────────────────────────────────────────────────┘
```

### Cross-Model Review

- **Implementation**: Claude Sonnet (fast)
- **Review**: Claude Opus (catches errors)

Opus reviews Sonnet's code, catching hallucinations.

## File Structure

```
.zenflow/
├── settings.json           # Zenflow reads this
├── README.md               # This file
├── rules/
│   ├── verification.md
│   ├── anti-hallucination.md
│   ├── schema-boundaries.md
│   └── workflow-checkpoints.md
├── workflows/
│   ├── full-sdd.md
│   ├── quick-change.md
│   └── fix-bug.md
├── templates/
│   ├── requirements.md
│   ├── spec.md
│   └── plan.md
└── tasks/                  # Task artifacts
```

## AI Assistant Instructions (For Claude Code)

When not using Zenflow IDE, AI must follow these rules:

### Before ANY Code Change

1. Read the workflow file: `.zenflow/workflows/[workflow].md`
2. Read relevant source files completely
3. Verify all imports exist
4. Check database schema in `prisma/schema.prisma`
5. Search for existing patterns

### Anti-Hallucination Rules

```
✅ GOOD: "I see in `file.py:L42` that..."
❌ BAD:  "I believe the function probably..."

✅ GOOD: "Verified in prisma/schema.prisma:L156"
❌ BAD:  "The table should exist..."
```

### Verification

```bash
# After EVERY edit:
.venv/bin/ruff check --select F401,F821 [file]

# Before claiming done:
# run the configured verification command from settings.json
```

### Checkpoint Behavior

At each checkpoint:
1. STOP and present artifact
2. Wait for explicit "approved" or "proceed"
3. Do not auto-continue

## Troubleshooting

### Zenflow not reading settings?

Verify you selected the repository root directory.

### Rules not loading?

Check Zenflow project settings:
- "Rules folders" → `.zenflow/rules`
- "Always include" → `CLAUDE.md`, `AGENTS.md`

### Verification failing?

Run the configured verification command from `.zenflow/settings.json`.

## Sources

- [Zenflow Documentation](https://docs.zencoder.ai/zenflow/integrations-and-settings)
- [Zenflow Download](https://zencoder.ai/download)
- [SDD Workflow](https://zencoder.ai/blog/spec-driven-development-sdd-the-engineering-method-ai-needed)
