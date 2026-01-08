#!/usr/bin/env python3
"""
BATCH 1: AI Compute Layer Scores
50 high-signal articles scored by Claude Opus 4.5
"""

import json
import psycopg2
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

def get_connection():
    env_path = PROJECT_ROOT / ".env"
    database_url = None
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    database_url = line.split("=", 1)[1].strip().strip('"')
                    break
    return psycopg2.connect(database_url)

# Batch 1 scores from Claude Opus 4.5 in-conversation analysis
BATCH1_SCORES = [
    # (raw_id, ai_score, sentiment, confidence, is_zl_relevant, affected_specialists, factor_breakdown, finbert_correction, overlay_narrative)
    (9223, 0.65, "bullish", 0.85, True, ["crush", "china"], 
     {"crush": {"supply_dynamics": 0.9}}, 
     "FinBERT wrong: 'cut' in supply = BULLISH not bearish",
     "Brazil soy cut 2.4 MMT supports ZL; r=-0.70 Brazil production correlation = bullish 3-5% over 1-month"),
    
    (9261, 0.45, "bullish", 0.75, True, ["crush", "substitutes"],
     {"crush": {"supply_dynamics": 0.8}, "substitutes": {"corn_correlation": 0.5}},
     "FinBERT wrong: Brazil corn drop = supply tightening = bullish",
     "Brazil corn 9.5% drop supports grain complex; r=+0.50 corn correlation lifts ZL 1-2%"),
    
    (9204, 0.78, "bullish", 0.90, True, ["crush", "china", "palm"],
     {"crush": {"supply_dynamics": 0.95}, "china": {"import_policy": 0.3}, "palm": {"substitution_effect": 0.4}},
     "FinBERT wrong: 11.3 MMT cut = MAJOR supply shock = very bullish",
     "Brazil soy lowest since 2015-16; SHAP weight -0.09 for SouthAm supply now POSITIVE; expect 5-8% upside"),
    
    (9274, 0.82, "bullish", 0.92, True, ["crush", "china", "substitutes"],
     {"crush": {"supply_dynamics": 0.95, "crush_margins": 0.3}},
     "FinBERT wrong: Argentina drought = 2/3 capacity idle = supply crisis = BULLISH",
     "Argentina historic drought; crush capacity 2/3 idle = global supply squeeze; r=-0.72 USD/ARS supports; +6-10% potential"),
    
    (12290, -0.40, "bearish", 0.65, True, ["tariff", "china"],
     {"tariff": {"trade_policy": 0.8}, "china": {"import_policy": 0.3}},
     None,
     "India-US tariff friction; trade uncertainty weighs on export sentiment; -2% risk"),
    
    (7296, -0.55, "bearish", 0.80, True, ["tariff", "crush"],
     {"tariff": {"trade_policy": 0.9}, "crush": {"farmer_economics": 0.5}},
     None,
     "Soy down 40% since 2013, farm income down 50%; structural bearish pressure without trade deals"),
    
    (11779, -0.70, "bearish", 0.88, True, ["crush", "china"],
     {"crush": {"export_demand": 0.9}, "china": {"import_policy": 0.5}},
     None,
     "US soy shipments slowest in decade; export weakness r=-0.65 USD/BRL pressure; -3-5% near-term"),
    
    (8962, 0.00, "neutral", 0.20, False, [],
     {},
     None,
     None),
    
    (190, -0.55, "bearish", 0.75, True, ["biofuel", "crush"],
     {"biofuel": {"rfs_compliance": 0.9}},
     None,
     "EPA ethanol formula disappoints farmers; SHAP biofuel +0.12 weight at risk; -2-3% policy headwind"),
    
    (12245, -0.60, "bearish", 0.80, True, ["energy", "biofuel"],
     {"energy": {"crude_correlation": 0.85}, "biofuel": {"biodiesel_economics": 0.7}},
     None,
     "Oil surplus depresses crude; cheap energy kills biodiesel economics; SHAP energy weight bearish"),
    
    (7250, -0.65, "bearish", 0.85, True, ["tariff", "china", "crush"],
     {"tariff": {"trade_policy": 0.9}, "china": {"import_policy": 0.7}},
     None,
     "Trade war drags ZL; China retaliation risk -10-15%; structural bearish without resolution"),
    
    (5060, -0.15, "bearish", 0.45, True, ["biofuel", "energy"],
     {"biofuel": {"ev_demand": 0.4}},
     None,
     "Tesla decline suggests EV momentum slowdown; indirect biofuel demand impact; -1% mild pressure"),
    
    (8624, 0.72, "bullish", 0.88, True, ["crush", "china"],
     {"crush": {"supply_dynamics": 0.9}},
     "FinBERT wrong: StoneX Brazil cut 11 MMT = supply shock = BULLISH",
     "Brazil supply revised down sharply; r=-0.70 SouthAm competition eases; +5-7% upside"),
    
    (8641, 0.55, "bullish", 0.70, True, ["fx", "tariff", "crush"],
     {"fx": {"usd_ars": 0.7}, "tariff": {"export_tax": 0.5}},
     "FinBERT wrong: ARS devaluation + export tax cuts = net BULLISH for Argentina exports but supports global prices short-term",
     "Argentina peso crash 50%; export tax cuts stimulate sales but USD strength caps gains; mixed +2-4%"),
    
    (9135, 0.50, "bullish", 0.75, True, ["crush", "substitutes"],
     {"crush": {"supply_dynamics": 0.8}},
     "FinBERT wrong: yield plummet = supply stress = BULLISH",
     "Midwest corn yields plummet; r=+0.50 corn correlation supports ZL; +2-3%"),
    
    (6825, 0.20, "bullish", 0.55, True, ["crush"],
     {"crush": {"export_demand": 0.6}},
     "FinBERT wrong: exports exceeding pace = demand signal = mildly bullish",
     "Wheat exports strong; grain complex sentiment supportive; +1%"),
    
    (5589, -0.25, "bearish", 0.50, True, ["fed", "volatility"],
     {"fed": {"monetary_policy": 0.5}, "volatility": {"market_stress": 0.4}},
     None,
     "Labor market weakness; Fed policy uncertainty; macro headwind -1-2%"),
    
    (8637, 0.65, "bullish", 0.85, True, ["crush", "substitutes"],
     {"crush": {"supply_dynamics": 0.9}},
     "FinBERT wrong: largest corn yield decline in 25 years = supply shock = BULLISH",
     "Record corn yield decline; tight stocks r=+0.50 supports ZL; +4-5%"),
    
    (87, -0.30, "bearish", 0.60, True, ["tariff", "trump_effect"],
     {"tariff": {"trade_policy": 0.7}, "trump_effect": {"policy_sentiment": 0.5}},
     None,
     "Waning farmer support for tariffs; policy uncertainty; -1-2%"),
    
    (9372, 0.35, "bullish", 0.55, True, ["energy"],
     {"energy": {"crude_correlation": 0.6}},
     "FinBERT wrong: Sudan oil disruption = energy support = mildly bullish for biodiesel economics",
     "Sudan drone strikes cut oil supply; crude support helps biofuel margins; +1-2%"),
    
    (4848, -0.20, "bearish", 0.45, True, ["energy", "biofuel"],
     {"energy": {"gas_prices": 0.5}},
     None,
     "CA gas decline on solar rise; energy transition headwind for fossil fuels; -1%"),
    
    (8650, 0.55, "bullish", 0.75, True, ["crush"],
     {"crush": {"supply_dynamics": 0.8}},
     "FinBERT wrong: 6.3M acre crop loss = supply tightening = BULLISH",
     "Mystery acreage loss tightens supply; +3-4%"),
    
    (11883, -0.15, "bearish", 0.40, True, ["trump_effect"],
     {"trump_effect": {"policy_uncertainty": 0.5}},
     None,
     "GOP unrest creates policy uncertainty; -1%"),
    
    (9283, 0.48, "bullish", 0.72, True, ["crush", "substitutes"],
     {"crush": {"supply_dynamics": 0.75}},
     "FinBERT wrong: corn plantings decline = supply reduction = BULLISH",
     "US corn plantings down 3M acres; supply tightening r=+0.50 supports ZL; +2-3%"),
    
    (8290, 0.00, "neutral", 0.10, False, [],
     {},
     None,
     None),
    
    (5011, -0.45, "bearish", 0.70, True, ["tariff", "crush"],
     {"tariff": {"trade_friction": 0.8}},
     None,
     "Mexico pork investigation; trade friction spreads; -2%"),
    
    (9268, 0.40, "bullish", 0.70, True, ["crush", "china"],
     {"crush": {"supply_dynamics": 0.7}},
     "FinBERT wrong: Brazil soy cut = supply concern = BULLISH",
     "Brazil rains too late; supply trimmed 1 MMT; +2%"),
    
    (7859, 0.00, "neutral", 0.10, False, [],
     {},
     None,
     None),
    
    (12073, -0.35, "bearish", 0.60, True, ["china"],
     {"china": {"demand_outlook": 0.7}},
     None,
     "China property slump; demand concerns; r=-0.58 USD/CNY; -2%"),
    
    (6772, 0.70, "bullish", 0.88, True, ["crush", "substitutes", "china"],
     {"crush": {"supply_dynamics": 0.9}, "substitutes": {"corn_stocks": 0.8}},
     "FinBERT wrong: 29-year low stocks = BULLISH not bearish!",
     "Global corn stocks at 29-year lows; extreme tightness r=+0.50 corn correlation; +5-7%"),
    
    (9290, 0.00, "neutral", 0.10, False, [],
     {},
     None,
     None),
    
    (4854, 0.00, "neutral", 0.15, False, [],
     {},
     None,
     None),
    
    (5229, 0.00, "neutral", 0.10, False, [],
     {},
     None,
     None),
    
    (5205, -0.50, "bearish", 0.75, True, ["tariff", "crush"],
     {"tariff": {"input_costs": 0.7}, "crush": {"farmer_economics": 0.6}},
     None,
     "Equipment prices climb on tariffs; farmer cost pressure; -2-3%"),
    
    (5546, -0.20, "bearish", 0.40, True, ["trump_effect"],
     {"trump_effect": {"policy_action": 0.5}},
     None,
     "Trump fraud suspensions; policy uncertainty; -1%"),
    
    (12207, -0.40, "bearish", 0.65, True, ["biofuel", "palm"],
     {"biofuel": {"saf_demand": 0.7}},
     None,
     "Malaysia SAF slowed by costs; biofuel headwind; -2%"),
    
    (7343, -0.60, "bearish", 0.80, True, ["biofuel", "crush"],
     {"biofuel": {"rfs_compliance": 0.9}},
     None,
     "EPA RFS waivers undermine biofuel demand; SHAP +0.12 biofuel weight at risk; -3-4%"),
    
    (7492, -0.45, "bearish", 0.70, True, ["crush"],
     {"crush": {"logistics": 0.8}},
     None,
     "Mississippi barge groundings; logistics disruption; -2%"),
    
    (157, -0.55, "bearish", 0.75, True, ["biofuel", "trump_effect"],
     {"biofuel": {"policy_support": 0.8}},
     None,
     "Biofuels plan disappoints; policy headwind for SHAP +0.12 biofuel; -3%"),
    
    (4743, 0.15, "neutral", 0.50, True, ["crush", "substitutes"],
     {"crush": {"price_outlook": 0.5}},
     None,
     "Mixed outlook for corn $5, beans $12; neutral near-term"),
    
    (5161, 0.00, "neutral", 0.10, False, [],
     {},
     None,
     None),
    
    (7519, -0.25, "bearish", 0.55, True, ["crush"],
     {"crush": {"farmer_economics": 0.6}},
     None,
     "Foliar fertilizers hurt profits; farmer economics pressure; -1%"),
    
    (7460, -0.40, "bearish", 0.65, True, ["trump_effect", "crush"],
     {"trump_effect": {"usda_policy": 0.7}},
     None,
     "USDA job cuts affect meat labs; policy concern; -2%"),
    
    (9213, 0.55, "bullish", 0.78, True, ["crush", "substitutes"],
     {"crush": {"supply_dynamics": 0.8}},
     "FinBERT wrong: corn yield cut = supply reduction = BULLISH",
     "US corn yield forecast cut 2 bu on rust; supply concern; r=+0.50 corn; +3%"),
    
    (5017, -0.30, "bearish", 0.60, True, ["crush"],
     {"crush": {"processing_capacity": 0.7}},
     None,
     "ADM Memphis closure reduces crush capacity; -1-2%"),
    
    (9234, 0.72, "bullish", 0.90, True, ["china", "crush"],
     {"china": {"import_demand": 0.9}, "crush": {"export_demand": 0.6}},
     "FinBERT wrong: China lowest inventories since 2010 = DEMAND SIGNAL = BULLISH!",
     "China soy inventories at 14-year lows; import demand surge imminent; r=-0.58 USD/CNY supports; +5-8%"),
    
    (5139, -0.35, "bearish", 0.60, True, ["tariff", "trump_effect"],
     {"tariff": {"policy_risk": 0.7}, "trump_effect": {"rhetoric": 0.5}},
     None,
     "Trump defends tariffs amid SCOTUS challenge; uncertainty; -2%"),
    
    (8789, 0.25, "bullish", 0.50, True, ["volatility"],
     {"volatility": {"market_sentiment": 0.6}},
     "FinBERT wrong: short squeeze = risk sentiment improving = mildly bullish",
     "Short losses $70B; risk-on sentiment; VIX r=-0.45 correlation easing; +1%"),
    
    (9197, -0.50, "bearish", 0.72, True, ["crush"],
     {"crush": {"farmer_economics": 0.85}},
     None,
     "Corn/fertilizer ratio worst on record; farmer stress; -2-3%"),
    
    (5117, -0.20, "bearish", 0.45, True, ["trump_effect", "energy"],
     {"trump_effect": {"energy_policy": 0.6}},
     None,
     "Trump wind blocks challenged; energy policy uncertainty; -1%"),
]

