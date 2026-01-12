#!/usr/bin/env python3
"""
Audit Model Registry - Check what models exist
"""
import os
import sys
from pathlib import Path
import psycopg2
import pandas as pd
from dotenv import load_dotenv

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Connect to database
DATABASE_URL = os.getenv('DATABASE_URL')
conn = psycopg2.connect(DATABASE_URL)

print("=" * 80)
print("MODEL REGISTRY AUDIT")
print("=" * 80)

# Query model registry
query = """
SELECT 
    model_id,
    model_name,
    model_type,
    horizon,
    version,
    trained_at,
    status,
    is_champion,
    mase,
    rmse,
    mae,
    mape,
    best_model,
    models_trained,
    artifact_path
FROM model.model_registry
ORDER BY trained_at DESC;
"""

df = pd.read_sql(query, conn)

print(f"\nTotal Models: {len(df)}")
print(f"Champion Models: {df['is_champion'].sum()}")

if len(df) > 0:
    print(f"\nBreakdown by Type:")
    print(df['model_type'].value_counts())
    print(f"\nBreakdown by Status:")
    print(df['status'].value_counts())
    
    print("\n" + "=" * 80)
    print("DETAILED LISTING")
    print("=" * 80)
    for idx, row in df.iterrows():
        print(f"\n[{idx+1}] {row['model_id']} (v{row['version']})")
        print(f"    Type: {row['model_type']}")
        print(f"    Horizon: {row['horizon']}")
        print(f"    Trained: {row['trained_at']}")
        print(f"    Status: {row['status']} | Champion: {row['is_champion']}")
        print(f"    Best Model: {row['best_model']}")
        print(f"    Models Trained: {row['models_trained']}")
        if pd.notna(row['mase']) and row['rmse'] is not None and row['mae'] is not None:
            print(f"    MASE: {float(row['mase']):.4f} | RMSE: {float(row['rmse']):.4f} | MAE: {float(row['mae']):.4f}")
        else:
            print(f"    Metrics: NOT RECORDED")
        print(f"    Artifact: {row['artifact_path']}")
else:
    print("\nNO MODELS FOUND IN REGISTRY")

# Check OOF predictions
print("\n" + "=" * 80)
print("OOF PREDICTIONS CHECK")
print("=" * 80)
oof_query = """
SELECT specialist, horizon, COUNT(*) as predictions
FROM model.oof_predictions
GROUP BY specialist, horizon
ORDER BY specialist, horizon;
"""
oof_df = pd.read_sql(oof_query, conn)
if len(oof_df) > 0:
    print(oof_df.to_string(index=False))
else:
    print("NO OOF PREDICTIONS FOUND (table is empty)")

# Check training features
print("\n" + "=" * 80)
print("TRAINING FEATURES CHECK")
print("=" * 80)
feat_query = """
SELECT 
    (SELECT COUNT(*) FROM training.core_features) as core_features_rows,
    (SELECT COUNT(DISTINCT bucket) FROM training.specialist_features) as specialist_buckets,
    (SELECT COUNT(*) FROM training.specialist_features) as specialist_features_rows;
"""
feat_df = pd.read_sql(feat_query, conn)
print(f"Core Features: {feat_df['core_features_rows'][0]} rows")
print(f"Specialist Buckets: {feat_df['specialist_buckets'][0]} buckets")
print(f"Specialist Features: {feat_df['specialist_features_rows'][0]} rows")

conn.close()
print("\n" + "=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)
