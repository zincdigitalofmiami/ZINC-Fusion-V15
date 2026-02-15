#!/usr/bin/env bash
# ============================================================================
# GIT INTEGRITY CHECK - catches "works locally, fails on CI" bugs
#
# Checks:
#   1. .git/info/exclude has no active rules hiding source files
#   2. Every module re-exported from functions.ts is git-tracked
#   3. No ghost .ts/.tsx files in frontend/src/ (on disk but untracked)
#
# Usage: scripts/check_git_integrity.sh
# Exit:  0 = clean, 1 = integrity violation
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

FAILURES=0

# --------------------------------------------------------------------------
# CHECK 1: .git/info/exclude poisoning
# --------------------------------------------------------------------------
echo "[1/3] Checking .git/info/exclude..."

EXCLUDE_FILE=".git/info/exclude"
if [ -f "$EXCLUDE_FILE" ]; then
    # Strip comments and blank lines - anything left is an active rule
    ACTIVE_RULES=$(grep -v '^\s*#' "$EXCLUDE_FILE" | grep -v '^\s*$' || true)
    if [ -n "$ACTIVE_RULES" ]; then
        echo "BLOCKED: .git/info/exclude contains active rules:"
        echo "$ACTIVE_RULES"
        echo ""
        echo "  These hide files from git locally while CI/Vercel won't see them."
        echo "  Fix: Move entries to .gitignore or remove them from .git/info/exclude"
        FAILURES=$((FAILURES + 1))
    else
        echo "  OK - no active exclude rules"
    fi
else
    echo "  OK - no exclude file"
fi

# --------------------------------------------------------------------------
# CHECK 2: Barrel re-export integrity (functions.ts)
# --------------------------------------------------------------------------
echo "[2/3] Checking inngest/functions.ts re-export integrity..."

BARREL="frontend/src/inngest/functions.ts"
if [ -f "$BARREL" ]; then
    # Extract module paths from: export { ... } from "./module-name";
    MODULES=$(grep -o 'from "\./[^"]*"' "$BARREL" | sed 's/from "\.\/\(.*\)"/\1/' || true)
    MISSING=0
    for module in $MODULES; do
        TARGET="frontend/src/inngest/${module}.ts"
        # Check git-tracked (not just on disk - that's the whole point)
        if ! git ls-files --error-unmatch "$TARGET" >/dev/null 2>&1; then
            echo "  NOT TRACKED: ${TARGET}"
            if [ -f "$TARGET" ]; then
                echo "    File exists on disk but is NOT in git - CI will fail"
                echo "    Fix: git add ${TARGET}"
            else
                echo "    File does not exist - build will fail everywhere"
            fi
            MISSING=$((MISSING + 1))
        fi
    done
    if [ "$MISSING" -gt 0 ]; then
        FAILURES=$((FAILURES + 1))
    else
        MODULE_COUNT=$(echo "$MODULES" | wc -w | tr -d ' ')
        echo "  OK - all ${MODULE_COUNT} re-exported modules are git-tracked"
    fi
else
    echo "  SKIP - $BARREL not found"
fi

# --------------------------------------------------------------------------
# CHECK 3: Ghost TypeScript files (on disk, not tracked)
# --------------------------------------------------------------------------
echo "[3/3] Checking for ghost .ts/.tsx files in frontend/src/..."

# Use --exclude-standard to apply .gitignore but NOT .git/info/exclude
# (which is intentional - we want to catch files hidden by exclude)
GHOSTS=$(git ls-files --others --exclude-from=.gitignore \
    -- 'frontend/src/**/*.ts' 'frontend/src/**/*.tsx' 2>/dev/null || true)

if [ -n "$GHOSTS" ]; then
    GHOST_COUNT=$(echo "$GHOSTS" | wc -l | tr -d ' ')
    echo "  FOUND ${GHOST_COUNT} untracked TypeScript file(s):"
    echo "$GHOSTS" | head -20
    echo ""
    echo "  These exist locally but won't be in CI/Vercel builds."
    echo "  Fix: git add <file> or add to .gitignore"
    FAILURES=$((FAILURES + 1))
else
    echo "  OK - no ghost TypeScript files"
fi

# --------------------------------------------------------------------------
# RESULT
# --------------------------------------------------------------------------
echo ""
if [ "$FAILURES" -eq 0 ]; then
    echo "Git integrity: PASSED"
    exit 0
else
    echo "Git integrity: FAILED ($FAILURES violation(s))"
    exit 1
fi
