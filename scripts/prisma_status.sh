#!/usr/bin/env bash
# Check Prisma migration status against PROD database
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Load DATABASE_URL from .env if not already set
if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  set -a
  source .env
  set +a
fi

echo "=== Prisma Migrate Status (PROD) ==="
npx prisma migrate status --config config/prisma.config.ts
