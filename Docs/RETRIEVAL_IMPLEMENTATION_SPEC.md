# ZINC-FUSION-V15: Complete Retrieval Implementation Specification

**For**: GPT/Codex Implementation
**Created**: 2025-01-09
**Purpose**: Fully functional retrieval layer - AI finds its own data

---

## PHILOSOPHY

> "AI is resourceful. It finds data. Python computes."

The retrieval layer must:
1. **API first** - Use official APIs when keys exist
2. **Scrape second** - Parse HTML/PDF when no API
3. **Web search fallback** - Use search when sources unavailable
4. **Cache everything** - Respect rate limits, minimize redundant calls
5. **Log receipts** - Every data point needs provenance

---

## API KEYS AVAILABLE (from consolidated .env)

```python
KEYS_AVAILABLE = {
    'FRED_API_KEY': 'dc195c8658c46ee1df83bcd4fd8a690b',      # 120 calls/min
    'EIA_API_KEY': 'I4XUi5PYnAkfMXPU3GvchRsplERC65DWri1AApqs',  # generous limits
    'NOAA_API_TOKEN': 'rxoLrCxYOlQyWvVjbBGRlMMhIRElWKZi',    # weather data
    'ANTHROPIC_API_KEY': '...',                               # AI analysis
    'OPENAI_API_KEY': '...',                                  # backup AI
    'SCRAPECREATORS_API_KEY': 'B1TOgQvMVSV6TDglqB8lJ2cirqi2', # scraping service
    'ANCHOR_API_KEY': 'sk-d22742b80f7f01b306fd39a2aac5d131',  # browser automation
}

KEYS_NEED_REGISTRATION = {
    'USDA_NASS_API_KEY': 'https://quickstats.nass.usda.gov/api',  # FREE - email registration
}

NO_KEY_NEEDED = [
    'CFTC COT',      # Public CSV downloads
    'World Bank',    # Open data
    'Yahoo Finance', # Public API
    'Federal Register', # Public API
    'CBOE VIX CSV',  # Direct download
]
```

---

## SOURCE CONFIGURATIONS BY DOMAIN

### SPECIALIST 1: CRUSH (Soybean Complex)
**Priority**: P0 - CRITICAL (28-35% variance)

```python
CRUSH_SOURCES = {
    # USDA NASS - FREE API (need to register for key)
    'usda_nass': {
        'base_url': 'https://quickstats.nass.usda.gov/api/api_GET/',
        'params': {
            'key': '{USDA_NASS_API_KEY}',
            'commodity_desc': 'SOYBEANS',
            'statisticcat_desc': ['AREA PLANTED', 'AREA HARVESTED', 'YIELD', 'PRODUCTION'],
            'format': 'JSON'
        },
        'rate_limit': 50000,  # records per request max
        'cache_hours': 24,
        'priority': 'P0'
    },

    # USDA WASDE - Scrape PDF
    'usda_wasde': {
        'url': 'https://www.usda.gov/oce/commodity/wasde',
        'method': 'scrape_pdf',
        'schedule': 'monthly_12th',
        'cache_hours': 720,  # 30 days
        'priority': 'P0'
    },

    # USDA FAS Export Sales
    'usda_fas_exports': {
        'url': 'https://apps.fas.usda.gov/esrquery/',
        'method': 'scrape_csv',
        'schedule': 'weekly_thursday',
        'cache_hours': 168,  # 7 days
        'priority': 'P0'
    },

    # USDA FAS GAIN API
    'usda_fas_gain': {
        'base_url': 'https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName',
        'method': 'api_get',
        'cache_hours': 24,
        'priority': 'P1'
    },

    # CONAB Brazil
    'conab_brazil': {
        'urls': [
            'https://www.conab.gov.br/ultimas-noticias',
            'https://www.conab.gov.br/info-agro/safras'
        ],
        'method': 'scrape_html',
        'language': 'pt-BR',
        'cache_hours': 24,
        'priority': 'P0'
    },

    # ABIOVE Brazil Crush Stats
    'abiove': {
        'url': 'https://abiove.org.br/en/statistics/',
        'method': 'scrape_pdf',
        'schedule': 'monthly',
        'cache_hours': 720,
        'priority': 'P1'
    },

    # NOPA Crush Report
    'nopa': {
        'url': 'https://nopa.org/nopa-crush-report/',
        'method': 'scrape_pdf',
        'schedule': 'monthly',
        'cache_hours': 720,
        'priority': 'P0'
    },

    # TradingEconomics - Scrape (no API key)
    'tradingeconomics_soy': {
        'urls': [
            'https://tradingeconomics.com/commodity/soybean-oil',
            'https://tradingeconomics.com/commodity/soybean-meal',
            'https://tradingeconomics.com/commodity/soybeans'
        ],
        'method': 'scrape_html',
        'cache_hours': 1,
        'priority': 'P1'
    },

    # Soybean & Corn Advisor
    'soybean_corn_advisor': {
        'url': 'https://www.soybeansandcorn.com',
        'method': 'scrape_html',
        'cache_hours': 12,
        'priority': 'P1'
    }
}
```

