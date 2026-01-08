#!/usr/bin/env python3
"""
Import Claude Opus 4.5 scores into silver.news_scored_1d
"""

import json
import sys
import os
from pathlib import Path

import psycopg2

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import the scores
from scripts.claude_opus_scores_batch1 import CLAUDE_OPUS_SCORES

def get_connection():
    """Get database connection from .env"""
    env_path = PROJECT_ROOT / ".env"
    database_url = None
    
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    database_url = line.split("=", 1)[1].strip().strip('"')
                    break
    
    if not database_url:
        raise ValueError("DATABASE_URL not found")
    
    return psycopg2.connect(database_url)


def import_opus_scores():
    """Import Claude Opus scores into the database"""
    
    conn = get_connection()
    
    try:
        with conn.cursor() as cur:
            updated = 0
            
            for score in CLAUDE_OPUS_SCORES:
                raw_id = score["raw_id"]
                affected = set(score.get("affected_specialists", []))
                
                # Build the matched_categories JSON with full analysis
                matched_categories = {
                    "finbert": None,  # Will be merged with existing
                    "claude_opus": {
                        "score": score.get("zl_impact_score"),
                        "sentiment": score.get("sentiment"),
                        "confidence": score.get("confidence"),
                        "time_horizon": score.get("time_horizon"),
                        "reasoning": score.get("reasoning"),
                        "key_quote": score.get("key_quote"),
                    },
                    "ensemble": {
                        "score": score.get("zl_impact_score"),
                        "direction": score.get("sentiment"),
                        "confidence": score.get("confidence"),
                        "method": "finbert+claude_opus"
                    },
                    "factor_breakdown": score.get("factor_breakdown", {}),
                    "affected_specialists": list(affected)
                }
                
                # Get existing finbert data to preserve it
                cur.execute("""
                    SELECT matched_categories 
                    FROM silver.news_scored_1d 
                    WHERE raw_id = %s
                """, (raw_id,))
                
                existing = cur.fetchone()
                if existing and existing[0]:
                    try:
                        existing_data = existing[0] if isinstance(existing[0], dict) else json.loads(existing[0])
                        matched_categories["finbert"] = existing_data.get("finbert")
                        
                        # Recalculate ensemble with both scores
                        finbert_score = existing_data.get("finbert", {}).get("finbert_score", 0)
                        finbert_conf = existing_data.get("finbert", {}).get("finbert_confidence", 0.5)
                        claude_score = score.get("zl_impact_score", 0)
                        claude_conf = score.get("confidence", 0.5)
                        
                        # Weighted fusion: Opus 65%, FinBERT 35%
                        w_fb = 0.35 * finbert_conf
                        w_cl = 0.65 * claude_conf
                        total_w = w_fb + w_cl
                        
                        if total_w > 0 and score.get("is_zl_relevant", True):
                            ensemble_score = (finbert_score * w_fb + claude_score * w_cl) / total_w
                            # Agreement bonus
                            agreement = 0.1 if (finbert_score * claude_score > 0) else -0.05
                            ensemble_conf = min(0.95, (finbert_conf * 0.4 + claude_conf * 0.6) + agreement)
                        else:
                            ensemble_score = claude_score
                            ensemble_conf = claude_conf
                        
                        if ensemble_score > 0.05:
                            direction = "bullish"
                        elif ensemble_score < -0.05:
                            direction = "bearish"
                        else:
                            direction = "neutral"
                        
                        matched_categories["ensemble"] = {
                            "score": round(ensemble_score, 4),
                            "direction": direction,
                            "confidence": round(ensemble_conf, 4),
                            "method": "finbert+claude_opus"
                        }
                        
                        final_score = ensemble_score
                        final_direction = direction
                        final_confidence = ensemble_conf
                    except:
                        final_score = score.get("zl_impact_score", 0)
                        final_direction = score.get("sentiment", "neutral")
                        final_confidence = score.get("confidence", 0.5)
                else:
                    final_score = score.get("zl_impact_score", 0)
                    final_direction = score.get("sentiment", "neutral")
                    final_confidence = score.get("confidence", 0.5)
                
                # Update the record
                cur.execute("""
                    UPDATE silver.news_scored_1d
                    SET 
                        sentiment_score = %s,
                        sentiment_direction = %s,
                        sentiment_confidence = %s,
                        is_zl_relevant = %s,
                        zl_impact_score = %s,
                        affects_crush = %s,
                        affects_china = %s,
                        affects_fx = %s,
                        affects_fed = %s,
                        affects_tariff = %s,
                        affects_energy = %s,
                        affects_biofuel = %s,
                        affects_palm = %s,
                        affects_volatility = %s,
                        affects_substitutes = %s,
                        affects_trump_effect = %s,
                        matched_categories = %s,
                        scoring_model = %s,
                        scored_at = NOW()
                    WHERE raw_id = %s
                """, (
                    final_score,
                    final_direction,
                    final_confidence,
                    score.get("is_zl_relevant", True),
                    final_score,
                    "crush" in affected,
                    "china" in affected,
                    "fx" in affected,
                    "fed" in affected,
                    "tariff" in affected,
                    "energy" in affected,
                    "biofuel" in affected,
                    "palm" in affected,
                    "volatility" in affected,
                    "substitutes" in affected,
                    "trump_effect" in affected,
                    json.dumps(matched_categories),
                    "finbert+claude_opus",
                    raw_id
                ))
                
                updated += 1
                print(f"  [{updated}/{len(CLAUDE_OPUS_SCORES)}] raw_id={raw_id}: {final_direction} ({final_score:.3f})")
            
            conn.commit()
            print(f"\n✅ Updated {updated} articles with Claude Opus 4.5 analysis")
            
            # Show distribution
            cur.execute("""
                SELECT 
                    scoring_model,
                    COUNT(*) as count,
                    ROUND(AVG(sentiment_score)::numeric, 4) as avg_score,
                    COUNT(*) FILTER (WHERE sentiment_direction = 'bullish') as bullish,
                    COUNT(*) FILTER (WHERE sentiment_direction = 'bearish') as bearish,
                    COUNT(*) FILTER (WHERE sentiment_direction = 'neutral') as neutral
                FROM silver.news_scored_1d
                GROUP BY scoring_model
                ORDER BY count DESC
            """)
            
            print("\n📊 Scoring Model Distribution:")
            print("-" * 80)
            for row in cur.fetchall():
                print(f"  {row[0]}: {row[1]} articles | avg={row[2]} | "
                      f"bullish={row[3]} bearish={row[4]} neutral={row[5]}")
    
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Importing Claude Opus 4.5 Sentiment Scores")
    print("=" * 60)
    import_opus_scores()
