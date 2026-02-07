#!/usr/bin/env python3
"""Quick EPU check against TradingView data."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

ECON_SERIES_CTE = """
    WITH econ AS (
        SELECT series_id, event_date, value FROM econ.rates_1d
        UNION ALL
        SELECT series_id, event_date, value FROM econ.inflation_1d
        UNION ALL
        SELECT series_id, event_date, value FROM econ.labor_1d
        UNION ALL
        SELECT series_id, event_date, value FROM econ.activity_1d
        UNION ALL
        SELECT series_id, event_date, value FROM econ.vol_indices_1d
        UNION ALL
        SELECT series_id, event_date, value FROM econ.commodities_1d
        UNION ALL
        SELECT pair as series_id, event_date, rate as value FROM mkt.fx_1d WHERE source = 'FRED'
        UNION ALL
        SELECT series_id, event_date, value FROM econ.money_1d
    )
"""

cur.execute(
    ECON_SERIES_CTE
    + """
    SELECT event_date, value
    FROM econ
    WHERE series_id = 'USEPUINDXD'
    ORDER BY event_date DESC
    LIMIT 1
"""
)
row = cur.fetchone()

if row:
    print(f'Latest EPU in our DB: {float(row[1]):.2f} on {row[0]}')
    print(f'TradingView shows: 426.99')
    print()
    
    # Get 2024-2026 context
    cur.execute(
        ECON_SERIES_CTE
        + """
        SELECT 
            DATE_TRUNC('month', event_date)::date as month,
            AVG(value) as avg_epu,
            MAX(value) as max_epu,
            MIN(value) as min_epu
        FROM econ
        WHERE series_id = 'USEPUINDXD'
        AND event_date >= '2024-01-01'
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    """
    )
    print('EPU by Month (2024-2026):')
    print(f'{"Month":12} | {"Avg":>7} | {"Max":>7} | {"Min":>7}')
    print('-' * 45)
    for r in cur.fetchall():
        print(f'{r[0]} | {float(r[1]):7.2f} | {float(r[2]):7.2f} | {float(r[3]):7.2f}')
    
    # COVID peak for comparison
    cur.execute(
        ECON_SERIES_CTE
        + """
        SELECT MAX(value) as covid_peak
        FROM econ
        WHERE series_id = 'USEPUINDXD'
        AND event_date BETWEEN '2020-03-01' AND '2020-05-01'
    """
    )
    covid = cur.fetchone()
    if covid:
        print(f'\nCOVID Peak (March-May 2020): {float(covid[0]):.2f}')
        print(f'Current (Jan 2026): ~427')
        print('\n🔥 IF EPU > 400: We are approaching COVID-level policy chaos')
        
else:
    print('No EPU data found')

cur.close()
conn.close()
