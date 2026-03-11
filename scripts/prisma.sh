#!/usr/bin/env bash
# Prisma CLI wrapper — normalizes DB env vars and forwards args
# Usage: scripts/prisma.sh studio
#        scripts/prisma.sh migrate status
#        scripts/prisma.sh db pull
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

source scripts/load_db_env.sh
load_db_env

if [ -z "${POSTGRES_URL:-}" ] && [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: set DIRECT_DATABASE_URL or POSTGRES_URL (or DATABASE_URL) in env, .env.local, or .env" >&2
  exit 1
fi

if printf "%s" "${POSTGRES_URL:-}" | grep -q '^prisma+postgres://'; then
  echo "ERROR: Prisma CLI needs a direct postgres:// URL for migrations/status." >&2
  echo "Set DIRECT_DATABASE_URL or POSTGRES_URL to direct Postgres from Prisma Console." >&2
  exit 1
fi

npx --prefix config prisma "$@" --config config/prisma.config.ts
