# Code Review Action Items - ZINC-Fusion-V15
## Prioritized Remediation Plan

**Review Date:** 2026-02-13  
**Total Issues Found:** 12 (4 Critical, 4 High, 4 Medium)

---

## 🔴 CRITICAL - Fix Immediately (Week 1)

### 1. Fix Connection Leak in zl-live.ts
**File:** `frontend/src/inngest/zl-live.ts`  
**Lines:** 160-170  
**Effort:** 10 minutes  
**Risk:** Pool exhaustion under load

**Current Code:**
```typescript
const receiptClient = await pool.connect();
await receiptClient.query(
  `INSERT INTO ops.inngest_receipts (event_name, status) VALUES ($1, $2)`,
  [event.name, 'processed']
);
// Missing: receiptClient.release()
```

**Fix:**
```typescript
const receiptClient = await pool.connect();
try {
  await receiptClient.query(
    `INSERT INTO ops.inngest_receipts (event_name, status) VALUES ($1, $2)`,
    [event.name, 'processed']
  );
} finally {
  receiptClient.release();
}
```

**Testing:**
```bash
# Simulate failure scenario
# Insert error before query, verify connection released
npm --prefix frontend run test:inngest -- zl-live
```

---

### 2. Implement API Authentication
**File:** `src/fusion/api/server.py`  
**Lines:** All public endpoints (30+)  
**Effort:** 2-4 hours  
**Risk:** Security vulnerability, data exposure

**Current State:**
- Only `/api/db/*` endpoints protected with token auth
- All business logic endpoints unprotected

**Implementation Plan:**

**Step 1: Add authentication dependency**
```python
from fastapi import Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)):
    """Verify API key against environment variable."""
    expected_key = os.environ.get("FUSION_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="API key not configured")
    if api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key
```

**Step 2: Apply to endpoints**
```python
@app.get("/api/dashboard/summary", dependencies=[Depends(verify_api_key)])
def dashboard_summary(...):
    ...

@app.get("/api/forecast/quantiles", dependencies=[Depends(verify_api_key)])
def forecast_quantiles(...):
    ...
```

**Step 3: Add rate limiting**
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/api/dashboard/summary", dependencies=[Depends(verify_api_key)])
@limiter.limit("100/hour")
def dashboard_summary(request: Request, ...):
    ...
```

**Testing:**
```bash
# Test without API key (should fail)
curl http://localhost:8000/api/dashboard/summary

# Test with valid API key (should succeed)
curl -H "X-API-Key: test-key" http://localhost:8000/api/dashboard/summary

# Test rate limiting (101st request should fail)
for i in {1..101}; do curl -H "X-API-Key: test-key" http://localhost:8000/api/dashboard/summary; done
```

**Environment Variables:**
```bash
# Add to .env
FUSION_API_KEY=<generate-secure-key>
```

---

### 3. Add Database Error Handling
**File:** `src/fusion/api/server.py`  
**Lines:** Multiple endpoints (872, 1088, 1595)  
**Effort:** 1-2 hours  
**Risk:** Unhandled exceptions, traceback exposure

**Implementation:**

**Step 1: Create error handler wrapper**
```python
from functools import wraps
import psycopg2

def handle_db_errors(func):
    """Decorator to catch and handle database errors."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except psycopg2.Error as e:
            logger.error(f"Database error in {func.__name__}: {e}")
            raise HTTPException(
                status_code=500,
                detail="Database query failed. Please try again later."
            )
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred."
            )
    return wrapper
```

**Step 2: Apply to endpoints**
```python
@app.get("/api/zl/live")
@handle_db_errors
def zl_live(limit: int = Query(100, ge=1, le=1000)):
    rows = _fetch_rows("""
        SELECT timestamp, open, high, low, close, volume
        FROM analytics.price_1m
        WHERE symbol = 'ZL'
        ORDER BY timestamp DESC
        LIMIT %s
    """, [limit])
    return {"data": rows}

@app.post("/api/db/query")
@handle_db_errors
def db_query(payload: dict[str, Any], ...):
    ...
```

**Testing:**
```bash
# Test with invalid SQL
curl -X POST http://localhost:8000/api/db/query \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM nonexistent_table"}'

# Test with database connection failure
# (stop database, make request, should return 500 without traceback)
```

---

### 4. Fix N+1 Query in Specialist Loop
**File:** `src/fusion/api/server.py`  
**Lines:** 351-365  
**Effort:** 30 minutes  
**Risk:** Performance degradation (2-3 second latency)

**Current Code:**
```python
for s in specialists:
    table = f"specialist_{s}_1d"
    if _table_exists("training", table):
        row = _fetch_rows(f"""
            SELECT '{s}' as specialist, COUNT(*)::BIGINT as rows,
                   MIN(trade_date) as start_date, MAX(trade_date) as end_date
            FROM training.{table}
        """)[0]
        result.append(row)
```

**Fix: Single Query**
```python
# Option 1: UNION ALL (if separate tables exist)
query = """
SELECT 'crush' as specialist, COUNT(*)::BIGINT as rows,
       MIN(trade_date) as start_date, MAX(trade_date) as end_date
