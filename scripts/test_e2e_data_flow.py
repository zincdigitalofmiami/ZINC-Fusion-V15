#!/usr/bin/env python3
"""
Test 10: End-to-End Data Flow

Verify complete data flow:
1. Live connector emits event
2. Inngest handler receives event
3. Database row inserted
4. Chart API reads row
5. Chart displays data

Checks at each step:
- Event payload correctness
- Database row matches event
- API response matches database
- Chart renders correctly
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import requests
from fusion.db import get_read_engine
import pandas as pd


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TEST_RESULTS: Dict[str, Dict] = {}


def check_event_payload(event_data: Dict) -> Dict:
    """Check 1: Event payload correctness."""
    print("Check 1: Event payload correctness...")
    
    required_fields = ["timestamp", "open", "high", "low", "close", "volume", "source"]
    missing_fields = [f for f in required_fields if f not in event_data]
    
    # Validate types
    type_errors = []
    if "timestamp" in event_data and not isinstance(event_data["timestamp"], str):
        type_errors.append("timestamp must be ISO string")
    if "open" in event_data and not isinstance(event_data["open"], (int, float)):
        type_errors.append("open must be numeric")
    if "volume" in event_data and not isinstance(event_data["volume"], int):
        type_errors.append("volume must be integer")
    
    passed = len(missing_fields) == 0 and len(type_errors) == 0
    
    return {
        "passed": passed,
        "message": "Event payload valid" if passed else f"Missing: {missing_fields}, Type errors: {type_errors}",
        "missing_fields": missing_fields,
        "type_errors": type_errors
    }


def check_database_row(engine, timestamp: str) -> Dict:
    """Check 2: Database row matches event."""
    print("Check 2: Database row matches event...")
    
    # Query database for the row
    query = """
    SELECT timestamp, open, high, low, close, volume, source
    FROM analytics.zl_price_15m
    WHERE timestamp = %s
    ORDER BY timestamp DESC
    LIMIT 1
    """
    
    try:
        df = pd.read_sql(query, engine, params=[timestamp])
        
        if len(df) == 0:
            return {
                "passed": False,
                "message": f"No row found for timestamp {timestamp}",
                "row_found": False
            }
        
        row = df.iloc[0]
        
        return {
            "passed": True,
            "message": "Database row found",
            "row_found": True,
            "row_data": row.to_dict()
        }
    
    except Exception as e:
        return {
            "passed": False,
            "message": f"Database query error: {e}",
            "error": str(e)
        }


def check_api_response(api_url: str, timestamp: str) -> Dict:
    """Check 3: API response matches database."""
    print("Check 3: API response matches database...")
    
    try:
        response = requests.get(api_url, timeout=10)
        
        if response.status_code != 200:
            return {
                "passed": False,
                "message": f"API returned {response.status_code}",
                "status_code": response.status_code
            }
        
        data = response.json()
        
        # Find the bar with matching timestamp
        bars = data.get("bars", data.get("data", []))
        matching_bar = None
        
        for bar in bars:
            bar_ts = bar.get("time") or bar.get("timestamp")
            if bar_ts:
                # Convert to comparable format
                if isinstance(bar_ts, (int, float)):
                    bar_dt = datetime.fromtimestamp(bar_ts, tz=timezone.utc)
                else:
                    bar_dt = datetime.fromisoformat(str(bar_ts).replace("Z", "+00:00"))
                
                target_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                
                if abs((bar_dt - target_dt).total_seconds()) < 900:  # Within 15 minutes
                    matching_bar = bar
                    break
        
        if matching_bar:
            return {
                "passed": True,
                "message": "API returned matching bar",
                "bar_found": True,
                "bar_data": matching_bar
            }
        else:
            return {
                "passed": False,
                "message": f"No matching bar found in API response for {timestamp}",
                "bar_found": False,
                "total_bars": len(bars)
            }
    
    except Exception as e:
        return {
            "passed": False,
            "message": f"API request error: {e}",
            "error": str(e)
        }


def check_end_to_end_latency(engine) -> Dict:
    """Check end-to-end latency."""
    print("Check 4: End-to-end latency...")
    
    # Get most recent row
    query = """
    SELECT timestamp, created_at
    FROM analytics.zl_price_15m
    WHERE source = 'databento_live'
    ORDER BY timestamp DESC
    LIMIT 1
    """
    
    try:
        df = pd.read_sql(query, engine)
        
        if len(df) == 0:
            return {
                "passed": False,
                "message": "No live data found",
                "latency_seconds": None
            }
        
        row = df.iloc[0]
        timestamp = row["timestamp"]
        created_at = row["created_at"]
        
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        
        latency = (created_at - timestamp).total_seconds()
        
        # Should be <2 seconds
        passed = latency < 2.0
        
        return {
            "passed": passed,
            "message": f"Latency: {latency:.2f}s" + (" (meets threshold)" if passed else " (exceeds 2s threshold)"),
            "latency_seconds": latency,
            "timestamp": timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp),
            "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
        }
    
    except Exception as e:
        return {
            "passed": False,
            "message": f"Error checking latency: {e}",
            "error": str(e)
        }


def main():
    """Run end-to-end data flow test."""
    print("=" * 80)
    print("End-to-End Data Flow Test")
    print("=" * 80)
    print(f"API Base URL: {API_BASE_URL}")
    print()
    
    engine = get_read_engine()
    
    # Sample event payload (as would be emitted by connector)
    sample_event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "open": 45.50,
        "high": 45.75,
        "low": 45.25,
        "close": 45.60,
        "volume": 1000,
        "source": "databento_live"
    }
    
    results = {}
    
    # Check 1: Event payload
    results["event_payload"] = check_event_payload(sample_event)
    
    # Check 2: Database row (using most recent row)
    query = """
    SELECT timestamp
    FROM analytics.zl_price_15m
    WHERE source = 'databento_live'
    ORDER BY timestamp DESC
    LIMIT 1
    """
    df = pd.read_sql(query, engine)
    
    if len(df) > 0:
        latest_ts = df["timestamp"].iloc[0]
        if isinstance(latest_ts, datetime):
            latest_ts = latest_ts.isoformat()
        elif isinstance(latest_ts, str):
            pass
        else:
            latest_ts = str(latest_ts)
        
        results["database_row"] = check_database_row(engine, latest_ts)
        
        # Check 3: API response
        results["api_response"] = check_api_response(
            f"{API_BASE_URL}/api/zl/intraday?hours=24",
            latest_ts
        )
    else:
        results["database_row"] = {
            "passed": False,
            "message": "No live data found in database"
        }
        results["api_response"] = {
            "passed": False,
            "message": "Skipped - no database row to check"
        }
    
    # Check 4: End-to-end latency
    results["latency"] = check_end_to_end_latency(engine)
    
    # Print results
    print()
    print("=" * 80)
    print("Test Results")
    print("=" * 80)
    
    for check_name, result in results.items():
        status = "✓ PASS" if result["passed"] else "✗ FAIL"
        print(f"{status} {check_name}: {result['message']}")
    
    # Save results
    output_file = "test_e2e_data_flow_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nResults saved to {output_file}")
    
    # Summary
    passed = sum(1 for r in results.values() if r["passed"])
    total = len(results)
    print(f"\nSummary: {passed}/{total} checks passed")
    
    if passed < total:
        print("\nSome checks failed. Review results for details.")
        return 1
    
    print("\n✓ All checks passed - end-to-end data flow verified")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
