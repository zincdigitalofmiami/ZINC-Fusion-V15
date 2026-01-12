# ZINC-FUSION-V15: Complete Data Source Registry

**Version**: 2.0 (Big 11 Specialists)
**Stack**: Prisma PostgreSQL
**Updated**: January 2026

---

## SPECIALIST 1: CRUSH (Soybean Complex Fundamentals)
**Variance Contribution: 28-35%**

### USDA Sources
| Source | URL | Data | Frequency |
|--------|-----|------|-----------|
| NASS QuickStats API | https://quickstats.nass.usda.gov/api | Acreage, yields, production | Weekly |
| WASDE Reports | https://www.usda.gov/oce/commodity/wasde | Global supply/demand | Monthly |
| FAS Export Sales | https://apps.fas.usda.gov/esrquery/ | Weekly export sales CSV | Weekly |
| FAS GAIN API | https://apps.fas.usda.gov/newgainapi/ | Global trade intel | Daily |
| FAS Open Data | https://apps.fas.usda.gov/OpenData/ | Bulk datasets | Daily |
| Grain Stocks | https://www.usda.gov/nass/ | Inventory reports | Quarterly |

### Global Production
| Source | URL | Data | Frequency |
|--------|-----|------|-----------|
| CONAB Brazil | https://www.conab.gov.br/ultimas-noticias | Brazil crop reports | Weekly |
| CONAB Safras | https://www.conab.gov.br/info-agro/safras | Harvest progress | Weekly |
| ABIOVE Brazil | https://abiove.org.br/en/statistics/ | Brazil crush stats (PDF) | Monthly |
| Argentine BOLSA | https://www.bolsa.com.ar/ | Argentina production | Weekly |

### Processing & Spreads
| Source | URL | Data | Frequency |
|--------|-----|------|-----------|
| NOPA Crush Report | https://nopa.org/nopa-crush-report/ | Monthly crush volume (PDF) | Monthly |
| TradingEcon Soy Oil | https://tradingeconomics.com/commodity/soybean-oil | ZL price | Hourly |
| TradingEcon Soy Meal | https://tradingeconomics.com/commodity/soybean-meal | ZM price | Hourly |
| TradingEcon Soybeans | https://tradingeconomics.com/commodity/soybeans | ZS price | Hourly |

### Premium News Sources
| Source | URL | Access | Priority |
|--------|-----|--------|----------|
| Oil World | https://www.oilworld.biz | Subscription | CRITICAL |
| AgriCensus | https://www.agricensus.com | Paid API | CRITICAL |
| ProFarmer | https://www.profarmer.com | Login required | CRITICAL |
| Soybean & Corn Advisor | https://www.soybeansandcorn.com | Free scrape | HIGH |

---

## SPECIALIST 2: CHINA (Trade Flows)
**Variance Contribution: 16-22%**

### Official Chinese Sources
| Source | URL | Data | Frequency |
|--------|-----|------|-----------|
| GACC Customs | http://english.customs.gov.cn/Statics/ | Import/export data | Monthly |
| GACC Data Portal | http://43.248.49.97/ | Detailed trade flows | Monthly |
| MOFCOM | http://english.mofcom.gov.cn/ | Trade policy | Daily |
| MOFCOM Ag Trade | http://www.mofcom.gov.cn/article/tongjiziliao/ | Agricultural trade | Weekly |
| National Grain Center | http://www.grain.gov.cn/ | Grain statistics | Weekly |
| CNGOIC | http://www.cngoic.com/ | Soybean import stats | Weekly |

### China Demand (TradingEconomics)
| Source | URL | Data |
|--------|-----|------|
| China Soybean Imports | https://tradingeconomics.com/china/imports/soybeans | Volume |
| China Soy Oil Imports | https://tradingeconomics.com/china/imports/soybean-oil | Volume |

### China News & Analysis
| Source | URL | Priority |
|--------|-----|----------|
| Agrimoney China | https://www.agrimoney.com/news/china/ | CRITICAL |
| US-China Business Council | https://www.uschina.org/ | HIGH |
| Reuters China | https://www.reuters.com/world/china/ | HIGH |

---

## SPECIALIST 3: FX (Currency Competitiveness)
**Variance Contribution: 3-5%**

