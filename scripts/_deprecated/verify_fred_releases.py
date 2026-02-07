#!/usr/bin/env python3
"""Verify FRED releases."""
import os, psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

cur.execute("""
    SELECT
        specialist_tags[1] as bucket_name,
        COUNT(*) as events,
        MIN(event_date) as earliest,
        MAX(event_date) as latest
    FROM alt.news_1d
    WHERE source = 'fred_release_calendar'
    GROUP BY specialist_tags[1]
    ORDER BY specialist_tags[1]
""")
print('FRED Release Events by Specialist:')
print(f'{"Specialist":15} | {"Events":>6} | {"Earliest":12} | {"Latest":12}')
print('-' * 60)
for row in cur.fetchall():
    print(f'{row[0]:15} | {row[1]:6} | {str(row[2]):12} | {str(row[3]):12}')

cur.execute("""
    SELECT headline, event_date, COUNT(*) as cnt
    FROM alt.news_1d
    WHERE source = 'fred_release_calendar'
    GROUP BY headline, event_date
    HAVING COUNT(*) > 1
""")
dups = cur.fetchall()
print(f'\n✅ Duplicate check: {len(dups)} duplicates')

cur.execute("""
    SELECT COUNT(*) FROM alt.news_1d
    WHERE source = 'fred_release_calendar'
""")
print(f'✅ Total FRED release events: {cur.fetchone()[0]}')

cur.close()
conn.close()
