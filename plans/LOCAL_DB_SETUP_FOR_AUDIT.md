# Local Database Setup for Codex Desktop Audit

**Created:** 2026-03-05  
**Author:** Architect Mode  
**Purpose:** Enable Codex Desktop to perform local forensic audits with V15 schema

---

## Execution Checkpoint (2026-03-05, America/Chicago)

### Where We Are

- Active branch in this workspace: `recovery/forensic-20260305-ui` (still heavily dirty; model artifacts + broad uncommitted changes remain).
- Clean promotion branch prepared and pushed from separate worktree:
  - `origin/integration/recovery-20260305-safe`
  - PR URL: `https://github.com/zincdigitalofmiami/ZINC-Fusion-V15/pull/new/integration/recovery-20260305-safe`

### What Has Been Done

1. Implemented DB identity lock + guardrails:
   - `scripts/db_identity_guard.py`
   - `scripts/sync_cloud_to_local_db.py`
   - `scripts/backfill_model_runs_event.py`
   - `scripts/check_local_v15_parity.sql`
   - `.env.local.audit.example`
2. Added guard targets and gates:
   - `Makefile` (`db-guard-cloud`, `db-guard-local`, `db-guard-shadow`, `db-parity-local`)
   - `scripts/verify.sh` cloud DB guard gate
3. Enforced runtime DB identity checks:
   - frontend: `frontend/src/lib/db.ts`
   - python: `src/fusion/db/connection.py`
4. Applied schema-contract/provenance fixes:
   - added Prisma ingest models + migration (`20260305093000_add_ingest_table_contracts`)
   - removed runtime DDL from Inngest ingest jobs (BLS/China/FAS/Panama)
   - backfilled `training.model_runs_event` from `training.oof_core_1d` (local)
5. Local DB identity now explicit and verified:
   - `zinc_fusion_v15_local` (runtime)
   - `zinc_fusion_v15_shadow` (shadow)
   - all DB guard modes pass
6. Cloud-to-local mirror for audit tables completed with row-count parity.

### What Is Left

1. Open/drive PR from `integration/recovery-20260305-safe` into `main`.
2. Run authenticated API smoke tests on deployed preview/prod routes (current unauthenticated checks return `401`).
3. Final visual acceptance pass on dashboard:
   - white crosshair present
   - right-side 4 Target Zone labels present
   - pulsing alert absent
   - mobile layout stable
4. Decide whether to port skipped high-overlap commits (`119826ee`, `ecc55603`) in a follow-up PR.

---

## Current State Analysis

### Production Database

- **Host:** `db.prisma.io:5432` (Prisma Cloud Postgres)
- **Database:** `postgres`
- **Schemas:** 12 (mkt, econ, alt, pos, supply, features, training, model, forecasts, analytics, ops, vegas)
- **Access:** Via `DATABASE_URL` in `.env`
- **Status:** Live production, all V15 tables present

### Local Postgres (localhost:5432)

- **Databases Found:** `fusion`, `postgres`, `rabid_raccoon`, `zinc_fusion_shadow`
- **Problem:** None have current V15 schema
- **`fusion` DB:** Old layout with deprecated schemas (raw/archive/reference) and outdated training.\* tables
- **Status:** NOT suitable for V15 audit work

### Data Sync Tool

- **Script:** [`scripts/sync_cloud_to_local.py`](scripts/sync_cloud_to_local.py)
- **Purpose:** Syncs cloud data to local **parquet files** for training (not to Postgres)
- **Output:** `data/training_cache/{schema}/{table}.parquet`
- **Limitation:** Does NOT create or populate a local Postgres database

---

## What Codex Needs

### Critical Tables for Audit

1. **`forecasts.production_1d`** — Dashboard forecast outputs with Monte Carlo probability
2. **`training.matrix_1d`** — Feature matrix with ~213+ features for core model training
3. **`training.specialist_signals_1d`** — 11 specialist buckets x 3 signals (33 columns)
4. **`training.oof_core_1d`** — Out-of-fold predictions from core models (`predicted_price` per horizon)