### SPECIALIST 2: CHINA (Trade Flows)
**Priority**: P0 - CRITICAL (16-22% variance)

```python
CHINA_SOURCES = {
    # GACC Customs - Official Chinese trade data
    'gacc_customs': {
        'urls': [
            'http://english.customs.gov.cn/Statics/',
            'http://43.248.49.97/'
        ],
        'method': 'scrape_html',
        'language': 'zh-CN',
        'cache_hours': 24,
        'priority': 'P0'
    },

    # MOFCOM
    'mofcom': {
        'urls': [
            'http://english.mofcom.gov.cn/',
            'http://www.mofcom.gov.cn/article/tongjiziliao/'
        ],
        'method': 'scrape_html',
        'cache_hours': 24,
        'priority': 'P0'
    },

    # National Grain Center
    'china_grain': {
        'url': 'http://www.grain.gov.cn/',
        'method': 'scrape_html',
        'language': 'zh-CN',
        'cache_hours': 24,
        'priority': 'P1'
    },

    # CNGOIC - China soybean imports
    'cngoic': {
        'url': 'http://www.cngoic.com/',
        'method': 'scrape_html',
        'language': 'zh-CN',
        'cache_hours': 24,
        'priority': 'P0'
    },

    # TradingEconomics China
    'tradingeconomics_china': {
        'urls': [
            'https://tradingeconomics.com/china/imports/soybeans',
            'https://tradingeconomics.com/china/imports/soybean-oil'
        ],
        'method': 'scrape_html',
        'cache_hours': 24,
        'priority': 'P1'
    },

    # News Sources
    'china_news': {
        'urls': [
            'https://www.agrimoney.com/news/china/',
            'https://www.uschina.org/',
            'https://www.reuters.com/world/china/'
        ],
        'method': 'scrape_html',
        'cache_hours': 4,
        'priority': 'P1'
    }
}
```

### SPECIALIST 3: FX (Currency Competitiveness)
**Priority**: P1 (3-5% variance)

```python
FX_SOURCES = {
    # FRED Exchange Rates - API with key
    'fred_fx': {
        'base_url': 'https://api.stlouisfed.org/fred/series/observations',
        'api_key': '{FRED_API_KEY}',
        'series': [
            'DEXBZUS',    # USD/BRL (Brazil)
            'DEXCHUS',    # USD/CNY (China)
            'DEXARUS',    # USD/ARS (Argentina)
            'DEXMXUS',    # USD/MXN (Mexico)
            'DEXUSEU',    # USD/EUR
            'DEXUSUK',    # USD/GBP
            'DEXJPUS',    # USD/JPY
            'DEXCAUS',    # USD/CAD
            'DTWEXBGS',   # Trade-Weighted USD Broad
            'DTWEXAFEGS', # USD vs Advanced FX
            'DTWEXEMEGS'  # USD vs EM FX
        ],
        'params': {'file_type': 'json'},
        'rate_limit_per_min': 120,
        'cache_hours': 24,
        'priority': 'P0'
    },

    # ECB Statistical Data Warehouse
    'ecb_sdw': {
        'base_url': 'https://sdw-wsrest.ecb.europa.eu/service/',
        'method': 'api_get',
        'cache_hours': 24,
        'priority': 'P1'
    },

    # USDA ERS Agricultural Exchange Rates
    'usda_ers_fx': {
        'url': 'https://www.ers.usda.gov/data-products/agricultural-exchange-rate-data-set',
        'method': 'scrape_csv',
        'cache_hours': 24,
        'priority': 'P1'
    }
}
```

