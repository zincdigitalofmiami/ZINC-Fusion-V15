# ZINC-FUSION-V15: SENTIMENT & AI COMPUTE LAYER ARCHITECTURE
## 🔒 LOCKED: January 7, 2026

---

## 📋 TABLE OF CONTENTS
1. [Architecture Philosophy](#architecture-philosophy)
2. [Deployment Architecture](#deployment-architecture)
3. [HuggingFace Resource Library](#huggingface-resource-library)
4. [Article Quality Pipeline](#article-quality-pipeline)
5. [BART Zero-Shot Categories](#bart-zero-shot-categories)
6. [Light Train Configuration](#light-train-configuration)
7. [AI Compute Layer](#ai-compute-layer)
8. [Database State](#database-state)

---

## 🏗️ ARCHITECTURE PHILOSOPHY

### The Shift
```
OLD: Heavy models carry ALL intelligence burden
NEW: Light models + AI agents = SMOKE
```

### Two-Tier Intelligence System

| Tier | Purpose | Components |
|------|---------|------------|
| **Tier 1: L0-L3 Heavy Models** | Trained, Backtested | Core TimeSeriesPredictor, 11 Specialists, Meta-learner, Monte Carlo |
| **Tier 2: AI Compute Agents** | On-Demand Intelligence | Sentiment scoring, Correlation analysis, Factor attribution, Scenario modeling |

---

## 🌐 DEPLOYMENT ARCHITECTURE

### CORRECT Split (Validated Jan 7, 2026)

```
┌─────────────────────────────────────────────────────────────────┐
│                        VERCEL (Frontend)                        │
│  • Next.js Dashboard (ALREADY DEPLOYED - zinc-fusion-v15)       │
│  • TradingView Charts (lightweight-charts bundled)              │
│  • API Routes (light queries)                                   │
│  • Direct Prisma connection ✅                                  │
│  • Auto-deploy, CDN, edge                                       │
│  • Pages: Dashboard, Sentiment, VegasIntel, Strategy,           │
│           Legislation                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PRISMA POSTGRESQL                            │
│  • fusion_db connected ✅                                       │
│  • 585.6k operations (7 days)                                   │
│  • 6.4M+ rows, 115+ tables                                      │
│  • Environments: Production, Preview, Development               │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────────┐
│                      LOCAL MAC (Compute)                        │
│  • Python ML training (AutoGluon)                               │
│  • Scheduled jobs (Saturday 6AM training)                       │
│  • Background workers (sentiment scoring)                       │
│  • Heavy compute jobs                                           │
│  • Runs on Mac M4 Pro                                           │
└─────────────────────────────────────────────────────────────────┘
```

### Key Insight
> Local compute for heavy ML, Vercel for frontend. Vercel is DESIGNED for Next.js + Prisma.

---

## 📚 HUGGINGFACE RESOURCE LIBRARY

### 🎯 SENTIMENT MODELS

#### Primary Financial Sentiment
| Model | Purpose | Notes |
|-------|---------|-------|
| [ArthurMrv/deberta-v3-ft-financial-news-sentiment-analysis-finetuned](https://huggingface.co/ArthurMrv/deberta-v3-ft-financial-news-sentiment-analysis-finetuned) | **Monte Carlo Fine Tuned** | ⭐ PRIMARY |
| [mrm8488/deberta-v3-ft-financial-news-sentiment-analysis](https://huggingface.co/mrm8488/deberta-v3-ft-financial-news-sentiment-analysis) | Financial news | Epochs: 5 |
| [ProsusAI/finbert](https://huggingface.co/ProsusAI/finbert) | Baseline financial NLP | 70.2M downloads, MPS accel |
| [facebook/bart-large-mnli](https://huggingface.co/facebook/bart-large-mnli) | Zero-shot classification | 3.6M downloads, relevance gate |

#### Trump/Political Analysis
| Model/Dataset | Purpose | Link |
|---------------|---------|------|
| [mradermacher/trumpgpt-GGUF](https://huggingface.co/mradermacher/trumpgpt-GGUF) | Trump policy prediction | Model |
| [yunfan-y/trump-tweets-cleaned](https://huggingface.co/datasets/yunfan-y/trump-tweets-cleaned) | **REQUIRED** - Trump sentiment training | Dataset |
| [coastalcph/populism-trump-chronos](https://huggingface.co/datasets/coastalcph/populism-trump-chronos) | Trump populism analysis | Dataset |
| [Trump datasets search](https://huggingface.co/datasets?search=trump) | Additional resources | Search |

#### Python Package
| Package | Purpose | Link |
|---------|---------|------|
| **NewsSentiment** | Target-dependent sentiment | [pypi.org/project/NewsSentiment](https://pypi.org/project/NewsSentiment/) |

---

### 📊 PRE-CLASSIFIED DATASETS

#### Financial Sentiment (Pre-labeled)
| Dataset | Purpose | Link |
|---------|---------|------|
| [ghbacct/twitter-financial-news-sentiment-classification](https://huggingface.co/datasets/ghbacct/twitter-financial-news-sentiment-classification) | Pre-classified financial sentiment | ⭐ Required |

#### 🌾 COMMODITY DATASETS (FILL THE GAPS!)

| Dataset | Purpose | Link |
|---------|---------|------|
| [paperswithbacktest/Commodities-Daily-Price](https://huggingface.co/datasets/paperswithbacktest/Commodities-Daily-Price) | **HOLY FUCK** - Daily commodity prices | ⭐⭐⭐ CRITICAL |
| [lisawen/soybean_dataset](https://huggingface.co/datasets/lisawen/soybean_dataset) | Soybean specific data | ⭐⭐ |
| [zseriz/soybeanidentification](https://huggingface.co/datasets/zseriz/soybeanidentification) | Soybean classification | Dataset |
| [zahidazmy/palmoil](https://huggingface.co/datasets/zahidazmy/palmoil) | Palm oil data | ⭐ For palm specialist |
| [Soybean datasets search](https://huggingface.co/datasets?search=soybean) | Additional resources | Search |

#### Palm Oil Space
| Resource | Purpose | Link |
|----------|---------|------|
| [faizirfan/fcpo](https://huggingface.co/spaces/faizirfan/fcpo/blob/main/index.html#L6) | FCPO (Crude Palm Oil Futures) | Space |

---

### 🔍 SEARCH QUERIES TO MINE

| Query | Purpose | Link |
|-------|---------|------|
| China Trade Models | Trade war impact | [Search](https://huggingface.co/search/full-text?q=china+trade&type=model&type=space) |
| Weather Models | Crop weather impact | [Search](https://huggingface.co/search/full-text?q=weather&type=model&type=dataset) |
| Market Shock Models | Volatility events | [Search](https://huggingface.co/search/full-text?q=market+shock&type=model&type=dataset) |

---

## 🔄 ARTICLE QUALITY PIPELINE

### Current State (Jan 7, 2026)
```
raw.news_articles_1d: 5,627 articles (mostly junk)

silver.news_scored_1d:
├── finbert-only:        5,502 articles (ALL marked relevant - wrong!)
├── finbert+ai_compute:     50 articles (86% actually relevant)
└── finbert+claude_opus:    30 articles (87% actually relevant)
```

### Target Pipeline
```
┌──────────────────────────────────────────────────────────────────┐
│                    GOLD ARTICLE PIPELINE                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  RAW (5,627 articles)                                            │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────────────┐                                     │
│  │  BART-MNLI Zero-Shot    │  ← Fast relevance gate              │
│  │  (LOCAL, no API cost)   │     facebook/bart-large-mnli        │
│  └─────────────────────────┘                                     │
│         │                                                         │
│         ├── NOT_RELEVANT → discard (~4,000 estimated)            │
│         │                                                         │
│         ▼                                                         │
│  SILVER (ZL-relevant only, ~1,500 estimated)                     │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────────────┐                                     │
│  │  DeBERTa Financial      │  ← ArthurMrv Monte Carlo tuned      │
│  │  (LOCAL, MPS accel)     │                                     │
│  └─────────────────────────┘                                     │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────────────┐                                     │
│  │  AI Scoring (Claude)    │  ← Only HIGH-SIGNAL articles        │
│  │  (In-conversation)      │    |sentiment_score| > 0.20         │
│  └─────────────────────────┘                                     │
│         │                                                         │
│         ▼                                                         │
│  GOLD (specialist training tables)                               │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🐱 BART ZERO-SHOT CATEGORIES (One Per Specialist)

```python
SPECIALIST_CATEGORIES = {
    # Category label → Specialist flag
    "soybean crushing, soybean meal, oil share, crush margins, processing": "affects_crush",
    "China demand, China imports, Chinese trade, China soybeans": "affects_china",
    "currency exchange, USD/BRL, dollar strength, forex, peso, real": "affects_fx",
    "Federal Reserve, interest rates, monetary policy, rate cuts": "affects_fed",
    "tariffs, trade war, import duties, trade policy, retaliatory": "affects_tariff",
    "crude oil, WTI, energy prices, diesel, gasoline, petroleum": "affects_energy",
    "biodiesel, renewable diesel, RFS, EPA mandate, ethanol, 45Z": "affects_biofuel",
    "palm oil, Indonesia, Malaysia, B40, B50 mandate": "affects_palm",
    "VIX, market volatility, risk sentiment, stock market crash": "affects_volatility",
    "canola oil, sunflower oil, rapeseed, vegetable oil substitutes": "affects_substitutes",
    "Trump policy, executive order, political announcement, White House": "affects_trump_effect",
    
    # REJECTION category
    "celebrity news, sports, entertainment, weather not crop-related, local crime": "NOT_RELEVANT"
}
```

---

## ⚡ LIGHT TRAIN CONFIGURATION

### Philosophy
> "With AI augmentation, we can lighten the load on models. Instead of kitchen sink, we have microwave + gummy bears + rocket."

### Config Comparison

| Parameter | HEAVY (Old) | LIGHT (New) |
|-----------|-------------|-------------|
| Validation Windows | 8 | **4** |
| Time Limit | 14,400s (4hr) | **3,600s (1hr)** |
| Feature Complexity | Kitchen sink | Microwave + essentials |
| Monte Carlo Runs | 10,000 | **10,000** ✅ KEEP |
| AI Augmentation | None | Real-time intelligence layer |

### Light Train Spec
```python
LIGHT_TRAIN_CONFIG = {
    "eval_metric": "WQL",
    "quantile_levels": [0.10, 0.50, 0.90],
    "known_covariates": [
        "day_of_week", 
        "month", 
        "is_wasde_week", 
        "is_fomc_week", 
        "is_expiry_week"
    ],
    "presets": "medium_quality",  # was high_quality
    "time_limit": 3600,           # was 14400
    "num_val_windows": 4,         # was 8
    
    # Horizons (unchanged)
    "horizons": {
        "5d": {"prediction_length": 5},
        "21d": {"prediction_length": 21},
        "63d": {"prediction_length": 63},
        "126d": {"prediction_length": 126}
    }
}
```

---

## 🤖 AI COMPUTE LAYER

### Agent Pool Framework
Location: `/src/fusion/ai_compute/agent_pool.py`

### Agent #1: SentimentScorerAgent ✅ IMPLEMENTED
- Scores news with ZL market intelligence
- Corrects FinBERT commodity-blind errors
- Routes to 11 specialists
- Outputs factor breakdowns for dashboard
- 70% AI / 30% FinBERT ensemble weighting

### Planned Agents
| Agent | Purpose | Status |
|-------|---------|--------|
| SentimentScorerAgent | News sentiment with ZL context | ✅ Done |
| CorrelationAnalyst | Compute and explain cross-specialist correlations | 🔜 Planned |
| FactorAttributor | Explain what's driving specialist signals | 🔜 Planned |
| OverlayNarrator | Generate Grok-style chart descriptions | 🔜 Planned |
| ScenarioModeler | What-if analysis for policy/weather/trade | 🔜 Planned |
| MarketIntelligenceAnalyst | Real-time web synthesis | 🔜 Planned |

### Market Intelligence Embedded
```python
MARKET_INTELLIGENCE = {
    "current_price": 50.61,  # cents/lb
    "correlations": {
        "USD/BRL": -0.65,
        "USD/ARS": -0.72,
        "USD/CNY": -0.58,
        "VIX": -0.45,
        "Fed Rates": -0.38,
        "Palm Oil": +0.68,
        "Canola": +0.62,
        "Brazil Production": -0.70
    },
    "shap_weights": {
        "biofuel_legislation": +0.12,  # #1 POSITIVE
        "south_america_supply": -0.09, # #1 NEGATIVE
        "fx_impact": -0.07,
        "vix_impact": -0.05
    }
}
```

---

## 💾 DATABASE STATE (Jan 7, 2026)

### Specialist Distribution (AI-Scored Only)
| Specialist | Count | Gap Assessment |
|------------|-------|----------------|
| crush | 45 | ✅ Strong |
| china | 16 | ✅ Good |
| biofuel | 14 | ✅ Good |
| energy | 13 | ✅ Good |
| volatility | 12 | ✅ Good |
| substitutes | 11 | ✅ Good |
| tariff | 11 | ✅ Good |
| trump_effect | 9 | ⚠️ Need more |
| palm | 2 | 🔴 CRITICAL GAP |
| fed | 1 | 🔴 CRITICAL GAP |
| fx | 1 | 🔴 CRITICAL GAP |

### Schema: silver.news_scored_1d
```sql
├── is_zl_relevant (boolean)      -- RELEVANCE GATE
├── affects_crush (boolean)        -- Specialist #1
├── affects_china (boolean)        -- Specialist #2
├── affects_fx (boolean)           -- Specialist #3
├── affects_fed (boolean)          -- Specialist #4
├── affects_tariff (boolean)       -- Specialist #5
├── affects_energy (boolean)       -- Specialist #6
├── affects_biofuel (boolean)      -- Specialist #7
├── affects_palm (boolean)         -- Specialist #8
├── affects_volatility (boolean)   -- Specialist #9
├── affects_substitutes (boolean)  -- Specialist #10
├── affects_trump_effect (boolean) -- Specialist #11
└── matched_categories (jsonb)     -- Factor breakdown jewelry
```

---

## 📅 NEXT ACTIONS

1. **BART Relevance Filter** - Clean 5,627 → ~1,500 relevant
2. **DeBERTa Financial** - Replace FinBERT with Monte Carlo tuned model
3. **Fill Dataset Gaps** - Palm, Fed, FX specialists need data
4. **Light Train Execution** - 4 windows, 3600s, get predictions
5. **Vercel API Routes** - Wire dashboard to live Prisma queries
6. **AI Agent Expansion** - CorrelationAnalyst, OverlayNarrator

---

## 🔗 RELATED DOCUMENTS
- `FINBERT_FRAMEWORK.md` - Original FinBERT implementation
- `ZINC_FUSION_V15_PREDICTOR_ARCHITECTURE_LOCKED.md` - Core model specs
- `SCHEMA_NAMING_RULES_COMPLETE_INVENTORY.md` - Database conventions

---

*Last Updated: January 7, 2026 06:00 ET*
*Author: Claude (AI Architect Assistant)*
*Architect: Kirk @ ZINC Digital of Miami*