### Schema Requirements

- All 12 schemas from [`prisma/schema.prisma`](prisma/schema.prisma)
- Current Prisma migration state (37 migrations applied)
- Correct data types, indexes, constraints

### Environment Variables for Dual Routing

```bash
export LOCAL_DATABASE_URL='postgresql://<user>:<pass>@localhost:5432/<db>'
export DB_ROUTING_MODE=dual
export DIRECT_DATABASE_URL="$LOCAL_DATABASE_URL"
export POSTGRES_URL="$LOCAL_DATABASE_URL"
export DATABASE_URL="$LOCAL_DATABASE_URL"
export SHADOW_DATABASE_URL='postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_shadow'
export LOCAL_DB_EXPECTED_NAME='zinc_fusion_v15_local'
export EXPECTED_DB_NAME='zinc_fusion_v15_local'
```

---

## Recommended Approach: Fresh Local Mirror DB

### Strategy Overview

1. **Create new local runtime database** (`zinc_fusion_v15_local`) — clean slate, no legacy schema conflicts
2. **Create local shadow database** (`zinc_fusion_v15_shadow`) — Prisma shadow only
3. **Apply V15 schema** using Prisma migrations — ensures exact schema parity with cloud
4. **Selectively sync critical tables** from cloud — only tables Codex needs for audit
5. **Configure dual routing** environment variables
6. **Verify schema parity** between local and cloud

### Why This Approach?

- ✅ **Clean separation** — Doesn't interfere with existing local databases
- ✅ **Schema accuracy** — Prisma migrations guarantee V15 schema correctness
- ✅ **Selective sync** — Only sync what's needed (faster, smaller footprint)
- ✅ **Dual routing** — Can compare local vs cloud in same session
- ✅ **Repeatable** — Can be dropped and recreated as needed

---

## Implementation Plan

### Phase 1: Local Database Creation

**1.1 Create New Database**

```bash
# Connect to local Postgres
psql -h localhost -p 5432 -U <your_postgres_user> postgres

# Create new database
CREATE DATABASE zinc_fusion_v15_local;
CREATE DATABASE zinc_fusion_v15_shadow;

# Exit psql
\q
```

**1.2 Verify Database Exists**

```bash
psql -h localhost -p 5432 -U <your_postgres_user> -l | grep zinc_fusion_v15_local
psql -h localhost -p 5432 -U <your_postgres_user> -l | grep zinc_fusion_v15_shadow
```

---

### Phase 2: Schema Setup with Prisma

**2.1 Create Temporary Environment File**

```bash
# Save current DATABASE_URL
cp .env .env.cloud.backup

# Create local-only env file for schema setup
cat > .env.local.db <<EOF
# Temporary local database URL for schema setup
DATABASE_URL="postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_local"
POSTGRES_URL="postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_local"
DIRECT_DATABASE_URL="postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_local"
SHADOW_DATABASE_URL="postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_shadow"
LOCAL_DB_EXPECTED_NAME="zinc_fusion_v15_local"
EXPECTED_DB_NAME="zinc_fusion_v15_local"
EOF
```

**2.2 Apply V15 Schema Using Prisma**

```bash
# Load local DB env vars
set -a
source .env.local.db
set +a

# Option A: Apply all migrations (recommended)
npx --prefix config prisma migrate deploy --schema prisma/schema.prisma

# Option B: Push schema without migration history (faster, but loses migration tracking)
npx --prefix config prisma db push --schema prisma/schema.prisma --accept-data-loss
```

**2.3 Verify Schema Creation**

```bash
# Check that all 12 schemas were created
psql -h localhost -p 5432 -U <user> -d zinc_fusion_v15_local -c "\dn"

# Expected output: mkt, econ, alt, pos, supply, features, training, model, forecasts, analytics, ops, vegas
```

