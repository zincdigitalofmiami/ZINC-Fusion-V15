-- Split alt.news_1d into 3 focused tables for better semantic clarity
-- 
-- alt.news_1d breakdown:
-- - 87% FRED Blog (Federal Reserve economic research)
-- - 7% WhiteHouse (Executive orders, proclamations, etc.)
-- - 6% Other policy sources (ICE, CBP, AEI, FarmDoc)

-- ============================================================================
-- 1. CREATE NEW TABLES
-- ============================================================================

-- 1.1 FRED Economic Research (Federal Reserve Blog)
CREATE TABLE IF NOT EXISTS alt.fed_research (
  id                SERIAL PRIMARY KEY,
  article_id        VARCHAR(100),
  event_date        DATE NOT NULL,
  published_at      TIMESTAMPTZ,
  headline          TEXT NOT NULL,
  content           TEXT,
  url               TEXT,
  author            VARCHAR(200),
  source            VARCHAR(100),
  zl_sentiment      VARCHAR(50),
  specialist_tags   TEXT[] NOT NULL DEFAULT '{}',
  ingested_at       TIMESTAMPTZ DEFAULT NOW(),
  knowledge_time    TIMESTAMPTZ DEFAULT NOW(),
  row_hash          VARCHAR(64),
  raw_payload       JSONB,
  ingestion_batch_id UUID
);

CREATE INDEX idx_fed_research_date ON alt.fed_research(event_date);
CREATE INDEX idx_fed_research_tags ON alt.fed_research USING gin(specialist_tags);
CREATE UNIQUE INDEX idx_fed_research_hash ON alt.fed_research(row_hash) WHERE row_hash IS NOT NULL;

-- 1.2 Executive Actions (WhiteHouse Presidential Documents)
CREATE TABLE IF NOT EXISTS alt.executive_actions (
  id                SERIAL PRIMARY KEY,
  article_id        VARCHAR(100),
  event_date        DATE NOT NULL,
  published_at      TIMESTAMPTZ,
  headline          TEXT NOT NULL,
  content           TEXT,
  url               TEXT,
  author            VARCHAR(200),
  source            VARCHAR(100),
  document_type     VARCHAR(100), -- executiveOrder, proclamation, memorandum, etc.
  zl_sentiment      VARCHAR(50),
  specialist_tags   TEXT[] NOT NULL DEFAULT '{}',
  ingested_at       TIMESTAMPTZ DEFAULT NOW(),
  knowledge_time    TIMESTAMPTZ DEFAULT NOW(),
  row_hash          VARCHAR(64),
  raw_payload       JSONB,
  ingestion_batch_id UUID
);

CREATE INDEX idx_executive_actions_date ON alt.executive_actions(event_date);
CREATE INDEX idx_executive_actions_tags ON alt.executive_actions USING gin(specialist_tags);
CREATE INDEX idx_executive_actions_type ON alt.executive_actions(document_type);
CREATE UNIQUE INDEX idx_executive_actions_hash ON alt.executive_actions(row_hash) WHERE row_hash IS NOT NULL;

-- 1.3 Policy News (Other sources: ICE, CBP, AEI, FarmDoc)
CREATE TABLE IF NOT EXISTS alt.policy_news (
  id                SERIAL PRIMARY KEY,
  article_id        VARCHAR(100),
  event_date        DATE NOT NULL,
  published_at      TIMESTAMPTZ,
  headline          TEXT NOT NULL,
  content           TEXT,
  url               TEXT,
  author            VARCHAR(200),
  source            VARCHAR(100),
  zl_sentiment      VARCHAR(50),
  specialist_tags   TEXT[] NOT NULL DEFAULT '{}',
  ingested_at       TIMESTAMPTZ DEFAULT NOW(),
  knowledge_time    TIMESTAMPTZ DEFAULT NOW(),
  row_hash          VARCHAR(64),
  raw_payload       JSONB,
  ingestion_batch_id UUID
);