def update_scores():
    conn = get_connection()
    try:
        cur = conn.cursor()
        
        for row in BATCH1_SCORES:
            raw_id, ai_score, sentiment, confidence, is_zl_relevant, specialists, factor_breakdown, fb_correction, overlay = row
            
            # Get original FinBERT score for ensemble
            cur.execute("SELECT sentiment_score FROM silver.news_scored_1d WHERE raw_id = %s", (raw_id,))
            result = cur.fetchone()
            fb_score = float(result[0]) if result else 0
            
            # Ensemble: 70% AI, 30% FinBERT (confidence weighted)
            if is_zl_relevant and confidence > 0:
                w_ai = 0.70 * confidence
                w_fb = 0.30 * 0.7  # Assume 0.7 FinBERT confidence
                total_w = w_ai + w_fb
                ensemble_score = (ai_score * w_ai + fb_score * w_fb) / total_w
                
                # Agreement bonus
                if ai_score * fb_score > 0:
                    ensemble_conf = min(0.95, confidence * 0.7 + 0.7 * 0.3 + 0.1)
                else:
                    ensemble_conf = min(0.95, confidence * 0.7 + 0.7 * 0.3 - 0.05)
            else:
                ensemble_score = ai_score
                ensemble_conf = confidence
            
            # Direction
            if ensemble_score > 0.05:
                direction = "bullish"
            elif ensemble_score < -0.05:
                direction = "bearish"
            else:
                direction = "neutral"
            
            # Build matched_categories JSON
            matched_categories = {
                "finbert": {"score": fb_score, "label": "bearish" if fb_score < 0 else "bullish", "confidence": 0.7},
                "ai_compute": {
                    "agent": "sentiment_scorer",
                    "model": "claude-opus-4.5",
                    "score": ai_score,
                    "sentiment": sentiment,
                    "confidence": confidence,
                    "finbert_correction": fb_correction,
                    "overlay_narrative": overlay,
                },
                "ensemble": {
                    "score": round(ensemble_score, 4),
                    "direction": direction,
                    "confidence": round(ensemble_conf, 4),
                    "method": "finbert+ai_compute"
                },
                "factor_breakdown": factor_breakdown,
                "affected_specialists": specialists
            }
            
            # Update
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
                ensemble_score,
                direction,
                ensemble_conf,
                is_zl_relevant,
                ensemble_score,
                "crush" in specialists,
                "china" in specialists,
                "fx" in specialists,
                "fed" in specialists,
                "tariff" in specialists,
                "energy" in specialists,
                "biofuel" in specialists,
                "palm" in specialists,
                "volatility" in specialists,
                "substitutes" in specialists,
                "trump_effect" in specialists,
                json.dumps(matched_categories),
                "finbert+ai_compute",
                raw_id
            ))
            
            print(f"Updated raw_id {raw_id}: {sentiment} ({ensemble_score:+.3f})")
        
        conn.commit()
        print(f"\n✅ BATCH 1 COMPLETE: {len(BATCH1_SCORES)} articles updated!")
        
    finally:
        conn.close()

if __name__ == "__main__":
    update_scores()
