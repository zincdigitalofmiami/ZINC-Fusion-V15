# Databento Live Integration - Testing Plan

## Overview

This document describes the comprehensive testing plan for Databento live integration. All tests follow the "Deep Testing First" philosophy: **NO CODE CHANGES until testing proves the current state is fully understood and symbol change (ZL.c.0 → ZL.n.0) is safe**.

## Test Scripts Created

All test scripts are located in `scripts/` directory:

1. **test_databento_current_state.py** - Database state audit
2. **test_databento_symbol_comparison.py** - Compare ZL.c.0 vs ZL.n.0 prices
3. **test_databento_live_connector.py** - Live connector behavior tests
4. **test_databento_historical_jobs.py** - Historical job behavior tests
5. **test_chart_api_integration.py** - Chart API endpoint tests
6. **test_parallel_symbols.py** - Parallel symbol collection (7 days)
7. **test_roll_date_impact.py** - Roll date impact analysis
8. **test_failure_modes.py** - Error scenario tests
9. **test_load.py** - 24-hour load testing
10. **test_e2e_data_flow.py** - End-to-end data flow validation

## Quick Start

### Prerequisites

```bash
# Ensure environment variables are set
export DATABENTO_API_KEY="your_key"
export INNGEST_EVENT_KEY="your_key"  # For live connector tests
export DATABASE_URL="your_connection_string"
export API_BASE_URL="http://localhost:8000"  # For API tests
```

### Running Tests

#### Phase 0: Current State Verification (CRITICAL - DO FIRST)

```bash
# 1. Audit current database state
python scripts/test_databento_current_state.py

# 2. Compare symbols (24h collection)
python scripts/test_databento_symbol_comparison.py

# 3. Test live connector behavior
python scripts/test_databento_live_connector.py

# 4. Test historical jobs
python scripts/test_databento_historical_jobs.py

# 5. Test chart API endpoints
python scripts/test_chart_api_integration.py
```

#### Phase 1: Symbol Change Safety Test

```bash
# 6. Parallel symbol collection (requires 2 terminals)
# Terminal 1:
python scripts/test_parallel_symbols.py --symbol ZL.c.0 --suffix c

# Terminal 2:
python scripts/test_parallel_symbols.py --symbol ZL.n.0 --suffix n

# After 7 days, compare results:
python scripts/test_parallel_symbols.py --compare

# 7. Analyze roll date impact
python scripts/test_roll_date_impact.py
```

#### Phase 2: Error Handling & Performance

```bash
# 8. Test failure modes
python scripts/test_failure_modes.py

# 9. Load testing (24 hours)
python scripts/test_load.py

# 10. End-to-end validation
python scripts/test_e2e_data_flow.py
```

## Test Outputs

Each test generates JSON reports:

- `test_results_current_state.json` - Database audit results
- `symbol_comparison_report.json` - Symbol comparison data
- `test_live_connector_results.json` - Connector behavior results
- `test_historical_jobs_results.json` - Historical job results
- `test_chart_api_results.json` - API endpoint results
- `parallel_symbols_comparison.json` - Parallel collection comparison
- `roll_date_impact_report.md` - Roll date analysis report
- `roll_date_impact_data.json` - Roll date data
- `test_failure_modes_results.json` - Failure mode results
- `test_load_results.json` - Load test metrics
- `test_e2e_data_flow_results.json` - E2E validation results

## Success Criteria

**ALL of these must pass before proceeding:**

1. ✅ Current state fully understood (no surprises)
2. ✅ Symbol comparison shows <0.1% price difference
3. ✅ Roll dates within acceptable range
4. ✅ All failure modes handled gracefully
5. ✅ Performance meets requirements (<500MB memory, <10% CPU)
6. ✅ E2E data flow 100% intact
7. ✅ Rollback plan documented and tested

## Test Details

### Test 1: Database State Audit

**Purpose**: Understand current database state before making changes.

**Checks**:
- Source distribution (`databento` vs `databento_live` vs `yahoo`)
- Price discontinuities (>5% jumps)
- Volume consistency
- Date coverage gaps
- Roll date patterns

**Run**: `python scripts/test_databento_current_state.py`

### Test 2: Symbol Comparison

**Purpose**: Compare ZL.c.0 vs ZL.n.0 prices in parallel.

**Duration**: 24 hours (configurable via `TEST_DURATION_HOURS`)

**Metrics**:
- Max price difference (%)
- Average price difference
- Volume correlation
- Roll date differences