### FRED Exchange Rates
| Series ID | URL | Currency |
|-----------|-----|----------|
| DEXBZUS | https://fred.stlouisfed.org/series/DEXBZUS | USD/BRL (Brazil) |
| DEXCHUS | https://fred.stlouisfed.org/series/DEXCHUS | USD/CNY (China) |
| DEXARUS | https://fred.stlouisfed.org/series/DEXARUS | USD/ARS (Argentina) |
| DEXMXUS | https://fred.stlouisfed.org/series/DEXMXUS | USD/MXN (Mexico) |
| DEXUSEU | https://fred.stlouisfed.org/series/DEXUSEU | USD/EUR |
| DEXUSUK | https://fred.stlouisfed.org/series/DEXUSUK | USD/GBP |
| DEXJPUS | https://fred.stlouisfed.org/series/DEXJPUS | USD/JPY |
| DEXCAUS | https://fred.stlouisfed.org/series/DEXCAUS | USD/CAD |
| DTWEXBGS | https://fred.stlouisfed.org/series/DTWEXBGS | Trade-Weighted USD |
| DTWEXAFEGS | https://fred.stlouisfed.org/series/DTWEXAFEGS | USD vs Advanced FX |
| DTWEXEMEGS | https://fred.stlouisfed.org/series/DTWEXEMEGS | USD vs EM FX |

### Central Banks
| Source | URL | Data |
|--------|-----|------|
| ECB SDW API | https://sdw-wsrest.ecb.europa.eu/service/ | Euro rates |
| Brazil Central Bank | https://www3.bcb.gov.br/sgspub/ | BRL rates |
| PBoC | http://www.pbc.gov.cn/en/ | CNY policy |
| BCRA Argentina | http://www.bcra.gob.ar/ | ARS rates |

### Other FX Sources
| Source | URL | Data |
|--------|-----|------|
| USDA ERS FX | https://www.ers.usda.gov/data-products/agricultural-exchange-rate-data-set | Ag-weighted FX |
| TradingEcon FX | https://tradingeconomics.com/united-states/currency | Real-time |

---

## SPECIALIST 4: FED (Monetary Policy)
**Variance Contribution: 2-4%**

### FRED API Base
```
https://api.stlouisfed.org/fred/series/observations
```

### Interest Rates & Yields (14 series)
| Series ID | URL | Description |
|-----------|-----|-------------|
| DFF | https://fred.stlouisfed.org/series/DFF | Fed Funds Effective |
| FEDFUNDS | https://fred.stlouisfed.org/series/FEDFUNDS | Fed Funds Rate |
| DFEDTARU | https://fred.stlouisfed.org/series/DFEDTARU | Fed Funds Target Upper |
| DGS1MO | https://fred.stlouisfed.org/series/DGS1MO | 1-Month Treasury |
| DGS3MO | https://fred.stlouisfed.org/series/DGS3MO | 3-Month Treasury |
| DGS6MO | https://fred.stlouisfed.org/series/DGS6MO | 6-Month Treasury |
| DGS1 | https://fred.stlouisfed.org/series/DGS1 | 1-Year Treasury |
| DGS2 | https://fred.stlouisfed.org/series/DGS2 | 2-Year Treasury |
| DGS5 | https://fred.stlouisfed.org/series/DGS5 | 5-Year Treasury |
| DGS7 | https://fred.stlouisfed.org/series/DGS7 | 7-Year Treasury |
| DGS10 | https://fred.stlouisfed.org/series/DGS10 | 10-Year Treasury |
| DGS20 | https://fred.stlouisfed.org/series/DGS20 | 20-Year Treasury |
| DGS30 | https://fred.stlouisfed.org/series/DGS30 | 30-Year Treasury |
| MORTGAGE30US | https://fred.stlouisfed.org/series/MORTGAGE30US | 30-Year Mortgage |

### Yield Spreads (3 series)
| Series ID | URL | Description |
|-----------|-----|-------------|
| T10Y2Y | https://fred.stlouisfed.org/series/T10Y2Y | 10Y-2Y Spread |
| T10Y3M | https://fred.stlouisfed.org/series/T10Y3M | 10Y-3M Spread |
| TEDRATE | https://fred.stlouisfed.org/series/TEDRATE | TED Spread |

