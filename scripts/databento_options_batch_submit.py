#!/usr/bin/env python3
"""
Submit Databento batch (warehouse) jobs for options on futures.

Queues 3 jobs per run so you can see them in the Databento portal and verify data:
  1. definition  – instrument reference (strike, expiration, option type)
  2. ohlcv-1d    – daily OHLCV bars
  3. statistics  – venue stats containing ALL 15 stat_type values (1–15)

The statistics schema is one schema; each record has a stat_type field (1=opening price,
2=indicative opening, 3=settlement, 4=session low, 5=session high, 6=cleared volume,
7=ask, 8=bid, 9=open interest, 10=fixing price, 11=close, 12=change, 13=vwap,
14=implied volatility, 15=delta). Download the statistics CSV/JSON from the portal
and check the stat_type column to confirm all 15 are present. Default encoding is DBN (fast, zstd-compressed); use --encoding csv or json only if you need human-readable output.

Requires: DATABENTO_API_KEY in .env
Usage:
  .venv/bin/python scripts/databento_options_batch_submit.py
  .venv/bin/python scripts/databento_options_batch_submit.py --start 2025-01-01 --end 2025-02-01
  .venv/bin/python scripts/databento_options_batch_submit.py --schema statistics   # only statistics job
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import databento as db

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Parent symbols for options on futures (same as backfill scripts)
OPTION_PARENTS = [
    "OZL.OPT",  # ZL Soybean Oil
    "OZS.OPT",  # ZS Soybean
    "OZM.OPT",  # ZM Soybean Meal
    "OZC.OPT",  # ZC Corn
    "OZW.OPT",  # ZW Wheat
    "OKE.OPT",  # KE KC HRW Wheat
    "LO.OPT",  # CL Crude Oil
    "ON.OPT",  # NG Natural Gas
    "OH.OPT",  # HO Heating Oil
    "OB.OPT",  # RB RBOB Gasoline
    "OG.OPT",  # GC Gold
    "SO.OPT",  # SI Silver
    "HXE.OPT",  # HG Copper
    "ES.OPT",  # ES E-mini S&P
    "NQ.OPT",  # NQ E-mini Nasdaq
    "OZN.OPT",  # ZN 10Y Treasury
    "OZB.OPT",  # ZB 30Y Treasury
    "OZF.OPT",  # ZF 5Y Treasury
    "EUU.OPT",  # 6E Euro FX
    "JPU.OPT",  # 6J Yen FX
]

DATASET = "GLBX.MDP3"
# Schemas: definition, ohlcv-1d, statistics (statistics has all 15 stat_type values)
SCHEMAS = ("definition", "ohlcv-1d", "statistics")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Submit Databento batch jobs for options (warehouse)"
    )
    parser.add_argument(
        "--start", type=str, default="2010-06-06", help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end", type=str, default=None, help="End date (exclusive); default today"
    )
    parser.add_argument(
        "--schema",
        type=str,
        choices=SCHEMAS,
        default=None,
        help="Submit only this schema (default: all three)",
    )
    parser.add_argument(
        "--encoding",
        type=str,
        choices=("dbn", "csv", "json"),
        default="dbn",
        help="Encoding: dbn=fast compressed binary (default); csv/json for inspection",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print what would be submitted"
    )
    args = parser.parse_args()

    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        try:
            from dotenv import load_dotenv

            load_dotenv(PROJECT_ROOT / ".env")
            api_key = os.getenv("DATABENTO_API_KEY")
        except Exception:
            pass
    if not api_key:
        print("ERROR: DATABENTO_API_KEY not set. Set it in .env or environment.")
        return 1

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today()
    if start >= end:
        print("ERROR: start must be before end")
        return 1

    # Databento batch: end is exclusive; API rejects end after last available (e.g. 2026-02-02)
    last_available = date(2026, 2, 2)
    end_cap = min(end, last_available)
    if end > last_available:
        print(
            f"Note: end capped to {end_cap} (data available through {last_available})"
        )
    start_str = start.isoformat()
    # Exclusive end: end_cap+1 normally; if that would be 2026-02-03 API rejects, so use 2026-02-02
    end_exclusive = end_cap + timedelta(days=1)
    end_str = (
        end_exclusive.isoformat()
        if end_exclusive <= last_available
        else last_available.isoformat()
    )

    schemas = (args.schema,) if args.schema else SCHEMAS
    client = db.Historical(key=api_key)

    if args.dry_run:
        print("DRY RUN – would submit:")
        print(
            f"  dataset={DATASET} symbols={len(OPTION_PARENTS)} parents start={start_str} end={end_str}"
        )
        print(f"  schemas={schemas} encoding={args.encoding} stype_in=parent")
        return 0

    failed = False
    for schema in schemas:
        try:
            job = client.batch.submit_job(
                dataset=DATASET,
                symbols=OPTION_PARENTS,
                schema=schema,
                start=start_str,
                end=end_str,
                encoding=args.encoding,
                compression="zstd",
                stype_in="parent",
                split_duration="month",
            )
            job_id = job.get("job_id") or job.get("id") or "?"
            print(f"Submitted {schema}: job_id={job_id}")
        except Exception as e:
            print(f"ERROR submitting {schema}: {e}")
            failed = True

    print()
    print(
        "Jobs are visible in the Databento portal (Download Center / Batch downloads)."
    )
    print(
        "The statistics job contains all 15 stat_type values (1–15); check stat_type column in CSV."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
