-- Migration: add_vegas_intel_tables
-- Date: 2026-01-14
-- Description: Creates Vegas Intel tables for Glide CRM integration and sales intelligence
-- IMPORTANT: Glide is READ-ONLY. We sync data FROM Glide, never write back.

-- =============================================================================
-- VEGAS INTEL - Glide CRM Integration Tables (READ-ONLY from Glide API)
-- =============================================================================
-- These tables store data synced from US Oil Solutions' Glide CRM.
-- Schema: glide_row_id (unique Glide ID) + data (JSONB payload) + ingested_at
-- The glide_vegas.py ingestion script uses TRUNCATE + INSERT pattern (full refresh).
-- =============================================================================

-- Restaurants from Glide
CREATE TABLE IF NOT EXISTS "ops"."vegas_restaurants" (
    "id" SERIAL NOT NULL,
    "glide_row_id" VARCHAR(100) NOT NULL,
    "data" JSONB NOT NULL,
    "ingested_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_restaurants_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_restaurants_glide_row_id_key" UNIQUE ("glide_row_id")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_restaurants_glide_row_id" ON "ops"."vegas_restaurants"("glide_row_id");
CREATE INDEX IF NOT EXISTS "idx_vegas_restaurants_ingested_at" ON "ops"."vegas_restaurants"("ingested_at");

-- Casinos from Glide
CREATE TABLE IF NOT EXISTS "ops"."vegas_casinos" (
    "id" SERIAL NOT NULL,
    "glide_row_id" VARCHAR(100) NOT NULL,
    "data" JSONB NOT NULL,
    "ingested_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_casinos_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_casinos_glide_row_id_key" UNIQUE ("glide_row_id")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_casinos_glide_row_id" ON "ops"."vegas_casinos"("glide_row_id");
CREATE INDEX IF NOT EXISTS "idx_vegas_casinos_ingested_at" ON "ops"."vegas_casinos"("ingested_at");

-- Fryers from Glide
CREATE TABLE IF NOT EXISTS "ops"."vegas_fryers" (
    "id" SERIAL NOT NULL,
    "glide_row_id" VARCHAR(100) NOT NULL,
    "data" JSONB NOT NULL,
    "ingested_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_fryers_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_fryers_glide_row_id_key" UNIQUE ("glide_row_id")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_fryers_glide_row_id" ON "ops"."vegas_fryers"("glide_row_id");
CREATE INDEX IF NOT EXISTS "idx_vegas_fryers_ingested_at" ON "ops"."vegas_fryers"("ingested_at");

-- Export List from Glide
CREATE TABLE IF NOT EXISTS "ops"."vegas_export_list" (
    "id" SERIAL NOT NULL,
    "glide_row_id" VARCHAR(100) NOT NULL,
    "data" JSONB NOT NULL,
    "ingested_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_export_list_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_export_list_glide_row_id_key" UNIQUE ("glide_row_id")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_export_list_glide_row_id" ON "ops"."vegas_export_list"("glide_row_id");
CREATE INDEX IF NOT EXISTS "idx_vegas_export_list_ingested_at" ON "ops"."vegas_export_list"("ingested_at");

-- Scheduled Reports from Glide
CREATE TABLE IF NOT EXISTS "ops"."vegas_scheduled_reports" (
    "id" SERIAL NOT NULL,
    "glide_row_id" VARCHAR(100) NOT NULL,
    "data" JSONB NOT NULL,
    "ingested_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_scheduled_reports_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_scheduled_reports_glide_row_id_key" UNIQUE ("glide_row_id")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_scheduled_reports_glide_row_id" ON "ops"."vegas_scheduled_reports"("glide_row_id");
CREATE INDEX IF NOT EXISTS "idx_vegas_scheduled_reports_ingested_at" ON "ops"."vegas_scheduled_reports"("ingested_at");

-- Shifts from Glide
CREATE TABLE IF NOT EXISTS "ops"."vegas_shifts" (
    "id" SERIAL NOT NULL,
    "glide_row_id" VARCHAR(100) NOT NULL,
    "data" JSONB NOT NULL,
    "ingested_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_shifts_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_shifts_glide_row_id_key" UNIQUE ("glide_row_id")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_shifts_glide_row_id" ON "ops"."vegas_shifts"("glide_row_id");
CREATE INDEX IF NOT EXISTS "idx_vegas_shifts_ingested_at" ON "ops"."vegas_shifts"("ingested_at");

-- Shift-Casino relationships from Glide
CREATE TABLE IF NOT EXISTS "ops"."vegas_shift_casinos" (
    "id" SERIAL NOT NULL,
    "glide_row_id" VARCHAR(100) NOT NULL,
    "data" JSONB NOT NULL,
    "ingested_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_shift_casinos_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_shift_casinos_glide_row_id_key" UNIQUE ("glide_row_id")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_shift_casinos_glide_row_id" ON "ops"."vegas_shift_casinos"("glide_row_id");
CREATE INDEX IF NOT EXISTS "idx_vegas_shift_casinos_ingested_at" ON "ops"."vegas_shift_casinos"("ingested_at");

-- Shift-Restaurant relationships from Glide
CREATE TABLE IF NOT EXISTS "ops"."vegas_shift_restaurants" (
    "id" SERIAL NOT NULL,
    "glide_row_id" VARCHAR(100) NOT NULL,
    "data" JSONB NOT NULL,
    "ingested_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_shift_restaurants_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_shift_restaurants_glide_row_id_key" UNIQUE ("glide_row_id")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_shift_restaurants_glide_row_id" ON "ops"."vegas_shift_restaurants"("glide_row_id");
CREATE INDEX IF NOT EXISTS "idx_vegas_shift_restaurants_ingested_at" ON "ops"."vegas_shift_restaurants"("ingested_at");


-- =============================================================================
-- VEGAS INTEL - Owned Tables (Our data, not from Glide)
-- =============================================================================
-- These tables store data WE create and maintain for Vegas Intel features.
-- Event calendar, behavioral model profiles, intel sheet tracking, etc.
-- =============================================================================

-- Events Calendar (from Ticketmaster API, CSV upload, or manual entry)
CREATE TABLE IF NOT EXISTS "ops"."vegas_events" (
    "id" SERIAL NOT NULL,
    "event_id" VARCHAR(100) NOT NULL,
    "name" VARCHAR(255) NOT NULL,
    "event_type" VARCHAR(100),
    "venue" VARCHAR(255),
    "start_date" DATE NOT NULL,
    "end_date" DATE,
    "attendance" INTEGER,
    "attendance_min" INTEGER,
    "attendance_max" INTEGER,
    "source" VARCHAR(50),
    "source_url" VARCHAR(500),
    "raw_payload" JSONB,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_events_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_events_event_id_key" UNIQUE ("event_id")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_events_start_date" ON "ops"."vegas_events"("start_date");
CREATE INDEX IF NOT EXISTS "idx_vegas_events_type" ON "ops"."vegas_events"("event_type");
CREATE INDEX IF NOT EXISTS "idx_vegas_events_active" ON "ops"."vegas_events"("is_active");

-- Event Type Profiles (demographic/psychographic mapping)
CREATE TABLE IF NOT EXISTS "ops"."vegas_event_profiles" (
    "id" SERIAL NOT NULL,
    "event_type" VARCHAR(100) NOT NULL,
    "display_name" VARCHAR(255) NOT NULL,
    "primary_demo" VARCHAR(255),
    "psychographic" VARCHAR(255),
    "cuisine_affinity" JSONB,
    "avg_spend_tier" VARCHAR(50),
    "peak_dining_hours" VARCHAR(100),
    "notes" TEXT,
    "created_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_event_profiles_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_event_profiles_event_type_key" UNIQUE ("event_type")
);

-- Casino Profiles (pull factor, vibe, target demo)
CREATE TABLE IF NOT EXISTS "ops"."vegas_casino_profiles" (
    "id" SERIAL NOT NULL,
    "casino_name" VARCHAR(255) NOT NULL,
    "vibe" VARCHAR(100),
    "pull_factor" DOUBLE PRECISION,
    "target_demo" VARCHAR(255),
    "tier" VARCHAR(50),
    "corridor" VARCHAR(100),
    "notes" TEXT,
    "created_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_casino_profiles_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_casino_profiles_casino_name_key" UNIQUE ("casino_name")
);

-- Cuisine Match Scores (event type → cuisine affinity)
CREATE TABLE IF NOT EXISTS "ops"."vegas_cuisine_match" (
    "id" SERIAL NOT NULL,
    "event_type" VARCHAR(100) NOT NULL,
    "cuisine_type" VARCHAR(100) NOT NULL,
    "affinity_score" DOUBLE PRECISION NOT NULL,
    "notes" TEXT,
    "created_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_cuisine_match_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_cuisine_match_event_cuisine_key" UNIQUE ("event_type", "cuisine_type")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_cuisine_match_event_type" ON "ops"."vegas_cuisine_match"("event_type");

-- Intel Sheets (generated sales collateral, tracking)
CREATE TABLE IF NOT EXISTS "ops"."vegas_intel_sheets" (
    "id" SERIAL NOT NULL,
    "sheet_id" VARCHAR(100) NOT NULL,
    "restaurant_id" VARCHAR(100),
    "event_id" VARCHAR(100),
    "sheet_type" VARCHAR(50) NOT NULL,
    "headline" VARCHAR(500),
    "content" JSONB,
    "shareable_url" VARCHAR(500),
    "pdf_url" VARCHAR(500),
    "view_count" INTEGER NOT NULL DEFAULT 0,
    "last_viewed_at" TIMESTAMPTZ(6),
    "sent_at" TIMESTAMPTZ(6),
    "sent_to" VARCHAR(255),
    "status" VARCHAR(50) NOT NULL DEFAULT 'draft',
    "created_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_intel_sheets_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_intel_sheets_sheet_id_key" UNIQUE ("sheet_id")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_intel_sheets_restaurant" ON "ops"."vegas_intel_sheets"("restaurant_id");
CREATE INDEX IF NOT EXISTS "idx_vegas_intel_sheets_event" ON "ops"."vegas_intel_sheets"("event_id");
CREATE INDEX IF NOT EXISTS "idx_vegas_intel_sheets_status" ON "ops"."vegas_intel_sheets"("status");

-- Customer Scores (priority ranking, at-risk detection)
CREATE TABLE IF NOT EXISTS "ops"."vegas_customer_scores" (
    "id" SERIAL NOT NULL,
    "restaurant_id" VARCHAR(100) NOT NULL,
    "casino_id" VARCHAR(100),
    "is_customer" BOOLEAN NOT NULL DEFAULT false,
    "priority_score" DOUBLE PRECISION,
    "at_risk_score" DOUBLE PRECISION,
    "days_since_order" INTEGER,
    "order_pattern" VARCHAR(100),
    "volume_trend" VARCHAR(50),
    "last_order_date" DATE,
    "avg_order_value" DOUBLE PRECISION,
    "fryer_count" INTEGER,
    "event_impact_score" DOUBLE PRECISION,
    "one_liner" VARCHAR(500),
    "computed_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_customer_scores_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "vegas_customer_scores_restaurant_id_key" UNIQUE ("restaurant_id")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_customer_scores_is_customer" ON "ops"."vegas_customer_scores"("is_customer");
CREATE INDEX IF NOT EXISTS "idx_vegas_customer_scores_priority" ON "ops"."vegas_customer_scores"("priority_score");
CREATE INDEX IF NOT EXISTS "idx_vegas_customer_scores_at_risk" ON "ops"."vegas_customer_scores"("at_risk_score");

-- Activity Log (engagement tracking for analytics)
CREATE TABLE IF NOT EXISTS "ops"."vegas_activity_log" (
    "id" SERIAL NOT NULL,
    "activity_type" VARCHAR(50) NOT NULL,
    "entity_type" VARCHAR(50) NOT NULL,
    "entity_id" VARCHAR(100) NOT NULL,
    "user_id" VARCHAR(100),
    "details" JSONB,
    "created_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "vegas_activity_log_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "idx_vegas_activity_log_type" ON "ops"."vegas_activity_log"("activity_type");
CREATE INDEX IF NOT EXISTS "idx_vegas_activity_log_entity" ON "ops"."vegas_activity_log"("entity_type", "entity_id");
CREATE INDEX IF NOT EXISTS "idx_vegas_activity_log_created" ON "ops"."vegas_activity_log"("created_at");

-- =============================================================================
-- DONE - Tables only, no seed data
-- =============================================================================
