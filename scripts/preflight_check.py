#!/usr/bin/env python3
"""
Preflight Check for ZINC-FUSION-V15.

Run this BEFORE and AFTER making changes to verify project integrity.
Usage: .venv/bin/python scripts/preflight_check.py [--db] [--imports] [--schema] [--all]

Designed for AI agents to run as a concrete verification step.
"""

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
CHECK = f"{GREEN}✓{RESET}"
CROSS = f"{RED}✗{RESET}"
WARN = f"{YELLOW}⚠{RESET}"

REPO_ROOT = Path(__file__).parent.parent
failures = []
warnings = []


def check(name: str, passed: bool, detail: str = ""):
    """Log a check result."""
    if passed:
        print(f"  {CHECK} {name}")
    else:
        msg = f"{name}: {detail}" if detail else name
        print(f"  {CROSS} {msg}")
        failures.append(msg)


def warn(name: str, detail: str = ""):
    """Log a warning (non-fatal)."""
    msg = f"{name}: {detail}" if detail else name
    print(f"  {WARN} {msg}")
    warnings.append(msg)


def check_structure():
    """Verify critical files and directories exist."""
    print("\n📁 Project Structure")

    critical_files = [
        "AGENTS.md",
        "CLAUDE.md",
        "prisma/schema.prisma",
        "src/fusion/__init__.py",
        "requirements.txt",
        ".env",
        ".github/copilot-instructions.md",
    ]

    for f in critical_files:
        path = REPO_ROOT / f
        check(f"EXISTS {f}", path.exists(), f"Missing: {f}")

    critical_dirs = [
        "src/fusion",
        "prisma",
        "frontend",
        "scripts",
        "tests",
    ]

    for d in critical_dirs:
        path = REPO_ROOT / d
        check(f"DIR {d}/", path.is_dir(), f"Missing directory: {d}")


def check_env():
    """Verify environment variables are set."""
    print("\n🔐 Environment Variables")

    # Check .env file exists
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        check("ENV .env file", False, ".env file missing")
        return

    # Read .env and check critical keys
    env_contents = env_file.read_text()
    critical_keys = ["DATABASE_URL"]
    optional_keys = ["FRED_API_KEY"]

    for key in critical_keys:
        has_key = key in env_contents and f"{key}=" in env_contents
        check(f"ENV {key}", has_key, f"{key} not found in .env")

    for key in optional_keys:
        has_key = key in env_contents and f"{key}=" in env_contents
        if not has_key:
            warn(f"ENV {key} not set (optional)")
        else:
            print(f"  {CHECK} ENV {key}")


def check_venv():
    """Verify virtual environment is active and correct."""
    print("\n🐍 Virtual Environment")

    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    check("VENV .venv/bin/python exists", venv_python.exists())

    # Check if we're running from venv
    in_venv = sys.prefix != sys.base_prefix
    if not in_venv:
        warn("Not running inside .venv — use .venv/bin/python")
    else:
        print(f"  {CHECK} Running inside virtual environment")


def check_imports():
    """Verify critical Python imports resolve."""
    print("\n📦 Python Imports")

    critical_imports = [
        ("fusion", "Core package"),
        ("psycopg2", "Database driver"),
        ("pandas", "Data processing"),
        ("numpy", "Numerical computing"),
        ("sklearn", "Machine learning"),
        ("sqlalchemy", "SQL toolkit"),
    ]

    optional_imports = [
        ("autogluon.timeseries", "Core model training"),
        ("fastapi", "API server"),
        ("xgboost", "Specialist models"),
        ("arch", "GARCH models"),
        ("statsmodels", "Statistical models"),
        ("fredapi", "FRED data access"),
    ]

    for module, desc in critical_imports:
        try:
            importlib.import_module(module)
            print(f"  {CHECK} import {module} ({desc})")
        except ImportError as e:
            check(f"import {module} ({desc})", False, str(e))

    for module, desc in optional_imports:
        try:
            importlib.import_module(module)
            print(f"  {CHECK} import {module} ({desc})")
        except ImportError:
            warn(f"import {module} ({desc}) — not installed")


