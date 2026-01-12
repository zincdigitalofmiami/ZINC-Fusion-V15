#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Garbage Cleanup Maintenance Job
=================================================
Runs daily/weekly to archive and purge low-quality articles.

Schedule via local crontab or Inngest:
    Daily:  0 2 * * * /path/to/.venv/bin/python scripts/maintenance/garbage_cleanup.py
    Weekly: 0 3 * * 0 /path/to/.venv/bin/python scripts/maintenance/garbage_cleanup.py --purge

Created: January 8, 2026
Author: Claude (AI Architect) for Kirk @ ZINC Digital
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Canonical Big 11 + garbage bucket
CANONICAL_BUCKETS = {
    "0",  # Garbage - not ZL relevant
    "crush", "china", "fx", "fed", "tariff",
    "energy", "biofuel", "palm", "volatility",
    "substitutes", "trump_effect"
}

BUCKET_MAPPING = {
    "Logistics/Chokepoints": "energy",
    "farm-bill": "tariff",
    "trade": "tariff",
    "ethanol": "biofuel",
    "Tariff Updates": "tariff",
    "Biofuel Mandates": "biofuel",
    "Fertilizer/Energy": "energy",
    "ESG/Deforestation": "palm",
    "Political Changes": "trump_effect",
    "China Relations": "china",
    "Animal Disease": "crush",
    "Labor Actions": "crush",
    "US Regulatory Filings": "tariff",
    "news": "0",
    "general": "0",
}

GARBAGE_IMPACT_THRESHOLD = 0.2
ARCHIVE_RETENTION_DAYS = 7


def get_connection():
    env_path = PROJECT_ROOT / ".env"
    database_url = None
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    database_url = line.split("=", 1)[1].strip().strip('"')
                    break
    if not database_url:
        database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found")
    return psycopg2.connect(database_url)