**Run**: `python scripts/test_databento_symbol_comparison.py`

### Test 3: Live Connector Behavior

**Purpose**: Test connector behavior under various scenarios.

**Scenarios**:
- Normal operation (1 hour)
- Graceful shutdown (manual SIGTERM)
- Network failure (manual simulation)
- Inngest failure (simulated)
- Data corruption (validation)

**Run**: `python scripts/test_databento_live_connector.py`

### Test 4: Historical Job Behavior

**Purpose**: Verify historical jobs work correctly.

**Checks**:
- Incremental fetch (only new data)
- 24h boundary (doesn't fetch last 24h)
- Source conflict (doesn't overwrite live data)
- Empty window handling
- Backfill capability (30 days)

**Run**: `python scripts/test_databento_historical_jobs.py`

### Test 5: Chart API Integration

**Purpose**: Verify all chart endpoints work correctly.

**Endpoints Tested**:
- `/api/zl/intraday?hours=24` (15m bars)
- `/api/zl/price-1h?hours=168` (1h bars)
- `/api/zl/price-1d?days=90` (daily bars)
- `/api/zl/chart?days=365` (chart format)

**Checks**:
- Response format
- Data ordering
- Missing timestamps
- Performance (<500ms)

**Run**: `python scripts/test_chart_api_integration.py`

### Test 6: Parallel Symbol Collection

**Purpose**: Run both symbols simultaneously for 7 days.

**Design**:
- Two connectors write to separate test tables
- Compare results after collection period
- Verify price differences <0.1% on 95% of bars

**Run**: See Phase 1 instructions above.

### Test 7: Roll Date Impact Analysis

**Purpose**: Understand when/why symbols diverge.

**Analysis**:
- Identify roll dates (last 90 days)
- Compare prices on roll dates
- Measure impact on daily aggregates

**Run**: `python scripts/test_roll_date_impact.py` (after Test 6 completes)

### Test 8: Failure Mode Testing

**Purpose**: Test error handling.

**Scenarios**:
- API timeout
- Connection drop
- Inngest failures
- Database disconnect
- Memory pressure
- Clock skew

**Run**: `python scripts/test_failure_modes.py`

### Test 9: Load Testing

**Purpose**: Verify performance under sustained load.

**Duration**: 24 hours (configurable via `TEST_DURATION_HOURS`)

**Metrics**:
- Memory usage (should be stable <500MB)
- CPU usage (should be <10% avg)
- Database write rate
- Event emission rate

**Run**: `python scripts/test_load.py`

### Test 10: End-to-End Data Flow

**Purpose**: Verify complete data flow integrity.

**Flow**:
1. Live connector emits event
2. Inngest handler receives event
3. Database row inserted
4. Chart API reads row
5. Chart displays data

**Checks**:
- Event payload correctness
- Database row matches event
- API response matches database
- End-to-end latency <2 seconds

**Run**: `python scripts/test_e2e_data_flow.py`

## Execution Timeline

### Week 1: Current State Verification
- **Day 1-2**: Run Tests 1-5
- **Day 3**: Analyze results, identify issues
- **Day 4-5**: Start Test 6 (parallel collection)

### Week 2: Symbol Comparison
- **Day 1-7**: Continue Test 6 (collect 7 days)
- **Day 8**: Run Test 7 (roll date analysis)
- **Day 9**: Analyze results, make go/no-go decision

### Week 3: Error Handling & Performance
- **Day 1-2**: Run Tests 8-9
- **Day 3**: Run Test 10 (E2E validation)
- **Day 4-5**: Fix any issues found

### Week 4: Production Readiness
- **Day 1**: Review all test results
- **Day 2**: Create rollback plan
- **Day 3**: Deploy to staging
- **Day 4-5**: Monitor staging, verify

## Rollback Plan

If any test fails:

1. **Keep current `ZL.c.0` connector running**
2. **New `ZL.n.0` connector writes to test tables only**
3. **Switch production only after 7 days of successful parallel operation**
4. **Can revert symbol change instantly (just restart with old symbol)**

## Notes

- Some tests require manual execution (timeout simulation, connection drop)
- Parallel symbol collection requires running two instances simultaneously
- Load testing runs for 24 hours - ensure adequate resources
- All tests generate JSON reports for analysis
- Review test results before proceeding to next phase

## Next Steps

After all tests pass:

1. Review all test results
2. Document findings
3. Create rollback plan
4. Proceed with symbol change (ZL.c.0 → ZL.n.0)
5. Monitor production closely after change
