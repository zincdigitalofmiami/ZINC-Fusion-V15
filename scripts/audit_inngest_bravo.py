#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    ELITE TEAM BRAVO — INNGEST INTEGRATION AUDIT                ║
║                                                                               ║
║  Deep scan of Inngest function wiring, data flows, and "true success"         ║
║  confirmations for all scheduled ingestion jobs.                              ║
║                                                                               ║
║  Mission: Verify every Inngest function is correctly wired end-to-end         ║
║           from external API → landing table → ops.ingest_run tracking         ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Usage:
    python scripts/audit_inngest_bravo.py
    python scripts/audit_inngest_bravo.py --section 3    # Run specific section
    python scripts/audit_inngest_bravo.py --dry-run      # Show what would be checked
    python scripts/audit_inngest_bravo.py --verbose      # Extra detail

Sections:
    1. Inngest Function Registry (registered vs expected)
    2. Cron Schedule Mapping (who runs when)
    3. Target Table Validation (every function → landing table exists)
    4. ops.ingest_run Tracking (Bronze Contract compliance)
    5. Recent Execution History (last 7 days of runs)
    6. Data Freshness Check (is data actually landing?)
    7. Wiring Integrity (source → table → tracking complete)
    8. True Success Confirmations (verify data matches expectations)
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Look for .env in project root (two levels up from scripts/)
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()  # Fall back to default search
except ImportError:
    pass  # dotenv not installed, rely on shell environment

import psycopg2
from psycopg2.extras import RealDictCursor

# ═══════════════════════════════════════════════════════════════════════════════
# INNGEST FUNCTION REGISTRY — Expected functions based on route.ts exports
# ═══════════════════════════════════════════════════════════════════════════════

FRED_TARGET_TABLES = [
    "econ.rates_1d",
    "econ.activity_1d",
    "econ.commodities_1d",
    "econ.vol_indices_1d",
    "econ.money_1d",
    "econ.labor_1d",
    "econ.inflation_1d",
]

