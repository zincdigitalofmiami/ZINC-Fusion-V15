# Quick Change Workflow

For simple changes (1-2 steps) that don't require full SDD ceremony.
Still enforces verification but skips the multi-phase artifact creation.

## When to Use

- Bug fixes in a single file
- Adding a small function to existing module
- Configuration changes
- Documentation updates
- Typo fixes

## When NOT to Use

If ANY of these apply, use `full-sdd.md` instead:
- [ ] Touching 3+ files
- [ ] Database schema changes
- [ ] New feature requiring design decisions
- [ ] Cross-cutting concerns (affects multiple modules)
- [ ] Unclear requirements

---

## Pre-Flight Checklist

Before making any change:

- [ ] Read the target file completely (not just the function)
- [ ] Search for similar patterns in codebase
- [ ] State the change: "I will modify `[file:line]` to [change] because [reason]"

---

## Execution

### Step 1: Verify Current State

```bash
# Read the file
cat [path/to/file.py]

# Check for existing patterns
rg "[pattern]" src/

# Verify imports exist (if adding new ones)
.venv/bin/python -c "from [module] import [thing]"
```

### Step 2: Make the Change

- Single edit operation
- Minimal diff
- Preserve existing style

### Step 3: Verify

```bash
# REQUIRED - must pass
scripts/verify.sh --python-only  # or --frontend-only

# If tests exist for this area
.venv/bin/pytest tests/[relevant_test].py -v
```

---

## Anti-Hallucination Mini-Checklist

- [ ] File exists and was read before editing
- [ ] All imports verified to exist
- [ ] All referenced functions/classes exist
- [ ] `scripts/verify.sh` passes

---

## Completion Criteria

Only claim done when:

1. Change is made
2. Verification script passes (exit 0)
3. You can cite: "Change made at `[file:line]`, verified by `[command]`"
