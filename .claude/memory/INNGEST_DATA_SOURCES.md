NOTE: Production is the dashboard/frontend, not the repo root.
# INNGEST DATA SOURCES MIGRATION
Forward fill policy: [Docs/FORWARD_FILL_POLICY.md](Docs/FORWARD_FILL_POLICY.md)


**Last Updated:** 2026-01-18 (Institutional Schema Migration)

## Current Inngest Functions (Already Implemented)
| Function | Schedule | Target Table |
|----------|----------|--------------|
| `zlPrice` | Every 15 min | `analytics.zl_price_15m` |
| `yahooEod` | Daily 5PM ET | `mkt.futures_1d` |
| `fredDaily` | Daily 10AM ET (Mon-Fri) | `econ.rates_1d` |
| `cftcWeekly` | Weekly Tuesday | `pos.cftc_1w` |

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
All news/social content goes to: `alt.news_1d`

Required columns:
- event_date (date) - when the article was published
- title (text) - article headline
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

---

# COMPREHENSIVE FEED REGISTRY (GPT-Verified Sources)

## POLLING STRATEGY (LOCKED)
| Asset | Frequency | Cron |
|-------|-----------|------|
| **ZL Price** | Every 15 min | `*/15 * * * *` |
| **Everything else** | 2x daily | `0 8,16 * * *` (8 AM & 4 PM CT) |

---

## CONGRESS.GOV RSS (Verified - Real URLs)

| feed_id | name | url | specialist_tags | cadence |
|---------|------|-----|-----------------|--------|
| `congress_most_viewed_bills` | Most-Viewed Bills | `https://www.congress.gov/rss/most-viewed-bills.xml` | trump_effect, policy, tariff, biofuel, crush | event |
| `congress_house_floor_today` | House Floor Today | `https://www.congress.gov/rss/house-floor-today.xml` | policy, tariff, biofuel, crush | event |
| `congress_senate_floor_today` | Senate Floor Today | `https://www.congress.gov/rss/senate-floor-today.xml` | policy, tariff, biofuel, crush | event |
| `congress_presented_to_president` | Bills Presented to President | `https://www.congress.gov/rss/presented-to-president.xml` | trump_effect, policy, tariff | event |

**Target:** `alt.legislation_event`

---

## COMMITTEE SCRAPES (No RSS Available)

| feed_id | name | url | specialist_tags | type |
|---------|------|-----|-----------------|------|
| `house_ag_news` | House Agriculture Committee | `https://agriculture.house.gov/news/documentquery.aspx` | crush, biofuel, policy | scrape |
| `senate_ag_majority_news` | Senate Ag - Majority | `https://www.agriculture.senate.gov/newsroom/majority-news` | crush, biofuel, policy | scrape |
| `senate_ag_minority_news` | Senate Ag - Minority | `https://www.agriculture.senate.gov/newsroom/minority-news` | crush, biofuel, tariff | scrape |
| `ways_means_trade_news` | Ways & Means - Trade | `https://waysandmeans.house.gov/news/` | tariff, trump_effect, policy | scrape |

**Target:** `alt.legislation_event`

**Filter Rules:**
```json
{
  "must_include_any": ["tariff", "trade", "301", "farm", "commodity", "crop", "biofuel", "renewable", "RFS", "soy", "oilseed"],
  "must_exclude_any": ["internship", "photo", "congratulations"]
}
```

---

## FEDERAL REGISTER API (Targeted - Not RSS)

| feed_id | name | url | type |
|---------|------|-----|------|
| `federal_register_targeted` | Federal Register (RULE + PRESDOCU) | `https://www.federalregister.gov/api/v1/documents.json` | api |

**Target:** `alt.legislation_event`
**Specialist Tags:** trump_effect, policy, tariff, biofuel, energy, crush

**Filter Rules:**
```json
{
  "doc_types": ["RULE", "PRESDOCU"],
  "presidential_document_types": ["executive_order", "proclamation", "memorandum", "determination", "notice"],
  "agencies_any": ["Agriculture Department", "U.S. Trade Representative", "Environmental Protection Agency", "Department of Energy", "Foreign Agricultural Service", "Commodity Futures Trading Commission"],
  "keywords_any": ["soy", "soybean", "vegetable oil", "biofuel", "biodiesel", "renewable fuel", "RFS", "45Z", "tariff", "section 301", "countervailing", "antidumping", "China", "import", "export", "sanctions", "EPA RIN", "EMTS"]
}
```

