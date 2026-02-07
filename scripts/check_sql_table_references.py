#!/usr/bin/env python3
"""
Validate schema.table references in changed code against prisma/schema.prisma.

Why this exists:
- Catches hallucinated table names early.
- Enforces banned schema policy at code-review time.

Usage:
  python3 scripts/check_sql_table_references.py [files_or_dirs...]

If no paths are provided, the script falls back to git diff filenames.
"""

from __future__ import annotations

import argparse
import difflib
import re
import subprocess
from pathlib import Path


ALLOWED_SCHEMAS = {
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
    "metadata",
    "ops",
}

BANNED_SCHEMAS = {
    "raw",
    "gold",
    "silver",
    "bronze",
    "monitoring",
    "specialist",
    "weather",
    "archive",
    "vegas",
}

CODE_EXTS = {".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".sql"}
PATH_PREFIXES = (
    "src/",
    "scripts/",
    "frontend/src/",
    "tests/",
    "sql/",
)
SKIP_SUBSTRINGS = (
    "/node_modules/",
    "/.next/",
    "/AutogluonModels/",
    "/data/",
    "/archive/",
    "/scripts/_deprecated/",
)

MODEL_START_RE = re.compile(r"^\s*(model|view)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{")
SCHEMA_RE = re.compile(r'@@schema\("([A-Za-z0-9_]+)"\)')
MAP_RE = re.compile(r'@@map\("([A-Za-z0-9_]+)"\)')
TABLE_REF_RE = re.compile(r"\b([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)\b")


def camel_to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def parse_prisma_tables(prisma_path: Path) -> set[str]:
    if not prisma_path.exists():
        raise FileNotFoundError(f"Prisma schema not found: {prisma_path}")

    known: set[str] = set()
    in_block = False
    model_name = ""
    schema_name = ""
    map_name = ""

    for raw_line in prisma_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not in_block:
            match = MODEL_START_RE.match(raw_line)
            if match:
                in_block = True
                model_name = match.group(2)
                schema_name = ""
                map_name = ""
            continue

        schema_match = SCHEMA_RE.search(raw_line)
        if schema_match:
            schema_name = schema_match.group(1)

        map_match = MAP_RE.search(raw_line)
        if map_match:
            map_name = map_match.group(1)

        if line == "}":
            if schema_name:
                table_candidates = {model_name, camel_to_snake(model_name)}
                if map_name:
                    table_candidates.add(map_name)
                for table_name in table_candidates:
                    known.add(f"{schema_name}.{table_name}")
            in_block = False

    return known


def discover_changed_files() -> list[Path]:
    cmds = [
        ["git", "diff", "--name-only", "--diff-filter=ACMRT"],
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRT"],
    ]
    seen: set[str] = set()
    out: list[Path] = []
    for cmd in cmds:
        try:
            result = subprocess.run(
                cmd, check=False, capture_output=True, text=True, timeout=5
            )
        except OSError:
            continue
        for line in result.stdout.splitlines():
            path = line.strip()
            if path and path not in seen:
                seen.add(path)
                out.append(Path(path))
    return out


def iter_code_files(paths: list[Path]) -> list[Path]:
    resolved: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            resolved.append(path)
            continue
        for child in path.rglob("*"):
            if child.is_file():
                resolved.append(child)

    out: list[Path] = []
    seen: set[str] = set()
    for file_path in resolved:
        rel = file_path.as_posix()
        if rel in seen:
            continue
        seen.add(rel)

        if file_path.suffix.lower() not in CODE_EXTS:
            continue
        if not rel.startswith(PATH_PREFIXES):
            continue
        if any(token in f"/{rel}" for token in SKIP_SUBSTRINGS):
            continue
        out.append(file_path)
    return out


def scan_file(file_path: Path, known_tables: set[str]) -> list[str]:
    violations: list[str] = []
    known_by_schema: dict[str, list[str]] = {}
    for full in known_tables:
        schema, _table = full.split(".", 1)
        known_by_schema.setdefault(schema, []).append(full)

    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return violations

    for idx, line in enumerate(lines, start=1):
        if "sqlref: ignore" in line:
            continue
        for schema, table in TABLE_REF_RE.findall(line):
            full = f"{schema}.{table}"
            if schema in BANNED_SCHEMAS:
                violations.append(
                    f"{file_path}:{idx}: banned schema reference `{full}` (policy violation)"
                )
                continue
            if schema in ALLOWED_SCHEMAS and full not in known_tables:
                suggestion = difflib.get_close_matches(
                    full, known_by_schema.get(schema, []), n=1, cutoff=0.6
                )
                hint = f" (did you mean `{suggestion[0]}`?)" if suggestion else ""
                violations.append(
                    f"{file_path}:{idx}: unknown table reference `{full}` not found in prisma/schema.prisma{hint}"
                )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate schema.table refs against prisma/schema.prisma"
    )
    parser.add_argument("paths", nargs="*", help="Files or directories to validate")
    parser.add_argument(
        "--prisma",
        default="prisma/schema.prisma",
        help="Path to Prisma schema (default: prisma/schema.prisma)",
    )
    args = parser.parse_args()

    try:
        known_tables = parse_prisma_tables(Path(args.prisma))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    candidate_paths = (
        [Path(p) for p in args.paths] if args.paths else discover_changed_files()
    )
    code_files = iter_code_files(candidate_paths)

    if not code_files:
        print("SQL table contract: no relevant files to check.")
        return 0

    violations: list[str] = []
    for file_path in code_files:
        violations.extend(scan_file(file_path, known_tables))

    if violations:
        print("SQL table contract violations:")
        for violation in violations:
            print(f"  - {violation}")
        return 1

    print(f"SQL table contract: passed ({len(code_files)} file(s) checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
