# INNGEST DATA SOURCES MIGRATION

## Current Inngest Functions (Already Implemented)
| Function | Schedule | Target Table |
|----------|----------|--------------|
| `zlPrice` | Every 15 min | `analytics.zl_live` |
| `yahooEod` | Daily 5PM ET | `raw.market_futures_1d` |
| `fredDaily` | Daily 10AM ET (Mon-Fri) | `raw.fred_observations_1d` |
| `cftcWeekly` | Weekly Tuesday | `raw.cftc_cot_1w` |

---

## NEWS SOURCES TO MIGRATE (from ingest_news_sources.py)

### Priority 0 - Critical (Every 2 hours)
| source_id | name | type | url | specialist |
|-----------|------|------|-----|------------|
| farm_policy_news | Farm Policy News | rss | https://farmpolicynews.illinois.edu/feed/ | crush |
| farmdoc_daily | FarmDoc Daily | rss | https://farmdocdaily.illinois.edu/feed | crush |
| reuters_commodities | Reuters Commodities | rss | https://www.reutersagency.com/feed/?best-topics=commodities&post_type=best | crush |
| usda_press | USDA Press Releases | rss | https://www.usda.gov/rss/latest-releases.xml | crush |
| dtn_progressive | DTN Progressive Farmer | scrape | https://www.dtnpf.com/agriculture/web/ag/home | crush |
| soybean_corn_advisor | Soybean & Corn Advisor | scrape | https://www.soybeansandcorn.com | crush |

### Priority 1 - High (Every 4 hours)
| source_id | name | type | url | specialist |
|-----------|------|------|-----|------------|
| agrimoney_grains | Agrimoney Grains | rss | https://www.agrimoney.com/rss/grains-oilseeds | crush |
| agweb_soybeans | AgWeb Soybeans | rss | https://www.agweb.com/rss/news/crops/soybeans | crush |
| farm_progress | Farm Progress | rss | https://www.farmprogress.com/rss.xml | crush |
| reuters_china | Reuters China | rss | https://www.reutersagency.com/feed/?best-regions=asia&post_type=best | china |
| agrimoney_china | Agrimoney China | scrape | https://www.agrimoney.com/news/china/ | china |
| fed_news | Federal Reserve News | rss | https://www.federalreserve.gov/feeds/press_all.xml | fed |
| whitehouse_briefing | White House Briefing | rss | https://www.whitehouse.gov/briefing-room/statements-releases/feed/ | tariff |
| ustr_press | USTR Press | scrape | https://ustr.gov/about-us/policy-offices/press-office/press-releases | tariff |
| eia_today | EIA Today in Energy | rss | https://www.eia.gov/rss/todayinenergy.xml | energy |
| epa_news | EPA News Releases | rss | https://www.epa.gov/newsreleases/search/rss | biofuel |
| mpob_news | MPOB Malaysia | scrape | https://www.mpob.gov.my/ | palm |
| gapki | GAPKI Indonesia | scrape | https://gapki.id/en/news/ | palm |
| canola_council | Canola Council News | scrape | https://www.canolacouncil.org/news/ | substitutes |
| oilseed_grain | Oilseed & Grain News | scrape | https://www.oilseedandgrain.com/ | substitutes |
| whitehouse_eo | White House Executive Orders | scrape | https://www.whitehouse.gov/presidential-actions/ | trump_effect |
| federal_register_eo | Federal Register Executive Orders | api | https://www.federalregister.gov/api/v1/documents.json?conditions[presidential_document_type][]=executive_order&per_page=20 | trump_effect |
| truth_social | Truth Social Trump | scrapecreators | https://api.scrapecreators.com/v1/truthsocial/user/realDonaldTrump/posts | trump_effect |

### Priority 2 - Medium (Every 6 hours)
| source_id | name | type | url | specialist |
|-----------|------|------|-----|------------|
| agriculture_com | Agriculture.com | rss | https://www.agriculture.com/rss/news/crops | crush |
| world_grain | World Grain | rss | https://www.world-grain.com/rss | crush |
| mofcom | MOFCOM Trade News | scrape | http://english.mofcom.gov.cn/ | china |
| ecb_press | ECB Press Releases | scrape | https://www.ecb.europa.eu/press/pr/html/index.en.html | fx |
| fed_speeches | Federal Reserve Speeches | scrape | https://www.federalreserve.gov/newsevents/speeches.htm | fed |
| federal_register_tariffs | Federal Register Tariffs | api | https://www.federalregister.gov/api/v1/documents.json?conditions[term]=tariff&conditions[type][]=RULE&per_page=20 | tariff |
| eia_petroleum | EIA Petroleum News | rss | https://www.eia.gov/rss/petroleum.xml | energy |
| biodiesel_mag | Biodiesel Magazine | rss | http://www.biodieselmagazine.com/rss/ | biofuel |
| palm_oil_today | Palm Oil Today | scrape | https://www.palmoiltoday.net/ | palm |
| rspo_news | RSPO News | scrape | https://rspo.org/news-and-events/ | palm |
| tradingec_palm | TradingEcon Palm Oil | scrape | https://tradingeconomics.com/commodity/palm-oil | palm |
| cboe_insights | CBOE Insights | scrape | https://www.cboe.com/insights/ | volatility |
| sunflower_nsa | National Sunflower Association | scrape | https://www.sunflowernsa.com/ | substitutes |
| ice_canola | ICE Canola Futures | scrape | https://www.theice.com/products/251/Canola-Futures | substitutes |
| tradingec_canola | TradingEcon Canola | scrape | https://tradingeconomics.com/commodity/canola | substitutes |
| tradingec_sunflower | TradingEcon Sunflower Oil | scrape | https://tradingeconomics.com/commodity/sunflower-oil | substitutes |
| tradingec_rapeseed | TradingEcon Rapeseed | scrape | https://tradingeconomics.com/commodity/rapeseed | substitutes |
| politico_trade | Politico Trade | scrape | https://www.politico.com/trade | trump_effect |

