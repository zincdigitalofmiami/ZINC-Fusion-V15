# STOP AND THINK BEFORE EDITING

## MANDATORY PROCESS BEFORE ANY FILE EDIT

1. **READ FIRST** - Read the file completely before proposing changes
2. **VERIFY** - Confirm the change is correct by checking the database/schema
3. **ASK** - If deleting or modifying Prisma schema, ASK FOR APPROVAL FIRST
4. **MINIMAL** - Make the smallest possible change

## NEVER DO WITHOUT EXPLICIT USER APPROVAL

- Delete files
- Modify prisma/schema.prisma
- Drop database tables
- Bulk edits across multiple files

## FROM AGENTS.md (Line 34)

> "No destructive repo edits without explicit consent: do not delete, rename, move, or 'replace' files (including configs) unless the user explicitly requests it."

## FROM CLAUDE.md (Line 23)

> "Do not mutate Prisma schemas unless the user explicitly approves the exact change."

## FROM CLAUDE.md (Lines 9-10)

> "You always prioritize accuracy over speed."
> "Speed and pleasing the user is not your objective."

## PROCESS

1. STOP
2. READ the file
3. VERIFY against database
4. PROPOSE the change
5. WAIT for approval
6. THEN edit
