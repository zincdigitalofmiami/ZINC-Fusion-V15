#!/usr/bin/env python3
"""Backfill training.model_runs_event from training.oof_core_1d.

This script restores MAE provenance rows expected by forecast-target APIs.
Default target is LOCAL_DATABASE_URL and localhost hosts only.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import psycopg2

LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "host.docker.internal",
}

AGG_SQL = """
SELECT
    run_hash,
    horizon_days,
    to_char(MAX(COALESCE(cutoff_date, trade_date)), 'YYYY-MM-DD') AS trained_date,
    COUNT(*)::int AS oof_count,
    AVG(ABS(predicted_price - target_value)) FILTER (WHERE target_value IS NOT NULL) AS mae
FROM training.oof_core_1d
GROUP BY run_hash, horizon_days
ORDER BY horizon_days, run_hash
"""

UPSERT_SQL = """
INSERT INTO training.model_runs_event (
    model_name,
    model_nickname,
    horizon_days,
    trained_date,
    run_hash,
    mae,
    coverage_30_70,
    oof_count,
    status,
    outcome,
    notes
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (run_hash, horizon_days)
DO UPDATE SET
    model_name = EXCLUDED.model_name,
    model_nickname = EXCLUDED.model_nickname,
    trained_date = EXCLUDED.trained_date,
    mae = EXCLUDED.mae,
    coverage_30_70 = EXCLUDED.coverage_30_70,
    oof_count = EXCLUDED.oof_count,
    status = EXCLUDED.status,
    outcome = EXCLUDED.outcome,
    notes = EXCLUDED.notes
"""


@dataclass(frozen=True)
class Endpoint:
    raw: str
    host: str
    database: str


def resolve_database_url(explicit_url: str | None) -> str:
    if explicit_url:
        return explicit_url.strip()

    for key in (
        "LOCAL_DATABASE_URL",
        "DIRECT_DATABASE_URL",
        "POSTGRES_URL",
        "DATABASE_URL",
    ):
        value = (os.getenv(key) or "").strip()
        if value:
            return value

    raise ValueError(
        "no database URL found; set LOCAL_DATABASE_URL (preferred) or DIRECT_DATABASE_URL/POSTGRES_URL/DATABASE_URL"
    )


def parse_endpoint(raw_url: str) -> Endpoint:
    parsed = urlparse(raw_url)
    host = (parsed.hostname or "").strip().lower()
    database = (parsed.path or "").lstrip("/").strip()
    if not host or not database:
        raise ValueError("database URL must include host and database name")
    return Endpoint(raw=raw_url, host=host, database=database)


def expected_local_db_name() -> str | None:
    return (
        os.getenv("LOCAL_DB_EXPECTED_NAME") or os.getenv("EXPECTED_DB_NAME") or ""
    ).strip() or None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill training.model_runs_event from training.oof_core_1d"
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="explicit database URL (otherwise resolves from env)",
    )
    parser.add_argument(
        "--allow-remote-host",
        action="store_true",
        help="allow non-localhost targets",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print planned upserts without writing",
    )
    parser.add_argument("--model-name", default="core_weighted_ensemble")
    parser.add_argument("--model-nickname", default="oof_backfill")
    parser.add_argument("--status", default="promoted")
    parser.add_argument("--outcome", default="success")
    args = parser.parse_args()

    try:
        db_url = resolve_database_url(args.database_url)
        endpoint = parse_endpoint(db_url)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    if not args.allow_remote_host and endpoint.host not in LOCAL_HOSTS:
        print(
            f"ERROR: refusing to write to non-local host {endpoint.host!r}; use --allow-remote-host if intentional"
        )
        return 1

    expected_db = expected_local_db_name()
    if expected_db and endpoint.database != expected_db:
        print(
            "ERROR: refusing to write to database "
            f"{endpoint.database!r}; expected {expected_db!r}"
        )
        return 1

    note_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    note = (
        "Backfilled from training.oof_core_1d via scripts/backfill_model_runs_event.py "
        f"at {note_timestamp}"
    )

    inserted_or_updated = 0
    with psycopg2.connect(endpoint.raw) as conn:
        with conn.cursor() as cur:
            cur.execute(AGG_SQL)
            rows = cur.fetchall()

            if not rows:
                print("No rows found in training.oof_core_1d; nothing to backfill")
                return 0

            print(
                f"Backfilling model_runs_event from {len(rows)} grouped run_hash/horizon rows in {endpoint.host}/{endpoint.database}"
            )

            for run_hash, horizon_days, trained_date, oof_count, mae in rows:
                payload = (
                    args.model_name,
                    args.model_nickname,
                    int(horizon_days),
                    trained_date,
                    run_hash,
                    float(mae) if mae is not None else None,
                    None,
                    int(oof_count),
                    args.status,
                    args.outcome,
                    note,
                )

                if args.dry_run:
                    print(
                        f"DRY-RUN horizon={horizon_days} run_hash={run_hash} trained_date={trained_date} oof_count={oof_count} mae={mae}"
                    )
                else:
                    cur.execute(UPSERT_SQL, payload)
                    inserted_or_updated += 1

        if args.dry_run:
            conn.rollback()
            print("Dry run complete; no writes committed")
        else:
            conn.commit()
            print(f"Committed upserts: {inserted_or_updated}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
