# Data Freshness Status - Quick Reference

**Last Checked:** 2026-01-02  
**Today's Date:** 2026-01-02

---

## Status Legend
- 🟢 **FRESH** - Data is current (< 5 days behind)
- 🟡 **STALE** - Data needs refresh (5-14 days behind)
- 🔴 **VERY STALE** - Data urgently needs update (> 14 days behind)

---

## Current Data Status

| Data Source | Last Update | Days Behind | Status | Action Required |
|-------------|-------------|-------------|--------|-----------------|
| **Market Futures** | 2025-12-29 | 4 days | 🟢 FRESH | Monitor daily |
| **FRED Observations** | 2025-12-31 | 2 days | 🟢 FRESH | Monitor daily |
| **CFTC COT** | 2025-12-23 | 10 days | 🟢 FRESH | Weekly update due |
| **Weather (NOAA)** | 2025-12-20 | **13 days** | 🟡 STALE | **UPDATE NOW** |
| **USDA Export Sales** | 2025-12-11 | **22 days** | 🔴 VERY STALE | **UPDATE URGENT** |
| **USDA WASDE** | 2025-12-12 | 21 days | 🟢 FRESH | Monthly - next due ~Jan 10 |

---

## Recommended Update Schedule

### Daily Updates
- ✅ Market Futures (all symbols)
- ✅ FRED Daily Series (FX, commodities, rates)
- ✅ Weather Data (NOAA stations)

### Weekly Updates
- ✅ CFTC COT Reports (Fridays)
- ✅ USDA Export Sales (Thursdays)
- ✅ FRED Weekly Series (gas prices, financial stress)

### Monthly Updates
- ✅ USDA WASDE (typically ~10th of month)
- ✅ FRED Monthly Series (CPI, employment, GDP)

---

## Priority Actions (Next 24 Hours)

1. **🔴 CRITICAL:** Update USDA Export Sales (22 days behind)
2. **🟡 HIGH:** Refresh Weather Data (13 days behind)
3. **🟢 MEDIUM:** Update Market Futures (4 days behind → target <3 days)
4. **🟢 LOW:** Update FRED Observations (2 days behind is acceptable)

---

## Data Pipeline Health

| Pipeline | Status | Last Run | Next Run |
|----------|--------|----------|----------|
| Futures Ingest | 🟢 | 2025-12-29 | Daily |
| FRED Sync | 🟢 | 2025-12-31 | Daily |
| Weather Scrape | 🔴 | 2025-12-20 | **OVERDUE** |
| COT Download | 🟢 | 2025-12-23 | Friday |
| USDA Export | 🔴 | 2025-12-11 | **OVERDUE** |
| USDA WASDE | 🟢 | 2025-12-12 | ~Jan 10 |

---

## Impact on Forecasting

### Near-Term Forecasts (1-7 days)
**Impact: MEDIUM**
- Weather staleness reduces accuracy for immediate supply shocks
- Market futures are fresh enough for price momentum
- FRED data is adequate

**Recommendation:** Update weather before running near-term forecasts.

### Medium-Term Forecasts (7-30 days)
**Impact: LOW-MEDIUM**
- Export sales staleness affects demand outlook
- Weather data matters for growing season (less critical in winter)
- Price data is sufficient

**Recommendation:** Update export sales before monthly forecast runs.

### Long-Term Forecasts (30-90 days)
**Impact: LOW**
- Structural factors (crush spreads, FX) are well-covered
- WASDE monthly reports are current
- COT positioning is recent

**Recommendation:** Current data is adequate for strategic forecasts.

---

## Data Quality Alerts

### 🔴 Critical Issues
- USDA Export Sales: 22 days behind target (weekly cadence)

### 🟡 Warnings
- Weather Data: 13 days behind target (daily cadence)

### 🟢 Normal Operations
- Market Futures: Within acceptable range
- FRED: Within acceptable range
- CFTC COT: Within acceptable range
- USDA WASDE: Within acceptable range

---

## Refresh Commands

### Quick Refresh (Weather + Export Sales)
```bash
# Refresh weather data
python scripts/ingest/weather_noaa.py --backfill-days 14

# Refresh USDA export sales
python scripts/ingest/usda_export_sales.py --backfill-weeks 4
```

### Full Refresh (All Sources)
```bash
# Run complete data pipeline
python scripts/data_pipeline.py --sources all --backfill auto
```

### Verify Freshness
```bash
# Check data freshness across all tables
python scripts/check_freshness.py --alert-threshold 7
```

---

*Auto-generated freshness check - Run `python data_quality_audit.py` to update*
