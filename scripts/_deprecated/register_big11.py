#!/usr/bin/env python3
"""Register Core + Big 11 specialists in model registry."""
import os
import psycopg2
from datetime import datetime, timezone

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

# Big 11 specialists with their descriptions
BIG_11 = {
    'crush': 'Crush spread dynamics: ZL/ZS/ZM relationships, CFTC positioning',
    'china': 'China demand: copper proxy, CNY, China-related news sentiment',
    'fx': 'Currency effects: DXY, BRL, key trading partner FX',
    'fed': 'Monetary policy: rates, yield curve, Fed communications',
    'tariff': 'Trade policy: EPU indices, tariff news, legislation',
    'energy': 'Energy complex: crude, heating oil, biodiesel feedstock',
    'biofuel': 'Biofuel policy: EPA RINs, RVO mandates, biodiesel blend',
    'palm': 'Palm oil: FCPO futures, Indonesia/Malaysia policy, substitution',
    'volatility': 'Volatility regime: VIX, OVIX, term structure',
    'substitutes': 'Substitute oils: sunflower, rapeseed, canola pricing',
    'trump_effect': 'Trump policy: EPU, executive actions, trade threats'
}

HORIZONS = [5, 21, 63, 126]
now = datetime.now(timezone.utc)

# Insert missing Big 11 specialists
for specialist, description in BIG_11.items():
    model_name = f'{specialist}_specialist'
    for h in HORIZONS:
        model_id = f'{specialist}_specialist_h{h}_v1'
        cur.execute("SELECT 1 FROM model.model_registry WHERE model_id = %s", (model_id,))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO model.model_registry 
                (model_id, model_name, model_type, horizon, version, trained_at, status, notes, created_at, updated_at)
                VALUES (%s, %s, 'specialist', %s, 1, %s, 'pending', %s, %s, %s)
            """, (model_id, model_name, h, now, description, now, now))
            print(f'Added: {model_id}')

conn.commit()

# Show final state
cur.execute("""
    SELECT model_name, model_type, COUNT(*) as horizons
    FROM model.model_registry 
    GROUP BY model_name, model_type
    ORDER BY model_type, model_name
""")
print('\nFinal model registry:')
for row in cur.fetchall():
    print(f'  {row[1]:12} | {row[0]:25} | {row[2]} horizons')

cur.execute('SELECT COUNT(*) FROM model.model_registry')
print(f'\nTotal: {cur.fetchone()[0]} models')
conn.close()

