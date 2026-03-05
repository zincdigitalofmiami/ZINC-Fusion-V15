# ============================================================================
# ZINC-FUSION-V15 — Makefile (Enforcement Gates)
#
# AI agents: run `make check` before claiming ANY task is done.
# If it returns non-zero, you are BLOCKED.
# ============================================================================

.PHONY: check lint test verify install setup help git-preflight git-checkpoint git-safe-checkout git-integrity clean-worktrees clean-worktrees-auto db-guard-cloud db-guard-local db-guard-shadow db-parity-local mcp-up mcp-down mcp-logs mcp-restart inngest-guard inngest-health inngest-up inngest-heal inngest-heal-loop inngest-healer-install inngest-healer-uninstall inngest-healer-status inngest-healer-logs inngest-service-start inngest-service-stop inngest-service-status inngest-service-logs

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

# Format (auto-fix)
format:
	@.venv/bin/ruff format src/ scripts/ tests/
	@.venv/bin/ruff check --fix --select F401,F403,F405,F821,F841 src/ scripts/ tests/

# Git integrity check only
git-integrity:
	@bash scripts/check_git_integrity.sh

# Database identity guards
db-guard-cloud:
	@.venv/bin/python scripts/db_identity_guard.py --target cloud

db-guard-local:
	@.venv/bin/python scripts/db_identity_guard.py --target local-runtime

db-guard-shadow:
	@.venv/bin/python scripts/db_identity_guard.py --target local-shadow --skip-v15-checks

db-parity-local:
	@psql "$$LOCAL_DATABASE_URL" -f scripts/check_local_v15_parity.sql

# Git preflight guard (blocks dirty tree on main)
git-preflight:
	@bash scripts/git_preflight.sh

# Non-destructive recovery snapshot (patches + untracked tar + recovery branch)
git-checkpoint:
	@bash scripts/git_checkpoint.sh

# Safe branch switch (blocks dirty-tree checkout)
git-safe-checkout:
	@if [ -z "$(BRANCH)" ]; then \
		echo "Usage: make git-safe-checkout BRANCH=<branch-name>"; \
		exit 1; \
	fi
	@bash scripts/git_safe_checkout.sh "$(BRANCH)"

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

# ─── MCP Server Stack (Docker) ──────────────────────────────────────────────
# Shared across ALL AI tools: Roo, Copilot, Claude, Codex
# Ports: memory=18100, sequential-thinking=18101, context7=18102
mcp-up:
	@docker compose -f docker-compose.mcp.yml up -d

mcp-down:
	@docker compose -f docker-compose.mcp.yml down

mcp-logs:
	@docker compose -f docker-compose.mcp.yml logs -f

mcp-restart:
	@docker compose -f docker-compose.mcp.yml restart

# ─── Inngest Sync Guardrails ───────────────────────────────────────────────
inngest-guard:
	@bash scripts/inngest_guard.sh --static

inngest-health:
	@bash scripts/inngest_guard.sh --health

inngest-up:
	@bash scripts/inngest_guard.sh --preflight
	@docker compose -f docker-compose.inngest.yml up -d
	@bash scripts/inngest_guard.sh --health

inngest-heal:
	@bash scripts/inngest_heal.sh --once

inngest-heal-loop:
	@bash scripts/inngest_heal.sh --loop

inngest-healer-install:
	@bash scripts/inngest_healer_launchd.sh install

inngest-healer-uninstall:
	@bash scripts/inngest_healer_launchd.sh uninstall

inngest-healer-status:
	@bash scripts/inngest_healer_launchd.sh status

inngest-healer-logs:
	@bash scripts/inngest_healer_launchd.sh logs

inngest-service-start:
	@bash scripts/inngest_heal_service.sh start

inngest-service-stop:
	@bash scripts/inngest_heal_service.sh stop

inngest-service-status:
	@bash scripts/inngest_heal_service.sh status

inngest-service-logs:
	@bash scripts/inngest_heal_service.sh logs

help:
	@echo "Usage:"
	@echo "  make check            Run ALL verification gates (REQUIRED before completing any task)"
	@echo "  make lint             Python ruff lint only"
	@echo "  make test             Python pytest only"
	@echo "  make lint-frontend    ESLint frontend only"
	@echo "  make tsc              TypeScript type-check only"
	@echo "  make prisma-validate  Validate Prisma schema"
	@echo "  make git-preflight    Guardrail check (branch + dirty-tree safety)"
	@echo "  make git-checkpoint   Create recovery snapshot + branch pointer"
	@echo "  make git-safe-checkout BRANCH=<name>  Safe branch switch (clean tree required)"
	@echo "  make git-integrity    Check .git/info/exclude & untracked files"
	@echo "  make db-guard-cloud   Assert cloud DB identity and V15 schema/table contract"
	@echo "  make db-guard-local   Assert LOCAL_DATABASE_URL points to zinc_fusion_v15_local"
	@echo "  make db-guard-shadow  Assert SHADOW_DATABASE_URL points to zinc_fusion_v15_shadow"
	@echo "  make db-parity-local  Run local V15 parity SQL report"
	@echo "  make clean-worktrees  Interactive worktree/branch cleanup"
	@echo "  make format           Auto-format Python code"
	@echo "  make install          Install all dependencies + hooks"
	@echo "  make setup            Full setup from scratch"
	@echo "  make mcp-up           Start MCP server stack (Docker) — memory/context7/sequential-thinking"
	@echo "  make mcp-down         Stop MCP server stack"
	@echo "  make mcp-logs         Tail MCP server logs"
	@echo "  make mcp-restart      Restart MCP server stack"
	@echo "  make inngest-guard    Static guardrail checks for Inngest sync config"
	@echo "  make inngest-health   Runtime Inngest health + port ownership checks"
	@echo "  make inngest-up       Preflight checks, start Inngest dev server, post-check health"
	@echo "  make inngest-heal     Auto-heal once (restart/repair if drift is detected)"
	@echo "  make inngest-heal-loop Continuous self-healing loop for dev uptime"
	@echo "  make inngest-healer-install Install launchd self-healer (always on)"
	@echo "  make inngest-healer-uninstall Remove launchd self-healer"
	@echo "  make inngest-healer-status Show launchd self-healer status"
	@echo "  make inngest-healer-logs Tail launchd self-healer logs"
	@echo "  make inngest-service-start Start fallback self-healing watchdog"
	@echo "  make inngest-service-stop Stop fallback self-healing watchdog"
	@echo "  make inngest-service-status Show fallback watchdog status"
	@echo "  make inngest-service-logs Tail fallback watchdog logs"
