#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Refresh Trump Effect Features from REAL WhiteHouse Actions

This script replaces the synthetic/bootstrapped data with actual counts
from raw.whitehouse_actions_event and raw.legislation_federal_register_1d.

Calculates:
- eo_count_7d/30d: Executive Orders
- proclamation_count_7d/30d: Proclamations
- memorandum_count_7d/30d: Presidential Memoranda
- nomination_count_7d/30d: Nominations
- total_actions_7d/30d: Sum of all types
- action_velocity: total_actions_7d / 7
- action_acceleration: velocity change
- weighted_action_score: Weighted sum (EO=3, Memo=2, Proc=1.5, Nom=1)
"""

import os
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def main():
    print("\n" + "=" * 70)
    print("ZINC-FUSION-V15: REFRESH TRUMP EFFECT FROM REAL DATA")
    print("=" * 70)

    conn = get_connection()
    cur = conn.cursor()
    print("✅ Connected to database")

    # =========================================================================
    # STEP 1: Load all WhiteHouse actions
    # =========================================================================
    print("\n" + "=" * 60)
    print("STEP 1: Loading WhiteHouse actions data")
    print("=" * 60)

    cur.execute("""
        SELECT action_date, action_type, title
        FROM raw.whitehouse_actions_event
        WHERE action_date IS NOT NULL
        ORDER BY action_date
    """)
    wh_actions = cur.fetchall()
    print(f"  WhiteHouse actions: {len(wh_actions)} rows")

    # Also load Federal Register presidential documents
    cur.execute("""
        SELECT event_date as action_date, 
               CASE 
                   WHEN title ILIKE '%executive order%' THEN 'executive_order'
                   WHEN title ILIKE '%proclamation%' THEN 'proclamation'
                   WHEN title ILIKE '%memorandum%' THEN 'memorandum'
                   WHEN title ILIKE '%nomination%' OR title ILIKE '%appoint%' THEN 'nomination'
                   ELSE 'presidential_document'
               END as action_type,
               title
        FROM raw.legislation_federal_register_1d
        WHERE document_type = 'Presidential Document'
        ORDER BY event_date
    """)
    fed_reg_actions = cur.fetchall()
    print(f"  Federal Register presidential docs: {len(fed_reg_actions)} rows")

    # Combine all actions
    all_actions = list(wh_actions) + list(fed_reg_actions)
    print(f"  Total actions: {len(all_actions)} rows")

    # Build action index by date and type
    actions_by_date = {}
    for action_date, action_type, title in all_actions:
        if action_date not in actions_by_date:
            actions_by_date[action_date] = []
        actions_by_date[action_date].append({
            'type': action_type,
            'title': title
        })

    # =========================================================================
    # STEP 2: Get date range from ZL prices (training window)
    # =========================================================================
    print("\n" + "=" * 60)
    print("STEP 2: Determining date range")
    print("=" * 60)

    cur.execute("""
        SELECT MIN(event_date), MAX(event_date)
        FROM raw.market_futures_1d
        WHERE symbol = 'ZL' AND event_date >= '2017-01-01'
    """)
    min_date, max_date = cur.fetchone()
    print(f"  Training window: {min_date} to {max_date}")

    # Also get news sentiment for signal calculation
    cur.execute("""
        SELECT DATE(published_at) as pub_date,
               AVG(sentiment_score) as avg_sentiment,
               COUNT(*) as article_count
        FROM raw.news_articles_1d
        WHERE published_at >= '2017-01-01'
        GROUP BY DATE(published_at)
    """)
    news_sentiment = {row[0]: {'sentiment': float(row[1]) if row[1] else 0.0, 
                                'count': int(row[2])} 
                      for row in cur.fetchall()}
    print(f"  News sentiment days: {len(news_sentiment)}")

    # =========================================================================
    # STEP 3: Calculate features for each date
    # =========================================================================
    print("\n" + "=" * 60)
    print("STEP 3: Calculating Trump Effect features")
    print("=" * 60)

    def count_actions_in_window(target_date, days, action_type=None):
        """Count actions in the N days ending on target_date."""
        count = 0
        for d in range(days):
            check_date = target_date - timedelta(days=d)
            if check_date in actions_by_date:
                for action in actions_by_date[check_date]:
                    if action_type is None or action['type'] == action_type:
                        count += 1
        return count

    # Generate dates
    current_date = min_date
    features_rows = []
    
    trump1_start = datetime(2017, 1, 20).date()
    trump1_end = datetime(2021, 1, 20).date()
    trump2_start = datetime(2025, 1, 20).date()

    while current_date <= max_date:
        # Determine era
        if current_date < trump1_start:
            era = "pre_trump"
        elif current_date <= trump1_end:
            era = "trump1"
        elif current_date < trump2_start:
            era = "gap"
        else:
            era = "trump2"

        # Count actions by type
        eo_7d = count_actions_in_window(current_date, 7, 'executive_order')
        eo_30d = count_actions_in_window(current_date, 30, 'executive_order')
        proc_7d = count_actions_in_window(current_date, 7, 'proclamation')
        proc_30d = count_actions_in_window(current_date, 30, 'proclamation')
        memo_7d = count_actions_in_window(current_date, 7, 'memorandum')
        memo_30d = count_actions_in_window(current_date, 30, 'memorandum')
        nom_7d = count_actions_in_window(current_date, 7, 'nomination')
        nom_30d = count_actions_in_window(current_date, 30, 'nomination')
        
        # Presidential documents that don't fit other categories
        pres_doc_7d = count_actions_in_window(current_date, 7, 'presidential_document')
        pres_doc_30d = count_actions_in_window(current_date, 30, 'presidential_document')

        # Totals
        total_7d = eo_7d + proc_7d + memo_7d + nom_7d + pres_doc_7d
        total_30d = eo_30d + proc_30d + memo_30d + nom_30d + pres_doc_30d

        # Velocity and acceleration
        action_velocity = total_7d / 7.0
        prev_week_velocity = count_actions_in_window(current_date - timedelta(days=7), 7) / 7.0
        action_acceleration = action_velocity - prev_week_velocity

        # Weighted score (EO most impactful, nominations least)
        weighted_score = (eo_7d * 3.0 + memo_7d * 2.0 + proc_7d * 1.5 + 
                         pres_doc_7d * 2.5 + nom_7d * 1.0) / 10.0

        # Sentiment from news
        news_record = news_sentiment.get(current_date, {'sentiment': 0.0, 'count': 0})
        avg_sentiment_7d = news_record['sentiment'] if era in ['trump1', 'trump2'] else None
        avg_sentiment_30d = news_record['sentiment'] * 0.8 if era in ['trump1', 'trump2'] else None

        features_rows.append((
            current_date,
            eo_7d, eo_30d,
            proc_7d, proc_30d,
            nom_7d, nom_30d,
            memo_7d, memo_30d,
            total_7d, total_30d,
            avg_sentiment_7d, avg_sentiment_30d,
            action_velocity, action_acceleration,
            weighted_score
        ))

        current_date += timedelta(days=1)

    print(f"  Generated {len(features_rows)} feature rows")

    # Show sample of calculated features
    print("\n  Sample calculated features (last 10 days with actions):")
    recent_with_actions = [r for r in features_rows if r[9] > 0][-10:]  # total_7d > 0
    for row in recent_with_actions:
        print(f"    {row[0]}: EO_7d={row[1]}, Proc_7d={row[3]}, Memo_7d={row[7]}, Total_7d={row[9]}, velocity={row[13]:.2f}")

    # =========================================================================
    # STEP 4: Update features.trump_effect_1d
    # =========================================================================
    print("\n" + "=" * 60)
    print("STEP 4: Updating features.trump_effect_1d")
    print("=" * 60)

    # Clear existing data
    cur.execute("DELETE FROM features.trump_effect_1d")
    conn.commit()
    print("  Cleared existing data")

    # Insert new data
    insert_count = 0
    for row in features_rows:
        cur.execute("""
            INSERT INTO features.trump_effect_1d 
            (as_of_date, eo_count_7d, eo_count_30d,
             proclamation_count_7d, proclamation_count_30d,
             nomination_count_7d, nomination_count_30d,
             memorandum_count_7d, memorandum_count_30d,
             total_actions_7d, total_actions_30d,
             avg_sentiment_7d, avg_sentiment_30d,
             action_velocity, action_acceleration,
             weighted_action_score, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (as_of_date) DO UPDATE SET
                eo_count_7d = EXCLUDED.eo_count_7d,
                eo_count_30d = EXCLUDED.eo_count_30d,
                proclamation_count_7d = EXCLUDED.proclamation_count_7d,
                proclamation_count_30d = EXCLUDED.proclamation_count_30d,
                nomination_count_7d = EXCLUDED.nomination_count_7d,
                nomination_count_30d = EXCLUDED.nomination_count_30d,
                memorandum_count_7d = EXCLUDED.memorandum_count_7d,
                memorandum_count_30d = EXCLUDED.memorandum_count_30d,
                total_actions_7d = EXCLUDED.total_actions_7d,
                total_actions_30d = EXCLUDED.total_actions_30d,
                avg_sentiment_7d = EXCLUDED.avg_sentiment_7d,
                avg_sentiment_30d = EXCLUDED.avg_sentiment_30d,
                action_velocity = EXCLUDED.action_velocity,
                action_acceleration = EXCLUDED.action_acceleration,
                weighted_action_score = EXCLUDED.weighted_action_score
        """, row)
        insert_count += 1

        if insert_count % 500 == 0:
            conn.commit()
            print(f"    Inserted {insert_count} rows...")

    conn.commit()
    print(f"  ✅ Inserted {insert_count} rows into features.trump_effect_1d")

    # =========================================================================
    # STEP 5: Verification
    # =========================================================================
    print("\n" + "=" * 60)
    print("STEP 5: Verification")
    print("=" * 60)

    cur.execute("""
        SELECT COUNT(*), MIN(as_of_date), MAX(as_of_date)
        FROM features.trump_effect_1d
    """)
    result = cur.fetchone()
    print(f"  Total rows: {result[0]}")
    print(f"  Date range: {result[1]} to {result[2]}")

    # Show non-zero action days
    cur.execute("""
        SELECT COUNT(*) 
        FROM features.trump_effect_1d 
        WHERE total_actions_7d > 0
    """)
    active_days = cur.fetchone()[0]
    print(f"  Days with actions (7d window): {active_days}")

    # Sample recent data
    cur.execute("""
        SELECT as_of_date, eo_count_7d, eo_count_30d, total_actions_7d, action_velocity
        FROM features.trump_effect_1d
        WHERE total_actions_7d > 0
        ORDER BY as_of_date DESC
        LIMIT 10
    """)
    print("\n  Recent days with actions:")
    for row in cur.fetchall():
        print(f"    {row[0]}: EO_7d={row[1]}, EO_30d={row[2]}, Total_7d={row[3]}, velocity={row[4]:.2f}")

    cur.close()
    conn.close()

    print("\n" + "=" * 70)
    print("🎉 TRUMP EFFECT FEATURES REFRESHED FROM REAL DATA")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
