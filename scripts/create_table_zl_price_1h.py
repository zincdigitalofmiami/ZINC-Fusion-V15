#!/usr/bin/env python3
"""Create analytics.zl_price_1h table"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

# Check if exists
cur.execute("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'analytics' AND table_name = 'zl_price_1h'
    )
""")
exists = cur.fetchone()[0]

if exists:
    print("✅ analytics.zl_price_1h already exists")
else:
    print("Creating analytics.zl_price_1h...")
    cur.execute("""
        CREATE TABLE analytics.zl_price_1h (
            timestamp TIMESTAMPTZ PRIMARY KEY,
            open NUMERIC(10,4) NOT NULL,
            high NUMERIC(10,4) NOT NULL,
            low NUMERIC(10,4) NOT NULL,
            close NUMERIC(10,4) NOT NULL,
            volume BIGINT NOT NULL DEFAULT 0,
            source VARCHAR(50) NOT NULL DEFAULT 'yahoo',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX idx_zl_price_1h_ts ON analytics.zl_price_1h(timestamp DESC)")
    conn.commit()
    print("✅ Table created")

# Verify
cur.execute("SELECT COUNT(*) FROM analytics.zl_price_1h")
count = cur.fetchone()[0]
print(f"Current rows: {count}")

conn.close()
