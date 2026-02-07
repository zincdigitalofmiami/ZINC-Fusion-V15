# Implementation Plan: {TASK_TITLE}

> **Created**: {DATE}
> **Task ID**: {TASK_ID}
> **Prerequisites**: spec.md approved

---

## Pre-Flight Checklist

Before starting implementation:

- [ ] `requirements.md` approved
- [ ] `spec.md` approved
- [ ] All source files read completely (not skimmed)
- [ ] All imports verified to exist
- [ ] All database tables verified in prisma/schema.prisma
- [ ] `scripts/verify.sh` runs successfully in current state
- [ ] User explicitly said "proceed with implementation"

---

## Implementation Steps

### Step 1: {Description}

**Target**: `{path/to/file.py}`
**Action**: {Add/Modify/Remove}
**Lines**: ~{line_range}

**What to do**:
```python
# Specific code or description of change
```

**Verify this step**:
```bash
.venv/bin/ruff check --select F401,F821 {path/to/file.py}
.venv/bin/python -c "from {module} import {thing}"
```

- [ ] Step complete
- [ ] Verification passed

---

### Step 2: {Description}

**Target**: `{path/to/file.py}`
**Action**: {Add/Modify/Remove}
**Lines**: ~{line_range}

**What to do**:
```python
# Specific code or description of change
```

**Verify this step**:
```bash
.venv/bin/ruff check --select F401,F821 {path/to/file.py}
```

- [ ] Step complete
- [ ] Verification passed

---

### Step 3: Add Tests

**Target**: `tests/test_{feature}.py`
**Action**: Create/Modify

**What to do**:
```python
# Test structure
def test_{function}():
    # Arrange
    # Act
    # Assert
```

**Verify this step**:
```bash
.venv/bin/pytest tests/test_{feature}.py -v
```

- [ ] Step complete
- [ ] Verification passed

---

## RED/GREEN/VERIFY Protocol

For EACH step:

```
┌─────────────────────────────────────────────────────────────┐
│  1. RED    │  Make the code change                          │
├────────────┼────────────────────────────────────────────────┤
│  2. GREEN  │  Run step verification → must pass             │
├────────────┼────────────────────────────────────────────────┤
│  3. VERIFY │  Run scripts/verify.sh → must exit 0           │
└────────────┴────────────────────────────────────────────────┘

          ┌──────────────────────┐
          │ STOP if verification │
          │ fails. Fix before    │
          │ proceeding.          │
          └──────────────────────┘
```

---

## Post-Implementation Checklist

### Code Quality Gates

```bash
# ALL must pass before marking complete

# 1. Ruff lint (catches hallucinated imports)
.venv/bin/ruff check --select F401,F403,F405,F821,F841 {modified_files}

# 2. Full verification suite
scripts/verify.sh

# 3. Specific tests
.venv/bin/pytest tests/test_{relevant}.py -v

# 4. If frontend changed
npm --prefix frontend run lint

# 5. If Prisma schema changed
npx prisma validate --schema prisma/schema.prisma
```

### Final Verification

- [ ] All steps marked complete
- [ ] All step verifications passed
- [ ] `scripts/verify.sh` exits with code 0
- [ ] No ruff errors (F401, F403, F405, F821, F841)
- [ ] pytest passes
- [ ] No new warnings introduced

---

## Anti-Hallucination Final Check

Before claiming done, verify:

- [ ] Every `import X from Y` - Y exists and exports X
- [ ] Every `function()` call - function exists in referenced module
- [ ] Every `table.column` - column exists in prisma/schema.prisma
- [ ] Every file path - file exists (use `ls` to verify)
- [ ] Every class instantiation - class is importable

---

## Evidence Log

<!-- Document verification evidence -->

| What | Evidence | Result |
|------|----------|--------|
| imports | `ruff check --select F821` | [ ] Pass |
| tests | `pytest -v` | [ ] Pass |
| full suite | `scripts/verify.sh` | [ ] Exit 0 |

---

## Completion

- [ ] All steps complete
- [ ] All verifications passed
- [ ] Evidence logged
- [ ] Ready for user review

**Final command output**:
```
# Paste output of scripts/verify.sh here
```
