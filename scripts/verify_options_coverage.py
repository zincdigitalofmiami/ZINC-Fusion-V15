#!/usr/bin/env python3
"""
Verify mkt.options_1d: date range, row counts, and which columns are populated.
Run: .venv/bin/python scripts/verify_options_coverage.py
"""
import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

print("=" * 70)
print("mkt.options_1d — COVERAGE & SCHEMA FILL")
print("=" * 70)

# Total and global date range
cur.execute("SELECT COUNT(*), MIN(event_date), MAX(event_date) FROM mkt.options_1d")
total, min_d, max_d = cur.fetchone()
print(f"\nTotal rows: {total:,}")
print(f"Date range: {min_d} to {max_d}")

# Per-underlying
cur.execute(
    """
    SELECT underlying, COUNT(*) AS rows, MIN(event_date), MAX(event_date)
    FROM mkt.options_1d
    GROUP BY underlying
    ORDER BY rows DESC
"""
)
print("\nPer underlying:")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]:,} rows  ({r[2]} → {r[3]})")

# Full schema = OHLCV + OI + bid/ask/change/premium + 10 stat columns
# Stat columns: opening_price_stat, indicative_opening, session_low_stat, session_high_stat,
#   cleared_volume, fixing_price, close_stat, vwap, implied_volatility, delta
STAT_COLUMNS = [
    "open_interest",
    "bid",
    "ask",
    "premium",
    "change",
    "opening_price_stat",
    "indicative_opening",
    "session_low_stat",
    "session_high_stat",
    "cleared_volume",
    "fixing_price",
    "close_stat",
    "vwap",
    "implied_volatility",
    "delta",
]
print("\nRows with non-NULL (full schema fill):")
cur.execute("SELECT COUNT(*) FROM mkt.options_1d")
tot = cur.fetchone()[0]
for col in STAT_COLUMNS:
    cur.execute(f"SELECT COUNT(*) FROM mkt.options_1d WHERE {col} IS NOT NULL")
    n = cur.fetchone()[0]
    pct = (100.0 * n / tot) if tot else 0
    print(f"  {col}: {n:,} ({pct:.1f}%)")

# Sample: rows that have ALL stat columns filled
cur.execute(
    """
    SELECT COUNT(*) FROM mkt.options_1d
    WHERE opening_price_stat IS NOT NULL AND implied_volatility IS NOT NULL AND delta IS NOT NULL
"""
)
full_fill = cur.fetchone()[0]
print(
    f"\nRows with full stat schema (e.g. opening_price_stat + iv + delta): {full_fill:,} ({100.0*full_fill/tot:.1f}%)"
)

conn.close()
print("\nDone.")
