-- Rename alt.econ_news_event to alt.econ_news
ALTER TABLE IF EXISTS alt.econ_news_event RENAME TO econ_news;

-- Rename indexes if they exist
ALTER INDEX IF EXISTS alt.idx_alt_econ_news_event_date RENAME TO idx_alt_econ_news_date;
ALTER INDEX IF EXISTS alt.idx_alt_econ_news_published_at RENAME TO idx_alt_econ_news_published_at;
ALTER INDEX IF EXISTS alt.idx_alt_econ_news_tags RENAME TO idx_alt_econ_news_tags;
