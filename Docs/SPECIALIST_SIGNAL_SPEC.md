# Specialist Signal Spec (Implementation-Aligned)

Status: Implementation-aligned (2026-01-24). This document reflects the current
specialist signal implementations in `src/fusion/specialists/`. Changes require
explicit approval.

## Purpose

Define clear, minimal signal outputs per specialist so the ensemble benefits from
orthogonal information without overfitting. Specialists emit scores/residuals,
not multi-horizon price predictions.

Specialists are **unaffected** by the Core CPU-only policy.

## Signal Contract (All Specialists)

- Output is a compact signal (1-2 values) per date and symbol.
- Signals are inputs to the core and meta-learner; horizons are owned by the core.
- No decision semantics (no buy/sell/act-now outputs).
- Use daily data only; intraday tables (`analytics.zl_price_15m`, `analytics.zl_price_1h`) are dashboard-only; daily dashboard copy is `analytics.zl_price_1d`.
- Proposed signals require explicit approval before implementation.

## Specialist Specs (Implementation Mapping)

Each entry reflects the current code. Changes should be validated with ablation
tests before adoption.

### crush

- Purpose: capture margin-driven production incentives.
- Inputs: ZL/ZS/ZM closes; WASDE fundamentals if present; volume/OI if present.
- Signal: `signal_1` model prediction of 21d forward ZL return; `signal_2` 21d crush momentum (lagged).
- Model class: XGBRegressor (fallback: GradientBoostingRegressor).

### china

- Purpose: demand shifts and shipment intensity.
- Inputs: copper (HG), CNY, BRL, shipping proxies (BDRY/SBLK), seasonality encodings.
- Signal: `signal_1` model prediction of 21d forward ZL return; `signal_2` Brazil competition z-score (BRL).
- Model class: GradientBoostingRegressor.

### fx

- Purpose: currency pressure on export competitiveness.
- Inputs: DXY + FX pairs (BRL, CNY, MXN, AUD), US rates and foreign rates when available.
- Signal: `signal_1` FX pressure index (ARDL-based when available); `signal_2` carry trade signal.
- Model class: statsmodels ARDL with lag selection; composite fallback if ARDL unavailable.

### fed

- Purpose: macro rate regime influence.
- Inputs: Fed funds, DGS10, DGS2, DGS3MO (or FedFunds proxy), T10YIE (if available), NFCI.
- Signal: `signal_1` rates regime score; `signal_2` regime change momentum.
- Model class: weighted z-score composite (ridge-style), no fitted estimator.

### tariff

- Purpose: discrete policy shocks on trade flows.
- Inputs: EPU indices (USEPUINDXM, EPUTRADE, EMVTRADEPOLEMV).
- Signal: `signal_1` tariff risk score (weighted EPU composite); `signal_2` EPU spike indicator.
- Model class: rules-based on EPU thresholds.

### energy

- Purpose: spillovers from energy complex.
- Inputs: CL/HO/RB, BOHO spread, 3-2-1 crack spread.
- Signal: `signal_1` energy spillover score (VAR/IRF/FEVD); `signal_2` spillover momentum.
- Model class: statsmodels VAR with IRF/FEVD (fallback to composite if VAR unavailable).

### biofuel

- Purpose: regulatory demand shifts (RFS, 45Z, CI scoring).
- Inputs: RIN prices (D4/D6/D3/D5), LCFS credit; HO for margin proxy.
- Signal: `signal_1` policy pressure (RIN/LCFS z-score, EMA-smoothed); `signal_2` RIN momentum (if RIN/LCFS available).
- Model class: EMA-smoothed policy proxy (no NLP).

### palm

- Purpose: substitution pressure from FCPO.
- Inputs: FCPO prices (cpo_close or palm_oil_close), optional MYR/USD as a feature.
- Signal: `signal_1` model prediction from ECM features; `signal_2` mean reversion speed.
- Model class: ECM cointegration + Ridge regression.

### volatility

