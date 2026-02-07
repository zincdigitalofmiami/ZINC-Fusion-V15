#!/usr/bin/env python3
"""
Backfill all FX options sequentially.

Runs each FX options underlying one by one to load all data.
"""

import os
import sys
import subprocess
from datetime import date

FX_UNDERLYINGS = ["6B", "6C", "6A", "6S", "6N", "6M", "6L", "6Z"]


def run_backfill(underlying: str) -> bool:
    """Run backfill for one underlying."""
    print(f"\n{'='*60}")
    print(f"Starting {underlying} FX options backfill...")
    print(f"{'='*60}")

    cmd = [
        sys.executable,
        "scripts/backfill_fx_options_simple.py",
        "--underlying",
        underlying,
        "--start",
        "2010-06-06",
        "--end",
        "2026-02-02",
    ]

    try:
        result = subprocess.run(cmd, timeout=3600)  # 1 hour timeout per underlying
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"Timeout for {underlying}")
        return False
    except Exception as e:
        print(f"Error for {underlying}: {e}")
        return False


def main():
    print("FX Options Complete Backfill")
    print("=" * 60)
    print(f"Will process {len(FX_UNDERLYINGS)} FX option underlyings:")
    for u in FX_UNDERLYINGS:
        print(f"  - {u}")
    print("=" * 60)

    success_count = 0
    for underlying in FX_UNDERLYINGS:
        if run_backfill(underlying):
            success_count += 1
            print(f"✓ {underlying} completed successfully")
        else:
            print(f"✗ {underlying} failed")

    print(f"\n{'='*60}")
    print(f"COMPLETE: {success_count}/{len(FX_UNDERLYINGS)} FX options backfilled")
    print("=" * 60)


if __name__ == "__main__":
    main()
