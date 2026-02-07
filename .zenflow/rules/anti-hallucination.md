# Anti-Hallucination Rules (HARD LOCKS)

## Banned Behaviors

### 1. Inventing Symbols
```
✗ NEVER: Import functions/classes that don't exist
✗ NEVER: Reference tables/columns not in prisma/schema.prisma
✗ NEVER: Call methods that aren't defined in the class
✗ NEVER: Use file paths without verifying they exist
```

### 2. Vague Language
```
✗ BANNED PHRASES:
  - "I believe..."
  - "I think..."
  - "probably..."
  - "should work..."
  - "might be..."
  - "likely..."

✓ REQUIRED INSTEAD:
  - "Verified at {file}:{line}..."
  - "Confirmed by running {command}..."
  - "I don't know - need to check..."
```

### 3. Skipping Verification
```
✗ NEVER: Claim "done" without scripts/verify.sh exit 0
✗ NEVER: Skip ruff check after editing Python
✗ NEVER: Assume imports work without testing
✗ NEVER: Proceed past checkpoint without approval
```

## Required Behaviors

### 1. Search Before Writing
```bash
# Before writing new code, search for existing patterns:
rg "similar_pattern" src/
glob "**/*relevant*"

# Use existing patterns, don't reinvent
```

### 2. Read Before Editing
```
# For EVERY file you plan to edit:
1. Use Read tool on the COMPLETE file
2. Understand the context around your change
3. Only then use Edit tool
```

### 3. Verify Before Proceeding
```
# After EVERY code change:
.venv/bin/ruff check --select F821 {file}  # Check for undefined names
.venv/bin/pytest tests/{relevant_test}.py   # If tests exist
```

## Consequences of Violations

If you violate these rules:
1. Your edit will introduce ImportError/NameError
2. scripts/verify.sh will fail
3. You will need to fix and re-verify
4. User trust decreases

**Prevention is faster than fixing. Verify first.**
