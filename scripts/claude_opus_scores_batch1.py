#!/usr/bin/env python3
"""
Claude Opus 4.5 Direct Scoring Results
Generated: 2026-01-07
Batch: 30 high-signal articles (FinBERT |score| > 0.15)

This file contains sentiment analysis performed directly by Claude Opus 4.5
in conversation, bypassing API rate limits using Kirk's Pro subscription.
"""

import json

CLAUDE_OPUS_SCORES = [
    # Article 1: Corn ethanol use down
    {
        "raw_id": 6828,
        "is_zl_relevant": True,
        "sentiment": "bearish",
        "zl_impact_score": -0.35,
        "confidence": 0.75,
        "time_horizon": "short_term",
        "affected_specialists": ["crush", "biofuel"],
        "factor_breakdown": {
            "crush": {"domestic_demand": 0.6, "processing_capacity": 0.3},
            "biofuel": {"rfs_volumes": 0.7, "blending_requirements": 0.3}
        },
        "reasoning": "Lower corn ethanol usage signals reduced biofuel demand, indirectly bearish for soybean oil as biodiesel feedstock competition eases. USDA target shortfall indicates demand weakness.",
        "key_quote": "down 18 million bushels or 1% from the previous year's pace"
    },
    
    # Article 2: World corn buffer stocks at 80 days - lowest since 2010
    {
        "raw_id": 9243,
        "is_zl_relevant": True,
        "sentiment": "bullish",
        "zl_impact_score": 0.55,
        "confidence": 0.80,
        "time_horizon": "medium_term",
        "affected_specialists": ["crush", "volatility"],
        "factor_breakdown": {
            "crush": {"soybean_supply": 0.7, "basis_levels": 0.3},
            "volatility": {"market_stress": 0.6, "risk_sentiment": 0.4}
        },
        "reasoning": "Tight global grain stocks (80 days, down 28% from 5 years ago) signal supply stress across oilseed complex. Bullish for ZL as tight corn stocks often correlate with soybean tightness.",
        "key_quote": "lowest level since 2010-11"
    },
    
    # Article 3: National gas price to fall to $3/gallon
    {
        "raw_id": 12238,
        "is_zl_relevant": True,
        "sentiment": "bearish",
        "zl_impact_score": -0.45,
        "confidence": 0.85,
        "time_horizon": "structural",
        "affected_specialists": ["energy", "biofuel", "trump_effect"],
        "factor_breakdown": {
            "energy": {"diesel_prices": 0.5, "crude_correlation": 0.5},
            "biofuel": {"biodiesel_mandates": 0.4, "renewable_diesel": 0.6},
            "trump_effect": {"energy_policy": 0.7, "deregulation": 0.3}
        },
        "reasoning": "Lower gasoline prices reduce biodiesel economics - when petroleum is cheap, renewable fuel blending is less attractive. $2.97/gal average strongly bearish for soybean oil demand.",
        "key_quote": "expected to be $2.97, down from $3.10 in 2025"
    },
    
    # Article 4: US corn conditions fall to 55% G/E - lowest since 1992
    {
        "raw_id": 6773,
        "is_zl_relevant": True,
        "sentiment": "bullish",
        "zl_impact_score": 0.65,
        "confidence": 0.90,
        "time_horizon": "short_term",
        "affected_specialists": ["crush", "volatility"],
        "factor_breakdown": {
            "crush": {"soybean_supply": 0.8, "basis_levels": 0.2},
            "volatility": {"market_stress": 0.7, "risk_sentiment": 0.3}
        },
        "reasoning": "Historic crop stress (lowest since 1992/2012) extremely bullish for oilseed complex. Illinois collapse from 48% to 36% G/E signals severe drought impact on soybean belt.",
        "key_quote": "lowest since 1992 and the lowest for any week in June or July since 2012"
    },
    
    # Article 5: US share of China soybean market fell to 21%
    {
        "raw_id": 50,
        "is_zl_relevant": True,
        "sentiment": "bearish",
        "zl_impact_score": -0.60,
        "confidence": 0.90,
        "time_horizon": "structural",
        "affected_specialists": ["china", "tariff", "crush"],
        "factor_breakdown": {
            "china": {"import_policy": 0.5, "buying_pace": 0.3, "trade_relations": 0.2},
            "tariff": {"trade_policy": 0.6, "bilateral_deals": 0.4},
            "crush": {"domestic_demand": 0.4, "soybean_supply": 0.6}
        },
        "reasoning": "Structural loss of China market share (21% down from historic 30-40%) represents permanent demand destruction for US soybeans. Brazil capturing market. Very bearish for US crush margins and ZL.",
        "key_quote": "US Share of China Soybean Market Fell to 21% in 2024"
    },
    
    # Article 6: US rig counts low, production efficiencies improve
    {
        "raw_id": 4851,
        "is_zl_relevant": True,
        "sentiment": "bearish",
        "zl_impact_score": -0.25,
        "confidence": 0.65,
        "time_horizon": "medium_term",
        "affected_specialists": ["energy"],
        "factor_breakdown": {
            "energy": {"crude_correlation": 0.6, "refinery_operations": 0.4}
        },
        "reasoning": "Declining rig count with stable production = efficient oil supply, keeping crude prices suppressed. Lower energy prices reduce biodiesel economics, mildly bearish for ZL.",
        "key_quote": "declined steadily from 750 rigs in December 2022 to 517 rigs this October"
    },
    
    # Article 7: Nat Gas futures fall 28% from highs
    {
        "raw_id": 6010,
        "is_zl_relevant": True,
        "sentiment": "bearish",
        "zl_impact_score": -0.30,
        "confidence": 0.70,
        "time_horizon": "short_term",
        "affected_specialists": ["energy", "volatility"],
        "factor_breakdown": {
            "energy": {"crude_correlation": 0.5, "fuel_demand": 0.5},
            "volatility": {"risk_sentiment": 0.6, "correlation_shifts": 0.4}
        },
        "reasoning": "Nat gas collapse on warmer weather signals broader energy weakness. Lower energy complex reduces renewable fuel competitiveness, bearish for ZL biodiesel demand.",
        "key_quote": "fallen ~28% from its Dec. 5 highs"
    },
    
    # Article 8: Crude oil prices fell in 2025 amid oversupply
    {
        "raw_id": 11914,
        "is_zl_relevant": True,
        "sentiment": "bearish",
        "zl_impact_score": -0.50,
        "confidence": 0.85,
        "time_horizon": "structural",
        "affected_specialists": ["energy", "biofuel"],
        "factor_breakdown": {
            "energy": {"crude_correlation": 0.7, "diesel_prices": 0.3},
            "biofuel": {"biodiesel_mandates": 0.4, "renewable_diesel": 0.6}
        },
        "reasoning": "Structural crude oversupply devastates biodiesel economics. When petroleum is cheap and abundant, ZL demand for renewable fuel production collapses.",
        "key_quote": "supplies in the global crude oil market exceeding demand"
    },
    
    # Article 9: USDA leaves US soybean exports at 13-year low
    {
        "raw_id": 10,
        "is_zl_relevant": True,
        "sentiment": "bearish",
        "zl_impact_score": -0.70,
        "confidence": 0.92,
        "time_horizon": "structural",
        "affected_specialists": ["china", "crush", "tariff"],
        "factor_breakdown": {
            "china": {"import_policy": 0.5, "buying_pace": 0.5},
            "crush": {"domestic_demand": 0.4, "soybean_supply": 0.6},
            "tariff": {"trade_policy": 0.7, "retaliatory_tariffs": 0.3}
        },
        "reasoning": "13-year low exports (1.635B bu, down 13%) confirms structural demand destruction. China tariff impact permanent. Extremely bearish for US soybean complex and ZL.",
        "key_quote": "13-year low of 1.635 billion bushels, down 13%"
    },
    
    # Article 10: Midwest basis declining, record harvest vs tight storage
    {
        "raw_id": 9241,
        "is_zl_relevant": True,
        "sentiment": "bearish",
        "zl_impact_score": -0.40,
        "confidence": 0.80,
        "time_horizon": "short_term",
        "affected_specialists": ["crush"],
        "factor_breakdown": {
            "crush": {"basis_levels": 0.7, "plant_operations": 0.2, "soybean_supply": 0.1}
        },
        "reasoning": "Record harvest crushing basis levels is bearish - oversupply forces farmers to sell at depressed prices. Storage crisis indicates glut conditions for soybeans.",
        "key_quote": "record harvest is running head on into extraordinarily tight storage capacity"
    },
    
    # Article 11: Worker bonuses slump after GOP tax cuts
    {
        "raw_id": 8292,
        "is_zl_relevant": False,
        "sentiment": "neutral",
        "zl_impact_score": 0.0,
        "confidence": 0.85,
        "time_horizon": "structural",
        "affected_specialists": [],
        "factor_breakdown": {},
        "reasoning": "General economic/political news about tax policy and worker compensation. No direct connection to soybean oil markets, oilseeds, or agricultural commodities.",
        "key_quote": None
    },
    
    # Article 12: US total crude inventories at 36-year low
    {
        "raw_id": 6921,
        "is_zl_relevant": True,
        "sentiment": "bullish",
        "zl_impact_score": 0.45,
        "confidence": 0.80,
        "time_horizon": "medium_term",
        "affected_specialists": ["energy", "biofuel"],
        "factor_breakdown": {
            "energy": {"crude_correlation": 0.8, "refinery_operations": 0.2},
            "biofuel": {"biodiesel_mandates": 0.5, "renewable_diesel": 0.5}
        },
        "reasoning": "Historic low crude inventories (36-year low, below 2001) bullish for energy prices. Higher crude improves biodiesel economics, bullish for ZL demand.",
        "key_quote": "fallen to a 36-year low, dropping below the previous bottom set in 2001"
    },
    
    # Article 13: USDA projects ag trade deficit will fall
    {
        "raw_id": 99,
        "is_zl_relevant": True,
        "sentiment": "neutral",
        "zl_impact_score": -0.15,
        "confidence": 0.60,
        "time_horizon": "medium_term",
        "affected_specialists": ["crush", "china"],
        "factor_breakdown": {
            "crush": {"domestic_demand": 0.5, "soybean_supply": 0.5},
            "china": {"import_policy": 0.4, "trade_relations": 0.6}
        },
        "reasoning": "Falling ag trade deficit could indicate reduced exports OR reduced imports. Without detail, slightly bearish as it often reflects weaker export demand.",
        "key_quote": "Trade Deficit Will Fall to $41.5 Billion in 2026"
    },
    
    # Article 14: EIA forecasts US crude production decrease in 2026
    {
        "raw_id": 4841,
        "is_zl_relevant": True,
        "sentiment": "bullish",
        "zl_impact_score": 0.30,
        "confidence": 0.75,
        "time_horizon": "medium_term",
        "affected_specialists": ["energy", "biofuel"],
        "factor_breakdown": {
            "energy": {"crude_correlation": 0.7, "pipeline_capacity": 0.3},
            "biofuel": {"biodiesel_mandates": 0.5, "renewable_diesel": 0.5}
        },
        "reasoning": "Declining US crude production (13.5M b/d, down 100K b/d) tightens supply, supports energy prices. Better crude prices improve ZL biodiesel economics.",
        "key_quote": "about 100,000 b/d less than in 2025"
    },
    
    # Article 15: European wealth tax countries fell from 12 to 3
    {
        "raw_id": 8257,
        "is_zl_relevant": False,
        "sentiment": "neutral",
        "zl_impact_score": 0.0,
        "confidence": 0.90,
        "time_horizon": "structural",
        "affected_specialists": [],
        "factor_breakdown": {},
        "reasoning": "European tax policy has no connection to soybean oil markets. This is general political/economic commentary with zero ZL relevance.",
        "key_quote": None
    },
    
    # Article 16: Farmers hurt by Trump tariffs + USDA staff losses
    {
        "raw_id": 6200,
        "is_zl_relevant": True,
        "sentiment": "bearish",
        "zl_impact_score": -0.55,
        "confidence": 0.85,
        "time_horizon": "structural",
        "affected_specialists": ["tariff", "trump_effect", "crush"],
        "factor_breakdown": {
            "tariff": {"trade_policy": 0.6, "retaliatory_tariffs": 0.4},
            "trump_effect": {"tariff_threats": 0.7, "ag_policy": 0.3},
            "crush": {"labor_issues": 0.3, "domestic_demand": 0.7}
        },
        "reasoning": "Direct statement of tariff damage to farmers combined with 20% USDA staff loss. Structural bearish pressure on ag sector including soybean complex.",
        "key_quote": "Farmers are being hurt by Trump's tariffs... lost nearly 20% of its staff"
    },
    
    # Article 17: Dr. Cordonnier cuts corn yield to 170 bpa
    {
        "raw_id": 9271,
        "is_zl_relevant": True,
        "sentiment": "bullish",
        "zl_impact_score": 0.50,
        "confidence": 0.85,
        "time_horizon": "short_term",
        "affected_specialists": ["crush", "volatility"],
        "factor_breakdown": {
            "crush": {"soybean_supply": 0.8, "basis_levels": 0.2},
            "volatility": {"market_stress": 0.6, "risk_sentiment": 0.4}
        },
        "reasoning": "Highly respected crop consultant cutting yields is bullish signal. Corn/soybean stress typically moves together. Crop tour confirmation adds credibility.",
        "key_quote": "cut his corn yield forecast by 3 bu. to 170 bpa"
    },
    
    # Article 18: Argentina soybeans to fall 35% from USDA predictions
    {
        "raw_id": 6786,
        "is_zl_relevant": True,
        "sentiment": "bullish",
        "zl_impact_score": 0.75,
        "confidence": 0.92,
        "time_horizon": "short_term",
        "affected_specialists": ["crush", "volatility", "substitutes"],
        "factor_breakdown": {
            "crush": {"soybean_supply": 0.9, "basis_levels": 0.1},
            "volatility": {"market_stress": 0.8, "risk_sentiment": 0.2},
            "substitutes": {"substitute_pricing": 0.6, "cross_commodity_spreads": 0.4}
        },
        "reasoning": "Historic 35% production loss in Argentina (worse than 2009/2018) is extremely bullish. Major global supply shock for soybeans and soy oil. USDA cut 20% in single month unprecedented.",
        "key_quote": "35% from USDA's original harvest predictions - more than in 2009 or 2018"
    },
    
    # Article 19: North Dakota spring wheat planting slowest in history
    {
        "raw_id": 6728,
        "is_zl_relevant": True,
        "sentiment": "bullish",
        "zl_impact_score": 0.40,
        "confidence": 0.75,
        "time_horizon": "short_term",
        "affected_specialists": ["crush", "substitutes"],
        "factor_breakdown": {
            "crush": {"soybean_supply": 0.6, "basis_levels": 0.4},
            "substitutes": {"cross_commodity_spreads": 0.7, "demand_switching": 0.3}
        },
        "reasoning": "Record slow wheat planting (27% vs normal 80%) indicates broader crop stress across northern plains. Cross-commodity supply stress bullish for oilseed complex.",
        "key_quote": "planting at the slowest rate in history"
    },
    
    # Article 20: Total principal crops fell by 6.3M acres YoY
    {
        "raw_id": 8649,
        "is_zl_relevant": True,
        "sentiment": "bullish",
        "zl_impact_score": 0.45,
        "confidence": 0.80,
        "time_horizon": "medium_term",
        "affected_specialists": ["crush"],
        "factor_breakdown": {
            "crush": {"soybean_supply": 0.8, "processing_capacity": 0.2}
        },
        "reasoning": "6.3M acre decline in total planted area is structurally bullish for all crops. Less acreage = tighter supply = higher prices for soybeans and ZL.",
        "key_quote": "fell by 6.3 million acres year-on-year"
    },
    
    # Article 21: WTI crude below $12 - lowest since 1999
    {
        "raw_id": 6105,
        "is_zl_relevant": True,
        "sentiment": "bearish",
        "zl_impact_score": -0.80,
        "confidence": 0.95,
        "time_horizon": "short_term",
        "affected_specialists": ["energy", "biofuel", "volatility"],
        "factor_breakdown": {
            "energy": {"crude_correlation": 0.9, "diesel_prices": 0.1},
            "biofuel": {"biodiesel_mandates": 0.3, "renewable_diesel": 0.7},
            "volatility": {"market_stress": 0.9, "liquidity_conditions": 0.1}
        },
        "reasoning": "Sub-$12 WTI is catastrophic for biodiesel economics. When petroleum is this cheap, there is ZERO economic incentive to blend soybean oil into fuel. Extremely bearish.",
        "key_quote": "lowest level since 1999"
    },
    
    # Article 22: Dr. Cordonnier cuts corn yield to 173 bpa
    {
        "raw_id": 9258,
        "is_zl_relevant": True,
        "sentiment": "bullish",
        "zl_impact_score": 0.45,
        "confidence": 0.82,
        "time_horizon": "short_term",
        "affected_specialists": ["crush", "volatility"],
        "factor_breakdown": {
            "crush": {"soybean_supply": 0.7, "basis_levels": 0.3},
            "volatility": {"market_stress": 0.5, "risk_sentiment": 0.5}
        },
        "reasoning": "Another Cordonnier yield cut plus 500K acre reduction for silage/abandonment. Continued deterioration bullish for oilseed complex.",
        "key_quote": "lopped 500,000 acres off his harvested acreage forecast"
    },
    
    # Article 23: Tesla sales plummet across Europe
    {
        "raw_id": 8887,
        "is_zl_relevant": False,
        "sentiment": "neutral",
        "zl_impact_score": 0.0,
        "confidence": 0.88,
        "time_horizon": "short_term",
        "affected_specialists": [],
        "factor_breakdown": {},
        "reasoning": "Tesla automotive sales have no direct connection to soybean oil markets. EV adoption is tangential at best to biodiesel demand.",
        "key_quote": None
    },
    
    # Article 24: Nestle Hong Kong recalls baby formula
    {
        "raw_id": 12198,
        "is_zl_relevant": False,
        "sentiment": "neutral",
        "zl_impact_score": 0.0,
        "confidence": 0.85,
        "time_horizon": "short_term",
        "affected_specialists": [],
        "factor_breakdown": {},
        "reasoning": "Baby formula recall is food safety news with no connection to soybean oil markets or oilseed complex.",
        "key_quote": None
    },
    
    # Article 25: Biostimulants don't always work - no reliable yield gains
    {
        "raw_id": 4772,
        "is_zl_relevant": True,
        "sentiment": "neutral",
        "zl_impact_score": -0.10,
        "confidence": 0.65,
        "time_horizon": "structural",
        "affected_specialists": ["crush"],
        "factor_breakdown": {
            "crush": {"soybean_supply": 0.6, "plant_operations": 0.4}
        },
        "reasoning": "Research showing biostimulants don't reliably improve yields is marginally bearish - limits upside potential for soybean production technology. Minor impact.",
        "key_quote": "no reliable yield gains in most cases"
    },
    
    # Article 26: Dr. Cordonnier slashes Brazil soy estimate by 6 MMT
    {
        "raw_id": 9203,
        "is_zl_relevant": True,
        "sentiment": "bullish",
        "zl_impact_score": 0.70,
        "confidence": 0.90,
        "time_horizon": "short_term",
        "affected_specialists": ["crush", "volatility", "china"],
        "factor_breakdown": {
            "crush": {"soybean_supply": 0.9, "basis_levels": 0.1},
            "volatility": {"market_stress": 0.7, "risk_sentiment": 0.3},
            "china": {"buying_pace": 0.5, "demand_signals": 0.5}
        },
        "reasoning": "6 MMT cut to Brazil (124 MMT) is major global supply shock. Brazil is world's largest producer - southern Brazil drought worse than expected. Very bullish for ZL.",
        "key_quote": "slashed his Brazilian soybean crop estimate by 6 MMT to 124 MMT"
    },
    
    # Article 27: China COVID lockdowns worsen supply chain - 20% of ships stuck
    {
        "raw_id": 6767,
        "is_zl_relevant": True,
        "sentiment": "bearish",
        "zl_impact_score": -0.35,
        "confidence": 0.75,
        "time_horizon": "short_term",
        "affected_specialists": ["china", "volatility"],
        "factor_breakdown": {
            "china": {"demand_signals": 0.6, "buying_pace": 0.4},
            "volatility": {"market_stress": 0.7, "liquidity_conditions": 0.3}
        },
        "reasoning": "COVID lockdowns reducing Chinese demand and causing logistics chaos. Ships stuck at port means delayed/reduced soybean imports. Bearish for demand side.",
        "key_quote": "One-fifth of the world's container ship fleet is estimated to be stuck in port congestion"
    },
    
    # Article 28: Corn condition index lowest since 1988
    {
        "raw_id": 8608,
        "is_zl_relevant": True,
        "sentiment": "bullish",
        "zl_impact_score": 0.60,
        "confidence": 0.88,
        "time_horizon": "short_term",
        "affected_specialists": ["crush", "volatility"],
        "factor_breakdown": {
            "crush": {"soybean_supply": 0.8, "basis_levels": 0.2},
            "volatility": {"market_stress": 0.7, "risk_sentiment": 0.3}
        },
        "reasoning": "Condition index score of 348 is lowest since 1988 - historic crop stress. Corn and soybean conditions highly correlated. Extremely bullish for oilseed complex.",
        "key_quote": "lowest since 1988 for this week of the season"
    },
    
    # Article 29: Rosario exchange cuts Argentina corn to 48 MMT
    {
        "raw_id": 9253,
        "is_zl_relevant": True,
        "sentiment": "bullish",
        "zl_impact_score": 0.50,
        "confidence": 0.82,
        "time_horizon": "short_term",
        "affected_specialists": ["crush", "substitutes"],
        "factor_breakdown": {
            "crush": {"soybean_supply": 0.7, "basis_levels": 0.3},
            "substitutes": {"cross_commodity_spreads": 0.6, "substitute_pricing": 0.4}
        },
        "reasoning": "Argentina corn cut from 50-51 MMT to 48 MMT due to drought. Cross-commodity stress in Argentina bullish for all grains/oilseeds including ZL.",
        "key_quote": "cut its Argentine corn production forecast to 48 MMT"
    },
    
    # Article 30: US retail gas below $3/gallon - lowest since 2021
    {
        "raw_id": 4844,
        "is_zl_relevant": True,
        "sentiment": "bearish",
        "zl_impact_score": -0.50,
        "confidence": 0.88,
        "time_horizon": "medium_term",
        "affected_specialists": ["energy", "biofuel"],
        "factor_breakdown": {
            "energy": {"diesel_prices": 0.6, "crude_correlation": 0.4},
            "biofuel": {"biodiesel_mandates": 0.4, "renewable_diesel": 0.6}
        },
        "reasoning": "Lowest gas prices since 2021 (inflation-adjusted since Feb 2021) is bearish for biodiesel. Cheap petroleum reduces blending incentives.",
        "key_quote": "lowest average U.S. gasoline price since February 2021"
    }
]

print(f"Loaded {len(CLAUDE_OPUS_SCORES)} article scores from Claude Opus 4.5")
