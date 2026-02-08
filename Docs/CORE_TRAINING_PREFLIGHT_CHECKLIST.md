# Core Training Pre-Flight Checklist

**Generated:** 2026-02-03
**Purpose:** Ensure all data is fresh and complete before Core training

---

## Data Freshness Requirements

| Frequency | Max Staleness | Rationale |
|-----------|---------------|-----------|
| **Daily** | 2 trading days | Market-critical signals |
| **Weekly** | 7 calendar days | CFTC COT, EPA RINs |
| **Monthly** | 35 calendar days | WASDE reports |

---

## 1. CRITICAL: Data Staleness Status

### ❌ STALE - Must Refresh Before Training

| Source | Latest Date | Stale Days | Max Allowed | Action Required |
|--------|-------------|------------|-------------|-----------------|
| `mkt.futures_1d` (ZL) | 2026-01-30 | 4 | 2 | Run Yahoo EOD ingestion |
| `econ.rates_1d` (DFF) | 2026-01-30 | 4 | 2 | Run FRED ingestion |
| `supply.epa_rin_1d` (D4) | 2025-12-22 | **43** | 7 | **CRITICAL: EPA RIN backfill** |
| `training.matrix_1d` | 2026-01-30 | 4 | 2 | Rebuild matrix |
| `specialist_signals (crush)` | 2026-01-22 | **12** | 2 | **Regenerate crush specialist** |
| `specialist_signals (all)` | 2026-01-29 | 5 | 2 | Regenerate all specialists |
| `alt.profarmer_news` | 2026-01-31 | 3 | 2 | Run ProFarmer scraper |
| `alt.econ_news` | 2026-01-29 | 5 | 3 | Run FRED blog scraper |
| `alt.policy_news` | 2026-01-26 | 8 | 7 | Run policy news scraper |

### ✅ OK - Current Data

| Source | Latest Date | Stale Days | Max Allowed |
|--------|-------------|------------|-------------|
| `mkt.etf_1d` | 2026-02-02 | 1 | 2 |
| `pos.cftc_1w` (ZL) | 2026-01-27 | 7 | 7 |
| `supply.usda_wasde_1m` | 2026-01-12 | 22 | 35 |
| `alt.weather_1d` | 2026-02-02 | 1 | 2 |
| `econ.rates_1d` | 2026-02-03 | 0 | 2 |
| `econ.commodities_1d` | 2026-02-02 | 1 | 2 |
| `econ.vol_indices_1d` | 2026-02-02 | 1 | 2 |
| `econ.inflation_1d` | 2026-02-02 | 1 | 2 |

---

## 2. Data Quality: NULL Analysis

### Matrix NULL Status (Last 12 Months)
✅ **CLEAN** - All key columns have 0% NULLs for recent data

### Raw Data NULL Concerns

| Table | Issue | Impact |
|-------|-------|--------|
| `mkt.futures_1d` (ZL) | 717 NULL closes (historical) | Handled by ffill in matrix build |
| `mkt.futures_1d` (ZL) | 4,395 NULL OI (historical) | Handled by ffill in matrix build |
| `mkt.futures_1d` (ZS) | 14,273 NULL OI | Historical, not recent |

---

## 3. Specialist Signals Status

| Bucket | Rows | Latest | Avg Confidence | Status |
|--------|------|--------|----------------|--------|
| crush | 7,052 | 2026-01-22 | 0.794 | ❌ **12 days stale** |
| china | 10,114 | 2026-01-29 | 0.527 | ⚠️ 5 days stale |
| substitutes | 8,445 | 2026-01-30 | 0.557 | ⚠️ 4 days stale |
| palm | 7,240 | 2026-01-30 | 0.880 | ⚠️ 4 days stale |
| energy | 8,093 | 2026-01-29 | 0.941 | ⚠️ 5 days stale |
| fed | 7,237 | 2026-01-29 | 0.824 | ⚠️ 5 days stale |
| fx | 7,237 | 2026-01-29 | 0.904 | ⚠️ 5 days stale |
| volatility | 7,237 | 2026-01-29 | 0.897 | ⚠️ 5 days stale |
| tariff | 7,237 | 2026-01-29 | 0.913 | ⚠️ 5 days stale |
| trump_effect | 7,478 | 2026-01-29 | 0.748 | ⚠️ 5 days stale |
| biofuel | 4,930 | 2026-01-29 | 0.831 | ⚠️ 5 days stale |

