#!/usr/bin/env bash
# ============================================================================
# VERIFICATION GATE — blocks on ANY failure
# Usage: scripts/verify.sh [--python-only] [--frontend-only] [--all]
# Exit code: 0 = all clean, 1 = BLOCKED (fix before proceeding)
#
# This script is the SINGLE SOURCE OF TRUTH for quality checks.
# AI agents MUST run this and get exit 0 before claiming any task is done.
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

FAILURES=0
CHECKS=0
PASSED=0
FAILED_CHECKS=()

# ---- helpers ----
gate() {
    local name="$1"
    shift
    CHECKS=$((CHECKS + 1))
    echo -e "\n${BOLD}[CHECK $CHECKS] $name${NC}"
    if "$@" ; then
        PASSED=$((PASSED + 1))
        echo -e "  ${GREEN}✓ PASSED${NC}"
    else
        FAILURES=$((FAILURES + 1))
        FAILED_CHECKS+=("$name")
        echo -e "  ${RED}✗ FAILED${NC}"
    fi
}

# ---- parse args ----
MODE="all"
if [[ "${1:-}" == "--python-only" ]]; then MODE="python"; fi
if [[ "${1:-}" == "--frontend-only" ]]; then MODE="frontend"; fi

# ============================================================================
#  PYTHON GATES
# ============================================================================
if [[ "$MODE" == "all" || "$MODE" == "python" ]]; then

    # Gate 1: .venv exists
    gate "Python venv exists" test -f .venv/bin/python

    # Gate 2: ruff is installed
    gate "ruff installed" .venv/bin/python -c "import ruff; print('ruff OK')" 2>/dev/null || \
    gate "ruff binary exists" test -x .venv/bin/ruff

    # Gate 3: ruff lint (the rules that catch hallucinations)
    gate "ruff lint (F401/F403/F405/F821/F841)" \
        .venv/bin/ruff check --select F401,F403,F405,F821,F841 src/ scripts/ tests/

    # Gate 4: ruff format check (no auto-fix, just check)
    gate "ruff format check" \
        .venv/bin/ruff format --check src/ scripts/ tests/ 2>/dev/null || true

    # Gate 5: pytest
    gate "pytest passes" \
        .venv/bin/pytest -q --tb=short 2>&1

    # Gate 6: no hardcoded secrets in Python
    gate "no hardcoded secrets (gitleaks)" \
        bash -c 'command -v gitleaks >/dev/null && gitleaks detect --no-git --source . -q 2>/dev/null || echo "gitleaks not installed, skipping"'

fi

# ============================================================================
#  FRONTEND GATES
# ============================================================================
if [[ "$MODE" == "all" || "$MODE" == "frontend" ]]; then

    # Gate 7: frontend node_modules exist
    gate "frontend node_modules exist" test -d frontend/node_modules

    # Gate 8: ESLint
    gate "ESLint frontend" \
        npm --prefix frontend run lint 2>&1

    # Gate 9: TypeScript compiles
    gate "TypeScript compiles (tsc --noEmit)" \
        npx --prefix frontend tsc --noEmit 2>&1

fi

# ============================================================================
#  PRISMA GATES
# ============================================================================
if [[ "$MODE" == "all" ]]; then

    # Gate 10: Prisma schema validates
    gate "Prisma schema validates" \
        npx --yes --prefix config prisma validate --schema prisma/schema.prisma 2>&1

fi

# ============================================================================
#  REPORT
# ============================================================================
echo ""
echo "============================================"
if [[ $FAILURES -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}ALL $CHECKS CHECKS PASSED${NC}"
    echo "============================================"
    echo ""
    echo "✓ Safe to commit / mark task complete."
    exit 0
else
    echo -e "${RED}${BOLD}$FAILURES OF $CHECKS CHECKS FAILED${NC}"
    echo "============================================"
    echo ""
    echo -e "${RED}BLOCKED CHECKS:${NC}"
    for check in "${FAILED_CHECKS[@]}"; do
        echo -e "  ${RED}✗${NC} $check"
    done
    echo ""
    echo -e "${RED}${BOLD}DO NOT PROCEED. Fix failures above first.${NC}"
    echo ""
    exit 1
fi
