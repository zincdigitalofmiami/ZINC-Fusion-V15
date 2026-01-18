#!/usr/bin/env python3
"""Audit all news sources for coverage and duplicate issues."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

# Check ALL sources
cur.execute("""
    SELECT 
        source,
        COUNT(*) as total_articles,
        COUNT(DISTINCT DATE(published_at)) as unique_dates,
        MIN(published_at) as earliest,
        MAX(published_at) as latest,
        EXTRACT(DAY FROM MAX(published_at) - MIN(published_at)) as days_span
    FROM raw.news_articles_event 
    WHERE published_at IS NOT NULL
    GROUP BY source
    ORDER BY total_articles DESC
""")

print('ALL News Sources in Database:')
print(f'{"Source":40} | {"Articles":>8} | {"Dates":>6} | {"Earliest":19} | {"Latest":19} | {"Days":>5}')
print('-' * 120)

total_articles = 0
for row in cur.fetchall():
    print(f'{row[0]:40} | {row[1]:8} | {row[2]:6} | {str(row[3])[:19]:19} | {str(row[4])[:19]:19} | {int(row[5]) if row[5] else 0:5}')
    total_articles += row[1]

print(f'\nTotal articles: {total_articles}')
print('\n' + '='*120)
print('DIAGNOSIS:')
print('  - If Days < 60: Limited historical coverage (source limitation)')
print('  - Duplicate flags on re-runs are EXPECTED (already in DB)')
print('  - Real problem: Are we getting ENOUGH historical data per source?')

cur.close()
conn.close()
