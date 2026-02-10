-- Normalize FX pair names to SLASH format established by 20260118_fx_consolidation
--
-- Root cause: fx-spot-daily.ts was never updated after the consolidation migration,
-- so rows ingested after 2026-01-23 have no-slash format (EURUSD) while migrated
-- data has slash format (EUR/USD). This normalizes all rows to slash format.
--
-- Safe: ON CONFLICT (pair, event_date) means if a slash version already exists
-- for a given date, the no-slash duplicate is simply deleted.

-- Step 1: Update no-slash pairs to slash format (matching migration convention)
-- Uses ON CONFLICT to handle any date collisions (keep existing slash row)
DO $$
DECLARE
  pair_map RECORD;
  updated_count INTEGER := 0;
  deleted_count INTEGER := 0;
BEGIN
  -- Process each pair mapping
  FOR pair_map IN
    SELECT * FROM (VALUES
      ('AUDUSD',  'AUD/USD'),
      ('EURUSD',  'EUR/USD'),
      ('GBPUSD',  'GBP/USD'),
      ('USDBRL',  'BRL/USD'),
      ('USDCAD',  'CAD/USD'),
      ('USDCHF',  'CHF/USD'),
      ('USDCNY',  'CNY/USD'),
      ('USDJPY',  'USD/JPY'),
      ('USDKRW',  'KRW/USD'),
      ('USDMXN',  'MXN/USD'),
      ('USDSGD',  'SGD/USD'),
      ('USDHKD',  'HKD/USD'),
      ('USDINR',  'INR/USD'),
      ('USDMYR',  'MYR/USD'),
      ('USDNOK',  'NOK/USD'),
      ('USDSEK',  'SEK/USD'),
      ('USDTHB',  'THB/USD'),
      ('USDTWD',  'TWD/USD'),
      ('NZDUSD',  'NZD/USD'),
      ('USDZAR',  'ZAR/USD')
    ) AS t(old_pair, new_pair)
  LOOP
    -- First: delete no-slash rows where a slash row already exists for that date
    -- (prevents unique constraint violation)
    DELETE FROM mkt.fx_1d
    WHERE pair = pair_map.old_pair
      AND event_date IN (
        SELECT event_date FROM mkt.fx_1d WHERE pair = pair_map.new_pair
      );
    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    -- Then: rename remaining no-slash rows to slash format
    UPDATE mkt.fx_1d
    SET pair = pair_map.new_pair
    WHERE pair = pair_map.old_pair;
    GET DIAGNOSTICS updated_count = ROW_COUNT;

    IF updated_count > 0 OR deleted_count > 0 THEN
      RAISE NOTICE 'FX pair %: renamed % rows, deleted % duplicates',
        pair_map.old_pair, updated_count, deleted_count;
    END IF;
  END LOOP;
END $$;