INNGEST_FUNCTION_REGISTRY = {
    # ─── Price Data ───────────────────────────────────────────────────────────
    "zl-15m": {
        "job_name": "zl-15m",
        "display": "ZL 15-Minute Prices",
        "target_table": "analytics.zl_price_15m",
        "frequency": "15min",
        "cron": "*/15 * * * *",
        "source": "Yahoo Finance",
        "specialist_tags": ["crush"],
    },
    "zl-1h": {
        "job_name": "zl-1h",
        "display": "ZL 1-Hour Prices",
        "target_table": "analytics.zl_price_1h",
        "frequency": "hourly",
        "cron": "0 * * * *",
        "source": "Yahoo Finance",
        "specialist_tags": ["crush"],
    },
    "yahoo-eod": {
        "job_name": "yahoo-eod",
        "display": "Yahoo EOD Prices",
        "target_table": "mkt.futures_1d",
        "target_tables": ["mkt.futures_1d", "analytics.zl_price_1d"],
        "frequency": "daily",
        "cron": "0 11 * * 1-5",  # 5AM CT
        "source": "Yahoo Finance",
        "specialist_tags": ["crush", "energy", "volatility"],
    },
    "barchart-futures-daily": {
        "job_name": "barchart-futures-daily",
        "display": "Barchart Futures Daily",
        "target_table": "mkt.futures_1d",
        "frequency": "daily",
        "cron": "0 23 * * 1-5",  # 5PM CT
        "source": "Barchart API",
        "specialist_tags": ["crush"],
    },

    # ─── FRED Segments ────────────────────────────────────────────────────────
    "fred-daily-fed": {
        "job_name": "fred-daily-fed",
        "display": "FRED Daily - Fed",
        "target_table": "econ.rates_1d",
        "target_tables": FRED_TARGET_TABLES,
        "frequency": "daily",
        "cron": "0 11 * * 1-5",
        "source": "FRED API",
        "specialist_tags": ["fed", "fx"],
    },
    "fred-daily-fx": {
        "job_name": "fred-daily-fx",
        "display": "FRED Daily - FX",
        "target_table": "econ.rates_1d",
        "target_tables": FRED_TARGET_TABLES,
        "frequency": "daily",
        "cron": "5 11 * * 1-5",
        "source": "FRED API",
        "specialist_tags": ["fx", "china"],
    },
    "fred-daily-energy": {
        "job_name": "fred-daily-energy",
        "display": "FRED Daily - Energy",
        "target_table": "econ.commodities_1d",
        "target_tables": FRED_TARGET_TABLES,
        "frequency": "daily",
        "cron": "10 11 * * 1-5",
        "source": "FRED API",
        "specialist_tags": ["energy", "biofuel"],
    },
    "fred-daily-biofuel": {
        "job_name": "fred-daily-biofuel",
        "display": "FRED Daily - Biofuel",
        "target_table": "econ.commodities_1d",
        "target_tables": FRED_TARGET_TABLES,
        "frequency": "daily",
        "cron": "15 11 * * 1-5",
        "source": "FRED API",
        "specialist_tags": ["biofuel", "energy"],
    },
    "fred-daily-crush": {
        "job_name": "fred-daily-crush",
        "display": "FRED Daily - Crush",
        "target_table": "econ.commodities_1d",
        "target_tables": FRED_TARGET_TABLES,
        "frequency": "daily",
        "cron": "20 11 * * 1-5",
        "source": "FRED API",
        "specialist_tags": ["crush", "china"],
    },
    "fred-daily-palm": {
        "job_name": "fred-daily-palm",
        "display": "FRED Daily - Palm",
        "target_table": "econ.commodities_1d",
        "target_tables": FRED_TARGET_TABLES,
        "frequency": "daily",
        "cron": "25 11 * * 1-5",
        "source": "FRED API",
        "specialist_tags": ["palm", "substitutes"],
    },
    "fred-daily-volatility": {
        "job_name": "fred-daily-volatility",
        "display": "FRED Daily - Volatility",
        "target_table": "econ.vol_indices_1d",
        "target_tables": FRED_TARGET_TABLES,
        "frequency": "daily",
        "cron": "30 11 * * 1-5",
        "source": "FRED API",
        "specialist_tags": ["volatility", "fed"],
    },
    "fred-daily-trump-effect": {
        "job_name": "fred-daily-trump-effect",
        "display": "FRED Daily - Trump Effect",
        "target_table": "econ.vol_indices_1d",
        "target_tables": FRED_TARGET_TABLES,
        "frequency": "daily",
        "cron": "35 11 * * 1-5",
        "source": "FRED API",
        "specialist_tags": ["trump_effect", "tariff"],
    },
    "fred-daily-china": {
        "job_name": "fred-daily-china",
        "display": "FRED Daily - China",
        "target_table": "econ.activity_1d",
        "target_tables": FRED_TARGET_TABLES,
        "frequency": "daily",
        "cron": "40 11 * * 1-5",
        "source": "FRED API",
        "specialist_tags": ["china", "crush"],
    },
    "fred-daily-general": {
        "job_name": "fred-daily-general",
        "display": "FRED Daily - General",
        "target_table": "econ.activity_1d",
        "target_tables": FRED_TARGET_TABLES,
        "frequency": "daily",
        "cron": "45 11 * * 1-5",
        "source": "FRED API",
        "specialist_tags": ["crush", "china"],
    },

    # ─── Government / Regulatory ──────────────────────────────────────────────
    "cftc-weekly": {
        "job_name": "cftc-weekly",
        "display": "CFTC Weekly COT",
        "target_table": "pos.cftc_1w",
        "frequency": "weekly",
        "cron": "0 21 * * 5",  # Friday 4PM ET
        "source": "CFTC API",
        "specialist_tags": ["crush", "volatility"],
    },
    "federal-register-daily": {
        "job_name": "federal-register-daily",
        "display": "Federal Register Daily",
        "target_table": "alt.legislation_1d",
        "frequency": "daily",
        "cron": "0 11 * * 1-5",
        "source": "Federal Register API",
        "specialist_tags": ["tariff", "biofuel"],
    },
    "nyfed-daily": {
        "job_name": "nyfed-daily",
        "display": "NY Fed Daily",
        "target_table": "econ.rates_1d",
        "frequency": "daily",
        "cron": "0 12 * * 1-5",
        "source": "NY Fed API",
        "specialist_tags": ["fed"],
    },
    "nass-crush-weekly": {
        "job_name": "nass-crush-weekly",
        "display": "NASS Soybean Crush & Prices",
        "target_table": "econ.rates_1d",
        "frequency": "weekly",
        "cron": "0 10 * * 1",
        "source": "USDA NASS",
        "specialist_tags": ["crush"],
    },
    "eia-petroleum-daily": {
        "job_name": "eia-petroleum-daily",
        "display": "EIA Petroleum Daily",
        "target_table": "econ.rates_1d",
        "frequency": "daily",
        "cron": "0 17 * * 1-5",
        "source": "EIA API",
        "specialist_tags": ["energy", "biofuel"],
    },
    "epa-rin-prices-daily": {
        "job_name": "epa-rin-prices-daily",
        "display": "EPA RIN Prices Daily",
        "target_table": "supply.epa_rin_1d",
        "frequency": "daily",
        "cron": "30 14 * * 1-5",
        "source": "EPA EMTS",
        "specialist_tags": ["biofuel", "energy"],
    },

    # ─── Trade Data ───────────────────────────────────────────────────────────
    "cbp-trade-daily": {
        "job_name": "cbp-trade-daily",
        "display": "CBP Trade Daily",
        "target_table": "alt.news_1d",
        "frequency": "daily",
        "cron": "0 13 * * 1-5",
        "source": "CBP RSS",
        "specialist_tags": ["tariff", "china"],
    },
    "ice-comprehensive-daily": {
        "job_name": "ice-comprehensive-daily",
        "display": "ICE.gov Comprehensive",
        "target_table": "alt.news_1d",
        "frequency": "daily",
        "cron": "0 8,14,20 * * *",
        "source": "ICE.gov",
        "specialist_tags": ["crush"],
    },
    "aei-trade-daily": {
        "job_name": "aei-trade-daily",
        "display": "AEI Trade Daily",
        "target_table": "alt.news_1d",
        "frequency": "daily",
        "cron": "0 14 * * 1-5",
        "source": "AEI Website",
        "specialist_tags": ["tariff", "china"],
    },
    "usda-export-sales-weekly": {
        "job_name": "usda-export-sales-weekly",
        "display": "USDA Export Sales Weekly",
        "target_table": "supply.usda_exports_1w",
        "frequency": "weekly",
        "cron": "0 18 * * 4",
        "source": "USDA FAS",
        "specialist_tags": ["crush", "china"],
    },
    "usda-wasde-monthly": {
        "job_name": "usda-wasde-monthly",
        "display": "USDA WASDE Monthly",
        "target_table": "supply.usda_wasde_1m",
        "frequency": "monthly",
        "cron": "0 16 * * 1-5",
        "source": "Cornell/USDA XML",
        "specialist_tags": ["crush"],
    },

    # ─── News / Press ─────────────────────────────────────────────────────────
    "farmdoc-rins-daily": {
        "job_name": "farmdoc-rins-daily",
        "display": "FarmDoc RINs Daily",
        "target_table": "alt.news_1d",
        "frequency": "daily",
        "cron": "0 14 * * 1-5",
        "source": "FarmDoc Daily",
        "specialist_tags": ["biofuel"],
    },
    "conab-news-daily": {
        "job_name": "conab-news-daily",
        "display": "CONAB News Daily",
        "target_table": "alt.news_1d",
        "frequency": "daily",
        "cron": "0 15 * * 1-5",
        "source": "CONAB Brazil",
        "specialist_tags": ["crush", "china"],
    },
    "whitehouse-comprehensive-daily": {
        "job_name": "whitehouse-comprehensive-daily",
        "display": "White House Comprehensive",
        "target_table": "alt.news_1d",
        "frequency": "daily",
        "cron": "0 7,11,15,19 * * *",
        "source": "White House",
        "specialist_tags": ["tariff", "trump_effect"],
    },
    "nass-weekly": {
        "job_name": "nass-weekly",
        "display": "NASS Weekly",
        "target_table": "econ.rates_1d",
        "frequency": "weekly",
        "cron": "0 17 * * 5",
        "source": "USDA NASS",
        "specialist_tags": ["crush"],
    },
    "barchart-zl-news-daily": {
        "job_name": "barchart-zl-news-daily",
        "display": "Barchart ZL News Daily",
        "target_table": "alt.news_1d",
        "frequency": "daily",
        "cron": "30 14 * * 1-5",
        "source": "Barchart News",
        "specialist_tags": ["crush"],
    },

    # ─── Weather ──────────────────────────────────────────────────────────────
    "noaa-weather-daily": {
        "job_name": "noaa-weather-daily",
        "display": "NOAA Weather Daily",
        "target_table": "alt.weather_1d",
        "frequency": "daily",
        "cron": "0 13 * * 1-5",
        "source": "NOAA API",
        "specialist_tags": ["crush"],
    },
    "openmeteo-weather-daily": {
        "job_name": "openmeteo-weather-daily",
        "display": "Open-Meteo Weather Daily",
        "target_table": "alt.weather_1d",
        "frequency": "daily",
        "cron": "10 13 * * 1-5",
        "source": "Open-Meteo API",
        "specialist_tags": ["crush"],
    },
    "weather-features-daily": {
        "job_name": "weather-features-daily",
        "display": "Weather Features Daily",
        "target_table": "features.weather_1d",
        "frequency": "daily",
        "cron": "0 14 * * *",
        "source": "Computed",
        "specialist_tags": ["crush"],
    },

    # ─── FX / Commodities ─────────────────────────────────────────────────────
    "fx-spot-daily": {
        "job_name": "fx-spot-daily",
        "display": "FX Spot Daily",
        "target_table": "mkt.fx_1d",
        "frequency": "daily",
        "cron": "0 12 * * 1-5",
        "source": "FRED/Yahoo",
        "specialist_tags": ["fx", "china"],
    },
    "cpo-palm-oil-daily": {
        "job_name": "cpo-palm-oil-daily",
        "display": "CPO Palm Oil Daily",
        "target_table": "mkt.futures_1d",
        "frequency": "daily",
        "cron": "0 10 * * 1-5",
        "source": "Investing.com/Yahoo",
        "specialist_tags": ["palm", "substitutes"],
    },
    "cpo-trading-economics": {
        "job_name": "cpo-trading-economics",
        "display": "CPO Trading Economics",
        "target_table": "mkt.futures_1d",
        "frequency": "daily",
        "cron": "0 12 * * 1-5",
        "source": "Trading Economics",
        "specialist_tags": ["palm"],
    },

    # ─── Premium Subscriptions ────────────────────────────────────────────────
    "profarmer-daily": {
        "job_name": "profarmer-daily",
        "display": "ProFarmer Daily",
        "target_table": "alt.news_1d",
        "frequency": "daily",
        "cron": "0 12,23 * * 1-5",
        "source": "ProFarmer",
        "specialist_tags": ["crush"],
    },

    # ─── ETF / Options ────────────────────────────────────────────────────────
    "barchart-etf-daily": {
        "job_name": "barchart-etf-daily",
        "display": "Barchart ETF Daily",
        "target_table": "mkt.etf_1d",
        "frequency": "daily",
        "cron": "0 0 * * 1-5",
        "source": "Barchart API",
        "specialist_tags": ["crush", "energy"],
    },
    "barchart-options-daily": {
        "job_name": "barchart-options-daily",
        "display": "Barchart Options Daily",
        "target_table": "mkt.options_greeks_1d",
        "frequency": "daily",
        "cron": "30 23 * * 1-5",
        "source": "Barchart API",
        "specialist_tags": ["crush", "volatility"],
    },
}