- Purpose: regime risk and variance shifts.
- Inputs: ZL returns, VIX, VIX3M term structure, OVX.
- Signal: `signal_1` volatility regime level; `signal_2` regime change probability.
- Model class: GJR-GARCH(1,1) Student-t when available; term-structure overlay.

### substitutes

- Purpose: switching behavior among soft oils.
- Inputs: relative prices vs canola/palm/sunflower/rapeseed.
- Signal: `signal_1` model prediction; `signal_2` ZL richness score (mean ratio z-score).
- Model class: RandomForestRegressor.

### trump_effect

- Purpose: trade/rhetoric risk premium.
- Inputs: EPU indices (daily/monthly), EPUTRADE, VIX, FXI (China ETF proxy).
- Signal: `signal_1` event intensity (trade tension + China exposure, regime-weighted); `signal_2` trade uncertainty share (trade EPU / total).
- Model class: event study + EPU decomposition + proxy composites.

## Evaluation (Required)

- Primary: correlation with forward returns, stability across regimes.
- Secondary: signal orthogonality and downstream ablation deltas.
- Reject any change that degrades core/ensemble accuracy or stability.

## Integration Rules

- Specialists output signals only; core produces multi-horizon forecasts.
- Meta-learner should be shallow (weighted ensemble or ridge).
- Log source provenance for each signal (news/event tags, series ids).

## Verification (Code References — 2026-01-24)

Line references below reflect the current implementation and should be re-checked
after any code edits.

| Specialist | File | Key references |
| --- | --- | --- |
| crush | `src/fusion/specialists/xgb_signals.py` | `CrushSignalGenerator` (197), `_create_model` (237-258) |
| substitutes | `src/fusion/specialists/xgb_signals.py` | `SubstitutesSignalGenerator` (394), `_create_model` (433-442) |
| china | `src/fusion/specialists/xgb_signals.py` | `ChinaSignalGenerator` (571), `_create_model` (621-630) |
| fx | `src/fusion/specialists/ardl_signals.py` | `FxSignalGenerator` (49), ARDL fit (495-506) |
| fed | `src/fusion/specialists/ardl_signals.py` | `FedSignalGenerator` (835), weights (979-1011) |
| volatility | `src/fusion/specialists/garch_signals.py` | `VolatilitySignalGenerator` (34), GJR-GARCH fit (96-103) |
| energy | `src/fusion/specialists/var_signals.py` | `EnergySignalGenerator` (52), VAR fit (184-221), IRF/FEVD (236-244) |
| palm | `src/fusion/specialists/ecm_signals.py` | `PalmSignalGenerator` (203), Ridge model (130-136), coint/OLS (311-317), `signal_2` (529-580) |
| tariff | `src/fusion/specialists/event_signals.py` | `TariffSignalGenerator` (27), spike/regime (80-115) |
| biofuel | `src/fusion/specialists/event_signals.py` | `BiofuelSignalGenerator` (216), RIN momentum (314-325) |
| trump_effect | `src/fusion/specialists/event_signals.py` | `TrumpEffectSignalGenerator` (426), EPU decomp (511-547), regime (549-558) |

## Open Questions

- Final list of entities/tickers for JV tracking and policy actors.
- Confirm which volatility indices are primary for the strategy page.
- Confirm availability of vessel/CI data sources and storage location.

## Source Review (Draft, Incomplete)

Tag each citation as one of: authoritative, context, or hypothesis.
Do not use a claim in model logic until it has a source and tag.

### Authoritative (Verified Links)

