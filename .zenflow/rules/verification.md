# Verification Rules (ENFORCED)

## Before ANY Code Edit

You MUST complete these checks before using Edit/Write tools:

### 1. File Read Requirement
```
✗ BLOCKED: Editing a file you haven't read in this session
✓ ALLOWED: Edit after using Read tool on the complete file
```

### 2. Import Verification
```bash
# Before adding any import, verify it exists:
.venv/bin/python -c "from {module} import {thing}"

# After editing, check for undefined names:
.venv/bin/ruff check --select F821 {file}
```

### 3. Database Schema Verification
```
# Before referencing any table/column:
1. Read prisma/schema.prisma
2. Find the exact model definition
3. Cite: "Verified in prisma/schema.prisma:L{line}"
```

## After ANY Code Edit

```bash
# MANDATORY - run after every edit:
.venv/bin/ruff check --select F401,F821 {modified_file}

# If ruff fails: FIX IMMEDIATELY before proceeding
```

## Before Claiming "Done"

```bash
# This MUST exit 0:
scripts/verify.sh

# If it fails, you are NOT done. Fix the failures.
```

## Evidence Citation Format

```
✗ BAD:  "The function probably exists..."
✗ BAD:  "I believe the table has..."
✓ GOOD: "Verified at src/fusion/db/connection.py:L42 - get_connection() exists"
✓ GOOD: "Confirmed in prisma/schema.prisma:L156 - mkt.futures_1d has 'close' column"
```
