#!/usr/bin/env python3
"""
Calculate ZL rolling correlations for ALL symbols in mkt.futures_1d.

Pre-computes 30d, 60d, and 90d return correlations with ZL (soybean oil)
so they are ready for training without real-time calculation.

CRITICAL for FX specialist — currency/commodity correlations drive carry-trade
signals.

Modes
-----
- full   : Recalculate every row (slow, ~5 min).
- incremental : Only rows where zl_corr_90d IS NULL (default, fast).

Usage
-----
    python scripts/calculate_zl_correlations.py              # incremental
    python scripts/calculate_zl_correlations.py --full        # full rebuild
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from tqdm import tqdm

from fusion.db import (
    execute_batch,
    get_read_engine,
    get_write_connection,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WINDOWS = [30, 60, 90]
MIN_OVERLAP = 90  # need at least 90 common dates with ZL
BATCH_SIZE = 2000  # rows per execute_batch page


def _load_zl_returns(engine) -> pd.Series:
    """Return ZL daily returns indexed by event_date."""
    zl = pd.read_sql(
        "SELECT event_date, close FROM mkt.futures_1d "
        "WHERE symbol = 'ZL' ORDER BY event_date",
        engine,
        parse_dates=["event_date"],
    ).set_index("event_date")
    return zl["close"].pct_change().rename("zl_ret")


def _symbols_needing_update(engine, full: bool) -> list[str]:
    """Return list of symbols that need correlation updates."""
    if full:
        df = pd.read_sql(
            "SELECT DISTINCT symbol FROM mkt.futures_1d "
            "WHERE symbol != 'ZL' ORDER BY symbol",
            engine,
        )
    else:
        df = pd.read_sql(
            "SELECT DISTINCT symbol FROM mkt.futures_1d "
            "WHERE zl_corr_90d IS NULL AND close IS NOT NULL "
            "ORDER BY symbol",
            engine,
        )
    return df["symbol"].tolist()


def _compute_for_symbol(symbol: str, engine, zl_ret: pd.Series) -> list[tuple]:
    """Compute rolling correlations for a single symbol vs ZL.

    Returns list of (corr_30, corr_60, corr_90, symbol, event_date) tuples
    ready for execute_batch.
    """
    sym = pd.read_sql(
        "SELECT event_date, close FROM mkt.futures_1d "
        f"WHERE symbol = %s ORDER BY event_date",
        engine,
        params=(symbol,),
        parse_dates=["event_date"],
    ).set_index("event_date")

    if len(sym) < MIN_OVERLAP:
        return []

    sym_ret = sym["close"].pct_change().rename("sym_ret")

    merged = pd.DataFrame({"sym": sym_ret, "zl": zl_ret}).dropna()
    if len(merged) < MIN_OVERLAP:
        return []

    for w in WINDOWS:
        merged[f"corr_{w}d"] = merged["sym"].rolling(w).corr(merged["zl"])

    # Only emit rows where the longest window has a value
    valid = merged.dropna(subset=["corr_90d"])

    rows = []
    for dt, r in valid.iterrows():
        rows.append(
            (
                float(r["corr_30d"]) if pd.notna(r["corr_30d"]) else None,
                float(r["corr_60d"]) if pd.notna(r["corr_60d"]) else None,
                float(r["corr_90d"]) if pd.notna(r["corr_90d"]) else None,
                symbol,
                dt,
            )
        )
    return rows


def calculate_correlations(full: bool = False):
    """Calculate and update ZL correlations for all symbols."""
    t0 = time.time()

    print("\n" + "=" * 70)
    print("  CALCULATING ZL CORRELATIONS FOR ALL FUTURES")
    mode_label = "FULL REBUILD" if full else "INCREMENTAL"
    print(f"  Mode: {mode_label}")
    print("=" * 70 + "\n")

    engine = get_read_engine()

    # 1. Load ZL returns -------------------------------------------------------
    print("Loading ZL returns...")
    zl_ret = _load_zl_returns(engine)
    print(f"  ZL: {len(zl_ret)} trading days\n")

    # 2. Symbols that need work ------------------------------------------------
    symbols = _symbols_needing_update(engine, full)
    if not symbols:
        print("All correlations are up to date.  Nothing to do.\n")
        return

    # Also include ZL itself (corr with itself = 1.0 but keep for consistency)
    if "ZL" not in symbols and full:
        symbols.append("ZL")

    print(f"Processing {len(symbols)} symbols...\n")

    # 3. Compute ---------------------------------------------------------------
    conn = get_write_connection()
    total_updated = 0

    with conn.cursor() as cur:
        for symbol in tqdm(symbols, desc="Correlations"):
            rows = _compute_for_symbol(symbol, engine, zl_ret)
            if not rows:
                continue

            execute_batch(
                cur,
                """
                UPDATE mkt.futures_1d
                SET zl_corr_30d = %s,
                    zl_corr_60d = %s,
                    zl_corr_90d = %s
                WHERE symbol = %s
                  AND event_date = %s
                """,
                rows,
                page_size=BATCH_SIZE,
            )
            total_updated += len(rows)

        conn.commit()

    conn.close()

    elapsed = time.time() - t0
    print(f"\n  Updated {total_updated:,} rows in {elapsed:.1f}s")
    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Calculate ZL rolling correlations (30/60/90-day)"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Recalculate ALL rows (default: only NULL rows)",
    )
    args = parser.parse_args()
    calculate_correlations(full=args.full)
