---
name: verify
description: Run the full project verification gate. Use before committing or when user says "verify", "check", or "run checks".
disable-model-invocation: true
---

## Current State
- Branch: !`git branch --show-current`
- Status: !`git status --short`

Run the full verification gate. Execute each step and report pass/fail:

1. **Python lint**: `make lint` (Ruff — F401, F403, F405, F821, F841)
2. **Frontend lint**: `make lint-frontend` (ESLint — max-warnings=0)
3. **TypeScript check**: `make tsc` (`npx tsc --noEmit`)
4. **Prisma validate**: `make prisma-validate` (schema consistency)
5. **Git integrity**: `make git-integrity` (exclude poisoning check)
6. **Python tests**: `make test` (pytest -q --tb=short)

## Output Format

```
VERIFICATION GATE
- Python lint:      [PASS/FAIL]
- Frontend lint:    [PASS/FAIL]
- TypeScript check: [PASS/FAIL]
- Prisma validate:  [PASS/FAIL]
- Git integrity:    [PASS/FAIL]
- Python tests:     [PASS/FAIL]

RESULT: [ALL PASS / X FAILURES]
```

If any step fails, show the error output and suggest a fix.
Do NOT proceed to commit if any step fails.
