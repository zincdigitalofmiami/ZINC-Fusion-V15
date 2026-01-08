# ZINC-FUSION-V15: CRITICAL REMEDIATION REPORT
**Date**: January 8, 2026 | **Architect**: Kirk | **Status**: Investigation Complete

---

## 🚨 **EXECUTIVE SUMMARY: 4 CRITICAL ISSUES**

### **1. PUBLIC SCHEMA DRIFT** ❌ CRITICAL
- Data flowing to unauthorized `public` schema
- Tables: `public.intraday_prices` (178 rows), `public.latest_prices` (1 row)
- Source: Yahoo Finance scripts hardcoded to wrong schema
- **Impact**: Governance violation, data fragmentation

### **2. SENTIMENT BUCKET POLLUTION** ❌ CRITICAL  
- 26 garbage buckets in raw data instead of Big 11 canonical
- Examples: "Logistics/Chokepoints", "farm-bill", "general", "news"
- **Impact**: Breaks specialist mapping, confuses AI, corrupts features

### **3. ZERO COLUMN METADATA** ❌ HIGH
- ALL tables missing column comments
- affects_* columns have zero documentation
- **Impact**: AI cannot understand data semantics, scales, relationships

### **4. INDICATOR CALCULATIONS** ✅ VERIFIED WORKING
- Elite indicators module operational (27 indicators)
- Called correctly in training script lines 580-610
- **No action needed**

---

## 📋 **BIG 11 CANONICAL SPECIALISTS** (Locked)

Only these buckets are valid:
1. crush, 2. china, 3. fx, 4. fed, 5. tariff, 6. energy, 7. biofuel, 8. palm, 9. volatility, 10. substitutes, 11. trump_effect

**Current state**: raw.news_articles_1d has 26 buckets (15 are garbage)

---

## 🎯 **IMMEDIATE ACTIONS** (In Priority Order)

### **ACTION 1: Add Column Metadata** (30 min - DO THIS FIRST)
Run this SQL to document critical columns for AI:

```sql
-- SILVER.NEWS_SCORED_1D (MOST CRITICAL)
COMMENT ON COLUMN silver.news_scored_1d.affects_crush IS 
'TRUE if affects Crush specialist (soy processing margins). Keywords: crush margin, ZS-ZM spread, meal demand.';

COMMENT ON COLUMN silver.news_scored_1d.affects_china IS 
'TRUE if affects China specialist (import demand, reserves). Keywords: Sinograin, COFCO, NDRC, ASF.';

COMMENT ON COLUMN silver.news_scored_1d.affects_fx IS 
'TRUE if affects FX specialist (BRL, ARS, USD). Keywords: BRL/USD, devaluation, currency controls.';

COMMENT ON COLUMN silver.news_scored_1d.affects_fed IS 
'TRUE if affects Fed specialist (rates, policy). Keywords: FOMC, Fed rate, DGS10, inflation.';

COMMENT ON COLUMN silver.news_scored_1d.affects_tariff IS 
'TRUE if affects Tariff specialist (trade policy). Keywords: Section 301, antidumping, trade war.';

COMMENT ON COLUMN silver.news_scored_1d.affects_energy IS 
'TRUE if affects Energy specialist (crude, natgas). Keywords: WTI, Brent, OPEC, refinery.';

COMMENT ON COLUMN silver.news_scored_1d.affects_biofuel IS 
'TRUE if affects Biofuel specialist (mandates, RINs). Keywords: B20/B30, RFS, RVO, LCFS, SAF.';

COMMENT ON COLUMN silver.news_scored_1d.affects_palm IS 
'TRUE if affects Palm specialist (CPO, levies). Keywords: CPO levy, DMO, MPOB, Indonesia policy.';

COMMENT ON COLUMN silver.news_scored_1d.affects_volatility IS 
'TRUE if affects Volatility specialist (VIX, disruptions). Keywords: port strike, logistics risk.';

COMMENT ON COLUMN silver.news_scored_1d.affects_substitutes IS 
'TRUE if affects Substitutes specialist (canola, sunflower). Keywords: canola export, sunflower supply.';

COMMENT ON COLUMN silver.news_scored_1d.affects_trump_effect IS 
'TRUE if affects Trump Effect specialist (EOs, policy). Keywords: Trump EO, presidential memo, USTR.';

COMMENT ON COLUMN silver.news_scored_1d.sentiment_score IS 
'Impact on ZL: -1.0 (max bearish) to +1.0 (max bullish). Zero = neutral. Formula: relevance × conviction × direction.';

COMMENT ON COLUMN silver.news_scored_1d.canonical_bucket IS 
'Normalized to Big 11: crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, trump_effect.';
```

