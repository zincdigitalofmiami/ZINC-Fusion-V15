# ZINC-Fusion-V15: Comprehensive Data Sources by Specialist

**Complete exhaustive catalog of all scrapeable URLs, APIs, and data endpoints organized by the 10 Specialist domains. All sources are FREE and production-ready.**

> **Version**: Canonical  
> **Authority**: Kirk (Project Owner)  
> **Status**: LOCKED — Aligned with `specs/contracts/` specifications

---

## SPECIALIST 1: CRUSH (Soybean Complex Fundamentals)
**Weight**: 28-35% | **Model**: TabularPredictor

### US Production & Supply
- **USDA NASS QuickStats**: https://quickstats.nass.usda.gov/api
- **USDA WASDE Reports**: https://www.usda.gov/oce/commodity/wasde/
- **USDA FAS Export Sales**: https://apps.fas.usda.gov/export-sales/esrd1.html
- **USDA Grain Stocks**: https://www.usda.gov/nass/
- **USDA Grain Inspection**: https://www.ams.usda.gov/services/transportation/grain-truck-tonnage

### Global Production
- **Brazilian CONAB**: https://www.conab.gov.br/info-agro/safras
- **Argentine BOLSA**: https://www.bolsa.com.ar/
- **USDA FAS GATS**: https://apps.fas.usda.gov/gats/

### Processing & Crush Spreads
- **NOPA Crush Reports**: https://nopa.org/nopa-crush-report/
- **Trading Economics Soybean Oil**: https://tradingeconomics.com/commodity/soybean-oil
- **Trading Economics Soybean Meal**: https://tradingeconomics.com/commodity/soybean-meal
- **Trading Economics Soybeans**: https://tradingeconomics.com/commodity/soybeans

---

## SPECIALIST 2: CHINA (Trade Flows — Largest Importer)
**Weight**: 16-22% | **Model**: TabularPredictor

### Chinese Customs & Trade Data
- **China Customs GACC**: http://english.customs.gov.cn/Statics/
- **GACC Import/Export Data**: http://43.248.49.97/
- **China Ministry of Commerce**: http://english.mofcom.gov.cn/
- **MOFCOM Agricultural Trade**: http://www.mofcom.gov.cn/article/tongjiziliao/
- **China National Grain Center**: http://www.grain.gov.cn/
- **China Soybean Import Stats**: http://www.cngoic.com/

### China Import Demand (TradingEconomics)
- **China Soybean Oil Imports**: https://tradingeconomics.com/china/imports/soybean-oil
- **China Soybean Imports**: https://tradingeconomics.com/china/imports/soybeans

---

## SPECIALIST 3: FX (Currency Competitiveness)
**Weight**: 3-5% | **Model**: TabularPredictor

### FRED Exchange Rates
- **FRED API**: https://api.stlouisfed.org/fred/series/observations
- **USD/BRL (Brazil Real)**: https://fred.stlouisfed.org/series/DEXBZUS
- **USD/MXN (Mexico Peso)**: https://fred.stlouisfed.org/series/DEXMXUS
- **USD/CNY (China Yuan)**: https://fred.stlouisfed.org/series/DEXCHUS
- **USD/EUR**: https://fred.stlouisfed.org/series/DEXUSEU
- **Trade-Weighted USD Index**: https://fred.stlouisfed.org/series/DTWEXBGS

### USDA Agricultural Exchange Rates
- **ERS Exchange Rate Data**: https://www.ers.usda.gov/data-products/agricultural-exchange-rate-data-set

---

## SPECIALIST 4: FED (Monetary Policy)
**Weight**: 2-4% | **Model**: TabularPredictor

### Interest Rates & Treasury Yields (FRED)
- **Fed Funds Rate**: https://fred.stlouisfed.org/series/DFF
- **10-Year Treasury**: https://fred.stlouisfed.org/series/DGS10
- **2-Year Treasury**: https://fred.stlouisfed.org/series/DGS2
- **10Y-2Y Spread**: https://fred.stlouisfed.org/series/T10Y2Y

### Inflation (FRED)
- **CPI All Urban**: https://fred.stlouisfed.org/series/CPIAUCSL
- **PCE Price Index**: https://fred.stlouisfed.org/series/PCEPI

### Fed Announcements
- **Federal Reserve Board**: https://www.federalreserve.gov/
- **FOMC Statements**: https://www.federalreserve.gov/monetarypolicy/default.htm

---

## SPECIALIST 5: TARIFF (Trade Policy Impacts)
**Weight**: 3-5% | **Model**: TabularPredictor

### White House & USTR
- **White House Briefing Room**: https://www.whitehouse.gov/briefing-room/
- **USTR Press Office**: https://ustr.gov/about-us/policy-offices/press-office

