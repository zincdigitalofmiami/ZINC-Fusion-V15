#!/usr/bin/env python3
"""Check date distribution of scraped news articles."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

# Check date distribution for soybean oil articles
cur.execute("""
    SELECT 
        DATE_TRUNC('month', published_at) as month,
        COUNT(*) as count,
        MIN(published_at) as earliest,
        MAX(published_at) as latest
    FROM raw.news_articles_event 
    WHERE source = 'barchart_scrape_soybean_oil'
    GROUP BY month
    ORDER BY month DESC
""")
print('Soybean Oil Date Distribution:')
for row in cur.fetchall():
    print(f'  {row[0].strftime("%Y-%m")}: {row[1]:3d} articles | {row[2]} to {row[3]}')

print()

# Check all barchart scraped sources
cur.execute("""
    SELECT source, COUNT(*) as count, MIN(published_at), MAX(published_at)
    FROM raw.news_articles_event 
    WHERE source LIKE 'barchart_scrape%'
    GROUP BY source
    ORDER BY source
""")
print('All Barchart Scraped Sources:')
for row in cur.fetchall():
    print(f'  {row[0]:40} | {row[1]:4d} articles | {row[2]} to {row[3]}')

# Check how many unique dates we have vs how many total articles
print('\n')
cur.execute("""
    SELECT 
        source,
        COUNT(*) as total_articles,
        COUNT(DISTINCT DATE(published_at)) as unique_dates,
        ROUND(COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT DATE(published_at)), 0), 1) as articles_per_date
    FROM raw.news_articles_event 
    WHERE source LIKE 'barchart_scrape%'
    GROUP BY source
    ORDER BY source
""")
print('Articles per Unique Date (reveals if scraper is hitting same dates):')
for row in cur.fetchall():
    print(f'  {row[0]:40} | {row[1]:4d} total | {row[2]:3d} dates | {row[3]:.1f} avg/date')

cur.close()
conn.close()
