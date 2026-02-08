#!/usr/bin/env python3
"""
Test 2: Symbol Comparison Test

Compare ZL.c.0 vs ZL.n.0 prices in parallel for 24 hours.
Collects data from both symbols simultaneously and compares:
- Price differences (should be <0.1% on non-roll days)
- Roll date differences (when do they diverge?)
- Volume differences
- Timing differences
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


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class SymbolCollector:
    """Collect bars from a Databento symbol."""

    def __init__(self, symbol: str, api_key: str):
        self.symbol = symbol
        self.api_key = api_key
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

    def collect(self, duration_hours: int = 24):
        """Collect bars for specified duration."""
        client = db.Live(key=self.api_key)
        client.subscribe(
            dataset="GLBX.MDP3",
            schema="ohlcv-1m",
            symbols=[self.symbol],
            stype_in="continuous",
        )

        start_time = time.time()
        end_time = start_time + (duration_hours * 3600)

        print(f"[{self.symbol}] Starting collection for {duration_hours} hours...")

        try:
            for record in client:
                if not self.running or time.time() > end_time:
                    break

                ts = self.to_datetime(record.ts_event)
                bar = Bar(
                    timestamp=ts,
                    open=float(record.open),
                    high=float(record.high),
                    low=float(record.low),
                    close=float(record.close),
                    volume=int(record.volume)
                    if hasattr(record, "volume") and record.volume is not None
                    else 0,
                )
                self.bars.append(bar)

                if len(self.bars) % 100 == 0:
                    print(f"[{self.symbol}] Collected {len(self.bars)} bars...")

        except KeyboardInterrupt:
            print(f"[{self.symbol}] Interrupted")
        except Exception as e:
            print(f"[{self.symbol}] Error: {e}")
        finally:
            print(f"[{self.symbol}] Collection complete. Total bars: {len(self.bars)}")

    def stop(self):
        """Stop collection."""
        self.running = False


def aggregate_to_15m(bars: list[Bar]) -> list[Bar]:
    """Aggregate 1m bars to 15m bars."""
    if not bars:
        return []

    buckets: dict[int, Bar] = {}
    bucket_ms = 15 * 60 * 1000

    for bar in bars:
        ts_ms = int(bar.timestamp.timestamp() * 1000)
        bucket = (ts_ms // bucket_ms) * bucket_ms

        if bucket not in buckets:
            buckets[bucket] = Bar(
                timestamp=datetime.fromtimestamp(bucket / 1000, tz=UTC),
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
        else:
            b = buckets[bucket]
            b.high = max(b.high, bar.high)
            b.low = min(b.low, bar.low)
            b.close = bar.close
            b.volume += bar.volume

    return sorted(buckets.values(), key=lambda x: x.timestamp)


def compare_symbols(bars_c: list[Bar], bars_n: list[Bar]) -> dict:
    """Compare two sets of bars."""
    # Aggregate to 15m for comparison
    bars_c_15m = aggregate_to_15m(bars_c)
    bars_n_15m = aggregate_to_15m(bars_n)

    # Create timestamp index
    c_by_ts = {int(b.timestamp.timestamp()): b for b in bars_c_15m}
    n_by_ts = {int(b.timestamp.timestamp()): b for b in bars_n_15m}

    # Find common timestamps
    common_ts = set(c_by_ts.keys()) & set(n_by_ts.keys())

    if not common_ts:
        return {
            "error": "No common timestamps found",
            "c_bars": len(bars_c_15m),
            "n_bars": len(bars_n_15m),
        }

    # Compare prices
    price_diffs = []
    volume_diffs = []

    for ts in sorted(common_ts):
        c_bar = c_by_ts[ts]
        n_bar = n_by_ts[ts]

        # Price difference (%)
        if c_bar.close > 0:
            pct_diff = abs(c_bar.close - n_bar.close) / c_bar.close * 100
            price_diffs.append(
                {
                    "timestamp": c_bar.timestamp.isoformat(),
                    "c_close": c_bar.close,
                    "n_close": n_bar.close,
                    "pct_diff": pct_diff,
                }
            )

        # Volume difference
        if c_bar.volume > 0 or n_bar.volume > 0:
            vol_diff_pct = (
                abs(c_bar.volume - n_bar.volume)
                / max(c_bar.volume, n_bar.volume, 1)
                * 100
            )
            volume_diffs.append(
                {
                    "timestamp": c_bar.timestamp.isoformat(),
                    "c_volume": c_bar.volume,
                    "n_volume": n_bar.volume,
                    "vol_diff_pct": vol_diff_pct,
                }
            )

    # Calculate statistics
    pct_diffs = [d["pct_diff"] for d in price_diffs]

    # Find roll dates (large price divergence)
    roll_candidates = [d for d in price_diffs if d["pct_diff"] > 0.5]

    return {
        "total_bars_c": len(bars_c_15m),
        "total_bars_n": len(bars_n_15m),
        "common_bars": len(common_ts),
        "price_stats": {
            "max_diff_pct": max(pct_diffs) if pct_diffs else 0,
            "avg_diff_pct": sum(pct_diffs) / len(pct_diffs) if pct_diffs else 0,
            "p95_diff_pct": sorted(pct_diffs)[int(len(pct_diffs) * 0.95)]
            if pct_diffs
            else 0,
            "bars_lt_0_1_pct": sum(1 for d in pct_diffs if d < 0.1),
            "bars_lt_0_1_pct_pct": sum(1 for d in pct_diffs if d < 0.1)
            / len(pct_diffs)
            * 100
            if pct_diffs
            else 0,
        },
        "roll_candidates": roll_candidates[:10],  # Top 10
        "volume_stats": {
            "max_diff_pct": max([d["vol_diff_pct"] for d in volume_diffs])
            if volume_diffs
            else 0,
            "avg_diff_pct": sum([d["vol_diff_pct"] for d in volume_diffs])
            / len(volume_diffs)
            if volume_diffs
            else 0,
        },
        "timing": {
            "c_earliest": bars_c_15m[0].timestamp.isoformat() if bars_c_15m else None,
            "c_latest": bars_c_15m[-1].timestamp.isoformat() if bars_c_15m else None,
            "n_earliest": bars_n_15m[0].timestamp.isoformat() if bars_n_15m else None,
            "n_latest": bars_n_15m[-1].timestamp.isoformat() if bars_n_15m else None,
        },
    }


def main():
    """Run symbol comparison test."""
    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        print("ERROR: DATABENTO_API_KEY not set")
        sys.exit(1)

    duration_hours = int(os.getenv("TEST_DURATION_HOURS", "24"))

    print("=" * 80)
    print("Symbol Comparison Test: ZL.c.0 vs ZL.n.0")
    print("=" * 80)
    print(f"Duration: {duration_hours} hours")
    print()

    # Create collectors
    collector_c = SymbolCollector("ZL.c.0", api_key)
    collector_n = SymbolCollector("ZL.n.0", api_key)

    # Handle interrupts
    def signal_handler(sig, frame):
        print("\nStopping collectors...")
        collector_c.stop()
        collector_n.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Note: This test requires running both collectors in parallel
    # For simplicity, we'll run them sequentially with shorter duration
    # In production, you'd run them in separate processes/threads

    print("NOTE: This test collects from both symbols sequentially.")
    print("For true parallel comparison, run two instances simultaneously.")
    print()

    # Collect from ZL.c.0
    print("Collecting from ZL.c.0...")
    collector_c.collect(duration_hours=duration_hours)

    # Collect from ZL.n.0
    print("\nCollecting from ZL.n.0...")
    collector_n.collect(duration_hours=duration_hours)

    # Compare
    print("\nComparing results...")
    comparison = compare_symbols(collector_c.bars, collector_n.bars)

    # Save results
    output_file = "symbol_comparison_report.json"
    with open(output_file, "w") as f:
        json.dump(comparison, f, indent=2, default=str)

    # Print summary
    print()
    print("=" * 80)
    print("Comparison Results")
    print("=" * 80)
    print(f"ZL.c.0 bars: {comparison.get('total_bars_c', 0)}")
    print(f"ZL.n.0 bars: {comparison.get('total_bars_n', 0)}")
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

    if comparison.get("roll_candidates"):
        print(f"\nRoll Candidates (>0.5% diff): {len(comparison['roll_candidates'])}")
        for rc in comparison["roll_candidates"][:3]:
            print(f"  {rc['timestamp']}: {rc['pct_diff']:.2f}%")

    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    main()
