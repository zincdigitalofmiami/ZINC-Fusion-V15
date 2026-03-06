#!/usr/bin/env bash
# Shared DB env loader for local tooling (Prisma status/build gates).
# Precedence:
#   1) caller-provided environment (always wins)
#   2) .env.local.audit
#   3) .env.local
#   4) .env

set -euo pipefail

load_db_env() {
  local env_database_url="${DATABASE_URL:-}"
  local env_postgres_url="${POSTGRES_URL:-}"
  local env_direct_database_url="${DIRECT_DATABASE_URL:-}"
  local missing=0

  if [ -z "${DATABASE_URL:-}" ] || [ -z "${POSTGRES_URL:-}" ] || [ -z "${DIRECT_DATABASE_URL:-}" ]; then
    missing=1
  fi

  if [ "$missing" -eq 1 ]; then
    local env_file
    for env_file in .env.local.audit .env.local .env; do
      if [ -f "$env_file" ]; then
        set -a
        # shellcheck source=/dev/null
        source "$env_file"
        set +a
      fi
    done
  fi

  # Preserve explicit caller-provided values over any file-loaded values.
  if [ -n "$env_database_url" ]; then
    export DATABASE_URL="$env_database_url"
  fi
  if [ -n "$env_postgres_url" ]; then
    export POSTGRES_URL="$env_postgres_url"
  fi
  if [ -n "$env_direct_database_url" ]; then
    export DIRECT_DATABASE_URL="$env_direct_database_url"
  fi

  # Normalize aliases for downstream scripts.
  if [ -z "${POSTGRES_URL:-}" ] && [ -n "${DIRECT_DATABASE_URL:-}" ]; then
    export POSTGRES_URL="${DIRECT_DATABASE_URL}"
  fi
  if [ -z "${POSTGRES_URL:-}" ] && [ -n "${DATABASE_URL:-}" ]; then
    export POSTGRES_URL="${DATABASE_URL}"
  fi
  if [ -z "${DATABASE_URL:-}" ] && [ -n "${POSTGRES_URL:-}" ]; then
    export DATABASE_URL="${POSTGRES_URL}"
  fi
  if [ -z "${DIRECT_DATABASE_URL:-}" ] && [ -n "${POSTGRES_URL:-}" ]; then
    export DIRECT_DATABASE_URL="${POSTGRES_URL}"
  fi
}
