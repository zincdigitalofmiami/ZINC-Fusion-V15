#!/usr/bin/env python3
"""
Database identity guard for ZINC-FUSION-V15.

Fail-closed checks to prevent cross-project DB drift.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

REQUIRED_SCHEMAS = {
    "mkt",
    "econ",
    "alt",
    "pos",
    "supply",
    "features",
    "training",
    "model",
    "forecasts",
    "analytics",
    "ops",
    "vegas",
}

REQUIRED_TABLES = {
    "forecasts.production_1d",
    "training.matrix_1d",
    "training.specialist_signals_1d",
    "training.oof_core_1d",
}

TARGETS = {
    "cloud": {
        "expected_db": "postgres",
        "expected_host_contains": "db.prisma.io",
        "url_env_order": ["DIRECT_DATABASE_URL", "POSTGRES_URL", "DATABASE_URL"],
        "validate_v15": True,
    },
    "local-runtime": {
        "expected_db": "zinc_fusion_v15_local",
        "expected_host_exact": {"localhost", "127.0.0.1", "::1"},
        "url_env_order": ["LOCAL_DATABASE_URL"],
        "validate_v15": True,
    },
    "local-shadow": {
        "expected_db": "zinc_fusion_v15_shadow",
        "expected_host_exact": {"localhost", "127.0.0.1", "::1"},
        "url_env_order": ["SHADOW_DATABASE_URL"],
        "default_url": "postgresql://zincdigital@localhost:5432/zinc_fusion_v15_shadow",
        "validate_v15": False,
    },
}


def fail(message: str) -> None:
    print(f"[db-guard] BLOCKED: {message}")
    raise SystemExit(1)


def normalize_url(url: str) -> str:
    if not url:
        fail("No database URL resolved.")
    if url.startswith("prisma+postgres://"):
        fail(
            "Direct postgres:// URL required for identity guard (prisma+postgres:// is not supported)."
        )
    if not (url.startswith("postgres://") or url.startswith("postgresql://")):
        fail("Unsupported URL scheme. Expected postgres:// or postgresql://")

    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    if "gssencmode" in q:
        return url
    sep = "&" if parsed.query else "?"
    return f"{url}{sep}gssencmode=disable"


def resolve_url(target: str, explicit_url: str | None) -> str:
    if explicit_url:
        return normalize_url(explicit_url)

    conf = TARGETS[target]
    for key in conf["url_env_order"]:
        value = os.getenv(key)
        if value:
            return normalize_url(value)

    default_url = conf.get("default_url")
    if default_url:
        return normalize_url(default_url)

    env_hint = ", ".join(conf["url_env_order"])
    fail(f"No URL set for target '{target}'. Expected one of env vars: {env_hint}")


def parse_host_db(url: str) -> tuple[str | None, str]:
    parsed = urlparse(url)
    host = parsed.hostname
    db_name = parsed.path.lstrip("/") or ""
    return host, db_name


def check_host_db_constraints(target: str, host: str | None, db_name: str) -> None:
    conf = TARGETS[target]
    expected_db = conf["expected_db"]

    if db_name != expected_db:
        fail(
            f"Wrong database name for target '{target}'. Expected '{expected_db}', got '{db_name or '<empty>'}'."
        )

    if "expected_host_contains" in conf:
        needle = conf["expected_host_contains"]
        if not host or needle not in host:
            fail(
                f"Wrong host for target '{target}'. Expected host containing '{needle}', got '{host}'."
            )

    if "expected_host_exact" in conf:
        allowed = conf["expected_host_exact"]
        if host not in allowed:
            fail(
                f"Wrong host for target '{target}'. Expected one of {sorted(allowed)}, got '{host}'."
            )


def fetch_runtime_identity(conn) -> tuple[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()::text, current_user::text")
        row = cur.fetchone()
        if not row:
            fail("Could not read current database identity.")
        return row[0], row[1]


def check_required_schemas(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name IN %s
            """,
            (tuple(REQUIRED_SCHEMAS),),
        )
        found = {r[0] for r in cur.fetchall()}

    missing = sorted(REQUIRED_SCHEMAS - found)
    if missing:
        fail(f"Missing required schemas: {', '.join(missing)}")


def check_required_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rel_name, to_regclass(rel_name)::text
            FROM unnest(%s::text[]) AS rel_name
            """,
            (list(REQUIRED_TABLES),),
        )
        rows = cur.fetchall()

    missing = sorted(rel for rel, reg in rows if reg is None)
    if missing:
        fail(f"Missing required tables: {', '.join(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="ZINC-FUSION DB identity guard")
    parser.add_argument("--target", choices=sorted(TARGETS.keys()), required=True)
    parser.add_argument("--url", help="Explicit database URL (overrides env)")
    parser.add_argument(
        "--skip-v15-checks",
        action="store_true",
        help="Skip required V15 schema/table checks (identity checks still enforced)",
    )
    args = parser.parse_args()

    url = resolve_url(args.target, args.url)
    host, db_name = parse_host_db(url)
    check_host_db_constraints(args.target, host, db_name)

    try:
        conn = psycopg2.connect(url, connect_timeout=10)
    except Exception as exc:
        fail(f"Connection failed for target '{args.target}': {exc}")

    try:
        runtime_db, runtime_user = fetch_runtime_identity(conn)
        expected_db = TARGETS[args.target]["expected_db"]
        if runtime_db != expected_db:
            fail(
                f"Connected to wrong runtime DB. Expected '{expected_db}', got '{runtime_db}' as user '{runtime_user}'."
            )

        should_validate_v15 = (
            TARGETS[args.target]["validate_v15"] and not args.skip_v15_checks
        )
        if should_validate_v15:
            check_required_schemas(conn)
            check_required_tables(conn)

        print(
            "[db-guard] PASS: "
            f"target={args.target} host={host} db={runtime_db} user={runtime_user} "
            f"v15_checks={'on' if should_validate_v15 else 'off'}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
