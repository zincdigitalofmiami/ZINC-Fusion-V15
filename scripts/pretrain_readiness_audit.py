#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Pre-Training Readiness Audit (SoT v2)

Read-only safety contract:
  - Connects to Prisma Postgres via DATABASE_URL
  - Runs SELECT-only checks (no DDL/DML)
  - Fails loudly (non-zero exit) if critical blockers are present when --strict is set

This is intended to answer: "Are we ready to run v2 training jobs without leaking,
joining on the wrong time key, or training on stale/synthetic inputs?"
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence

import psycopg2
from dotenv import load_dotenv


@dataclass(frozen=True)
class TableCheck:
    schema: str
    table: str
    date_col: Optional[str]
    label: str
    stale_days_warn: Optional[int] = None
    stale_days_fail: Optional[int] = None


def load_env() -> None:
    load_dotenv(dotenv_path=Path.cwd() / ".env")


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not found in environment (expected in .env)")
    return url


def table_exists(cur, schema: str, table: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema=%s AND table_name=%s
        LIMIT 1
        """,
        (schema, table),
    )
    return cur.fetchone() is not None


def get_columns(cur, schema: str, table: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    return [r[0] for r in cur.fetchall()]


def get_count(cur, schema: str, table: str) -> int:
    cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
    return int(cur.fetchone()[0])


def get_min_max(cur, schema: str, table: str, date_col: str) -> tuple[Optional[date], Optional[date]]:
    cur.execute(
        f'SELECT MIN({date_col})::date, MAX({date_col})::date FROM "{schema}"."{table}"'
    )
    mn, mx = cur.fetchone()
    return mn, mx


def days_stale(latest: Optional[date], today: date) -> Optional[int]:
    if latest is None:
        return None
    return (today - latest).days


def print_kv(label: str, value: str) -> None:
    print(f"- {label}: {value}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-training readiness audit (read-only).")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if critical blockers are present.",
    )
    args = parser.parse_args(argv)

    load_env()
    url = get_database_url()

    now = datetime.now(timezone.utc)
    today = date.today()

    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()

    blockers: list[str] = []
    warnings: list[str] = []
    had_errors = False

    try:
        print("# ZINC-FUSION-V15: Pre-Training Readiness Audit (SoT v2)")
        print(f"- Generated at: {now.isoformat()}")
        print(f"- Today (local): {today.isoformat()}")
        print()

        # ------------------------------------------------------------------
        # 1) Metadata governance
        # ------------------------------------------------------------------
        print("## Metadata Coverage")
        if not table_exists(cur, "metadata", "symbol_mapping"):
            blockers.append("Missing table: metadata.symbol_mapping")
            print_kv("metadata.symbol_mapping", "MISSING")
        else:
            cur.execute("SELECT COUNT(*) FROM metadata.symbol_mapping")
            mapping_rows = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(DISTINCT canonical_id) FROM metadata.symbol_mapping")
            mapped_canonical = int(cur.fetchone()[0])
            print_kv("metadata.symbol_mapping rows", str(mapping_rows))
            print_kv("metadata.symbol_mapping canonical_id", str(mapped_canonical))

        if table_exists(cur, "raw", "market_futures_1d") and table_exists(
            cur, "metadata", "symbol_mapping"
        ):
            cur.execute("SELECT COUNT(DISTINCT symbol) FROM raw.market_futures_1d")
            raw_symbols = int(cur.fetchone()[0])
            cur.execute(
                """
                SELECT COUNT(*)
                FROM (SELECT DISTINCT symbol FROM raw.market_futures_1d) s
                WHERE NOT EXISTS (
                  SELECT 1 FROM metadata.symbol_mapping m
                  WHERE m.source_table='raw.market_futures_1d' AND m.source_symbol=s.symbol
                )
                """
            )
            missing = int(cur.fetchone()[0])
            print_kv("raw.market_futures_1d distinct symbols", str(raw_symbols))
            print_kv("missing mappings (raw.market_futures_1d)", f"{missing} / {raw_symbols}")
            if missing > 0:
                warnings.append(
                    f"metadata.symbol_mapping missing {missing}/{raw_symbols} symbols for raw.market_futures_1d"
                )

        print()

        # ------------------------------------------------------------------
        # 2) Raw freshness (training inputs)
        # ------------------------------------------------------------------
        raw_checks: list[TableCheck] = [
            TableCheck("raw", "market_futures_1d", "event_date", "Market futures (1d)", stale_days_warn=5, stale_days_fail=14),
            TableCheck("raw", "fred_observations_1d", "event_date", "FRED observations (1d)", stale_days_warn=5, stale_days_fail=14),
            TableCheck("raw", "fx_spot_1d", "event_date", "FX spot (1d)", stale_days_warn=7, stale_days_fail=14),
            TableCheck("raw", "cftc_cot_1w", "event_date", "CFTC COT (1w)", stale_days_warn=14, stale_days_fail=28),
            TableCheck("raw", "weather_noaa_1d", "event_date", "NOAA weather (1d)", stale_days_warn=5, stale_days_fail=14),
            TableCheck("raw", "usda_export_sales_1w", "event_date", "USDA export sales (1w)", stale_days_warn=14, stale_days_fail=28),
            TableCheck("raw", "usda_wasde_1m", "event_date", "USDA WASDE (1m)", stale_days_warn=21, stale_days_fail=31),
            TableCheck("raw", "epa_rin_prices_1d", "event_date", "EPA RIN prices (1d)", stale_days_warn=14, stale_days_fail=28),
            TableCheck("raw", "news_articles_event", "event_date", "News (event)", stale_days_warn=7, stale_days_fail=30),
            TableCheck("raw", "whitehouse_actions_event", "event_date", "White House actions (event)", stale_days_warn=7, stale_days_fail=30),
        ]

        print("## Raw Data Freshness (Inputs)")
        for chk in raw_checks:
            if not table_exists(cur, chk.schema, chk.table):
                blockers.append(f"Missing table: {chk.schema}.{chk.table}")
                print_kv(chk.label, "MISSING")
                continue
            try:
                cnt = get_count(cur, chk.schema, chk.table)
                if chk.date_col:
                    mn, mx = get_min_max(cur, chk.schema, chk.table, chk.date_col)
                    stale = days_stale(mx, today)
                    stale_str = "unknown"
                    if stale is not None:
                        stale_str = f"{stale}d"
                        if stale < 0:
                            stale_str = f"{stale}d (future-dated)"
                    print_kv(chk.label, f"{cnt:,} rows | {mn} → {mx} | stale={stale_str}")

                    if stale is None:
                        warnings.append(f"{chk.schema}.{chk.table}: no {chk.date_col} values")
                    else:
                        if stale < 0:
                            warnings.append(f"{chk.schema}.{chk.table}: has future-dated max {mx}")
                        if chk.stale_days_fail is not None and stale > chk.stale_days_fail:
                            blockers.append(
                                f"{chk.schema}.{chk.table} stale {stale}d (>{chk.stale_days_fail}d)"
                            )
                        elif chk.stale_days_warn is not None and stale > chk.stale_days_warn:
                            warnings.append(
                                f"{chk.schema}.{chk.table} stale {stale}d (>{chk.stale_days_warn}d)"
                            )
                else:
                    print_kv(chk.label, f"{cnt:,} rows")
            except Exception as e:
                had_errors = True
                try:
                    conn.rollback()
                except Exception:
                    pass
                blockers.append(f"Error reading {chk.schema}.{chk.table}: {e}")
                print_kv(chk.label, f"ERROR: {e}")

        # Special: future-dated FRED rows
        if table_exists(cur, "raw", "fred_observations_1d"):
            try:
                cur.execute(
                    "SELECT COUNT(*) FROM raw.fred_observations_1d WHERE event_date::date > current_date"
                )
                future_cnt = int(cur.fetchone()[0])
                if future_cnt:
                    warnings.append(f"raw.fred_observations_1d has {future_cnt} future-dated rows")
            except Exception as e:
                had_errors = True
                warnings.append(f"Could not check future-dated FRED rows: {e}")

        print()

        # ------------------------------------------------------------------
        # 2b) Silver/Gold feature availability (sanity)
        # ------------------------------------------------------------------
        print("## Feature Tables (Silver/Gold/Features)")

        # features.trump_effect_1d
        if table_exists(cur, "features", "trump_effect_1d"):
            cnt = get_count(cur, "features", "trump_effect_1d")
            mn, mx = get_min_max(cur, "features", "trump_effect_1d", "as_of_date")
            print_kv("features.trump_effect_1d", f"{cnt:,} rows | {mn} → {mx}")
            # Compare to raw.whitehouse_actions_event freshness if available
            if table_exists(cur, "raw", "whitehouse_actions_event"):
                _, raw_max = get_min_max(cur, "raw", "whitehouse_actions_event", "event_date")
                if raw_max and mx and raw_max > mx:
                    warnings.append(
                        f"features.trump_effect_1d lags raw.whitehouse_actions_event ({mx} < {raw_max})"
                    )
        else:
            warnings.append("features.trump_effect_1d missing (trump_effect feature store unavailable)")

        # mkt.futures_1d (canonical OHLCV)
        if table_exists(cur, "silver", "futures_prices_1d"):
            cur.execute(
                """
                SELECT COUNT(*)::int, MIN(trade_date)::date, MAX(trade_date)::date
                FROM mkt.futures_1d
                WHERE canonical_id='ZL'
                """
            )
            cnt, mn, mx = cur.fetchone()
            print_kv("mkt.futures_1d[ZL]", f"{cnt:,} rows | {mn} → {mx}")
        else:
            warnings.append("mkt.futures_1d missing (silver canonical prices unavailable)")

        # features.elite_1d (denormalized indicators)
        if table_exists(cur, "gold", "elite_indicators_1d"):
            cur.execute(
                """
                SELECT COUNT(*)::int, MIN(trade_date)::date, MAX(trade_date)::date
                FROM features.elite_1d
                WHERE symbol='ZL'
                """
            )
            cnt, mn, mx = cur.fetchone()
            cur.execute("SELECT COUNT(DISTINCT symbol)::int FROM features.elite_1d")
            distinct_symbols = int(cur.fetchone()[0])
            print_kv(
                "features.elite_1d[ZL]",
                f"{cnt:,} rows | {mn} → {mx} | symbols={distinct_symbols}",
            )
        else:
            warnings.append("features.elite_1d missing (gold indicators unavailable)")

        print()

        # ------------------------------------------------------------------
        # 3) Feature stores + training tables
        # ------------------------------------------------------------------
        print("## Feature Stores")
        if table_exists(cur, "training", "specialist_features"):
            cur.execute(
                """
                SELECT bucket, COUNT(*)::int, MIN(as_of_date)::date, MAX(as_of_date)::date
                FROM training.specialist_features
                GROUP BY bucket
                ORDER BY bucket
                """
            )
            rows = cur.fetchall()
            print_kv("training.specialist_features buckets", str(len(rows)))
            for bucket, cnt, mn, mx in rows:
                print(f"- training.specialist_features[{bucket}]: {cnt:,} rows | {mn} → {mx}")
        else:
            blockers.append("Missing table: training.specialist_features")
            print_kv("training.specialist_features", "MISSING")

        if table_exists(cur, "training", "core_features"):
            cnt = get_count(cur, "training", "core_features")
            mn, mx = get_min_max(cur, "training", "core_features", "as_of_date")
            print_kv("training.core_features", f"{cnt:,} rows | {mn} → {mx} (JSON blob, no targets)")
        else:
            blockers.append("Missing table: training.core_features")
            print_kv("training.core_features", "MISSING")

        if table_exists(cur, "training", "core_matrix_1d"):
            cnt = get_count(cur, "training", "core_matrix_1d")
            print_kv("training.core_matrix_1d", f"{cnt:,} rows (SoT v2 matrix)")
            if cnt == 0:
                blockers.append("training.core_matrix_1d is empty (cannot train L0 core)")
            cols = set(get_columns(cur, "training", "core_matrix_1d"))
            required_targets = {"target_5d", "target_21d", "target_63d", "target_126d"}
            missing_targets = sorted(required_targets - cols)
            if missing_targets:
                blockers.append(
                    f"training.core_matrix_1d missing targets: {', '.join(missing_targets)}"
                )
        else:
            blockers.append("Missing table: training.core_matrix_1d")
            print_kv("training.core_matrix_1d", "MISSING")

        # Specialist staging tables (current DB reality)
        buckets = [
            "crush",
            "china",
            "fx",
            "fed",
            "tariff",
            "energy",
            "biofuel",
            "palm",
            "volatility",
            "substitutes",
            "trump_effect",
        ]
        required_targets = {"target_5d", "target_21d", "target_63d", "target_126d"}

        print()
        print("## Specialist Tables (training.specialist_*_1d)")
        for bucket in buckets:
            table = f"specialist_{bucket}_1d"
            if not table_exists(cur, "training", table):
                blockers.append(f"Missing table: training.{table}")
                print_kv(f"training.{table}", "MISSING")
                continue

            cnt = get_count(cur, "training", table)
            mn, mx = get_min_max(cur, "training", table, "as_of_date")
            cols = set(get_columns(cur, "training", table))
            missing_targets = sorted(required_targets - cols)

            print_kv(f"training.{table}", f"{cnt:,} rows | {mn} → {mx} | missing_targets={len(missing_targets)}")
            if missing_targets:
                blockers.append(f"training.{table} missing targets: {', '.join(missing_targets)}")

        # OOF + meta inputs existence (should be empty before training)
        print()
        print("## SoT v2 Output Tables (expected empty before training)")

        # training.oof_* tables
        cur.execute(
            """
            SELECT COUNT(*)::int
            FROM information_schema.tables
            WHERE table_schema='training' AND table_name LIKE 'oof_%'
            """
        )
        oof_tables = int(cur.fetchone()[0])
        print_kv("training.oof_* table count", str(oof_tables))
        if oof_tables != 48:
            warnings.append(f"Expected 48 training.oof_* tables, found {oof_tables}")

        # meta_inputs tables
        for h in (5, 21, 63, 126):
            table = f"meta_inputs_{h}d_1d"
            if not table_exists(cur, "training", table):
                blockers.append(f"Missing table: training.{table}")
                print_kv(f"training.{table}", "MISSING")
                continue
            cnt = get_count(cur, "training", table)
            print_kv(f"training.{table}", f"{cnt:,} rows")

        # forecasts production tables
        for h in (5, 21, 63, 126):
            table = f"production_{h}d_1d"
            if not table_exists(cur, "forecasts", table):
                blockers.append(f"Missing table: forecasts.{table}")
                print_kv(f"forecasts.{table}", "MISSING")
                continue
            cnt = get_count(cur, "forecasts", table)
            print_kv(f"forecasts.{table}", f"{cnt:,} rows")

        # analytics scenario/event tables
        for h in (5, 21, 63, 126):
            t1 = f"price_scenarios_{h}d_1d"
            t2 = f"event_probabilities_{h}d_1d"
            if not table_exists(cur, "analytics", t1):
                blockers.append(f"Missing table: analytics.{t1}")
                print_kv(f"analytics.{t1}", "MISSING")
            else:
                print_kv(f"analytics.{t1}", f"{get_count(cur, 'analytics', t1):,} rows")
            if not table_exists(cur, "analytics", t2):
                blockers.append(f"Missing table: analytics.{t2}")
                print_kv(f"analytics.{t2}", "MISSING")
            else:
                print_kv(f"analytics.{t2}", f"{get_count(cur, 'analytics', t2):,} rows")

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        print()
        print("## Verdict")
        if blockers:
            print_kv("Pre-training ready", "NO")
        else:
            print_kv("Pre-training ready", "YES")

        if blockers:
            print()
            print("### Blockers")
            for b in blockers:
                print(f"- {b}")

        if warnings:
            print()
            print("### Warnings")
            for w in warnings:
                print(f"- {w}")

        if had_errors:
            print()
            print("### Audit Errors")
            print("- One or more queries failed; see output above.")

        if args.strict and blockers:
            return 1
        return 0 if not had_errors else 2

    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
