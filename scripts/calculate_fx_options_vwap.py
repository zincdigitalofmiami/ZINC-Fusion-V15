#!/usr/bin/env python3
"""
Calculate VWAP approximations for FX options using available Databento data.
Uses Ray distributed processing for efficient calculation across 300K+ records.

IMPORTANT: This is NOT true VWAP calculation, which requires intraday trade data.
This calculates daily approximations using available OHLCV data.

VWAP Methods:
1. close_vwap: Close price × volume (simplest approximation)
2. ohlc_avg_vwap: OHLC average × volume (better daily approximation)
"""

import os
import sys
import ray
import psycopg2
from psycopg2.extras import execute_batch
from psycopg2 import pool

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)


def get_db_connection():
    """Create a new database connection (each Ray task gets its own)."""
    return psycopg2.connect(DATABASE_URL)


def close_db_connection(conn):
    """Close a database connection."""
    if conn:
        conn.close()


@ray.remote
def calculate_vwap_batch(records):
    """Ray remote function to calculate VWAP for a batch of records."""
    results = []
    for record in records:
        underlying, event_date, open_, high, low, close, volume = record

        # Method 1: Close price × volume (simplest)
        close_vwap = close * volume if close and volume else None

        # Method 2: OHLC average × volume (better daily approximation)
        if open_ and high and low and close and volume:
            ohlc_avg = (open_ + high + low + close) / 4
            ohlc_avg_vwap = ohlc_avg * volume
        else:
            ohlc_avg_vwap = None

        results.append((close_vwap, ohlc_avg_vwap, underlying, event_date))

    return results


@ray.remote
def process_symbol_vwap(underlying):
    """Process VWAP for a single underlying symbol using individual connections."""
    try:
        # Create dedicated connection for this task
        conn = get_db_connection()
        cur = conn.cursor()

        # Get data for this underlying only
        cur.execute(
            """
            SELECT underlying, event_date, open, high, low, close, volume
            FROM mkt.options_1d
            WHERE underlying = %s AND volume IS NOT NULL AND close IS NOT NULL
            ORDER BY event_date
        """,
            (underlying,),
        )

        rows = cur.fetchall()
        cur.close()
        close_db_connection(conn)  # Close connection

        if not rows:
            return []

        # Process in small batches locally
        batch_size = 500
        batches = [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]

        # Process batches locally (call function directly, not remote)
        symbol_updates = []
        for batch in batches:
            # Call the calculation function directly (not as Ray remote)
            batch_updates = []
            for record in batch:
                underlying, event_date, open_, high, low, close, volume = record

                # Method 1: Close price × volume (simplest)
                close_vwap = close * volume if close and volume else None

                # Method 2: OHLC average × volume (better daily approximation)
                if open_ and high and low and close and volume:
                    ohlc_avg = (open_ + high + low + close) / 4
                    ohlc_avg_vwap = ohlc_avg * volume
                else:
                    ohlc_avg_vwap = None

                batch_updates.append(
                    (close_vwap, ohlc_avg_vwap, underlying, event_date)
                )

            symbol_updates.extend(batch_updates)

        return symbol_updates

    except Exception as e:
        print(f"❌ Error processing {underlying}: {e}")
        return []