- EPA Renewable Fuel Standard (RFS) overview: https://www.epa.gov/renewable-fuel-standard-program
- EPA Public Data for the Renewable Fuel Standard: https://www.epa.gov/fuels-registration-reporting-and-compliance-help/public-data-renewable-fuel-standard
- EPA RIN Generation Spreadsheet (CSV): https://www.epa.gov/fuels-registration-reporting-and-compliance-help/spreadsheet-rin-generation-data-renewable-fuel
- IRS Clean Fuel Production Credit (45Z): https://www.irs.gov/credits-deductions/clean-fuel-production-credit
- USDA ERS Oil Crops Outlook (Dec 2025 PDF, OCS-25l): https://ers.usda.gov/sites/default/files/_laserfiche/outlooks/113558/OCS-25l.pdf?v=68939
- USDA WASDE archive (Cornell USDA Library): https://usda.library.cornell.edu/concern/publications/3t945q76s?locale=en
- USDA FAS GATS trade data (imports/exports): https://apps.fas.usda.gov/gats/default.aspx
- California Air Resources Board LCFS: https://ww2.arb.ca.gov/our-work/programs/low-carbon-fuel-standard
- CBOE VIX product page (volatility methodology anchor): https://www.cboe.com/tradable_products/vix/
- CME CVOL methodology (benchmark PDF): https://www.cmegroup.com/market-data/cme-group-benchmark-administration/files/cvol-methodology.pdf
- CME CVOL data portal: https://www.cmegroup.com/market-data/cme-group-benchmark-administration/cme-group-volatility-indexes.html
- Bursa Malaysia Derivatives rules (CFTC-hosted copy): https://www.cftc.gov/sites/default/files/idc/groups/public/%40otherif/documents/ifdocs/bmdbursamalaysiaderivativesbe.pdf
- USDA ERS Chart of Note (2021-2022 soy oil prices): https://ers.usda.gov/data-products/charts-of-note/chart-detail?chartId=103795

### Context (Verified Links)

- CHS domestic soybean demand outlook (Aug 13, 2024): https://www.chsinc.com/news-and-stories/2024/08/13/domestic-soybean-demand-outlook
- Grease Connections soybean oil price guide (Jun 9, 2025): https://greaseconnections.com/soybean-oil-price-guide-2025/
- IG market trends primer (Feb 10, 2025): https://www.ig.com/en/trading-strategies/understanding-market-trends-for-your-investing-decisions-250209
- Biodiesel Magazine USDA biofuel use report (Jul 11, 2025): https://biodieselmagazine.com/articles/usda-july-wasde-boosts-forecast-for-soybean-oil-use-in-biofuel-production
- Foodcom soybean market overview (2026): https://foodcom.pl/en/soybean-market-overview-global-report/
- Mordor Intelligence soybean oil market report (2026-2031): https://www.mordorintelligence.com/industry-reports/global-soybean-oil-market
- Argus Media biofuel credit cut (Jan 15, 2026): https://www.argusmedia.com/en/news-and-insights/latest-market-news/2776451-us-imported-biofuel-credit-cut-unlikely-in-2026
- Chronicle-Journal biofuel limbo (Jan 16, 2026): http://markets.chroniclejournal.com/chroniclejournal/article/marketminute-2026-1-16-biofuel-limbo-why-45z-tax-credit-uncertainty-is-paralyzing-us-soybean-oil-markets-in-2026
- The Business Research Company soybean oil market report: https://www.thebusinessresearchcompany.com/report/soybean-oil-global-market-report
- Research and Markets soybean oil report (Renub Research): https://www.researchandmarkets.com/report/soybean-oil
- Pinion Global 45Z uncertainty (Oct 29, 2025): https://www.pinionglobal.com/blog/preparing-for-45z-operating-amid-uncertainty/
- Farm Policy News 45Z guidance (Oct 30, 2024): https://farmpolicynews.illinois.edu/2024/10/lack-of-45z-guidance-could-cause-biofuel-production-shutdowns/
- FCPO contract specs mirror (uTrade): https://www.utrade.com.my/pdf/UserGuides/FCPO_specification_english.pdf
- FCPO contract overview (Kenanga Futures, 2018): https://www.kenangafutures.com.my/wp-content/uploads/sites/3/2018/11/Crude-Palm-Oil-Futures-Options-FCPO-and-OCPO.pdf
- CME rule filing (BMD FCPO spot limit mention): https://www.cmegroup.com/market-regulation/rule-filings/2020/11/20-462_1.pdf
- IndexBox mirror of Platts survey (palm oil, 2026): https://www.indexbox.io/blog/palm-oil-prices-to-average-lower-in-2026-on-rising-indonesia-malaysia-supply/
- MarketMinute summary of BofA outlook (soy oil bullish 2026): https://markets.chroniclejournal.com/chroniclejournal/article/marketminute-2025-11-25-bank-of-america-forecasts-divergent-paths-for-key-agricultural-commodities-in-2026
- Barchart ZL continuous opinion: https://www.barchart.com/futures/quotes/ZL%2A0/opinion
- Barchart ZL continuous technical analysis: https://www.barchart.com/futures/quotes/ZL%2A0/technical-analysis

