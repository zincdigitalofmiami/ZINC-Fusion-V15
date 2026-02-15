#!/usr/bin/env bash
# Prisma CLI wrapper — normalizes DB env vars and forwards args
# Usage: scripts/prisma.sh studio
#        scripts/prisma.sh migrate status
#        scripts/prisma.sh db pull
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Load env file when DB vars are missing.
_ENV_DATABASE_URL="${DATABASE_URL:-}"
_ENV_POSTGRES_URL="${POSTGRES_URL:-}"
_ENV_DIRECT_DATABASE_URL="${DIRECT_DATABASE_URL:-}"
if { [ -z "${DIRECT_DATABASE_URL:-}" ] || [ -z "${POSTGRES_URL:-}" ] || [ -z "${DATABASE_URL:-}" ]; } && [ -f .env ]; then
  set -a
  source .env
  set +a
fi
# Preserve explicit caller-provided env values.
if [ -n "${_ENV_DATABASE_URL}" ]; then
  export DATABASE_URL="${_ENV_DATABASE_URL}"
fi
if [ -n "${_ENV_POSTGRES_URL}" ]; then
  export POSTGRES_URL="${_ENV_POSTGRES_URL}"
fi
if [ -n "${_ENV_DIRECT_DATABASE_URL}" ]; then
  export DIRECT_DATABASE_URL="${_ENV_DIRECT_DATABASE_URL}"
fi

# Normalize aliases so downstream tooling can rely on either key.
if [ -z "${POSTGRES_URL:-}" ] && [ -n "${DIRECT_DATABASE_URL:-}" ]; then
  export POSTGRES_URL="${DIRECT_DATABASE_URL}"
fi
if [ -z "${POSTGRES_URL:-}" ] && [ -n "${DATABASE_URL:-}" ]; then
  export POSTGRES_URL="${DATABASE_URL}"
fi
if [ -z "${DATABASE_URL:-}" ] && [ -n "${POSTGRES_URL:-}" ]; then
  export DATABASE_URL="${POSTGRES_URL}"
fi

if [ -z "${POSTGRES_URL:-}" ] && [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: set DIRECT_DATABASE_URL or POSTGRES_URL (or DATABASE_URL) in environment/.env" >&2
  exit 1
fi

if printf "%s" "${POSTGRES_URL:-}" | grep -q '^prisma+postgres://'; then
  echo "ERROR: Prisma CLI needs a direct postgres:// URL for migrations/status." >&2
  echo "Set DIRECT_DATABASE_URL or POSTGRES_URL to direct Postgres from Prisma Console." >&2
  exit 1
fi

npx --prefix config prisma "$@" --config config/prisma.config.ts
