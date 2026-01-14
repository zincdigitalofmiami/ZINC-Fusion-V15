#!/usr/bin/env python3
"""Audit specialist tag disasters"""
import os
import psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
conn.autocommit = True
cur = conn.cursor()

print('='*70)
print('DATA TAGGING DISASTER AUDIT')
print('='*70)

# 1. Yahoo equity - DJT tagged as "general"?!
print('\n=== YAHOO EQUITY TAGGING ===')
cur.execute('''
    SELECT symbol, specialist_tags, COUNT(*) 
    FROM raw.yahoo_equity_1d 
    GROUP BY symbol, specialist_tags
    ORDER BY symbol
''')
for r in cur.fetchall():
    tag_issue = ' <-- WTF should be trump_effect!' if r[0] == 'DJT' and 'general' in str(r[1]) else ''
    print(f'  {r[0]}: {r[1]} ({r[2]} rows){tag_issue}')

# 2. AEI articles - what's in there?
print('\n=== AEI ARTICLES ===')
cur.execute('SELECT COUNT(*) FROM raw.aei_articles_event')
total = cur.fetchone()[0]
print(f'Total: {total} rows')

cur.execute('SELECT title FROM raw.aei_articles_event ORDER BY published_at DESC LIMIT 15')
print('\nRecent articles:')
for r in cur.fetchall():
    title = r[0][:80] if r[0] else 'NULL'
    print(f'  - {title}')

# 3. Where is Trump-related content ACTUALLY stored?
print('\n=== TRUMP CONTENT LOCATIONS ===')

# AEI
cur.execute("SELECT COUNT(*) FROM raw.aei_articles_event WHERE title ILIKE '%trump%'")
print(f'aei_articles_event (Trump in title): {cur.fetchone()[0]}')

# News articles 1d
cur.execute("SELECT COUNT(*) FROM raw.news_articles_1d WHERE is_trump_related = true")
print(f'news_articles_1d (is_trump_related): {cur.fetchone()[0]}')

# News articles event
cur.execute("SELECT COUNT(*) FROM raw.news_articles_event")
print(f'news_articles_event (total): {cur.fetchone()[0]}')

# WhiteHouse
cur.execute("SELECT COUNT(*) FROM raw.whitehouse_actions_event")
print(f'whitehouse_actions_event: {cur.fetchone()[0]}')

# 4. Specialist tags usage across ALL tables
print('\n=== SPECIALIST_TAGS VALUES ACROSS DB ===')
cur.execute('''
    SELECT table_name 
    FROM information_schema.columns 
    WHERE table_schema = 'raw' AND column_name = 'specialist_tags'
''')
tables = [r[0] for r in cur.fetchall()]

for table in tables:
    cur.execute(f'''
        SELECT specialist_tags, COUNT(*) 
        FROM raw."{table}" 
        GROUP BY specialist_tags
        ORDER BY COUNT(*) DESC
    ''')
    results = cur.fetchall()
    if results:
        print(f'\n  {table}:')
        for tag, cnt in results[:5]:
            print(f'    {tag}: {cnt}')

# 5. What SHOULD have trump_effect tag?
print('\n=== MISSING TRUMP_EFFECT TAGS ===')
cur.execute("SELECT COUNT(*) FROM raw.yahoo_equity_1d WHERE symbol = 'DJT'")
djt_cnt = cur.fetchone()[0]
print(f'DJT rows that should be trump_effect: {djt_cnt}')

cur.execute("SELECT COUNT(*) FROM raw.aei_articles_event WHERE title ILIKE '%trump%' OR title ILIKE '%tariff%'")
aei_trump = cur.fetchone()[0]
print(f'AEI articles about Trump/tariffs: {aei_trump}')

# 6. Check if AEI has specialist_tags column
print('\n=== AEI ARTICLES STRUCTURE ===')
cur.execute('''
    SELECT column_name FROM information_schema.columns 
    WHERE table_schema = 'raw' AND table_name = 'aei_articles_event'
    ORDER BY ordinal_position
''')
cols = [r[0] for r in cur.fetchall()]
print(f'Columns: {cols}')

has_tags = 'specialist_tags' in cols
print(f'Has specialist_tags column: {has_tags}')

if has_tags:
    cur.execute('SELECT specialist_tags, COUNT(*) FROM raw.aei_articles_event GROUP BY specialist_tags')
    print('\nAEI specialist_tags:')
    for r in cur.fetchall():
        print(f'  {r[0]}: {r[1]}')

conn.close()