FROM training.specialist_signals_1d WHERE specialist = 'crush'
UNION ALL
SELECT 'china' as specialist, COUNT(*)::BIGINT as rows,
       MIN(trade_date) as start_date, MAX(trade_date) as end_date
FROM training.specialist_signals_1d WHERE specialist = 'china'
UNION ALL
-- ... (repeat for all 11 specialists)
"""

# Option 2: GROUP BY (if single table with specialist column)
query = """
SELECT specialist, COUNT(*)::BIGINT as rows,
       MIN(trade_date) as start_date, MAX(trade_date) as end_date
FROM training.specialist_signals_1d
GROUP BY specialist
"""

result = _fetch_rows(query)
```

**Testing:**
```bash
# Benchmark before
time curl http://localhost:8000/api/overview/models

# Benchmark after (should be <100ms vs 2-3 seconds)
time curl http://localhost:8000/api/overview/models
```

---

## ⚠️ HIGH PRIORITY - Fix Within Month

### 5. Add Metadata Schema to Prisma
**File:** `prisma/schema.prisma`  
**Lines:** 9  
**Effort:** 30 minutes + migration  
**Risk:** Architecture violation

**Fix:**
```prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
  schemas  = ["alt", "analytics", "econ", "features", "forecasts", 
              "metadata", "mkt", "model", "ops", "pos", "supply", "training"]
}

// Add metadata models
model instrument {
  canonical_id    String   @id
  asset_class     String
  primary_source  String
  created_at      DateTime @default(now())
  
  @@map("instrument")
  @@schema("metadata")
}

model symbol_mapping {
  id             String   @id @default(cuid())
  canonical_id   String
  source_table   String
  source_symbol  String
  is_primary     Boolean  @default(false)
  confidence     Float?
  
  @@unique([source_table, source_symbol])
  @@map("symbol_mapping")
  @@schema("metadata")
}
```

**Migration:**
```bash
scripts/prisma.sh migrate dev --name add-metadata-schema
scripts/prisma.sh migrate deploy
```

---

### 6. Migrate Float to Decimal for Price Columns
**File:** `prisma/schema.prisma`  
**Tables:** `mkt.futures_1d`, `model.core_cone_1d`  
**Effort:** 1 hour + migration testing  
**Risk:** Data migration, requires downtime

**Implementation:**

**Step 1: Create migration**
```prisma
// Update mkt.futures_1d
model futures_1d {
  // BEFORE
  // open  Float
  // high  Float
  // low   Float
  // close Float
  
  // AFTER
  open  Decimal @db.Decimal(10, 4)
  high  Decimal @db.Decimal(10, 4)
  low   Decimal @db.Decimal(10, 4)
  close Decimal @db.Decimal(10, 4)
}

// Update model.core_cone_1d
model core_cone_1d {
  // BEFORE
  // p10 Float
  // p50 Float
  // p90 Float
  
  // AFTER
  p10 Decimal @db.Decimal(10, 6)
  p50 Decimal @db.Decimal(10, 6)
  p90 Decimal @db.Decimal(10, 6)
}
```

**Step 2: Test migration**
```sql
-- Dry run: Check data conversion
SELECT 
  event_date,
  symbol,
  close::NUMERIC(10, 4) as close_decimal,
  ABS(close - close::NUMERIC(10, 4)) as precision_loss
FROM mkt.futures_1d
WHERE ABS(close - close::NUMERIC(10, 4)) > 0.0001
LIMIT 10;

-- If precision_loss is acceptable, proceed with migration
```

**Step 3: Execute migration**
```bash
scripts/prisma.sh migrate dev --name float-to-decimal
scripts/prisma.sh migrate deploy
```

---

### 7. Add Indexes to training.matrix_1d
**File:** `prisma/schema.prisma`  
**Lines:** 1659  
**Effort:** 20 minutes  
**Risk:** Index build time (5-10 minutes on large table)

**Implementation:**
```prisma
model matrix_1d {
  trade_date DateTime @db.Date
  symbol     String   @db.VarChar(20)
  
  // ... (existing columns)
  
  @@id([trade_date, symbol])
  @@index([trade_date])  // ADD: For date range queries
  @@index([symbol])      // ADD: For symbol filtering
  @@schema("training")
  @@map("matrix_1d")
}
```

**Migration:**
```bash
scripts/prisma.sh migrate dev --name add-matrix-indexes
```

**Testing:**
```sql
-- Before: Explain analyze (should show seq scan)
EXPLAIN ANALYZE
SELECT * FROM training.matrix_1d
WHERE trade_date >= '2024-01-01'
LIMIT 1000;

-- After: Explain analyze (should show index scan)
EXPLAIN ANALYZE
SELECT * FROM training.matrix_1d
WHERE trade_date >= '2024-01-01'
LIMIT 1000;
```

---

### 8. Fix N+1 Backfill Query in Board Crush
**File:** `frontend/src/inngest/board-crush-daily.ts`  
**Lines:** 291-300  
**Effort:** 30 minutes  
**Risk:** Backfill performance (500 individual queries)

**Current Code:**
```typescript
for (const components of batch) {
  const existing = await client.query(
    `SELECT board_crush FROM analytics.board_crush_1d WHERE trade_date = $1`,
    [crushResult.tradeDate]
  );
  if (!existing.rows.length) {
    // Insert new row
  }
}
```

**Fix:**
```typescript
// Batch fetch all existing dates
const dates = batch.map(c => c.tradeDate);
const existingResult = await client.query(
  `SELECT trade_date, board_crush 
   FROM analytics.board_crush_1d 
   WHERE trade_date = ANY($1::date[])`,
  [dates]
);

// Create lookup map
const existingMap = new Map(
  existingResult.rows.map(r => [r.trade_date.toISOString().split('T')[0], r.board_crush])
);

// Check existence in O(1)
for (const components of batch) {
  const dateKey = crushResult.tradeDate.toISOString().split('T')[0];
  if (!existingMap.has(dateKey)) {
    // Insert new row
  }
}
```

**Testing:**
```bash
# Benchmark backfill (500 dates)
npm --prefix frontend run test:inngest -- board-crush-daily --backfill

# Before: ~5 seconds (500 queries)
# After: ~200ms (1 batch query)
```

---

## ℹ️ MEDIUM PRIORITY - Fix Within Quarter

### 9-12. Additional Items
See `CODE_REVIEW_FINDINGS.md` for details on:
- FRED idempotency key (Issue #10)
- API rate limiting implementation (Issue #11)
- Vegas schema documentation (Issue #12)
- INTERVAL injection mitigation (Issue #8)

---

## IMPLEMENTATION CHECKLIST

### Week 1 (Critical)
- [ ] Fix zl-live.ts connection leak
- [ ] Add API authentication
- [ ] Implement database error handling
- [ ] Fix specialist loop N+1 query
- [ ] Test all 4 critical fixes
- [ ] Deploy to staging
- [ ] Smoke test production

### Week 2-4 (High Priority)
- [ ] Add metadata schema to Prisma
- [ ] Create Float → Decimal migration
- [ ] Test migration on staging
- [ ] Add indexes to training.matrix_1d
- [ ] Fix board-crush backfill query
- [ ] Deploy to production

### Month 2-3 (Medium Priority)
- [ ] Add FRED idempotency
- [ ] Implement API rate limiting
- [ ] Document vegas schema
- [ ] Refactor INTERVAL usage
- [ ] Create telemetry dashboard
- [ ] Write integration tests

---

## SUCCESS METRICS

### Performance Improvements
- API specialist endpoint: 2-3s → <100ms (95% reduction)
- Board crush backfill: 5s → <200ms (96% reduction)
- Pool exhaustion incidents: 0 (baseline)

### Security Improvements
- Protected endpoints: 0 → 30+ (100% coverage)
- Rate limit violations: Track with monitoring
- Unauthorized access attempts: Log and alert

### Data Integrity
- Price precision errors: Reduce from Float rounding
- Connection leaks: 0 incidents
- Query failures: Proper error handling (no traceback exposure)

---

## ROLLBACK PLAN

### If Issues Arise During Implementation

**API Authentication:**
```python
# Emergency rollback: Comment out authentication
# @app.get("/api/dashboard/summary", dependencies=[Depends(verify_api_key)])
@app.get("/api/dashboard/summary")
def dashboard_summary(...):
    ...
```

**Database Migration:**
```bash
# Rollback last migration
scripts/prisma.sh migrate resolve --rolled-back <migration-name>
```

**Connection Leak Fix:**
```bash
# Revert zl-live.ts to previous version
git checkout HEAD~1 frontend/src/inngest/zl-live.ts
npm --prefix frontend run build
```

---

## MONITORING POST-DEPLOYMENT

### Critical Metrics to Watch

**API Performance:**
```sql
-- Monitor endpoint latency (should be <100ms for 95th percentile)
SELECT endpoint, percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)
FROM api_logs
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY endpoint;
```

**Connection Pool Health:**
```sql
-- Monitor pool utilization (should stay <80%)
SELECT 
  (count(*) FILTER (WHERE state = 'active'))::float / 
  (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') * 100 
  AS pool_utilization_pct
FROM pg_stat_activity;
```

**Authentication Success Rate:**
```sql
-- Monitor auth failures (should be <1% of total requests)
SELECT 
  COUNT(*) FILTER (WHERE status = 401) as auth_failures,
  COUNT(*) as total_requests,
  (COUNT(*) FILTER (WHERE status = 401))::float / COUNT(*) * 100 as failure_rate_pct
FROM api_logs
WHERE timestamp > NOW() - INTERVAL '1 hour';
```

---

**Generated:** 2026-02-13T18:35:11.751Z  
**Review Tool:** GitHub Copilot Agent