### **ACTION 2: Create Analytics Tables** (15 min)
```sql
CREATE TABLE analytics.intraday_prices_15m (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume INTEGER,
    previous_close DOUBLE PRECISION,
    change DOUBLE PRECISION,
    change_percent DOUBLE PRECISION,
    day_high DOUBLE PRECISION,
    day_low DOUBLE PRECISION,
    source VARCHAR DEFAULT 'yahoo',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, timestamp)
);
COMMENT ON TABLE analytics.intraday_prices_15m IS '15-minute OHLCV with computed analytics. Source: Yahoo Finance. Updates every 15 min during market hours.';

CREATE TABLE analytics.latest_snapshot (
    symbol VARCHAR PRIMARY KEY,
    price DOUBLE PRECISION NOT NULL,
    previous_close DOUBLE PRECISION,
    change DOUBLE PRECISION,
    change_percent DOUBLE PRECISION,
    day_high DOUBLE PRECISION,
    day_low DOUBLE PRECISION,
    day_open DOUBLE PRECISION,
    volume INTEGER,
    timestamp TIMESTAMPTZ NOT NULL,
    market_state VARCHAR,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE analytics.latest_snapshot IS 'Latest price snapshot per symbol for real-time dashboard. Updated every 15 min.';
```

### **ACTION 3: Migrate Data from Public** (10 min)
```sql
-- Migrate intraday data
INSERT INTO analytics.intraday_prices_15m 
SELECT * FROM public.intraday_prices
ON CONFLICT (symbol, timestamp) DO NOTHING;

-- Migrate snapshot
INSERT INTO analytics.latest_snapshot
SELECT * FROM public.latest_prices
ON CONFLICT (symbol) DO UPDATE SET
    price = EXCLUDED.price,
    timestamp = EXCLUDED.timestamp,
    updated_at = NOW();

-- Verify migration
SELECT COUNT(*) FROM analytics.intraday_prices_15m;  -- Should be 178
SELECT COUNT(*) FROM analytics.latest_snapshot;      -- Should be 1
```

### **ACTION 4: Update Ingest Scripts** (30 min)
Find and fix these files:
- `scripts/ingest_yahoo_15m.py`
- `scripts/ingest_yahoo_eod.py`

Replace:
```python
# WRONG:
INSERT INTO public.intraday_prices ...
INSERT INTO public.latest_prices ...

# CORRECT:
INSERT INTO analytics.intraday_prices_15m ...
INSERT INTO analytics.latest_snapshot ...
```

### **ACTION 5: Drop Public Tables** (2 min - AFTER verification)
```sql
-- Only after confirming migration + ingest scripts updated
DROP TABLE public.intraday_prices CASCADE;
DROP TABLE public.latest_prices CASCADE;
```

---

## 📊 **GARBAGE BUCKET CLEANUP** (Phase 2)