def ensure_archive_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raw.news_articles_archive (
                id SERIAL PRIMARY KEY, original_id INTEGER, headline TEXT, content TEXT,
                source VARCHAR(255), published_at TIMESTAMP, bucket_name VARCHAR(100),
                sentiment_score NUMERIC, archived_at TIMESTAMP DEFAULT NOW(), archive_reason VARCHAR(100)
            );
            CREATE INDEX IF NOT EXISTS idx_archive_date ON raw.news_articles_archive(archived_at);
            CREATE INDEX IF NOT EXISTS idx_archive_original_id ON raw.news_articles_archive(original_id);
        """)
        conn.commit()


def consolidate_buckets(conn) -> int:
    updated = 0
    with conn.cursor() as cur:
        for polluted, canonical in BUCKET_MAPPING.items():
            cur.execute("""
                UPDATE silver.news_scored_1d SET canonical_bucket = %s
                WHERE raw_bucket = %s AND (canonical_bucket IS NULL OR canonical_bucket != %s)
            """, (canonical, polluted, canonical))
            updated += cur.rowcount
        conn.commit()
    if updated > 0:
        logger.info(f"Consolidated {updated} articles from polluted buckets")
    return updated


def archive_garbage(conn) -> int:
    ensure_archive_table(conn)
    with conn.cursor() as cur:
        # Use efficient INSERT...SELECT
        cur.execute("""
            INSERT INTO raw.news_articles_archive 
            (original_id, headline, content, source, published_at, bucket_name, sentiment_score, archive_reason)
            SELECT r.id, r.headline, LEFT(r.content, 1000), r.source, r.published_at, 
                   s.canonical_bucket, s.zl_impact_score,
                   CASE WHEN s.canonical_bucket = '0' THEN 'not_zl_relevant'
                        WHEN s.is_zl_relevant = FALSE THEN 'failed_relevance_gate'
                        WHEN ABS(COALESCE(s.zl_impact_score, 0)) < %s THEN 'low_impact'
                        ELSE 'other' END
            FROM raw.news_articles_1d r
            JOIN silver.news_scored_1d s ON r.id = s.raw_id
            WHERE s.canonical_bucket = '0' OR s.is_zl_relevant = FALSE 
               OR ABS(COALESCE(s.zl_impact_score, 0)) < %s
            ON CONFLICT DO NOTHING
        """, (GARBAGE_IMPACT_THRESHOLD, GARBAGE_IMPACT_THRESHOLD))
        archived = cur.rowcount
        
        if archived > 0:
            # Delete from silver and raw
            cur.execute("""
                DELETE FROM silver.news_scored_1d
                WHERE canonical_bucket = '0' OR is_zl_relevant = FALSE 
                   OR ABS(COALESCE(zl_impact_score, 0)) < %s
            """, (GARBAGE_IMPACT_THRESHOLD,))
            cur.execute("""
                DELETE FROM raw.news_articles_1d r
                WHERE EXISTS (SELECT 1 FROM raw.news_articles_archive a 
                              WHERE a.original_id = r.id AND a.archived_at > NOW() - INTERVAL '1 minute')
            """)
        conn.commit()
        logger.info(f"Archived and removed {archived} garbage articles")
        return archived


def purge_old_archives(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM raw.news_articles_archive WHERE archived_at < NOW() - INTERVAL '%s days'", 
                    (ARCHIVE_RETENTION_DAYS,))
        purged = cur.rowcount
        conn.commit()
    if purged > 0:
        logger.info(f"Purged {purged} archives older than {ARCHIVE_RETENTION_DAYS} days")
    return purged


def get_stats(conn) -> dict:
    stats = {}
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM raw.news_articles_1d")
        stats["raw_articles"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM silver.news_scored_1d")
        stats["silver_articles"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='raw' AND table_name='news_articles_archive'")
        if cur.fetchone()[0] > 0:
            cur.execute("SELECT COUNT(*) FROM raw.news_articles_archive")
            stats["archived_articles"] = cur.fetchone()[0]
        else:
            stats["archived_articles"] = 0
        cur.execute("SELECT canonical_bucket, COUNT(*) FROM silver.news_scored_1d GROUP BY canonical_bucket ORDER BY COUNT(*) DESC")
        stats["buckets"] = {row[0]: row[1] for row in cur.fetchall()}
    return stats


def run_cleanup(do_purge: bool = False, dry_run: bool = False):
    logger.info("=" * 60)
    logger.info("ZINC-FUSION Garbage Cleanup")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info(f"Purge: {do_purge} | Dry run: {dry_run}")
    logger.info("=" * 60)
    
    conn = get_connection()
    try:
        before = get_stats(conn)
        logger.info(f"Before: {before['raw_articles']} raw, {before['silver_articles']} silver")
        
        if dry_run:
            logger.info("[DRY RUN - No changes made]")
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM silver.news_scored_1d
                    WHERE canonical_bucket = '0' OR is_zl_relevant = FALSE 
                       OR ABS(COALESCE(zl_impact_score, 0)) < %s
                """, (GARBAGE_IMPACT_THRESHOLD,))
                logger.info(f"Would archive: {cur.fetchone()[0]} garbage articles")
            return
        
        consolidated = consolidate_buckets(conn)
        archived = archive_garbage(conn)
        purged = purge_old_archives(conn) if do_purge else 0
        
        after = get_stats(conn)
        logger.info("\n" + "=" * 60)
        logger.info("CLEANUP SUMMARY")
        logger.info(f"Consolidated: {consolidated} | Archived: {archived} | Purged: {purged}")
        logger.info(f"After: {after['raw_articles']} raw, {after['silver_articles']} silver, {after['archived_articles']} archived")
        if after.get("buckets"):
            logger.info("Bucket Distribution:")
            for bucket, count in after["buckets"].items():
                logger.info(f"  {bucket or 'NULL'}: {count}")
        logger.info("=" * 60)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="ZINC-FUSION Garbage Cleanup")
    parser.add_argument("--purge", action="store_true", help="Also purge old archives")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    args = parser.parse_args()
    run_cleanup(do_purge=args.purge, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
