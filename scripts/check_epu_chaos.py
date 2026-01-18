#!/usr/bin/env python3
"""Check EPU uncertainty data to see the chaos regime."""
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

# Check what EPU series we have
cur.execute(
    ECON_SERIES_CTE
    + """
    SELECT series_id, COUNT(*), MIN(event_date), MAX(event_date)
    FROM econ
    WHERE series_id LIKE '%EPU%' OR series_id LIKE '%UNCERTAINTY%' OR series_id = 'VIXCLS'
    GROUP BY series_id
    ORDER BY series_id
"""
)
print('Available Uncertainty/EPU Series:')
for row in cur.fetchall():
    print(f'  {row[0]:20} | {row[1]:5} obs | {row[2]} to {row[3]}')

print('\n' + '='*80 + '\n')

# Get recent EPU values
cur.execute(
    ECON_SERIES_CTE
    + """
    SELECT event_date, value
    FROM econ
    WHERE series_id = 'USEPUINDXD' 
    AND event_date >= '2024-01-01'
    ORDER BY event_date DESC
    LIMIT 60
"""
)
rows = cur.fetchall()

if rows:
    print('US Economic Policy Uncertainty Index (Daily) - Last 60 trading days:')
    print(f'{"Date":12} | {"EPU":>7} | {"Bar Chart":50}')
    print('-' * 80)
    
    # Get max for scaling
    max_val = max(float(r[1]) for r in rows)
    
    for row in rows[:30]:  # Show last 30
        date = row[0]
        val = float(row[1])
        bar_len = int((val / max_val) * 40)
        bar = '█' * bar_len
        print(f'{date} | {val:7.2f} | {bar}')
    
    print()
    latest = float(rows[0][1])
    print(f'Latest EPU (most recent): {latest:.2f}')
    
    # Get historical context
    cur.execute(
        ECON_SERIES_CTE
        + """
        SELECT 
            AVG(value) as avg,
            STDDEV(value) as stddev,
            MAX(value) as max,
            MIN(value) as min
        FROM econ
        WHERE series_id = 'USEPUINDXD'
    """
    )
    stats = cur.fetchone()
    if stats:
        avg = float(stats[0])
        stddev = float(stats[1])
        max_all_time = float(stats[2])
        min_val = float(stats[3])
        z_score = (latest - avg) / stddev
        
        print(f'\nHistorical Context:')
        print(f'  All-Time Avg: {avg:.2f}')
        print(f'  All-Time Max: {max_all_time:.2f}')
        print(f'  All-Time Min: {min_val:.2f}')
        print(f'  Std Dev: {stddev:.2f}')
        print(f'  Current Z-Score: {z_score:.2f}σ')
        print()
        
        if latest > avg + 2*stddev:
            print('🔥 EXTREME UNCERTAINTY REGIME (>2σ above historical mean)')
            print('   This is a tail-risk environment. News sentiment is CRITICAL.')
        elif latest > avg + stddev:
            print('⚠️  ELEVATED UNCERTAINTY REGIME (>1σ above historical mean)')
            print('   Heightened volatility. News-driven moves expected.')
        elif latest > avg:
            print('📊 ABOVE-AVERAGE UNCERTAINTY')
        else:
            print('✅ NORMAL/LOW UNCERTAINTY REGIME')
            
        # Check VIX too
        cur.execute(
            ECON_SERIES_CTE
            + """
            SELECT event_date, value
            FROM econ
            WHERE series_id = 'VIXCLS'
            ORDER BY event_date DESC
            LIMIT 1
        """
        )
        vix = cur.fetchone()
        if vix:
            vix_val = float(vix[1])
            print(f'\nVIX (Fear Gauge): {vix_val:.2f}')
            if vix_val > 30:
                print('  🔥 FEAR MODE (VIX > 30)')
            elif vix_val > 20:
                print('  ⚠️  ELEVATED FEAR (VIX > 20)')
            else:
                print('  ✅ COMPLACENT (VIX < 20)')
                
else:
    print('❌ No USEPUINDXD data found - need to ingest!')

cur.close()
conn.close()
