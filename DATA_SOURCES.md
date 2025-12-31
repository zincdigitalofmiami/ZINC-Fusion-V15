# ZINC-Fusion-V15 Data Sources Registry

This document is the authoritative reference for all external data sources to be ingested.

---

## Current Status

| Status | Meaning |
|--------|---------|
| ✅ LIVE | Script exists, Prisma-ready |
| 🔄 NEEDS UPDATE | Script exists, needs DuckDB→Prisma conversion |
| ❌ TODO | Not yet implemented |

---

## 1. Financial / Economic Data

### Federal Reserve & Treasury

| Source | URL | Status | API Key |
|--------|-----|--------|---------|
| FRED Observations | `https://api.stlouisfed.org/fred/series/observations` | 🔄 `pull_all_fred.py` | `FRED_API_KEY` |
| Fed Speeches | `https://www.federalreserve.gov/newsevents/speech/` | ❌ TODO | Scrape |
| FOMC Calendar | `https://www.federalreserve.gov/monetarypolicy/fomccalendar.htm` | ❌ TODO | Scrape |
| U.S. Treasury Fiscal Data | `https://api.fiscaldata.treasury.gov/services/api/v1/` | ❌ TODO | Public |
| BLS API | `https://api.bls.gov/publicAPI/v2/` | ❌ TODO | `BLS_API_KEY` |

### International Central Banks

| Source | URL | Status | Notes |
|--------|-----|--------|-------|
| ECB API | `https://sdw-wsrest.ecb.europa.eu/service/` | ❌ TODO | Euro area data |
| Brazil Central Bank | `https://api.bcb.gov.br/sgspub/` | ❌ TODO | BRL, Selic rate |
| People's Bank of China | `https://www.pbc.gov.cn/en/` | ❌ TODO | CNY policy |

---

## 2. Market Data

### Price Data (LIVE)

| Source | URL | Status | Schedule |
|--------|-----|--------|----------|
| Polygon Futures (ZL) | `api.polygon.io` | ✅ `update_zl_price.py` | Every 15 min |
| Polygon Options + Greeks | `api.polygon.io` | ✅ `ingest_polygon_options.py` | Daily |

### Other Market APIs

| Source | URL | Status | Notes |
|--------|-----|--------|-------|
| Databento | `https://api.databento.com` | ❌ SKIPPED | User preference |
| TradingEconomics | `https://api.tradingeconomics.com/` | ❌ TODO | Paid |

---

## 3. Agricultural / USDA Data

### Government Sources

| Source | URL | Status | Notes |
|--------|-----|--------|-------|
| USDA NASS QuickStats | `https://quickstats.nass.usda.gov/api` | 🔄 `backfill_usda_data.py` | Acreage, yields |
| USDA FAS Export Sales | `https://apps.fas.usda.gov/esrquery/` | ❌ TODO | Weekly, CSV - HIGH SIGNAL |
| USDA FAS GAIN | `https://apps.fas.usda.gov/newgainapi/` | ❌ TODO | Global trade intel - HIGH |
| USDA Open Data | `https://apps.fas.usda.gov/OpenData/` | ❌ TODO | Bulk datasets |
| USDA WASDE | `https://www.usda.gov/oce/commodity/wasde` | ❌ TODO | PDF - CRITICAL |
| CFTC COT Reports | `https://www.cftc.gov/MarketReports/CommitmentsofTraders/` | ❌ TODO | Scrape - CRITICAL |

### Brazil

| Source | URL | Status | Notes |
|--------|-----|--------|-------|
| Conab | `https://www.conab.gov.br/ultimas-noticias` | ❌ TODO | Brazil crop reports - HIGH |
| ABIOVE | `https://abiove.org.br/en/statistics/` | ❌ TODO | Brazil crush - PDF scrape |

---

## 4. Energy & Biofuels

| Source | URL | Status | Notes |
|--------|-----|--------|-------|
| EIA API v2 | `https://api.eia.gov/v2/` | ❌ TODO | `EIA_API_KEY` |
| EIA Open Data | `https://www.eia.gov/opendata/` | ❌ TODO | Alternative access |
| EPA RIN Prices | `https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information` | ❌ TODO | **CRITICAL** |
| EIA Biodiesel Production | `https://www.eia.gov/biofuels/biodiesel/production/` | ❌ TODO | Production stats |

---

## 5. Weather & Climate

| Source | URL | Status | Notes |
|--------|-----|--------|-------|
| NOAA CDO | NOAA Climate Data Online | 🔄 `backfill_noaa_weather.py` | US weather |
| NOAA NOMADS/GFS | `https://nomads.ncep.noaa.gov/` | ❌ TODO | Forecast models |
| INMET (Brazil) | `https://portal.inmet.gov.br/` | ❌ TODO | Brazil weather |
| SMN (Argentina) | `https://www.smn.gob.ar/` | ❌ TODO | Argentina weather |
| Copernicus CDS | `https://cds.climate.copernicus.eu/` | ❌ TODO | Global climate |
| Meteomatics | `https://www.meteomatics.com/` | ❌ TODO | Paid API |

---

## 6. News & Media

### Already Implemented

| Source | Status | Schedule |
|--------|--------|----------|
| Yahoo Finance RSS | ✅ `ingest_news.py` | Every 4 hours |
| Polygon News | ✅ `ingest_news.py` | Every 4 hours (backup) |

### Agricultural Media (TO IMPLEMENT)

