# Agent 3 Worklog: Data Plumbing / Backfill

**Branch:** `agent3/ingestion-backfill`
**Mission:** Fix P0 blockers (§2, §8) and make §8.5 GO/NO-GO SQL green.

---

## Session 2026-01-30

### 1) MANDATORY FIRST ACTION: Prove DB Access

**STATUS:** COMPLETE - DB ACCESS CONFIRMED

**Env setup source:** Docs/VERCEL_PRISMA_SETUP.md
- Scripts `scripts/prisma_status.sh` and `scripts/vercel_env_pull.sh` are referenced but DO NOT EXIST
- Used `.env` file (exists at repo root) with `DATABASE_URL`
- Standard DB connector: `src/fusion/db/connection.py`

**Commands run:**
```bash
PYTHONPATH="${PWD}/src:${PYTHONPATH}" .venv/bin/python -c "
from fusion.db import get_read_engine
import pandas as pd

engine = get_read_engine()
result = pd.read_sql('SELECT current_timestamp as ts, current_database() as db', engine)
print('DB CONNECTION SUCCESS')
print(result.to_string())
"
```

**Output:**
```
DB CONNECTION SUCCESS
                                ts        db
0 2026-01-30 17:16:54.554577+00:00  postgres
```

---

### 2) §8.5 GO/NO-GO SQL: Baseline Status

**Query run:**
```sql
SELECT 
    bucket,
    COUNT(*) as row_count,
    MIN(as_of_date) as min_date,
    MAX(as_of_date) as max_date,
    COUNT(*) FILTER (WHERE as_of_date >= CURRENT_DATE - INTERVAL '180 days') as last_180d_rows,
    ROUND(STDDEV(signal_1)::numeric, 6) as signal_1_stddev
FROM training.specialist_signals_1d
GROUP BY bucket
ORDER BY bucket
```

**Output (2026-01-30 17:16 UTC):**
```
          bucket  row_count    min_date    max_date  last_180d_rows  signal_1_stddev
0        biofuel       4794  2010-08-22  2026-01-27             150         1.214996
1          china       6398  2000-11-21  2026-01-16             116         1.210620
2          crush       6390  2000-08-11  2026-01-22             119         0.359749
3         energy       9269  1970-01-01  2026-01-27             150         0.612677
4            fed       8415  1970-01-01  2026-01-27             128         0.923620
5             fx       8415  1970-01-01  2026-01-27             128         0.931838
6           palm       3515  2010-11-22  2025-12-29             103         0.951136
7    substitutes       6698  1995-07-03  2026-01-15             115         1.129700
8         tariff       8415  1970-01-01  2026-01-27             128         0.963363
9   trump_effect       7289  2000-11-29  2026-01-22             146         0.793477
10    volatility       8280  1972-04-17  2026-01-27             128         0.789861
```

---

### 3) GO/NO-GO Analysis

**Criteria (from §8 P0 blockers):**
- Freshness: max(as_of_date) within 2 days of today (2026-01-30)
- Coverage: last 180 days ≥ 90% present (162 rows needed)
- Variance: stddev > epsilon (all pass, stddev > 0.35)

**Assessment:**

| bucket | max_date | Days Stale | last_180d_rows | Coverage % | Freshness | Coverage | VERDICT |
|--------|----------|------------|----------------|------------|-----------|----------|---------|
| biofuel | 2026-01-27 | 3 | 150 | 83% | FAIL | FAIL | NO-GO |
| china | 2026-01-16 | 14 | 116 | 64% | FAIL | FAIL | NO-GO |
| crush | 2026-01-22 | 8 | 119 | 66% | FAIL | FAIL | NO-GO |
| energy | 2026-01-27 | 3 | 150 | 83% | FAIL | FAIL | NO-GO |
| fed | 2026-01-27 | 3 | 128 | 71% | FAIL | FAIL | NO-GO |
| fx | 2026-01-27 | 3 | 128 | 71% | FAIL | FAIL | NO-GO |
| palm | 2025-12-29 | 32 | 103 | 57% | FAIL | FAIL | NO-GO |
| substitutes | 2026-01-15 | 15 | 115 | 64% | FAIL | FAIL | NO-GO |
| tariff | 2026-01-27 | 3 | 128 | 71% | FAIL | FAIL | NO-GO |
| trump_effect | 2026-01-22 | 8 | 146 | 81% | FAIL | FAIL | NO-GO |
| volatility | 2026-01-27 | 3 | 128 | 71% | FAIL | FAIL | NO-GO |

**DECISION: NO-GO (ALL 11 specialists)**

**Root causes:**
1. All specialists are stale (3-32 days behind)
2. No specialist meets 90% coverage threshold
3. PALM is critically stale (32 days)
4. Signal generation pipeline not running daily

---

### 4) Next Actions (Pending Agent 1 Directive)

Per role spec: "DATA COMPLETENESS ACTIONS (ONLY AFTER AGENT 1 FLAGS FAILURES)"