### SPECIALIST 4: FED (Monetary Policy)
**Priority**: P1 (2-4% variance)

```python
FED_SOURCES = {
    # FRED Interest Rates & Yields - API with key
    'fred_rates': {
        'base_url': 'https://api.stlouisfed.org/fred/series/observations',
        'api_key': '{FRED_API_KEY}',
        'series': [
            # Fed Funds
            'DFF', 'FEDFUNDS', 'DFEDTARU',
            # Treasury Yields
            'DGS1MO', 'DGS3MO', 'DGS6MO', 'DGS1', 'DGS2',
            'DGS5', 'DGS7', 'DGS10', 'DGS20', 'DGS30',
            # Mortgage
            'MORTGAGE30US',
            # Yield Spreads
            'T10Y2Y', 'T10Y3M', 'TEDRATE',
            # Employment
            'PAYEMS', 'UNRATE', 'CIVPART',
            # Inflation
            'CPIAUCSL', 'CPILFESL', 'PCEPI', 'PCEPILFE', 'GDP',
            # Monetary Aggregates
            'AMBSL', 'M1SL', 'M2SL'
        ],
        'params': {'file_type': 'json'},
        'rate_limit_per_min': 120,
        'cache_hours': 24,
        'priority': 'P0'
    },

    # Federal Reserve Official
    'fed_official': {
        'urls': [
            'https://www.federalreserve.gov/',
            'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',
            'https://www.federalreserve.gov/newsevents/speech/'
        ],
        'method': 'scrape_html',
        'cache_hours': 4,
        'priority': 'P0'
    },

    # BLS API - FREE (optional key for higher limits)
    'bls_api': {
        'base_url': 'https://api.bls.gov/publicAPI/v2/timeseries/data/',
        'method': 'api_post',
        'cache_hours': 24,
        'priority': 'P1'
    },

    # Treasury Fiscal Data API - FREE no key
    'treasury_api': {
        'base_url': 'https://api.fiscaldata.treasury.gov/services/api/v1/',
        'method': 'api_get',
        'cache_hours': 24,
        'priority': 'P1'
    },

    # NY Fed Rates - FREE no key
    'nyfed_rates': {
        'url': 'https://markets.newyorkfed.org/api/rates/all/latest.json',
        'method': 'api_get',
        'cache_hours': 1,
        'priority': 'P0'
    }
}
```

### SPECIALIST 5: TARIFF (Trade Policy)
**Priority**: P1 (3-5% variance)

```python
TARIFF_SOURCES = {
    # USTR Official
    'ustr': {
        'urls': [
            'https://ustr.gov/about-us/policy-offices/press-office',
            'https://ustr.gov/trade-agreements/'
        ],
        'method': 'scrape_html',
        'cache_hours': 4,
        'priority': 'P0'
    },

    # Federal Register API - FREE no key
    'federal_register': {
        'base_url': 'https://www.federalregister.gov/api/v1/documents.json',
        'params': {
            'conditions[term]': 'tariff',
            'conditions[type][]': 'PRESDOCU',
            'per_page': 100
        },
        'method': 'api_get',
        'cache_hours': 4,
        'priority': 'P0'
    },

    # USITC DataWeb
    'usitc': {
        'url': 'https://dataweb.usitc.gov/',
        'method': 'scrape_html',
        'cache_hours': 24,
        'priority': 'P1'
    },

    # Trade Policy Think Tanks
    'trade_policy_analysis': {
        'urls': [
            'https://www.piie.com/research/piie-charts/us-china-trade-war-tariffs-date-chart',
            'https://www.csis.org/programs/scholl-chair-international-business/trade-war-monitor',
            'https://taxfoundation.org/research/all/federal/trade/',
            'https://www.aei.org/tag/trade-policy/'
        ],
        'method': 'scrape_html',
        'cache_hours': 12,
        'priority': 'P1'
    }
}
```

### SPECIALIST 6: ENERGY (Crude Oil & Energy Complex)
**Priority**: P0 - CRITICAL (10-14% variance)