### Employment (4 series)
| Series ID | URL | Description |
|-----------|-----|-------------|
| PAYEMS | https://fred.stlouisfed.org/series/PAYEMS | Nonfarm Payrolls |
| UNRATE | https://fred.stlouisfed.org/series/UNRATE | Unemployment Rate |
| CIVPART | https://fred.stlouisfed.org/series/CIVPART | Labor Force Participation |

### Inflation (4 series)
| Series ID | URL | Description |
|-----------|-----|-------------|
| CPIAUCSL | https://fred.stlouisfed.org/series/CPIAUCSL | CPI All Urban |
| CPILFESL | https://fred.stlouisfed.org/series/CPILFESL | CPI ex-Food/Energy |
| PCEPI | https://fred.stlouisfed.org/series/PCEPI | PCE Price Index |
| PCEPILFE | https://fred.stlouisfed.org/series/PCEPILFE | Core PCE |
| GDP | https://fred.stlouisfed.org/series/GDP | Gross Domestic Product |

### Monetary Aggregates (3 series)
| Series ID | URL | Description |
|-----------|-----|-------------|
| AMBSL | https://fred.stlouisfed.org/series/AMBSL | Monetary Base |
| M1SL | https://fred.stlouisfed.org/series/M1SL | M1 Money Stock |
| M2SL | https://fred.stlouisfed.org/series/M2SL | M2 Money Stock |

### Fed Official Sources
| Source | URL | Data |
|--------|-----|------|
| Federal Reserve Board | https://www.federalreserve.gov/ | Policy statements |
| FOMC Calendar | https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm | Meeting dates |
| Fed Speeches | https://www.federalreserve.gov/newsevents/speech/ | Official remarks |
| BLS API | https://api.bls.gov/publicAPI/v2/ | Labor data |
| US Treasury API | https://api.fiscaldata.treasury.gov/services/api/v1/ | Fiscal data |

---

## SPECIALIST 5: TARIFF (Trade Policy)
**Variance Contribution: 3-5%**

### Official Government
| Source | URL | Data | Frequency |
|--------|-----|------|-----------|
| USTR Press | https://ustr.gov/about-us/policy-offices/press-office | Trade policy | Daily |
| USTR Trade Agreements | https://ustr.gov/trade-agreements/ | Active deals | Weekly |
| Federal Register API | https://www.federalregister.gov/api/v1/documents.json | Executive orders | Daily |
| Federal Register Tariffs | https://www.federalregister.gov/api/v1/documents.json?search_term=tariff | Tariff orders | Daily |
| USITC DataWeb | https://dataweb.usitc.gov/ | Trade statistics | Monthly |
| HTS Schedule | https://hts.usitc.gov/ | Tariff codes | Static |

### TradingEconomics
| Source | URL | Data |
|--------|-----|------|
| US Tariffs | https://tradingeconomics.com/united-states/tariffs | Current rates |
| US-China Balance | https://tradingeconomics.com/united-states/balance-of-trade | Trade flows |

### Trade Policy Think Tanks
| Source | URL | Focus |
|--------|-----|-------|
| PIIE Trade War Chart | https://www.piie.com/research/piie-charts/us-china-trade-war-tariffs-date-chart | Tariff timeline |
| CSIS Trade Monitor | https://www.csis.org/programs/scholl-chair-international-business/trade-war-monitor | Analysis |
| Tax Foundation Trade | https://taxfoundation.org/research/all/federal/trade/ | Economic impact |
| AEI Trade Policy | https://www.aei.org/tag/trade-policy/ | Policy analysis |

---

## SPECIALIST 6: ENERGY (Crude Oil & Energy Complex)
**Variance Contribution: 10-14%**

### EIA Sources
| Source | URL | Data | Frequency |
|--------|-----|------|-----------|
| EIA API v2 | https://api.eia.gov/v2/ | All energy data | Daily |
| EIA Open Data | https://www.eia.gov/opendata/ | Bulk downloads | Daily |
| Weekly Petroleum | https://www.eia.gov/petroleum/supply/weekly/ | Inventories | Weekly |
| WTI Spot | https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm | Crude prices | Daily |
| Natural Gas | https://www.eia.gov/dnav/ng/hist/rngwhhd.htm | NG prices | Daily |