### Pending (URL Needed)

- Palm oil market source (Bursa Malaysia specs/circulars; blocked here)
- Investing.com bullish 2026 BofA note (blocked here)
- StockInvest.us ZL forecast (blocked here; replaced by Barchart)
- S&P Global palm oil survey (blocked here; replaced by IndexBox mirror)

### User-Provided Sources (Unverified; Needs Link Validation)

Classify after link validation; tags below reflect intended hierarchy.

Authoritative (intended):
- RIN definition (DOE AFDC): https://afdc.energy.gov/laws/RIN.html
- EPA public RFS data: https://www.epa.gov/fuels-registration-reporting-and-compliance-help/public-data-renewable-fuel-standard
- EPA RIN generation spreadsheet: https://www.epa.gov/fuels-registration-reporting-and-compliance-help/spreadsheet-rin-generation-data-renewable-fuel
- CME CVOL methodology (Confluence): https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/331283351/CME+Group+Volatility+Indexes+-+CVOL
- CME CVOL methodology PDF: https://www.cmegroup.com/market-data/cme-group-benchmark-administration/files/cvol-methodology.pdf
- CME CVOL data portal: https://www.cmegroup.com/market-data/cme-group-benchmark-administration/cme-group-volatility-indexes.html
- Bursa Malaysia FCPO product page: https://www.bursamalaysia.com/trade/our_products_services/derivatives/commodity_derivatives/crude_palm_oil_futures
- Bursa Malaysia FCPO contract specs (PDF): https://www.bursamalaysia.com/sites/5d809dcf39fba22790cad230/assets/605322fb5b711a61ee8be2ae/BURSA_FCPO_Contract_Spec_EN_digital.pdf
- Bursa Malaysia FCPO circular: https://www.bursamalaysia.com/sites/5bb54be15f36ca0af339077a/assets/5bb55b165f36ca0c38d98b81/1TP_Circular__FCPO__Final___002_.pdf
- Bursa Malaysia Derivatives rules (CFTC-hosted copy): https://www.cftc.gov/sites/default/files/idc/groups/public/%40otherif/documents/ifdocs/bmdbursamalaysiaderivativesbe.pdf

