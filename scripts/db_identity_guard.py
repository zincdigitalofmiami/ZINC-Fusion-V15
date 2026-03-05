#!/usr/bin/env python3
"""Validate database identity for cloud/local/shadow routing modes.

This guard prevents accidental writes/queries against the wrong database by
checking URL presence, host classification, and expected database name.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "host.docker.internal",
}


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    mode: str
    endpoint: str
    db_name: str
    message: str


def _parse_db_url(raw: str) -> tuple[str, str]:
    parsed = urlparse(raw)
    host = (parsed.hostname or "").strip().lower()
    db_name = (parsed.path or "").lstrip("/").strip()
    return host, db_name


def _redact_endpoint(raw: str) -> str:
    parsed = urlparse(raw)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    db_name = (parsed.path or "").lstrip("/") or "<unknown>"
    return f"{host}{port}/{db_name}"


def _pick_url(mode: str) -> tuple[str | None, str]:
    if mode == "cloud":
        return (
            os.getenv("CLOUD_DATABASE_URL")
            or os.getenv("DIRECT_DATABASE_URL")
            or os.getenv("POSTGRES_URL")
            or os.getenv("DATABASE_URL"),
            "CLOUD_DATABASE_URL or DIRECT_DATABASE_URL/POSTGRES_URL/DATABASE_URL",
        )
    if mode == "local":
        return (
            os.getenv("LOCAL_DATABASE_URL")
            or os.getenv("DIRECT_DATABASE_URL")
            or os.getenv("POSTGRES_URL")
            or os.getenv("DATABASE_URL"),
            "LOCAL_DATABASE_URL or DIRECT_DATABASE_URL/POSTGRES_URL/DATABASE_URL",
        )
    if mode == "shadow":
        return (
            os.getenv("SHADOW_DATABASE_URL"),
            "SHADOW_DATABASE_URL",
        )
    raise ValueError(f"unsupported mode: {mode}")


def _expected_db_name(mode: str) -> str | None:
    if mode == "cloud":
        return os.getenv("EXPECTED_CLOUD_DB_NAME")
    if mode == "local":
        return os.getenv("LOCAL_DB_EXPECTED_NAME") or os.getenv("EXPECTED_DB_NAME")
    if mode == "shadow":
        return os.getenv("SHADOW_DB_EXPECTED_NAME") or "zinc_fusion_v15_shadow"
    return None


def validate(mode: str) -> GuardResult:
    raw, source_desc = _pick_url(mode)
    if not raw:
        return GuardResult(
            ok=False,
            mode=mode,
            endpoint="<unset>",
            db_name="<unset>",
            message=(
                f"missing database URL for mode={mode}. Expected env: {source_desc}."
            ),
        )

    host, db_name = _parse_db_url(raw)
    endpoint = _redact_endpoint(raw)

    if not host or not db_name:
        return GuardResult(
            ok=False,
            mode=mode,
            endpoint=endpoint,
            db_name=db_name or "<unknown>",
            message="invalid database URL; host and database name are required.",
        )

    if mode in {"local", "shadow"}:
        if host not in LOCAL_HOSTS:
            return GuardResult(
                ok=False,
                mode=mode,
                endpoint=endpoint,
                db_name=db_name,
                message=(
                    f"{mode} mode requires localhost endpoint; resolved host={host!r}."
                ),
            )

    if mode == "cloud":
        expected_host = os.getenv("EXPECTED_CLOUD_DB_HOST", "db.prisma.io")
        if host in LOCAL_HOSTS:
            return GuardResult(
                ok=False,
                mode=mode,
                endpoint=endpoint,
                db_name=db_name,
                message="cloud mode resolved to localhost endpoint.",
            )
        if expected_host and expected_host not in host:
            return GuardResult(
                ok=False,
                mode=mode,
                endpoint=endpoint,
                db_name=db_name,
                message=(
                    f"cloud host mismatch: expected host containing "
                    f"{expected_host!r}, got {host!r}."
                ),
            )

    expected_name = _expected_db_name(mode)
    if expected_name and db_name != expected_name:
        return GuardResult(
            ok=False,
            mode=mode,
            endpoint=endpoint,
            db_name=db_name,
            message=(
                f"database name mismatch for mode={mode}: "
                f"expected {expected_name!r}, got {db_name!r}."
            ),
        )

    return GuardResult(
        ok=True,
        mode=mode,
        endpoint=endpoint,
        db_name=db_name,
        message="ok",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate DB endpoint identity for cloud/local/shadow routing"
    )
    parser.add_argument(
        "--mode",
        choices=["cloud", "local", "shadow"],
        required=True,
        help="guard mode to validate",
    )
    args = parser.parse_args()

    result = validate(args.mode)
    prefix = "PASS" if result.ok else "FAIL"
    print(
        f"[{prefix}] mode={result.mode} endpoint={result.endpoint} "
        f"db={result.db_name} message={result.message}"
    )
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
