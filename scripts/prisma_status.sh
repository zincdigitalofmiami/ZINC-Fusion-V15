#!/usr/bin/env bash
# Check Prisma migration status against PROD database
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

source scripts/load_db_env.sh
load_db_env

if [ -z "${POSTGRES_URL:-}" ] && [ -z "${DATABASE_URL:-}" ]; then
  echo "FALLBACK FAILED: set DIRECT_DATABASE_URL or POSTGRES_URL (or DATABASE_URL) in env, .env.local.audit, .env.local, or .env"
  exit 1
fi

if printf "%s" "${POSTGRES_URL:-}" | grep -q '^prisma+postgres://'; then
  echo "FALLBACK FAILED: POSTGRES_URL/DIRECT_DATABASE_URL must be direct postgres:// for migrate/status."
  echo "Set direct URL from Prisma Console; do not use prisma+postgres:// for this script."
  exit 1
fi

echo "=== Prisma Migrate Status (PROD) ==="
STATUS_OUTPUT=""
STATUS_EXIT=0
set +e
STATUS_OUTPUT="$(npx --prefix config prisma migrate status --config config/prisma.config.ts 2>&1)"
STATUS_EXIT=$?
set -e

echo "$STATUS_OUTPUT"

# Fast path: Prisma CLI succeeded
if [ "$STATUS_EXIT" -eq 0 ]; then
  exit 0
fi

# If Prisma reports unapplied migrations, fail directly (expected strict behavior).
if echo "$STATUS_OUTPUT" | grep -qi "not yet been applied"; then
  exit 1
fi

echo ""
echo "Prisma CLI status failed (engine/connectivity). Running DB-backed fallback check..."

if [ ! -x ".venv/bin/python" ]; then
  echo "FALLBACK FAILED: .venv/bin/python not found"
  exit 1
fi

.venv/bin/python - <<'PY'
import os
import sys
import time
from pathlib import Path

try:
    import psycopg2
except Exception as exc:
    print(f"FALLBACK FAILED: psycopg2 not available ({exc})")
    sys.exit(1)

repo = Path(".")
migrations_dir = repo / "prisma" / "migrations"
if not migrations_dir.exists():
    print("FALLBACK FAILED: prisma/migrations directory missing")
    sys.exit(1)

# Local migration folders with migration.sql (sorted deterministically)
local = sorted(
    p.name
    for p in migrations_dir.iterdir()
    if p.is_dir() and (p / "migration.sql").exists()
)

url = os.getenv("DIRECT_DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
if not url:
    print("FALLBACK FAILED: DIRECT_DATABASE_URL/POSTGRES_URL/DATABASE_URL not set")
    sys.exit(1)

conn = None
last_exc = None
for attempt in range(1, 6):
    try:
        conn = psycopg2.connect(url)
        break
    except Exception as exc:
        last_exc = exc
        print(f"Fallback connect attempt {attempt}/5 failed: {exc}")
        if attempt < 5:
            time.sleep(2)

if conn is None:
    print(f"FALLBACK FAILED: cannot connect to DB after retries ({last_exc})")
    sys.exit(1)

cur = conn.cursor()

# Applied migrations: finished and not rolled back
cur.execute(
    """
    SELECT migration_name
    FROM _prisma_migrations
    WHERE finished_at IS NOT NULL
      AND rolled_back_at IS NULL
    """
)
applied = {row[0] for row in cur.fetchall()}

# Failed/incomplete migrations should block
cur.execute(
    """
    SELECT migration_name
    FROM _prisma_migrations
    WHERE finished_at IS NULL
      AND rolled_back_at IS NULL
    """
)
incomplete = [row[0] for row in cur.fetchall()]

cur.close()
conn.close()

pending = [name for name in local if name not in applied]

if incomplete:
    print("FALLBACK RESULT: FAILED")
    print("Incomplete migrations found in _prisma_migrations:")
    for name in incomplete:
        print(f"  - {name}")
    sys.exit(1)

if pending:
    print("FALLBACK RESULT: FAILED")
    print("Unapplied migrations:")
    for name in pending:
        print(f"  - {name}")
    sys.exit(1)

print("FALLBACK RESULT: PASSED")
print(f"Applied migrations: {len(applied)} | Local migrations: {len(local)}")
sys.exit(0)
PY
