#!/usr/bin/env python3
"""
Test 6: Parallel Symbol Collection

Run TWO live connectors simultaneously:
- Connector A: ZL.c.0 (calendar)
- Connector B: ZL.n.0 (OI-ranked)

Write to separate test tables (not in production):
- test_c (calendar-ranked)
- test_n (OI-ranked)

Run for 7 days minimum and compare results.
"""

from __future__ import annotations

__test__ = False  # Pytest should not collect integration scripts.

import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import databento as db

from fusion.db import get_write_connection

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
TEST_DURATION_DAYS = int(os.getenv("TEST_DURATION_DAYS", "7"))


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class ParallelCollector:
    """Collect bars and write to test table."""

    def __init__(self, symbol: str, table_suffix: str):
        self.symbol = symbol
        self.table_suffix = table_suffix
        self.table_name = f"analytics.zl_price_15m_test_{table_suffix}"  # test tables (not in production)
        self.bars: list[Bar] = []
        self.running = True

    def to_datetime(self, ts_event) -> datetime:
        """Convert timestamp to datetime."""
        if isinstance(ts_event, datetime):
            return ts_event.astimezone(UTC)
        if isinstance(ts_event, int):
            return datetime.fromtimestamp(ts_event / 1_000_000_000, tz=UTC)
        if isinstance(ts_event, float):
            return datetime.fromtimestamp(ts_event, tz=UTC)
        return datetime.fromisoformat(str(ts_event)).astimezone(UTC)

    def create_test_table(self):
        """Create test table if it doesn't exist."""
        conn = get_write_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL UNIQUE,
                        open NUMERIC(10,4) NOT NULL,
                        high NUMERIC(10,4) NOT NULL,
                        low NUMERIC(10,4) NOT NULL,
                        close NUMERIC(10,4) NOT NULL,
                        volume INTEGER,
                        source VARCHAR(50) DEFAULT 'test_{self.table_suffix}',
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.table_name}_ts
                    ON {self.table_name}(timestamp DESC)
                """)
            conn.commit()
        finally:
            conn.close()

    def collect_and_write(self, duration_days: int):
        """Collect bars and write to database."""
        self.create_test_table()

        client = db.Live(key=DATABENTO_API_KEY)
        client.subscribe(
            dataset="GLBX.MDP3",
            schema="ohlcv-1m",
            symbols=[self.symbol],
            stype_in="continuous",
        )

        start_time = time.time()
        end_time = start_time + (duration_days * 24 * 3600)

        current_15m = None
        bucket_15m = 15 * 60 * 1000
        bars_written = 0

        print(f"[{self.symbol}] Starting collection for {duration_days} days...")
        print(f"[{self.symbol}] Writing to {self.table_name}")

        conn = get_write_connection()

        try:
            for record in client:
                if not self.running or time.time() > end_time:
                    break

                ts = self.to_datetime(record.ts_event)
                ts_ms = int(ts.timestamp() * 1000)
                b15 = (ts_ms // bucket_15m) * bucket_15m
                bucket_ts = datetime.fromtimestamp(b15 / 1000, tz=UTC)

                if current_15m is None:
                    current_15m = b15
                    current_bar = Bar(
                        timestamp=bucket_ts,
                        open=float(record.open),
                        high=float(record.high),
                        low=float(record.low),
                        close=float(record.close),
                        volume=int(record.volume)
                        if hasattr(record, "volume") and record.volume is not None
                        else 0,
                    )
                elif b15 != current_15m:
                    # Write previous bar
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""
                            INSERT INTO {self.table_name}
                            (timestamp, open, high, low, close, volume, source)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (timestamp) DO UPDATE SET
                                open = EXCLUDED.open,
                                high = EXCLUDED.high,
                                low = EXCLUDED.low,
                                close = EXCLUDED.close,
                                volume = EXCLUDED.volume
                        """,
                            (
                                current_bar.timestamp,
                                current_bar.open,
                                current_bar.high,
                                current_bar.low,
                                current_bar.close,
                                current_bar.volume,
                                f"test_{self.table_suffix}",
                            ),
                        )
                    conn.commit()
                    bars_written += 1
                    self.bars.append(current_bar)

                    # Start new bar
                    current_15m = b15
                    current_bar = Bar(
                        timestamp=bucket_ts,
                        open=float(record.open),
                        high=float(record.high),
                        low=float(record.low),
                        close=float(record.close),
                        volume=int(record.volume)
                        if hasattr(record, "volume") and record.volume is not None
                        else 0,
                    )

                    if bars_written % 100 == 0:
                        print(f"[{self.symbol}] Written {bars_written} bars...")
                else:
                    # Update current bar
                    current_bar.high = max(current_bar.high, float(record.high))
                    current_bar.low = min(current_bar.low, float(record.low))
                    current_bar.close = float(record.close)
                    current_bar.volume += (
                        int(record.volume)
                        if hasattr(record, "volume") and record.volume is not None
                        else 0
                    )

        except KeyboardInterrupt:
            print(f"[{self.symbol}] Interrupted")
        except Exception as e:
            print(f"[{self.symbol}] Error: {e}")
        finally:
            conn.close()
            print(
                f"[{self.symbol}] Collection complete. Total bars written: {bars_written}"
            )

    def stop(self):
        """Stop collection."""
        self.running = False