Awaiting Agent 1 to flag specific failures from §4 validation path before proceeding with:
1. Upstream raw table analysis per specialist
2. Backfill planning
3. Ingestion runner fixes

---

## 5) PALM Investigation (Priority 1)

**Query run:**
```sql
SELECT symbol, COUNT(*) as row_count, MIN(event_date) as min_date, MAX(event_date) as max_date,
       COUNT(*) FILTER (WHERE event_date >= CURRENT_DATE - INTERVAL '180 days') as last_180d_rows
FROM mkt.futures_1d WHERE symbol = 'CPO' GROUP BY symbol
```

**Output:**
```
  symbol  row_count    min_date    max_date  last_180d_rows
0    CPO       3780  2010-05-25  2026-01-29             116
```

**Finding:** CPO raw data is FRESH (max_date = 2026-01-29, only 1 day stale).
PALM specialist signal is stale (2025-12-29) because **signal generation pipeline has not run**, NOT because raw data is missing.

**FIX:** Re-run signal generation for PALM bucket.

---

## 6) CRUSH Investigation (Priority 2)

### 6a) Volume/Open Interest Analysis

**Query run:**
```sql
SELECT COUNT(*) as total,
       COUNT(*) FILTER (WHERE volume IS NOT NULL AND volume > 0) as with_volume,
       COUNT(*) FILTER (WHERE open_interest IS NOT NULL AND open_interest > 0) as with_oi
FROM mkt.futures_1d WHERE symbol = 'ZL'
```

**Output:**
```
   total  with_volume  with_oi
0   8417         6507      315
```

**Finding 1:** ZL has volume (77% coverage) but open_interest is SPARSE (3.7% coverage, only 315 rows).

**Finding 2:** COLUMN NAME MISMATCH
- Crush specialist expects: `volume`, `open_interest` (no prefix)
- Data loader produces: `zl_volume`, `zl_open_interest` (with prefix)
- File: `src/fusion/specialists/xgb_signals.py` L284-285
- File: `src/fusion/specialists/data_loaders.py` L82-86

### 6b) WASDE Column Name Analysis

**Query run:**
```sql
SELECT DISTINCT commodity, metric,
       CONCAT('wasde_', LOWER(REPLACE(commodity, ' ', '_')), '_', metric) as expected_col
FROM supply.usda_wasde_1m WHERE commodity = 'Soybean Oil'
```

**Output:**
```
      commodity                 metric                             expected_col
3   Soybean Oil   domestic_consumption   wasde_soybean_oil_domestic_consumption
```

**Finding 3:** WASDE COLUMN NAME MISMATCH
- Crush specialist expects: `wasde_soybean_oil_domestic`
- Data loader produces: `wasde_soybean_oil_domestic_consumption`
- File: `src/fusion/specialists/xgb_signals.py` L293

### 6c) Root Cause Summary for CRUSH

| Missing Feature | Expected Name | Actual Name | Issue Type |
|-----------------|---------------|-------------|------------|
| volume | `volume` | `zl_volume` | Wiring mismatch |
| open_interest | `open_interest` | `zl_open_interest` (sparse) | Wiring + data sparseness |
| wasde_soybean_oil_domestic | `wasde_soybean_oil_domestic` | `wasde_soybean_oil_domestic_consumption` | Naming mismatch |

**FIX OPTIONS:**
1. **Option A (preferred):** Fix data_loaders.py to add aliases: `volume` = `zl_volume`, `open_interest` = `zl_open_interest`
2. **Option B:** Fix xgb_signals.py to expect prefixed column names
3. **For WASDE:** Update xgb_signals.py L293 to use `wasde_soybean_oil_domestic_consumption`

---

## Blockers Identified

1. **Missing scripts:** `scripts/prisma_status.sh`, `scripts/vercel_env_pull.sh` referenced in docs but don't exist
2. **Signal pipeline stale:** All specialists need fresh signal generation run
3. **PALM:** Signal stale due to pipeline not running (raw CPO data is fresh)
4. **CRUSH:** Column name wiring mismatches + sparse OI data

---

## Proposed Fixes (Awaiting Agent 1 Approval)

### Fix 1: CRUSH column name aliases (data_loaders.py)
Add after L88:
```python
result["volume"] = result["zl_volume"]
result["open_interest"] = result["zl_open_interest"]
```

### Fix 2: CRUSH WASDE column name (xgb_signals.py L293)
Change `wasde_soybean_oil_domestic` → `wasde_soybean_oil_domestic_consumption`

### Fix 3: Regenerate all specialist signals
```bash
PYTHONPATH="${PWD}/src:${PYTHONPATH}" .venv/bin/python scripts/generate_specialist_signals.py --bucket all
```

---

## Commits This Session

1. `agent3: WORKLOG_AGENT3.md - DB access confirmed, §8.5 baseline captured`
