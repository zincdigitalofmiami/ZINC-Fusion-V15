# DATABASE SCHEMA REFERENCE
## Generated: 2026-01-15

Use this reference when database connection is unavailable.

---

## DATE COLUMN REFERENCE (Avoid MCP Errors)

| Schema | Table | Primary Date Column |
|--------|-------|---------------------|
| raw.* | most tables | `event_date` |
| raw.whitehouse_actions_event | | `action_date` |
| raw.news_articles_1d | | `published_at` or `event_date` |
| silver.news_scored_1d | | `published_at` |
| silver.futures_prices_1d | | `trade_date` |
| silver.fx_rates_1d | | `trade_date` |
| training.* | most tables | `as_of_date` |
| gold.elite_indicators_1d | | `trade_date` |
| model.* | most tables | `as_of_date` or `trained_at` |

---

## RAW TABLES (Bronze Layer)

| Table | Rows | Description |
|-------|------|-------------|
| raw.market_futures_1d | 432,152 | OHLCV futures data |
| raw.fred_observations_1d | 513,630 | FRED economic series |
| raw.weather_noaa_1d | 220,976 | Weather data |
| raw.fx_spot_1d | 59,168 | FX spot rates |
| raw.cftc_cits_1w | 39,028 | CFTC CITS data |
| raw.cftc_cot_1w | 18,381 | COT positioning |
| raw.usda_wasde_1m | 12,608 | WASDE reports |
| raw.usda_export_sales_1w | 9,752 | Export sales |
| raw.yahoo_equity_1d | 9,534 | Yahoo equities |
| raw.market_futures_1h | 4,967,276 | Hourly futures |
| raw.news_articles_event | 3,219 | News archive |
| raw.epa_rin_prices_1d | 3,136 | RIN prices |
| raw.news_articles_1d | 2,901 | Daily news |
| raw.legislation_federal_register_1d | 798 | Federal register |
| raw.usda_nass_event | 407 | NASS data |
| raw.options_futures_1d | 28,648 | Options data |
| raw.whitehouse_actions_event | 41 | WhiteHouse actions |
| raw.aei_articles_event | 24 | AEI articles |
| raw.nyfed_rates_1d | 23 | NY Fed rates |
| raw.cbp_trade_event | 12 | CBP trade |
| raw.farmdoc_articles_event | 10 | Farmdoc articles |

---

## SYMBOLS IN raw.market_futures_1d

### Core Soybean Complex
| Symbol | Rows | Start | End | Description |
|--------|------|-------|-----|-------------|
| ZL | 8,398 | 1970-01-01 | 2026-01-09 | Soybean Oil |
| ZS | 14,573 | 1968-12-05 | 2026-01-09 | Soybeans |
| ZM | 6,490 | 2000-05-15 | 2026-01-09 | Soybean Meal |
| XK | 4,012 | 2010-06-07 | 2025-12-15 | Mini Soybeans |

### Energy Complex
| Symbol | Rows | Start | End | Description |
|--------|------|-------|-----|-------------|
| CL | 7,290 | 2000-08-23 | 2026-01-09 | Crude Oil WTI |
| BZ | 5,332 | 2007-07-30 | 2025-12-29 | Brent Crude |
| HO | 7,278 | 2000-09-01 | 2026-01-08 | Heating Oil |
| RB | 7,239 | 2000-11-01 | 2026-01-08 | RBOB Gasoline |
| NG | 7,285 | 2000-08-30 | 2026-01-09 | Natural Gas |

### Treasury/Fed
| Symbol | Rows | Start | End | Description |
|--------|------|-------|-----|-------------|
| ZN | 7,259 | 2000-09-21 | 2025-12-29 | 10Y Treasury Note |
| ZB | 7,264 | 2000-09-21 | 2025-12-29 | 30Y Treasury Bond |
| ZT | 7,316 | 2000-06-02 | 2025-12-29 | 2Y Treasury Note |
| ZF | 7,265 | 2000-09-21 | 2025-12-29 | 5Y Treasury Note |
| ZQ | 4,536 | 2010-06-07 | 2025-12-15 | Fed Funds |

### FX/Currencies
| Symbol | Rows | Start | End | Description |
|--------|------|-------|-----|-------------|
| DX | 6,795 | 1999-03-18 | 2025-07-18 | Dollar Index Futures |
| DXY | 2,597 | 2015-06-08 | 2026-01-08 | Dollar Index |
| 6E | 7,294 | 2000-09-12 | 2025-12-29 | EUR/USD |
| 6B | 7,208 | 2000-10-05 | 2025-12-29 | GBP/USD |
| 6J | 7,215 | 2000-09-13 | 2025-12-29 | USD/JPY |
| 6C | 7,309 | 2000-05-23 | 2025-12-29 | USD/CAD |
| 6A | 7,190 | 2000-11-08 | 2025-12-29 | AUD/USD |
| 6L | 4,165 | 2010-06-14 | 2025-12-15 | BRL/USD |
| 6M | 7,014 | 2001-06-18 | 2025-12-29 | USD/MXN |