### FRED Energy
| Series ID | URL | Description |
|-----------|-----|-------------|
| DCOILWTICO | https://fred.stlouisfed.org/series/DCOILWTICO | WTI Crude |
| DCOILBRENTEU | https://fred.stlouisfed.org/series/DCOILBRENTEU | Brent Crude |
| DHHNGSP | https://fred.stlouisfed.org/series/DHHNGSP | Natural Gas |
| GASDESW | https://fred.stlouisfed.org/series/GASDESW | Gasoline Weekly |

### TradingEconomics Energy
| Source | URL |
|--------|-----|
| Crude WTI | https://tradingeconomics.com/commodity/crude-oil |
| Brent | https://tradingeconomics.com/commodity/brent-crude-oil |
| Natural Gas | https://tradingeconomics.com/commodity/natural-gas |
| Heating Oil | https://tradingeconomics.com/commodity/heating-oil |

---

## SPECIALIST 7: BIOFUEL (Biodiesel & Renewable Fuel)
**Variance Contribution: 6-10%**

### EPA Sources
| Source | URL | Data | Priority |
|--------|-----|------|----------|
| EPA RIN Prices | https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information | D3/D4/D5/D6 RINs | CRITICAL |
| EPA RFS Program | https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rfs-program-data | RVO data | HIGH |
| EPA Main | https://www.epa.gov | Policy | Daily |

### EIA Biofuels
| Source | URL | Data |
|--------|-----|------|
| Biodiesel Production | https://www.eia.gov/biofuels/biodiesel/production/ | Monthly volume |
| Biofuels Data | https://www.eia.gov/opendata/ (biofuels category) | Historical |

### Industry Sources
| Source | URL | Data |
|--------|-----|------|
| National Biodiesel Board | https://biodiesel.org/ | Industry news |
| Renewable Fuels Assoc | https://ethanolrfa.org/ | Ethanol data |
| Clean Fuels Alliance | https://cleanfuels.org | Policy advocacy |

---

## SPECIALIST 8: PALM (Palm Oil Substitution)
**Variance Contribution: 8-12%**

### Malaysian Sources
| Source | URL | Data | Frequency |
|--------|-----|------|-----------|
| MPOB Statistics | http://bepi.mpob.gov.my/index.php/en/statistics/sectoral-status.html | Production/stocks | Monthly |
| MPOB Prices | http://bepi.mpob.gov.my/index.php/en/price/monthly-prices | CPO prices | Monthly |
| Bursa Malaysia | https://www.bursamalaysia.com/ | FCPO futures | Daily |
| Bursa Market Data | https://www.bursamalaysia.com/market_data | Historical | Daily |

### Indonesian Sources
| Source | URL | Data |
|--------|-----|------|
| Indonesia Min of Ag | https://www.pertanian.go.id/ | Production |
| GAPKI | https://gapki.id/ | Industry stats |

### TradingEconomics Palm
| Source | URL |
|--------|-----|
| FCPO Prices | https://tradingeconomics.com/commodity/palm-oil |
| Malaysia Stocks | https://tradingeconomics.com/malaysia/palm-oil-stocks |
| Malaysia Exports | https://tradingeconomics.com/malaysia/palm-oil-exports |
| Indonesia Production | https://tradingeconomics.com/indonesia/palm-oil-production |
| Indonesia Exports | https://tradingeconomics.com/indonesia/palm-oil-exports |

---

## SPECIALIST 9: VOLATILITY (Financial Stress)
**Variance Contribution: 2-3%**

### VIX Sources
| Source | URL | Data | Frequency |
|--------|-----|------|-----------|
| CBOE VIX CSV | http://www.cboe.com/publish/ScheduledTask/MktData/datahouse/vixcurrent.csv | Direct download | Daily |
| CBOE VIX Page | https://www.cboe.com/tradable_products/vix/ | Current level | Real-time |
| Yahoo VIX | https://finance.yahoo.com/quote/%5EVIX/ | Historical | Daily |

### FRED Volatility & Stress
| Series ID | URL | Description |
|-----------|-----|-------------|
| VIXCLS | https://fred.stlouisfed.org/series/VIXCLS | VIX Index |
| STLFSI4 | https://fred.stlouisfed.org/series/STLFSI4 | St. Louis Financial Stress |
| NFCI | https://fred.stlouisfed.org/series/NFCI | National Financial Conditions |
| KCFSI | https://fred.stlouisfed.org/series/KCFSI | Kansas City Financial Stress |

