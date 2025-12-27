# Neural Sentiment Routing

Sentiment signals route to ALL specialists, not a subset. This document defines the ownership and weighting.

## Core Principle

**Every specialist receives sentiment signal.** Commodity markets are driven by narrative and news across all domains.

## Sentiment Weight Distribution

| Specialist | Weight | Rationale | Example Headlines |
|------------|--------|-----------|-------------------|
| crush | 0.10 | WASDE/supply sentiment | "USDA raises soybean yield estimate" |
| china | 0.15 | Trade/demand sentiment | "China increases soybean imports despite tensions" |
| fx | 0.08 | Currency/macro sentiment | "Fed signals rate pause, dollar weakens" |
| fed | 0.10 | Monetary policy tone | "Powell testimony spooks markets" |
| tariff | 0.15 | Trade policy sentiment | "New tariffs announced on agricultural products" |
| energy | 0.12 | Energy/crude sentiment | "EIA reports surprise crude build" |
| biofuel | 0.12 | Biofuel mandate sentiment | "EPA finalizes higher biodiesel blend mandate" |
| palm | 0.08 | Palm/deforestation sentiment | "Indonesia palm export levy increased" |
| volatility | 0.05 | Risk sentiment amplifier | "Markets tumble on geopolitical fears" |
| substitutes | 0.05 | Cross-commodity sentiment | "Canola prices surge on drought concerns" |

**Total: 1.00**

## Implementation in taxonomy.py

Update `NEURAL_DRIVER_OWNERSHIP` to route `neural_sentiment` to all specialists:

```python
NEURAL_DRIVER_OWNERSHIP = {
    "neural_sentiment": [
        ("crush", 0.10, "WASDE/supply sentiment"),
        ("china", 0.15, "Trade/demand sentiment"),
        ("fx", 0.08, "Currency/macro sentiment"),
        ("fed", 0.10, "Monetary policy tone"),
        ("tariff", 0.15, "Trade policy sentiment"),
        ("energy", 0.12, "Energy/crude sentiment"),
        ("biofuel", 0.12, "Biofuel mandate sentiment"),
        ("palm", 0.08, "Palm/deforestation sentiment"),
        ("volatility", 0.05, "Risk sentiment amplifier"),
        ("substitutes", 0.05, "Cross-commodity sentiment"),
    ],
    # Other neural drivers...
}
```

## AI Agent Jobs

| Job | Frequency | Model | Owner |
|-----|-----------|-------|-------|
| News sentiment scoring | 2x daily (6AM, 6PM ET) | Claude Sonnet 4.5 | `neural_sentiment` → ALL |
| CFTC COT interpretation | Weekly (Tuesday 8AM CT) | Claude Sonnet 4.5 | `volatility` |
| WASDE PDF extraction | Monthly (10th-12th) | Claude Sonnet 4.5 | `crush` |
| Crop anomaly detection | Weekly (Saturday) | Claude Sonnet 4.5 | `core` |
| GDELT geopolitical | Daily (7AM ET) | Claude Sonnet 4.5 | `tariff`, `china` |

## Sentiment Feature Schema

Each specialist receives its own sentiment features:

```sql
CREATE TABLE features.sentiment_specialist_1d (
    as_of_date DATE NOT NULL,
    specialist VARCHAR NOT NULL,
    
    -- Core sentiment metrics
    sentiment_score DOUBLE,           -- -1 to +1 polarity
    sentiment_confidence DOUBLE,      -- 0 to 1 model confidence
    
    -- Volume metrics
    news_volume_24h INTEGER,
    news_volume_7d_avg DOUBLE,
    volume_zscore DOUBLE,
    
    -- Momentum
    sentiment_momentum_3d DOUBLE,
    sentiment_momentum_7d DOUBLE,
    sentiment_acceleration DOUBLE,
    
    -- Source breakdown (optional)
    source_reuters DOUBLE,
    source_bloomberg DOUBLE,
    source_usda DOUBLE,
    source_twitter DOUBLE,
    
    -- AI agent attribution
    agent_model VARCHAR,              -- 'claude-sonnet-4.5'
    agent_run_id VARCHAR,
    
    PRIMARY KEY (as_of_date, specialist)
);
```

## Rule-Based vs AI Sentiment

Current state: `src/fusion/api/news_sentiment.py` is **rule-based** (keyword matching).

Future state: Claude API jobs for richer interpretation.

```python
# Rule-based (current)
from fusion.api.news_sentiment import classify_article

# AI-enhanced (planned)
from fusion.agents.sentiment import score_with_claude
```

Both should output to the same schema. The `agent_model` column distinguishes:
- `NULL` or `'rule_based'` → keyword matcher
- `'claude-sonnet-4.5'` → AI-scored

## Category → Specialist Mapping

From `news_sentiment.py`, map alert buckets to specialists:

| Alert Bucket | Primary Specialist | Secondary |
|--------------|-------------------|-----------|
| US Regulatory Filings | fed | tariff |
| Political Changes | tariff | china |
| Tariff Updates | tariff | china |
| China Relations | china | tariff |
| Legislation Changes | biofuel | fed |
| Biofuel Mandates | biofuel | energy |
| Logistics/Chokepoints | crush | energy |
| ESG/Deforestation | palm | substitutes |
| Labor Actions | crush | energy |
| Fertilizer/Energy | energy | crush |
| Animal Disease | china | crush |

## Validation

Ensure sentiment features exist for ALL specialists:

```sql
-- Check all specialists have sentiment
SELECT specialist, COUNT(*) as days
FROM features.sentiment_specialist_1d
WHERE as_of_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY specialist
ORDER BY specialist;

-- Should return 10 rows (all specialists)

-- Check for missing specialists
SELECT s.specialist
FROM (VALUES ('crush'), ('china'), ('fx'), ('fed'), ('tariff'),
             ('energy'), ('biofuel'), ('palm'), ('volatility'), ('substitutes')
     ) AS s(specialist)
LEFT JOIN features.sentiment_specialist_1d f 
    ON s.specialist = f.specialist
WHERE f.specialist IS NULL;

-- Should return 0 rows
```