Context (intended):
- Chronicle-Journal biofuel limbo: http://markets.chroniclejournal.com/chroniclejournal/article/marketminute-2026-1-16-biofuel-limbo-why-45z-tax-credit-uncertainty-is-paralyzing-us-soybean-oil-markets-in-2026
- Fastmarkets 45Z uncertainty: https://www.fastmarkets.com/insights/us-soybean-oil-prices-stall-amid-biofuel-policy-45z-uncertainty-2026-preview
- Pinion Global 45Z uncertainty: https://www.pinionglobal.com/blog/preparing-for-45z-operating-amid-uncertainty/
- Farm Policy News 45Z guidance: https://farmpolicynews.illinois.edu/2024/10/lack-of-45z-guidance-could-cause-biofuel-production-shutdowns/
- Argus biodiesel supply domestic: https://www.argusmedia.com/en/news/2641586-viewpoint-us-biodiesel-supply-to-lean-domestic-in-2026
- Argus imported biofuel credit cut: https://www.argusmedia.com/en/news/2635392-us-imported-biofuel-credit-cut-unlikely-in-2026
- Argus biofuel exemptions update: https://www.argusmedia.com/en/news/2623785-api-pitches-revamp-of-biofuel-exemptions-update
- Foodcom soybean market 2026: https://foodcom.pl/en/soybean-market-overview-global-report/
- Investing.com soybean oil bullish 2026: https://www.investing.com/news/commodities-news/soybean-oil-poised-for-bullish-2026-as-wheat-faces-pressure-bofa-reports-3226230
- Investing.com BofA sector note: https://www.investing.com/news/stock-market-news/which-sp-500-sectors-do-you-want-to-own-into-2026-bofa-answers-3230487
- Mordor Intelligence market size report: https://www.mordorintelligence.com/industry-reports/global-soybean-oil-market
- Business Research Company market size report: https://www.thebusinessresearchcompany.com/report/soybean-oil-global-market-report
- Research and Markets soybean oil report: https://www.researchandmarkets.com/report/soybean-oil
- S&P Global palm oil survey: https://www.spglobal.com/energy/en/news-research/latest-news/agriculture/010626-palm-oil-prices-to-weaken-in-2026-biofuel-policy-clarity-crucial-survey
- IndexBox mirror of Platts survey: https://www.indexbox.io/blog/palm-oil-prices-to-average-lower-in-2026-on-rising-indonesia-malaysia-supply/
- StockInvest.us ZL forecast: https://stockinvest.us/stock/ZLUSX
- Barchart ZL continuous opinion: https://www.barchart.com/futures/quotes/ZL%2A0/opinion
- Barchart ZL continuous technical analysis: https://www.barchart.com/futures/quotes/ZL%2A0/technical-analysis
- FCPO specs mirror (uTrade): https://www.utrade.com.my/pdf/UserGuides/FCPO_specification_english.pdf
- FCPO overview deck (Kenanga Futures): https://www.kenangafutures.com.my/wp-content/uploads/sites/3/2018/11/Crude-Palm-Oil-Futures-Options-FCPO-and-OCPO.pdf
- CME rule filing (BMD FCPO spot limit mention): https://www.cmegroup.com/market-regulation/rule-filings/2020/11/20-462_1.pdf

### Citation Table (User-Provided Summaries)

Direct URLs are filled where available. Descriptions are user-provided and not
verified unless a source tag indicates otherwise.