```python
ENERGY_SOURCES = {
    # EIA API v2 - API with key
    'eia_api': {
        'base_url': 'https://api.eia.gov/v2/',
        'api_key': '{EIA_API_KEY}',
        'endpoints': [
            'petroleum/pri/spt/data/',      # Spot prices
            'petroleum/stoc/wstk/data/',    # Weekly stocks
            'petroleum/sum/snd/data/',      # Supply/demand
            'natural-gas/pri/fut/data/'     # NG futures
        ],
        'cache_hours': 24,
        'priority': 'P0'
    },

    # FRED Energy - API with key
    'fred_energy': {
        'base_url': 'https://api.stlouisfed.org/fred/series/observations',
        'api_key': '{FRED_API_KEY}',
        'series': [
            'DCOILWTICO',   # WTI Crude
            'DCOILBRENTEU', # Brent Crude
            'DHHNGSP',      # Natural Gas
            'GASDESW'       # Gasoline Weekly
        ],
        'cache_hours': 24,
        'priority': 'P0'
    },

    # EIA Weekly Petroleum Status
    'eia_weekly': {
        'url': 'https://www.eia.gov/petroleum/supply/weekly/',
        'method': 'scrape_html',
        'schedule': 'weekly_wednesday',
        'cache_hours': 168,
        'priority': 'P0'
    },

    # TradingEconomics Energy
    'tradingeconomics_energy': {
        'urls': [
            'https://tradingeconomics.com/commodity/crude-oil',
            'https://tradingeconomics.com/commodity/brent-crude-oil',
            'https://tradingeconomics.com/commodity/natural-gas',
            'https://tradingeconomics.com/commodity/heating-oil'
        ],
        'method': 'scrape_html',
        'cache_hours': 1,
        'priority': 'P1'
    }
}
```

### SPECIALIST 7: BIOFUEL (Biodiesel & Renewable Fuel)
**Priority**: P1 (6-10% variance)

```python
BIOFUEL_SOURCES = {
    # EPA RIN Prices - CRITICAL
    'epa_rin': {
        'url': 'https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information',
        'method': 'scrape_html',
        'cache_hours': 24,
        'priority': 'P0'
    },

    # EPA RFS Program Data
    'epa_rfs': {
        'url': 'https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rfs-program-data',
        'method': 'scrape_html',
        'cache_hours': 24,
        'priority': 'P0'
    },

    # EIA Biofuels - API with key
    'eia_biofuels': {
        'base_url': 'https://api.eia.gov/v2/',
        'api_key': '{EIA_API_KEY}',
        'endpoints': [
            'biofuels/data/'
        ],
        'cache_hours': 24,
        'priority': 'P1'
    },

    # Industry Sources
    'biofuel_industry': {
        'urls': [
            'https://biodiesel.org/',
            'https://ethanolrfa.org/',
            'https://cleanfuels.org'
        ],
        'method': 'scrape_html',
        'cache_hours': 24,
        'priority': 'P1'
    }
}
```

### SPECIALIST 8: PALM (Palm Oil Substitution)
**Priority**: P1 (8-12% variance)

```python
PALM_SOURCES = {
    # MPOB Malaysia - Official stats
    'mpob': {
        'urls': [
            'http://bepi.mpob.gov.my/index.php/en/statistics/sectoral-status.html',
            'http://bepi.mpob.gov.my/index.php/en/price/monthly-prices'
        ],
        'method': 'scrape_html',
        'cache_hours': 24,
        'priority': 'P0'
    },

    # Bursa Malaysia - FCPO futures
    'bursa_malaysia': {
        'urls': [
            'https://www.bursamalaysia.com/',
            'https://www.bursamalaysia.com/market_data'
        ],
        'method': 'scrape_html',
        'cache_hours': 4,
        'priority': 'P0'
    },

    # Indonesia Sources
    'indonesia_palm': {
        'urls': [
            'https://www.pertanian.go.id/',
            'https://gapki.id/'
        ],
        'method': 'scrape_html',
        'language': 'id',
        'cache_hours': 24,
        'priority': 'P1'
    },

    # TradingEconomics Palm
    'tradingeconomics_palm': {
        'urls': [
            'https://tradingeconomics.com/commodity/palm-oil',
            'https://tradingeconomics.com/malaysia/palm-oil-stocks',
            'https://tradingeconomics.com/malaysia/palm-oil-exports',
            'https://tradingeconomics.com/indonesia/palm-oil-production',
            'https://tradingeconomics.com/indonesia/palm-oil-exports'
        ],
        'method': 'scrape_html',
        'cache_hours': 24,
        'priority': 'P1'
    }
}
```