### Federal Register (Executive Orders)
- **Executive Orders**: https://www.federalregister.gov/presidential-documents/executive-orders
- **Federal Register API**: https://www.federalregister.gov/api/v1/documents.json

### Trading Economics Tariffs
- **US Import Tariffs**: https://tradingeconomics.com/united-states/tariffs
- **US-China Trade Balance**: https://tradingeconomics.com/united-states/balance-of-trade

---

## SPECIALIST 6: ENERGY (Crude Oil & Energy Complex)
**Weight**: 10-14% | **Model**: TabularPredictor

### EIA Energy Data
- **EIA API**: https://api.eia.gov/v2/
- **EIA Weekly Petroleum Supply**: https://www.eia.gov/petroleum/supply/weekly/
- **Crude Oil Prices (WTI)**: https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm

### FRED Energy Prices
- **Crude Oil (WTI)**: https://fred.stlouisfed.org/series/DCOILWTICO
- **Crude Oil (Brent)**: https://fred.stlouisfed.org/series/DCOILBRENTEU
- **Natural Gas**: https://fred.stlouisfed.org/series/DHHNGSP

---

## SPECIALIST 7: BIOFUEL (Renewable Fuel Demand)
**Weight**: 6-10% | **Model**: TabularPredictor

### EPA Renewable Fuel Standard
- **EPA RFS Program Data**: https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rfs-program-data

### USDA Biofuels
- **USDA ERS Biofuels**: https://www.ers.usda.gov/webdocs/

---

## SPECIALIST 8: PALM (Palm Oil Substitution)
**Weight**: 8-12% | **Model**: TabularPredictor

### Malaysian Palm Oil Board (MPOB)
- **MPOB Statistics**: http://bepi.mpob.gov.my/index.php/en/statistics/sectoral-status.html
- **MPOB Price Data**: http://bepi.mpob.gov.my/index.php/en/price/monthly-prices

### Trading Economics Palm Oil
- **FCPO Prices**: https://tradingeconomics.com/commodity/palm-oil
- **Malaysia Palm Oil Exports**: https://tradingeconomics.com/malaysia/palm-oil-exports
- **Indonesia Palm Oil Production**: https://tradingeconomics.com/indonesia/palm-oil-production

---

## SPECIALIST 9: VOLATILITY (Financial Stress Indicators)
**Weight**: 2-3% | **Model**: TabularPredictor

### VIX & Volatility Indices
- **CBOE VIX**: https://www.cboe.com/tradable_products/vix/
- **FRED VIX**: https://fred.stlouisfed.org/series/VIXCLS
- **St. Louis Fed Financial Stress Index**: https://fred.stlouisfed.org/series/STLFSI4

### Credit Spreads (FRED)
- **High Yield OAS**: https://fred.stlouisfed.org/series/BAMLH0A0HYM2

---

## SPECIALIST 10: SUBSTITUTES (Vegetable Oil Substitution)
**Weight**: 4-6% | **Model**: TabularPredictor

### Competing Vegetable Oils
- **Canola Oil**: https://tradingeconomics.com/commodity/canola
- **Sunflower Oil**: https://tradingeconomics.com/commodity/sunflower-oil

### USDA Oilseed Data
- **USDA Oilseeds**: https://www.fas.usda.gov/commodities/oilseeds

---

## SUPPORTING DATA: WEATHER (Data Source — NOT a Specialist)

### US Weather (NOAA)
- **NOAA NCEI**: https://www.ncei.noaa.gov/
- **Daily Summaries**: https://www.ncei.noaa.gov/data/daily-summaries/

### Brazil Weather (INMET)
- **INMET API**: https://apitempo.inmet.gov.br/estacao/{start_date}/{end_date}/{station_id}

---

## L0 SPECIALIST SUMMARY

| ID | Specialist | Weight | OOF Table |
|----|------------|--------|-----------|
| 0 | core | — | `training.oof_core` |
| 1 | crush | 28-35% | `training.oof_crush` |
| 2 | china | 16-22% | `training.oof_china` |
| 3 | fx | 3-5% | `training.oof_fx` |
| 4 | fed | 2-4% | `training.oof_fed` |
| 5 | tariff | 3-5% | `training.oof_tariff` |
| 6 | energy | 10-14% | `training.oof_energy` |
| 7 | biofuel | 6-10% | `training.oof_biofuel` |
| 8 | palm | 8-12% | `training.oof_palm` |
| 9 | volatility | 2-3% | `training.oof_volatility` |
| 10 | substitutes | 4-6% | `training.oof_substitutes` |

---

**END OF CANONICAL DATA SOURCES REFERENCE**

*Last Updated: December 26, 2025*  
*Authority: Kirk (Project Owner)*  
*Total Specialists: 10 (energy/biofuel separate)*  
*Aligned with: `specs/contracts/` specifications*
