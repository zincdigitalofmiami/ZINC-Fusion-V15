#!/usr/bin/env python3
import psycopg2
import os

DATABASE_URL = "postgres://d687a7ec267e124a21607a1e5dd9a89d60c9a122d219e499e32f3eee42a858c0:sk_NLg8ZV3VJ61FPM0F_QHMe@db.prisma.io:5432/postgres?sslmode=require"
conn = psycopg2.connect(DATABASE_URL)

# Get one row to see the features structure
query = "SELECT features FROM training.core_features LIMIT 1;"
cursor = conn.cursor()
cursor.execute(query)
row = cursor.fetchone()

if row:
    features = row[0]
    print("Feature columns in core_features JSON:")
    print("=" * 60)
    for key in sorted(features.keys())[:30]:  # First 30 keys
        print(f"  {key}")
    print(f"\n  ... ({len(features)} total features)")
    
    # Check for target-like columns
    print("\n" + "=" * 60)
    print("Looking for target columns (ZL, close, target, price):")
    print("=" * 60)
    matching = []
    for key in features.keys():
        if any(x in key.lower() for x in ['zl', 'close', 'target', 'price']):
            matching.append((key, features[key]))
    
    if matching:
        for key, val in matching[:10]:
            print(f"  {key}: {val}")
    else:
        print("  NO MATCHING COLUMNS FOUND")

conn.close()
