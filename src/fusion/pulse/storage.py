"""
ZINC-FUSION-V15 Pulse Storage Layer
====================================

Storage helpers for persisting Intel Drops to Prisma PostgreSQL.
Uses the features.intel_drops table with narrative + quantPayload structure.
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import asdict

import asyncpg

from .extractors import ExtractedFeatures


# Database connection settings
DATABASE_URL = os.environ.get('DATABASE_URL', os.environ.get('POSTGRES_URL'))

def _parse_json(value: Any, default: Any) -> Any:
    """Normalize jsonb values across drivers (asyncpg vs psycopg2)."""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


async def get_connection() -> asyncpg.Connection:
    """Get database connection from pool."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable not set")
    return await asyncpg.connect(DATABASE_URL)


async def insert_intel_drop(
    conn: asyncpg.Connection,
    domain: str,
    horizon: str,
    as_of_ts: datetime,
    direction: int,
    pressure_cents: float,
    edge: float,
    driver_weights: Dict[str, float],
    top_drivers: List[str],
    regime_tags: List[str],
    quality_flags: List[str],
    data_gaps: List[str],
    narrative: str,
    quant_payload: Dict[str, Any],
    receipts: Optional[Dict[str, Any]] = None,
    source_model: Optional[str] = None
) -> int:
    """
    Insert a single Intel Drop into the database.

    Args:
        conn: Database connection
        domain: Specialist domain (CRUSH, CHINA, etc.)
        horizon: Time horizon (1W, 1M, 3M, 6M)
        as_of_ts: Timestamp of the pulse
        direction: Directional signal (-1, 0, 1)
        pressure_cents: Expected price movement
        edge: Confidence score
        driver_weights: Driver attribution weights
        top_drivers: Top drivers by importance
        regime_tags: Market regime classifications
        quality_flags: Data quality indicators
        data_gaps: Missing data sources
        narrative: Full narrative text (1000+ words)
        quant_payload: Quantitative metrics JSON
        receipts: Evidence/source receipts
        source_model: AI model used (gpt-4, claude-3, etc.)

    Returns:
        ID of inserted row
    """
    query = """
        INSERT INTO features.intel_drops (
            as_of_ts, domain, horizon, direction, pressure_cents, edge,
            driver_weights, top_drivers, regime_tags, quality_flags, data_gaps,
            narrative, quant_payload, receipts, source_model, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        ON CONFLICT (as_of_ts, domain, horizon)
        DO UPDATE SET
            direction = EXCLUDED.direction,
            pressure_cents = EXCLUDED.pressure_cents,
            edge = EXCLUDED.edge,
            driver_weights = EXCLUDED.driver_weights,
            top_drivers = EXCLUDED.top_drivers,
            regime_tags = EXCLUDED.regime_tags,
            quality_flags = EXCLUDED.quality_flags,
            data_gaps = EXCLUDED.data_gaps,
            narrative = EXCLUDED.narrative,
            quant_payload = EXCLUDED.quant_payload,
            receipts = EXCLUDED.receipts,
            source_model = EXCLUDED.source_model
        RETURNING id
    """

    result = await conn.fetchval(
        query,
        as_of_ts,
        domain,
        horizon,
        direction,
        pressure_cents,
        edge,
        driver_weights,
        top_drivers,
        regime_tags,
        quality_flags,
        data_gaps,
        narrative,
        quant_payload,
        receipts,
        source_model,
        datetime.utcnow()
    )

    return result


async def insert_intel_drop_from_features(
    conn: asyncpg.Connection,
    features: ExtractedFeatures,
    narrative: str,
    quant_payload: Dict[str, Any],
    receipts: Optional[Dict[str, Any]] = None,
    source_model: Optional[str] = None
) -> int:
    """
    Insert Intel Drop from ExtractedFeatures.

    Args:
        conn: Database connection
        features: Extracted features from pulse
        narrative: Full narrative text
        quant_payload: Quantitative metrics
        receipts: Evidence sources
        source_model: AI model used

    Returns:
        ID of inserted row
    """
    return await insert_intel_drop(
        conn=conn,
        domain=features.domain,
        horizon=features.horizon,
        as_of_ts=features.as_of_ts,
        direction=features.direction,
        pressure_cents=features.pressure_cents,
        edge=features.edge,
        driver_weights=features.driver_weights,
        top_drivers=features.top_drivers,
        regime_tags=features.regime_tags,
        quality_flags=features.quality_flags,
        data_gaps=features.data_gaps,
        narrative=narrative,
        quant_payload=quant_payload,
        receipts=receipts,
        source_model=source_model
    )