CREATE INDEX idx_policy_news_date ON alt.policy_news(event_date);
CREATE INDEX idx_policy_news_source ON alt.policy_news(source);
CREATE INDEX idx_policy_news_tags ON alt.policy_news USING gin(specialist_tags);
CREATE UNIQUE INDEX idx_policy_news_hash ON alt.policy_news(row_hash) WHERE row_hash IS NOT NULL;

-- ============================================================================
-- 2. MIGRATE DATA
-- ============================================================================

-- 2.1 Migrate FRED Blog
INSERT INTO alt.fed_research 
  (article_id, event_date, published_at, headline, content, url, author, source, 
   zl_sentiment, specialist_tags, ingested_at, knowledge_time, row_hash, raw_payload, ingestion_batch_id)
SELECT 
  article_id, event_date, published_at, headline, content, url, author, source,
  zl_sentiment, specialist_tags, ingested_at, knowledge_time, row_hash, raw_payload, ingestion_batch_id
FROM alt.news_1d
WHERE source = 'fred_blog';

-- 2.2 Migrate WhiteHouse (extract document type from source)
INSERT INTO alt.executive_actions
  (article_id, event_date, published_at, headline, content, url, author, source, document_type,
   zl_sentiment, specialist_tags, ingested_at, knowledge_time, row_hash, raw_payload, ingestion_batch_id)
SELECT 
  article_id, event_date, published_at, headline, content, url, author, source,
  -- Extract document type from source name
  CASE 
    WHEN source LIKE '%executiveOrders%' THEN 'Executive Order'
    WHEN source LIKE '%proclamations%' THEN 'Proclamation'
    WHEN source LIKE '%memoranda%' THEN 'Presidential Memorandum'
    WHEN source LIKE '%briefings%' THEN 'Press Briefing'
    WHEN source LIKE '%factSheets%' THEN 'Fact Sheet'
    WHEN source LIKE '%remarks%' THEN 'Remarks'
    ELSE 'Other'
  END as document_type,
  zl_sentiment, specialist_tags, ingested_at, knowledge_time, row_hash, raw_payload, ingestion_batch_id
FROM alt.news_1d
WHERE source LIKE 'whitehouse_%';

-- 2.3 Migrate Other policy sources
INSERT INTO alt.policy_news
  (article_id, event_date, published_at, headline, content, url, author, source,
   zl_sentiment, specialist_tags, ingested_at, knowledge_time, row_hash, raw_payload, ingestion_batch_id)
SELECT 
  article_id, event_date, published_at, headline, content, url, author, source,
  zl_sentiment, specialist_tags, ingested_at, knowledge_time, row_hash, raw_payload, ingestion_batch_id
FROM alt.news_1d
WHERE source != 'fred_blog' AND source NOT LIKE 'whitehouse_%';

-- ============================================================================
-- 3. VERIFICATION
-- ============================================================================

-- Verify row counts match
DO $$
DECLARE
  orig_count INTEGER;
  new_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO orig_count FROM alt.news_1d;
  SELECT 
    (SELECT COUNT(*) FROM alt.fed_research) +
    (SELECT COUNT(*) FROM alt.executive_actions) +
    (SELECT COUNT(*) FROM alt.policy_news)
  INTO new_count;
  
  RAISE NOTICE 'Original alt.news_1d: % rows', orig_count;
  RAISE NOTICE 'New tables total: % rows', new_count;
  
  IF orig_count != new_count THEN
    RAISE EXCEPTION 'Row count mismatch! Original: %, New: %', orig_count, new_count;
  END IF;
  
  RAISE NOTICE 'Migration verified: All rows migrated successfully';
END $$;

-- Show summary
SELECT 
  'alt.fed_research' as table_name,
  COUNT(*) as rows,
  MIN(event_date) as earliest,
  MAX(event_date) as latest
FROM alt.fed_research
UNION ALL
SELECT 
  'alt.executive_actions',
  COUNT(*),
  MIN(event_date),
  MAX(event_date)
FROM alt.executive_actions
UNION ALL
SELECT 
  'alt.policy_news',
  COUNT(*),
  MIN(event_date),
  MAX(event_date)
FROM alt.policy_news
ORDER BY rows DESC;
