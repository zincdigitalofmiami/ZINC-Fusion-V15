# Fake Data Audit - January 31, 2026

## 🔍 Comprehensive Data Quality Investigation

### Objective
Hunt for and remove any fake, synthetic, test, or corrupted data across all schemas.

---

## FINDINGS

### ❌ **FOUND: Bad ETF Data (REMOVED)**

#### VXX and UVXY - Reverse Split Artifacts

**Problem**: Yahoo Finance does not properly split-adjust leveraged volatility products.

| Symbol | Rows | Max Price | Real Max Price |
|--------|------|-----------|----------------|
| UVXY | 1,776 | **$276,575** | ~$100 |
| VXX | 2,011 | **$4,416** | ~$60 |

**Example**: UVXY on 2020-03-18 showed $276,575 (should be ~$55 split-adjusted)

**Impact**: Would corrupt volatility models with fake $200k+ price spikes

**Action Taken**: ✅ Deleted all 3,787 rows of VXX and UVXY data

**Alternative**: Use VIXCLS, OVXCLS, GVZCLS from FRED (econ.vol_indices_1d) - these are index values without split issues

---

### ✅ **VERIFIED CLEAN: Futures Data**

Checked major futures symbols for impossible values:

| Symbol | Rows | Price Range | Status |
|--------|------|-------------|--------|
| ZL | 8,418 | $12.90 - $86.55 | ✅ Valid |
| ZS | 14,588 | $237.50 - $1,770.00 | ✅ Valid |
| ZM | 6,505 | $146.00 - $534.60 | ✅ Valid |
| CL | 7,312 | $12.26 - $145.29 | ✅ Valid |
| HG | 7,302 | $0.60 - $6.26 | ✅ Valid |
| HO | 7,301 | $0.50 - $4.61 | ✅ Valid |
| RB | 7,262 | $0.49 - $4.32 | ✅ Valid |

**Checks Performed**:
- ✅ No zero or negative prices
- ✅ No prices > $10,000
- ✅ No duplicates (same date + symbol + price)
- ✅ All prices within historical ranges

---

### ✅ **VERIFIED CLEAN: FRED Economic Data**

Checked interest rates for impossible values:

| Series | Rows | Range | Status |
|--------|------|-------|--------|
| FEDFUNDS | 858 | 0.05% - 19.10% | ✅ Valid |
| DGS10 | 16,002 | 0.52% - 15.84% | ✅ Valid |
| DFF | 26,143 | 0.04% - 22.36% | ✅ Valid |
| SOFR | 1,952 | 0.01% - 5.40% | ✅ Valid |
| T10Y2Y | 12,411 | -2.41% - 2.91% | ✅ Valid |

**Checks Performed**:
- ✅ No extreme values (< -1000% or > 10000%)
- ✅ All within historical ranges
- ✅ No future dates

---

### ✅ **VERIFIED CLEAN: ETF Data (Remaining)**

After removing VXX/UVXY, remaining 24 ETFs all validated:

**No issues found**:
- ✅ No test/fake/mock/dummy symbols
- ✅ All prices within reasonable ranges
- ✅ No zero volume anomalies (sparse volume is expected for some ETFs)
- ✅ No future dates

---

### ✅ **VERIFIED CLEAN: News/Alt Data**

**Source Field Audit**:
- ✅ No sources named "test", "fake", "synthetic", "mock", "dummy"
- ✅ All sources are legitimate:
  - fred_blog (FRED)
  - whitehouse_* (WhiteHouse.gov)
  - profarmer (ProFarmer subscription)
  - farmdoc_rins_rss (University of Illinois)
  - cbp_rss (US Customs)
  - aei_rss (American Enterprise Institute)
  - ice_factsheets (ICE)

---

### ✅ **VERIFIED CLEAN: No Future Data**

Checked for data with dates > CURRENT_DATE:
- ✅ mkt.futures_1d: 0 future rows
- ✅ mkt.etf_1d: 0 future rows
- ✅ econ.rates_1d: 0 future rows

