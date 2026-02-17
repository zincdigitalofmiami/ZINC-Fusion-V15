-- backfill_matrix_nan_to_null.sql
-- Fix NaN values stored as literal NaN in training.matrix_1d
--
-- PostgreSQL stores Python float('nan') as NaN in REAL/DOUBLE columns.
-- These look non-NULL to IS NOT NULL but poison aggregates (AVG, SUM).
--
-- Strategy: UPDATE all REAL/DOUBLE columns, setting NaN to NULL.
-- Run AFTER fixing build_matrix.py to prevent new NaN writes.
--
-- USAGE:
--   psql $DATABASE_URL -f scripts/backfill_matrix_nan_to_null.sql
--
-- PREFERRED ALTERNATIVE: Re-run build_matrix.py (Phase 3) which does
-- TRUNCATE + INSERT. That rebuilds the matrix from scratch with the
-- fixed NaN->None conversion.

BEGIN;

DO $$
DECLARE
    col_name TEXT;
    update_count INT;
    total_fixed INT := 0;
BEGIN
    FOR col_name IN
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'training'
          AND table_name = 'matrix_1d'
          AND data_type IN ('real', 'double precision')
          AND column_name NOT IN ('trade_date', 'symbol', 'matrix_version', 'created_at')
    LOOP
        EXECUTE format(
            'UPDATE training.matrix_1d SET %I = NULL WHERE %I::text = ''NaN''',
            col_name, col_name
        );
        GET DIAGNOSTICS update_count = ROW_COUNT;
        IF update_count > 0 THEN
            total_fixed := total_fixed + update_count;
            RAISE NOTICE 'Fixed % NaN values in column %', update_count, col_name;
        END IF;
    END LOOP;
    RAISE NOTICE 'Total NaN -> NULL fixes: %', total_fixed;
END $$;

COMMIT;