### SPECIALIST 9: VOLATILITY (Financial Stress)
**Priority**: P2 (2-3% variance)

```python
VOLATILITY_SOURCES = {
    # CBOE VIX - Direct CSV download (no key)
    'cboe_vix': {
        'url': 'http://www.cboe.com/publish/ScheduledTask/MktData/datahouse/vixcurrent.csv',
        'method': 'download_csv',
        'cache_hours': 1,
        'priority': 'P0'
    },

    # Yahoo Finance VIX (backup)
    'yahoo_vix': {
        'url': 'https://finance.yahoo.com/quote/%5EVIX/',
        'method': 'scrape_html',
        'cache_hours': 1,
        'priority': 'P1'
    },

    # FRED Volatility & Stress - API with key
    'fred_volatility': {
        'base_url': 'https://api.stlouisfed.org/fred/series/observations',
        'api_key': '{FRED_API_KEY}',
        'series': [
            'VIXCLS',       # VIX Index
            'STLFSI4',      # St. Louis Financial Stress
            'NFCI',         # National Financial Conditions
            'KCFSI',        # Kansas City Financial Stress
            'BAMLH0A0HYM2', # High Yield OAS
            'BAMLEMNADE',   # BAA-AAA Spread
            'BAMLC0A0CM'    # ICE BofA OAS
        ],
        'cache_hours': 24,
        'priority': 'P0'
    }
}
```

### SPECIALIST 10: SUBSTITUTES (Vegetable Oil Competition)
**Priority**: P2 (4-6% variance)

```python
SUBSTITUTES_SOURCES = {
    # TradingEconomics Oils
    'tradingeconomics_oils': {
        'urls': [
            'https://tradingeconomics.com/commodity/canola',
            'https://tradingeconomics.com/commodity/sunflower-oil',
            'https://tradingeconomics.com/commodity/rapeseed'
        ],
        'method': 'scrape_html',
        'cache_hours': 24,
        'priority': 'P1'
    },

    # USDA FAS Oilseeds Circular
    'usda_oilseeds': {
        'url': 'https://www.fas.usda.gov/data/oilseeds-world-markets-and-trade',
        'method': 'scrape_pdf',
        'schedule': 'monthly',
        'cache_hours': 720,
        'priority': 'P0'
    }
}
```

### SPECIALIST 11: TRUMP EFFECT (Political & Policy Volatility)
**Priority**: P1 (5-10% regime-dependent)

```python
TRUMP_SOURCES = {
    # White House Official
    'whitehouse': {
        'urls': [
            'https://www.whitehouse.gov/briefing-room/',
            'https://www.whitehouse.gov/issues/trade/',
            'https://www.whitehouse.gov/presidential-actions/'
        ],
        'method': 'scrape_html',
        'cache_hours': 1,
        'priority': 'P0'
    },

    # White House RSS Feed
    'whitehouse_rss': {
        'url': 'https://www.whitehouse.gov/briefing-room/statements-releases/feed/',
        'method': 'parse_rss',
        'cache_hours': 1,
        'priority': 'P0'
    },

    # Truth Social - via ScrapeCreators
    'truth_social': {
        'url': 'https://truthsocial.com/@realDonaldTrump',
        'method': 'scrapecreators_api',
        'api_key': '{SCRAPECREATORS_API_KEY}',
        'cache_hours': 0.5,  # 30 minutes
        'priority': 'P0'
    },

    # Federal Register Executive Orders
    'federal_register_eo': {
        'url': 'https://www.federalregister.gov/presidential-documents/executive-orders',
        'method': 'scrape_html',
        'cache_hours': 4,
        'priority': 'P0'
    },

    # Congress Trade Bills
    'congress_trade': {
        'url': 'https://www.congress.gov/search?q=%7B%22source%22%3A%22legislation%22%2C%22search%22%3A%22tariff%22%7D',
        'method': 'scrape_html',
        'cache_hours': 24,
        'priority': 'P1'
    },

    # Prediction Markets
    'prediction_markets': {
        'urls': [
            'https://polymarket.com/',
            'https://www.predictit.org/',
            'https://kalshi.com/'
        ],
        'method': 'scrape_html',
        'cache_hours': 1,
        'priority': 'P1'
    },

    # Policy Think Tanks
    'policy_analysis': {
        'urls': [
            'https://www.heritage.org/agriculture',
            'https://americafirstpolicy.com/',
            'https://www.politico.com/trade'
        ],
        'method': 'scrape_html',
        'cache_hours': 12,
        'priority': 'P1'
    }
}
```

