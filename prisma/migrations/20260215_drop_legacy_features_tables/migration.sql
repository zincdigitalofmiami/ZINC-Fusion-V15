-- Drop legacy features tables now replaced by specialist/training and mkt tables.
-- - features.elite_1d moved to mkt.futures_1d (20260131_move_elite_to_futures)
-- - features.trump_effect_1d replaced by training.specialist_trump_effect_1d payloads

DROP TABLE IF EXISTS features.elite_1d;
DROP TABLE IF EXISTS features.trump_effect_1d;
