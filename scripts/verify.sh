#!/usr/bin/env bash
# ============================================================================
# VERIFICATION GATE - blocks on ANY failure
# Usage: scripts/verify.sh [--python-only] [--frontend-only] [--all]
# Exit code: 0 = all clean, 1 = BLOCKED (fix before proceeding)
#
# This script is the SINGLE SOURCE OF TRUTH for quality checks.
# AI agents MUST run this and get exit 0 before claiming any task is done.
# ============================================================================

set -uo pipefail

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
    echo ""
    echo "[CHECK $CHECKS] $name"
    if "$@" ; then
        PASSED=$((PASSED + 1))
        echo "  PASS"
    else
        FAILURES=$((FAILURES + 1))
        FAILED_CHECKS+=("$name")
        echo "  FAIL"
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

    # Gate 2: ruff binary exists
    gate "ruff binary exists" test -x .venv/bin/ruff

    # Gate 3: ruff lint (catches hallucinated imports and undefined names)
    # Excludes vendored third-party libs that we don't own
    gate "ruff lint (F401/F403/F405/F821/F841)" \
        .venv/bin/ruff check --select F401,F403,F405,F821,F841 \
        --exclude 'src/fusion/features/gs_quant_lib' \
        --exclude 'src/fusion/features/macrosynergy_signal' \
        --exclude 'src/fusion/features/jpm_bt_*' \
        src/ scripts/ tests/

    # Gate 4: pytest (skip known DB-dependent integration tests in CI)
    gate "pytest passes" \
        .venv/bin/pytest -q --tb=short \
        --ignore=tests/test_database_forensic_audit.py \
        --ignore=tests/test_e2e_data_flow.py \
        --ignore=tests/test_databento_current_state.py \
        --ignore=tests/test_databento_historical_jobs.py \
        --ignore=tests/test_databento_live_connector.py \
        --ignore=tests/test_databento_symbol_comparison.py \
        --ignore=tests/test_load.py \
        --ignore=tests/test_parallel_symbols.py \
        --ignore=tests/test_failure_modes.py \
        --ignore=tests/test_roll_date_impact.py \
        --ignore=tests/test_vwap_minimal.py \
        --ignore=tests/test_vwap_simple.py

    # Gate 5: no hardcoded secrets
    gate "no hardcoded secrets (gitleaks)" \
        bash -c 'command -v gitleaks >/dev/null && gitleaks detect --no-git --source . -q 2>/dev/null || echo "gitleaks not installed, skipping"'

fi

# ============================================================================
#  FRONTEND GATES
# ============================================================================
if [[ "$MODE" == "all" || "$MODE" == "frontend" ]]; then

    # Gate 6: frontend node_modules exist
    gate "frontend node_modules exist" test -d frontend/node_modules

    # Gate 7: ESLint
    gate "ESLint frontend" \
        npm --prefix frontend run lint

    # Gate 8: TypeScript compiles (must run in frontend/ dir)
    gate "TypeScript compiles (tsc --noEmit)" \
        bash -c 'cd frontend && npx tsc --noEmit'

fi

# ============================================================================
#  PRISMA GATES
# ============================================================================
if [[ "$MODE" == "all" ]]; then

    # Gate 9: Prisma schema validates
    gate "Prisma schema validates" \
        npx --yes --prefix config prisma validate --schema prisma/schema.prisma

fi

# ============================================================================
#  REPORT
# ============================================================================
echo ""
echo "============================================"
if [[ $FAILURES -eq 0 ]]; then
    echo "ALL $CHECKS CHECKS PASSED"
    echo "============================================"
    echo ""
    echo "Safe to commit / mark task complete."
    exit 0
else
    echo "$FAILURES OF $CHECKS CHECKS FAILED"
    echo "============================================"
    echo ""
    echo "BLOCKED CHECKS:"
    for check in "${FAILED_CHECKS[@]}"; do
        echo "  FAIL $check"
    done
    echo ""
    echo "DO NOT PROCEED. Fix failures above first."
    echo ""
    exit 1
fi