| Citation Title (Publication Title) | Source/Publisher | Direct URL | Brief Description |
| --- | --- | --- | --- |
| Public Data for the Renewable Fuel Standard (Oct 30, 2025) | US Environmental Protection Agency | https://www.epa.gov/fuels-registration-reporting-and-compliance-help/public-data-renewable-fuel-standard | Official EPA portal providing public RFS data (RIN generation, available RINs, trades, usage), with interactive custom reports and historical monthly files. |
| RIN Generation Spreadsheet (CSV) | US Environmental Protection Agency | https://www.epa.gov/fuels-registration-reporting-and-compliance-help/spreadsheet-rin-generation-data-renewable-fuel | Direct CSV download for monthly RIN generation data. |
| CME Group Volatility Index (CVOL) Benchmark Methodology (Dec 8, 2025) | CME Group (Benchmark Admin.) | https://www.cmegroup.com/market-data/cme-group-benchmark-administration/files/cvol-methodology.pdf | Official methodology for CME CVOL implied volatility indexes (including soy complex), detailing the simple variance calculation and index components (Up/Down Variance, Skew, ATM vol). |
| CME Group Volatility Indexes (CVOL) Data Portal | CME Group | https://www.cmegroup.com/market-data/cme-group-benchmark-administration/cme-group-volatility-indexes.html | Data portal for CVOL benchmark values and related materials. |
| Palm oil prices to weaken in 2026, biofuel policy clarity crucial: survey (Jan 6, 2026) | IndexBox (Platts survey mirror) | https://www.indexbox.io/blog/palm-oil-prices-to-average-lower-in-2026-on-rising-indonesia-malaysia-supply/ | Mirror of Platts survey reporting 2025 average and 2026 median palm oil price expectations and policy clarity risks (context-tier mirror). |
| Crude Palm Oil Futures (FCPO) | Bursa Malaysia | https://www.bursamalaysia.com/trade/our_products_services/derivatives/commodity_derivatives/crude_palm_oil_futures | Official exchange product page for FCPO contract specifications (may be blocked in some environments). |
| Crude Palm Oil Futures (FCPO) - Contract Specifications (EN) | Bursa Malaysia | https://www.bursamalaysia.com/sites/5d809dcf39fba22790cad230/assets/605322fb5b711a61ee8be2ae/BURSA_FCPO_Contract_Spec_EN_digital.pdf | Official FCPO contract specification PDF (may be blocked in some environments). |
| FCPO Specification (English) | uTrade | https://www.utrade.com.my/pdf/UserGuides/FCPO_specification_english.pdf | Public mirror of FCPO contract specs (context backup when Bursa blocks). |
| Crude Palm Oil Futures (FCPO) and OCPO (2018) | Kenanga Futures | https://www.kenangafutures.com.my/wp-content/uploads/sites/3/2018/11/Crude-Palm-Oil-Futures-Options-FCPO-and-OCPO.pdf | Broker slide deck listing FCPO contract size and trading hours (context backup). |
| Rules of Bursa Malaysia Derivatives Berhad (BMD) | U.S. CFTC (hosted copy) | https://www.cftc.gov/sites/default/files/idc/groups/public/%40otherif/documents/ifdocs/bmdbursamalaysiaderivativesbe.pdf | Regulator-hosted copy with historical FCPO position limits (authoritative but dated). |
| CME Rule Filing 20-462 (BMD FCPO spot limit mention) | CME Group | https://www.cmegroup.com/market-regulation/rule-filings/2020/11/20-462_1.pdf | CME rule filing referencing BMD FCPO position limit context (context backup). |
| Biofuel Limbo: Why 45Z Tax Credit Uncertainty is Paralyzing US Soybean Oil Markets in 2026 (Jan 16, 2026) | The Chronicle-Journal (MarketMinute) | http://markets.chroniclejournal.com/chroniclejournal/article/marketminute-2026-1-16-biofuel-limbo-why-45z-tax-credit-uncertainty-is-paralyzing-us-soybean-oil-markets-in-2026 | Article describing 45Z guidance delays, market limbo, and soybean oil rangebound conditions. |
| Preparing for 45Z: Operating Amid Uncertainty (Oct 29, 2025) | Pinion Global | https://www.pinionglobal.com/blog/preparing-for-45z-operating-amid-uncertainty/ | Advisory piece describing operational implications of 45Z uncertainty. |
| Lack of 45Z Guidance Could Cause Biofuel Production Shutdowns (Oct 30, 2024) | Farm Policy News (University of Illinois) | https://farmpolicynews.illinois.edu/2024/10/lack-of-45z-guidance-could-cause-biofuel-production-shutdowns/ | Context summary of 45Z uncertainty and potential production impacts. |
| US imported biofuel credit cut unlikely in 2026 (Jan 15, 2026) | Argus Media (Latest Market News) | https://www.argusmedia.com/en/news-and-insights/latest-market-news/2776451-us-imported-biofuel-credit-cut-unlikely-in-2026 | Argus report noting import credit cuts are unlikely and highlighting ongoing policy debate. |
| Soybean Market Review 2026 [Global Report] (Jan 15, 2026) | Foodcom S.A. | https://foodcom.pl/en/soybean-market-overview-global-report/ | Global soybean market outlook covering production, stocks, demand, and policy-driven volatility. |
| Soybean Oil Market Size and Share Analysis - Growth Trends and Forecast (2026-2031) | Mordor Intelligence | https://www.mordorintelligence.com/industry-reports/global-soybean-oil-market | Market research report estimating global soybean oil market size and CAGR. |
| Bank of America forecasts divergent paths for key agricultural commodities in 2026 (Nov 25, 2025) | MarketMinute via Chronicle-Journal | https://markets.chroniclejournal.com/chroniclejournal/article/marketminute-2025-11-25-bank-of-america-forecasts-divergent-paths-for-key-agricultural-commodities-in-2026 | Public summary of BofA framing (soy oil bullish vs. wheat/meal dynamics). |
| Soybean Market Report 2025-2033: Biofuel Expansion and Plant Protein Demand | Research and Markets (Renub Research) | https://www.researchandmarkets.com/report/soybean-oil | Press release projecting global soybean market growth with biofuel and plant-protein demand drivers. |
| USDA: July WASDE boosts forecast for soybean oil use in biofuel production (Jul 11, 2025) | Biodiesel Magazine | https://biodieselmagazine.com/articles/usda-july-wasde-boosts-forecast-for-soybean-oil-use-in-biofuel-production | Report on USDA WASDE update raising 2025/26 soy oil-for-biofuel use estimates. |
| Global Soybean Oil Market Projected to Grow at 7.1% CAGR, Reaching $87.63B by 2029 (Jul 31, 2025) | The Business Research Company | https://www.thebusinessresearchcompany.com/report/soybean-oil-global-market-report | Market report summary forecasting global soybean oil market growth and drivers. |
| Soybean Oil Futures Opinion (ZL continuous) | Barchart | https://www.barchart.com/futures/quotes/ZL%2A0/opinion | Public opinion page with buy/sell/hold-style signal for ZL continuous contract. |
| Soybean Oil Futures Technical Analysis (ZL continuous) | Barchart | https://www.barchart.com/futures/quotes/ZL%2A0/technical-analysis | Public technical indicators page (moving averages, momentum, etc.) for ZL continuous contract. |
| Strong demand for soybean oil elevated U.S. prices in 2021 and 2022 (Apr 27, 2022) | USDA Economic Research Service | https://ers.usda.gov/data-products/charts-of-note/chart-detail?chartId=103795 | ERS chart/note describing biofuel demand and tight veg oil supplies driving 2021-2022 price gains. |

