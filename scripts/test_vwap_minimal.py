#!/usr/bin/env python3
"""
Minimal VWAP test with just a few records
"""
__test__ = False  # Pytest should not collect integration scripts.


import os
import psycopg2
import ray

DATABASE_URL = os.environ.get("DATABASE_URL")


@ray.remote
def calculate_vwap_batch_minimal(records):
    """Minimal VWAP calculation for testing"""
    results = []
    for record in records:
        underlying, event_date, open_, high, low, close, volume = record

        # Simple close × volume
        close_vwap = close * volume if close and volume else None

        results.append((close_vwap, underlying, event_date))

    return results


def test_minimal_vwap():
    """Test VWAP with minimal data"""
    print("Testing minimal VWAP calculation...")

    ray.init(address="auto", ignore_reinit_error=True)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Get just 100 records for testing
    cur.execute(
        """
        SELECT underlying, event_date, open, high, low, close, volume
        FROM mkt.options_1d
        WHERE underlying LIKE '6%' AND volume IS NOT NULL AND close IS NOT NULL
        LIMIT 100
    """
    )

    rows = cur.fetchall()
    conn.close()

    print(f"Testing with {len(rows)} records...")

    # Split into tiny batches
    batch_size = 10
    batches = [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]

    print(f"Split into {len(batches)} batches")

    # Submit to Ray
    ray_futures = [calculate_vwap_batch_minimal.remote(batch) for batch in batches]
    print(f"Submitted {len(ray_futures)} tasks to Ray")

    # Collect results
    all_results = []
    for future in ray_futures:
        batch_results = ray.get(future)
        all_results.extend(batch_results)

    print(f"Received {len(all_results)} results")

    # Sample results
    print("Sample results:")
    for result in all_results[:5]:
        close_vwap, underlying, event_date = result
        print(f"  {underlying} {event_date}: VWAP={close_vwap}")

    ray.shutdown()
    print("✅ Minimal VWAP test successful!")


if __name__ == "__main__":
    test_minimal_vwap()
