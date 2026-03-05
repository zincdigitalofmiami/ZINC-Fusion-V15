# DATA SOURCE CATALOG — ALL URLs

## USDA (8 sub-agencies)

| Agency | URL | Status in V15 |
|---|---|---|
| NASS QuickStats API | https://quickstats.nass.usda.gov/api | Not built |
| WASDE Reports | https://www.usda.gov/oce/commodity/wasde/ | Not built |
| FAS Export Sales | https://apps.fas.usda.gov/export-sales/esrd1.html | WORKING |
| FAS GATS | https://apps.fas.usda.gov/gats/ | Not built |
| ERS Exchange Rates | https://www.ers.usda.gov/data-products/agricultural-exchange-rate-data-set | Not built |
| ERS Biofuels | https://www.ers.usda.gov/webdocs/ | Not built |
| AMS Grain Truck | https://www.ams.usda.gov/services/transportation/grain-truck-tonnage | Not built |
| NASS Grain Stocks | https://www.usda.gov/nass/ | Not built |
| USDA Press Releases | https://www.usda.gov/media/press-releases | Not built |
| NASS Newsroom | https://www.nass.usda.gov/Newsroom/ | Not built |
| FAS Newsroom | https://www.fas.usda.gov/newsroom/news-releases | Not built |

## FRED / Federal Reserve

| Series/Endpoint | URL | Status in V15 |
|---|---|---|
| FRED API | https://api.stlouisfed.org/fred/series/observations | WORKING (130+ series) |
| Fed Funds (DFF) | https://fred.stlouisfed.org/series/DFF | WORKING |
| 10Y Treasury (DGS10) | https://fred.stlouisfed.org/series/DGS10 | WORKING |
| 2Y Treasury (DGS2) | https://fred.stlouisfed.org/series/DGS2 | WORKING |
| 5Y Treasury (DGS5) | https://fred.stlouisfed.org/series/DGS5 | WORKING |
| 30Y Treasury (DGS30) | https://fred.stlouisfed.org/series/DGS30 | WORKING |
| 10Y-2Y Spread (T10Y2Y) | https://fred.stlouisfed.org/series/T10Y2Y | WORKING |
| Mortgage 30Y (MORTGAGE30US) | https://fred.stlouisfed.org/series/MORTGAGE30US | WORKING |
| USD/BRL (DEXBZUS) | https://fred.stlouisfed.org/series/DEXBZUS | WORKING |
| USD/MXN (DEXMXUS) | https://fred.stlouisfed.org/series/DEXMXUS | WORKING |
| USD/CNY (DEXCHUS) | https://fred.stlouisfed.org/series/DEXCHUS | WORKING |
| USD/EUR (DEXUSEU) | https://fred.stlouisfed.org/series/DEXUSEU | WORKING |
| Trade-Weighted USD (DTWEXBGS) | https://fred.stlouisfed.org/series/DTWEXBGS | WORKING |
| Nonfarm Payroll (PAYEMS) | https://fred.stlouisfed.org/series/PAYEMS | WORKING |
| Unemployment (UNRATE) | https://fred.stlouisfed.org/series/UNRATE | WORKING |
| CPI (CPIAUCSL) | https://fred.stlouisfed.org/series/CPIAUCSL | WORKING |
| PCE (PCEPI) | https://fred.stlouisfed.org/series/PCEPI | WORKING |
| WTI Crude (DCOILWTICO) | https://fred.stlouisfed.org/series/DCOILWTICO | WORKING |
| Brent Crude (DCOILBRENTEU) | https://fred.stlouisfed.org/series/DCOILBRENTEU | WORKING |
| Natural Gas (DHHNGSP) | https://fred.stlouisfed.org/series/DHHNGSP | WORKING |
| VIX (VIXCLS) | https://fred.stlouisfed.org/series/VIXCLS | WORKING |
| Financial Stress (STLFSI4) | https://fred.stlouisfed.org/series/STLFSI4 | WORKING |
| HY OAS (BAMLH0A0HYM2) | https://fred.stlouisfed.org/series/BAMLH0A0HYM2 | WORKING |
| Tallow PPI (WPU06410132) | https://fred.stlouisfed.org/series/WPU06410132 | WORKING |
| Rendering PPI (PCU3116133116132) | https://fred.stlouisfed.org/series/PCU3116133116132 | WORKING |
| econ.activity_1d (29 series) | various FRED series | STALE (Jan 12) — needs fix |
| Federal Reserve Board | https://www.federalreserve.gov/ | Not built (news) |
| FOMC Statements | https://www.federalreserve.gov/monetarypolicy/default.htm | Not built |

## EIA (Energy Information Administration)

