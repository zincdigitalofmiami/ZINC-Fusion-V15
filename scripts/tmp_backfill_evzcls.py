#!/usr/bin/env python3
import os, requests, psycopg2, hashlib
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
sid = "EVZCLS"
r = requests.get("https://api.stlouisfed.org/fred/series/observations",
    params={"series_id": sid, "api_key": os.environ["FRED_API_KEY"],
            "file_type": "json", "observation_start": "2000-01-01"}, timeout=30)
obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
print(f"Fetched {len(obs)} observations")
inserted = 0
for o in obs:
    h = hashlib.sha256((sid + "|" + o["date"] + "|" + o["value"]).encode()).hexdigest()
    cur.execute("INSERT INTO econ.vol_indices_1d (series_id, event_date, value, source, ingested_at, row_hash) VALUES (%s, %s, %s, %s, NOW(), %s) ON CONFLICT DO NOTHING",
        (sid, o["date"], float(o["value"]), "FRED", h))
    if cur.rowcount > 0: inserted += 1
conn.commit()
print(f"Inserted {inserted}")
conn.close()