### Credit Spreads (FRED)
| Series ID | URL | Description |
|-----------|-----|-------------|
| BAMLH0A0HYM2 | https://fred.stlouisfed.org/series/BAMLH0A0HYM2 | High Yield OAS |
| BAMLEMNADE | https://fred.stlouisfed.org/series/BAMLEMNADE | BAA-AAA Spread |
| BAMLC0A0CM | https://fred.stlouisfed.org/series/BAMLC0A0CM | ICE BofA OAS |

---

## SPECIALIST 10: SUBSTITUTES (Vegetable Oil Competition)
**Variance Contribution: 4-6%**

### TradingEconomics Oils
| Source | URL |
|--------|-----|
| Canola | https://tradingeconomics.com/commodity/canola |
| Sunflower Oil | https://tradingeconomics.com/commodity/sunflower-oil |
| Rapeseed | https://tradingeconomics.com/commodity/rapeseed |

### USDA Sources
| Source | URL | Data |
|--------|-----|------|
| Oilseeds Circular | https://www.fas.usda.gov/data/oilseeds-world-markets-and-trade | Global production |

---

## SPECIALIST 11: TRUMP EFFECT (Political & Policy Volatility)
**Variance Contribution: 5-10% (regime-dependent)**

### Official White House
| Source | URL | Data | Frequency |
|--------|-----|------|-----------|
| Briefing Room | https://www.whitehouse.gov/briefing-room/ | Press releases | Real-time |
| Trade Page | https://www.whitehouse.gov/issues/trade/ | Trade policy | Daily |
| Press RSS | https://www.whitehouse.gov/briefing-room/statements-releases/feed/ | RSS feed | Real-time |
| Executive Orders | https://www.whitehouse.gov/presidential-actions/ | Official orders | Daily |

### Social Media
| Source | URL | Access |
|--------|-----|--------|
| Truth Social | https://truthsocial.com/@realDonaldTrump | ScrapeCreators API |

### Policy Tracking
| Source | URL | Data |
|--------|-----|------|
| Federal Register EOs | https://www.federalregister.gov/presidential-documents/executive-orders | Executive orders |
| Congress.gov Trade | https://www.congress.gov/search?q=%7B%22source%22%3A%22legislation%22%2C%22search%22%3A%22tariff%22%7D | Trade bills |

### Prediction Markets
| Source | URL | Data |
|--------|-----|------|
| Polymarket | https://polymarket.com/ | Policy probabilities |
| PredictIt | https://www.predictit.org/ | Political outcomes |
| Kalshi | https://kalshi.com/ | Regulatory outcomes |

### Policy Think Tanks
| Source | URL | Focus |
|--------|-----|-------|
| Heritage Agriculture | https://www.heritage.org/agriculture | Conservative ag policy |
| America First Policy | https://americafirstpolicy.com/ | Trump policy support |
| Politico Trade | https://www.politico.com/trade | Trade news |

---

## WEATHER DATA (Cross-Specialist)

> **STATUS: UPDATING** - Weather sources are being migrated. Check back for updated endpoints.

*Weather data updates twice daily. Source integration in progress.*

---

## NEWS & SENTIMENT

### Agricultural News (Priority Order)
| Source | URL | Priority |
|--------|-----|----------|
| Reuters Commodities | https://www.reuters.com/markets/commodities/ | P0 - CRITICAL |
| DTN Progressive Farmer | https://www.dtnpf.com/agriculture/web/ag/home | P0 - CRITICAL |
| Farm Policy News | https://farmpolicynews.illinois.edu | P0 - CRITICAL |
| FarmDoc Daily | https://farmdocdaily.illinois.edu | P0 - CRITICAL |
| Agrimoney Grains | https://www.agrimoney.com/news/grains-oilseeds/ | P1 - HIGH |
| AgWeb Soybeans | https://www.agweb.com/news/crops/soybeans | P1 - HIGH |
| Farm Progress | https://www.farmprogress.com/soybeans | P1 - HIGH |
| Agriculture.com | https://www.agriculture.com/markets-commodities | P2 - MEDIUM |
| World Grain | https://www.world-grain.com/ | P2 - MEDIUM |