### Link Validation Results (2026-01-21)

Automated HEAD/GET checks completed; update or replace any failing URLs.

OK (200):
- https://afdc.energy.gov/laws/RIN.html
- https://www.epa.gov/fuels-registration-reporting-and-compliance-help/public-data-renewable-fuel-standard
- https://www.epa.gov/fuels-registration-reporting-and-compliance-help/spreadsheet-rin-generation-data-renewable-fuel
- https://www.cmegroup.com/market-data/cme-group-benchmark-administration/files/cvol-methodology.pdf
- https://www.cmegroup.com/market-data/cme-group-benchmark-administration/cme-group-volatility-indexes.html
- https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/331283351/CME+Group+Volatility+Indexes+-+CVOL
- https://www.fastmarkets.com/insights/us-soybean-oil-prices-stall-amid-biofuel-policy-45z-uncertainty-2026-preview/
- http://markets.chroniclejournal.com/chroniclejournal/article/marketminute-2026-1-16-biofuel-limbo-why-45z-tax-credit-uncertainty-is-paralyzing-us-soybean-oil-markets-in-2026
- https://www.argusmedia.com/en/news-and-insights/latest-market-news/2776451-us-imported-biofuel-credit-cut-unlikely-in-2026
- https://foodcom.pl/en/soybean-market-overview-global-report/
- https://www.mordorintelligence.com/industry-reports/global-soybean-oil-market
- https://biodieselmagazine.com/articles/usda-july-wasde-boosts-forecast-for-soybean-oil-use-in-biofuel-production
- https://www.thebusinessresearchcompany.com/report/soybean-oil-global-market-report
- https://www.researchandmarkets.com/report/soybean-oil
- https://www.utrade.com.my/pdf/UserGuides/FCPO_specification_english.pdf
- https://www.kenangafutures.com.my/wp-content/uploads/sites/3/2018/11/Crude-Palm-Oil-Futures-Options-FCPO-and-OCPO.pdf
- https://www.cftc.gov/sites/default/files/idc/groups/public/%40otherif/documents/ifdocs/bmdbursamalaysiaderivativesbe.pdf
- https://www.cmegroup.com/market-regulation/rule-filings/2020/11/20-462_1.pdf
- https://www.pinionglobal.com/blog/preparing-for-45z-operating-amid-uncertainty/
- https://farmpolicynews.illinois.edu/2024/10/lack-of-45z-guidance-could-cause-biofuel-production-shutdowns/
- https://www.indexbox.io/blog/palm-oil-prices-to-average-lower-in-2026-on-rising-indonesia-malaysia-supply/
- https://www.barchart.com/futures/quotes/ZL%2A0/opinion
- https://www.barchart.com/futures/quotes/ZL%2A0/technical-analysis
- https://ers.usda.gov/data-products/charts-of-note/chart-detail?chartId=103795

