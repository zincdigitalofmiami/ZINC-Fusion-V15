"""
Matrix persistence: write feature matrix to database.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

import pandas as pd
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)


def write_matrix(conn, df: pd.DataFrame, matrix_version: str) -> int:
    """Write matrix to training.matrix_1d."""
    logger.info("Writing to training.matrix_1d...")

    # Add metadata columns first (before table creation)
    df["matrix_version"] = matrix_version
    df["created_at"] = datetime.utcnow()

    # Full rebuild: DROP + CREATE + INSERT.
    # Schema is fully derived from the DataFrame — no need to preserve old columns.
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS training.matrix_1d")
            logger.info("   Dropped training.matrix_1d")
        conn.commit()

        create_table_from_df(conn, df, "training", "matrix_1d", matrix_version)
        conn.commit()
        logger.info(f"   Created training.matrix_1d with {len(df.columns)} columns")
        conn.commit()

        # Insert rows in chunks to avoid SSL timeout on Prisma Postgres proxy.
        # With 1400+ columns, each row is ~50KB of SQL — large batches blow
        # past the proxy's payload/timeout limit and cause "SSL connection
        # has been closed unexpectedly".
        cols = list(df.columns)
        insert_sql = f"""
            INSERT INTO training.matrix_1d ({",".join(cols)})
            VALUES %s
        """

        # Convert NaN -> None so Postgres stores NULL (not NaN which poisons aggregates).
        # Reuses double-defense pattern from train_models.py OOF write path.
        df = df.where(df.notna(), None)
        values = [
            tuple(None if pd.isna(v) else v for v in row)
            for row in df.itertuples(index=False, name=None)
        ]

        chunk_size = 500
        for i in range(0, len(values), chunk_size):
            chunk = values[i : i + chunk_size]
            with conn.cursor() as cur:
                execute_values(cur, insert_sql, chunk, page_size=100)
            conn.commit()
            logger.info(f"   Inserted chunk {i // chunk_size + 1}: {len(chunk)} rows")
        logger.info(f"   Total: {len(df):,} rows inserted")
    except Exception:
        conn.rollback()
        logger.error("   Matrix write failed — rolled back TRUNCATE")
        raise

    return len(df)


def create_table_from_df(conn, df: pd.DataFrame, schema: str, table: str, version: str):
    """Create table dynamically from DataFrame structure."""

    # All numeric types use 4-byte storage to keep rows under PostgreSQL's
    # 8,160-byte tuple limit with 1400+ columns. ML feature matrices don't
    # need 8-byte precision — single-precision float and 32-bit int are
    # more than sufficient for training data.
    dtype_map = {
        "int64": "INTEGER",
        "int32": "INTEGER",
        "float64": "REAL",
        "float32": "REAL",
        "bool": "BOOLEAN",
        "datetime64[ns]": "TIMESTAMP",
        "object": "TEXT",
    }

    col_defs = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        sql_type = dtype_map.get(dtype, "TEXT")

        if col == "trade_date":
            col_defs.append(f'"{col}" DATE NOT NULL')
        elif col == "symbol":
            col_defs.append(f'"{col}" VARCHAR(20) NOT NULL')
        else:
            col_defs.append(f'"{col}" {sql_type}')

    create_sql = f"""
        CREATE TABLE IF NOT EXISTS {schema}.{table} (
            {",".join(col_defs)},
            PRIMARY KEY (trade_date, symbol)
        )
    """

    with conn.cursor() as cur:
        cur.execute(create_sql)
    # Caller is responsible for conn.commit() — no mid-transaction commit here.

    logger.info(f"   Created table {schema}.{table}")


def compute_matrix_version(df: pd.DataFrame) -> str:
    """Compute hash of matrix for lineage tracking."""
    content = (
        f"{len(df)}_{len(df.columns)}_{df['trade_date'].min()}_{df['trade_date'].max()}"
    )
    return hashlib.sha256(content.encode()).hexdigest()[:16]
