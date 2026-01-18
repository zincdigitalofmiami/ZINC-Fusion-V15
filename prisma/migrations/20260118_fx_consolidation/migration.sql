-- FX Data Consolidation
-- All FX data now goes to mkt.fx_1d
-- Deprecated tables: econ.fx_1d, training.specialist_fx_1d, analytics.specialist_fx_1h

-- Migrate FRED FX data from econ.fx_1d to mkt.fx_1d with pair mapping
-- This assumes econ.fx_1d still exists and has data to migrate
DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'econ' AND table_name = 'fx_1d') THEN
        INSERT INTO mkt.fx_1d (pair, event_date, rate, source, ingested_at, knowledge_time, row_hash)
        SELECT
            CASE series_id
                WHEN 'DEXBZUS' THEN 'BRL/USD'
                WHEN 'DEXCHUS' THEN 'CNY/USD'
                WHEN 'DEXUSEU' THEN 'EUR/USD'
                WHEN 'DEXJPUS' THEN 'USD/JPY'
                WHEN 'DEXMXUS' THEN 'MXN/USD'
                WHEN 'DEXCAUS' THEN 'CAD/USD'
                WHEN 'DEXKOUS' THEN 'KRW/USD'
                WHEN 'DEXINUS' THEN 'INR/USD'
                WHEN 'DEXTAUS' THEN 'TWD/USD'
                WHEN 'DEXUSAL' THEN 'AUD/USD'
                WHEN 'DTWEXBGS' THEN 'DXY_BROAD'
                WHEN 'DTWEXAFEGS' THEN 'DXY_AFE'
                WHEN 'DTWEXEMEGS' THEN 'DXY_EME'
                WHEN 'DTWEXM' THEN 'DXY_MAJOR'
                ELSE series_id
            END as pair,
            event_date,
            value as rate,
            'FRED' as source,
            ingested_at,
            knowledge_time,
            row_hash
        FROM econ.fx_1d
        ON CONFLICT (pair, event_date) DO NOTHING;

        RAISE NOTICE 'Migrated FRED FX data from econ.fx_1d to mkt.fx_1d';
    ELSE
        RAISE NOTICE 'econ.fx_1d does not exist, skipping migration';
    END IF;
END $$;

-- Drop deprecated FX tables (only after confirming data migrated)
-- Uncomment when ready to drop:
-- DROP TABLE IF EXISTS econ.fx_1d CASCADE;
-- DROP TABLE IF EXISTS training.specialist_fx_1d CASCADE;
-- DROP TABLE IF EXISTS analytics.specialist_fx_1h CASCADE;

-- Note: Prisma schema already updated to remove these models
-- Run `prisma generate` after this migration
