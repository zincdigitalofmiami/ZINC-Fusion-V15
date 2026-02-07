#!/usr/bin/env python3
"""
Audit mkt.options_1d for fake/synthetic data.
Checks: impossible dates, constant values, null OHLCV, duplicates, non-databento source.
Run: .venv/bin/python scripts/audit_options_fake_data.py
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import psycopg2

load_dotenv(Path(__file__).parent.parent / ".env")
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()


def run(q, *a):
    cur.execute(q, a or ())
    return cur.fetchone()[0]


def run_row(q, *a):
    cur.execute(q, a or ())
    return cur.fetchone()


issues = []
total = run("SELECT COUNT(*) FROM mkt.options_1d")

# 1) Event date before 2010 (bad/epoch)
n_bad_date = run(
    "SELECT COUNT(*) FROM mkt.options_1d WHERE event_date < %s", "2010-01-01"
)
if n_bad_date:
    issues.append(
        ("event_date < 2010", n_bad_date, "Remove or backfill with real dates")
    )

# 2) Null close (required for a bar)
n_null_close = run("SELECT COUNT(*) FROM mkt.options_1d WHERE close IS NULL")
if n_null_close:
    issues.append(("close IS NULL", n_null_close, "Invalid bars"))

# 3) Duplicate (underlying, event_date, expiration, strike, option_type)
n_dup = run(
    """
    SELECT COUNT(*) FROM (
        SELECT underlying, event_date, expiration, strike, option_type, COUNT(*)
        FROM mkt.options_1d
        GROUP BY underlying, event_date, expiration, strike, option_type
        HAVING COUNT(*) > 1
    ) x
"""
)
if n_dup:
    issues.append(("duplicate key rows", n_dup, "Dedupe"))

# 4) Source not databento
n_other_source = run(
    "SELECT COUNT(*) FROM mkt.options_1d WHERE source IS NULL OR source != %s",
    "databento",
)
if n_other_source:
    issues.append(("source != 'databento'", n_other_source, "Review source"))

# 5) Same close across huge fraction (suspicious constant)
cur.execute(
    """
    SELECT close, COUNT(*) c FROM mkt.options_1d WHERE close IS NOT NULL
    GROUP BY close ORDER BY c DESC LIMIT 1
"""
)
row = cur.fetchone()
if row and total:
    pct = 100.0 * row[1] / total
    if pct > 50:
        issues.append(("constant close (%.1f%%)" % pct, row[1], "Suspicious"))

# 6) Negative volume
n_neg_vol = run(
    "SELECT COUNT(*) FROM mkt.options_1d WHERE volume IS NOT NULL AND volume < 0"
)
if n_neg_vol:
    issues.append(("volume < 0", n_neg_vol, "Invalid"))

# 7) Rows with full stat schema (target: all 15)
n_full_stat = run(
    """
    SELECT COUNT(*) FROM mkt.options_1d
    WHERE opening_price_stat IS NOT NULL AND implied_volatility IS NOT NULL AND delta IS NOT NULL
"""
)
pct_full = 100.0 * n_full_stat / total if total else 0

# Report
print("mkt.options_1d — FAKE DATA AUDIT")
print("Total rows:", total)
print()
if issues:
    print("ISSUES:")
    for name, count, action in issues:
        print("  %s: %s — %s" % (name, count, action))
else:
    print(
        "No fake-data issues found (dates, null close, duplicates, source, constant close, neg volume)."
    )
print()
print(
    "Full schema fill (opening_price_stat + iv + delta): %s / %s (%.2f%%)"
    % (n_full_stat, total, pct_full)
)
conn.close()
sys.exit(1 if issues else 0)
