NOTE: Production is the dashboard/frontend, not the repo root.
# ZINC-Fusion Grafana Configuration Guide

## Overview

This document covers the Grafana setup for ZINC-Fusion-V15, including both local development and Grafana Cloud deployment.

---

## Quick Start: Full Monitoring Stack

The complete monitoring stack includes:
1. **Grafana Alloy** - Collects macOS metrics and ZINC-Fusion training logs
2. **Grafana Cloud Prometheus** - Stores system metrics
3. **Grafana Cloud Loki** - Stores logs for correlation
4. **PostgreSQL Datasource** - ML metrics from Prisma database

### Start Alloy (if not running)
```bash
alloy run /opt/homebrew/etc/alloy/config.alloy &
```

### Verify Alloy is Working
```bash
# Check if running
pgrep -fl alloy

# Check metrics endpoint
curl -s http://127.0.0.1:12345/metrics | grep samples
```

---

## Database Schema Reference

### Tables Used by Dashboards

| Table | Purpose | Status |
|-------|---------|--------|
| `model.model_registry` | Production model registry (AutoML models) | Active |
| `training.model_runs` | Training experiments with human-readable names | Active |
| `training.oof_core_zl_1d` | OOF predictions for core ZL model | Active |
| `ops.data_quality_metrics` | Data source freshness monitoring | Active |
| `ops.training_runs` | Detailed training run metadata | Active |

### Key Views

| View | Purpose |
|------|---------|
| `model.v_champions` | Current champion models by horizon |
| `model.v_data_freshness` | Data source health summary |
| `model.v_recent_runs` | Recent training runs with metrics |
| `model.v_mase_history` | MASE score trends over time |

---

## Grafana Cloud Setup

### Step 1: Create PostgreSQL Data Source

1. Go to **Configuration > Data Sources > Add data source**
2. Select **PostgreSQL**
3. Configure connection:

```
Name: ZINC-Fusion-Prisma
Host: db.prisma.io:5432
Database: postgres
User: d687a7ec267e124a21607a1e5dd9a89d60c9a122d219e499e32f3eee42a858c0
Password: [from .env POSTGRES_PASSWORD]
SSL Mode: require
Version: 17
```

**Important Settings:**
- TLS/SSL Mode: `require`
- Max open connections: 5 (Prisma Postgres has connection limits)
- Max idle connections: 2
- Connection max lifetime: 14400

### Step 2: Import Dashboards

Three dashboard JSON files are available in `grafana/dashboards/`:

1. **zinc-fusion-unified.json** - Recommended primary dashboard
   - System overview stats
   - Training experiments table
   - OOF performance analysis
   - Data freshness monitoring
   - Model registry

2. **zinc-fusion-training-registry.json** - Training-focused dashboard
   - Training runs with win/fail status
   - MAE by model and horizon
   - OOF performance by validation window

3. **zinc-fusion-model-registry.json** - Model registry focused
   - Specialist MASE scores
   - Data freshness table
   - Recent training runs

To import:
1. Go to **Dashboards > Import**
2. Upload the JSON file or paste content
3. Select the PostgreSQL data source you created

---

## Available Dashboards

### ZINC-Fusion Unified Dashboard
**UID:** `zinc-fusion-unified`

This is the primary dashboard combining:
- **System Overview Row**: Model counts, stale sources, training wins/fails
- **Training Experiments Row**: Table of all training runs with MAE, outcome, notes
- **OOF Performance Row**: Validation window analysis + error time series
- **Data Freshness Row**: Source health table + freshness distribution
- **Model Registry Row**: Production models from `model.model_registry`

### Key Metrics to Monitor

1. **Stale Data Sources** - Alert if > 0 (data ingestion issues)
2. **Training Wins vs Fails** - Track model development progress
3. **MAE Thresholds**:
   - Green: < 0.08 (good)
   - Yellow: 0.08 - 0.15 (acceptable)
   - Red: > 0.15 (needs improvement)

---

## Cloud Dashboard Cleanup

You mentioned these existing Cloud dashboards:
- Alert Groups Insights
- Incident Insights
- Live Training Monitor
- Model Performance - Core & Specialist Models
- PostgreSQL Analytics Dashboard
- Project Crystal Ball - Oil Market Forecasting
- Training Pipeline - Data Quality & Troubleshooting