---

## SOCIAL MEDIA SOURCES (from scrape_social_intel.py)

### HIGH_ALPHA - Every 5 minutes (Market-moving)
**Trump Administration & Executive:**
- realDonaldTrump, DonaldJTrumpJr, EricTrump, POTUS, VP, WhiteHouse → trump_effect

**Trade Policy:**
- USTR, USTreasury, SecYellen → tariff

**Immigration/Labor:**
- ICEgov, CBP, DHSgov → trump_effect

**China State Media & Trade:**
- MOFCOMChina, GACC_China, cofcointl, sinochem_news, sinograin_china, MFA_China, ChinaEmbinUS → china

### REGULATORY - Every 15 minutes
**US Agriculture:**
- USDA, SecVilsack, USDA_NASS → crush

**Biofuel/Energy Policy:**
- EPA, EnergyGov, CleanFuelsDA, BiodieselNow, EthanolRFA, CARB → biofuel/energy

**Exchanges:**
- CMEGroup, ICE_Markets, nasdaq, CBOTExchange → volatility/crush

**Congress Ag Committees:**
- SenateAg, HouseAg, ChairmanThompson, SenBooker, etc. → tariff

**Brazil Agriculture:**
- MinAgricultura, abioveoficial, AprosojaBrasil, conab_oficial, anpbrasil, ubrabio → crush/biofuel

**Argentina Agriculture:**
- CIARA_CEC, ArgentinaGob, BCRAmercados, MAGyPArgentina, INDEC_Argentina → crush

**Palm Oil:**
- mpobmalaysia, gapki_id, icopalmoil → palm

**EU Policy:**
- EU_Commission, EU_CouncilEU → tariff

**China State Media:**
- CCTVNews, XinhuaNews, PDChina, CGTNOfficial, ChinaDaily → china

### DISCOVERY - Every 60 minutes
**Commodity Majors:**
- ADMCorp, BungeGlobal, Cargill, LouisDreyfus, Viterra_Global → crush

**US Farm Associations:**
- FarmBureau, NationalCorn, ASA_Soybeans, NOPA_News → crush

**Ag Media:**
- corn_soydigest, SuccessfulFarm, FarmProgress, AgWeb, dtnpf → crush

**Weather:**
- NOAA, NWS, NOAAClimate, WorldWeather, AccuWeather → crush

**Think Tanks:**
- Heritage, AEI, BrookingsInst, CatoInstitute → tariff

**Financial Media:**
- CNBC, BloombergNews, Reuters, WSJ, MarketWatch, FT → volatility

### ANALYST TWITTER (Priority 1)
| handle | name | specialist |
|--------|------|------------|
| kannbwx | Karen Braun | crush |
| ArlanFF101 | Arlan Suderman | crush |
| ScottIrwinUIUC | Scott Irwin | biofuel |
| SoybeanCorn | Dr. Michael Cordonnier | crush |
| JavierBlas | Javier Blas | energy |

---

## TARGET TABLE
All news/social content goes to: `raw.news_articles_1d`

Required columns:
- as_of_date (date)
- headline (text)
- content (text)
- source (text)
- bucket_name (text) - specialist name
- zl_sentiment (float)
- is_trump_related (boolean)
- content_hash (varchar 64) - for deduplication
- url (text)
- ingested_at (timestamptz)

---

## INNGEST FUNCTION DESIGN

### Recommended New Functions:

1. **newsRss** - Fetch all RSS feeds
   - Cron: `0 6,8,10,12,14,16,18,20,22 * * *` (every 2 hours market hours)
   - Sources: All RSS type sources
   - Use `fetch()` + RSS parsing

2. **newsApi** - Fetch Federal Register API
   - Cron: `0 */4 * * *` (every 4 hours)
   - Sources: federal_register_tariffs, federal_register_eo
   - Direct JSON API calls

3. **socialTwitter** - Twitter/X via ScrapeCreators
   - Cron: `*/15 * * * *` (every 15 minutes)
   - Requires: SCRAPECREATORS_API_KEY
   - HIGH_ALPHA handles (5 min in production, 15 min for MVP)

4. **socialTruthSocial** - Truth Social via ScrapeCreators
   - Cron: `*/5 * * * *` (every 5 minutes)
   - Requires: SCRAPECREATORS_API_KEY
   - Just Trump handle

---

## ENVIRONMENT VARIABLES NEEDED
- DATABASE_URL (already have)
- FRED_API_KEY (already have)
- SCRAPECREATORS_API_KEY (for Twitter/Truth Social)

---

## NOTES
- Web scraping (`type: scrape`) is harder in Inngest - consider using RSS alternatives or API where possible
- ScrapeCreators handles Twitter/Truth Social - need API key
- Facebook/LinkedIn endpoints not available in ScrapeCreators basic tier
- Priority 0/1 sources are most important for MVP