# Target tables that Inngest functions write to
def get_target_tables(config: dict):
    tables = config.get("target_tables")
    if tables:
        return tables
    return [config["target_table"]]


TARGET_TABLES = sorted({table for f in INNGEST_FUNCTION_REGISTRY.values() for table in get_target_tables(f)})


def get_connection():
    """Get PostgreSQL connection."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        print("❌ DATABASE_URL not found in environment")
        sys.exit(1)
    return psycopg2.connect(database_url)


def print_header(title: str, section_num: int = None):
    """Print section header."""
    if section_num:
        print(f"\n{'═' * 80}")
        print(f"  SECTION {section_num}: {title}")
        print(f"{'═' * 80}\n")
    else:
        print(f"\n{'─' * 60}")
        print(f"  {title}")
        print(f"{'─' * 60}\n")


def print_subheader(title: str):
    """Print subsection header."""
    print(f"\n  ┌─ {title}")
    print(f"  │")


def section_1_function_registry(cur, verbose: bool = False):
    """Section 1: Inngest Function Registry — verify all expected functions."""
    print_header("INNGEST FUNCTION REGISTRY", 1)

    # Group by frequency
    by_frequency = {}
    for func_id, config in INNGEST_FUNCTION_REGISTRY.items():
        freq = config.get("frequency", "unknown")
        if freq not in by_frequency:
            by_frequency[freq] = []
        by_frequency[freq].append((func_id, config))

    total_functions = len(INNGEST_FUNCTION_REGISTRY)
    print(f"  Total registered functions: {total_functions}")
    print()

    for freq in ["15min", "hourly", "daily", "weekly", "monthly"]:
        if freq not in by_frequency:
            continue
        funcs = by_frequency[freq]
        print(f"  ┌─ {freq.upper()} ({len(funcs)} functions)")
        for func_id, config in sorted(funcs, key=lambda x: x[0]):
            cron = config.get("cron", "event-triggered")
            tables = get_target_tables(config)
            table_label = tables[0] if len(tables) == 1 else f"{tables[0]} (+{len(tables) - 1})"
            print(f"  │  {func_id:30s} → {table_label:25s} [{cron}]")
        print(f"  └─")
        print()

    return {"total_functions": total_functions, "by_frequency": {k: len(v) for k, v in by_frequency.items()}}


def section_2_cron_schedule(cur, verbose: bool = False):
    """Section 2: Cron Schedule Mapping — who runs when."""
    print_header("CRON SCHEDULE MAPPING", 2)

    # Build schedule by hour (UTC)
    schedule = {}
    for func_id, config in INNGEST_FUNCTION_REGISTRY.items():
        cron = config.get("cron")
        if not cron:
            continue

        parts = cron.split()
        if len(parts) >= 2:
            minute = parts[0]
            hour = parts[1]
            time_key = f"{hour.zfill(2)}:{minute.zfill(2)} UTC"
            if time_key not in schedule:
                schedule[time_key] = []
            schedule[time_key].append(func_id)

    print("  Daily Schedule (UTC):")
    print()

    for time_key in sorted(schedule.keys()):
        funcs = schedule[time_key]
        print(f"  {time_key}:")
        for func_id in sorted(funcs):
            config = INNGEST_FUNCTION_REGISTRY[func_id]
            print(f"    • {config['display']}")

    print()

    # Show weekly/monthly triggers
    print("  Weekly/Monthly Triggers:")
    for func_id, config in sorted(INNGEST_FUNCTION_REGISTRY.items()):
        freq = config.get("frequency")
        if freq in ["weekly", "monthly"]:
            cron = config.get("cron", "event-triggered")
            print(f"    • {config['display']:40s} {cron}")

    return {"scheduled_functions": len(schedule)}


def section_3_target_tables(cur, verbose: bool = False):
    """Section 3: Target Table Validation — verify all target tables exist."""
    print_header("TARGET TABLE VALIDATION", 3)

    results = {"exists": [], "missing": []}

    print("  Checking target tables for all Inngest functions:\n")

    for table in TARGET_TABLES:
        schema, table_name = table.split(".")

        # Check if table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
            )
        """, (schema, table_name))
        exists = cur.fetchone()[0]

        if exists:
            # Get row count
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table_name}"')
                count = cur.fetchone()[0]
                print(f"  ✓ {table:30s} — {count:>10,} rows")
                results["exists"].append({"table": table, "count": count})
            except Exception as e:
                print(f"  ⚠ {table:30s} — exists but count failed: {e}")
                results["exists"].append({"table": table, "count": -1})
        else:
            print(f"  ✗ {table:30s} — MISSING")
            results["missing"].append(table)

    print()
    print(f"  Summary: {len(results['exists'])} tables exist, {len(results['missing'])} missing")

    if results["missing"]:
        print(f"\n  ⚠️  ALERT: Missing tables need to be created!")
        for table in results["missing"]:
            print(f"      • {table}")

    return results


