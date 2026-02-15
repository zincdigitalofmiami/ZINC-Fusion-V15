#!/usr/bin/env bash
# Prisma CLI wrapper — loads DATABASE_URL from .env and forwards args
# Usage: scripts/prisma.sh studio
#        scripts/prisma.sh migrate status
#        scripts/prisma.sh db pull
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Load DATABASE_URL from .env if not already set
if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  set -a
  source .env
  set +a
fi

npx --prefix config prisma "$@" --config config/prisma.config.ts