| Endpoint | URL | Status in V15 |
|---|---|---|
| EIA API v2 | https://api.eia.gov/v2/ | DOWN (upstream since ~Mar 1) |
| Weekly Petroleum Supply | https://www.eia.gov/petroleum/supply/weekly/ | HTML scrape not built |
| Crude Oil Prices | https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm | Not built |
| Natural Gas Prices | https://www.eia.gov/dnav/ng/hist/rngwhhd.htm | Not built |
| Biodiesel Monthly | via API: petroleum/cons/wpsup/data/ | At source limit (Nov 2025) |
| Biodiesel Weekly | via API | BROKEN (0 rows, API down) |

## EPA (Environmental Protection Agency)

| Endpoint | URL | Status in V15 |
|---|---|---|
| RFS Program Data | https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rfs-program-data | Reference |
| RIN Trades & Prices | https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information | Reference |
| EPA Qlik WebSocket | wss://edap.epa.gov/public/app/{app_id} | WORKING (at source limit Jan 19) |

## CFTC (Commodity Futures Trading Commission)

| Endpoint | URL | Status in V15 |
|---|---|---|
| COT Reports Index | https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm | Reference |
| Historical Compressed | https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm | Not built |
| Socrata Legacy | https://publicreporting.cftc.gov/resource/6dca-aqww.json | NOT BUILT — V14 code exists |
| Socrata Disaggregated | https://publicreporting.cftc.gov/resource/jun7-fc8e.json | NOT BUILT — V14 code exists |
| Socrata TFF | https://publicreporting.cftc.gov/resource/gpe5-46if.json | NOT BUILT — V14 code exists |

## BLS (Bureau of Labor Statistics)

| Endpoint | URL | Status in V15 |
|---|---|---|
| BLS API v2 | https://api.bls.gov/publicapi/v2/timeseries | Not built |
| PPI Data | https://www.bls.gov/ppi/ | Not built (using FRED proxy) |

## NOAA (Weather)

| Endpoint | URL | Status in V15 |
|---|---|---|
| NCEI | https://www.ncei.noaa.gov/ | Not built |
| Daily Summaries | https://www.ncei.noaa.gov/data/daily-summaries/ | Not built |

## White House / USTR / Federal Register

| Endpoint | URL | Status in V15 |
|---|---|---|
| WH Briefing Room | https://www.whitehouse.gov/briefing-room/ | Not built |
| WH Trade | https://www.whitehouse.gov/trade/ | Not built |
| WH RSS | https://www.whitehouse.gov/briefing-room/statements-releases/feed/ | Not built |
| USTR Press | https://ustr.gov/about-us/policy-offices/press-office | Not built |
| Federal Register API | https://www.federalregister.gov/api/v1/documents.json | Not built |
| FR Tariff Search | https://www.federalregister.gov/api/v1/documents.json?search_term=tariff | Not built |
| Executive Orders | https://www.federalregister.gov/presidential-documents/executive-orders | Not built |

## CBOE

| Endpoint | URL | Status in V15 |
|---|---|---|
| VIX CSV | http://www.cboe.com/publish/ScheduledTask/MktData/datahouse/vixcurrent.csv | Not built (using FRED) |

## Foreign Government (Brazil, Malaysia, Indonesia, China, Argentina)

| Agency | URL | Status in V15 |
|---|---|---|
| CONAB (Brazil harvests) | https://www.conab.gov.br/info-agro/safras | Not built |
| INMET (Brazil weather) | https://apitempo.inmet.gov.br/estacao/{start}/{end}/{station} | Not built |
| INTA (Argentina) | https://www.inta.gob.ar/ | Not built |
| Bolsa Buenos Aires | https://www.bolsa.com.ar/ | Not built |
| MPOB Statistics | http://bepi.mpob.gov.my/index.php/en/statistics/sectoral-status.html | STALE (Dec 2025) |
| MPOB Prices | http://bepi.mpob.gov.my/index.php/en/price/monthly-prices | STALE |
| Bursa Malaysia | https://www.bursamalaysia.com/market_data | Not built |
| Indonesia Ministry of Ag | https://www.pertanian.go.id/ | Not built |
| China GACC Customs | http://english.customs.gov.cn/Statics/ | Not built |
| GACC Data Portal | http://43.248.49.97/ | Not built |
| China MOFCOM | http://english.mofcom.gov.cn/ | Not built |
| China Grain Center | http://www.grain.gov.cn/ | Not built |
| CNGOIC (China soy stats) | http://www.cngoic.com/ | Not built |
| Panama Canal Ops | https://www.pancanal.com/en/daily-canal-operations/ | Not built |

---

## PRIORITY FIXES — What needs building NOW

| # | Source | Gap | Fix |
|---|---|---|---|
| 1 | CFTC COT | Never built | Port V14 Socrata API → new Inngest function |
| 2 | econ.activity_1d | Stale since Jan 12 | Wire 29 missing FRED series into daily poller |
| 3 | CPO Palm Oil | Stale since Feb 9 | Yahoo Finance palm oil company proxies |
| 4 | MPOB Palm Monthly | Stale since Dec 2025 | USDA PSD Online fallback or MPOB scrape |
| 5 | EIA Biodiesel Weekly | 0 rows | HTML scrape fallback (API is down upstream) |