### Recommendations:

**KEEP:**
- **PostgreSQL Analytics Dashboard** - If using Grafana's Postgres integration plugin, useful for DB monitoring
- **Live Training Monitor** - If it queries `ops.training_runs`, keep for real-time monitoring
- **Training Pipeline - Data Quality & Troubleshooting** - Useful if queries `ops.data_quality_metrics`

**REVIEW:**
- **Model Performance - Core & Specialist Models** - Check if queries correct tables
- **Project Crystal Ball - Oil Market Forecasting** - May need updating for new schema

**LIKELY UNUSED (AI/Alerting features you mentioned not needing):**
- **Alert Groups Insights** - Grafana alerting feature dashboard
- **Incident Insights** - Incident management feature

---

## Database Observe and Optimize

Grafana Cloud's "Database Observe and Optimize" is available for PostgreSQL monitoring. This provides:
- Query performance analysis
- Connection pool monitoring
- Slow query detection

To enable:
1. Go to **Connections > Databases**
2. Add your Prisma Postgres connection
3. Enable "Observe and Optimize"

**Useful for:**
- Identifying slow dashboard queries
- Monitoring connection pool usage (important with Prisma's connection limits)
- Query plan analysis

---

## Local Development Setup

### Starting Local Grafana

```bash
cd /Volumes/Satechi\ Hub/ZINC-FUSION-V15/grafana
./start-grafana.sh
```

Access at: http://localhost:3000
Login: admin / admin

### Provisioning

Local Grafana auto-loads:
- **Datasource**: `provisioning/datasources/prisma-postgres.yaml`
- **Dashboards**: `provisioning/dashboards/default.yaml` points to `grafana/dashboards/`

Environment variables are loaded from `.env` via `start-grafana.sh`.

---

## Query Reference

### Training Experiments Query
```sql
SELECT
    model_name || ' | ' || COALESCE(model_nickname, '') as "Model",
    horizon_days || 'd' as "Horizon",
    trained_date as "Trained",
    ROUND(mae::numeric, 4) as "MAE",
    oof_count as "OOF Count",
    outcome as "Outcome",
    status as "Status",
    notes as "Notes"
FROM training.model_runs
ORDER BY created_at DESC
```

### OOF Performance by Window
```sql
SELECT
    horizon_days || 'd' as "Horizon",
    window_id as "Window",
    to_char(cutoff_date, 'MM/DD/YY') as "Cutoff",
    COUNT(*) as "Predictions",
    ROUND(AVG(core_p50)::numeric, 4) as "Avg P50",
    ROUND(AVG(target_value)::numeric, 4) as "Avg Target",
    ROUND(AVG(ABS(core_p50 - target_value))::numeric, 4) as "MAE"
FROM training.oof_core_zl_1d
WHERE target_value IS NOT NULL
GROUP BY horizon_days, window_id, cutoff_date
ORDER BY horizon_days, window_id
```

### Data Freshness Query
```sql
SELECT
    source as "Data Source",
    total_rows as "Rows",
    ROUND(hours_since_update::numeric, 1) as "Hours Since Update",
    CASE
        WHEN hours_since_update < 24 THEN 'OK'
        WHEN hours_since_update < 48 THEN 'Warning'
        ELSE 'Stale'
    END as "Status"
FROM ops.data_quality_metrics
ORDER BY hours_since_update DESC
```

---

## Troubleshooting

### Dashboard shows "No data"
1. Verify data source connection (test in Data Sources page)
2. Check table exists: `SELECT * FROM <table> LIMIT 1`
3. Check query syntax in panel edit mode

### Connection timeout
- Prisma Postgres may have connection limits
- Reduce max_open_conns in datasource config
- Check if accelerate proxy is needed

### SSL errors
- Ensure `sslmode=require` is set
- Grafana Cloud may need additional SSL settings

---

## Summary

1. **Primary dashboard**: Use `zinc-fusion-unified.json`
2. **Data source**: PostgreSQL pointing to `db.prisma.io:5432`
3. **Key tables**: `training.model_runs`, `training.oof_core_zl_1d`, `ops.data_quality_metrics`
4. **Clean up**: Remove unused alerting/incident dashboards if not needed
5. **Database Observe**: Enable for query performance monitoring