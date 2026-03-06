#!/usr/bin/env python3
"""Sync audit-critical tables from cloud Postgres to local Postgres.

Usage:
  CLOUD_DATABASE_URL='postgresql://...' \
  LOCAL_DATABASE_URL='postgresql://...' \
  .venv/bin/python scripts/sync_cloud_to_local_db.py

Defaults enforce safety:
- source must look like cloud (default host contains db.prisma.io)
- destination must be localhost
- source and destination endpoints must differ
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

import psycopg2
from psycopg2 import sql

DEFAULT_TABLES = [
    "forecasts.production_1d",
    "training.matrix_1d",
    "training.specialist_signals_1d",
    "training.oof_core_1d",
]

LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "host.docker.internal",
}

TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class Endpoint:
    raw: str
    host: str
    port: int | None
    database: str

    @property
    def display(self) -> str:
        port = f":{self.port}" if self.port else ""
        return f"{self.host}{port}/{self.database}"


def parse_endpoint(raw_url: str) -> Endpoint:
    parsed = urlparse(raw_url)
    host = (parsed.hostname or "").strip().lower()
    database = (parsed.path or "").lstrip("/").strip()
    if not host or not database:
        raise ValueError("URL must include host and database name")
    return Endpoint(raw=raw_url, host=host, port=parsed.port, database=database)


def is_local_host(host: str) -> bool:
    return host in LOCAL_HOSTS


def load_required_url(env_name: str) -> str:
    value = (os.getenv(env_name) or "").strip()
    if not value:
        raise ValueError(f"environment variable {env_name} is required")
    return value


def parse_tables(raw_tables: str) -> list[tuple[str, str]]:
    tables = [entry.strip() for entry in raw_tables.split(",") if entry.strip()]
    if not tables:
        raise ValueError("at least one table is required")

    parsed: list[tuple[str, str]] = []
    for full_name in tables:
        if not TABLE_RE.match(full_name):
            raise ValueError(
                f"invalid table reference {full_name!r}; expected schema.table with lowercase identifiers"
            )
        schema, table = full_name.split(".", 1)
        parsed.append((schema, table))
    return parsed


def row_count(conn: psycopg2.extensions.connection, schema: str, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                sql.Identifier(schema),
                sql.Identifier(table),
            )
        )
        return int(cur.fetchone()[0])


def ensure_safe_routing(
    source: Endpoint,
    destination: Endpoint,
    expected_cloud_host: str,
    expected_destination_db: str | None,
) -> None:
    if source.host == destination.host and source.database == destination.database:
        raise ValueError(
            "source and destination resolve to the same endpoint; refusing to run"
        )

    if is_local_host(source.host):
        raise ValueError(
            f"source endpoint must be cloud, got local host {source.host!r}"
        )

    if expected_cloud_host and expected_cloud_host not in source.host:
        raise ValueError(
            f"source host {source.host!r} does not contain expected cloud host fragment {expected_cloud_host!r}"
        )

    if not is_local_host(destination.host):
        raise ValueError(
            f"destination endpoint must be localhost, got {destination.host!r}"
        )

    if expected_destination_db and destination.database != expected_destination_db:
        raise ValueError(
            "destination database mismatch: "
            f"expected {expected_destination_db!r}, got {destination.database!r}"
        )


def copy_table(
    source_conn: psycopg2.extensions.connection,
    dest_conn: psycopg2.extensions.connection,
    schema: str,
    table: str,
    truncate: bool,
) -> tuple[int, int]:
    source_count = row_count(source_conn, schema, table)

    with source_conn.cursor() as source_cur, dest_conn.cursor() as dest_cur:
        if truncate:
            dest_cur.execute(
                sql.SQL("TRUNCATE TABLE {}.{} CASCADE").format(
                    sql.Identifier(schema),
                    sql.Identifier(table),
                )
            )

        buffer = io.StringIO()
        source_cur.copy_expert(
            sql.SQL("COPY {}.{} TO STDOUT WITH (FORMAT CSV)")
            .format(
                sql.Identifier(schema),
                sql.Identifier(table),
            )
            .as_string(source_conn),
            buffer,
        )
        buffer.seek(0)
        dest_cur.copy_expert(
            sql.SQL("COPY {}.{} FROM STDIN WITH (FORMAT CSV)")
            .format(
                sql.Identifier(schema),
                sql.Identifier(table),
            )
            .as_string(dest_conn),
            buffer,
        )

    dest_conn.commit()
    dest_count = row_count(dest_conn, schema, table)
    return source_count, dest_count


def format_table(schema: str, table: str) -> str:
    return f"{schema}.{table}"


def run_sync(
    source_url: str,
    destination_url: str,
    tables: Iterable[tuple[str, str]],
    expected_cloud_host: str,
    expected_destination_db: str | None,
    truncate: bool,
) -> int:
    source = parse_endpoint(source_url)
    destination = parse_endpoint(destination_url)
    ensure_safe_routing(
        source,
        destination,
        expected_cloud_host,
        expected_destination_db,
    )

    print("Cloud to local sync")
    print(f"source      : {source.display}")
    print(f"destination : {destination.display}")
    print(f"truncate    : {truncate}")

    failures = 0
    with (
        psycopg2.connect(source.raw) as source_conn,
        psycopg2.connect(destination.raw) as dest_conn,
    ):
        for schema, table in tables:
            label = format_table(schema, table)
            print(f"\nSyncing {label} ...")
            try:
                src_count, dst_count = copy_table(
                    source_conn,
                    dest_conn,
                    schema,
                    table,
                    truncate,
                )
                status = "OK" if src_count == dst_count else "MISMATCH"
                print(
                    f"  source_rows={src_count:,} destination_rows={dst_count:,} status={status}"
                )
                if src_count != dst_count:
                    failures += 1
            except Exception as exc:  # noqa: BLE001
                dest_conn.rollback()
                failures += 1
                print(f"  ERROR: {exc}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync audit-critical tables from cloud DB to local DB"
    )
    parser.add_argument(
        "--source-env",
        default="CLOUD_DATABASE_URL",
        help="environment variable containing cloud DB URL (default: CLOUD_DATABASE_URL)",
    )
    parser.add_argument(
        "--dest-env",
        default="LOCAL_DATABASE_URL",
        help="environment variable containing local DB URL (default: LOCAL_DATABASE_URL)",
    )
    parser.add_argument(
        "--tables",
        default=",".join(DEFAULT_TABLES),
        help="comma-separated schema.table list to sync",
    )
    parser.add_argument(
        "--expected-cloud-host",
        default=os.getenv("EXPECTED_CLOUD_DB_HOST", "db.prisma.io"),
        help="required cloud host fragment (default: db.prisma.io)",
    )
    parser.add_argument(
        "--expected-dest-db",
        default=os.getenv("LOCAL_DB_EXPECTED_NAME") or os.getenv("EXPECTED_DB_NAME"),
        help=(
            "required destination database name "
            "(default: LOCAL_DB_EXPECTED_NAME or EXPECTED_DB_NAME)"
        ),
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="do not truncate destination tables before copy",
    )
    args = parser.parse_args()

    try:
        source_url = load_required_url(args.source_env)
        destination_url = load_required_url(args.dest_env)
        tables = parse_tables(args.tables)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    try:
        failures = run_sync(
            source_url=source_url,
            destination_url=destination_url,
            tables=tables,
            expected_cloud_host=args.expected_cloud_host,
            expected_destination_db=args.expected_dest_db,
            truncate=not args.no_truncate,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    if failures:
        print(f"\nFAILED: {failures} table(s) had errors or count mismatches")
        return 1

    print("\nSUCCESS: all tables synced with matching row counts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
