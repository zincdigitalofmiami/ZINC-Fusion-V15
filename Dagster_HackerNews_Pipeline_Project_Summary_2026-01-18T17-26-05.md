[ ] NAME:Current Task List DESCRIPTION:Root task for conversation __NEW_AGENT__
-[ ] NAME:ZINC-FUSION-V15 Production Readiness Migration DESCRIPTION:Complete migration from legacy medallion architecture to institutional schemas, remove MLflow, and prepare for 52-model training pipeline. Timeline: 10-15 days.
--[ ] NAME:Phase 1: MLflow Infrastructure Removal DESCRIPTION:Remove all MLflow dependencies, services, and files. Validate GrafanaRegistry as replacement. Timeline: 1-2 days. Risk: Low.
---[ ] NAME:1.1 Stop MLflow Docker Services DESCRIPTION:Scope: docker/docker-compose.yml
Commands: docker compose -f docker/docker-compose.yml down mlflow mlflow-postgres minio minio-init
Services at lines 19-99
Validation: docker ps | grep mlflow (should return nothing)
---[ ] NAME:1.2 Delete MLflow Files DESCRIPTION:Files to delete:
- docker/Dockerfile.mlflow
- scripts/start-mlflow.sh
- scripts/sync_prisma_to_mlflow.py
- Docs/MLFLOW_SETUP.md
- mlflow.db
- mlruns/ (directory)
Validation: ls docker/Dockerfile.mlflow (should fail)
---[ ] NAME:1.3 Update docker-compose.yml DESCRIPTION:Scope: docker/docker-compose.yml
Remove services: mlflow (lines 19-50), mlflow-postgres (lines 51-70), minio (lines 71-85), minio-init (lines 86-99)
Remove volumes: mlflow-postgres-data, mlflow-minio-data
Validation: grep -c mlflow docker/docker-compose.yml (should return 0)
---[ ] NAME:1.4 Remove MLflow from README DESCRIPTION:Scope: README.md lines 721-783
Remove entire MLflow section
Validation: grep -c MLflow README.md (should return 0 or only historical references)
---[ ] NAME:1.5 Validate GrafanaRegistry Replacement DESCRIPTION:Scope: grafana/grafana_registry.py
Test: python3 -c "from grafana.grafana_registry import GrafanaRegistry; print('OK')"
Verify writes to: model.training_runs, model.model_registry
Acceptance: No import errors, registry functional
---[ ] NAME:1.6 Phase 1 Rollback Checkpoint DESCRIPTION:Create rollback snapshot:
- Document current docker-compose state
- Backup any MLflow data if needed
- Test Grafana dashboards still query Prisma
Validation: curl http://localhost:3000/api/health
--[ ] NAME:Phase 2: Production API Schema Migration DESCRIPTION:Migrate production API endpoints from legacy schemas to institutional schemas. Timeline: 2-3 days. Risk: Medium (production impact).
---[ ] NAME:2.1 [CRITICAL] Fix Forecast Schema Drift DESCRIPTION:GOVERNANCE DECISION: Option A - Align code to Prisma schema

Status: server.py already uses correct schema (lines 605, 609, 619, 639, 643) ✅

Files requiring update:
- scripts/generate_core_forecasts.py (lines 8, 1089, 1230, 1247, 1284, 1293)
- scripts/push_results_to_cloud.py (lines 106, 113)

Schema Mapping:
- model.forecast_quantiles → forecasts.forecast_quantiles

Validation: grep -r 'model\.forecast_quantiles' src/ scripts/ (should return 0)
---[ ] NAME:2.2 Migrate API Server Landing Schema Refs DESCRIPTION:Scope: src/fusion/api/server.py

Schema Mappings:
- raw.epa_rin_prices_1d → supply.epa_rin_1d
- raw.weather_noaa_1d → alt.weather_1d
- raw.news_articles_1d → alt.news_1d
- gold.intel_drops → features.intel_drops

Validation: grep -E 'raw\.|gold\.' src/fusion/api/server.py (should return 0)
---[ ] NAME:2.3 Migrate Pulse Storage Module DESCRIPTION:Scope: src/fusion/pulse/storage.py

Schema Mappings:
- gold.intel_drops → features.intel_drops (INSERT and SELECT)

Note: Table already has ON CONFLICT (as_of_ts, domain, horizon) DO UPDATE SET - idempotency preserved.