**All 11 specialists need regeneration before Core training.**

---

## 4. News Data Status

### ProFarmer News ✅ GOOD
- **8,461 articles** (2021-05-25 to 2026-01-31)
- Properly tagged for specialists (5,831 crush, 1,804 tariff/trump, etc.)
- Flowing correctly to all specialists

### FRED Blog (econ_news) ✅ GOOD
- **1,131 articles** (2014-03-24 to 2026-01-29)
- Source: `fred_blog`
- Note: `econ.news_event` has same data but NO specialist tags

### FRED Data Segments ✅ SPLIT CORRECTLY
| Segment | Series | Latest |
|---------|--------|--------|
| `econ.rates_1d` | 52 | 2026-02-03 |
| `econ.activity_1d` | 29 | 2026-01-12 |
| `econ.inflation_1d` | 17 | 2026-02-02 |
| `econ.commodities_1d` | 30 | 2026-02-02 |
| `econ.vol_indices_1d` | 20 | 2026-02-02 |
| `econ.money_1d` | 9 | 2026-02-02 |
| `econ.labor_1d` | 5 | 2026-01-24 |

---

## 5. Potential Additions to Core

### ETF Features (NOT YET IN MATRIX)
- **24 ETFs** with 1,950 rows each (2018-05-01 to 2026-02-02)
- VWAP available for most
- ZL correlations (21d/63d/126d) calculated
- **Recommendation:** Consider adding top ETF correlations to matrix

### Missing Data Identified
1. **VIX in rates_1d** - NOT PRESENT (check series_id)
2. **Options data** - No dedicated options tables found

---

## 6. Pre-Training Commands

### Step 1: Refresh Raw Data
```bash
# Yahoo EOD (futures)
.venv/bin/python scripts/ingest_yahoo_eod.py

# FRED data (uses downloaded CSVs)
.venv/bin/python scripts/ingest_downloads_fred.py

# EPA RIN (CRITICAL - check staleness)
.venv/bin/python scripts/refresh_epa_rin.py

# News sources (ProFarmer, FRED blog, policy)
.venv/bin/python scripts/ingest_news_sources.py
```

### Step 2: Regenerate All Specialists
```bash
# Generate specialist signals for all 11 buckets
.venv/bin/python scripts/generate_specialist_signals.py --bucket all --strict
```

### Step 3: Rebuild Training Matrix
```bash
# Build core training matrix (training.matrix_1d)
.venv/bin/python -m fusion.core_training.build_matrix --symbol ZL
```

### Step 4: Validate Pre-Flight
```bash
# ALL DATA policy is now enforced automatically in train_models.py
# Manual check (optional):
.venv/bin/python -c "from fusion.validation.all_data_policy import enforce_all_data_policy; import psycopg2, os; conn=psycopg2.connect(os.getenv('DATABASE_URL')); enforce_all_data_policy(conn, horizon=5, strict=True)"
```

### Step 5: Run Core Training
```bash
# Smoke test (single horizon)
.venv/bin/python -m fusion.core_training.run_pipeline --skip-matrix --horizons 5

# Full run (all horizons)
.venv/bin/python -m fusion.core_training.run_pipeline --skip-matrix
```

---

## 7. Validation Gates

Before training, these must pass:

- [ ] All daily sources < 2 days stale
- [ ] All weekly sources < 7 days stale
- [ ] EPA RIN data < 7 days stale
- [ ] All 11 specialists regenerated
- [ ] Matrix rebuilt with fresh data
- [ ] `enforce_all_data_policy()` passes
- [ ] 600+ features loaded
- [ ] Zero NaN values in final matrix

---

## 8. Known Issues to Monitor

1. **econ.news_event has no specialist_tags** - Not flowing to specialists
2. **VIX not in econ.rates_1d** - Check if in vol_indices_1d instead
3. **ETF features not in matrix** - Potential enhancement
4. **Historical OI gaps** - Handled by ffill, not blocking

---

*Checklist generated by Claude | ZINC-FUSION-V15 | 2026-02-03*
