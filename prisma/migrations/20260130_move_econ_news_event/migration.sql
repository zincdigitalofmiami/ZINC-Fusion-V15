-- Move econ.news_event to alt.econ_news_event
ALTER TABLE IF EXISTS econ.news_event SET SCHEMA alt;
ALTER TABLE IF EXISTS alt.news_event RENAME TO econ_news_event;

-- Rename indexes if they exist
ALTER INDEX IF EXISTS alt.idx_econ_news_event_date RENAME TO idx_alt_econ_news_event_date;
ALTER INDEX IF EXISTS alt.idx_econ_news_published_at RENAME TO idx_alt_econ_news_published_at;
ALTER INDEX IF EXISTS alt.idx_econ_news_tags RENAME TO idx_alt_econ_news_tags;
