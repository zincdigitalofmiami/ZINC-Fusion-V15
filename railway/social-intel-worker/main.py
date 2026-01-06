#!/usr/bin/env python3
"""
Entry point for Railway cron job.
Runs the social intelligence scraper.

Usage:
    python main.py                    # All tiers
    python main.py --tier high        # High-alpha only (Trump, USTR, China)
    python main.py --tier regulatory  # Government/exchanges
    python main.py --tier discovery   # Industry/associations
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from scripts.scrape_social_intel import main

if __name__ == "__main__":
    sys.exit(main())
