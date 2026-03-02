-- Add EMA columns to mkt.futures_1d
-- Part of indicator cleanup: pandas_ta removed, TA-Lib EMAs added
ALTER TABLE mkt.futures_1d
  ADD COLUMN IF NOT EXISTS ema_21  REAL,
  ADD COLUMN IF NOT EXISTS ema_50  REAL,
  ADD COLUMN IF NOT EXISTS ema_100 REAL,
  ADD COLUMN IF NOT EXISTS ema_200 REAL;
