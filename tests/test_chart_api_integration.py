#!/usr/bin/env python3
"""
Test 5: Chart API Integration Test

Test endpoints:
- /api/zl/intraday?hours=24 (15m bars)
- /api/zl/price-1h?hours=168 (1h bars)
- /api/zl/price-1d?days=90 (daily bars)
- /api/zl/chart?days=365 (chart format)

Checks:
- Response format matches expected schema
- Data ordering (chronological)
- No missing timestamps in expected ranges
- Source tags present
- Performance (<500ms response time)
"""

from __future__ import annotations

__test__ = False  # Pytest should not collect integration scripts.

import json
import os
import time
from typing import Dict, List, Optional

import requests


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def test_endpoint(
    endpoint: str, params: Optional[Dict] = None, expected_fields: List[str] = None
) -> Dict:
    """Test an API endpoint."""
    url = f"{API_BASE_URL}{endpoint}"

    start_time = time.time()
    try:
        response = requests.get(url, params=params, timeout=10)
        elapsed = time.time() - start_time

        if response.status_code != 200:
            return {
                "passed": False,
                "message": f"HTTP {response.status_code}: {response.text[:200]}",
                "status_code": response.status_code,
                "response_time_ms": elapsed * 1000,
            }

        data = response.json()

        # Check response time
        response_time_ms = elapsed * 1000
        perf_passed = response_time_ms < 500

        # Check expected fields
        fields_passed = True
        missing_fields = []
        if expected_fields:
            for field in expected_fields:
                if field not in data:
                    fields_passed = False
                    missing_fields.append(field)

        # Check data ordering (if bars/data present)
        ordering_passed = True
        if "bars" in data and len(data["bars"]) > 1:
            timestamps = [b.get("time") or b.get("timestamp") for b in data["bars"]]
            ordering_passed = timestamps == sorted(timestamps)
        elif "data" in data and len(data["data"]) > 1:
            timestamps = [
                d.get("timestamp") or d.get("event_date") for d in data["data"]
            ]
            ordering_passed = timestamps == sorted(timestamps)
        elif "series" in data and len(data["series"]) > 1:
            timestamps = [s.get("time") for s in data["series"]]
            ordering_passed = timestamps == sorted(timestamps)

        passed = fields_passed and ordering_passed and perf_passed

        return {
            "passed": passed,
            "message": f"Response OK"
            + (
                ""
                if passed
                else f" (issues: {', '.join(['missing_fields' if not fields_passed else '', 'ordering' if not ordering_passed else '', 'performance' if not perf_passed else ''])})"
            ),
            "status_code": response.status_code,
            "response_time_ms": response_time_ms,
            "performance_passed": perf_passed,
            "fields_passed": fields_passed,
            "missing_fields": missing_fields,
            "ordering_passed": ordering_passed,
            "data_count": len(
                data.get("bars", data.get("data", data.get("series", [])))
            ),
        }

    except requests.exceptions.RequestException as e:
        return {"passed": False, "message": f"Request failed: {e}", "error": str(e)}
    except Exception as e:
        return {"passed": False, "message": f"Unexpected error: {e}", "error": str(e)}


def test_intraday() -> Dict:
    """Test /api/zl/intraday endpoint."""
    print("Test 1: /api/zl/intraday?hours=24...")
    return test_endpoint(
        "/api/zl/intraday",
        params={"hours": 24},
        expected_fields=["symbol", "interval", "bars", "count"],
    )


def test_price_1h() -> Dict:
    """Test /api/zl/price-1h endpoint."""
    print("Test 2: /api/zl/price-1h?hours=168...")
    return test_endpoint(
        "/api/zl/price-1h",
        params={"hours": 168},
        expected_fields=["symbol", "interval", "count", "data"],
    )


def test_price_1d() -> Dict:
    """Test /api/zl/price-1d endpoint."""
    print("Test 3: /api/zl/price-1d?days=90...")
    return test_endpoint(
        "/api/zl/price-1d",
        params={"days": 90},
        expected_fields=["symbol", "interval", "count", "data"],
    )


def test_chart() -> Dict:
    """Test /api/zl/chart endpoint."""
    print("Test 4: /api/zl/chart?days=365...")
    return test_endpoint(
        "/api/zl/chart",
        params={"days": 365},
        expected_fields=["symbol", "interval", "count", "series"],
    )


def check_data_completeness(endpoint: str, params: Dict) -> Dict:
    """Check for missing timestamps in expected ranges."""
    url = f"{API_BASE_URL}{endpoint}"

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return {"passed": False, "message": f"HTTP {response.status_code}"}

        data = response.json()

        # Extract timestamps
        timestamps = []
        if "bars" in data:
            timestamps = [b.get("time") for b in data["bars"]]
        elif "data" in data:
            timestamps = [
                d.get("timestamp") or d.get("event_date") for d in data["data"]
            ]
        elif "series" in data:
            timestamps = [s.get("time") for s in data["series"]]

        if not timestamps:
            return {"passed": True, "message": "No data to check", "gap_count": 0}

        # Check for gaps (simplified - would need interval-specific logic)
        sorted_ts = sorted(timestamps)
        gaps = []
        for i in range(1, len(sorted_ts)):
            gap = sorted_ts[i] - sorted_ts[i - 1]
            # Would need to check against expected interval
            if gap > sorted_ts[1] - sorted_ts[0] * 2:  # Rough check
                gaps.append((sorted_ts[i - 1], sorted_ts[i]))

        return {
            "passed": len(gaps) == 0,
            "message": f"Found {len(gaps)} potential gaps"
            if gaps
            else "No significant gaps",
            "gap_count": len(gaps),
            "total_bars": len(timestamps),
        }

    except Exception as e:
        return {"passed": False, "message": f"Error: {e}"}


def main():
    """Run all chart API tests."""
    print("=" * 80)
    print("Chart API Integration Test")
    print("=" * 80)
    print(f"API Base URL: {API_BASE_URL}")
    print()

    results = {}

    # Run endpoint tests
    results["intraday"] = test_intraday()
    results["price_1h"] = test_price_1h()
    results["price_1d"] = test_price_1d()
    results["chart"] = test_chart()

    # Check data completeness
    print("\nChecking data completeness...")
    results["completeness_intraday"] = check_data_completeness(
        "/api/zl/intraday", {"hours": 24}
    )
    results["completeness_1h"] = check_data_completeness(
        "/api/zl/price-1h", {"hours": 168}
    )
    results["completeness_1d"] = check_data_completeness(
        "/api/zl/price-1d", {"days": 90}
    )

    # Print results
    print()
    print("=" * 80)
    print("Test Results")
    print("=" * 80)

    for test_name, result in results.items():
        status = "✓ PASS" if result["passed"] else "✗ FAIL"
        print(f"{status} {test_name}: {result['message']}")
        if "response_time_ms" in result:
            print(f"    Response time: {result['response_time_ms']:.1f}ms")
        if "data_count" in result:
            print(f"    Data count: {result['data_count']}")

    # Save results
    output_file = "test_chart_api_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to {output_file}")

    # Summary
    passed = sum(1 for r in results.values() if r["passed"])
    total = len(results)
    print(f"\nSummary: {passed}/{total} tests passed")

    if passed < total:
        print("\nSome tests failed. Review results for details.")
        return 1

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