def section_4_ingest_run_tracking(cur, verbose: bool = False):
    """Section 4: ops.ingest_run Tracking — Bronze Contract compliance."""
    print_header("OPS.INGEST_RUN TRACKING (BRONZE CONTRACT)", 4)

    # Check if ops.ingest_run exists
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'ops' AND table_name = 'ingest_run'
        )
    """)
    if not cur.fetchone()[0]:
        print("  ✗ ops.ingest_run table does not exist!")
        return {"exists": False}

    print("  ✓ ops.ingest_run table exists\n")

    # Get all unique job names
    cur.execute("""
        SELECT DISTINCT job_name
        FROM ops.ingest_run
        ORDER BY job_name
    """)
    tracked_jobs = [row[0] for row in cur.fetchall()]

    print(f"  Tracked Jobs ({len(tracked_jobs)}):")
    for job in tracked_jobs:
        print(f"    • {job}")

    # Find jobs that should be tracked but aren't
    expected_jobs = set(f["job_name"] for f in INNGEST_FUNCTION_REGISTRY.values())
    tracked_set = set(tracked_jobs)

    missing_tracking = expected_jobs - tracked_set
    extra_tracking = tracked_set - expected_jobs

    print()
    if missing_tracking:
        print(f"  ⚠️  Jobs NOT tracked in ops.ingest_run ({len(missing_tracking)}):")
        for job in sorted(missing_tracking):
            print(f"      • {job}")
    else:
        print("  ✓ All expected jobs have tracking records")

    if extra_tracking and verbose:
        print(f"\n  ℹ️  Extra jobs in ops.ingest_run (not in registry):")
        for job in sorted(extra_tracking):
            print(f"      • {job}")

    return {
        "exists": True,
        "tracked_jobs": len(tracked_jobs),
        "expected_jobs": len(expected_jobs),
        "missing_tracking": list(missing_tracking),
    }


def section_5_execution_history(cur, verbose: bool = False):
    """Section 5: Recent Execution History — last 7 days of runs."""
    print_header("RECENT EXECUTION HISTORY (7 DAYS)", 5)

    # Check ops.ingest_run exists
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'ops' AND table_name = 'ingest_run'
        )
    """)
    if not cur.fetchone()[0]:
        print("  ✗ ops.ingest_run table does not exist — cannot check history")
        return {"available": False}

    # Get execution stats by job for last 7 days
    cur.execute("""
        SELECT
            job_name,
            COUNT(*) as total_runs,
            COUNT(*) FILTER (WHERE status = 'success') as success_count,
            COUNT(*) FILTER (WHERE status = 'failed') as failed_count,
            COUNT(*) FILTER (WHERE status = 'partial_success') as partial_count,
            MAX(completed_at) as last_completed,
            SUM(COALESCE(rows_inserted, 0)) as total_inserted
        FROM ops.ingest_run
        WHERE started_at >= NOW() - INTERVAL '7 days'
        GROUP BY job_name
        ORDER BY job_name
    """)

    rows = cur.fetchall()

    if not rows:
        print("  ℹ️  No execution records in the last 7 days")
        return {"available": True, "runs": 0}

    print(f"  {'Job Name':35s} {'Runs':>6s} {'✓':>5s} {'✗':>5s} {'~':>5s} {'Inserted':>10s} {'Last Run'}")
    print(f"  {'-' * 35} {'-' * 6} {'-' * 5} {'-' * 5} {'-' * 5} {'-' * 10} {'-' * 20}")

    total_runs = 0
    total_success = 0
    total_failed = 0

    for row in rows:
        job_name, runs, success, failed, partial, inserted, last_completed = row
        total_runs += runs
        total_success += success
        total_failed += failed

        last_str = last_completed.strftime("%Y-%m-%d %H:%M") if last_completed else "never"
        status_indicator = "✓" if failed == 0 else "⚠" if success > failed else "✗"

        print(f"  {job_name:35s} {runs:>6d} {success:>5d} {failed:>5d} {partial or 0:>5d} {inserted or 0:>10,d} {last_str} {status_indicator}")

    print()
    print(f"  Total: {total_runs} runs, {total_success} success, {total_failed} failed")

    success_rate = (total_success / total_runs * 100) if total_runs > 0 else 0
    print(f"  Success Rate: {success_rate:.1f}%")

    return {
        "available": True,
        "total_runs": total_runs,
        "success_count": total_success,
        "failed_count": total_failed,
        "success_rate": success_rate,
    }


