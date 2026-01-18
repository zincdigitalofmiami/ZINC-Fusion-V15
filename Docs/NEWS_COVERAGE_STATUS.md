# News Data Coverage Status

**Generated:** 2026-01-16  
**Total Articles:** 3,557

## Honest Scorecard

| Metric | Count |
|--------|-------|
| **Total Articles** | 3,557 |
| **With Date** | 495 (14%) |
| **Missing Date** | 3,062 (86%) |
| **Unique Sources** | 110 |
| **Sources with Dates** | 13 |

**Bottom Line:** 86% of our news data is undated legacy junk. Only 14% is usable for time-series features.

## Barchart RSS Coverage (With Dates ✅)

| Feed | Articles | Earliest | Latest | Avg Sentiment |
|------|----------|----------|--------|---------------|
| grain | 80 | 2026-01-14 | 2026-01-16 | -0.003 |
| energy | 60 | 2026-01-12 | 2026-01-15 | +0.137 |
| softs | 59 | 2026-01-13 | 2026-01-15 | -0.620 |
| interest_rates | 40 | 2026-01-12 | 2026-01-16 | -0.081 |
| commodities | 39 | 2026-01-15 | 2026-01-16 | -0.432 |
| fx | 20 | 2026-01-08 | 2026-01-16 | -0.113 |
| financials | 20 | 2026-01-14 | 2026-01-16 | +0.240 |
| metals | 20 | 2026-01-12 | 2026-01-15 | -0.098 |
| **TOTAL** | **338** | **2026-01-08** | **2026-01-16** | **-0.117** |

**RSS Reality:** We can only pull the last ~20 articles per feed. That's ~8 days of coverage max.

## Current Coverage by Specialist

| Bucket | Articles | With Date | With Sentiment | Date Range | Status |
|--------|----------|-----------|----------------|------------|--------|
| crush | 1,275 | 0 | 1,275 | - | 🔴 Missing dates |
| trump_effect | 434 | 0 | 434 | - | 🔴 Missing dates |
| tariff | 407 | 3 | 407 | 2025-12-15 | 🔴 Missing dates |
| china | 340 | 0 | 340 | - | 🔴 Missing dates |
| volatility | 235 | 0 | 235 | - | 🔴 Missing dates |
| (unlabeled) | 204 | 204 | 100 | 2026-01-12 to 2026-01-16 | ✅ Recent RSS |
| biofuel | 126 | 6 | 126 | 2025-12-15 to 2025-12-16 | 🟡 Partial |
| farm-bill | 68 | 68 | 68 | 2017-08-27 to 2025-11-13 | ✅ Good |
| Logistics | 66 | 0 | 66 | - | 🔴 Missing dates |
| energy | 52 | 1 | 52 | 2025-12-15 | 🔴 Missing dates |
| substitutes | 46 | 0 | 46 | - | 🔴 Missing dates |
| trade | 30 | 30 | 30 | 2024-10-08 to 2025-12-05 | ✅ Good |
| palm | 27 | 0 | 27 | - | 🔴 Missing dates |
| fed | 20 | 0 | 20 | - | 🔴 Missing dates |
| ethanol | 15 | 15 | 15 | 2017-05-08 to 2025-04-29 | ✅ Good |
| fx | 7 | 0 | 7 | - | 🔴 Missing dates |
| general | 7 | 2 | 7 | 2025-12-15 to 2025-12-16 | 🟡 Partial |

## RSS Feed Limits (Reality Check)

**RSS feeds typically provide only the last 20-50 articles per feed.**

This is an RSS protocol limitation, not something we can work around without API access.

### Working RSS Feeds (Can run daily)

| Feed | Specialist | ~Articles/Pull | Status |
|------|------------|----------------|--------|
| grain | crush | ~20 | ✅ Working |
| energy | energy | ~20 | ✅ Working |
| softs | substitutes | ~20 | ✅ Working |
| interest_rates | fed | ~20 | ✅ Working |
| fx | fx | ~20 | ✅ Working |
| financials | fed | ~20 | ✅ Working |
| metals | general | ~20 | ✅ Working |
| commodities | general | ~20 | ✅ Working |
| options_news | volatility | ~20 | ✅ Working |
| etfs | general | ~20 | ✅ Working |

### Search Feeds (Require API - Available Tomorrow)

| Feed | Specialist | Status |
|------|------------|--------|
| china | china | ❌ Needs API |
| trump | trump_effect | ❌ Needs API |
| tariff | tariff | ❌ Needs API |
| vix | volatility | ❌ Needs API |
| legislative | tariff | ❌ Needs API |
| lobbying | general | ❌ Needs API |

## What's Needed for 1-Year Coverage

To get 365 days of historical news per specialist, we need **Barchart API** access.

### API Endpoints Required

```
GET /getHistory.json?symbols=ZL&type=news&startDate=20250116&endDate=20260116
```

### Estimated Article Counts (1 Year)

| Specialist | Est. Daily Articles | Est. 1-Year Total |
|------------|---------------------|-------------------|
| crush/grain | 5-10 | 1,825 - 3,650 |
| energy | 10-20 | 3,650 - 7,300 |
| china | 3-5 | 1,095 - 1,825 |
| trump_effect | 2-5 | 730 - 1,825 |
| tariff | 2-3 | 730 - 1,095 |
| fed | 3-5 | 1,095 - 1,825 |
| volatility | 2-3 | 730 - 1,095 |
| biofuel | 1-2 | 365 - 730 |
| palm | 1-2 | 365 - 730 |
| fx | 2-3 | 730 - 1,095 |
| substitutes | 2-3 | 730 - 1,095 |

**Total Estimated:** 12,000 - 24,000 articles for 1-year coverage

## Action Items

### Today (RSS Only)
- [x] Configure 10 working RSS feeds
- [x] Run initial pull (got ~200 new articles with dates/sentiment)
- [ ] Set up daily cron to pull RSS feeds

### Tomorrow (With API Key)
- [ ] Create `scripts/ingest_barchart_news_api.py`
- [ ] Backfill 1 year for each specialist keyword
- [ ] Keywords to backfill:
  - `soybean oil`, `soybeans`, `crush`
  - `china imports`, `china soybean`
  - `trump tariff`, `trade war`
  - `biofuel`, `biodiesel`, `RFS`
  - `palm oil`, `CPO`
  - `fed rates`, `FOMC`
  - `VIX`, `volatility`
  - `dollar`, `yuan`, `USDBRL`

## Uniformity Gap Analysis

| Big 11 Specialist | Current Articles | Target (1 Year) | Gap |
|-------------------|------------------|-----------------|-----|
| crush | 1,275 | 3,000 | -1,725 |
| china | 340 | 1,500 | -1,160 |
| fx | 7 | 1,000 | -993 |
| fed | 20 | 1,500 | -1,480 |
| tariff | 407 | 1,000 | -593 |
| energy | 52 | 5,000 | -4,948 |
| biofuel | 126 | 500 | -374 |
| palm | 27 | 500 | -473 |
| volatility | 235 | 1,000 | -765 |
| substitutes | 46 | 1,000 | -954 |
| trump_effect | 434 | 1,500 | -1,066 |

**Total Gap: ~14,531 articles needed for uniform 1-year coverage**

## Summary

🔴 **RSS Limitation:** Can only get last ~20 articles per feed per pull  
🟡 **Current State:** 3,398 articles but most missing dates  
🟢 **Tomorrow:** API access enables 1-year historical backfill  

**Bottom line:** We can't get historical news without the API. RSS is forward-looking only.
