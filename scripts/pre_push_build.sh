#!/usr/bin/env bash
# ============================================================================
# PRE-PUSH BUILD GATE - mirrors Vercel's build to catch failures locally
#
# Runs: git integrity check + next build
# Blocks push on failure. Use --no-verify to bypass in emergencies.
#
# Usage: scripts/pre_push_build.sh       (called by pre-push hook)
#        git push --no-verify             (emergency bypass)
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "============================================"
echo "  Pre-push build gate"
echo "============================================"

# Step 1: Git integrity (fast, < 1s)
echo ""
echo "[1/2] Git integrity check..."
if ! bash scripts/check_git_integrity.sh; then
    echo "PUSH BLOCKED: git integrity check failed"
    echo "Emergency bypass: git push --no-verify"
    exit 1
fi

# Step 2: Next.js build (mirrors Vercel, ~12s)
echo ""
echo "[2/2] Running next build (mirrors Vercel)..."
BUILD_START=$(date +%s)

if npm --prefix frontend run build >/dev/null 2>&1; then
    BUILD_END=$(date +%s)
    BUILD_DURATION=$((BUILD_END - BUILD_START))
    echo "  Build passed in ${BUILD_DURATION}s"
else
    BUILD_END=$(date +%s)
    BUILD_DURATION=$((BUILD_END - BUILD_START))
    echo ""
    echo "============================================"
    echo "PUSH BLOCKED: next build failed (${BUILD_DURATION}s)"
    echo "============================================"
    echo ""
    echo "This failure would also fail on Vercel."
    echo "Run 'npm --prefix frontend run build' to see full errors."
    echo ""
    echo "Emergency bypass: git push --no-verify"
    exit 1
fi

echo ""
echo "Pre-push gate: PASSED"
echo "============================================"
exit 0