**2.4 Restore Cloud Environment**

```bash
# Restore original cloud DATABASE_URL
cp .env.cloud.backup .env
```

---

### Phase 3: Selective Data Sync

**3.1 Local Data Sync Script**

Use script: [`scripts/sync_cloud_to_local_db.py`](scripts/sync_cloud_to_local_db.py)

```python
#!/usr/bin/env python3
"""
Sync critical tables from Prisma Cloud to local Postgres for audit work.
Usage: python scripts/sync_cloud_to_local_db.py
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

# Tables to sync for audit (only critical tables)
AUDIT_TABLES = [
    "forecasts.production_1d",
    "training.matrix_1d",
    "training.specialist_signals_1d",
    "training.oof_core_1d",
]

def get_connection(url):
    """Get Postgres connection from URL."""
    return psycopg2.connect(url)

def sync_table(source_conn, dest_conn, table_name):
    """Copy table data from source to destination."""
    schema, table = table_name.split(".")

    print(f"\n📦 Syncing {table_name}...")

    # Get row count from source
    with source_conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        source_count = cur.fetchone()[0]
        print(f"  Source rows: {source_count:,}")

    # Copy data using COPY command (fastest method)
    with source_conn.cursor() as source_cur:
        with dest_conn.cursor() as dest_cur:
            # Truncate destination table first
            dest_cur.execute(f'TRUNCATE TABLE "{schema}"."{table}" CASCADE')

            # Stream copy from source to destination
            copy_sql = f'COPY "{schema}"."{table}" TO STDOUT WITH (FORMAT CSV, HEADER)'
            with source_cur.copy(copy_sql) as copy_out:
                dest_cur.copy_expert(
                    f'COPY "{schema}"."{table}" FROM STDIN WITH (FORMAT CSV, HEADER)',
                    copy_out
                )

    dest_conn.commit()

    # Verify destination count
    with dest_conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        dest_count = cur.fetchone()[0]
        print(f"  ✅ Synced {dest_count:,} rows")

    return source_count == dest_count

def main():
    load_dotenv()

    # Cloud source
    cloud_url = os.getenv("DATABASE_URL")  # Prisma Cloud
    if not cloud_url or "db.prisma.io" not in cloud_url:
        print("ERROR: DATABASE_URL must point to Prisma Cloud")
        sys.exit(1)

    # Local destination
    local_url = os.getenv("LOCAL_DATABASE_URL")
    if not local_url:
        print("ERROR: LOCAL_DATABASE_URL not set")
        print("Example: export LOCAL_DATABASE_URL='postgresql://user:pass@localhost:5432/zinc_fusion_v15_local'")
        sys.exit(1)

    print("="*60)
    print("ZINC-FUSION-V15: Cloud → Local DB Sync (Audit Tables)")
    print("="*60)
    print(f"Source: {cloud_url.split('@')[1].split('/')[0]}")  # Hide credentials
    print(f"Destination: {local_url.split('@')[1]}")
    print(f"Tables: {len(AUDIT_TABLES)}")

    # Connect
    source_conn = get_connection(cloud_url)
    dest_conn = get_connection(local_url)

    # Sync each table
    results = []
    for table in AUDIT_TABLES:
        try:
            success = sync_table(source_conn, dest_conn, table)
            results.append((table, "✅" if success else "⚠️"))
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results.append((table, "❌"))

    source_conn.close()
    dest_conn.close()

    # Summary
    print("\n" + "="*60)
    print("SYNC SUMMARY")
    print("="*60)
    for table, status in results:
        print(f"{status} {table}")

if __name__ == "__main__":
    main()
```

**3.2 Run Sync**

```bash
# Set environment variables
export LOCAL_DATABASE_URL='postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_local'
export SHADOW_DATABASE_URL='postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_shadow'

# Run sync script
python scripts/sync_cloud_to_local_db.py
```

