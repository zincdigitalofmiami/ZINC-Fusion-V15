# 🚀 ZINC-FUSION-V15 Migration Quick Start Guide

**Use this guide for rapid execution. See PRODUCTION_READINESS_PLAN.md for full details.**

---

## Pre-Flight Checklist

```bash
# 1. Backup database
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Verify Prisma schema
cd /Volumes/Satechi\ Hub/ZINC-FUSION-V15
npx prisma validate

# 3. Check current state
python3 scripts/validate_db_state.py
```

---

## Phase 1: MLflow Removal (1-2 hours)

```bash
# Stop services
docker compose -f docker/docker-compose.yml down mlflow mlflow-postgres minio

# Remove files
rm docker/Dockerfile.mlflow
rm scripts/start-mlflow.sh
rm scripts/sync_prisma_to_mlflow.py
rm Docs/MLFLOW_SETUP.md
rm mlflow.db
rm -rf mlruns/

# Remove volumes
docker volume rm zinc-fusion-v15_mlflow-postgres-data 2>/dev/null || true
docker volume rm zinc-fusion-v15_mlflow-minio-data 2>/dev/null || true

# Validate
python3 -c "from grafana.grafana_registry import GrafanaRegistry; print('✅ GrafanaRegistry OK')"
```

**Edit docker-compose.yml**: Remove mlflow, mlflow-postgres, minio services

**Edit README.md**: Remove lines 760-779 (MLflow section)

**Success Check**:
```bash
docker ps | grep mlflow  # Should return nothing
grep -r "import mlflow" src/ scripts/  # Should return nothing
```

---

## Phase 2: API Migration (2-4 hours)

**Files to Edit**:

1. `src/fusion/api/server.py`:
   ```python
   # Change:
   raw.epa_rin_prices_1d  → supply.epa_rin_1d
   raw.weather_noaa_1d    → alt.weather_1d
   raw.news_articles_1d   → alt.news_1d
   gold.intel_drops       → features.intel_drops
   ```

2. `src/fusion/pulse/storage.py`:
   ```python
   # Change:
   gold.intel_drops → features.intel_drops
   ```

3. `scripts/generate_core_forecasts.py`:
   ```python
   # Change:
   model.forecast_quantiles → forecasts.forecast_quantiles
   ```

**Test**:
```bash
# Start API
python3 -m uvicorn fusion.api.server:app --reload

# Test endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/zl/latest
```

---

## Phase 3: Ingestion Migration (3-6 hours)

**Frontend Inngest Jobs** (in `frontend/src/inngest/`):

```typescript
// yahoo-eod.ts
raw.market_futures_1d → mkt.futures_1d

// fx-spot-daily.ts
raw.fx_spot_1d → mkt.fx_1d

// cftc-weekly.ts
raw.cftc_cot_1w → pos.cftc_1w

// usda-export-sales-weekly.ts
raw.usda_export_sales_1w → supply.usda_exports_1w

// usda-wasde-monthly.ts
raw.usda_wasde_1m → supply.usda_wasde_1m

// epa-rin-prices-daily.ts
raw.epa_rin_prices_1d → supply.epa_rin_1d

// noaa-weather-daily.ts
raw.weather_noaa_1d → alt.weather_1d

// fred-daily.ts
raw.fred_observations_1d → econ.* (use router)

// barchart-zl-news.ts
raw.news_articles_1d → alt.news_1d
```

**Test**:
```bash
cd frontend
npm run dev
npx inngest-cli dev
```

---

## Phase 4: Training Migration (4-8 hours)

**Files to Edit**:

1. `scripts/preflight_52model.py`:
   ```python
   raw.market_futures_1d → mkt.futures_1d
   raw.fx_spot_1d → mkt.fx_1d
   raw.options_futures_1d → mkt.options_1d
   raw.fred_observations_1d → econ.*
   raw.weather_noaa_1d → alt.weather_1d
   raw.cftc_cot_1w → pos.cftc_1w
   raw.usda_export_sales_1w → supply.usda_exports_1w
   raw.usda_wasde_1m → supply.usda_wasde_1m
   raw.epa_rin_prices_1d → supply.epa_rin_1d
   ```

2. `scripts/audit_core_training_data.py`:
   ```python
   raw.market_futures_1d → mkt.futures_1d
   gold.elite_indicators_1d → features.elite_1d
   raw.fred_observations_1d → econ.*
   ```

3. Feature modules in `src/fusion/features/`:
   - Verify they read from `mkt.*` not `raw.*`
   - Verify they write to `features.*` not `gold.*`

**Test**:
```bash
python3 scripts/preflight_52model.py
python3 scripts/audit_core_training_data.py
python3 src/fusion/core_training/phase3_build_core_matrix.py
```

---

## Phase 5: Validator Migration (2-4 hours)

**Create**: `src/fusion/validators/schema_guard.py`

```python
REQUIRED_SCHEMAS = ['mkt', 'econ', 'pos', 'supply', 'alt', 'features', 'training', 'model']
BANNED_SCHEMAS = ['raw', 'gold', 'silver', 'bronze', 'archive']

def validate_schema_compliance(conn):
    for schema in BANNED_SCHEMAS:
        result = conn.execute(f"""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = '{schema}'
        """).fetchone()
        if result[0] > 0:
            raise SchemaViolationError(f"Banned schema '{schema}' still has tables")
```

**Update**: `src/fusion/validators/freshness_monitor.py`
- Change monitoring from `raw.*` to `mkt.*`, `econ.*`, `alt.*`, `pos.*`, `supply.*`

**Retire**: `src/fusion/validators/anomaly_detection.py` (or rewrite to use `ops.*`)

---

## Phase 6: Final Validation (1-2 hours)

```bash
# Database state
psql $DATABASE_URL -c "SELECT table_schema, COUNT(*) FROM information_schema.tables WHERE table_schema IN ('raw', 'gold', 'silver') GROUP BY table_schema;"
# Expected: 0 rows

# Code state
grep -r "raw\." --include="*.py" --include="*.ts" src/ scripts/ frontend/src/ | grep -v ".pyc" | wc -l
# Expected: 0

grep -r "gold\." --include="*.py" --include="*.ts" src/ scripts/ frontend/src/ | grep -v ".pyc" | wc -l
# Expected: 0

# Prisma validation
npx prisma validate

# Training readiness
python3 scripts/validate_training_tables.py
python3 scripts/preflight_52model.py

# API health
curl http://localhost:8000/health

# Grafana
open http://localhost:3000
```

---

## Rollback Procedure

```bash
# Stop all services
docker compose down
pkill -f uvicorn

# Restore database
psql $DATABASE_URL < backup_YYYYMMDD_HHMMSS.sql

# Revert code
git reset --hard HEAD~N  # N = number of commits to revert

# Restart services
docker compose up -d
python3 -m uvicorn fusion.api.server:app --reload
```

---

## Emergency Contacts

- **Database Issues**: Check `ops.data_quality_metrics`
- **API Issues**: Check logs at `logs/api_server.log`
- **Training Issues**: Check `model.training_runs` for failures
- **Grafana Issues**: Check http://localhost:3000/api/health

---

**Full Plan**: `PRODUCTION_READINESS_PLAN.md`  
**Summary**: `MIGRATION_EXECUTIVE_SUMMARY.md`

