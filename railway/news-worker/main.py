#!/usr/bin/env python3
"""
Entry point for Railway cron job.
Runs the news ingestion pipeline.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from scripts.ingest_news_sources import main

if __name__ == "__main__":
    sys.exit(main())
