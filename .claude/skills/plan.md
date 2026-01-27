NOTE: Production is the dashboard/frontend, not the repo root.
# /plan - Structured Implementation Planning

## Purpose
Augment-style structured planning before implementation. Forces thorough analysis and explicit plan approval before any code is written.

## Trigger
Use `/plan` when starting any non-trivial implementation task.

## Planning Protocol

### Phase 1: Context Gathering
```
1. Read MCP memory graph (mcp__memory__read_graph)
2. Identify relevant files using Glob/Grep
3. Read key files that will be affected
4. Check git status for current state
5. Query database if task involves data
```

### Phase 2: Analysis (Use Sequential Thinking)
```
mcp__sequential-thinking__sequentialthinking with:
- Thought 1: What is the actual goal?
- Thought 2: What exists today that relates to this?
- Thought 3: What are the possible approaches?
- Thought 4: What are the tradeoffs of each approach?
- Thought 5: What could go wrong?
- Thought 6: What's the minimal viable implementation?
```

### Phase 3: Plan Output

Generate this exact format:

```markdown
## Implementation Plan: [Task Name]

### Goal
[One sentence describing the objective]

### Current State
- [What exists today]
- [What works/doesn't work]
- [Relevant constraints]

### Proposed Approach
[Brief description of the chosen approach and why]

### Files to Modify
| File | Action | Reason |
|------|--------|--------|
| path/to/file.py | Edit | [reason] |
| path/to/new.py | Create | [reason] |

### Implementation Steps
1. [ ] Step 1 - [description]
2. [ ] Step 2 - [description]
3. [ ] Step 3 - [description]
...

### Validation Plan
- [ ] [How to verify step 1 worked]
- [ ] [How to verify step 2 worked]
- [ ] [Final acceptance criteria]

### Risks & Mitigations
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| [risk 1] | Low/Med/High | [mitigation] |

### Reversibility
- Can this be reverted? [Yes/No/Partial]
- Rollback steps: [if applicable]

### Approval Required
- [ ] Schema changes: [Yes/No - if Yes, list them]
- [ ] New dependencies: [Yes/No - if Yes, list them]
- [ ] Breaking changes: [Yes/No - if Yes, describe]
```

### Phase 4: Approval Gate

**Before proceeding, explicitly ask:**
> "Here is my implementation plan. Please review and approve, or let me know what changes you'd like."

**Do NOT start implementation until user confirms.**

## When to Use /plan

| Scenario | Use /plan? |
|----------|------------|
| New feature implementation | ✅ Yes |
| Multi-file refactor | ✅ Yes |
| Database schema change | ✅ Yes (mandatory) |
| Bug fix (single file) | ⚠️ Optional |
| Config change | ❌ No |
| Documentation update | ❌ No |
| Single-line fix | ❌ No |

## Integration with Other Tools

- **Sequential Thinking**: Use for analysis phase
- **Memory**: Store approved plans for reference
- **Micro-Planner**: Use during implementation for progress tracking
- **TodoWrite**: Convert plan steps to tracked todos

## Example Usage

User: "Add caching to the API endpoints"