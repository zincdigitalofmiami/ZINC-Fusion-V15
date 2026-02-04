# alt.news_1d Restructuring Proposal

## Current State Analysis

### Content Breakdown (1,301 rows)
- **FRED Blog**: 1,131 rows (87%) - Federal Reserve economic research/analysis
- **WhiteHouse**: 96 rows (7%) - Executive orders, proclamations, memoranda, briefings
- **Other Sources**: 74 rows (6%) - ICE, AEI, CBP, FarmDoc

### Problem
The table name `alt.news_1d` suggests general news, but it's actually:
- 87% Federal Reserve economic research
- 7% Presidential/executive actions
- 6% Miscellaneous policy sources

This is confusing and doesn't follow our schema naming conventions.

## Proposed Restructuring

### Option 1: Split by Source Type (RECOMMENDED)

Create three focused tables:

#### 1.1 `alt.fed_research` (FRED Blog - 1,131 rows)
```sql
-- Federal Reserve economic research and analysis
-- Source: FRED blog (St. Louis Fed)
-- Use case: FED specialist, economic context
```

#### 1.2 `alt.executive_actions` (WhiteHouse - 96 rows)
```sql
-- Presidential documents: Executive Orders, Proclamations, Memoranda
-- Source: whitehouse.gov
-- Use case: TRUMP_EFFECT specialist, policy event detection
```

#### 1.3 `alt.policy_news` (Other - 74 rows)
```sql
-- Policy news from ICE, CBP, AEI, FarmDoc
-- Source: Multiple federal agencies + think tanks
-- Use case: Multi-specialist (tariff, biofuel, immigration)
```

**Benefits**:
- Clear semantic separation
- Easier to maintain specialist routing
- Each table serves specific specialist needs
- Follows institutional schema pattern

### Option 2: Keep Unified with Better Naming

Rename `alt.news_1d` → `alt.policy_research` and keep all sources together.

**Benefits**:
- Simple migration
- All policy-related content in one place

**Drawbacks**:
- Mixed semantics (research vs. actions vs. news)
- Harder to maintain

## Recommendation

**Go with Option 1**: Split into three tables

### Migration Plan

```sql
-- 1. Create new tables
CREATE TABLE alt.fed_research (
  -- Same schema as news_1d but optimized for Fed content
);

CREATE TABLE alt.executive_actions (
  -- Optimized for presidential documents
  -- Add: document_number, action_type, agencies_affected
);

CREATE TABLE alt.policy_news (
  -- General policy news
);

-- 2. Migrate data
INSERT INTO alt.fed_research 
SELECT * FROM alt.news_1d WHERE source = 'fred_blog';

INSERT INTO alt.executive_actions
SELECT * FROM alt.news_1d WHERE source LIKE 'whitehouse_%';

INSERT INTO alt.policy_news
SELECT * FROM alt.news_1d WHERE source NOT LIKE 'whitehouse_%' AND source != 'fred_blog';

-- 3. Update specialist tags to point to new tables

-- 4. Drop alt.news_1d after verification
```

### Specialist Routing After Split

- **FED Specialist** → `alt.fed_research` (FRED blog analysis)
- **TRUMP_EFFECT Specialist** → `alt.executive_actions` (Presidential actions)
- **TARIFF Specialist** → `alt.executive_actions` + `alt.policy_news`
- **BIOFUEL Specialist** → `alt.policy_news` (FarmDoc RIN analysis)

### Current Specialist Tags in alt.news_1d

Based on current tagging:
```
trump_effect: 147 articles (mostly WhiteHouse)
fx: 1 article
biofuel: 24 articles (FarmDoc)
energy: 11 articles
china: 3 articles
tariff: 65 articles (WhiteHouse trade policy)
fed: 7 articles (FRED blog)
```

## Decision Point

Should we:
1. **✅ Split into 3 focused tables** (fed_research, executive_actions, policy_news)
2. **Keep unified** but rename to `alt.policy_research`
3. **Keep as-is** but document that it's multi-source

**My recommendation**: Option 1 - Split for clarity and proper specialist routing.

What do you prefer?