**3.3 Guardrail checks**

```bash
make db-guard-cloud
make db-guard-local
make db-guard-shadow
make db-parity-local
```

**Expected Output:**

```
📦 Syncing forecasts.production_1d...
  Source rows: XXX
  ✅ Synced XXX rows

📦 Syncing training.matrix_1d...
  Source rows: XXX
  ✅ Synced XXX rows

📦 Syncing training.specialist_signals_1d...
  Source rows: XXX
  ✅ Synced XXX rows

📦 Syncing training.oof_core_1d...
  Source rows: XXX
  ✅ Synced XXX rows
```

---

### Phase 4: Environment Configuration for Dual Routing

**4.1 Create Local Audit Environment File**

Create `.env.local.audit`:

```bash
# ============================================================================
# Local Database Configuration for Codex Desktop Audit
# ============================================================================

# Primary local database URL (overrides cloud)
LOCAL_DATABASE_URL="postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_local"

# Dual routing mode
DB_ROUTING_MODE=dual

# All standard aliases point to local
DIRECT_DATABASE_URL="postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_local"
POSTGRES_URL="postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_local"
DATABASE_URL="postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_local"

# Cloud database URL for comparison (read-only reference)
CLOUD_DATABASE_URL="postgres://d687a7ec267e124a21607a1e5dd9a89d60c9a122d219e499e32f3eee42a858c0:sk_NLg8ZV3VJ61FPM0F_QHMe@db.prisma.io:5432/postgres?sslmode=require&gssencmode=disable"
```

**4.2 Activate Local Audit Environment**

```bash
# For single session
set -a
source .env.local.audit
set +a

# Verify
echo $DATABASE_URL | grep localhost# Should return matching line
```

**4.3 Codex Desktop Session Startup**

```bash
# In Codex Desktop session, set env vars as requested:
export LOCAL_DATABASE_URL='postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_local'
export DB_ROUTING_MODE=dual
export DIRECT_DATABASE_URL="$LOCAL_DATABASE_URL"
export POSTGRES_URL="$LOCAL_DATABASE_URL"
export DATABASE_URL="$LOCAL_DATABASE_URL"

# Verify connection
psql $DATABASE_URL -c "\dn"  # Should show 12 schemas
psql $DATABASE_URL -c "SELECT COUNT(*) FROM forecasts.production_1d"
```

---

### Phase 5: Verification & Drift Detection

**5.1 Schema Parity Check**

```sql
-- In local DB
SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname IN ('forecasts', 'training', 'model', 'analytics')
ORDER BY schemaname, tablename;

-- Compare with cloud (same query)
```

**5.2 Critical Table Health Check**

```sql
-- Local DB health check
SELECT
    'forecasts.production_1d' AS table_name,
    COUNT(*) AS row_count,
    MAX(forecast_date) AS max_date,
    MIN(forecast_date) AS min_date
FROM forecasts.production_1d
UNION ALL
SELECT
    'training.matrix_1d',
    COUNT(*),
    MAX(trade_date),
    MIN(trade_date)
FROM training.matrix_1d
UNION ALL
SELECT
    'training.specialist_signals_1d',
    COUNT(*),
    MAX(as_of_date),
    MIN(as_of_date)
FROM training.specialist_signals_1d
UNION ALL
SELECT
    'training.oof_core_1d',
    COUNT(*),
    MAX(trade_date),
    MIN(trade_date)
FROM training.oof_core_1d;
```

**5.3 Cloud vs Local Drift Report**