### Volatility
| Symbol | Rows | Start | End | Description |
|--------|------|-------|-----|-------------|
| VX | 9,278 | 1990-01-02 | 2025-07-24 | VIX Futures |
| VIX | 7 | 2025-12-30 | 2026-01-08 | VIX Index (recent) |
| GVZ | 2,590 | 2015-04-01 | 2025-07-18 | Gold VIX |
| ES | 7,298 | 2000-09-18 | 2026-01-08 | S&P 500 E-mini |
| NQ | 7,298 | 2000-09-18 | 2026-01-08 | Nasdaq E-mini |

### Palm Oil / Substitutes
| Symbol | Rows | Start | End | Description |
|--------|------|-------|-----|-------------|
| CPO | 3,767 | 2010-05-25 | 2025-12-29 | Crude Palm Oil |
| RS | 3,575 | 2011-07-13 | 2025-10-15 | Canola (STALE) |

### China Proxies
| Symbol | Rows | Start | End | Description |
|--------|------|-------|-----|-------------|
| HG | 7,281 | 2000-08-30 | 2026-01-09 | Copper |
| FXI | 7 | 2025-12-30 | 2026-01-08 | China ETF (recent) |
| KWEB | 7 | 2025-12-30 | 2026-01-08 | China Tech ETF (recent) |

### Metals
| Symbol | Rows | Start | End | Description |
|--------|------|-------|-----|-------------|
| GC | 7,277 | 2000-08-30 | 2026-01-09 | Gold |
| SI | 7,279 | 2000-08-30 | 2026-01-09 | Silver |

### Shipping (Tariff)
| Symbol | Rows | Start | End | Description |
|--------|------|-------|-----|-------------|
| BDRY | 1,954 | 2018-03-22 | 2025-12-29 | Dry Bulk Index |
| SBLK | 4,547 | 2007-12-03 | 2025-12-29 | Star Bulk Carriers |

---

## SPECIALIST FEATURES (training.specialist_features)

All 11 buckets: 6,627 rows each | 2000-01-03 to 2026-01-09

| Bucket | Feature Count | Key Features |
|--------|---------------|--------------|
| biofuel | 56 | rin_D3/D4/D5/D6, biodiesel_margin, ho/cl prices |
| china | 59 | hg_*, fx_USDCNY, usda_exports, china_demand_score |
| crush | 67 | board_crush, oil_share, zl/zm/zs ratios, cot_* |
| energy | 76 | cl/ho/rb/ng prices, crack spreads, boho_* |
| fed | 43 | DGS10/DGS2, T10Y2Y, FEDFUNDS, NFCI, zn/zb prices |
| fx | 38 | dx_*, dxy_*, fx_EUR/BRL/CNY/JPY, correlations |
| palm | 56 | palm_*, xk_*, weather_*, zl_palm_spread |
| substitutes | 38 | rs_*, canola_*, zl_canola_spread |
| tariff | 56 | USEPUINDXM, trade_war_regime, tariff flags |
| trump_effect | 76 | VIXCLS, T10Y2Y, rin_*, trump_regime_score |
| volatility | 49 | VIXCLS, vx_*, es_*, realized_vol |

---

## KNOWN GAPS (Per GPT Audit)

1. **NO NEWS SENTIMENT** in any specialist bucket
2. **PALM**: CPO exists in raw but not used (only XK)
3. **SUBSTITUTES**: Only canola (RS), missing sunflower/rapeseed
4. **VOLATILITY**: Missing GVZ, OVX in features
5. **TRUMP_EFFECT**: Missing WhiteHouse/social feeds integration
6. **RS (Canola)**: STALE - ends 2025-10-15

---

## SILVER LAYER

| Table | Rows | Date Range |
|-------|------|------------|
| silver.news_scored_1d | 2,389 | 2016-12-22 to 2025-12-24 |
| silver.futures_prices_1d | ? | ? |
| silver.fx_rates_1d | ? | ? |

News scored has `affects_*` flags for each bucket but NOT merged into specialist_features.

---

## CONNECTION INFO

- Database: postgres
- User: prisma_migration
- PostgreSQL: 17.2
- Host: 10.0.2.73:5432 (internal)
- Max connections: 50
- DB Size: ~5.5 GB