async def insert_intel_drop_rows(
    conn: asyncpg.Connection,
    rows: List[Dict[str, Any]]
) -> List[int]:
    """
    Batch insert multiple Intel Drop rows.

    Args:
        conn: Database connection
        rows: List of row dictionaries

    Returns:
        List of inserted IDs
    """
    ids = []
    for row in rows:
        row_id = await insert_intel_drop(
            conn=conn,
            domain=row['domain'],
            horizon=row['horizon'],
            as_of_ts=row['as_of_ts'],
            direction=row['direction'],
            pressure_cents=row['pressure_cents'],
            edge=row['edge'],
            driver_weights=row.get('driver_weights', {}),
            top_drivers=row.get('top_drivers', []),
            regime_tags=row.get('regime_tags', []),
            quality_flags=row.get('quality_flags', []),
            data_gaps=row.get('data_gaps', []),
            narrative=row['narrative'],
            quant_payload=row.get('quant_payload', {}),
            receipts=row.get('receipts'),
            source_model=row.get('source_model')
        )
        ids.append(row_id)
    return ids


async def get_latest_intel_drops(
    conn: asyncpg.Connection,
    domain: Optional[str] = None,
    horizon: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get the most recent Intel Drops.

    Args:
        conn: Database connection
        domain: Filter by domain (can be None for all)
        horizon: Filter by horizon (can be None for all)
        limit: Maximum number of rows

    Returns:
        List of Intel Drop dictionaries
    """
    query = """
        SELECT
            id, as_of_ts, domain, horizon, direction, pressure_cents, edge,
            driver_weights, top_drivers, regime_tags, quality_flags, data_gaps,
            narrative, quant_payload, receipts, source_model, created_at
        FROM features.intel_drops
        WHERE ($1::text IS NULL OR domain = $1)
          AND ($2::text IS NULL OR horizon = $2)
        ORDER BY as_of_ts DESC, domain, horizon
        LIMIT $3
    """

    rows = await conn.fetch(query, domain, horizon, limit)

    return [
        {
            'id': row['id'],
            'as_of_ts': row['as_of_ts'].isoformat() if row['as_of_ts'] else None,
            'domain': row['domain'],
            'horizon': row['horizon'],
            'direction': row['direction'],
            'pressure_cents': row['pressure_cents'],
            'edge': row['edge'],
            'driver_weights': _parse_json(row['driver_weights'], {}),
            'top_drivers': _parse_json(row['top_drivers'], []),
            'regime_tags': row['regime_tags'],
            'quality_flags': row['quality_flags'],
            'data_gaps': row['data_gaps'],
            'narrative': row['narrative'],
            'quant_payload': _parse_json(row['quant_payload'], {}),
            'receipts': _parse_json(row['receipts'], None),
            'source_model': row['source_model'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None
        }
        for row in rows
    ]


async def get_intel_drop_by_id(
    conn: asyncpg.Connection,
    drop_id: int
) -> Optional[Dict[str, Any]]:
    """
    Get a single Intel Drop by ID.

    Args:
        conn: Database connection
        drop_id: Intel Drop ID

    Returns:
        Intel Drop dictionary or None
    """
    query = """
        SELECT
            id, as_of_ts, domain, horizon, direction, pressure_cents, edge,
            driver_weights, top_drivers, regime_tags, quality_flags, data_gaps,
            narrative, quant_payload, receipts, source_model, created_at
        FROM features.intel_drops
        WHERE id = $1
    """

    row = await conn.fetchrow(query, drop_id)
    if not row:
        return None

    return {
        'id': row['id'],
        'as_of_ts': row['as_of_ts'].isoformat() if row['as_of_ts'] else None,
        'domain': row['domain'],
        'horizon': row['horizon'],
        'direction': row['direction'],
        'pressure_cents': row['pressure_cents'],
        'edge': row['edge'],
        'driver_weights': _parse_json(row['driver_weights'], {}),
        'top_drivers': _parse_json(row['top_drivers'], []),
        'regime_tags': row['regime_tags'],
        'quality_flags': row['quality_flags'],
        'data_gaps': row['data_gaps'],
        'narrative': row['narrative'],
        'quant_payload': _parse_json(row['quant_payload'], {}),
        'receipts': _parse_json(row['receipts'], None),
        'source_model': row['source_model'],
        'created_at': row['created_at'].isoformat() if row['created_at'] else None
    }


async def get_domain_history(
    conn: asyncpg.Connection,
    domain: str,
    horizon: str = '1W',
    days: int = 30
) -> List[Dict[str, Any]]:
    """
    Get historical Intel Drops for a domain.

    Args:
        conn: Database connection
        domain: Specialist domain
        horizon: Time horizon
        days: Number of days of history

    Returns:
        List of Intel Drop dictionaries
    """
    query = """
        SELECT
            id, as_of_ts, domain, horizon, direction, pressure_cents, edge,
            driver_weights, top_drivers, regime_tags, created_at
        FROM features.intel_drops
        WHERE domain = $1
          AND horizon = $2
          AND as_of_ts >= NOW() - INTERVAL '1 day' * $3
        ORDER BY as_of_ts ASC
    """

    rows = await conn.fetch(query, domain, horizon, days)

    return [
        {
            'id': row['id'],
            'as_of_ts': row['as_of_ts'].isoformat() if row['as_of_ts'] else None,
            'domain': row['domain'],
            'horizon': row['horizon'],
            'direction': row['direction'],
            'pressure_cents': row['pressure_cents'],
            'edge': row['edge'],
            'driver_weights': _parse_json(row['driver_weights'], {}),
            'top_drivers': _parse_json(row['top_drivers'], []),
            'regime_tags': row['regime_tags'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None
        }
        for row in rows
    ]


async def get_consensus_view(
    conn: asyncpg.Connection,
    as_of_ts: Optional[datetime] = None,
    horizon: str = '1W'
) -> Dict[str, Any]:
    """
    Get consensus view across all domains for a timestamp.

    Args:
        conn: Database connection
        as_of_ts: Point in time (default: latest)
        horizon: Time horizon

    Returns:
        Consensus dictionary with aggregated signals
    """
    if as_of_ts is None:
        # Get latest timestamp
        latest = await conn.fetchval("""
            SELECT MAX(as_of_ts) FROM features.intel_drops WHERE horizon = $1
        """, horizon)
        as_of_ts = latest

    query = """
        SELECT
            domain, direction, pressure_cents, edge, top_drivers, regime_tags
        FROM features.intel_drops
        WHERE as_of_ts = $1 AND horizon = $2
        ORDER BY domain
    """

    rows = await conn.fetch(query, as_of_ts, horizon)

    if not rows:
        return {'as_of_ts': as_of_ts.isoformat() if as_of_ts else None, 'domains': {}}

    domains = {}
    total_direction = 0
    total_pressure = 0.0
    total_edge = 0.0

    for row in rows:
        domains[row['domain']] = {
            'direction': row['direction'],
            'pressure_cents': row['pressure_cents'],
            'edge': row['edge'],
            'top_drivers': row['top_drivers'],
            'regime_tags': row['regime_tags']
        }
        total_direction += row['direction']
        total_pressure += row['pressure_cents']
        total_edge += row['edge']

    n = len(rows)

    return {
        'as_of_ts': as_of_ts.isoformat() if as_of_ts else None,
        'horizon': horizon,
        'num_domains': n,
        'consensus_direction': total_direction / n if n > 0 else 0,
        'consensus_pressure': total_pressure / n if n > 0 else 0,
        'average_edge': total_edge / n if n > 0 else 0,
        'domains': domains
    }


# Synchronous wrappers for convenience
def insert_intel_drop_sync(row: Dict[str, Any]) -> int:
    """Synchronous wrapper for insert_intel_drop."""
    import asyncio

    async def _insert():
        conn = await get_connection()
        try:
            return await insert_intel_drop(
                conn=conn,
                domain=row['domain'],
                horizon=row['horizon'],
                as_of_ts=row['as_of_ts'],
                direction=row['direction'],
                pressure_cents=row['pressure_cents'],
                edge=row['edge'],
                driver_weights=row.get('driver_weights', {}),
                top_drivers=row.get('top_drivers', []),
                regime_tags=row.get('regime_tags', []),
                quality_flags=row.get('quality_flags', []),
                data_gaps=row.get('data_gaps', []),
                narrative=row['narrative'],
                quant_payload=row.get('quant_payload', {}),
                receipts=row.get('receipts'),
                source_model=row.get('source_model')
            )
        finally:
            await conn.close()

    return asyncio.run(_insert())


def get_latest_intel_drops_sync(
    domain: Optional[str] = None,
    horizon: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Synchronous wrapper for get_latest_intel_drops."""
    import asyncio

    async def _get():
        conn = await get_connection()
        try:
            return await get_latest_intel_drops(conn, domain, horizon, limit)
        finally:
            await conn.close()

    return asyncio.run(_get())