---

## EIA RSS FEEDS (5 Verified)

| feed_id | name | url | cadence | specialist_tags |
|---------|------|-----|---------|----------------|
| `eia_wpsr` | Weekly Petroleum Status Report | `https://www.eia.gov/rss/weekly_petroleum.xml` | _1w | energy, biofuel |
| `eia_today_in_energy` | Today in Energy | `https://www.eia.gov/rss/todayinenergy.xml` | _event | energy |
| `eia_press_releases` | EIA Press Releases | `https://www.eia.gov/rss/press_releases.xml` | _event | energy |
| `eia_steo` | Short-Term Energy Outlook | `https://www.eia.gov/rss/steo.xml` | _1m | energy |
| `eia_petroleum` | Petroleum & Liquids | `https://www.eia.gov/rss/petroleum.xml` | _event | energy |

**Target:** `supply.eia_*_event` or `supply.eia_*_1w`

**Note:** RSS for event detection only. Use EIA API for numeric inventory series.

---

## REGULATORY / POLICY FEEDS

| feed_id | name | url | type | specialist_tags |
|---------|------|-----|------|----------------|
| `govinfo_feeds` | GovInfo RSS Registry | `https://www.govinfo.gov/feeds` | scrape | policy, trump_effect |
| `oira_eo_review` | OIRA EO Submissions | `https://www.reginfo.gov/public/do/eoReviewSearch` | scrape | trump_effect, policy |
| `whitehouse_briefing` | White House Briefings | `https://www.whitehouse.gov/briefing-room/feed/` | rss | trump_effect, policy |

**Target:** `alt.legislation_event` (consolidated from whitehouse, oira, govinfo)

---

## BIOFUEL FEEDS (Verified)

| feed_id | name | url | type | legal_risk |
|---------|------|-----|------|------------|
| `biofuels_digest` | Biofuels Digest | `https://www.biofuelsdigest.com/bdigest/feed/` | rss | medium |
| `clean_fuels_alliance` | Clean Fuels Alliance | `https://cleanfuels.org/feed/` | rss | low |

**Target:** `alt.legislation_event` (biofuel policy)

---

## PALM OIL / ASIA FEEDS

| feed_id | name | url | type | legal_risk |
|---------|------|-----|------|------------|
| `thestar_business` | The Star (Malaysia) | `https://www.thestar.com.my/RSS` | rss | **HIGH** |
| `scmp_rss` | SCMP Directory | `https://www.scmp.com/rss` | rss | medium |
| `jakarta_post` | Jakarta Post | `https://www.thejakartapost.com/rss` | rss | medium |
| `mpob_malaysia` | MPOB Malaysia | `https://www.mpob.gov.my/rss` | rss | low |

**Target:** `alt.news_event` (palm oil, china trade)

**⚠️ The Star has restrictive terms - HIGH risk unless licensed**

---

## CHINA FEEDS

| feed_id | name | url | type | notes |
|---------|------|-----|------|-------|
| `xinhua_business` | Xinhua Business | `http://www.xinhuanet.com/english/rss/businessrss.xml` | rss | Official state media |
| `scmp_commodities` | SCMP Commodities | Select from `https://www.scmp.com/rss` | rss | Pick topic feed |
| `caixin_global` | Caixin Global | `https://www.caixinglobal.com/rss/feed.xml` | rss | May need verification |

**Target:** `alt.news_event` (china trade)

---

## MACRO / INSTITUTIONAL RESEARCH (Reference Only)

| source | url | notes |
|--------|-----|-------|
| IEA News | `https://www.iea.org/rss/news.xml` | Macro energy context |
| IEA Reports | `https://www.iea.org/rss/reports.xml` | Balance modeling |
| World Bank | `https://www.worldbank.org/en/news/all?feed=rss` | Global macro |
| OECD | `https://www.oecd.org/newsroom/rss.xml` | Policy context |

**Note:** Not for price prediction - regime/context signals only.

---

## LICENSED / PAYWALLED (DO NOT SCRAPE)

