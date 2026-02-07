# Full SDD Workflow

Spec-Driven Development workflow for complex tasks requiring 3+ steps.
Forces verification at each phase to eliminate hallucinations and ensure understanding.

## Configuration

- **Artifacts Path**: `.zenflow/tasks/{task_id}` (`.zenflow/tasks/{task_id}`)
- **Verification Script**: `scripts/verify.sh`
- **Review Required**: Yes (at each checkpoint)

---

## Phase 1: Requirements Gathering (PRD)

### Objective
Understand the problem completely before proposing solutions.

### Actions

1. **Read all relevant files** mentioned in the request
2. **Search codebase** for existing patterns that solve similar problems
3. **Query database schema** if data is involved (check `prisma/schema.prisma`)
4. **Document unknowns** - list what you DON'T know and need clarification on

### Artifact: `requirements.md`

Create `.zenflow/tasks/{task_id}/requirements.md` with:

```markdown
# Requirements: [Task Title]

## Problem Statement
[What problem are we solving? Why does it matter?]

## Success Criteria
- [ ] [Measurable outcome 1]
- [ ] [Measurable outcome 2]

## Constraints
- [Technical constraints from AGENTS.md]
- [Schema constraints - banned patterns, allowed schemas]
- [Performance/resource constraints]

## Existing Patterns Found
- `[file:line]` - [description of relevant code]
- `[file:line]` - [description of relevant code]

## Open Questions
1. [Question needing clarification]

## Evidence Gathered
- Searched: [list of grep/glob patterns used]
- Read: [list of files read completely]
- Verified: [database tables checked, schemas confirmed]
```

### Checkpoint 1: STOP
> **USER REVIEW REQUIRED**
> - Are requirements complete and correct?
> - Any missing constraints or context?
> - Approve before proceeding to Phase 2

---

## Phase 2: Technical Specification

### Objective
Design the solution with concrete references to existing code.

### Pre-Conditions
- [ ] Phase 1 `requirements.md` approved
- [ ] All open questions resolved

### Actions

1. **Identify all files to modify** (read each one completely)
2. **Map dependencies** between components
3. **Design data flow** with exact table/column names (verify they exist!)
4. **Identify test coverage** needed

### Artifact: `spec.md`

Create `.zenflow/tasks/{task_id}/spec.md` with:

```markdown
# Technical Specification: [Task Title]

## Architecture Overview
[How does this fit into the existing system?]

## Files to Modify

### [filename.py]
- **Current state**: [describe what exists at file:line]
- **Change**: [what will be added/modified]
- **Why**: [justification referencing requirements]

### [filename.ts]
- **Current state**: [describe what exists at file:line]
- **Change**: [what will be added/modified]
- **Why**: [justification referencing requirements]

## Files to Create
- `[path/to/new/file.py]` - [purpose]

## Database Changes
- [ ] No schema changes required
- [ ] Schema change required (STOP - get approval first per AGENTS.md)

## Dependencies
- Imports: [list all imports that will be used - verify they exist]
- External: [any new packages]

## Data Flow
```
[input] --> [step 1] --> [step 2] --> [output]
```

## Test Plan
- [ ] Unit test: [test_file.py::test_function]
- [ ] Integration test: [describe]
- [ ] Manual verification: [describe]

## Verification Commands
```bash
# Run after implementation
scripts/verify.sh
.venv/bin/pytest -q tests/[relevant_test].py
```

## Risk Assessment
- **Reversibility**: [Can this be easily reverted?]
- **Blast radius**: [What could break?]
- **Rollback plan**: [How to undo if needed]
```

### Checkpoint 2: STOP
> **USER REVIEW REQUIRED**
> - Is the technical approach sound?
> - Are all files and dependencies verified to exist?
> - Any architectural concerns?
> - Approve before proceeding to Phase 3

---

## Phase 3: Implementation Plan

### Objective
Break work into atomic, verifiable steps.

### Pre-Conditions
- [ ] Phase 2 `spec.md` approved
- [ ] All verification commands identified

### Artifact: `plan.md`

Create `.zenflow/tasks/{task_id}/plan.md` with:

