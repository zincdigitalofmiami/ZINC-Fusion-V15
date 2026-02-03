-- Remove redundant is_trump_related boolean column from all tables
-- This column was error-prone and redundant since specialist_tags array 
-- is the proper source of truth

-- Drop from all tables that had it
ALTER TABLE alt.econ_news DROP COLUMN IF EXISTS is_trump_related;
ALTER TABLE alt.news_1d DROP COLUMN IF EXISTS is_trump_related;
ALTER TABLE alt.profarmer_news DROP COLUMN IF EXISTS is_trump_related;
ALTER TABLE econ.news_event DROP COLUMN IF EXISTS is_trump_related;
ALTER TABLE features.news_sentiment_1d DROP COLUMN IF EXISTS is_trump_related;

-- Proper way to check for trump_effect articles:
-- SELECT * FROM table_name WHERE 'trump_effect' = ANY(specialist_tags);
