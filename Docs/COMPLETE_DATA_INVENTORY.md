# ZINC-FUSION-V15: Complete Data Inventory

> Generated: January 2026
> Purpose: Comprehensive reference for all training data, features, and sources

---

## Table of Contents

1. [Symbols & Tickers](#1-symbols--tickers)
2. [Technical Indicators (Elite 27)](#2-technical-indicators-elite-27)
3. [Core Training Features (~1,384)](#3-core-training-features-1384)
4. [FRED Economic Series (111)](#4-fred-economic-series-111)
5. [Weather Data (NOAA)](#5-weather-data-noaa)
6. [CFTC COT Positioning](#6-cftc-cot-positioning)
7. [USDA Agricultural Data](#7-usda-agricultural-data)
8. [EPA RIN Prices](#8-epa-rin-prices)
9. [News Sources (46)](#9-news-sources-46)
10. [Specialist Buckets (Big-11)](#10-specialist-buckets-big-11)
11. [Database Tables](#11-database-tables)
12. [Forecast Horizons & Models](#12-forecast-horizons--models)
13. [Summary Statistics](#13-summary-statistics)

---

## 1. Symbols & Tickers

### Primary Target
| Symbol | Description |
|--------|-------------|
| **ZL** | Soybean Oil Futures (PRIMARY TARGET) |

### Soy Complex (4)
| Symbol | Description |
|--------|-------------|
| ZS | Soybeans |
| ZM | Soybean Meal |
| ZC | Corn |
| ZW | Wheat |

### Energy Complex (5)
| Symbol | Description |
|--------|-------------|
| CL | Crude Oil (WTI) |
| HO | Heating Oil |
| RB | RBOB Gasoline |
| NG | Natural Gas (Henry Hub) |
| CPO/FCPO | Crude Palm Oil (Malaysia) |

### Macro/Equity Proxies (3)
| Symbol | Description |
|--------|-------------|
| ES | S&P 500 E-mini |
| GC | Gold |
| BTC | Bitcoin |

### Equity/ETF Proxies (3)
| Symbol | Description |
|--------|-------------|
| DJT | Trump Media (market-implied regime proxy) |
| FXI | iShares China Large-Cap ETF |
| KWEB | KraneShares China Internet ETF |

### FX Pairs (11)
- USD/BRL, USD/CNY, USD/ARS, USD/MXN, USD/EUR
- USD/JPY, USD/GBP, USD/CAD, USD/INR, USD/KRW
- DXY (Dollar Index), Trade-Weighted USD

### Substitute Oils (5)
| Commodity | Description |
|-----------|-------------|
| Canola | Canadian canola oil |
| Rapeseed | European rapeseed oil |
| Sunflower | Sunflower oil |
| UCO | Used Cooking Oil |
| Tallow | Animal fat |

**Total Symbols: 34+**

---

## 2. Technical Indicators (Elite 27)

### TIER 1: Institutional Gems (8)

| # | Indicator | Purpose | Levels |
|---|-----------|---------|--------|
| 1 | `hurst_exponent` | Regime detection | >0.5 trending, <0.5 mean-reverting |
| 2 | `connors_rsi` | 3-component RSI (price + streak + percentile) | <10 oversold, >90 overbought |
| 3 | `fisher_transform` | Normalized price to Gaussian | <-1.5 oversold, >1.5 overbought |
| 4 | `mcginley_dynamic` | Self-adjusting MA (solves lag) | Price crossovers |
| 5 | `ttm_squeeze_on` | BB inside Keltner = low vol | 1 = squeeze active |
| 6 | `schaff_trend_cycle` | MACD through double Stochastic | <25 bullish, >75 bearish |
| 7 | `rvi` | Relative Vigor Index | Signal line crossovers |
| 8 | `elder_force_index` | Price change × Volume | Zero-line crossovers |

### TIER 2: Optimized Staples (14)

#### Horizon-Matched Moving Averages
| Indicator | Horizon | Description |
|-----------|---------|-------------|
| `kama_10` | 5d | Kaufman Adaptive MA |
| `hma_20` | 21d | Hull MA (zero-lag) |
| `alma_50` | 63d | Arnaud Legoux MA (smoothest) |
| `mcginley_100` | 126d | "Systemic Floor" |

#### Price Deviations (Stationarized)
- `price_vs_kama10_pct`
- `price_vs_hma20_pct`
- `price_vs_alma50_pct`
- `price_vs_mcg100_pct`

#### RSI Variants
| Indicator | Purpose |
|-----------|---------|
| `rsi_2` | Mean-reversion (Connors style) |
| `rsi_14` | Standard momentum |
| `cumulative_rsi` | Sum of last 3 RSI(2) |

#### MACD Variants
| Indicator | Settings | Purpose |
|-----------|----------|---------|
| `macd`, `macd_signal`, `macd_histogram` | (12,26,9) | Standard |
| `macd_fast`, `macd_fast_signal`, `macd_fast_histogram` | (5,13,4) | Short-term |

#### CCI Variants
| Indicator | Purpose |
|-----------|---------|
| `cci_14` | Short-term commodity channel |
| `cci_50` | Longer-term regime |

### TIER 3: Volatility Regime (5)

| Indicator | Purpose |
|-----------|---------|
| `atr_ratio` | ATR(10)/ATR(50) - expanding vs contracting |
| `garman_klass_vol` | OHLC-based volatility (more efficient than HV) |
| `yang_zhang_vol` | Handles overnight gaps (futures-specific) |
| `bb_percent_b` | Position within Bollinger Bands (0-1) |
| `hurst_regime` | Classification: mean_reverting / random / trending |

### TIER 4: Volume/Flow (3)

| Indicator | Purpose |
|-----------|---------|
| `cmf_21` | Chaikin Money Flow (accumulation/distribution) |
| `volume_zscore` | Standardized volume (20-period) |
| `unusual_volume` | Flag when >2 std deviation |

**Total Elite Indicators: 27 (yielding ~45 columns with signals)**

---

## 3. Core Training Features (~1,384)

### 3.1 Market Symbols OHLCV (~420 features)

84 symbols × 5 columns = 420 features

Format: `{SYMBOL}_{ohlcv}`
- `ZL_open`, `ZL_high`, `ZL_low`, `ZL_close`, `ZL_volume`
- `ZS_open`, `ZS_high`, `ZS_low`, `ZS_close`, `ZS_volume`
- ... (all 84 symbols)

### 3.2 Volatility Proxy Features (42 features)

For 7 key symbols (ZL, ZS, ZM, CL, CPO, ES, GC):

| Feature | Description |
|---------|-------------|
| `{SYM}_intraday_range` | High - Low |
| `{SYM}_intraday_range_pct` | (High - Low) / Close × 100 |
| `{SYM}_gap` | Open - Previous Close |
| `{SYM}_gap_pct` | Gap as percentage |
| `{SYM}_wick_ratio` | (H-L) / abs(C-O) |
| `{SYM}_garman_klass` | Garman-Klass OHLC volatility |

### 3.3 FRED Economic (111 features)

See [Section 4](#4-fred-economic-series-111) for complete list.

### 3.4 Weather (~570 features)

57 NOAA stations × 10 variables = 570 features

Format: `weather_{variable}_{station_id}`

### 3.5 CFTC COT (~210 features)

30+ contracts × 7 metrics = 210+ features

Format: `cot_{metric}_{symbol}`

### 3.6 FX Spot (11 features)

Format: `fx_{pair}`

### 3.7 USDA Exports (5 features)

- `usda_soy_net_sales`
- `usda_soy_exports`
- `usda_zl_net_sales`
- `usda_zl_exports`
- `usda_zm_net_sales`

### 3.8 USDA WASDE (5 features)

- `wasde_soy_production`
- `wasde_soy_exports`
- `wasde_soy_stocks`
- `wasde_zl_production`
- `wasde_zl_exports`

### 3.9 EPA RINs (4 features)

- `rin_D3`, `rin_D4`, `rin_D5`, `rin_D6`

### 3.10 News Sentiment (6 features)

- `news_sentiment_mean`
- `news_sentiment_std`
- `news_article_count`
- `news_bullish_count`
- `news_bearish_count`
- `news_trump_count`

---

## 4. FRED Economic Series (111)

### Daily Series (46)

#### Interest Rates & Yields (25)
| Series | Description |
|--------|-------------|
| DGS1MO, DGS3MO, DGS6MO | Treasury yields (1M, 3M, 6M) |
| DGS1, DGS2, DGS5, DGS7, DGS10, DGS20, DGS30 | Treasury yields |
| DFII5, DFII7, DFII10, DFII20, DFII30 | TIPS spreads |
| T10Y2Y | 10Y-2Y yield spread |
| T10Y3M | 10Y-3M yield spread |
| T10YIE | 10Y breakeven inflation |
| TEDRATE | TED spread |
| DFF | Fed Funds effective rate |
| DPRIME | Prime rate |
| SOFR | Secured Overnight Financing Rate |
| DFEDTARL, DFEDTARU | Fed target rate bounds |
| DTB3, DTB6 | T-Bill rates |

#### Credit Spreads (4)
| Series | Description |
|--------|-------------|
| DAAA | Moody's AAA corporate yield |
| DBAA | Moody's BAA corporate yield |
| BAMLH0A0HYM2 | BofA High Yield OAS |
| BAMLC0A0CM | BofA Corporate Master OAS |

#### FX Rates (18)
| Series | Description |
|--------|-------------|
| DEXCHUS | USD/CNY |
| DEXUSEU | USD/EUR |
| DEXJPUS | USD/JPY |
| DEXUSUK | USD/GBP |
| DEXCAUS | USD/CAD |
| DEXMXUS | USD/MXN |
| DEXBZUS | USD/BRL |
| DEXINUS | USD/INR |
| DEXMAUS | USD/MYR |
| DEXKOUS | USD/KRW |
| DEXSIUS | USD/SGD |
| DEXTHUS | USD/THB |
| DEXHKUS | USD/HKD |
| DEXSZUS | USD/CHF |
| DEXSFUS | USD/ZAR |
| DEXTAUS | USD/TWD |
| DEXUSAL | USD/AUD |
| DEXNOUS | USD/NOK |

#### Dollar Indices (4)
| Series | Description |
|--------|-------------|
| DTWEXBGS | Trade-Weighted USD (Broad) |
| DTWEXAFEGS | Trade-Weighted USD (Advanced) |
| DTWEXEMEGS | Trade-Weighted USD (Emerging) |
| DTWEXM | Trade-Weighted USD (Major) |

#### Energy Prices (4)
| Series | Description |
|--------|-------------|
| DCOILWTICO | WTI Crude Oil |
| DCOILBRENTEU | Brent Crude Oil |
| DHHNGSP | Henry Hub Natural Gas |
| DHOILNYH | NY Harbor Heating Oil |

#### Volatility & Equity (2)
| Series | Description |
|--------|-------------|
| VIXCLS | CBOE VIX |
| NASDAQCOM | NASDAQ Composite |

#### Policy Uncertainty (1)
| Series | Description |
|--------|-------------|
| USEPUINDXD | US Economic Policy Uncertainty (Daily) |

### Weekly Series (14)

| Series | Description |
|--------|-------------|
| GASREGW | Regular gasoline price |
| GASDESW | Diesel price |
| ICSA | Initial jobless claims |
| CCSA | Continued claims |
| NFCI | Chicago Fed National Financial Conditions |
| STLFSI | St. Louis Fed Financial Stress Index |
| STLFSI4 | STLFSI (4-week) |
| WALCL | Fed total assets |
| WRESBAL | Reserve balances |
| MORTGAGE30US | 30-year mortgage rate |
| RRPONTSYD | Overnight repo rate |
| DDFUELUSGULF | Gulf Coast diesel |
| SP500 | S&P 500 Index |
| SP500_HISTORICAL | S&P 500 (historical) |

### Monthly Series (67)

#### CPI / Inflation (6)
| Series | Description |
|--------|-------------|
| CPIAUCSL | CPI All Urban |
| CPILFESL | Core CPI (less food & energy) |
| PCEPI | PCE Price Index |
| PCEPILFE | Core PCE |
| PCE | Personal Consumption Expenditures |
| CHNCPIALLMINMEI | China CPI |

#### PPI / Producer Prices (10)
| Series | Description |
|--------|-------------|
| PPIACO | PPI All Commodities |
| WPSFD49207 | PPI Farm Products |
| WPSFD49502 | PPI Processed Foods |
| WPUFD49116 | PPI Foods |
| WPUFD49207 | PPI Farm Products (alt) |
| WPUSI012011 | PPI Fats & Oils |
| WPU06140341 | PPI Soybean Oil |
| WPU01830171 | PPI Soybeans |
| WPU057303 | PPI Fuel |
| PCU311224311224 | Soybean Oil Processing PPI |

#### Consumer Prices Specific (6)
| Series | Description |
|--------|-------------|
| APU000074714 | Fats & Oils CPI |
| CUSR0000SAF11 | Food at home CPI |
| CUSR0000SETA01 | New vehicles CPI |
| CUSR0000SETA02 | Used vehicles CPI |
| CUSR0000SETB01 | Motor fuel CPI |
| CUSR0000SAH1 | Shelter CPI |

#### Employment (6)
| Series | Description |
|--------|-------------|
| UNRATE | Unemployment rate |
| PAYEMS | Nonfarm payrolls |
| MANEMP | Manufacturing employment |
| AWHMAN | Avg weekly hours manufacturing |
| CES0500000003 | Avg hourly earnings |
| JTSJOL | Job openings (JOLTS) |

#### Money Supply / Fed (5)
| Series | Description |
|--------|-------------|
| M2SL | M2 Money Stock |
| TOTRESNS | Total reserves |
| BOGMBASE | Monetary base |
| FEDFUNDS | Fed Funds rate |
| BUSLOANS | Commercial & industrial loans |

#### Industrial / Manufacturing (3)
| Series | Description |
|--------|-------------|
| INDPRO | Industrial production |
| DGORDER | Durable goods orders |
| NEWORDER | Manufacturers' new orders |

#### Consumer (6)
| Series | Description |
|--------|-------------|
| RSAFS | Retail sales |
| RSXFS | Retail sales ex autos |
| DSPIC96 | Real disposable income |
| UMCSENT | U of Michigan Consumer Sentiment |
| MICH | Michigan Inflation Expectations |
| PSAVERT | Personal saving rate |

#### Housing (3)
| Series | Description |
|--------|-------------|
| HOUST | Housing starts |
| PERMIT | Building permits |
| CSUSHPISA | Case-Shiller Home Price Index |

#### Trade (3)
| Series | Description |
|--------|-------------|
| BOPGSTB | Trade balance (goods & services) |
| BOPGTB | Trade balance (goods) |
| IEABC | Current account balance |

#### China-Specific (5)
| Series | Description |
|--------|-------------|
| CHNMAINLANDTPU | China Trade Policy Uncertainty |
| MYAGM2CNM189N | China M2 |
| IMPCH | US Imports from China |
| XTEXVA01CNM667S | China Exports |
| XTIMVA01CNM667S | China Imports |

#### IMF Commodity Prices (10)
| Series | Description |
|--------|-------------|
| PSOILUSDM | Soybean Oil (USD) - **DIRECT ZL INDICATOR** |
| PSOYBUSDM | Soybeans (USD) |
| PPOILUSDM | Palm Oil (USD) |
| PROILUSDM | Rapeseed Oil (USD) |
| PSUNOUSDM | Sunflower Oil (USD) |
| PCOPPUSDM | Copper (USD) |
| PMAIZMTUSDM | Maize (USD) |
| PWHEAMTUSDM | Wheat (USD) |
| PRICENPQUSDM | Rice (USD) |
| PNGASEUUSDM | Natural Gas EU (USD) |

#### Policy Uncertainty (3)
| Series | Description |
|--------|-------------|
| USEPUINDXM | US Economic Policy Uncertainty (Monthly) |
| EMVTRADEPOLEMV | Equity Market Trade Policy Volatility |
| EPUTRADE | Trade Policy Uncertainty |

#### Oil Volatility (1)
| Series | Description |
|--------|-------------|
| OVXCLS | CBOE Oil Volatility Index |

### Quarterly Series (10)

| Series | Description |
|--------|-------------|
| GDPC1 | Real GDP |
| GDP | Nominal GDP |
| DRCCLACBS | Consumer Loan Delinquency Rate |
| B235RC1Q027SBEA | Farm Income |
| CHNGDPNQDSMEI | China GDP |
| EXPGS | Exports of Goods & Services |
| IMPGS | Imports of Goods & Services |
| WPU01830161 | Farm Products PPI |
| IR3TIB01CNM156N | China 3-Month Interbank Rate |
| PPIFGS | PPI Finished Goods |

---

## 5. Weather Data (NOAA)

### Source
- **Provider:** NOAA Climate Data Online (CDO)
- **Frequency:** Daily (updated 2x/day)
- **Table:** `weather_noaa_1d`

### Variables (10)
| Variable | Unit | Description |
|----------|------|-------------|
| temp_avg | °F | Average temperature |
| temp_min | °F | Minimum temperature |
| temp_max | °F | Maximum temperature |
| precip | mm | Precipitation |
| humidity | % | Relative humidity |
| wind_avg | mph | Average wind speed |
| wind_gust | mph | Peak wind gust |
| snow_depth | mm | Snow depth |
| evaporation | mm | Evaporation |
| soil_moisture | % | Soil moisture content |

### Coverage
- **Primary:** US soybean/corn belt (Midwest)
- **Secondary:** Brazil, Argentina, global ag zones
- **Stations:** ~57 stations tracked
- **Features:** ~570 (57 stations × 10 variables)

### Feature Format
```
weather_{variable}_{station_id}
```
Example: `weather_temp_avg_USW00014820`

---

## 6. CFTC COT Positioning

### Source
- **Provider:** CFTC Commitments of Traders Report
- **Frequency:** Weekly (Tuesday data, Friday release)
- **Table:** `cftc_cot_1w`

### Contracts Tracked (30+)
| Symbol | Description |
|--------|-------------|
| ZL | Soybean Oil |
| ZS | Soybeans |
| ZM | Soybean Meal |
| ZC | Corn |
| ZW | Wheat |
| CL | Crude Oil (WTI) |
| HO | Heating Oil |
| RB | RBOB Gasoline |
| NG | Natural Gas |
| GC | Gold |
| SI | Silver |
| HG | Copper |
| ... | + 18 more contracts |

### Metrics Per Contract (7)
| Metric | Description |
|--------|-------------|
| `commercial_long` | Commercial hedger long positions |
| `commercial_short` | Commercial hedger short positions |
| `noncommercial_long` | Speculator (fund) long positions |
| `noncommercial_short` | Speculator (fund) short positions |
| `open_interest` | Total open interest |
| `net_commercial` | Commercial net (long - short) |
| `net_noncommercial` | Speculator net (long - short) |

### Feature Format
```
cot_{metric}_{symbol}
```
Example: `cot_net_commercial_ZL`, `cot_open_interest_CL`

### Total Features
~210 (30 contracts × 7 metrics)

---

## 7. USDA Agricultural Data

### Export Sales (Weekly)
| Feature | Description |
|---------|-------------|
| `usda_soy_net_sales` | Weekly soybean net sales (MT) |
| `usda_soy_exports` | Weekly soybean exports (MT) |
| `usda_zl_net_sales` | Soybean oil net sales (MT) |
| `usda_zl_exports` | Soybean oil exports (MT) |
| `usda_zm_net_sales` | Soybean meal net sales (MT) |

**Source:** USDA FAS Export Sales Reporting
**Frequency:** Weekly (Thursday release)
**Table:** `usda_export_sales_1w`

### WASDE Reports (Monthly)
| Feature | Description |
|---------|-------------|
| `wasde_soy_production` | Global soybean production forecast (MMT) |
| `wasde_soy_exports` | Global soybean exports forecast (MMT) |
| `wasde_soy_stocks` | Ending stocks forecast (MMT) |
| `wasde_zl_production` | Soybean oil production (1000 MT) |
| `wasde_zl_exports` | Soybean oil exports (1000 MT) |

**Source:** USDA World Agricultural Supply and Demand Estimates
**Frequency:** Monthly (around 12th)
**Table:** `usda_wasde_1m`

---

## 8. EPA RIN Prices

### Source
- **Provider:** EPA Renewable Fuel Standard Program
- **Frequency:** Daily
- **Table:** `epa_rin_prices_1d`

### RIN Types (4)
| Feature | RIN Type | Description |
|---------|----------|-------------|
| `rin_D3` | D3 | Cellulosic biofuel |
| `rin_D4` | D4 | Biomass-based diesel (BBD) - **KEY FOR ZL** |
| `rin_D5` | D5 | Advanced biofuel |
| `rin_D6` | D6 | Renewable fuel (corn ethanol) |

**Note:** D4 RINs are most relevant for soybean oil demand (biodiesel feedstock).

---

## 9. News Sources (46)

### By Specialist Bucket

#### Crush (11 sources)
| Priority | Source | Type |
|----------|--------|------|
| P0 | Farm Policy News | RSS |
| P0 | FarmDoc Daily | RSS |
| P0 | Reuters Commodities | RSS |
| P0 | USDA Press Releases | RSS |
| P0 | DTN Progressive Farmer | Scrape |
| P0 | Soybean & Corn Advisor | Scrape |
| P1 | Agrimoney Grains | RSS |
| P1 | AgWeb Soybeans | RSS |
| P1 | Farm Progress | RSS |
| P2 | Agriculture.com | RSS |
| P2 | World Grain | RSS |

#### China (3 sources)
| Priority | Source | Type |
|----------|--------|------|
| P1 | Reuters China | RSS |
| P1 | Agrimoney China | Scrape |
| P2 | MOFCOM Trade News | Scrape |

#### FX (1 source)
| Priority | Source | Type |
|----------|--------|------|
| P2 | ECB Press Releases | Scrape |

#### Fed (2 sources)
| Priority | Source | Type |
|----------|--------|------|
| P1 | Federal Reserve News | RSS |
| P2 | Federal Reserve Speeches | Scrape |

#### Tariff (3 sources)
| Priority | Source | Type |
|----------|--------|------|
| P1 | White House Briefing | RSS |
| P1 | USTR Press | Scrape |
| P2 | Federal Register Tariffs | API |

#### Energy (2 sources)
| Priority | Source | Type |
|----------|--------|------|
| P1 | EIA Today in Energy | RSS |
| P2 | EIA Petroleum News | RSS |

#### Biofuel (2 sources)
| Priority | Source | Type |
|----------|--------|------|
| P1 | EPA News Releases | RSS |
| P2 | Biodiesel Magazine | RSS |

#### Palm (5 sources)
| Priority | Source | Type |
|----------|--------|------|
| P1 | MPOB Malaysia | Scrape |
| P1 | GAPKI Indonesia | Scrape |
| P2 | Palm Oil Today | Scrape |
| P2 | RSPO News | Scrape |
| P2 | TradingEcon Palm Oil | Scrape |

#### Volatility (1 source)
| Priority | Source | Type |
|----------|--------|------|
| P2 | CBOE Insights | Scrape |

#### Substitutes (7 sources)
| Priority | Source | Type |
|----------|--------|------|
| P1 | Canola Council News | Scrape |
| P1 | Oilseed & Grain News | Scrape |
| P2 | National Sunflower Association | Scrape |
| P2 | ICE Canola Futures | Scrape |
| P2 | TradingEcon Canola | Scrape |
| P2 | TradingEcon Sunflower Oil | Scrape |
| P2 | TradingEcon Rapeseed | Scrape |

#### Trump Effect (4 sources)
| Priority | Source | Type |
|----------|--------|------|
| P1 | White House Executive Orders | Scrape |
| P1 | Federal Register Executive Orders | API |
| P1 | Truth Social Trump | ScrapeCreators API |
| P2 | Politico Trade | Scrape |

### Priority Levels
- **P0 (Critical):** Every 2 hours during market hours
- **P1 (High):** Every 4 hours
- **P2 (Medium):** Every 6 hours or daily

### Analyst Twitter Follows (5)
| Handle | Name | Specialist |
|--------|------|------------|
| @kannbwx | Karen Braun | crush |
| @ArlanFF101 | Arlan Suderman | crush |
| @ScottIrwinUIUC | Scott Irwin | biofuel |
| @SoybeanCorn | Dr. Michael Cordonnier | crush |
| @JavierBlas | Javier Blas | energy |

---

## 10. Specialist Buckets (Big-11)

### Economic Drivers (11)

| # | Bucket | Key Features | Primary Sources |
|---|--------|--------------|-----------------|
| 1 | `crush` | Board crush, oil share, NOPA | USDA, CFTC, News |
| 2 | `china` | Soy imports, Dalian prices | MOFCOM, FAS |
| 3 | `fx` | USD/BRL, USD/CNY | FRED FX |
| 4 | `fed` | Fed funds, yield curve | FRED rates |
| 5 | `tariff` | Trade policy, USTR | Federal Register |
| 6 | `energy` | WTI, crack spreads | EIA, FRED |
| 7 | `biofuel` | RIN prices, RFS mandates | EPA |
| 8 | `palm` | CPO, Malaysia/Indonesia | MPOB, GAPKI |
| 9 | `volatility` | VIX, financial stress | CBOE, FRED |
| 10 | `substitutes` | Canola, sunflower, rapeseed | TradingEconomics |
| 11 | `trump_effect` | EPU indices, tariff threats | White House, Fed Reg |

> **⚠️ Specialist weights are learned by the L1 meta-ensemble, not predetermined.**

### Neural Drivers (5)

| # | Bucket | Description |
|---|--------|-------------|
| 1 | `neural_trend` | Learned price trend & momentum |
| 2 | `neural_regime` | Latent market regime classification |
| 3 | `neural_flow` | Multi-asset flow pressure |
| 4 | `neural_sentiment` | News + narrative tone |
| 5 | `neural_residual` | Unexplained pressure (alpha) |

---

## 11. Database Tables

### Raw Ingestion (`raw` schema)

| Table | Frequency | Description |
|-------|-----------|-------------|
| `market_futures_1h` | Hourly | OHLCV futures data |
| `market_futures_1d` | Daily | OHLCV futures data |
| `fred_observations_1d` | Daily | FRED time series |
| `fx_spot_1d` | Daily | FX spot rates |
| `weather_noaa_1d` | Daily | NOAA weather data |
| `cftc_cot_1w` | Weekly | COT positioning |
| `epa_rin_prices_1d` | Daily | EPA RIN prices |
| `usda_export_sales_1w` | Weekly | USDA export sales |
| `usda_wasde_1m` | Monthly | USDA WASDE reports |
| `news_articles_1d` | Daily | News articles |

### Feature/Training Tables

| Table | Description |
|-------|-------------|
| `specialist_features` | Per-specialist engineered features |
| `core_features` | Core/meta features |
| `oof_predictions` | Out-of-fold quantile predictions |
| `forecast_quantiles` | p10, p50, p90 forecasts |
| `driver_scores` | Per-specialist attribution |
| `lasso_coefficients` | Feature importance (sparse) |

### Analysis/Risk Tables

| Table | Description |
|-------|-------------|
| `risk_metrics` | VaR, CVaR, tail risk |
| `monte_carlo_runs` | MC simulation outputs |
| `garch_forecasts` | Conditional volatility |
| `regime_probabilities` | Regime detection |
| `shap_values` | Per-sample attributions |

**Total Tables: 60+**

---

## 12. Forecast Horizons & Models

### Horizons

| Horizon | Trading Days | Description | Use Case |
|---------|--------------|-------------|----------|
| 5d | 5 | 1 Week | Short-term tactical |
| 21d | 21 | 1 Month | Monthly planning |
| 63d | 63 | 3 Months | Quarterly strategy |
| 126d | 126 | 6 Months | Long-term procurement |

### Models by Horizon

| Model | 5d | 21d | 63d | 126d |
|-------|:--:|:---:|:---:|:----:|
| Chronos2 | ✓ | ✓ | ✓ | - |
| Chronos2SmallFineTuned | ✓ | ✓ | - | ✓ |
| ChronosWithRegressor[bolt_small] | ✓ | ✓ | - | - |
| TemporalFusionTransformer | ✓ | ✓ | - | - |
| DeepAR | ✓ | ✓ | - | - |
| AutoETS | ✓ | ✓ | - | - |
| DirectTabular | ✓ | ✓ | ✓ | ✓ |
| RecursiveTabular | ✓ | ✓ | ✓ | ✓ |
| DynamicOptimizedTheta | ✓ | ✓ | ✓ | ✓ |
| SeasonalNaive | ✓ | ✓ | ✓ | ✓ |
| WeightedEnsemble | ✓ | ✓ | - | - |

### Output Quantiles

| Quantile | Percentile | Description |
|----------|------------|-------------|
| p10 | 10th | Bearish scenario |
| p50 | 50th | Median forecast |
| p90 | 90th | Bullish scenario |

---

## 13. Summary Statistics

| Category | Count |
|----------|-------|
| **Symbols Tracked** | 34+ |
| **Technical Indicators (Elite)** | 27 |
| **Core Training Features** | ~1,384 |
| **FRED Economic Series** | 111 |
| **Weather Stations** | 57 |
| **Weather Variables** | 10 |
| **CFTC Contracts** | 30+ |
| **News Sources** | 46 |
| **Specialist Buckets (Economic)** | 11 |
| **Specialist Buckets (Neural)** | 5 |
| **Database Tables** | 60+ |
| **Forecast Horizons** | 4 |
| **Quantile Outputs** | 3 (p10, p50, p90) |

### Data Volumes (Approximate)

| Table | Rows |
|-------|------|
| Market Futures (1D) | 385K+ |
| FRED Observations | 386K+ |
| Weather NOAA | 215K+ |
| CFTC COT | 6K+ |
| Driver Scores | 47K+ |

---

## Appendix: Feature Categories Summary

```
CORE TRAINING FEATURES (~1,384 total)
├── Market Symbols OHLCV        ~420 features
│   └── 84 symbols × 5 columns
├── Volatility Proxies           42 features
│   └── 7 symbols × 6 metrics
├── FRED Economic               111 features
│   ├── Daily                    46 series
│   ├── Weekly                   14 series
│   ├── Monthly                  67 series
│   └── Quarterly                10 series
├── Weather (NOAA)             ~570 features
│   └── 57 stations × 10 variables
├── CFTC COT                   ~210 features
│   └── 30 contracts × 7 metrics
├── FX Spot                      11 features
├── USDA Exports                  5 features
├── USDA WASDE                    5 features
├── EPA RINs                      4 features
└── News Sentiment                6 features
```

---

*Last Updated: January 2026*
*Source: ZINC-FUSION-V15 Codebase Analysis*
