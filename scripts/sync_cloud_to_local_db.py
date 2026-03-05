#!/usr/bin/env python3
"""
Sync critical audit tables from Prisma cloud Postgres to local V15 Postgres.

Fail-closed behavior:
- Source must be cloud host containing db.prisma.io
- Destination must be local host and database zinc_fusion_v15_local
"""

from __future__ import annotations

import argparse
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

ALLOWED_TABLES = [
    "forecasts.production_1d",
    "training.matrix_1d",
    "training.specialist_signals_1d",
    "training.oof_core_1d",
]

EXPECTED_LOCAL_DB = "zinc_fusion_v15_local"


@dataclass
class SyncResult:
    table: str
    source_count: int
    dest_count: int
    elapsed_s: float
    status: str
    error: str | None = None


def fail(msg: str) -> None:
    print(f"[sync-cloud-to-local-db] BLOCKED: {msg}")
    raise SystemExit(1)


def normalize_url(url: str) -> str:
    if not url:
        fail("Missing database URL.")
    if url.startswith("prisma+postgres://"):
        fail("Direct postgres URL required; prisma+postgres is not supported.")
    if not (url.startswith("postgres://") or url.startswith("postgresql://")):
        fail("Unsupported URL scheme. Expected postgres:// or postgresql://")
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    if "gssencmode" in q:
        return url
    sep = "&" if parsed.query else "?"
    return f"{url}{sep}gssencmode=disable"


def parse_host_db(url: str) -> tuple[str | None, str]:
    parsed = urlparse(url)
    host = parsed.hostname
    db = parsed.path.lstrip("/")
    return host, db


def resolve_urls(source_url: str | None, dest_url: str | None) -> tuple[str, str]:
    source = source_url or os.getenv("CLOUD_DATABASE_URL") or os.getenv("DIRECT_DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    dest = dest_url or os.getenv("LOCAL_DATABASE_URL")

    if not source:
        fail("Could not resolve source URL. Set CLOUD_DATABASE_URL or DIRECT_DATABASE_URL or POSTGRES_URL or DATABASE_URL.")
    if not dest:
        fail("Could not resolve destination URL. Set LOCAL_DATABASE_URL.")

    return normalize_url(source), normalize_url(dest)


def validate_urls(source: str, dest: str) -> None:
    source_host, source_db = parse_host_db(source)
    dest_host, dest_db = parse_host_db(dest)

    if not source_host or "db.prisma.io" not in source_host:
        fail(f"Source host must contain db.prisma.io, got '{source_host}'.")
    if source_db != "postgres":
        fail(f"Source database must be 'postgres', got '{source_db}'.")

    allowed_local_hosts = {"localhost", "127.0.0.1", "::1"}
    if dest_host not in allowed_local_hosts:
        fail(f"Destination host must be local ({sorted(allowed_local_hosts)}), got '{dest_host}'.")
    if dest_db != EXPECTED_LOCAL_DB:
        fail(f"Destination DB must be '{EXPECTED_LOCAL_DB}', got '{dest_db}'.")


def ensure_dest_table_exists(conn, table_name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (table_name,))
        row = cur.fetchone()
        if not row or row[0] is None:
            fail(f"Destination missing required table: {table_name}")


def count_rows(conn, table_name: str) -> int:
    schema, table = table_name.split(".", 1)
    with conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        return int(cur.fetchone()[0])


def copy_table(source_conn, dest_conn, table_name: str, dry_run: bool) -> SyncResult:
    start = time.perf_counter()
    schema, table = table_name.split(".", 1)

    try:
        source_count = count_rows(source_conn, table_name)
        if dry_run:
            elapsed = time.perf_counter() - start
            return SyncResult(table_name, source_count, -1, elapsed, "dry_run")

        ensure_dest_table_exists(dest_conn, table_name)

        with source_conn.cursor() as source_cur, dest_conn.cursor() as dest_cur:
            dest_cur.execute(f'TRUNCATE TABLE "{schema}"."{table}" CASCADE')

            export_sql = f'COPY "{schema}"."{table}" TO STDOUT WITH (FORMAT CSV, HEADER TRUE)'
            import_sql = f'COPY "{schema}"."{table}" FROM STDIN WITH (FORMAT CSV, HEADER TRUE)'

            # Use a temporary file to keep compatibility across psycopg2 versions.
            with tempfile.NamedTemporaryFile(mode="w+b") as tmp:
                source_cur.copy_expert(export_sql, tmp)
                tmp.flush()
                tmp.seek(0)
                dest_cur.copy_expert(import_sql, tmp)

        dest_conn.commit()
        dest_count = count_rows(dest_conn, table_name)
        elapsed = time.perf_counter() - start

        if source_count != dest_count:
            return SyncResult(
                table_name,
                source_count,
                dest_count,
                elapsed,
                "mismatch",
                error="row count mismatch",
            )

        return SyncResult(table_name, source_count, dest_count, elapsed, "ok")
    except Exception as exc:
        dest_conn.rollback()
        elapsed = time.perf_counter() - start
        return SyncResult(table_name, -1, -1, elapsed, "error", str(exc))


def parse_tables(requested: list[str]) -> list[str]:
    if requested == ["all"]:
        return ALLOWED_TABLES

    invalid = [t for t in requested if t not in ALLOWED_TABLES]
    if invalid:
        fail(f"Unsupported tables requested: {', '.join(invalid)}")
    return requested


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync cloud Postgres tables to local V15 Postgres")
    parser.add_argument("--source-url", help="Override cloud source URL")
    parser.add_argument("--dest-url", help="Override local destination URL")
    parser.add_argument("--tables", nargs="+", default=["all"], help="Subset of tables to sync")
    parser.add_argument("--dry-run", action="store_true", help="Only print source row counts")
    args = parser.parse_args()

    source_url, dest_url = resolve_urls(args.source_url, args.dest_url)
    validate_urls(source_url, dest_url)

    tables = parse_tables(args.tables)

    print("[sync-cloud-to-local-db] start")
    print(f"  source_host={parse_host_db(source_url)[0]} source_db={parse_host_db(source_url)[1]}")
    print(f"  dest_host={parse_host_db(dest_url)[0]} dest_db={parse_host_db(dest_url)[1]}")
    print(f"  tables={len(tables)} dry_run={args.dry_run}")

    source_conn = psycopg2.connect(source_url)
    dest_conn = psycopg2.connect(dest_url)

    try:
        results: list[SyncResult] = []
        for table in tables:
            result = copy_table(source_conn, dest_conn, table, args.dry_run)
            results.append(result)
            if result.status == "dry_run":
                print(f"  DRY-RUN {table}: source_rows={result.source_count} elapsed={result.elapsed_s:.2f}s")
            elif result.status == "ok":
                print(
                    f"  OK {table}: source_rows={result.source_count} dest_rows={result.dest_count} elapsed={result.elapsed_s:.2f}s"
                )
            else:
                print(
                    f"  {result.status.upper()} {table}: source_rows={result.source_count} dest_rows={result.dest_count} elapsed={result.elapsed_s:.2f}s error={result.error}"
                )

        failures = [r for r in results if r.status not in {"ok", "dry_run"}]
        if failures:
            print(f"[sync-cloud-to-local-db] FAILED: {len(failures)} table(s) had errors")
            return 1

        print("[sync-cloud-to-local-db] PASS")
        return 0
    finally:
        source_conn.close()
        dest_conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