Validation: grep 'gold\.' src/fusion/pulse/storage.py (should return 0)
---[ ] NAME:2.4 Test API Endpoints DESCRIPTION:Commands:
- python3 -m uvicorn fusion.api.server:app --reload
- curl http://localhost:8000/health
- curl http://localhost:8000/api/zl/latest
- curl http://localhost:8000/api/forecasts/quantiles

Acceptance: All endpoints return 200 with valid data
---[ ] NAME:2.5 Phase 2 Rollback Checkpoint DESCRIPTION:Pre-phase backup: pg_dump $DATABASE_URL > backup_phase2_$(date +%Y%m%d).sql

Rollback procedure:
1. git stash or git reset on API changes
2. Restart API server

Validation: API returns data from correct schemas
---[ ] NAME:2.6 Extend TABLE_MAP for Missing Aliases DESCRIPTION:TACTICAL: src/fusion/api/db.py has TABLE_MAP (lines 140-150) but is incomplete

Add missing mappings:
```python
TABLE_MAP = {
    # Existing...
    'raw.weather_noaa_1d': '"alt"."weather_1d"',           # ADD
    'raw.news_articles_1d': '"alt"."news_1d"',             # ADD  
    'gold.intel_drops': '"features"."intel_drops"',       # ADD
    'raw.epa_rin_prices_1d': '"supply"."epa_rin_1d"',     # ADD
    'raw.whitehouse_actions_event': '"alt"."legislation_1d"', # ADD (merge)
    'silver.news_scored_1d': '"features"."news_sentiment_1d"', # ADD (new table)
}
```

Note: This is transitional - end goal is zero legacy refs

