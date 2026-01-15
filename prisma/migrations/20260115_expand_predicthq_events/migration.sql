-- Migration: expand_predicthq_events
-- Date: 2026-01-15
-- Description: Expands Vegas events schema to store full PredictHQ data
-- Source: PredictHQ Events API (verified attendance + impact data)
--
-- This stores ALL granular data from PredictHQ including:
-- - Geo coordinates, placekey, address
-- - Impact patterns (daily demand by industry)
-- - Predicted event spend (total + by industry)
-- - PHQ labels with weights
-- - Venue entities with formatted addresses
-- - Confidence scores, rankings, duration

-- =============================================================================
-- 1. Expand vegas_events table with additional PredictHQ fields
-- =============================================================================

-- Add new columns to vegas_events for granular PredictHQ data
ALTER TABLE ops.vegas_events
ADD COLUMN IF NOT EXISTS description TEXT,
ADD COLUMN IF NOT EXISTS alternate_titles TEXT[],
ADD COLUMN IF NOT EXISTS category VARCHAR(50),
ADD COLUMN IF NOT EXISTS rank INTEGER,
ADD COLUMN IF NOT EXISTS local_rank INTEGER,
ADD COLUMN IF NOT EXISTS duration_seconds INTEGER,
ADD COLUMN IF NOT EXISTS start_time TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS end_time TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS predicted_end_time TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS timezone VARCHAR(50),
ADD COLUMN IF NOT EXISTS scope VARCHAR(50),
ADD COLUMN IF NOT EXISTS brand_safe BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS state VARCHAR(50),
ADD COLUMN IF NOT EXISTS first_seen TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS phq_updated TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS start_confidence DECIMAL(3,1),
ADD COLUMN IF NOT EXISTS location_confidence DECIMAL(3,1),
ADD COLUMN IF NOT EXISTS predicted_event_spend DECIMAL(15,2),
ADD COLUMN IF NOT EXISTS spend_accommodation DECIMAL(15,2),
ADD COLUMN IF NOT EXISTS spend_hospitality DECIMAL(15,2),
ADD COLUMN IF NOT EXISTS spend_transportation DECIMAL(15,2);

-- Add indexes for new searchable columns
CREATE INDEX IF NOT EXISTS idx_vegas_events_category ON ops.vegas_events(category);
CREATE INDEX IF NOT EXISTS idx_vegas_events_rank ON ops.vegas_events(rank DESC);
CREATE INDEX IF NOT EXISTS idx_vegas_events_local_rank ON ops.vegas_events(local_rank DESC);
CREATE INDEX IF NOT EXISTS idx_vegas_events_predicted_spend ON ops.vegas_events(predicted_event_spend DESC);

-- =============================================================================
-- 2. Create vegas_venues table for venue/geo data
-- =============================================================================

CREATE TABLE IF NOT EXISTS ops.vegas_venues (
    id SERIAL PRIMARY KEY,
    venue_id VARCHAR(100) UNIQUE NOT NULL,  -- PredictHQ entity_id
    name VARCHAR(255) NOT NULL,
    formatted_address TEXT,
    latitude DECIMAL(10, 7),
    longitude DECIMAL(10, 7),
    placekey VARCHAR(50),                   -- Placekey for POI matching
    postcode VARCHAR(20),
    locality VARCHAR(100),
    region VARCHAR(100),
    country_code VARCHAR(5),
    geo_type VARCHAR(20) DEFAULT 'Point',   -- GeoJSON type
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vegas_venues_name ON ops.vegas_venues(name);
CREATE INDEX IF NOT EXISTS idx_vegas_venues_placekey ON ops.vegas_venues(placekey);
CREATE INDEX IF NOT EXISTS idx_vegas_venues_coords ON ops.vegas_venues(latitude, longitude);

-- =============================================================================
-- 3. Create vegas_event_venues junction table
-- =============================================================================

CREATE TABLE IF NOT EXISTS ops.vegas_event_venues (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(100) NOT NULL REFERENCES ops.vegas_events(event_id) ON DELETE CASCADE,
    venue_id VARCHAR(100) NOT NULL,  -- References vegas_venues.venue_id
    is_primary BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vegas_event_venues_event ON ops.vegas_event_venues(event_id);
CREATE INDEX IF NOT EXISTS idx_vegas_event_venues_venue ON ops.vegas_event_venues(venue_id);

-- =============================================================================
-- 4. Create vegas_event_labels table for PHQ labels with weights
-- =============================================================================

CREATE TABLE IF NOT EXISTS ops.vegas_event_labels (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(100) NOT NULL REFERENCES ops.vegas_events(event_id) ON DELETE CASCADE,
    label VARCHAR(100) NOT NULL,
    weight DECIMAL(4, 3),  -- 0.000 to 1.000
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, label)
);

CREATE INDEX IF NOT EXISTS idx_vegas_event_labels_event ON ops.vegas_event_labels(event_id);
CREATE INDEX IF NOT EXISTS idx_vegas_event_labels_label ON ops.vegas_event_labels(label);
CREATE INDEX IF NOT EXISTS idx_vegas_event_labels_weight ON ops.vegas_event_labels(weight DESC);

-- =============================================================================
-- 5. Create vegas_event_impact table for daily impact patterns
-- =============================================================================
-- This is the KEY table for our calculator - shows predicted demand by day

CREATE TABLE IF NOT EXISTS ops.vegas_event_impact (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(100) NOT NULL REFERENCES ops.vegas_events(event_id) ON DELETE CASCADE,
    vertical VARCHAR(50) NOT NULL,          -- accommodation, hospitality, retail
    impact_type VARCHAR(50) NOT NULL,       -- phq_attendance
    impact_date DATE NOT NULL,
    impact_value INTEGER NOT NULL,          -- predicted attendance for that day
    position VARCHAR(20),                   -- leading, event_day, lagging
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, vertical, impact_date)
);

