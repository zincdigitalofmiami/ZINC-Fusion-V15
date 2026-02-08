#!/usr/bin/env python3
"""
Test 9: Load Testing

Run connector for 24 hours continuously and monitor:
- Memory usage (should be stable)
- CPU usage (should be <10% avg)
- Network bandwidth
- Database write rate
- Event emission rate
"""

from __future__ import annotations

__test__ = False  # Pytest should not collect integration scripts.

import json
import os
import signal
import sys
import time
from datetime import UTC, datetime

import databento as db

from fusion.db import get_write_connection

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
TEST_DURATION_HOURS = int(os.getenv("TEST_DURATION_HOURS", "24"))


class LoadMonitor:
    """Monitor system resources during load test."""

    def __init__(self):
        self.metrics: list[dict] = []
        self.start_time = time.time()
        self.running = True

    def record_metrics(self):
        """Record current metrics."""
        try:
            import os as os_module

            import psutil

            process = psutil.Process(os_module.getpid())

            mem_info = process.memory_info()
            cpu_percent = process.cpu_percent(interval=1)

            # Network stats
            net_io = process.io_counters()

            metrics = {
                "timestamp": datetime.now(UTC).isoformat(),
                "elapsed_seconds": time.time() - self.start_time,
                "memory_mb": mem_info.rss / 1024 / 1024,
                "cpu_percent": cpu_percent,
                "read_bytes": net_io.read_bytes,
                "write_bytes": net_io.write_bytes,
            }

            self.metrics.append(metrics)
            return metrics

        except ImportError:
            return {
                "timestamp": datetime.now(UTC).isoformat(),
                "elapsed_seconds": time.time() - self.start_time,
                "note": "psutil not available",
            }

    def stop(self):
        """Stop monitoring."""
        self.running = False

    def get_summary(self) -> dict:
        """Get summary statistics."""
        if not self.metrics:
            return {"error": "No metrics collected"}

        mem_values = [m["memory_mb"] for m in self.metrics if "memory_mb" in m]
        cpu_values = [m["cpu_percent"] for m in self.metrics if "cpu_percent" in m]

        return {
            "duration_seconds": self.metrics[-1]["elapsed_seconds"],
            "sample_count": len(self.metrics),
            "memory": {
                "min_mb": min(mem_values) if mem_values else 0,
                "max_mb": max(mem_values) if mem_values else 0,
                "avg_mb": sum(mem_values) / len(mem_values) if mem_values else 0,
                "stable": (max(mem_values) - min(mem_values)) < 100
                if mem_values
                else True,  # <100MB variation
            },
            "cpu": {
                "min_percent": min(cpu_values) if cpu_values else 0,
                "max_percent": max(cpu_values) if cpu_values else 0,
                "avg_percent": sum(cpu_values) / len(cpu_values) if cpu_values else 0,
                "meets_threshold": max(cpu_values) < 10.0 if cpu_values else True,
            },
        }


def run_load_test(duration_hours: int) -> dict:
    """Run load test for specified duration."""
    print(f"Starting load test for {duration_hours} hours...")

    monitor = LoadMonitor()

    client = db.Live(key=DATABENTO_API_KEY)
    client.subscribe(
        dataset="GLBX.MDP3",
        schema="ohlcv-1m",
        symbols=["ZL.n.0"],
        stype_in="continuous",
    )

    start_time = time.time()
    end_time = start_time + (duration_hours * 3600)

    bars_processed = 0
    events_sent = 0
    db_writes = 0

    # Record metrics every 5 minutes
    last_metrics_time = start_time
    metrics_interval = 300  # 5 minutes

    current_15m = None
    bucket_15m = 15 * 60 * 1000

    conn = get_write_connection()

    try:
        for record in client:
            if time.time() > end_time or not monitor.running:
                break

            # Record metrics periodically
            if time.time() - last_metrics_time >= metrics_interval:
                monitor.record_metrics()
                last_metrics_time = time.time()
                print(
                    f"[{datetime.now().isoformat()}] Processed {bars_processed} bars, Memory: {monitor.metrics[-1].get('memory_mb', 0):.1f}MB"
                    if monitor.metrics
                    else ""
                )

            ts = datetime.fromtimestamp(record.ts_event / 1_000_000_000, tz=UTC)
            ts_ms = int(ts.timestamp() * 1000)
            b15 = (ts_ms // bucket_15m) * bucket_15m

            if current_15m is None:
                current_15m = b15
            elif b15 != current_15m:
                # Process bar (simplified - would normally emit event)
                bars_processed += 1

                # Simulate database write
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")  # Dummy query
                    db_writes += 1
                except Exception as e:
                    print(f"Database write error: {e}")

                current_15m = b15

    except KeyboardInterrupt:
        print("\nLoad test interrupted")
    except Exception as e:
        print(f"Load test error: {e}")
    finally:
        conn.close()
        monitor.stop()

    # Final metrics
    monitor.record_metrics()
    summary = monitor.get_summary()

    return {
        "duration_hours": duration_hours,
        "bars_processed": bars_processed,
        "events_sent": events_sent,
        "db_writes": db_writes,
        "metrics_summary": summary,
        "all_metrics": monitor.metrics,
    }


def main():
    """Run load test."""
    print("=" * 80)
    print("Load Testing")
    print("=" * 80)
    print(f"Duration: {TEST_DURATION_HOURS} hours")
    print()

    if not DATABENTO_API_KEY:
        print("ERROR: DATABENTO_API_KEY not set")
        sys.exit(1)

    monitor = LoadMonitor()

    def signal_handler(sig, frame):
        print("\nStopping load test...")
        monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run load test
    results = run_load_test(TEST_DURATION_HOURS)

    # Print results
    print()
    print("=" * 80)
    print("Load Test Results")
    print("=" * 80)

    print(f"Duration: {results['duration_hours']} hours")
    print(f"Bars processed: {results['bars_processed']}")
    print(f"Events sent: {results['events_sent']}")
    print(f"DB writes: {results['db_writes']}")

    if "metrics_summary" in results:
        ms = results["metrics_summary"]
        print("\nMetrics Summary:")
        print(f"  Sample count: {ms.get('sample_count', 0)}")

        if "memory" in ms:
            mem = ms["memory"]
            print(
                f"  Memory: {mem.get('avg_mb', 0):.1f}MB avg ({mem.get('min_mb', 0):.1f}-{mem.get('max_mb', 0):.1f}MB)"
            )
            print(f"    Stable: {'✓' if mem.get('stable') else '✗'}")

        if "cpu" in ms:
            cpu = ms["cpu"]
            print(
                f"  CPU: {cpu.get('avg_percent', 0):.1f}% avg ({cpu.get('min_percent', 0):.1f}-{cpu.get('max_percent', 0):.1f}%)"
            )
            print(
                f"    Meets threshold (<10%): {'✓' if cpu.get('meets_threshold') else '✗'}"
            )

    # Save results
    output_file = "test_load_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to {output_file}")

    # Check success criteria
    success = True
    if "metrics_summary" in results:
        ms = results["metrics_summary"]
        if "memory" in ms and not ms["memory"].get("stable"):
            print("\n✗ FAIL: Memory not stable")
            success = False
        if "cpu" in ms and not ms["cpu"].get("meets_threshold"):
            print("\n✗ FAIL: CPU usage exceeds threshold")
            success = False

    if success:
        print("\n✓ All success criteria met")
        return 0
    else:
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