---

## CROSS-DOMAIN SOURCES

### CFTC COT (Positioning Data) - NO KEY NEEDED

```python
CFTC_SOURCES = {
    'cftc_cot': {
        'urls': [
            'https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm',
            'https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalViewable/index.htm'
        ],
        'method': 'download_csv',
        'schedule': 'weekly_tuesday',
        'cache_hours': 168,
        'priority': 'P0'
    },

    # Alternative: Python library
    'cftc_library': {
        'pip': 'cot_reports',
        'method': 'python_library',
        'priority': 'P0'
    }
}
```

### NEWS & SENTIMENT

```python
NEWS_SOURCES = {
    # Priority 0 - Critical
    'news_p0': {
        'urls': [
            'https://www.reuters.com/markets/commodities/',
            'https://www.dtnpf.com/agriculture/web/ag/home',
            'https://farmpolicynews.illinois.edu',
            'https://farmdocdaily.illinois.edu'
        ],
        'method': 'scrape_html',
        'cache_hours': 2,
        'priority': 'P0'
    },

    # Priority 1 - High
    'news_p1': {
        'urls': [
            'https://www.agrimoney.com/news/grains-oilseeds/',
            'https://www.agweb.com/news/crops/soybeans',
            'https://www.farmprogress.com/soybeans'
        ],
        'method': 'scrape_html',
        'cache_hours': 4,
        'priority': 'P1'
    },

    # Priority 2 - Medium
    'news_p2': {
        'urls': [
            'https://www.agriculture.com/markets-commodities',
            'https://www.world-grain.com/'
        ],
        'method': 'scrape_html',
        'cache_hours': 12,
        'priority': 'P2'
    },

    # Government News
    'gov_news': {
        'urls': [
            'https://www.usda.gov/media/press-releases',
            'https://www.nass.usda.gov/Newsroom/',
            'https://www.fas.usda.gov/newsroom/news-releases'
        ],
        'method': 'scrape_html',
        'cache_hours': 4,
        'priority': 'P0'
    }
}
```

### SHIPPING & LOGISTICS

```python
SHIPPING_SOURCES = {
    'shipping': {
        'urls': [
            'https://www.pancanal.com/en/daily-canal-operations/',
            'https://www.investing.com/indices/baltic-dry',
            'https://www.freightos.com/freight-resources/freightos-baltic-index/'
        ],
        'method': 'scrape_html',
        'cache_hours': 24,
        'priority': 'P2'
    }
}
```

### WEATHER (NOAA) - API with key

```python
WEATHER_SOURCES = {
    'noaa': {
        'base_url': 'https://www.ncdc.noaa.gov/cdo-web/api/v2/',
        'api_key': '{NOAA_API_TOKEN}',
        'endpoints': [
            'data',
            'datasets',
            'stations'
        ],
        'cache_hours': 6,
        'priority': 'P1'
    }
}
```

---

## RATE LIMIT STRATEGY

```python
RATE_LIMITS = {
    'fred': {'calls_per_min': 120, 'daily_limit': 10000},
    'eia': {'calls_per_min': 100, 'daily_limit': None},  # generous
    'noaa': {'calls_per_min': 5, 'daily_limit': 1000},
    'scrapecreators': {'calls_per_min': 60, 'daily_limit': 10000},
    'general_scrape': {'calls_per_min': 10, 'backoff_base': 2.0},
}

BACKOFF_STRATEGY = {
    'initial_delay': 1.0,
    'max_delay': 60.0,
    'multiplier': 2.0,
    'jitter': 0.1
}
```

---

## IMPLEMENTATION REQUIREMENTS

### 1. Retrieval Function Signature

