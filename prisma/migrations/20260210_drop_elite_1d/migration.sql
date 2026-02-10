-- Migration: Drop features.elite_1d (consolidated into mkt.futures_1d)
--
-- All elite indicator columns were migrated to mkt.futures_1d by
-- migration 20260131_move_elite_to_futures. All code references have
-- been cut over. This migration drops the now-redundant table.
--
-- Pre-requisites (verify before applying):
--   1. No active code references features.elite_1d (grep confirmed)
--   2. mkt.futures_1d contains all indicator columns with data parity
--   3. build_matrix end-to-end produces non-empty output from mkt.futures_1d

-- Drop the table
DROP TABLE IF EXISTS "features"."elite_1d";

-- Post-drop verification (run manually):
--   SELECT to_regclass('features.elite_1d');  -- Should return NULL