def section_6_data_freshness(cur, verbose: bool = False):
    """Section 6: Data Freshness Check — is data actually landing?"""
    print_header("DATA FRESHNESS CHECK", 6)

    print("  Checking most recent data in each target table:\n")

    results = []
    today = datetime.now().date()

    for table in TARGET_TABLES:
        schema, table_name = table.split(".")

        # Try to get most recent event_date
        try:
            # Check for event_date column
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = %s
                    AND table_name = %s
                    AND column_name = 'event_date'
                )
            """, (schema, table_name))
            has_event_date = cur.fetchone()[0]

            if has_event_date:
                cur.execute(f'''
                    SELECT
                        MAX(event_date) as latest,
                        COUNT(*) FILTER (WHERE event_date >= CURRENT_DATE - INTERVAL '7 days') as recent_count
                    FROM "{schema}"."{table_name}"
                ''')
                latest, recent_count = cur.fetchone()

                if latest:
                    days_old = (today - latest).days
                    freshness = "🟢" if days_old <= 1 else "🟡" if days_old <= 3 else "🟠" if days_old <= 7 else "🔴"
                    print(f"  {freshness} {table:30s} — latest: {latest}, {days_old}d old, {recent_count:,} rows (7d)")
                    results.append({"table": table, "latest": str(latest), "days_old": days_old, "recent_count": recent_count})
                else:
                    print(f"  ⚫ {table:30s} — EMPTY (no data)")
                    results.append({"table": table, "latest": None, "days_old": -1, "recent_count": 0})
            else:
                # Fallback to timestamp column for intraday-style tables
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = %s
                        AND table_name = %s
                        AND column_name = 'timestamp'
                    )
                """, (schema, table_name))
                has_timestamp = cur.fetchone()[0]

                if has_timestamp:
                    cur.execute(f'''
                        SELECT
                            MAX(timestamp) as latest,
                            COUNT(*) FILTER (WHERE timestamp >= NOW() - INTERVAL '7 days') as recent_count
                        FROM "{schema}"."{table_name}"
                    ''')
                    latest, recent_count = cur.fetchone()

                    if latest:
                        latest_date = latest.date() if hasattr(latest, "date") else None
                        days_old = (today - latest_date).days if latest_date else -1
                        freshness = "🟢" if days_old <= 1 else "🟡" if days_old <= 3 else "🟠" if days_old <= 7 else "🔴"
                        print(f"  {freshness} {table:30s} — latest: {latest}, {days_old}d old, {recent_count:,} rows (7d)")
                        results.append({"table": table, "latest": str(latest), "days_old": days_old, "recent_count": recent_count})
                    else:
                        print(f"  ⚫ {table:30s} — EMPTY (no data)")
                        results.append({"table": table, "latest": None, "days_old": -1, "recent_count": 0})
                else:
                    # No event_date or timestamp column, just count
                    cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table_name}"')
                    count = cur.fetchone()[0]
                    print(f"  ❓ {table:30s} — no date column, {count:,} total rows")
                    results.append({"table": table, "latest": "unknown", "days_old": -1, "recent_count": count})

        except Exception as e:
            print(f"  ✗ {table:30s} — error: {e}")
            results.append({"table": table, "latest": "error", "days_old": -1, "recent_count": 0})

    print()
    print("  Legend: 🟢 Fresh (≤1d) | 🟡 OK (2-3d) | 🟠 Stale (4-7d) | 🔴 Old (>7d) | ⚫ Empty")

    return results