Blocked (403):
- https://www.bursamalaysia.com/trade/our_products_services/derivatives/commodity_derivatives/crude_palm_oil_futures
- https://www.bursamalaysia.com/sites/5d809dcf39fba22790cad230/assets/605322fb5b711a61ee8be2ae/BURSA_FCPO_Contract_Spec_EN_digital.pdf
- https://www.bursamalaysia.com/sites/5bb54be15f36ca0af339077a/assets/5bb55b165f36ca0c38d98b81/1TP_Circular__FCPO__Final___002_.pdf
- https://www.spglobal.com/energy/en/news-research/latest-news/agriculture/010626-palm-oil-prices-to-weaken-in-2026-biofuel-policy-clarity-crucial-survey
- https://www.investing.com/news/commodities-news/soybean-oil-poised-for-bullish-2026-as-wheat-faces-pressure-bofa-reports-3226230
- https://www.investing.com/news/stock-market-news/which-sp-500-sectors-do-you-want-to-own-into-2026-bofa-answers-3230487
- https://www.investing.com/news/commodities-news/soybean-oil-poised-for-bullish-2026-as-wheat-faces-pressure-bofa-reports-93CH-4377754
- https://stockinvest.us/stock/ZLUSX

Not Found (404):
- https://www.epa.gov/renewable-fuel-standard-program/renewable-identification-numbers-rins
- https://www.epa.gov/renewable-fuel-standard-program/public-data-renewable-fuel-standard
- https://www.epa.gov/renewable-fuel-standard-program/renewable-identification-number-rin-data-renewable-fuel-standard-program
- https://www.epa.gov/renewable-fuel-standard-program/spreadsheet-rin-generation-data-renewable-fuel-standard
- https://www.cmegroup.com/market-data/cme-group-volatility-indexes.html
- https://www.cmegroup.com/market-data/files/cme-group-volatility-index-methodology.pdf
- https://www.argusmedia.com/en/news/2641586-viewpoint-us-biodiesel-supply-to-lean-domestic-in-2026
- https://www.argusmedia.com/en/news/2635392-us-imported-biofuel-credit-cut-unlikely-in-2026
- https://www.argusmedia.com/en/news/2623785-api-pitches-revamp-of-biofuel-exemptions-update

## Ablation Checklist (Before Adopting Any Specialist Signal)

- Define signal formula and unit; document expected directionality.
- Run baseline core model (no specialists) and save metrics.
- Add one specialist signal; rerun with identical splits and settings.
- Compare MAE/MASE + quantile coverage vs baseline.
- Check stability across regimes (pre/post 2020, post-2022).
- Inspect leakage risk (timing, look-ahead, reporting lag).
- Keep only signals with positive, stable deltas.

## Validation Steps (Operational)

- Query training matrix coverage for the signal inputs.
- Verify null rates and date alignment; reject if coverage < threshold.
- Run `pytest -q` after any feature integration.
