import os
import re

import psycopg2
import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


@pytest.fixture(scope="module")
def db_connection():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
    except psycopg2.OperationalError as exc:
        pytest.skip(f"DATABASE_URL unreachable: {exc}")
    yield conn
    conn.close()


def get_all_tables(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        """)
        return cur.fetchall()


def get_columns_for_table(conn, schema, table):
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = '{schema}' AND table_name = '{table}'
        """,
            (schema, table),
        )
        return cur.fetchall()


def test_no_banned_schemas(db_connection):
    """
    Check for banned schemas: raw, gold, silver, bronze, monitoring, specialist, weather, archive
    """
    banned_schemas = {
        "raw",
        "gold",
        "silver",
        "bronze",
        "monitoring",
        "specialist",
        "weather",
        "archive",
    }
    tables = get_all_tables(db_connection)
    found_schemas = {t[0] for t in tables}

    violating_schemas = found_schemas.intersection(banned_schemas)
    assert not violating_schemas, (
        f"Banned schemas found in database: {violating_schemas}"
    )


def test_canonical_schemas_only(db_connection):
    """
    Check if all schemas are among the canonical or governance schemas.
    """
    allowed_schemas = {
        "alt",
        "analytics",
        "econ",
        "features",
        "forecasts",
        "mkt",
        "model",
        "ops",
        "pos",
        "supply",
        "training",
        "metadata",
        "vegas",
        "public",
    }
    tables = get_all_tables(db_connection)
    found_schemas = {t[0] for t in tables}

    extra_schemas = found_schemas - allowed_schemas
    # Filter out internal postgres schemas if any missed
    extra_schemas = {s for s in extra_schemas if not s.startswith("pg_")}

    assert not extra_schemas, (
        f"Non-canonical schemas found: {extra_schemas}. Please verify if they should be allowed."
    )


def test_grain_suffix_naming(db_connection):
    """
    Tables in landing and derived schemas should have grain suffixes: _1h, _1d, _1w, _1m, _event, _static
    Exceptions: Some specific tables like oof_core_1d (which has suffix) but others might miss.
    """
    landing_derived = {"mkt", "econ", "alt", "pos", "supply", "features", "training"}
    valid_suffixes = ("_1h", "_1d", "_1w", "_1m", "_event", "_static")

    tables = get_all_tables(db_connection)
    violations = []

    for schema, table in tables:
        if schema in landing_derived:
            # Special exceptions for known tables if any
            if table in ("specialist_features"):  # Example from schema.prisma line 91
                continue

            if not table.endswith(valid_suffixes):
                violations.append(f"{schema}.{table}")

    assert not violations, f"Tables missing required grain suffixes: {violations}"


def test_time_column_semantics(db_connection):
    """
    Validate time column names based on schema category.
    Landing: event_date
    Derived: trade_date
    """
    landing_schemas = {"mkt", "econ", "alt", "pos", "supply"}
    derived_schemas = {"features", "training"}

    tables = get_all_tables(db_connection)
    violations = []

    for schema, table in tables:
        columns = [c[0] for c in get_columns_for_table(db_connection, schema, table)]

        if schema in landing_schemas:
            # Should not use trade_date or as_of_date for real world events
            if "trade_date" in columns:
                violations.append(
                    f"{schema}.{table} uses trade_date instead of event_date"
                )
            if (
                "as_of_date" in columns and schema != "alt"
            ):  # alt might use as_of_date for some things, but usually event_date
                # Verify if as_of_date is used incorrectly as event_date
                pass

        if schema in derived_schemas:
            # Should prefer trade_date
            if "event_date" in columns:
                violations.append(
                    f"{schema}.{table} uses event_date instead of trade_date"
                )

    assert not violations, f"Time column semantic violations: {violations}"


def test_quantile_naming_contract(db_connection):
    """
    Validate quantile column naming.
    OOF: p30, p50, p70
    Risk: p10, p30, p50, p70, p90
    Banned: camelCase, pred_ prefix, q prefix
    """
    tables = get_all_tables(db_connection)
    violations = []

    for schema, table in tables:
        columns = [c[0] for c in get_columns_for_table(db_connection, schema, table)]

        for col in columns:
            # Check for banned q prefix (q10, q50)
            if re.match(r"^q\d+$", col):
                violations.append(f"{schema}.{table}.{col} (use p instead of q)")

            # Check for pred_ prefix
            if col.startswith("pred_p"):
                violations.append(f"{schema}.{table}.{col} (pred_ prefix is banned)")

            # Check for camelCase quantiles
            if re.match(r".*[a-z][A-Z].*", col) and ("p" in col.lower()):
                violations.append(f"{schema}.{table}.{col} (camelCase is banned)")

    assert not violations, f"Quantile naming violations: {violations}"


def test_as_of_date_audit(db_connection):
    """
    as_of_date should not be used in landing tables (mkt, econ, supply, etc.)
    """
    landing_schemas = {"mkt", "econ", "pos", "supply"}
    tables = get_all_tables(db_connection)
    violations = []

    for schema, table in tables:
        if schema in landing_schemas:
            columns = [
                c[0] for c in get_columns_for_table(db_connection, schema, table)
            ]
            if "as_of_date" in columns:
                violations.append(f"{schema}.{table}")

    assert not violations, (
        f"Landing tables using as_of_date (should use event_date): {violations}"
    )


def test_banned_patterns_in_table_names(db_connection):
    """
    Check for banned patterns in table names:
    - Horizon in table name (e.g., oof_core_5d_1d)
    - Symbol in table name (e.g., oof_core_zl_1d)
    """
    tables = get_all_tables(db_connection)
    violations = []

    # Pattern for horizon in name like _5d_, _21d_, etc.
    horizon_pattern = re.compile(r"_(5|21|63|126)d_")

    # Pattern for known symbols if any
    symbols = {"zl", "zs", "zm", "cl", "ho"}

    for schema, table in tables:
        if horizon_pattern.search(table):
            violations.append(f"{schema}.{table} (contains horizon in name)")

        for sym in symbols:
            if (
                f"_{sym}_" in table.lower()
                or table.lower().startswith(f"{sym}_")
                or table.lower().endswith(f"_{sym}")
            ):
                # Some exceptions might exist, but usually banned
                violations.append(f"{schema}.{table} (contains symbol '{sym}' in name)")

    assert not violations, f"Banned patterns in table names: {violations}"
