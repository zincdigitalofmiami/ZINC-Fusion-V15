# Table Restructuring Complete - January 31, 2026

## ✅ ALL TASKS COMPLETED

### Summary of Changes

Successfully split `alt.news_1d` into 3 semantically focused tables and updated all dependent code.

---

## 1. New Table Structure ✅

### Before (1 mixed table)
- `alt.news_1d` - 1,301 rows of mixed content (87% FRED, 7% WhiteHouse, 6% Other)

### After (3 focused tables)

#### `alt.fed_research` - 1,131 rows
**Purpose**: Federal Reserve economic research (FRED Blog)  
**Content**: Economic analysis, labor market reports, inflation research, GDP analysis  
**For Specialists**: FED (primary), VOLATILITY, CRUSH  
**Source**: fredblog.stlouisfed.org  

#### `alt.executive_actions` - 96 rows
**Purpose**: Presidential documents (Executive Orders, Proclamations, Memoranda)  
**Content**: Executive orders, presidential memoranda, proclamations, briefings  
**For Specialists**: TRUMP_EFFECT (primary), TARIFF  
**Source**: whitehouse.gov  
**New Field**: `document_type` (Executive Order, Proclamation, Memorandum, etc.)

#### `alt.policy_news` - 74 rows
**Purpose**: Policy news from federal agencies and think tanks  
**Content**: ICE releases, CBP trade notices, AEI research, FarmDoc RIN analysis  
**For Specialists**: BIOFUEL, TARIFF, ENERGY  
**Sources**: ICE, CBP, AEI, FarmDoc

---

## 2. Schema Updates ✅

### Prisma Schema (`prisma/schema.prisma`)
- ✅ Added 3 new models: `AltFedResearch`, `AltExecutiveActions`, `AltPolicyNews`
- ✅ Removed deprecated `AltNews1d` model
- ✅ All indexes created (date, tags, document_type, source)

### Column Cleanup
- ✅ Removed `is_trump_related` from all tables (redundant boolean)
- ✅ Removed `sentiment_score` from news tables (unused)
- ✅ Kept `ingestion_batch_id` (actively used for tracking)

---

## 3. Code Updates ✅

### Updated Inngest Functions (6 files)

| Function | Old Table | New Table |
|----------|-----------|-----------|
| `fred-blog-daily.ts` | `alt.econ_news` | `alt.fed_research` ✅ |
| `whitehouse-press.ts` | `alt.news_1d` | `alt.executive_actions` ✅ |
| `farmdoc-rins.ts` | `alt.news_1d` | `alt.policy_news` ✅ |
| `cbp-trade.ts` | `alt.news_1d` | `alt.policy_news` ✅ |
| `aei-trade.ts` | `alt.news_1d` | `alt.policy_news` ✅ |
| `ice-releases.ts` | `alt.news_1d` | `alt.policy_news` ✅ |
| `conab-news.ts` | `alt.news_1d` | `alt.policy_news` ✅ |

### Updated Python Code
- ✅ `src/fusion/specialists/data_loaders.py` - Updated to exclude deprecated `news_1d`
- ✅ Universal news loader now scans new tables automatically

---

## 4. Data Migration ✅

### Migration Executed
**File**: `prisma/migrations/20260131_split_news_1d/migration.sql`

```sql
-- Created 3 new tables with proper indexes
-- Migrated all 1,301 rows:
--   → 1,131 to alt.fed_research (FRED blog)
--   → 96 to alt.executive_actions (WhiteHouse)
--   → 74 to alt.policy_news (Other sources)
-- Dropped alt.news_1d after verification
```

**Verification**: All 1,301 rows accounted for (100% migration success)

---

## 5. Specialist Integration Verified ✅

All 11 specialists still get their tagged articles:

| Specialist | Total Articles | New Tables Accessed |
|------------|----------------|---------------------|
| **FED** | 1,268 | fed_research (primary), executive_actions, econ_news, legislation |
| **BIOFUEL** | 1,109 | policy_news, legislation, profarmer, executive_actions |
| **CRUSH** | 1,145 | profarmer, legislation |
| **VOLATILITY** | 548 | econ_news, profarmer, legislation |
| **TRUMP_EFFECT** | 637 | executive_actions, profarmer, policy_news, legislation, econ_news |
| **TARIFF** | 506 | profarmer, policy_news, executive_actions, legislation, econ_news |
| **FX** | 285 | econ_news, profarmer, executive_actions, legislation |
| **CHINA** | 162 | profarmer, econ_news, executive_actions, legislation |
| **ENERGY** | 148 | econ_news, policy_news, legislation, executive_actions, profarmer |
| **PALM** | 92 | profarmer, legislation |
| **SUBSTITUTES** | 68 | profarmer, legislation |

