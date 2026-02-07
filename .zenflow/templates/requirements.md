# Requirements: {TASK_TITLE}

> **Created**: {DATE}
> **Task ID**: {TASK_ID}
> **Workflow**: Full SDD

---

## Problem Statement

<!-- What problem are we solving? Why does it matter? Be specific. -->

[DESCRIBE THE PROBLEM HERE]

---

## Success Criteria

<!-- Measurable outcomes - how do we know when we're done? -->

- [ ] [Criterion 1 - specific and measurable]
- [ ] [Criterion 2 - specific and measurable]
- [ ] [Criterion 3 - specific and measurable]

---

## Constraints

### From AGENTS.md (Non-Negotiable)

- [ ] No fabricated artifacts (schemas, tables, columns, functions)
- [ ] No mock/synthetic data unless explicitly requested
- [ ] Minimal and surgical changes only
- [ ] Forward fill is OFF by default
- [ ] No decision semantics (buy/sell/act now logic)

### Schema Constraints

- **Allowed schemas**: mkt, econ, alt, pos, supply, features, training, model, forecasts, analytics, metadata, ops
- **BANNED schemas**: raw, gold, silver, bronze, monitoring, specialist, weather, archive

### Project-Specific Constraints

<!-- Add any task-specific constraints here -->

- [Constraint 1]
- [Constraint 2]

---

## Existing Patterns Found

<!-- REQUIRED: Search the codebase before proposing new patterns -->

| File:Line | Description | Relevance |
|-----------|-------------|-----------|
| `[file.py:123]` | [What it does] | [How it relates to this task] |
| `[file.py:456]` | [What it does] | [How it relates to this task] |

### Search Evidence

```bash
# Searches performed:
rg "[pattern1]" src/
rg "[pattern2]" src/
glob "**/*[pattern]*"
```

---

## Database Verification

<!-- REQUIRED for any data-related work -->

### Tables Involved

| Schema.Table | Exists? | Columns Verified |
|--------------|---------|------------------|
| `[schema.table]` | [ ] Yes / [ ] No | [list relevant columns] |

### Verification Query

```sql
-- Run to verify table structure
\d [schema.table]
-- Or check prisma/schema.prisma
```

---

## Open Questions

<!-- List anything unclear - MUST be resolved before Phase 2 -->

1. [ ] [Question needing clarification]
2. [ ] [Question needing clarification]

---

## Files Read

<!-- REQUIRED: Document what you've actually read -->

- [ ] `[file1.py]` - read completely
- [ ] `[file2.py]` - read completely
- [ ] `prisma/schema.prisma` - verified tables

---

## Approval

- [ ] **Requirements approved by user** - Date: ___
- [ ] All open questions resolved
- [ ] Ready to proceed to Phase 2: Technical Specification
