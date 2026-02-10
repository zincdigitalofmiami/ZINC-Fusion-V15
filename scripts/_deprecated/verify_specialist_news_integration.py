#!/usr/bin/env python3
"""
Verify that ALL 11 specialists get news data from tables with specialist_tags.

Tests the universal news loader for each specialist bucket.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fusion.specialists.data_loaders import (
    load_specialist_data,
)
from datetime import date, timedelta
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

SPECIALISTS = [
    "crush",
    "china",
    "fx",
    "fed",
    "tariff",
    "energy",
    "biofuel",
    "palm",
    "volatility",
    "substitutes",
    "trump_effect",
]


def verify_news_integration():
    """Verify each specialist can load news data tagged for them."""

    print("\n" + "=" * 70)
    print("🔍 VERIFYING NEWS INTEGRATION FOR ALL 11 SPECIALISTS")
    print("=" * 70 + "\n")

    # Test period: last 90 days
    end_date = date.today()
    start_date = end_date - timedelta(days=90)

    results = {}

    for specialist in SPECIALISTS:
        print(f"\n📊 {specialist.upper()}")
        print("-" * 70)

        try:
            # Load full specialist data (includes news now)
            df = load_specialist_data(specialist, start_date, end_date)

            # Check for news columns
            news_cols = [c for c in df.columns if c.startswith("news_")]

            if news_cols:
                print(f"  ✅ News columns: {', '.join(news_cols)}")

                # Count news coverage
                if "news_article_count" in df.columns:
                    total_articles = df["news_article_count"].sum()
                    days_with_news = (df["news_article_count"] > 0).sum()
                    print(
                        f"  📰 Articles: {total_articles:.0f} articles across {days_with_news} days"
                    )

                if "news_avg_sentiment" in df.columns:
                    avg_sentiment = df["news_avg_sentiment"].mean()
                    if not pd.isna(avg_sentiment):
                        print(f"  😊 Avg sentiment: {avg_sentiment:.3f}")

                results[specialist] = {
                    "has_news": True,
                    "news_columns": len(news_cols),
                    "total_articles": total_articles
                    if "news_article_count" in df.columns
                    else 0,
                }
            else:
                print(f"  ⚠️  No news columns found")
                results[specialist] = {
                    "has_news": False,
                    "news_columns": 0,
                    "total_articles": 0,
                }

            print(f"  📏 Total features: {len(df.columns)} columns, {len(df)} rows")

        except Exception as e:
            print(f"  ❌ Error: {str(e)[:80]}")
            results[specialist] = {"has_news": False, "error": str(e)}

    # Summary
    print("\n" + "=" * 70)
    print("📈 SUMMARY")
    print("=" * 70)

    with_news = sum(1 for r in results.values() if r.get("has_news", False))
    total_articles = sum(r.get("total_articles", 0) for r in results.values())

    print(f"\n  Specialists with news: {with_news}/{len(SPECIALISTS)}")
    print(f"  Total articles across all specialists: {total_articles:.0f}")

    if with_news == len(SPECIALISTS):
        print("\n  ✅ ALL SPECIALISTS HAVE NEWS DATA!")
    else:
        missing = [k for k, v in results.items() if not v.get("has_news", False)]
        print(f"\n  ⚠️  Missing news: {', '.join(missing)}")

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    verify_news_integration()