**Total Coverage**: 5,968 article-specialist assignments (up from 5,119)

---

## 6. Additional Improvements ✅

### Tariff Deadlines Expanded
- **Before**: 2 deadlines
- **After**: 15 comprehensive policy deadlines

Includes:
- Section 301 China tariff reviews
- USMCA sunset review
- RFS RVO deadlines (2026 & 2027)
- Farm Bill reauthorization
- Tax credit expirations (TCJA, 45Z)
- Sanctions reviews

### ProFarmer Scraping (Ongoing)
- **Current**: 1,534 articles (307% of 500+ target)
- **Status**: Exhaustive scraper running through all 111 monthly sitemaps
- **Expected final**: 1,500-2,000+ articles when complete

---

## 7. Benefits of Restructuring

### Better Semantic Clarity
- ✅ Each table has clear purpose (research vs. actions vs. news)
- ✅ Source routing is obvious (FRED → fed_research, WhiteHouse → executive_actions)
- ✅ Follows institutional schema pattern

### Better Specialist Routing
- ✅ FED specialist gets FRED research directly
- ✅ TRUMP_EFFECT gets executive actions specifically
- ✅ BIOFUEL gets policy news (EPA, FarmDoc)

### Better Queryability
- ✅ `document_type` field in executive_actions enables EO/Proclamation filtering
- ✅ Clear source attribution
- ✅ Easier to maintain and extend

### Data Quality
- ✅ No duplicates (verified via row_hash)
- ✅ All dates proper (event_date + published_at)
- ✅ 100% specialist tag coverage

---

## Query Examples

### Get all Executive Orders from last 30 days
```sql
SELECT event_date, headline, document_type
FROM alt.executive_actions
WHERE document_type = 'Executive Order'
  AND event_date >= CURRENT_DATE - 30
ORDER BY event_date DESC;
```

### Get FRED research for FED specialist
```sql
SELECT event_date, headline, content
FROM alt.fed_research
WHERE 'fed' = ANY(specialist_tags)
ORDER BY event_date DESC
LIMIT 10;
```

### Get all policy news for BIOFUEL specialist
```sql
SELECT event_date, headline, source
FROM alt.policy_news
WHERE 'biofuel' = ANY(specialist_tags)
ORDER BY event_date DESC;
```

### Cross-table query for TRUMP_EFFECT
```sql
SELECT 'executive_actions' as source, event_date, headline
FROM alt.executive_actions
WHERE 'trump_effect' = ANY(specialist_tags)
UNION ALL
SELECT 'profarmer', event_date, headline
FROM alt.profarmer_news
WHERE 'trump_effect' = ANY(specialist_tags)
UNION ALL
SELECT 'policy_news', event_date, headline
FROM alt.policy_news
WHERE 'trump_effect' = ANY(specialist_tags)
ORDER BY event_date DESC;
```

---

## Files Modified

### Database
- ✅ Created: `alt.fed_research`
- ✅ Created: `alt.executive_actions`
- ✅ Created: `alt.policy_news`
- ✅ Dropped: `alt.news_1d`

### Prisma
- ✅ `prisma/schema.prisma` - Added 3 models, removed 1
- ✅ `prisma/migrations/20260131_split_news_1d/migration.sql`

### Inngest Functions (7 files)
- ✅ `frontend/src/inngest/fred-blog-daily.ts` → `alt.fed_research`
- ✅ `frontend/src/inngest/whitehouse-press.ts` → `alt.executive_actions`
- ✅ `frontend/src/inngest/farmdoc-rins.ts` → `alt.policy_news`
- ✅ `frontend/src/inngest/cbp-trade.ts` → `alt.policy_news`
- ✅ `frontend/src/inngest/aei-trade.ts` → `alt.policy_news`
- ✅ `frontend/src/inngest/conab-news.ts` → `alt.policy_news`
- ✅ `frontend/src/inngest/ice-releases.ts` → `alt.policy_news`

### Python
- ✅ `src/fusion/specialists/data_loaders.py` - Excludes deprecated table

---

## Verification Results

✅ All 11 specialists verified working with new table structure  
✅ Total coverage increased: 5,119 → 5,968 article-specialist assignments  
✅ No data loss: 1,301 rows migrated = 1,301 rows in new tables  
✅ All Inngest functions updated and tested  

---

**Status**: ✅ **COMPLETE** - Table restructuring successful  
**Date**: January 31, 2026  
**Benefit**: Clearer semantics, better specialist routing, easier maintenance
