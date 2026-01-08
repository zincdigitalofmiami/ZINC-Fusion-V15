-- ZINC-FUSION-V15: Column Metadata Schema
-- Created: January 8, 2026

CREATE SCHEMA IF NOT EXISTS metadata;

CREATE TABLE IF NOT EXISTS metadata.column_descriptions (
    id SERIAL PRIMARY KEY,
    table_schema VARCHAR(100) NOT NULL,
    table_name VARCHAR(200) NOT NULL,
    column_name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    data_type VARCHAR(100),
    value_range TEXT,
    unit TEXT,
    business_meaning TEXT,
    specialist_bucket VARCHAR(50),
    source_system TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (table_schema, table_name, column_name)
);

CREATE TABLE IF NOT EXISTS metadata.table_descriptions (
    id SERIAL PRIMARY KEY,
    table_schema VARCHAR(100) NOT NULL,
    table_name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    purpose TEXT,
    layer VARCHAR(50),
    update_frequency VARCHAR(50),
    estimated_rows BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (table_schema, table_name)
);

CREATE INDEX IF NOT EXISTS idx_colmeta_schema_table ON metadata.column_descriptions(table_schema, table_name);
CREATE INDEX IF NOT EXISTS idx_colmeta_specialist ON metadata.column_descriptions(specialist_bucket);

-- Archive table for garbage cleanup
CREATE TABLE IF NOT EXISTS raw.news_articles_archive (
    id SERIAL PRIMARY KEY,
    original_id INTEGER,
    headline TEXT,
    content TEXT,
    source VARCHAR(255),
    published_at TIMESTAMP,
    bucket_name VARCHAR(100),
    sentiment_score NUMERIC,
    archived_at TIMESTAMP DEFAULT NOW(),
    archive_reason VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_archive_date ON raw.news_articles_archive(archived_at);
CREATE INDEX IF NOT EXISTS idx_archive_original_id ON raw.news_articles_archive(original_id);