Validation: API queries work during migration phase
--[ ] NAME:Phase 3: Ingestion Layer Schema Migration DESCRIPTION:Update all Inngest jobs and data collectors to write to institutional schemas. Timeline: 2-3 days. Risk: Medium (data pipeline).
---[ ] NAME:3.1 Migrate Inngest Market Data Jobs DESCRIPTION:Scope: frontend/src/inngest/*.ts (24 job files)

Schema Mappings:
- raw.market_futures_1d → mkt.futures_1d (yahoo-eod.ts)
- raw.market_futures_1h → mkt.futures_1h (yahoo-intraday.ts)
- raw.fx_spot_1d → mkt.fx_1d (fx-spot-daily.ts)
- raw.options_futures_1d → mkt.options_1d (options-daily.ts)

Idempotency: Verify ON CONFLICT clauses exist

Validation: grep -r 'raw\.market' frontend/src/inngest/ (should return 0)
---[ ] NAME:3.2 Migrate Inngest Economic Data Jobs DESCRIPTION:Scope: frontend/src/inngest/fred-*.ts

Schema Mappings (FRED router):
- raw.fred_observations_1d → econ.rates_1d, econ.inflation_1d, econ.labor_1d, econ.activity_1d, econ.vol_indices_1d, econ.commodities_1d, econ.fx_1d, econ.money_1d

Router: src/fusion/ingestion/router.py FRED_SERIES_BUCKETS

Validation: grep -r 'raw\.fred' frontend/src/inngest/ (should return 0)
---[ ] NAME:3.3 Migrate Inngest Positioning Jobs DESCRIPTION:Scope: frontend/src/inngest/cftc-*.ts

Schema Mappings:
- raw.cftc_cot_1w → pos.cftc_1w
- raw.cftc_cits_1w → pos.cftc_cits_1w

Note: scripts/ingest_cits.py also needs update

Validation: grep -r 'raw\.cftc' frontend/src/inngest/ scripts/ (should return 0)
---[ ] NAME:3.4 Migrate Inngest Supply Jobs DESCRIPTION:Scope: frontend/src/inngest/usda-*.ts, epa-*.ts

Schema Mappings:
- raw.usda_wasde_1m → supply.usda_wasde_1m
- raw.usda_export_sales_1w → supply.usda_exports_1w
- raw.epa_rin_prices_1d → supply.epa_rin_1d

Note: scripts/ingest_wasde_backfill.py also needs update

Validation: grep -r 'raw\.usda\|raw\.epa' frontend/src/inngest/ scripts/ (should return 0)
---[ ] NAME:3.5 Migrate Inngest Alternative Data Jobs DESCRIPTION:Scope: frontend/src/inngest/noaa-*.ts, news-*.ts, barchart-zl-news.ts, whitehouse-press.ts

Schema Mappings:
- raw.weather_noaa_1d → alt.weather_1d
- raw.news_articles_1d → alt.news_1d
- raw.whitehouse_actions_event → alt.legislation_1d (with source='WHITEHOUSE')

GOVERNANCE DECISION: Whitehouse actions merge into alt.legislation_1d

Validation: grep -r 'raw\.weather\|raw\.news\|raw\.whitehouse' frontend/src/inngest/ (should return 0)
---[ ] NAME:3.6 Migrate Python Ingestion Scripts DESCRIPTION:Scope: scripts/ingest_*.py (pattern match)

Files confirmed:
- scripts/ingest_yahoo_eod.py (already has ON CONFLICT)
- scripts/ingest_cits.py
- scripts/ingest_wasde_backfill.py
- scripts/ingest_all_downloads.py
- scripts/ingest_barchart_*.py

Validation: grep -r 'raw\.' scripts/ingest_*.py | wc -l (should decrease to 0)
---[ ] NAME:3.7 Define Idempotency Contracts DESCRIPTION:MEDIUM PRIORITY finding: No documented dedupe strategy

For each landing table, define:
- Primary Key: (symbol, event_date, source)
- Dedupe: ON CONFLICT (symbol, event_date, source) DO UPDATE
- row_hash: Optional for change detection

Verify existing ON CONFLICT clauses in:
- scripts/ingest_yahoo_eod.py (confirmed)
- src/fusion/pulse/storage.py (confirmed)
- src/fusion/core_training/phase6_train_core_seq.py (confirmed)

Validation: All landing tables have idempotent inserts
---[ ] NAME:3.8 Phase 3 Rollback Checkpoint DESCRIPTION:Pre-phase: Pause Inngest jobs, take data freshness snapshot

Rollback procedure:
1. Revert frontend/src/inngest/ changes
2. Restore scripts from git
3. Resume jobs

Validation: Data freshness metrics show < 24h staleness
---[ ] NAME:3.9 Complete Inngest Job Inventory DESCRIPTION:MEDIUM PRIORITY finding: Plan lists 8-10 jobs but 25 exist

Full inventory (25 files):

**mkt.* target:**
- yahoo-eod.ts
- fx-spot-daily.ts
- zl-price.ts

**econ.* target:**
- fred-daily.ts
- nyfed-daily.ts

**pos.* target:**
- cftc-weekly.ts

**supply.* target:**
- usda-wasde-monthly.ts
- usda-export-sales-weekly.ts
- epa-rin-prices-daily.ts
- nass-weekly.ts

**alt.* target:**
- whitehouse-press.ts
- barchart-zl-news.ts
- federal-register.ts
- noaa-weather-daily.ts
- openmeteo-weather-daily.ts
- conab-news.ts
- ice-releases.ts
- usda-press.ts
- eia-today.ts

**Requires target review:**
- aei-trade.ts
- cbp-trade.ts
- glide-vegas.ts
- farmdoc-rins.ts

**Non-job files (skip):**
- client.ts
- functions.ts

Validation: All 23 job files mapped to institutional schemas
--[ ] NAME:Phase 4: Training Pipeline Schema Migration DESCRIPTION:Migrate training scripts, feature engineering, and specialist configurations. Timeline: 3-4 days. Risk: High (70 Python files).
---[ ] NAME:4.1 Migrate Preflight Script DESCRIPTION:Scope: scripts/preflight_52model.py
Impact: HEAVY - multiple raw.* references

Schema Mappings:
- raw.market_futures_1d → mkt.futures_1d
- raw.fx_spot_1d → mkt.fx_1d
- raw.options_futures_1d → mkt.options_1d
- raw.fred_observations_1d → econ.* (domain split)
- raw.weather_noaa_1d → alt.weather_1d
- raw.cftc_cot_1w → pos.cftc_1w
- raw.usda_export_sales_1w → supply.usda_exports_1w
- raw.usda_wasde_1m → supply.usda_wasde_1m
- raw.epa_rin_prices_1d → supply.epa_rin_1d

Validation: python3 scripts/preflight_52model.py (should pass)
---[ ] NAME:4.2 Migrate Audit Script DESCRIPTION:Scope: scripts/audit_core_training_data.py

Schema Mappings:
- raw.market_futures_1d → mkt.futures_1d
- gold.elite_indicators_1d → features.elite_1d
- raw.fred_observations_1d → econ.*

Column Note: features.elite_1d uses trade_date (not event_date)

Validation: python3 scripts/audit_core_training_data.py (should pass)
---[ ] NAME:4.3 Create features.news_sentiment_1d DESCRIPTION:GOVERNANCE DECISION: Option B - Create new features.news_sentiment_1d table

PRE-REQ: Task 0.2 must complete first (Prisma model creation)

Files requiring update (silver.news_scored_1d refs):
- scripts/backfill_sentiment_scores.py (5 refs)
- scripts/garbage_cleanup.py (6 refs)
- scripts/batch1_ai_scores.py (2 refs)
- scripts/deberta_relevance_gate.py (4 refs)
- scripts/import_opus_scores.py (4 refs)
- src/fusion/ai_compute/agent_pool.py (lines 406, 476, 545)
- scripts/generate_specialist_features.py (lines 852, 857, 1179, 1706)
- scripts/neural_sentiment_scoring.py (lines 777, 809, 816, 911, 1117)

Schema Mapping:
- silver.news_scored_1d → features.news_sentiment_1d

Validation: grep -r 'silver\.' src/ scripts/ (should return 0)
---[ ] NAME:4.4 Migrate Specialist Feature Generation DESCRIPTION:Scope: scripts/generate_specialist_features.py
Impact: Core training dependency

Verify writes to: training.specialist_{bucket}_1d for all 11 buckets:
crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, trump_effect

Column: Uses as_of_date (verify alignment with Prisma)

Validation: All 11 specialist tables have fresh data
---[ ] NAME:4.5 Migrate Feature Engineering Modules DESCRIPTION:Scope: src/fusion/features/*.py

Files:
- src/fusion/features/elite.py → features.elite_1d
- src/fusion/features/options.py → features.options_1d
- src/fusion/features/weather.py → features.weather_1d

Verify: Read from mkt.* (not raw.*), write to features.*

Column: Output uses trade_date (derived schema)

Validation: python3 -c "from fusion.features.elite import build_elite_features"
---[ ] NAME:4.6 Migrate Core Training Scripts DESCRIPTION:Scope: src/fusion/core_training/*.py, scripts/train_*.py

Files:
- src/fusion/core_training/phase3_build_core_matrix.py
- src/fusion/core_training/phase6_train_core_seq.py (has ON CONFLICT)
- scripts/train_core_oof.py

Verify:
- Reads from features.* tables
- Writes to training.matrix_1d, training.oof_core_1d
- Uses trade_date column

Validation: python3 src/fusion/core_training/phase3_build_core_matrix.py
---[ ] NAME:4.7 Standardize Quantile Column Names DESCRIPTION:LOW PRIORITY finding: Some docs show pred_p30/pred_p50/pred_p70

Confirmed Prisma uses: p30, p50, p70 (no prefix) in:
- training.oof_core_1d
- training.meta_inputs_1d (core_p30, core_p50, core_p70)

File with violation: scripts/generate_synthesis.py:237 uses pred_p50

Standard: OOF tables use p30/p50/p70 (simple, no prefix)

Validation: grep -r 'pred_p' src/ scripts/ (should return 0 or be intentional)
---[ ] NAME:4.8 Validate OOF Table Schema Contract DESCRIPTION:Contract (LOCKED):
- Columns: trade_date, symbol, horizon_days, window_id, cutoff_date, p30, p50, p70, target_value, trained_at, run_hash, matrix_version
- PK: (trade_date, symbol, horizon_days, window_id)
- Quantiles: p30 ≤ p50 ≤ p70 (enforce monotonicity)

Verify 12 OOF tables:
- training.oof_core_1d
- training.oof_{11 specialists}_1d (biofuel, china, crush, energy, fed, fx, palm, substitutes, tariff, trump_effect, volatility)

Note: Specialist OOF tables need to be created if missing

Validation: psql -c "SELECT table_name FROM information_schema.tables WHERE table_schema='training' AND table_name LIKE 'oof_%'"
---[ ] NAME:4.9 Remove Symbol from Table Names DESCRIPTION:MEDIUM PRIORITY finding: Legacy patterns bake symbol into table name

Example violations:
- training.oof_core_zl_1d (should be training.oof_core_1d with symbol column)

Verify Prisma uses symbol column (confirmed in OofCore1d model)

Validation: No table names contain '_zl_' or other symbol prefixes
---[ ] NAME:4.10 Phase 4 Rollback Checkpoint DESCRIPTION:Pre-phase: Take training table snapshots

Rollback procedure:
1. Revert all Python scripts from git
2. Clear corrupted OOF tables if needed
3. Re-run feature generation from mkt.* tables

Validation: training.matrix_1d has ~130 features, preflight passes
---[ ] NAME:4.11 Migrate Whitehouse Actions to alt.legislation_1d DESCRIPTION:GOVERNANCE DECISION: Option A (Modified) - Merge to alt.legislation_1d with source='WHITEHOUSE'

PRE-REQ: Task 0.1 must complete first (add url column to Prisma model)

Files requiring update (10+ files, 20+ refs):
- scripts/scrape_whitehouse_actions.py (lines 181, 212, 246, 312, 333, 370, 384)
- scripts/refresh_trump_effect_features.py (lines 6, 51)
- scripts/generate_specialist_features.py (line 935)
- scripts/comprehensive_data_audit.py (line 235)
- scripts/comprehensive_audit_v2.py (line 230)
- scripts/audit_schema_readonly.py (lines 110, 121)
- scripts/audit_tagging_disaster.py (line 56)
- scripts/run_migration_001.py (lines 273, 276, 277, 280, 292, 331)
- frontend/src/audit_specialists.mjs (line 173)
- frontend/src/audit-freshness.js (line 11)

Schema Mapping:
- raw.whitehouse_actions_event → alt.legislation_1d (with source='WHITEHOUSE')

Validation: grep -r 'raw\.whitehouse' scripts/ src/ frontend/ (should return 0)
--[ ] NAME:Phase 5: Validation & Monitoring Migration DESCRIPTION:Update validators, monitoring, and schema guards to enforce institutional standards. Timeline: 1 day. Risk: Low.
---[ ] NAME:5.1 Canonize Schema List in V2 Rules DESCRIPTION:HIGH PRIORITY finding: SCHEMA_RULES_V2_DRAFT.md lists 8 schemas, missing alt, pos, supply, forecasts

Update Docs/SCHEMA_RULES_V2_DRAFT.md to match Prisma:

Canonical schemas (13 total per Prisma line 9):
- Landing: mkt, econ, alt, pos, supply
- Derived: features, training
- Output: model, forecasts, analytics
- Governance: metadata, ops
- Deprecated: archive (read-only)

Validation: diff Docs/SCHEMA_RULES_V2_DRAFT.md vs Prisma schemas list
---[ ] NAME:5.2 Update AGENTS.md Schema Section DESCRIPTION:Scope: AGENTS.md lines 153-175

Current: Lists 8 schemas (features, econ, mkt, training, model, analytics, metadata, ops)
Needed: Add alt, pos, supply, forecasts

Update 'Allowed Schemas (v2, 8 total)' to '(v2, 12 total)'

Validation: AGENTS.md matches Prisma schema list
---[ ] NAME:5.3 Update Legacy Config Files DESCRIPTION:Scope: src/fusion/config.py, src/fusion/taxonomy.py

Current SCHEMAS list (lines 59-71, 87-99):
- Contains raw, silver, gold, monitoring, specialist, weather, archive

Update to institutional schemas only:
- mkt, econ, alt, pos, supply, features, training, model, forecasts, analytics, metadata, ops

Validation: grep 'raw\|silver\|gold' src/fusion/config.py src/fusion/taxonomy.py (should return 0)
---[ ] NAME:5.4 Update .claude Memory Files DESCRIPTION:Scope: .claude/memory/ZINC_FUSION_KNOWLEDGE_BASE.md, .claude/skills/*/references/*.md

Current: References medallion architecture (raw → silver → gold)
Update: Document institutional schema flow

Validation: grep -r 'raw\.' .claude/ (should return 0 or be historical)
---[ ] NAME:5.5 Implement Schema Guard Validator DESCRIPTION:Create: src/fusion/validators/schema_guard.py

Required functionality:
- REQUIRED_SCHEMAS = ['mkt', 'econ', 'pos', 'supply', 'alt', 'features', 'training', 'model', 'forecasts', 'analytics', 'metadata', 'ops']
- BANNED_SCHEMAS = ['raw', 'gold', 'silver', 'bronze']
- validate_schema_compliance(conn) - fail hard if banned schemas have tables
- Call at API startup via @app.on_event('startup')

Validation: python3 src/fusion/validators/schema_guard.py
---[ ] NAME:5.6 Update Freshness Monitor DESCRIPTION:Scope: src/fusion/validators/freshness_monitor.py

Current: Monitors raw.* tables
Update: Monitor landing schemas (mkt.*, econ.*, alt.*, pos.*, supply.*)

Validation: Freshness metrics show all sources < 24h stale
---[ ] NAME:5.7 Retire or Rewrite Anomaly Detection DESCRIPTION:Scope: src/fusion/validators/anomaly_detection.py

CURRENT ISSUE: Violates append-only landing posture by updating raw.* tables

Options:
- A (Recommended): Write anomaly events to ops.anomaly_events (append-only log)
- B: Retire the script entirely
- C: Add anomaly columns to V2 tables (requires schema approval)

Validation: No UPDATE statements target landing schemas
---[ ] NAME:5.8 Document Time Key Join Contract DESCRIPTION:MEDIUM PRIORITY finding: Landing uses event_date, derived uses trade_date

Add to SCHEMA_RULES_V2_DRAFT.md:

```
## Time Key Join Contract
Landing schemas (mkt/econ/alt/pos/supply): event_date
Derived schemas (features/training): trade_date
Forecast outputs: forecast_date (reference) + target_date (prediction)

Join pattern:
  FROM mkt.futures_1d m
  JOIN features.elite_1d f ON m.event_date = f.trade_date
```

Future: Consider metadata.trading_calendar table for business day mapping

Validation: Time key contract documented
---[ ] NAME:5.9 Phase 5 Rollback Checkpoint DESCRIPTION:Pre-phase: Backup current validator files

Rollback procedure:
1. Revert validator changes
2. Remove schema_guard.py if causing startup failures

Validation: API starts without errors, validators run clean
--[ ] NAME:Phase 6: Final Production Hardening DESCRIPTION:Complete validation, team training, rollback testing, and go-live decision. Timeline: 1-2 days. Risk: Low.
---[ ] NAME:6.1 Final Validation Suite DESCRIPTION:Run complete validation:

# Database state
psql $DATABASE_URL -c "SELECT table_schema, COUNT(*) FROM information_schema.tables WHERE table_schema IN ('raw', 'gold', 'silver') GROUP BY table_schema;"
# Expected: 0 rows

# Code state (must all return 0)
grep -r 'raw\.' --include='*.py' --include='*.ts' src/ scripts/ frontend/src/ | grep -v '.pyc' | wc -l
grep -r 'gold\.' --include='*.py' --include='*.ts' src/ scripts/ frontend/src/ | wc -l
grep -r 'silver\.' --include='*.py' --include='*.ts' src/ scripts/ frontend/src/ | wc -l

# Prisma validation
npx prisma validate

Acceptance: All checks pass
---[ ] NAME:6.2 Training Readiness Validation DESCRIPTION:Run training pipeline checks:

# Preflight
python3 scripts/preflight_52model.py

# Feature generation
python3 -c "from fusion.features.elite import build_elite_features; build_elite_features()"

# Matrix build
python3 src/fusion/core_training/phase3_build_core_matrix.py

# Validate specialist tables (11 buckets)
python3 scripts/validate_training_tables.py

Acceptance:
- Preflight passes for all 11 specialists
- training.matrix_1d contains ~130 features
- OOF tables follow p30/p50/p70 contract
---[ ] NAME:6.3 API Health Check DESCRIPTION:Commands:
curl http://localhost:8000/health
curl http://localhost:8000/api/zl/latest
curl http://localhost:8000/api/forecasts/quantiles
curl http://localhost:8000/api/specialists/status

Acceptance: All endpoints return 200 with valid JSON
---[ ] NAME:6.4 Grafana Dashboard Validation DESCRIPTION:Commands:
curl http://localhost:3000/api/health

Manual checks:
- Data Freshness dashboard shows all sources
- Training Progress dashboard shows recent runs
- Model Performance dashboard loads
- No broken queries

Acceptance: All dashboards functional, no Prisma query errors
---[ ] NAME:6.5 Test Rollback Procedure DESCRIPTION:Execute dry-run rollback:

1. Take fresh backup: pg_dump $DATABASE_URL > backup_final_$(date +%Y%m%d).sql
2. Document rollback steps:
   - git reset --hard HEAD~N (number of commits)
   - psql $DATABASE_URL < backup_YYYYMMDD.sql
   - Restart services
3. Verify backup restores cleanly (on test DB)

Acceptance: Rollback procedure tested and documented
---[ ] NAME:6.6 Update Documentation DESCRIPTION:Update:
- README.md: Remove any remaining legacy references
- PRODUCTION_READINESS_PLAN.md: Mark phases complete
- MIGRATION_EXECUTIVE_SUMMARY.md: Update status
- Docs/SCHEMA_RULES_V2_DRAFT.md → Docs/SCHEMA_RULES_V2.md (remove draft)

Validation: All docs reflect current institutional architecture
---[ ] NAME:6.7 Team Training Session DESCRIPTION:Topics to cover:
1. New schema architecture (landing vs derived vs output)
2. Prisma as single source of truth
3. GrafanaRegistry usage for training tracking
4. Time key join contract (event_date vs trade_date)
5. Idempotency patterns for ingestion
6. Rollback procedures

Deliverables: Training deck, Q&A session
---[ ] NAME:6.8 Go/No-Go Decision DESCRIPTION:Checklist:
✅ Zero MLflow dependencies
✅ Zero raw/gold/silver references in code
✅ All ingestion writes to institutional schemas
✅ Training matrices build from features.*
✅ OOF predictions in standardized format
✅ Grafana monitoring operational
✅ Rollback tested
✅ Team trained

Decision: Proceed to production or identify blockers
--[ ] NAME:Phase 0: Pre-Migration Prisma Schema Updates DESCRIPTION:BLOCKING: Must complete before Phase 2-4 code migrations

Required Prisma schema changes:
1. Add url column to AltLegislation1d
2. Create FeaturesNewsSentiment1d model

Timeline: 1 day
Risk: Medium (schema changes require migration)
---[ ] NAME:0.1 Add url Column to AltLegislation1d DESCRIPTION:BLOCKER for Task 4.11 (Whitehouse migration)

Add to prisma/schema.prisma in AltLegislation1d model:

```prisma
model AltLegislation1d {
  // ... existing fields ...
  url             String?   @db.Text  // ADD THIS COLUMN
  // ...
}
```

Commands:
npx prisma db push --accept-data-loss  # OR
npx prisma migrate dev --name add_url_to_legislation

Validation: npx prisma validate
---[ ] NAME:0.2 Create FeaturesNewsSentiment1d Model DESCRIPTION:BLOCKER for Task 4.3 (News sentiment migration)

Add to prisma/schema.prisma:

```prisma
model FeaturesNewsSentiment1d {
  id              Int       @id @default(autoincrement())
  rawId           Int       @map("raw_id")
  tradeDate       DateTime  @map("trade_date") @db.Date
  sentimentScore  Float?    @map("sentiment_score")
  zlSentiment     Float?    @map("zl_sentiment")
  canonicalBucket String?   @map("canonical_bucket") @db.VarChar(50)
  isTrumpRelated  Boolean?  @default(false) @map("is_trump_related")
  relevanceScore  Float?    @map("relevance_score")
  specialistTags  String[]  @map("specialist_tags")
  ingestedAt      DateTime? @default(now()) @map("ingested_at") @db.Timestamptz(6)

  @@unique([rawId])
  @@index([tradeDate], map: "idx_news_sentiment_date")
  @@index([canonicalBucket], map: "idx_news_sentiment_bucket")
  @@map("news_sentiment_1d")
  @@schema("features")
}
```

Commands:
npx prisma db push  # OR
npx prisma migrate dev --name create_news_sentiment

Validation: npx prisma validate
---[ ] NAME:0.3 Run Prisma Generate DESCRIPTION:After schema changes, regenerate Prisma client:

Commands:
npx prisma generate

Validation:
- TypeScript types updated
- No import errors in frontend/src/

Dependencies: 0.1 and 0.2 must complete first
---[ ] NAME:0.4 Phase 0 Rollback Checkpoint DESCRIPTION:Pre-phase: Take full database backup

Commands:
pg_dump $DATABASE_URL > backup_phase0_$(date +%Y%m%d).sql

Rollback procedure:
1. psql $DATABASE_URL < backup_phase0_YYYYMMDD.sql
2. git checkout prisma/schema.prisma
3. npx prisma generate

Validation: Backup file exists and is > 1MB