```markdown
# Implementation Plan: [Task Title]

## Prerequisites
- [ ] Read spec.md
- [ ] All source files read completely
- [ ] Verification script ready: `scripts/verify.sh`

## Steps

### Step 1: [Description]
- **File**: `[path/to/file.py]`
- **Action**: [Add/Modify/Delete] [what specifically]
- **Lines**: [approximate line numbers]
- **Verify**: [how to verify this step worked]
- [ ] Complete

### Step 2: [Description]
- **File**: `[path/to/file.py]`
- **Action**: [Add/Modify/Delete] [what specifically]
- **Lines**: [approximate line numbers]
- **Verify**: [how to verify this step worked]
- [ ] Complete

### Step 3: Add tests
- **File**: `tests/test_[feature].py`
- **Action**: Create test file
- **Verify**: `.venv/bin/pytest tests/test_[feature].py -v`
- [ ] Complete

## Post-Implementation Checklist

- [ ] All steps marked complete
- [ ] `scripts/verify.sh` passes (exit 0)
- [ ] Tests pass: `.venv/bin/pytest -q`
- [ ] No new ruff errors
- [ ] If frontend changed: `npm --prefix frontend run lint`
- [ ] If Prisma changed: `npx prisma validate --schema prisma/schema.prisma`

## RED/GREEN/VERIFY Loop

For each step:
1. **RED**: Write/modify code
2. **GREEN**: Run step verification
3. **VERIFY**: Run `scripts/verify.sh`

Only proceed to next step when verification passes.
```

### Checkpoint 3: STOP
> **USER REVIEW REQUIRED**
> - Is the plan granular enough?
> - Are all verification steps clear?
> - Approve before proceeding to Phase 4

---

## Phase 4: Implementation

### Objective
Execute the plan with continuous verification.

### Pre-Conditions
- [ ] Phase 3 `plan.md` approved
- [ ] User explicitly said "proceed with implementation"

### Execution Rules

1. **One step at a time** - Complete and verify each step before moving on
2. **Update plan.md** - Mark each checkbox as you complete it
3. **Verify after each step** - Run the step's verification command
4. **STOP on failure** - Do not proceed if verification fails; fix first
5. **No invention** - Only use imports/functions/tables that exist

### AI Review Integration

After completing each file modification:

```bash
# Verify no hallucinated imports
.venv/bin/ruff check --select F401,F821 [modified_file.py]
```

### Final Verification

```bash
# MUST pass before marking complete
scripts/verify.sh

# Exit code 0 = safe to proceed
# Exit code 1 = BLOCKED - fix before claiming done
```

### Checkpoint 4: STOP
> **USER REVIEW REQUIRED**
> - Review all changes made
> - Verify `scripts/verify.sh` output shows all green
> - Approve before closing task

---

## Anti-Hallucination Checklist

Before claiming ANY task complete:

- [ ] Every import statement verified to exist
- [ ] Every function/class referenced verified to exist
- [ ] Every database table/column verified against `prisma/schema.prisma`
- [ ] Every file path verified with `ls` or glob
- [ ] `scripts/verify.sh` returns exit code 0
- [ ] Evidence cited: "I see in `file.py:L42` that..." not "I believe..."

---

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     FULL SDD WORKFLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│  │   Phase 1    │     │   Phase 2    │     │   Phase 3    │    │
│  │ Requirements │────▶│    Spec      │────▶│    Plan      │    │
│  │              │     │              │     │              │    │
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘    │
│         │                    │                    │             │
│    ┌────▼────┐          ┌────▼────┐          ┌────▼────┐       │
│    │ REVIEW  │          │ REVIEW  │          │ REVIEW  │       │
│    │CHECKPOINT│          │CHECKPOINT│          │CHECKPOINT│       │
│    └────┬────┘          └────┬────┘          └────┬────┘       │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                      Phase 4                              │  │
│  │                   Implementation                          │  │
│  │  ┌────────┐   ┌────────┐   ┌────────┐   ┌────────────┐   │  │
│  │  │ Step 1 │──▶│ Verify │──▶│ Step 2 │──▶│ ... │──▶ ✓  │   │  │
│  │  └────────┘   └────────┘   └────────┘   └────────────┘   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                         ┌────▼────┐                            │
│                         │ FINAL   │                            │
│                         │ REVIEW  │                            │
│                         └─────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```