| source | status | action |
|--------|--------|--------|
| ChAI | Licensed only | Benchmark comparator, not ingestable |
| Bloomberg Terminal | Licensed only | No free RSS for commodities |
| Oil World | Licensed only | Paid PDF reports |
| Reuters Premium | Licensed only | LSEG products |

**These require commercial agreements - mark `enabled = false` in registry**

---

## metadata.feed REGISTRY SCHEMA

```sql
CREATE TABLE metadata.feed (
  feed_id            VARCHAR PRIMARY KEY,
  source_id          VARCHAR NOT NULL,
  name               VARCHAR NOT NULL,
  description        TEXT,
  feed_url           TEXT NOT NULL,
  feed_type          VARCHAR NOT NULL,   -- rss | api | scrape | licensed
  enabled            BOOLEAN DEFAULT TRUE,
  cadence            VARCHAR NOT NULL,   -- event | 1h | 1d | 1w | 1m | static
  target_table       VARCHAR NOT NULL,
  specialist_tags    TEXT[] NOT NULL,
  cron               VARCHAR NOT NULL,
  release_tz         VARCHAR DEFAULT 'America/Chicago',
  release_window     JSONB,
  freshness_sla_min  INTEGER DEFAULT 1440,
  filter_rules       JSONB DEFAULT '{}',
  guid_strategy      VARCHAR DEFAULT 'guid_or_link_hash',
  item_hash_fields   TEXT[] DEFAULT ARRAY['guid','link','title','published'],
  parser_profile     VARCHAR DEFAULT 'rss_v2',
  legal_risk         VARCHAR DEFAULT 'low',
  license_note       TEXT,
  failure_policy     JSONB DEFAULT '{"retries":3,"backoff":"exp2"}',
  http_etag          TEXT,
  http_last_modified TEXT,
  last_polled_at     TIMESTAMPTZ,
  last_success_at    TIMESTAMPTZ
);
```

---

## INNGEST PULL ENGINE CONTRACT

### Single Job Class: `ingest:feed:pull`

**Event:**
```typescript
type FeedPullEvent = {
  name: "feed/pull";
  data: {
    feed_id?: string;        // pull one feed
    cadence?: "event" | "1w"; // or pull all by cadence
    force?: boolean;         // bypass freshness SLA
  };
};
```

**Behavior:**
1. Load feeds from `metadata.feed` where `enabled = true`
2. Check freshness SLA (skip if recent)
3. Create `ops.ingest_run` record
4. Fetch by `feed_type` (rss/api/scrape)
5. Apply `filter_rules` to items
6. Normalize → Bronze row with PIT semantics
7. Dedupe via `row_hash`
8. Handle revisions via `revision_no` + `supersedes_id`
9. Quarantine bad rows to `ops.quarantined_record`
10. Complete `ops.ingest_run` with stats

**Cron Triggers:**
```typescript
// Event feeds - 2x daily
inngest.createFunction(
  { id: "cron:feed:event" },
  { cron: "0 8,16 * * *" },  // 8 AM & 4 PM CT
  async () => inngest.send({ name: "feed/pull", data: { cadence: "event" } })
);

// Weekly feeds - aligned to release windows
inngest.createFunction(
  { id: "cron:feed:weekly" },
  { cron: "0 12 * * 3" },  // Wed noon CT (EIA WPSR)
  async () => inngest.send({ name: "feed/pull", data: { cadence: "1w" } })
);
```

---

## TOTAL FEED INVENTORY

| Category | Count | Type |
|----------|-------|------|
| Congress.gov RSS | 4 | rss |
| Committee scrapes | 4 | scrape |
| Federal Register | 1 | api |
| EIA | 5 | rss |
| Regulatory/Policy | 3 | mixed |
| Biofuel | 2 | rss |
| Palm/Asia | 4 | rss |
| China | 3 | rss |
| Macro/Institutional | 4 | rss |
| News (from scripts) | 42 | mixed |
| Social (Twitter) | 100+ | scrapecreators |
| **TOTAL** | **170+** | - |

---

## NEXT STEPS

1. Create `metadata.feed` table in Prisma Postgres
2. Seed with all verified feeds (start with RSS, skip scrapes)
3. Build single `ingest:feed:pull` Inngest function
4. Kill individual hardcoded jobs
5. Add `ops.feed_health` monitoring