---

## ACTIONS TAKEN

### 1. Deleted Bad Data ✅
```sql
DELETE FROM mkt.etf_1d WHERE symbol IN ('VXX', 'UVXY');
-- Removed: 3,787 rows
-- Reason: Reverse split artifacts creating fake $200k+ prices
```

### 2. Updated Documentation ✅
- Created `FAKE_DATA_AUDIT_20260131.md`
- Created `scripts/fix_etf_reverse_splits.sql`
- Created `scripts/check_etf_fake_data.js`

### 3. Validation Script Created ✅
Run `node scripts/check_etf_fake_data.js` to verify ETF data quality

---

## DATA QUALITY RULES ESTABLISHED

### What is NOT Fake Data

1. **Split-Adjusted Prices** - Yahoo Finance returns split-adjusted by default
   - Example: XLE in 2015 shows ~$40 (was ~$80 pre-split)
   - ✅ This is CORRECT for backtesting
   
2. **Historical Low Prices** - Some commodities/ETFs had very low prices
   - Example: CL hit $12.26 (April 2020 COVID crash)
   - ✅ This is REAL historical data

3. **High Volatility** - Extreme moves during crises
   - Example: VIX > 80 in March 2020
   - ✅ This is REAL market volatility

### What IS Fake/Bad Data

1. **Reverse Split Artifacts** - Products with 100+ reverse splits
   - VXX, UVXY showing $4k - $276k prices
   - ❌ Yahoo does not adjust these correctly
   - **Action**: Deleted

2. **Future Dates** - Data dated after today
   - None found ✅

3. **Test/Mock Sources** - Source fields containing "test", "fake", etc.
   - None found ✅

4. **Impossible Values** - Prices < 0 or absurdly high
   - None found in futures/rates ✅
   - Found in UVXY/VXX ❌ - Deleted

---

## REMAINING VOLATILITY PROXIES

After removing VXX/UVXY, volatility specialist uses:

### From FRED (econ.vol_indices_1d) - RECOMMENDED
- ✅ VIXCLS - S&P 500 VIX Index
- ✅ OVXCLS - Crude Oil VIX Index  
- ✅ GVZCLS - Gold VIX Index
- ✅ VXVCLS - VIX 3-Month
- ✅ VXEEMCLS - Emerging Markets VIX

### From ETFs (mkt.etf_1d) - FOR MARKET STRUCTURE ONLY
- ✅ SPY - S&P 500 (volatility proxy via returns)
- ✅ QQQ - Nasdaq (volatility proxy via returns)

**Note**: FRED VIX indices are superior - they're index values, not ETFs, so no split issues.

---

## VERIFICATION COMMANDS

### Check for bad data patterns
```sql
-- Check for extreme ETF prices
SELECT symbol, event_date, close
FROM mkt.etf_1d
WHERE close > 1000
ORDER BY close DESC;

-- Check for future dates
SELECT COUNT(*) 
FROM mkt.futures_1d 
WHERE event_date > CURRENT_DATE;

-- Check for zero/negative prices
SELECT symbol, event_date, close
FROM mkt.futures_1d
WHERE close <= 0;
```

---

## NEXT STEPS FOR DATA QUALITY

### Recommended Additional Checks
1. ✅ ETF reverse splits - DONE (VXX, UVXY removed)
2. Check options data for impossible Greeks
3. Check WASDE for negative production values
4. Check CFTC for impossible positioning values
5. Validate all ingestion_batch_id references

### Monitoring
- Set up alerts for extreme price moves (> 50% in 1 day)
- Monitor for future dates in ingestion
- Check for duplicate row_hash values

---

**Status**: ✅ First pass complete - VXX/UVXY bad data removed  
**Next**: Continue hunting through options, supply, positioning data  
**Impact**: Prevented $276k fake prices from corrupting volatility models
