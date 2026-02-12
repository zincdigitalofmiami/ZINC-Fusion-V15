#!/usr/bin/env bash
# ============================================================================
# PRE-PUSH BUILD GATE — mirrors Vercel's build to catch failures locally
#
# Runs: git integrity check + next build
# Blocks push on failure. Use --no-verify to bypass in emergencies.
#
# Usage: scripts/pre_push_build.sh       (called by pre-push hook)
#        git push --no-verify             (emergency bypass)
# ============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "============================================"
echo "  Pre-push build gate"
echo "============================================"

# Step 1: Git integrity (fast, < 1s)
echo ""
echo "[1/2] Git integrity check..."
if ! bash scripts/check_git_integrity.sh; then
    echo -e "${RED}PUSH BLOCKED: git integrity check failed${NC}"
    echo -e "${YELLOW}Emergency bypass: git push --no-verify${NC}"
    exit 1
fi

# Step 2: Next.js build (mirrors Vercel, ~12s)
echo ""
echo "[2/2] Running next build (mirrors Vercel)..."
BUILD_START=$(date +%s)

if npm --prefix frontend run build >/dev/null 2>&1; then
    BUILD_END=$(date +%s)
    BUILD_DURATION=$((BUILD_END - BUILD_START))
    echo -e "  ${GREEN}Build passed in ${BUILD_DURATION}s${NC}"
else
    BUILD_END=$(date +%s)
    BUILD_DURATION=$((BUILD_END - BUILD_START))
    echo ""
    echo -e "${RED}============================================${NC}"
    echo -e "${RED}PUSH BLOCKED: next build failed (${BUILD_DURATION}s)${NC}"
    echo -e "${RED}============================================${NC}"
    echo ""
    echo "This failure would also fail on Vercel."
    echo "Run 'npm --prefix frontend run build' to see full errors."
    echo ""
    echo -e "${YELLOW}Emergency bypass: git push --no-verify${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Pre-push gate: PASSED${NC}"
echo "============================================"
exit 0
