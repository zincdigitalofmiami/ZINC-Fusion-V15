# Fix Bug Workflow

Structured approach to debugging that prevents "fixing" the wrong thing.

## Configuration

- **Artifacts Path**: `.zenflow/tasks/{task_id}`
- **Required Evidence**: Reproduction steps + root cause analysis

---

## Phase 1: Reproduce and Understand

### Objective
Prove you understand the bug before attempting to fix it.

### Actions

1. **Get reproduction steps** - Ask if not provided
2. **Reproduce locally** - Run the failing scenario
3. **Capture error output** - Full stack trace, not just the message
4. **Identify the failing line** - Exact file:line where error originates

### Artifact: Bug Report

Document in `.zenflow/tasks/{task_id}/bug-report.md`:

```markdown
# Bug Report: [Brief Description]

## Reproduction Steps
1. [Step 1]
2. [Step 2]
3. [Expected vs Actual]

## Error Output
```
[Full stack trace]
```

## Root Cause Analysis

### Failing Location
- **File**: `[file.py:line]`
- **Function**: `[function_name]`
- **Symptom**: [What goes wrong]

### Root Cause
[Why it fails - the actual bug, not just where it crashes]

### Evidence
- Read `[file:line]` - found [observation]
- Searched for `[pattern]` - found [count] occurrences
- Verified [table/schema/function] exists: [yes/no]
```

### Checkpoint: STOP
> **Confirm understanding before fixing**
> - Can you explain WHY it fails, not just WHERE?
> - Is this the root cause or a symptom?

---

## Phase 2: Design the Fix

### Objective
Propose a minimal, targeted fix.

### Anti-Patterns to Avoid

- **Fixing symptoms** - Adding try/catch around the real bug
- **Over-engineering** - Refactoring unrelated code
- **Guessing** - "This might help" without understanding

### Artifact: Fix Proposal

Add to `.zenflow/tasks/{task_id}/bug-report.md`:

```markdown
## Proposed Fix

### Change Summary
[One sentence describing the fix]

### File(s) to Modify
- `[file.py:line]` - [specific change]

### Why This Fixes It
[Explain how this addresses the root cause]

### What We're NOT Changing
[Explicitly list related code we're leaving alone]

### Test to Verify
```bash
[Command that will prove the fix works]
```
```

### Checkpoint: STOP
> **Review fix proposal**
> - Is this the minimal fix?
> - Does it address root cause?
> - What could this break?

---

## Phase 3: Implement and Verify

### Pre-Conditions
- [ ] Root cause understood and documented
- [ ] Fix proposal approved
- [ ] Test command identified

### Execution

1. **Read the file completely** before editing
2. **Make the minimal change** - no drive-by refactoring
3. **Run the verification test** immediately
4. **Run full verification** - `scripts/verify.sh`

### Post-Fix Verification

```bash
# 1. Specific test for this bug
[reproduction command - should now pass]

# 2. Regression check
scripts/verify.sh

# 3. Related tests
.venv/bin/pytest tests/[related_module]_test.py -v
```

### Completion Criteria

- [ ] Bug no longer reproduces
- [ ] `scripts/verify.sh` passes
- [ ] No new failures introduced
- [ ] Root cause documented for future reference
