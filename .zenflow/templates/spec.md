# Technical Specification: {TASK_TITLE}

> **Created**: {DATE}
> **Task ID**: {TASK_ID}
> **Prerequisites**: requirements.md approved

---

## Architecture Overview

<!-- How does this change fit into the existing system? -->

```
[Diagram or description of where this fits]
```

---

## Files to Modify

### `{path/to/file1.py}`

**Current State** (verified at line {N}):
```python
# Actual code from the file - COPY/PASTE, don't paraphrase
```

**Proposed Change**:
```python
# What this will become
```

**Justification**: [Reference requirement this addresses]

---

### `{path/to/file2.py}`

**Current State** (verified at line {N}):
```python
# Actual code from the file
```

**Proposed Change**:
```python
# What this will become
```

**Justification**: [Reference requirement this addresses]

---

## Files to Create

| New File | Purpose | Template/Pattern Reference |
|----------|---------|---------------------------|
| `[path/to/new.py]` | [Purpose] | Based on `[existing/similar.py]` |

---

## Database Changes

### Schema Modifications

- [x] **No schema changes required** - Skip to Dependencies
- [ ] **Schema change required** - STOP: Get explicit approval per AGENTS.md

<!-- If schema change needed: -->
```prisma
// Proposed addition to prisma/schema.prisma
model NewTable {
  // ...
}
```

**Migration Plan**:
1. [Step 1]
2. [Step 2]

---

## Dependencies

### Internal Imports (Verified to Exist)

| Import | Source File | Verified |
|--------|-------------|----------|
| `from fusion.x import Y` | `src/fusion/x.py:L123` | [ ] Yes |
| `from fusion.a import B` | `src/fusion/a.py:L456` | [ ] Yes |

### External Packages

| Package | Version | Already in pyproject.toml? |
|---------|---------|---------------------------|
| `[package]` | `[version]` | [ ] Yes / [ ] No (needs approval) |

---

## Data Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Input     │────▶│  Process    │────▶│   Output    │
│ [describe]  │     │ [describe]  │     │ [describe]  │
└─────────────┘     └─────────────┘     └─────────────┘
```

### Data Contracts

- **Input**: [Schema/format of input data]
- **Output**: [Schema/format of output data]
- **Validation**: [How we verify correctness]

---

## Test Plan

### Unit Tests

| Test File | Test Function | What It Verifies |
|-----------|---------------|------------------|
| `tests/test_[module].py` | `test_[function]` | [Description] |

### Integration Tests

| Scenario | Steps | Expected Result |
|----------|-------|-----------------|
| [Scenario 1] | [Steps] | [Expected] |

### Manual Verification

```bash
# Commands to manually verify the change works
[command 1]
[command 2]
```

---

## Verification Commands

```bash
# Run after EACH implementation step
.venv/bin/ruff check --select F401,F821 [modified_files]

# Run after ALL changes
scripts/verify.sh

# Run specific tests
.venv/bin/pytest tests/test_[relevant].py -v
```

---

## Risk Assessment

### Reversibility

- [ ] **Easily reversible** - Can git revert
- [ ] **Requires migration rollback** - Document rollback steps
- [ ] **Not easily reversible** - Requires explicit approval

### Blast Radius

| Component | Could Be Affected? | Mitigation |
|-----------|-------------------|------------|
| [Component 1] | [ ] Yes / [ ] No | [How we prevent breakage] |
| [Component 2] | [ ] Yes / [ ] No | [How we prevent breakage] |

### Rollback Plan

1. [Step to undo if something goes wrong]
2. [Step to undo if something goes wrong]

---

## Cross-Reference Check

### Similar Implementations

<!-- REQUIRED: Find similar patterns in codebase -->

- `[file.py:line]` - [How this similar case was handled]

### Conflicts Check

```bash
# Verify no one else is modifying these files
git status
git log --oneline -5 [files_to_modify]
```

---

## Approval

- [ ] **Spec approved by user** - Date: ___
- [ ] All imports verified to exist
- [ ] All database tables verified to exist
- [ ] Risk assessment reviewed
- [ ] Ready to proceed to Phase 3: Implementation Plan
