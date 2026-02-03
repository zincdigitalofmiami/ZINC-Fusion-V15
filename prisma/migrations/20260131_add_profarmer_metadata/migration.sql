-- Add metadata columns to alt.profarmer_news
-- Extracted from raw_payload JSON for better queryability

-- Add new columns
ALTER TABLE alt.profarmer_news 
  ADD COLUMN IF NOT EXISTS summary TEXT,
  ADD COLUMN IF NOT EXISTS subject VARCHAR(500),
  ADD COLUMN IF NOT EXISTS tags TEXT[],
  ADD COLUMN IF NOT EXISTS topics TEXT[],
  ADD COLUMN IF NOT EXISTS keywords TEXT[],
  ADD COLUMN IF NOT EXISTS categories TEXT[];

-- Populate from raw_payload JSON
UPDATE alt.profarmer_news
SET 
  summary = raw_payload->>'summary',
  subject = COALESCE(raw_payload->>'section', section),
  tags = CASE 
    WHEN raw_payload->'tags' IS NOT NULL 
    THEN ARRAY(SELECT jsonb_array_elements_text(raw_payload->'tags'))
    ELSE ARRAY[]::text[]
  END,
  topics = CASE 
    WHEN raw_payload->'topics' IS NOT NULL 
    THEN ARRAY(SELECT jsonb_array_elements_text(raw_payload->'topics'))
    ELSE ARRAY[]::text[]
  END,
  keywords = CASE 
    WHEN raw_payload->'keywords' IS NOT NULL 
    THEN ARRAY(SELECT jsonb_array_elements_text(raw_payload->'keywords'))
    ELSE ARRAY[]::text[]
  END,
  categories = CASE 
    WHEN raw_payload->'categories' IS NOT NULL 
    THEN ARRAY(SELECT jsonb_array_elements_text(raw_payload->'categories'))
    ELSE ARRAY[]::text[]
  END
WHERE raw_payload IS NOT NULL;

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_profarmer_summary ON alt.profarmer_news USING gin(to_tsvector('english', summary));
CREATE INDEX IF NOT EXISTS idx_profarmer_tags ON alt.profarmer_news USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_profarmer_topics ON alt.profarmer_news USING gin(topics);
CREATE INDEX IF NOT EXISTS idx_profarmer_keywords ON alt.profarmer_news USING gin(keywords);
CREATE INDEX IF NOT EXISTS idx_profarmer_categories ON alt.profarmer_news USING gin(categories);
