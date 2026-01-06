#!/usr/bin/env python3
"""
Entry point for Railway cron job.
Runs the data ingestion worker based on schedule.

Schedules:
- Daily (8 AM UTC): FRED, EPA RIN
- Weekly (Wednesday 2 PM UTC): CFTC COT, USDA Export Sales
- Monthly (13th 10 AM UTC): USDA WASDE
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent))

from scripts.ingest_all_sources import main as run_ingestion


def determine_mode() -> str:
    """Determine which ingestion mode to run based on schedule."""
    # Check for explicit mode from environment
    mode = os.getenv("INGEST_MODE")
    if mode:
        return mode

    # Auto-detect based on day/time
    now = datetime.utcnow()

    # Monthly: Run on 13th (day after WASDE release on 12th)
    if now.day == 13:
        return "monthly"

    # Weekly: Run on Wednesday (CFTC releases Tuesday, Export Sales Thursday)
    if now.weekday() == 2:  # Wednesday
        return "weekly"

    # Default: Daily
    return "daily"


if __name__ == "__main__":
    # If no arguments provided, auto-detect mode
    if len(sys.argv) == 1:
        mode = determine_mode()
        sys.argv.extend(["--mode", mode])
        print(f"Auto-detected mode: {mode}")

    sys.exit(run_ingestion())