### Government News
| Source | URL | Data |
|--------|-----|------|
| USDA Press | https://www.usda.gov/media/press-releases | Official releases |
| NASS Newsroom | https://www.nass.usda.gov/Newsroom/ | Data releases |
| FAS News | https://www.fas.usda.gov/newsroom/news-releases | Trade news |

---

## ANALYSTS TO FOLLOW (via ScrapeCreators)

| Analyst | Handle | Focus | Priority |
|---------|--------|-------|----------|
| Karen Braun | @kannbwx | Weather, crops, global grains | P0 |
| Arlan Suderman | @ArlanFF101 | Grain markets, policy | P0 |
| Scott Irwin | @ScottIrwinUIUC | Ag economics, biofuels | P0 |
| Dr. Michael Cordonnier | @SoybeanCorn | South America crops | P0 |
| Javier Blas | @JavierBlas | Commodities, energy | P1 |

---

## API KEYS REQUIRED

| Service | Registration URL | Cost |
|---------|------------------|------|
| FRED | https://fredaccount.stlouisfed.org/ | Free |
| data.gov (USDA) | https://api.data.gov/ | Free |
| NOAA CDO | https://www.ncdc.noaa.gov/cdo-web/token | Free |
| EIA | https://www.eia.gov/opendata/register.php | Free |
| ScrapeCreators | https://api.scrapecreators.com/ | Paid |
| TradingEconomics | https://tradingeconomics.com/api/ | Paid |
| Databento | https://api.databento.com | Paid |

---

## CFTC COT (Positioning Data)

| Source | URL | Data | Frequency |
|--------|-----|------|-----------|
| CFTC COT Reports | https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm | Fund positioning | Weekly (Tuesday) |
| CFTC Historical | https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalViewable/index.htm | Archive | Historical |

---

## MARKET DATA APIs

| Source | URL | Data |
|--------|-----|------|
| Databento | https://api.databento.com | Futures OHLCV |
| TradingEconomics | https://api.tradingeconomics.com/ | Commodities |
| Polygon.io | https://api.polygon.io | Market data |
| Yahoo Finance | https://finance.yahoo.com/ | Free prices |
| NY Fed Rates | https://markets.newyorkfed.org/api/rates/all/latest.json | Reference rates |

---

## SHIPPING & LOGISTICS

| Source | URL | Data |
|--------|-----|------|
| Panama Canal | https://www.pancanal.com/en/daily-canal-operations/ | Transit delays |
| Baltic Dry Index | https://www.investing.com/indices/baltic-dry | Freight rates |
| Freightos | https://www.freightos.com/freight-resources/freightos-baltic-index/ | Container rates |
| Marine Traffic | https://www.marinetraffic.com/en/ais/home | Vessel tracking |

---

## SCRAPING FREQUENCY SCHEDULE

```
REAL-TIME (1-2 hours):
├─ Trump social media (Specialist 11)
├─ VIX/volatility
├─ Breaking news sentiment
└─ Prediction markets

DAILY (8 AM, 12 PM, 4 PM CT):
├─ FRED economic series
├─ Treasury yields
├─ FX rates
├─ Commodity prices
└─ RIN prices

WEEKLY:
├─ CFTC COT (Tuesday)
├─ USDA Export Sales (Thursday)
├─ MPOB palm oil
└─ EIA petroleum

MONTHLY:
├─ USDA WASDE (12th)
├─ CPI/PCE inflation
├─ FOMC statements
└─ NOPA crush
```

---

## TABLE TARGETS (Prisma PostgreSQL)

```sql
raw.market_futures_1h          -- Databento hourly
raw.market_futures_1d          -- Databento daily
raw.fred_observations_1d       -- FRED series
raw.fx_spot_1d                 -- Exchange rates
raw.cftc_cot_1w                -- COT positioning
raw.epa_rin_prices_1d          -- RIN prices
raw.usda_export_sales_1w       -- Export sales
raw.usda_wasde_1m              -- WASDE reports
raw.news_articles_1d           -- Sentiment
```

---

**Total Sources**: 150+ URLs across 11 Specialists
**API Keys Required**: 7 (4 free, 3 paid)
**Update Frequency**: Real-time to Monthly

---

*Last Updated: January 2026*
*Authority: Kirk (Project Owner)*
*Total Specialists: 11 (Big 11 including Trump Effect)*