```python
async def fetch_domain_sources(
    domain: str,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Fetch all sources for a specialist domain.

    Returns:
        {
            'sources': {
                'source_name': {
                    'data': {...},
                    'fetched_at': datetime,
                    'cache_hit': bool,
                    'status': 'success' | 'failed' | 'partial'
                }
            },
            'missing_sources': ['source1', 'source2'],
            'errors': [{'source': 'x', 'error': 'msg'}]
        }
    """
```

### 2. Required Methods

```python
# API calls with key
async def api_get(url: str, params: dict, api_key: str) -> dict

# API POST (for BLS, etc)
async def api_post(url: str, payload: dict) -> dict

# HTML scraping
async def scrape_html(url: str, selectors: dict = None) -> dict

# PDF parsing
async def scrape_pdf(url: str) -> str

# CSV download
async def download_csv(url: str) -> pd.DataFrame

# RSS parsing
async def parse_rss(url: str) -> List[dict]

# ScrapeCreators API
async def scrapecreators_fetch(url: str, api_key: str) -> dict
```

### 3. Caching Layer

```python
class RetrievalCache:
    """Redis or file-based cache with TTL per source"""

    def get(self, key: str) -> Optional[dict]
    def set(self, key: str, value: dict, ttl_hours: float)
    def invalidate(self, pattern: str)
```

### 4. Error Handling

- Log all failures with full context
- Return partial data when some sources fail
- Track source reliability metrics
- Alert on critical source failures (P0 sources)

---

## SCRAPING SCHEDULE

```
REAL-TIME (30 min - 2 hours):
├─ Truth Social (TRUMP_EFFECT)
├─ VIX/volatility (VOLATILITY)
├─ Breaking news (NEWS)
├─ Prediction markets (TRUMP_EFFECT)
└─ White House briefings (TRUMP_EFFECT)

DAILY (8 AM, 12 PM, 4 PM CT):
├─ FRED economic series (FED, FX, ENERGY)
├─ Treasury yields (FED)
├─ FX rates (FX)
├─ Commodity prices (ALL)
├─ RIN prices (BIOFUEL)
└─ EIA data (ENERGY)

WEEKLY:
├─ CFTC COT - Tuesday (POSITIONING)
├─ USDA Export Sales - Thursday (CRUSH)
├─ MPOB palm oil (PALM)
├─ EIA petroleum - Wednesday (ENERGY)
└─ CONAB Brazil (CRUSH)

MONTHLY:
├─ USDA WASDE - 12th (CRUSH)
├─ CPI/PCE inflation (FED)
├─ FOMC statements (FED)
├─ NOPA crush report (CRUSH)
├─ ABIOVE stats (CRUSH)
└─ USDA Oilseeds Circular (SUBSTITUTES)
```

---

## PRIORITY ORDER FOR IMPLEMENTATION

1. **P0 CRITICAL - Implement First**
   - FRED API (covers FED, FX, ENERGY, VOLATILITY)
   - EIA API (ENERGY, BIOFUEL)
   - CBOE VIX CSV download (VOLATILITY)
   - Federal Register API (TARIFF, TRUMP_EFFECT)
   - CFTC COT download (POSITIONING)

2. **P1 HIGH - Implement Second**
   - TradingEconomics scraping (ALL domains)
   - News scraping (Reuters, DTN, FarmDoc)
   - USDA WASDE PDF parsing (CRUSH)
   - Truth Social via ScrapeCreators (TRUMP_EFFECT)
   - MPOB scraping (PALM)

3. **P2 MEDIUM - Implement Third**
   - China sources (GACC, MOFCOM) - complex
   - Brazil sources (CONAB, ABIOVE) - Portuguese
   - Industry sources (NOPA, Biodiesel.org)
   - Shipping/logistics

---

## TESTING CHECKLIST

- [ ] FRED API returns data for all 40+ series
- [ ] EIA API returns petroleum and biofuel data
- [ ] NOAA API returns weather data
- [ ] VIX CSV downloads and parses correctly
- [ ] Federal Register API filters tariff documents
- [ ] CFTC COT CSV downloads and parses
- [ ] TradingEconomics scraping works without blocking
- [ ] News sources return recent articles
- [ ] Cache correctly stores and retrieves data
- [ ] Rate limiting prevents 429 errors
- [ ] Error handling logs failures without crashing

---

*Last Updated: 2025-01-09*
*For: GPT/Codex Implementation*