def section_7_wiring_integrity(cur, verbose: bool = False):
    """Section 7: Wiring Integrity — source → table → tracking complete."""
    print_header("WIRING INTEGRITY CHECK", 7)

    print("  Verifying end-to-end data flow for each function:\n")

    results = {"complete": [], "incomplete": []}

    for func_id, config in sorted(INNGEST_FUNCTION_REGISTRY.items()):
        job_name = config["job_name"]
        target_tables = get_target_tables(config)

        issues = []

        # Check 1: Tables exist
        missing_tables = []
        for table in target_tables:
            schema, table_name = table.split(".")
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                )
            """, (schema, table_name))
            if not cur.fetchone()[0]:
                missing_tables.append(table)

        if missing_tables:
            issues.append(f"missing tables: {', '.join(missing_tables)}")

        # Check 2: Has recent data (for daily jobs)
        if config.get("frequency") == "daily" and not issues:
            try:
                has_recent = False
                for table in target_tables:
                    schema, table_name = table.split(".")
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = %s
                            AND table_name = %s
                            AND column_name = 'event_date'
                        )
                    """, (schema, table_name))
                    if not cur.fetchone()[0]:
                        continue
                    cur.execute(f"""
                        SELECT EXISTS (
                            SELECT 1 FROM "{schema}"."{table_name}"
                            WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
                            LIMIT 1
                        )
                    """)
                    if cur.fetchone()[0]:
                        has_recent = True
                        break

                if not has_recent:
                    issues.append("no recent data")
            except Exception:
                pass  # May not have event_date column

        # Check 3: Has tracking records
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'ops' AND table_name = 'ingest_run'
            )
        """)
        if cur.fetchone()[0]:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM ops.ingest_run
                    WHERE job_name = %s
                    LIMIT 1
                )
            """, (job_name,))
            if not cur.fetchone()[0]:
                issues.append("no tracking")

        # Report
        if issues:
            print(f"  ⚠ {func_id:35s} — {', '.join(issues)}")
            results["incomplete"].append({"function": func_id, "issues": issues})
        else:
            if verbose:
                print(f"  ✓ {func_id:35s} — wiring complete")
            results["complete"].append(func_id)

    print()
    print(f"  Summary: {len(results['complete'])} complete, {len(results['incomplete'])} with issues")

    return results