def calculate_vwap_approximations():
    """Calculate VWAP approximations for FX options using Ray distributed processing."""

    # Initialize Ray cluster
    ray.init(address="auto", ignore_reinit_error=True)
    cluster_cpus = ray.cluster_resources().get("CPU", 0)
    print("=== CALCULATING FX OPTIONS VWAP APPROXIMATIONS (INDIVIDUAL CONNECTIONS) ===")
    print(f"Ray cluster: {cluster_cpus:.0f} CPUs available")

    # Get total count first
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM mkt.options_1d WHERE underlying LIKE '6%' AND volume IS NOT NULL AND close IS NOT NULL"
    )
    total_records = cur.fetchone()[0]
    cur.close()
    close_db_connection(conn)

    print(f"Total FX options records to process: {total_records:,}")

    # Get unique underlying symbols
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT underlying FROM mkt.options_1d WHERE underlying LIKE '6%' ORDER BY underlying"
    )
    underlyings = [row[0] for row in cur.fetchall()]
    cur.close()
    close_db_connection(conn)

    print(f"Found {len(underlyings)} unique FX underlying symbols")

    # Process symbols in parallel with Ray (each task creates its own connection)
    print("Submitting symbols to Ray cluster...")
    symbol_futures = [
        process_symbol_vwap.remote(underlying) for underlying in underlyings
    ]

    # Collect results
    all_updates = []
    completed = 0
    for future in symbol_futures:
        symbol_updates = ray.get(future)
        all_updates.extend(symbol_updates)
        completed += 1
        if completed % 1 == 0:  # Show progress for each symbol since there are only 5
            print(
                f"  Processed {completed}/{len(underlyings)} symbols ({len(all_updates):,} updates so far)"
            )

    print(
        f"Calculated {len(all_updates)} VWAP approximations across {len(underlyings)} symbols"
    )

    # Batch update the database in smaller chunks
    if all_updates:
        print("Updating database in batches...")

        # Split updates into smaller chunks
        update_batch_size = 5000  # Reasonable batch size
        update_batches = [
            all_updates[i : i + update_batch_size]
            for i in range(0, len(all_updates), update_batch_size)
        ]

        total_updated = 0
        for i, update_batch in enumerate(update_batches):
            conn = get_db_connection()
            cur = conn.cursor()

            execute_batch(
                cur,
                """
                UPDATE mkt.options_1d
                SET
                    close_vwap = %s,
                    ohlc_avg_vwap = %s
                WHERE underlying = %s AND event_date = %s
            """,
                update_batch,
                page_size=1000,
            )

            conn.commit()
            cur.close()
            close_db_connection(conn)

            total_updated += len(update_batch)
            print(
                f"  Updated batch {i+1}/{len(update_batches)}: {total_updated:,}/{len(all_updates):,} records"
            )

        print(f"✅ Updated {len(all_updates)} records with VWAP approximations")

    # Show sample results
    print("\n=== SAMPLE VWAP RESULTS ===")
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT underlying, event_date, close, volume, close_vwap, ohlc_avg_vwap
        FROM mkt.options_1d
        WHERE underlying LIKE '6%' AND close_vwap IS NOT NULL
        ORDER BY event_date DESC
        LIMIT 10
    """
    )

    for row in cur.fetchall():
        underlying, date, close, volume, close_vwap, ohlc_vwap = row
        print(
            f"{underlying} {date}: Close={close:.6f}, Vol={volume}, Close_VWAP={close_vwap:.2f}, OHLC_VWAP={ohlc_vwap:.2f}"
        )

    # Summary statistics
    print("\n=== VWAP CALCULATION SUMMARY ===")
    cur.execute(
        """
        SELECT
            COUNT(*) as total_records,
            COUNT(close_vwap) as close_vwap_calculated,
            COUNT(ohlc_avg_vwap) as ohlc_vwap_calculated,
            ROUND(AVG(close_vwap)::numeric, 2) as avg_close_vwap,
            ROUND(AVG(ohlc_avg_vwap)::numeric, 2) as avg_ohlc_vwap
        FROM mkt.options_1d
        WHERE underlying LIKE '6%'
    """
    )

    stats = cur.fetchone()
    total, close_calc, ohlc_calc, avg_close, avg_ohlc = stats

    print(f"Total FX options records: {total:,}")
    print(f"Close VWAP calculated: {close_calc:,} ({100*close_calc/total:.1f}%)")
    print(f"OHLC VWAP calculated: {ohlc_calc:,} ({100*close_calc/total:.1f}%)")
    print(f"Average Close VWAP: {avg_close}")
    print(f"Average OHLC VWAP: {avg_ohlc}")

    cur.close()
    close_db_connection(conn)

    print("\n" + "=" * 60)
    print("⚠️  IMPORTANT DISCLAIMER:")
    print("These are DAILY VWAP APPROXIMATIONS, not true VWAP.")
    print("True VWAP requires intraday trade data (price × volume).")
    print("Databento provides daily aggregates only.")
    print("=" * 60)


if __name__ == "__main__":
    calculate_vwap_approximations()