def check_schema():
    """Verify Prisma schema has expected schemas/tables."""
    print("\n🗃️  Prisma Schema")

    schema_file = REPO_ROOT / "prisma" / "schema.prisma"
    if not schema_file.exists():
        check("SCHEMA prisma/schema.prisma", False, "File not found")
        return

    content = schema_file.read_text()

    # Check for banned schema references in Prisma schema
    banned = [
        "raw",
        "gold",
        "silver",
        "bronze",
        "monitoring",
        "specialist",
        "weather",
        "archive",
    ]
    for schema_name in banned:
        # Look for @@schema("banned_name") pattern
        if f'@@schema("{schema_name}")' in content:
            check(
                f"BANNED schema '{schema_name}'",
                False,
                f"Found banned schema '{schema_name}' in Prisma",
            )

    # Check expected schemas exist
    expected_schemas = [
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
    ]
    found_schemas = set()
    for line in content.split("\n"):
        if '@@schema("' in line:
            schema = line.split('@@schema("')[1].split('"')[0]
            found_schemas.add(schema)

    for schema in expected_schemas:
        if schema in found_schemas:
            print(f"  {CHECK} SCHEMA {schema}.*")
        else:
            warn(f"SCHEMA {schema}.* not found in Prisma (may be OK)")

    print(
        f"\n  Found {len(found_schemas)} schemas in Prisma: {', '.join(sorted(found_schemas))}"
    )


def check_db():
    """Test database connectivity."""
    print("\n🔌 Database Connectivity")

    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        warn("python-dotenv not installed — loading .env manually")
        # Manual .env loading
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    value = value.strip().strip('"').strip("'")
                    os.environ[key.strip()] = value

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        check("DB DATABASE_URL set", False, "DATABASE_URL not in environment")
        return

    # Mask URL for display
    masked = db_url[:20] + "..." if len(db_url) > 20 else db_url
    print(f"  {CHECK} DATABASE_URL configured ({masked})")

    try:
        import psycopg2

        conn = psycopg2.connect(db_url, connect_timeout=10)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        check("DB connection", result == (1,))

        # Check schema count
        cur.execute("""
            SELECT schema_name FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'public')
            ORDER BY schema_name
        """)
        schemas = [r[0] for r in cur.fetchall()]
        print(f"  {CHECK} DB schemas found: {', '.join(schemas)}")

        # Quick table count per schema
        for schema in ["mkt", "training", "analytics"]:
            if schema in schemas:
                cur.execute(f"""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema = '{schema}'
                """)
                count = cur.fetchone()[0]
                print(f"  {CHECK} {schema}.* has {count} tables")

        cur.close()
        conn.close()
    except ImportError:
        check("DB psycopg2", False, "psycopg2 not installed")
    except Exception as e:
        check("DB connection", False, str(e)[:100])


def check_tests():
    """Run a quick test smoke check."""
    print("\n🧪 Tests (smoke check)")

    pytest_bin = REPO_ROOT / ".venv" / "bin" / "pytest"
    if not pytest_bin.exists():
        warn("pytest not found at .venv/bin/pytest")
        return

    try:
        result = subprocess.run(
            [str(pytest_bin), "--co", "-q", "--no-header"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=30,
        )
        if result.returncode == 0:
            lines = [line for line in result.stdout.strip().split("\n") if line.strip()]
            test_count = len([line for line in lines if "::" in line])
            print(f"  {CHECK} {test_count} tests collected")
        elif result.returncode == 5:
            warn("No tests collected (returncode 5)")
        else:
            warn(f"Test collection issue: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        warn("Test collection timed out (30s)")
    except Exception as e:
        warn(f"Test check failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="ZINC-FUSION-V15 Preflight Check")
    parser.add_argument(
        "--db", action="store_true", help="Include database connectivity check"
    )
    parser.add_argument("--imports", action="store_true", help="Check Python imports")
    parser.add_argument("--schema", action="store_true", help="Validate Prisma schema")
    parser.add_argument(
        "--tests", action="store_true", help="Smoke-check test collection"
    )
    parser.add_argument("--all", action="store_true", help="Run all checks")
    args = parser.parse_args()

    # Default: run structure + env + venv checks
    run_all = args.all or not any([args.db, args.imports, args.schema, args.tests])

    print("=" * 60)
    print("  ZINC-FUSION-V15 Preflight Check")
    print("=" * 60)

    check_structure()
    check_env()
    check_venv()

    if run_all or args.imports:
        check_imports()

    if run_all or args.schema:
        check_schema()

    if run_all or args.db:
        check_db()

    if run_all or args.tests:
        check_tests()

    # Summary
    print("\n" + "=" * 60)
    if failures:
        print(f"  {RED}FAILED: {len(failures)} issue(s){RESET}")
        for f in failures:
            print(f"    {CROSS} {f}")
    else:
        print(f"  {GREEN}ALL CHECKS PASSED{RESET}")

    if warnings:
        print(f"  {YELLOW}{len(warnings)} warning(s){RESET}")
        for w in warnings:
            print(f"    {WARN} {w}")

    print("=" * 60)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
