#!/usr/bin/env bash
# Check Prisma migration status against the resolved DB target.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

source scripts/load_db_env.sh
load_db_env

if [ -z "${DATABASE_URL:-}" ]; then
  echo "FALLBACK FAILED: set DATABASE_URL in env, .env.local, or .env"
  exit 1
fi

ACTIVE_DB_URL="${DATABASE_URL}"
ACTIVE_DB_SOURCE="DATABASE_URL"

if printf "%s" "${ACTIVE_DB_URL}" | grep -q '^prisma+postgres://'; then
  echo "FALLBACK FAILED: DATABASE_URL must be direct postgres:// for migrate/status."
  echo "Set direct URL from Prisma Console; do not use prisma+postgres:// for this script."
  exit 1
fi

export ACTIVE_DB_URL
TARGET_INFO="$(
  python3 - <<'PY'
import os
from urllib.parse import urlparse

url = os.getenv("ACTIVE_DB_URL", "")
parsed = urlparse(url)
host = (parsed.hostname or "").lower()
port = parsed.port or 5432
database = (parsed.path or "").lstrip("/") or "(unknown)"
local_hosts = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}
scope = "local" if host in local_hosts else "cloud"
print(f"{host}|{port}|{database}|{scope}")
PY
)"
IFS='|' read -r TARGET_HOST TARGET_PORT TARGET_DB TARGET_SCOPE <<< "${TARGET_INFO}"

echo "Resolved DB target: ${TARGET_HOST}:${TARGET_PORT}/${TARGET_DB} (${TARGET_SCOPE}, source=${ACTIVE_DB_SOURCE})"

REQUIRE_TARGET="${PRISMA_STATUS_REQUIRE_TARGET:-any}"
case "${REQUIRE_TARGET}" in
  ""|"any")
    ;;
  "local"|"cloud")
    if [ "${TARGET_SCOPE}" != "${REQUIRE_TARGET}" ]; then
      echo "FALLBACK FAILED: PRISMA_STATUS_REQUIRE_TARGET=${REQUIRE_TARGET} but resolved target is ${TARGET_SCOPE}"
      exit 1
    fi
    ;;
  *)
    echo "FALLBACK FAILED: PRISMA_STATUS_REQUIRE_TARGET must be one of: any, local, cloud"
    exit 1
    ;;
esac

TARGET_SCOPE_UPPER="$(printf '%s' "${TARGET_SCOPE}" | tr '[:lower:]' '[:upper:]')"
echo "=== Prisma Migrate Status (${TARGET_SCOPE_UPPER}) ==="

if [ "${TARGET_SCOPE}" = "local" ]; then
  TOXIC_LOCAL_REPORT="$(
    psql "${ACTIVE_DB_URL}" -X -q -A -t -F '|' -c "
      WITH required_tables(schema_name, table_name) AS (
        VALUES
          ('analytics', 'price_1d'),
          ('analytics', 'price_1m'),
          ('analytics', 'latest_price'),
          ('mkt', 'futures_1d')
      ),
      present_tables AS (
        SELECT rt.schema_name, rt.table_name
        FROM required_tables rt
        JOIN information_schema.tables t
          ON t.table_schema = rt.schema_name
         AND t.table_name = rt.table_name
      ),
      duplicate_migration_names AS (
        SELECT migration_name
        FROM _prisma_migrations
        GROUP BY migration_name
        HAVING COUNT(*) > 1
      )
      SELECT
        (SELECT COUNT(*) FROM required_tables),
        (SELECT COUNT(*) FROM present_tables),
        (
          SELECT COUNT(*)
          FROM _prisma_migrations
          WHERE finished_at IS NULL
            AND rolled_back_at IS NULL
        ),
        (
          SELECT COUNT(*)
          FROM _prisma_migrations
          WHERE rolled_back_at IS NOT NULL
        ),
        (
          SELECT COUNT(*)
          FROM _prisma_migrations
          WHERE migration_name IN (SELECT migration_name FROM duplicate_migration_names)
        );
    " 2>/dev/null || true
  )"

  if [ -n "${TOXIC_LOCAL_REPORT}" ]; then
    IFS='|' read -r REQUIRED_TABLE_COUNT PRESENT_TABLE_COUNT UNFINISHED_COUNT ROLLED_BACK_COUNT DUPLICATE_NAME_ROWS <<< "${TOXIC_LOCAL_REPORT}"
    MISSING_TABLE_COUNT=$((REQUIRED_TABLE_COUNT - PRESENT_TABLE_COUNT))

    if [ "${MISSING_TABLE_COUNT}" -gt 0 ] || [ "${UNFINISHED_COUNT}" -gt 0 ] || [ "${ROLLED_BACK_COUNT}" -gt 0 ] || [ "${DUPLICATE_NAME_ROWS}" -gt 0 ]; then
      echo "TOXIC LOCAL DB BLOCKED: local database is off-contract for migration safety."
      echo "  Required serving tables missing: ${MISSING_TABLE_COUNT}"
      echo "  Unfinished migration rows: ${UNFINISHED_COUNT}"
      echo "  Rolled-back migration rows: ${ROLLED_BACK_COUNT}"
      echo "  Duplicate-named migration rows: ${DUPLICATE_NAME_ROWS}"
      echo "Local fix path: rebuild or re-sync local from a trusted source before any migration work."
      exit 1
    fi
  fi
fi

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

url = os.getenv("DATABASE_URL")
if not url:
    print("FALLBACK FAILED: DATABASE_URL not set")
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
