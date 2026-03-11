# ============================================================================
# ZINC-FUSION-V15 — Makefile (Enforcement Gates)
#
# AI agents: run `make check` before claiming ANY task is done.
# If it returns non-zero, you are BLOCKED.
# ============================================================================

.PHONY: check lint test verify install setup help git-integrity clean-worktrees clean-worktrees-auto db-parity-local

# The ONE command. Run this. If it fails, you're blocked.
check: verify

# Full verification gate (calls scripts/verify.sh)
verify:
	@bash scripts/verify.sh

# Python lint only
lint:
	@.venv/bin/ruff check --select F401,F403,F405,F821,F841 src/ scripts/ tests/

# Python tests only
test:
	@.venv/bin/pytest -q --tb=short

# Frontend lint only
lint-frontend:
	@npm --prefix frontend run lint

# TypeScript type-check only
tsc:
	@cd frontend && npx tsc --noEmit

# Prisma validate only
prisma-validate:
	@npx --yes --prefix config prisma validate --schema prisma/schema.prisma

# Local schema/data parity checks for audit-critical tables
db-parity-local:
	@bash -lc 'if [ -z "$${LOCAL_DATABASE_URL:-}" ]; then echo "ERROR: LOCAL_DATABASE_URL is not set"; exit 1; fi; psql "$$LOCAL_DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/check_local_v15_parity.sql'

# Format (auto-fix)
format:
	@.venv/bin/ruff format src/ scripts/ tests/
	@.venv/bin/ruff check --fix --select F401,F403,F405,F821,F841 src/ scripts/ tests/

# Git integrity check only
git-integrity:
	@bash scripts/check_git_integrity.sh

# Worktree cleanup (interactive)
clean-worktrees:
	@bash scripts/cleanup_worktrees.sh

# Worktree cleanup (auto — stale > 7 days)
clean-worktrees-auto:
	@bash scripts/cleanup_worktrees.sh --auto

# Install dependencies
install:
	@pip install -e ".[dev]"
	@pip install pre-commit ruff
	@pre-commit install
	@pre-commit install --hook-type pre-push
	@cd frontend && npm ci

# Setup from scratch
setup: install
	@echo "Setup complete. Run 'make check' to verify."

help:
	@echo "Usage:"
	@echo "  make check            Run ALL verification gates (REQUIRED before completing any task)"
	@echo "  make lint             Python ruff lint only"
	@echo "  make test             Python pytest only"
	@echo "  make lint-frontend    ESLint frontend only"
	@echo "  make tsc              TypeScript type-check only"
	@echo "  make prisma-validate  Validate Prisma schema"
	@echo "  make db-parity-local  Run local parity SQL checks"
	@echo "  make git-integrity    Check .git/info/exclude & untracked files"
	@echo "  make clean-worktrees  Interactive worktree/branch cleanup"
	@echo "  make format           Auto-format Python code"
	@echo "  make install          Install all dependencies + hooks"
	@echo "  make setup            Full setup from scratch"
