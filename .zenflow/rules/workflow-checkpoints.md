# Workflow Checkpoints (ENFORCED)

## Full SDD Workflow Phases

### Phase 1: Requirements → STOP

**Deliverable:** `.zenflow/tasks/{id}/requirements.md`

**Before proceeding to Phase 2:**
```
[ ] Problem statement documented
[ ] Success criteria defined (measurable)
[ ] Constraints from AGENTS.md listed
[ ] Existing patterns searched and documented
[ ] Open questions listed (if any)
[ ] All relevant files READ (not skimmed)

>>> STOP: Present requirements.md for user review
>>> DO NOT proceed until user says "approved" or "proceed"
```

### Phase 2: Specification → STOP

**Deliverable:** `.zenflow/tasks/{id}/spec.md`

**Before proceeding to Phase 3:**
```
[ ] Every file to modify listed with current state
[ ] Every import verified to exist
[ ] Database tables verified in prisma/schema.prisma
[ ] Dependencies mapped
[ ] Test plan defined
[ ] Risk assessment completed

>>> STOP: Present spec.md for user review
>>> DO NOT proceed until user says "approved" or "proceed"
```

### Phase 3: Plan → STOP

**Deliverable:** `.zenflow/tasks/{id}/plan.md`

**Before proceeding to Phase 4:**
```
[ ] Steps are atomic and ordered
[ ] Each step has verification command
[ ] RED/GREEN/VERIFY pattern documented
[ ] Post-implementation checklist ready

>>> STOP: Present plan.md for user review
>>> DO NOT proceed until user says "approved" or "proceed"
```

### Phase 4: Implementation → Verify

**Execute plan with continuous verification:**
```
For each step:
  1. Make the change
  2. Run step verification
  3. Mark checkbox in plan.md
  4. If verification fails: FIX before next step

After all steps:
  scripts/verify.sh  # MUST exit 0
```

## Checkpoint Behavior

At each checkpoint:

1. **Present the artifact** - Show what you created
2. **Summarize key points** - 2-3 bullets
3. **List any concerns** - Risks, unknowns
4. **Wait explicitly** - Do not auto-continue

Example:
```markdown
## Checkpoint: Requirements Complete

Created: .zenflow/tasks/task-xxx/requirements.md

Key points:
- Adding new feature X to handle Y
- Will modify 3 files: A, B, C
- No schema changes required

Open questions:
- None

**Please review and approve to proceed to specification phase.**
```

## What "Approval" Looks Like

Valid approval signals:
- "Approved"
- "Proceed"
- "Looks good, continue"
- "Go ahead"

NOT approval:
- Silence
- Asking clarifying questions
- Suggesting changes

If unclear, ask: "Should I proceed to the next phase?"