| Source | URL | Priority | Notes |
|--------|-----|----------|-------|
| Oil World | `https://www.oilworld.biz` | CRITICAL | Manual/scrape |
| NOPA | `https://www.nopa.org` | CRITICAL | Monthly crush PDF |
| AgriCensus | `https://www.agricensus.com` | HIGH | Paid API |
| Reuters Commodities | `https://www.reuters.com/markets/commodities` | HIGH | Fastest wire |
| DTN / Progressive Farmer | `https://www.dtnpf.com/agriculture/web/ag/home` | HIGH | US farm news |
| Soybean & Corn Advisor | `https://www.soybeansandcorn.com` | HIGH | Brazil/Argentina |
| FarmDoc Daily | `https://farmdocdaily.illinois.edu` | CRITICAL | Ag economics |
| Farm Policy News | `https://farmpolicynews.illinois.edu` | CRITICAL | Policy aggregator |
| AgWeb Soybeans | `https://www.agweb.com/news/crops/soybeans` | MEDIUM | US soybean news |
| Farm Progress | `https://www.farmprogress.com/soybeans` | MEDIUM | Field updates |
| Agriculture.com | `https://www.agriculture.com/markets-commodities` | MEDIUM | Markets & weather |
| Agrimoney Grains | `https://www.agrimoney.com/news/grains-oilseeds/` | HIGH | Analysis |
| Agrimoney China | `https://www.agrimoney.com/news/china/` | CRITICAL | China updates |
| World Grain | `https://www.world-grain.com/` | MEDIUM | Global grain |
| ProFarmer | `https://www.profarmer.com` | CRITICAL | Paid - premium intel |

---

## 7. Think Tanks & Policy

### Trade Policy

| Source | URL | Priority | Notes |
|--------|-----|----------|-------|
| PIIE | `https://www.piie.com` | HIGH | Trade analysis |
| CSIS Trade War Monitor | `https://www.csis.org` | HIGH | Geopolitics |
| Heritage Foundation | `https://www.heritage.org` | MEDIUM | Conservative policy |
| America First Policy Institute | `https://americafirstpolicy.com` | MEDIUM | Trump-aligned |
| Tax Foundation | `https://taxfoundation.org` | MEDIUM | Tax policy |
| AEI | `https://www.aei.org` | MEDIUM | Economic policy |

### Immigration / Labor

| Source | URL | Priority | Notes |
|--------|-----|----------|-------|
| American Immigration Council | `https://immigrationimpact.com/` | MEDIUM | Labor impact |
| Migration Policy Institute | `https://www.migrationpolicy.org/` | MEDIUM | Policy analysis |
| SPLC Immigrant Justice | `https://www.splcenter.org/issues/immigrant-justice` | MEDIUM | Advocacy |

### Farm Organizations

| Source | Notes |
|--------|-------|
| Farm Labor Organizing Committee | Labor actions |
| UFW | Farmworker union |
| Farm Bureau | Industry lobby |

---

## 8. Social Media / Analysts

**Via ScrapeCreators API** (`https://api.scrapecreators.com/`)

| Analyst | Handle | Focus |
|---------|--------|-------|
| Karen Braun | @kannbwx | Reuters commodities |
| Arlan Suderman | @ArlanFF101 | StoneX chief economist |
| Scott Irwin | @ScottIrwinUIUC | UIUC ag economics |
| Dr. Michael Cordonnier | @SoybeanCorn | South America crops |
| Javier Blas | @JavierBlas | Bloomberg commodities |

**Other Social**

| Source | URL | Notes |
|--------|-----|-------|
| Truth Social (Trump) | `https://truthsocial.com/@realDonaldTrump` | Policy signals |

---

## 9. Miscellaneous APIs

| Source | URL | Notes |
|--------|-----|-------|
| ScrapeCreators | `https://api.scrapecreators.com/` | API gateway for social |
| Glide API | `https://api.glide.app/api/v1/` | App data |
| Vegas Intel | `https://vegas.eater.com/` | ? |

---

## Environment Variables Required

```bash
# Already configured
DATABASE_URL=postgresql://...
POLYGON_API_KEY=...

# Needs adding for full coverage
FRED_API_KEY=...
NOAA_API_TOKEN=...
USDA_NASS_API_KEY=...
EIA_API_KEY=...
BLS_API_KEY=...
SCRAPECREATORS_API_KEY=...
TRADINGECONOMICS_API_KEY=...
```

---

## Priority Implementation Order

### Phase 1 - CRITICAL (Immediate)
1. ✅ Polygon prices (done)
2. ✅ Polygon options (done)
3. ✅ Yahoo/Polygon news (done)
4. 🔄 FRED → Prisma conversion
5. ❌ EPA RIN prices
6. ❌ CFTC COT reports
7. ❌ USDA FAS Export Sales

### Phase 2 - HIGH (This Week)
1. ❌ EIA biofuels
2. ❌ Conab (Brazil)
3. ❌ ABIOVE (Brazil crush)
4. ❌ FarmDoc Daily
5. ❌ Farm Policy News
6. ❌ ScrapeCreators (analyst feeds)

### Phase 3 - MEDIUM (Next Sprint)
1. ❌ International weather (INMET, SMN)
2. ❌ Central bank APIs (ECB, BCB, PBoC)
3. ❌ Think tank scrapers
4. ❌ Remaining ag media

---

## Notes

- All new scripts must write to **Prisma only** (no DuckDB)
- Each data source should have its own cron service in Railway
- Prioritize APIs over scraping where available
- For paid sources, confirm API key availability before implementation