CREATE INDEX IF NOT EXISTS idx_vegas_event_impact_event ON ops.vegas_event_impact(event_id);
CREATE INDEX IF NOT EXISTS idx_vegas_event_impact_date ON ops.vegas_event_impact(impact_date);
CREATE INDEX IF NOT EXISTS idx_vegas_event_impact_vertical ON ops.vegas_event_impact(vertical);
CREATE INDEX IF NOT EXISTS idx_vegas_event_impact_value ON ops.vegas_event_impact(impact_value DESC);

-- Compound index for date range queries by vertical
CREATE INDEX IF NOT EXISTS idx_vegas_event_impact_date_vertical
ON ops.vegas_event_impact(impact_date, vertical, impact_value DESC);

-- =============================================================================
-- 6. Create vegas_event_entities table for all entities (venues, performers, groups)
-- =============================================================================

CREATE TABLE IF NOT EXISTS ops.vegas_event_entities (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(100) NOT NULL REFERENCES ops.vegas_events(event_id) ON DELETE CASCADE,
    entity_id VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,       -- venue, person, event-group
    name VARCHAR(255) NOT NULL,
    formatted_address TEXT,
    category VARCHAR(50),
    description TEXT,
    labels TEXT[],
    recurring_ical TEXT,                    -- For recurring event patterns
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_vegas_event_entities_event ON ops.vegas_event_entities(event_id);
CREATE INDEX IF NOT EXISTS idx_vegas_event_entities_type ON ops.vegas_event_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_vegas_event_entities_name ON ops.vegas_event_entities(name);

-- =============================================================================
-- 7. Create view for hospitality impact by date (for calculator)
-- =============================================================================

CREATE OR REPLACE VIEW ops.vegas_hospitality_demand AS
SELECT
    i.impact_date,
    SUM(i.impact_value) as total_demand,
    COUNT(DISTINCT i.event_id) as event_count,
    STRING_AGG(DISTINCT e.name, ', ' ORDER BY e.name) as events
FROM ops.vegas_event_impact i
JOIN ops.vegas_events e ON e.event_id = i.event_id
WHERE i.vertical = 'hospitality'
  AND e.is_active = true
GROUP BY i.impact_date
ORDER BY i.impact_date;

-- =============================================================================
-- 8. Create materialized view for event summary with spend
-- =============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS ops.vegas_event_summary AS
SELECT
    e.event_id,
    e.name,
    e.category,
    e.start_date,
    e.end_date,
    e.attendance,
    e.rank,
    e.local_rank,
    e.predicted_event_spend,
    e.spend_hospitality,
    v.name as venue_name,
    v.latitude,
    v.longitude,
    v.formatted_address,
    ARRAY_AGG(DISTINCT el.label ORDER BY el.label) as labels,
    (SELECT SUM(impact_value) FROM ops.vegas_event_impact
     WHERE event_id = e.event_id AND vertical = 'hospitality') as total_hospitality_impact
FROM ops.vegas_events e
LEFT JOIN ops.vegas_event_venues ev ON ev.event_id = e.event_id AND ev.is_primary = true
LEFT JOIN ops.vegas_venues v ON v.venue_id = ev.venue_id
LEFT JOIN ops.vegas_event_labels el ON el.event_id = e.event_id
WHERE e.is_active = true
GROUP BY e.event_id, e.name, e.category, e.start_date, e.end_date,
         e.attendance, e.rank, e.local_rank, e.predicted_event_spend, e.spend_hospitality,
         v.name, v.latitude, v.longitude, v.formatted_address;

CREATE UNIQUE INDEX IF NOT EXISTS idx_vegas_event_summary_event_id
ON ops.vegas_event_summary(event_id);

CREATE INDEX IF NOT EXISTS idx_vegas_event_summary_start_date
ON ops.vegas_event_summary(start_date);

-- =============================================================================
-- Done
-- =============================================================================