```bash
# Create drift detection script for Codex
cat > scripts/check_local_cloud_drift.sql <<'EOF'
-- Run this on LOCAL DB first, then CLOUD DB, compare results
SELECT
    schemaname || '.' || tablename AS full_table_name,
    (SELECT COUNT(*) FROM "{schemaname}"."{tablename}") AS row_count,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size
FROM pg_tables
WHERE schemaname IN ('forecasts', 'training', 'model', 'analytics', 'mkt', 'econ')
ORDER BY schemaname, tablename;
EOF

# Run on local
psql $LOCAL_DATABASE_URL -f scripts/check_local_cloud_drift.sql > /tmp/local_schema.txt

# Run on cloud (switch env)
psql $CLOUD_DATABASE_URL -f scripts/check_local_cloud_drift.sql > /tmp/cloud_schema.txt

# Diff
diff /tmp/local_schema.txt /tmp/cloud_schema.txt
```

---

## Troubleshooting

### Issue: Prisma migrations fail on empty database

**Solution:** Use `prisma db push` instead of `migrate deploy` for initial schema setup

### Issue: psycopg2 COPY command fails

**Solution:** Use `pg_dump` / `pg_restore` approach instead:

```bash
# Dump specific table from cloud
PGPASSWORD=<cloud_pass> pg_dump -h db.prisma.io -U <cloud_user> -d postgres \
  -t forecasts.production_1d --data-only --column-inserts \
  > /tmp/production_1d.sql

# Restore to local
psql -h localhost -U <local_user> -d zinc_fusion_v15_local \
  -f /tmp/production_1d.sql
```

### Issue: Local Postgres user permissions

**Solution:** Grant schema creation privileges:

```sql
-- As superuser
ALTER USER <your_user> WITH CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE zinc_fusion_v15_local TO <your_user>;
```

### Issue: Connection refused on localhost:5432

**Solution:** Check if Postgres is running:

```bash
# macOS
brew services list | grep postgresql

# Start if not running
brew services start postgresql@14  # or your version
```

---

## Cleanup & Maintenance

### Drop Local Database (when audit complete)

```bash
psql -h localhost -p 5432 -U <user> postgres -c "DROP DATABASE zinc_fusion_v15_local;"
```

### Re-sync After Cloud Updates

```bash
# Just re-run the sync script
export LOCAL_DATABASE_URL='postgresql://<user>:<pass>@localhost:5432/zinc_fusion_v15_local'
python scripts/sync_cloud_to_local_db.py
```

### Switch Back to Cloud Database

```bash
# Unset local env vars
unset LOCAL_DATABASE_URL DB_ROUTING_MODE

# Reload cloud env
set -a
source .env
set +a
```

---

## Security Considerations

1. **`.env.local.audit` is gitignored** — Contains sensitive credentials
2. **Local database has NO public access** — Localhost only
3. **Cloud credentials preserved** — Original `.env` backed up before any changes
4. **Read-only cloud access** — Local sync does NOT write back to cloud

---

## Summary for Codex Desktop

**Immediate Next Steps:**

1. Determine local Postgres user/password (check `whoami` and local pg_hba.conf)
2. Create `zinc_fusion_v15_local` database
3. Apply V15 schema using Prisma migrations
4. Run selective sync script for 4 critical tables
5. Set environment variables as requested
6. Run forensic checks against local DB

**Expected State After Setup:**

- Fresh local database with V15 schema (12 schemas, all tables defined)
- 4 critical tables populated with latest cloud data
- Environment configured for dual routing
- Ability to run same forensic queries against local and cloud for drift detection

**Time Estimate:**

- Schema setup: ~5 minutes
- Data sync: ~2-5 minutes (depending on table sizes)
- Verification: ~2 minutes
- **Total: ~10-15 minutes**

---

**References:**

- Prisma schema: [`prisma/schema.prisma`](prisma/schema.prisma)
- Cloud sync script (parquet): [`scripts/sync_cloud_to_local.py`](scripts/sync_cloud_to_local.py)
- Prisma migration history: `prisma/migrations/` (37 migrations)
- Audit report (cloud data): [`Docs/audit/pre_rebuild_forecast_audit_2026_03_04.md`](Docs/audit/pre_rebuild_forecast_audit_2026_03_04.md)
