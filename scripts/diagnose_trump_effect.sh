#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

source scripts/load_db_env.sh
load_db_env

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is not configured." >&2
  exit 1
fi

psql "$DATABASE_URL" -f scripts/diagnose_trump_effect.sql