def section_8_true_success(cur, verbose: bool = False):
    """Section 8: True Success Confirmations — verify data matches expectations."""
    print_header("TRUE SUCCESS CONFIRMATIONS", 8)

    print("  Running validation queries to confirm 'true success':\n")

    validations = []

    # ─── Validation 1: ZL prices in mkt.futures_1d ────────────────────────────
    print_subheader("ZL Prices (Core Product)")
    try:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE event_date >= CURRENT_DATE - INTERVAL '7 days') as last_7d,
                MAX(event_date) as latest,
                AVG(close) FILTER (WHERE event_date >= CURRENT_DATE - INTERVAL '30 days') as avg_close_30d
            FROM mkt.futures_1d
            WHERE symbol = 'ZL'
        """)
        row = cur.fetchone()
        total, last_7d, latest, avg_close = row

        success = last_7d >= 3 and latest and (datetime.now().date() - latest).days <= 3
        status = "✓ PASS" if success else "✗ FAIL"
        avg_close_str = f"{avg_close:.2f}" if avg_close is not None else "0.00"
        print(f"  │  {status}: {total:,} total rows, {last_7d} in last 7d, latest={latest}, avg_close=${avg_close_str}")
        validations.append({"check": "ZL prices", "success": success, "details": {"total": total, "last_7d": last_7d}})
    except Exception as e:
        print(f"  │  ✗ ERROR: {e}")
        validations.append({"check": "ZL prices", "success": False, "error": str(e)})

    # ─── Validation 2: ZL dashboard copy ──────────────────────────────────────
    print_subheader("ZL Dashboard Copy (analytics.zl_price_1d)")
    try:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE event_date >= CURRENT_DATE - INTERVAL '7 days') as last_7d,
                MAX(event_date) as latest
            FROM analytics.zl_price_1d
        """)
        total, last_7d, latest = cur.fetchone()
        success = last_7d >= 3 and latest and (datetime.now().date() - latest).days <= 3
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  │  {status}: {total:,} total rows, {last_7d} in last 7d, latest={latest}")
        validations.append({"check": "ZL dashboard copy", "success": success, "details": {"total": total, "last_7d": last_7d}})
    except Exception as e:
        print(f"  │  ✗ ERROR: {e}")
        validations.append({"check": "ZL dashboard copy", "success": False, "error": str(e)})

    # ─── Validation 3: FRED data landing ──────────────────────────────────────
    print_subheader("FRED Series (Macro Data)")
    for table in FRED_TARGET_TABLES:
        try:
            schema, tbl = table.split(".")
            cur.execute(f"""
                SELECT
                    COUNT(DISTINCT series_id) as series_count,
                    COUNT(*) FILTER (WHERE event_date >= CURRENT_DATE - INTERVAL '7 days') as recent
                FROM "{schema}"."{tbl}"
            """)
            series_count, recent = cur.fetchone()
            success = series_count > 0
            status = "✓" if success else "✗"
            print(f"  │  {status} {table:25s}: {series_count:>3} series, {recent:>5} recent rows")
            validations.append({"check": f"FRED {table}", "success": success, "series_count": series_count})
        except Exception as e:
            print(f"  │  ✗ {table:25s}: error - {e}")

    # ─── Validation 4: CFTC COT data ──────────────────────────────────────────
    print_subheader("CFTC COT (Positioning)")
    try:
        cur.execute("""
            SELECT
                COUNT(DISTINCT symbol) as symbols,
                COUNT(*) as total,
                MAX(event_date) as latest
            FROM pos.cftc_1w
        """)
        symbols, total, latest = cur.fetchone()
        success = symbols >= 5 and total > 0
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  │  {status}: {symbols} symbols, {total:,} rows, latest={latest}")
        validations.append({"check": "CFTC COT", "success": success, "symbols": symbols})
    except Exception as e:
        print(f"  │  ✗ ERROR: {e}")
        validations.append({"check": "CFTC COT", "success": False, "error": str(e)})

    # ─── Validation 5: WASDE data ─────────────────────────────────────────────
    print_subheader("USDA WASDE (Supply)")
    try:
        cur.execute("""
            SELECT
                COUNT(DISTINCT event_date) as reports,
                COUNT(DISTINCT commodity) as commodities,
                MAX(event_date) as latest
            FROM supply.usda_wasde_1m
        """)
        reports, commodities, latest = cur.fetchone()
        success = reports > 0 and commodities >= 3
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  │  {status}: {reports} reports, {commodities} commodities, latest={latest}")
        validations.append({"check": "USDA WASDE", "success": success, "reports": reports})
    except Exception as e:
        print(f"  │  ✗ ERROR: {e}")
        validations.append({"check": "USDA WASDE", "success": False, "error": str(e)})

    # ─── Validation 6: News data ──────────────────────────────────────────────
    print_subheader("News Articles (alt.news_1d)")
    try:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE event_date >= CURRENT_DATE - INTERVAL '7 days') as recent,
                COUNT(DISTINCT source) as sources
            FROM alt.news_1d
        """)
        total, recent, sources = cur.fetchone()
        success = total > 0
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  │  {status}: {total:,} total, {recent} recent, {sources} sources")
        validations.append({"check": "News articles", "success": success, "total": total})
    except Exception as e:
        print(f"  │  ✗ ERROR: {e}")
        validations.append({"check": "News articles", "success": False, "error": str(e)})

    # ─── Summary ──────────────────────────────────────────────────────────────
    print()
    passed = sum(1 for v in validations if v.get("success"))
    failed = len(validations) - passed
    print(f"  TRUE SUCCESS SUMMARY: {passed}/{len(validations)} validations passed")

    if failed > 0:
        print(f"\n  ⚠️  {failed} validations failed — investigate data flows!")

    return {"passed": passed, "failed": failed, "validations": validations}


def run_audit(sections: list = None, verbose: bool = False, dry_run: bool = False):
    """Run the full audit or specific sections."""

    print("\n" + "╔" + "═" * 78 + "╗")
    print("║" + " ELITE TEAM BRAVO — INNGEST INTEGRATION DEEP AUDIT ".center(78) + "║")
    print("║" + f" Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ".center(78) + "║")
    print("╚" + "═" * 78 + "╝")

    if dry_run:
        print("\n  [DRY RUN MODE — showing what would be checked]\n")
        print("  Sections available:")
        print("    1. Inngest Function Registry")
        print("    2. Cron Schedule Mapping")
        print("    3. Target Table Validation")
        print("    4. ops.ingest_run Tracking")
        print("    5. Recent Execution History")
        print("    6. Data Freshness Check")
        print("    7. Wiring Integrity")
        print("    8. True Success Confirmations")
        return

    conn = get_connection()
    cur = conn.cursor()

    all_sections = [
        (1, section_1_function_registry),
        (2, section_2_cron_schedule),
        (3, section_3_target_tables),
        (4, section_4_ingest_run_tracking),
        (5, section_5_execution_history),
        (6, section_6_data_freshness),
        (7, section_7_wiring_integrity),
        (8, section_8_true_success),
    ]

    results = {}

    for section_num, section_func in all_sections:
        if sections and section_num not in sections:
            continue

        try:
            result = section_func(cur, verbose=verbose)
            results[section_num] = {"status": "complete", "data": result}
        except Exception as e:
            print(f"\n  ❌ Section {section_num} failed: {e}")
            results[section_num] = {"status": "error", "error": str(e)}

    cur.close()
    conn.close()

    # Final summary
    print("\n" + "═" * 80)
    print("  AUDIT COMPLETE")
    print("═" * 80)

    completed = sum(1 for r in results.values() if r["status"] == "complete")
    errors = sum(1 for r in results.values() if r["status"] == "error")
    print(f"  Sections completed: {completed}")
    if errors:
        print(f"  Sections with errors: {errors}")

    # Key findings
    if 8 in results and results[8]["status"] == "complete":
        data = results[8]["data"]
        passed = data.get("passed", 0)
        failed = data.get("failed", 0)
        if failed > 0:
            print(f"\n  ⚠️  ACTION REQUIRED: {failed} true success validations failed")
        else:
            print(f"\n  ✅ All {passed} true success validations passed")

    print()
    return results


def main():
    parser = argparse.ArgumentParser(description="Elite Team Bravo — Inngest Integration Audit")
    parser.add_argument("--section", type=int, help="Run specific section (1-8)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be checked")

    args = parser.parse_args()

    sections = [args.section] if args.section else None

    run_audit(sections=sections, verbose=args.verbose, dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
