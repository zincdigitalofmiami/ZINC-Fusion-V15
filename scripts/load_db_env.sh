#!/usr/bin/env bash
# Shared DB env loader for local tooling (Prisma status/build gates).
# Precedence:
#   1) caller-provided environment (always wins)
#   2) .env.local
#   3) .env

set -euo pipefail

load_db_env() {
  local env_database_url="${DATABASE_URL:-}"
  local env_shadow_database_url="${SHADOW_DATABASE_URL:-}"
  local missing=0

  if [ -z "${DATABASE_URL:-}" ]; then
    missing=1
  fi

  if [ "$missing" -eq 1 ]; then
    local env_file
    for env_file in .env .env.local; do
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
  if [ -n "$env_shadow_database_url" ]; then
    export SHADOW_DATABASE_URL="$env_shadow_database_url"
  fi
}