def compare_results() -> dict:
    """Compare results from both test tables."""
    import pandas as pd

    from fusion.db import get_read_engine

    engine = get_read_engine()

    # Read both tables
    # test tables (not in production)
    query_c = "SELECT timestamp, open, high, low, close, volume FROM analytics.zl_price_15m_test_c ORDER BY timestamp"
    query_n = "SELECT timestamp, open, high, low, close, volume FROM analytics.zl_price_15m_test_n ORDER BY timestamp"

    df_c = pd.read_sql(query_c, engine)
    df_n = pd.read_sql(query_n, engine)

    if len(df_c) == 0 or len(df_n) == 0:
        return {
            "error": "One or both tables are empty",
            "c_count": len(df_c),
            "n_count": len(df_n),
        }

    # Merge on timestamp
    merged = pd.merge(df_c, df_n, on="timestamp", suffixes=("_c", "_n"), how="outer")

    # Calculate differences
    common = merged.dropna(subset=["close_c", "close_n"])

    if len(common) == 0:
        return {
            "error": "No common timestamps",
            "c_count": len(df_c),
            "n_count": len(df_n),
        }

    common["price_diff_pct"] = (
        abs(common["close_c"] - common["close_n"]) / common["close_c"] * 100
    )
    common["volume_diff_pct"] = (
        abs(common["volume_c"] - common["volume_n"])
        / common[["volume_c", "volume_n"]].max(axis=1)
        * 100
    )

    # Statistics
    price_stats = {
        "max_diff_pct": common["price_diff_pct"].max(),
        "avg_diff_pct": common["price_diff_pct"].mean(),
        "p95_diff_pct": common["price_diff_pct"].quantile(0.95),
        "bars_lt_0_1_pct": (common["price_diff_pct"] < 0.1).sum(),
        "bars_lt_0_1_pct_pct": (common["price_diff_pct"] < 0.1).sum()
        / len(common)
        * 100,
    }

    volume_stats = {
        "max_diff_pct": common["volume_diff_pct"].max(),
        "avg_diff_pct": common["volume_diff_pct"].mean(),
        "correlation": common["volume_c"].corr(common["volume_n"]),
    }

    # Coverage
    c_only = merged[merged["close_n"].isna()]
    n_only = merged[merged["close_c"].isna()]

    return {
        "c_bars": len(df_c),
        "n_bars": len(df_n),
        "common_bars": len(common),
        "c_only_bars": len(c_only),
        "n_only_bars": len(n_only),
        "coverage_c": len(common) / len(df_c) * 100 if len(df_c) > 0 else 0,
        "coverage_n": len(common) / len(df_n) * 100 if len(df_n) > 0 else 0,
        "price_stats": price_stats,
        "volume_stats": volume_stats,
    }


def main():
    """Run parallel symbol collection test."""
    print("=" * 80)
    print("Parallel Symbol Collection Test")
    print("=" * 80)
    print(f"Duration: {TEST_DURATION_DAYS} days")
    print()

    if not DATABENTO_API_KEY:
        print("ERROR: DATABENTO_API_KEY not set")
        sys.exit(1)

    print("NOTE: This test requires running TWO instances simultaneously.")
    print("Run in separate terminals:")
    print("  1. python scripts/test_parallel_symbols.py --symbol ZL.c.0 --suffix c")
    print("  2. python scripts/test_parallel_symbols.py --symbol ZL.n.0 --suffix n")
    print()
    print("After collection completes, run comparison:")
    print("  python scripts/test_parallel_symbols.py --compare")
    print()

    # Check if comparing
    if "--compare" in sys.argv:
        print("Comparing results...")
        comparison = compare_results()

        output_file = "parallel_symbols_comparison.json"
        with open(output_file, "w") as f:
            json.dump(comparison, f, indent=2, default=str)

        print("=" * 80)
        print("Comparison Results")
        print("=" * 80)
        print(f"ZL.c.0 bars: {comparison.get('c_bars', 0)}")
        print(f"ZL.n.0 bars: {comparison.get('n_bars', 0)}")
        print(f"Common bars: {comparison.get('common_bars', 0)}")

        if "price_stats" in comparison:
            ps = comparison["price_stats"]
            print("\nPrice Differences:")
            print(f"  Max: {ps['max_diff_pct']:.4f}%")
            print(f"  Avg: {ps['avg_diff_pct']:.4f}%")
            print(f"  P95: {ps['p95_diff_pct']:.4f}%")
            print(
                f"  Bars <0.1%: {ps['bars_lt_0_1_pct']} ({ps['bars_lt_0_1_pct_pct']:.1f}%)"
            )

        print(f"\nResults saved to {output_file}")
        return

    # Parse args for symbol/suffix
    symbol = "ZL.c.0"
    suffix = "c"

    if "--symbol" in sys.argv:
        idx = sys.argv.index("--symbol")
        if idx + 1 < len(sys.argv):
            symbol = sys.argv[idx + 1]

    if "--suffix" in sys.argv:
        idx = sys.argv.index("--suffix")
        if idx + 1 < len(sys.argv):
            suffix = sys.argv[idx + 1]

    collector = ParallelCollector(symbol, suffix)

    def signal_handler(sig, frame):
        print("\nStopping collector...")
        collector.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    collector.collect_and_write(TEST_DURATION_DAYS)


if __name__ == "__main__":
    main()