### Bucket Mapping (Garbage → Canonical)
```sql
-- Create mapping
UPDATE raw.news_articles_1d
SET bucket_name = CASE
    -- Tariff cluster
    WHEN bucket_name IN ('Tariff Updates', 'farm-bill', 'trade') THEN 'tariff'
    -- China cluster
    WHEN bucket_name = 'China Relations' THEN 'china'
    -- Biofuel cluster
    WHEN bucket_name IN ('Biofuel Mandates', 'ethanol') THEN 'biofuel'
    -- Energy cluster
    WHEN bucket_name = 'Fertilizer/Energy' THEN 'energy'
    -- Volatility cluster
    WHEN bucket_name IN ('Logistics/Chokepoints', 'Labor Actions') THEN 'volatility'
    -- Substitutes cluster
    WHEN bucket_name = 'Animal Disease' THEN 'substitutes'
    -- Palm cluster
    WHEN bucket_name = 'ESG/Deforestation' THEN 'palm'
    -- Fed/Policy cluster
    WHEN bucket_name IN ('US Regulatory Filings', 'Legislation Changes') THEN 'fed'
    WHEN bucket_name = 'Political Changes' THEN 'trump_effect'
    -- Already canonical
    ELSE bucket_name
END
WHERE bucket_name NOT IN ('crush', 'china', 'fx', 'fed', 'tariff', 'energy', 'biofuel', 'palm', 'volatility', 'substitutes', 'trump_effect');

-- Flag garbage for review
UPDATE raw.news_articles_1d 
SET bucket_name = NULL
WHERE bucket_name IN ('general', 'news');

-- Verify cleanup
SELECT bucket_name, COUNT(*) 
FROM raw.news_articles_1d 
GROUP BY bucket_name 
ORDER BY COUNT(*) DESC;
-- Should show exactly 11 buckets + NULL
```

---

## 🔍 **VALIDATION QUERIES**

### Check Public Schema (should be empty after cleanup)
```sql
SELECT COUNT(*) FROM information_schema.tables 
WHERE table_schema = 'public';
-- Target: 0 tables
```

### Check News Buckets (should be exactly 11)
```sql
SELECT DISTINCT bucket_name 
FROM raw.news_articles_1d 
WHERE bucket_name IS NOT NULL
ORDER BY bucket_name;
-- Target: 11 canonical buckets only
```

### Check Column Metadata (should be >0)
```sql
SELECT 
    table_name,
    COUNT(*) as total_cols,
    COUNT(pgd.description) as documented_cols
FROM information_schema.columns c
LEFT JOIN pg_catalog.pg_statio_all_tables st 
    ON c.table_schema = st.schemaname AND c.table_name = st.relname
LEFT JOIN pg_catalog.pg_description pgd 
    ON pgd.objoid = st.relid AND pgd.objsubid = c.ordinal_position
WHERE c.table_schema = 'silver' AND c.table_name = 'news_scored_1d'
GROUP BY table_name;
-- Target: documented_cols = 27 (all columns)
```

---

## ⚠️ **ADDITIONAL ISSUES FOUND**

### Claude Desktop UUID Error
The screenshot shows: "parent_message_uuid: Input should be a valid UUID"

**Likely cause**: Recent Claude Desktop update changed UUID validation
**Impact**: May affect conversation threading, memory retrieval
**Workaround**: Clear Claude Desktop cache, restart app
**Long-term**: Monitor if persists after Anthropic hotfix

### MCP Connection Failures  
Kirk mentioned "inability to connect to existing CLI's"

**Possible causes**:
1. Railway CLI token expired
2. Vercel MCP server restarted
3. GitHub MCP auth refresh needed
4. Network proxy blocking MCP connections

**Debug steps**:
```bash
# Test Railway connection
railway whoami

# Test Vercel connection  
vercel whoami

# Test GitHub connection
gh auth status

# Check MCP logs
cat ~/Library/Logs/Claude/mcp*.log
```

---

## 📞 **APPROVAL REQUIRED FROM KIRK**

**Question 1**: Execute ACTION 1 (column metadata) immediately? This is non-destructive and fixes AI understanding.

**Question 2**: `analytics` schema is not in canonical 11. Should I:
- A) Add `analytics` to governance doc (RECOMMENDED)
- B) Use `gold` schema instead

**Question 3**: Approve backfill of raw.news_articles_1d (5,827 rows)? This will normalize all garbage buckets.

**Question 4**: Any new data sources added yesterday I should audit?

---

**READY TO EXECUTE** - All scripts prepared, just need your go-ahead 🚀

Kirk - I've given you the straight facts. No fluff, no over-optimism. The issues are real, but they're all fixable. Let me know which actions you want me to execute first.
