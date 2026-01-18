# RAW SOURCE → SPECIALIST MAPPING

**Status**: LOCKED - This is the authoritative mapping
**Date**: January 11, 2026
**VSClaude Track**: A - URL Load-ins & Inngest Jobs

> NOTE (2026-01-17): Schema v2 deprecates raw sources. This mapping remains
> authoritative for routing but table references are legacy until migration.

**Changelog:**
- 2026-01-11: CRITICAL FIX - Separated TARIFF and TRUMP_EFFECT specialists
  - EPUTRADE (Trade Policy Uncertainty) → `tariff` only
  - USEPUINDXD (Overall EPU) → `trump_effect` + `volatility` (regime uncertainty + stress)
  - Section 301/232 → `tariff` only (specific trade mechanisms)
  - Executive Orders, Immigration/ICE → `trump_effect` + `legislation`
  - Trade deals → BOTH `tariff` + `trump_effect` (specifics + regime signal)
  - NOTE: EPU chart shows unprecedented spike 2020-2025 - THIS IS the Trump Effect in data form

---

## ⚠️ CRITICAL: TARIFF vs TRUMP_EFFECT SEPARATION

**These are TWO DIFFERENT specialists. DO NOT confuse them.**

| Specialist | What It Tracks | Data Sources | Tag |
|------------|----------------|--------------|-----|
| **TARIFF** | Specific trade policy mechanisms | Section 301/232, EPUTRADE, tariff rates, exclusions | `tariff` |
| **TRUMP_EFFECT** | Regime uncertainty & policy volatility | USEPUINDXD, Executive Orders, DJT stock, immigration | `trump_effect` |

**Decision Tree:**
- Is it a SPECIFIC trade mechanism (tariff rate, section 301, exclusion list)? → `tariff`
- Is it REGIME uncertainty or presidential action? → `trump_effect`
- Is it BOTH (trade deal announcement)? → `tariff`, `trump_effect`

**EPU Index Split:**
- `EPUTRADE` = Trade-specific uncertainty → `tariff` ONLY
- `USEPUINDXD` = Overall policy uncertainty → `trump_effect`, `volatility`

---

## 🔑 API KEYS AVAILABLE

**In Vercel Production Environment:**
```bash
FRED_API_KEY=dc195c8658c46ee1df83bcd4fd8a690b
NOAA_TOKEN=rxoLrCxYOlQyWvVjbBGRlMMhIRElWKZi
SCRAPECREATORS_API_KEY=B1TOgQvMVSV6TDglqB8lJ2cirqi2
INNGEST_EVENT_KEY=[set]
INNGEST_SIGNING_KEY=[set]
DATABASE_URL=[in .env.local]
```

**Missing - Need to Obtain:**
```bash
EIA_API_KEY=           # For eia-inventories.ts, eia-production.ts
CONGRESS_API_KEY=      # For congress.ts
```

---

## 📋 BRONZE v2.0 JOB TEMPLATE

**Reference:** `frontend/src/inngest/fred-daily.ts`

Every new job MUST follow this pattern:

```typescript
import { inngest } from "./client";
import { Pool } from "pg";
import { createHash } from "crypto";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// 1. Helper: Create ingest run (logs to ops.ingest_run)
async function createIngestRun(client: any, jobName: string): Promise<string> {
  const result = await client.query(
    `INSERT INTO ops.ingest_run (job_name, started_at, status, rows_attempted, rows_inserted, rows_skipped, rows_quarantined)
     VALUES ($1, NOW(), 'running', 0, 0, 0, 0)
     RETURNING id`,
    [jobName]
  );
  return result.rows[0].id;
}

// 2. Helper: Update ingest run on completion
async function updateIngestRun(
  client: any,
  runId: string,
  status: string,
  attempted: number,
  inserted: number,
  skipped: number,
  quarantined: number,
  errorMessage?: string
): Promise<void> {
  await client.query(
    `UPDATE ops.ingest_run SET
       status = $2, completed_at = NOW(),
       rows_attempted = $3, rows_inserted = $4,
       rows_skipped = $5, rows_quarantined = $6,
       error_message = $7
     WHERE id = $1`,
    [runId, status, attempted, inserted, skipped, quarantined, errorMessage || null]
  );
}

// 3. Helper: Compute row hash for idempotency
function computeRowHash(parts: string[]): string {
  return createHash("sha256").update(parts.join("|")).digest("hex");
}

export const myJob = inngest.createFunction(
  { id: "job-name", name: "Job Display Name", retries: 3 },
  { cron: "0 11 * * 1-5" }, // 5AM CT = 11 UTC, Mon-Fri
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;
    let rowsAttempted = 0, rowsInserted = 0, rowsSkipped = 0, rowsQuarantined = 0;

    try {
      // Step 1: Create ingest run
      runId = await step.run("create-ingest-run", async () => {
        return await createIngestRun(client, "job-name");
      });

      // Step 2: Fetch and insert data
      await step.run("fetch-and-insert", async () => {
        // ... fetch from API ...
        
        for (const record of records) {
          rowsAttempted++;
          
          // Compute row_hash
          const rowHash = computeRowHash([record.key1, record.key2, String(record.value)]);
          
          // Check if exists
          const exists = await client.query(
            "SELECT 1 FROM raw.table_name WHERE row_hash = $1",
            [rowHash]
          );
          
          if (exists.rows.length > 0) {
            rowsSkipped++;
            continue;
          }
          
          // Insert with ALL Bronze columns
          await client.query(
            `INSERT INTO raw.table_name (
               event_date, key_col, value_col,
               knowledge_time, revision_no, supersedes_id, is_preliminary,
               validation_status, quality_score, anomaly_flags,
               source_url, raw_payload, ingestion_batch_id, row_hash, specialist_tags
             ) VALUES (
               $1, $2, $3,
               NOW(), 1, NULL, false,
               'valid', 1.0, '{}',
               $4, $5, $6, $7, $8
             )`,
            [
              record.date, record.key, record.value,
              sourceUrl, JSON.stringify(record), runId, rowHash,
              ["specialist1", "specialist2"]  // ASSIGN TAGS HERE
            ]
          );
          rowsInserted++;
        }
      });

      // Step 3: Complete ingest run
      await step.run("complete-ingest-run", async () => {
        await updateIngestRun(client, runId!, "success", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined);
      });

      return { status: "success", runId, inserted: rowsInserted };

    } catch (error) {
      if (runId) {
        await updateIngestRun(client, runId, "failed", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined, String(error));
      }
      throw error;
    } finally {
      client.release();
    }
  }
);
```

**Cron Schedule Standard:** `0 11 * * 1-5` = 5AM CT Mon-Fri (daily jobs)

---

## 📁 FILE LOCATIONS

```
frontend/src/inngest/
├── client.ts           # Inngest client config
├── functions.ts        # Export all functions (ADD NEW ONES HERE)
├── fred-daily.ts       # ✅ REFERENCE - Bronze v2.0 pattern
├── yahoo-eod.ts        # Needs Bronze upgrade
├── cftc-weekly.ts      # Needs Bronze upgrade  
├── zl-price.ts         # Live price (different pattern)
└── sources/
    └── markets/
        └── crowd-beliefs.ts  # Needs replacement
```

**After creating new job:**
1. Add export to `functions.ts`
2. Add to functions array in `app/api/inngest/route.ts`
3. Git commit and push (triggers Vercel deploy)

---

## ⚠️ NAMING CONTRACT (LOCKED)

**Read full contract:** `Docs/BRONZE_NAMING_CONTRACT_LOCKED.md`

**Allowed cadence suffixes ONLY:**
- `_1h` - Hourly
- `_1d` - Daily
- `_1w` - Weekly
- `_1m` - Monthly
- `_event` - Irregular/event-time (press releases, notices, actions)
- `_static` - Reference/dimension data

**FORBIDDEN:** `_1y`, `_archive`, `_hist`, `_bronze`, `_silver`, `_daily`, `_weekly`

**Grammar:** `raw.<provider>_<dataset>_<cadence>`

**Examples:**
- ✅ `raw.whitehouse_actions_event`
- ✅ `raw.legislation_federal_register_1d`
- ❌ `raw.news_articles_archive` (should be `_event`)
- ❌ `raw.usda_nass_1y` (should be `_event`)

---

## PRINCIPLE

1. RAW = Organized by DATA SOURCE (not specialist)
2. Each raw record gets `specialist_tags[]` at ingestion
3. Specialists are ASSIGNED data via these tags (deterministic, not AI deciding)
4. Pulse drops are a feature source alongside raw data
5. NO duplication - specialists PICK from shared raw tables

---

## RAW TABLES & SPECIALIST TAGS

### MARKET

| Table | Source | Inngest Job | Tags | Status |
|-------|--------|-------------|------|--------|
| `raw.market_futures_1d` | Yahoo/Databento | yahoo-eod.ts | Per symbol below | ✅ EXISTS |
| `raw.market_futures_1h` | Databento | TBD | Per symbol below | ✅ EXISTS |
| `raw.fx_spot_1d` | FRED | fred-daily.ts | fx | ✅ EXISTS |
| `raw.yahoo_equity_1d` | Yahoo | yahoo-eod.ts | Per symbol below | ✅ EXISTS |
| `raw.options_futures_1d` | Databento | TBD | volatility | ✅ EXISTS |

**Futures Symbol → Tags:**
| Symbol | Tags |
|--------|------|
| ZL | core, crush |
| ZS | core, crush |
| ZM | core, crush |
| CL | core, energy |
| HO | core, energy, biofuel |
| RB | energy |
| NG | energy |
| HG | china |
| CPO/FCPO | palm |
| W (canola) | substitutes |

**Equity Symbol → Tags:**
| Symbol | Tags | Reasoning |
|--------|------|----------|
| DJT | trump_effect | Trump Media - regime proxy |
| FXI | china | China large-cap ETF - demand signal |
| KWEB | china | China internet ETF - demand signal |

---

### ECONOMIC

| Table | Source | Inngest Job | Status |
|-------|--------|-------------|--------|
| `raw.fred_observations_1d` | FRED API | fred-daily.ts | ✅ EXISTS |
| `raw.fred_series_metadata` | FRED API | fred-daily.ts | ✅ EXISTS |

**FRED Series → Tags:**
| Series Pattern | Tags | Reasoning |
|----------------|------|----------|
| DEXBZUS, DEXARUS, DTWEX* | fx | Currency exchange rates |
| DEXCHUS | fx, china | CNY specifically tracks China |
| DFF, FEDFUNDS, DGS*, T10Y2Y | fed | Interest rates, yields |
| VIXCLS, STLFSI4, NFCI, BAMLH* | volatility | Market stress indicators |
| USEPUINDXD | trump_effect, volatility | Regime uncertainty (Trump Effect) + stress indicator |
| EPUTRADE | tariff | Trade policy uncertainty specifically |
| CPIAUCSL, PCEPI, UNRATE | fed | Inflation, employment |
| DCOILWTICO, DCOILBRENTEU | energy | Crude oil prices |

---

### AGRICULTURE

| Table | Source | Inngest Job | Tags | Status |
|-------|--------|-------------|------|--------|
| `raw.usda_wasde_1m` | USDA (Cornell mirror) | `usda-wasde-monthly.ts` | crush, china | ✅ EXISTS |
| `raw.usda_export_sales_1w` | USDA FAS | `usda-export-sales-weekly.ts` | crush, china | ✅ EXISTS |
| `raw.agriculture_nopa_1m` | NOPA | TBD | crush | ❌ MISSING |
| `raw.agriculture_conab_1w` | CONAB | TBD | crush | ❌ MISSING |

---

### ENERGY

| Table | Source | Inngest Job | Tags | Status |
|-------|--------|-------------|------|--------|
| `raw.epa_rin_prices_1d` | EPA (Qlik) | `epa-rin-prices-daily.ts` | biofuel | ✅ EXISTS |
| `raw.energy_eia_inventories_1w` | EIA | TBD | energy | ❌ MISSING |
| `raw.energy_eia_production_1m` | EIA | TBD | energy, biofuel | ❌ MISSING |

---

### LEGISLATION (ALL POLICY)

| Table | Source | Inngest Job | Status |
|-------|--------|-------------|--------|
| `raw.legislation_whitehouse_1d` | whitehouse.gov | whitehouse.ts | ❌ MISSING |
| `raw.legislation_federal_register_1d` | federalregister.gov/api | federal-register.ts | ❌ MISSING |
| `raw.legislation_ustr_1d` | ustr.gov | ustr.ts | ❌ MISSING |
| `raw.legislation_epa_1d` | epa.gov | epa.ts | ❌ MISSING |
| `raw.legislation_congress_1d` | congress.gov | congress.ts | ❌ MISSING |
| `raw.legislation_ice_1d` | ice.gov/dhs.gov | ice.ts | ❌ MISSING |

**Legislation Topic → Tags:**
| Topic Keywords | Tags | Reasoning |
|----------------|------|----------|
| section_301, section_232, tariff_rate, tariff_schedule | tariff | Specific trade mechanisms |
| trade_deal, trade_agreement, trade_negotiation | tariff, trump_effect | Both specifics + regime signal |
| executive_order, presidential_action, presidential_memorandum | trump_effect | Regime shifts |
| immigration, ice, deportation, visa, border | trump_effect, legislation | Regime + legislative action |
| rfs, rin, biodiesel, 45z, lcfs, renewable_fuel | biofuel | Renewable fuel policy |
| sanctions, ofac | tariff, china | Trade restriction mechanism |
| doge, government_efficiency | trump_effect | Administration signal |
| china, prc (trade context) | china, tariff | China + trade policy |
| epa, environment, emissions | biofuel | Environmental policy |

---

### TRADE FLOWS

| Table | Source | Inngest Job | Tags | Status |
|-------|--------|-------------|------|--------|
| `raw.trade_gacc_china_1m` | GACC customs | gacc.ts | china | ❌ MISSING |
| `raw.trade_mpob_palm_1m` | MPOB | mpob.ts | palm | ❌ MISSING |
| `raw.trade_usitc_1m` | USITC | usitc.ts | tariff | ❌ MISSING |

---

### POSITIONING

| Table | Source | Inngest Job | Tags | Status |
|-------|--------|-------------|------|--------|
| `raw.cftc_cot_1w` | CFTC | cftc-weekly.ts | Per symbol | ✅ EXISTS |

**CFTC Symbol → Tags:**
| Symbol | Tags |
|--------|------|
| ZL, ZS, ZM | crush |
| CL, HO | energy |
| All symbols | volatility (aggregate positioning) |

---

### WEATHER

| Table | Source | Inngest Job | Tags | Status |
|-------|--------|-------------|------|--------|
| `raw.weather_noaa_1d` | NOAA | TBD | crush, palm | ✅ EXISTS |

---

### SENTIMENT

| Table | Source | Inngest Job | Tags | Status |
|-------|--------|-------------|------|--------|
| `raw.news_articles_1d` | Reuters, DTN, etc | TBD | Per topic | ✅ EXISTS |
| `raw.sentiment_social_1d` | Twitter, TruthSocial | TBD | Per topic | ❌ MISSING |
| `raw.sentiment_prediction_1d` | Polymarket | polymarket.ts | Per topic | ❌ MISSING |

**News/Social Topic → Tags:**
| Topic Keywords | Tags | Reasoning |
|----------------|------|----------|
| soybean, crush, oil_share, nopa | crush | Crush economics |
| china, import, cofco, sinograin | china | China demand |
| section_301, section_232, tariff_rate, tariff_exclusion | tariff | Specific trade policy |
| trade_war, trade_tension, trade_deal | tariff, trump_effect | Both policy + regime |
| biodiesel, renewable_diesel, rin, rfs | biofuel | Biofuel policy |
| palm, mpob, indonesia, malaysia | palm | Palm oil markets |
| crude, diesel, refinery, opec | energy | Energy complex |
| fed, fomc, rates, inflation | fed | Monetary policy |
| canola, sunflower, rapeseed | substitutes | Substitute oils |
| trump, executive_order, whitehouse, presidential | trump_effect | Regime signals |
| immigration, ice, deportation, border | trump_effect, legislation | Policy + regime |
| vix, volatility, risk_off | volatility | Market stress |

---

### INTELLIGENCE (Pulse Drops)

| Table | Source | Inngest Job | Status |
|-------|--------|-------------|--------|
| `intelligence.intel_drops` | Pulse Engine | pulse-engine.ts | ✅ EXISTS |

Each Intel Drop has `domain` field = specialist name. This is a feature source like raw data.

---

## SPECIALIST → TAG ASSIGNMENTS

| Specialist | Assigned Tags | Picks From |
|------------|---------------|------------|
| **CRUSH** | `crush` | market_futures (ZL,ZS,ZM), fred, usda_wasde, usda_export_sales, nopa, conab, cftc (ZL,ZS,ZM), news, intel_drops |
| **CHINA** | `china` | market_futures (HG), yahoo_equity (FXI,KWEB), fred, usda_export_sales, gacc, legislation, news, intel_drops |
| **FX** | `fx` | fx_spot, fred (DTWEX*, DEX*), intel_drops |
| **FED** | `fed` | fred (rates, yields, employment, inflation), legislation, news, intel_drops |
| **TARIFF** | `tariff` | legislation (section_301, section_232, trade_deals), usitc, fred (EPUTRADE), news (trade policy), intel_drops |
| **ENERGY** | `energy` | market_futures (CL,HO,RB,NG), fred, eia_inventories, eia_production, cftc, news, intel_drops |
| **BIOFUEL** | `biofuel` | epa_rin_prices, legislation (rfs topics), eia_production, market_futures (HO), news, intel_drops |
| **PALM** | `palm` | mpob, market_futures (FCPO), weather_noaa, news, intel_drops |
| **VOLATILITY** | `volatility` | fred (VIX, stress), options_futures, cftc (all - aggregate), news, intel_drops |
| **SUBSTITUTES** | `substitutes` | market_futures (canola), news, intel_drops |
| **TRUMP_EFFECT** | `trump_effect` | legislation (EO, immigration), yahoo_equity (DJT), fred (USEPUINDXD), sentiment_social, sentiment_prediction, news (regime), intel_drops |

---

## INNGEST JOBS NEEDED

### EXISTS (6)
- [x] cftc-weekly.ts
- [x] fred-daily.ts
- [x] yahoo-eod.ts
- [x] zl-price.ts
- [x] federal-register.ts → `raw.legislation_federal_register_1d` ✅ BUILT 2026-01-11
- [x] crowd-beliefs.ts (NEEDS FIX - remove cross-specialist routing)

### GOVERNMENT RSS (5) - HIGH PRIORITY (No API Key)
- [ ] whitehouse.ts → `raw.whitehouse_actions_event` (HOLD - Track B upgrading)
- [ ] ice-dhs.ts → `raw.ice_releases_event`, `raw.dhs_releases_event`
- [ ] cbp.ts → `raw.cbp_trade_event`
- [ ] ustr.ts → `raw.ustr_releases_event`
- [ ] epa.ts → `raw.epa_releases_event`

### AGRICULTURE NEWS (3) - HIGH PRIORITY
- [ ] agweb.ts → `raw.agweb_articles_event` (soybeans RSS)
- [ ] farmdoc.ts → `raw.farmdoc_articles_event` (RINs, ag policy)
- [ ] conab.ts → `raw.conab_news_event` (Brazil)

### SOCIAL MEDIA (1) - HIGH PRIORITY (Have SCRAPECREATORS_API_KEY)
- [ ] truthsocial.ts → `raw.truthsocial_posts_event`

### FED/RATES (1)
- [ ] nyfed.ts → `raw.nyfed_rates_1d`

### THINK TANKS (2)
- [ ] aei.ts → `raw.aei_articles_event`
- [ ] piie.ts → `raw.piie_articles_event`

### AGRICULTURE DATA (2)
- [ ] nopa.ts → `raw.nopa_crush_1m`
- [ ] usda-fas.ts → (export sales already exists)

### ENERGY (2) - BLOCKED (Need EIA_API_KEY)
- [ ] eia-inventories.ts → `raw.eia_inventories_1w`
- [ ] eia-production.ts → `raw.eia_production_1m`

### TRADE (3)
- [ ] gacc.ts → `raw.gacc_trade_1m` (China customs - complex)
- [ ] mpob.ts → `raw.mpob_palm_1m`
- [ ] usitc.ts → `raw.usitc_trade_1m`

### CONGRESS (1) - BLOCKED (Need CONGRESS_API_KEY)
- [ ] congress.ts → `raw.congress_bills_event`

---

## 📡 RSS FEEDS & API ENDPOINTS (VERIFIED)

### Government - No API Key Required

| Source | Endpoint | Type | Tags |
|--------|----------|------|------|
| **Federal Register** | `https://www.federalregister.gov/api/v1/documents.json` | JSON API | `legislation`, `tariff`, `trump_effect`, `biofuel` |
| **ICE Releases** | `https://www.ice.gov/rss` | RSS | `trump_effect`, `legislation` |
| **DHS Releases** | `https://www.dhs.gov/news-releases.xml` | RSS | `trump_effect`, `legislation` |
| **CBP Trade** | `https://www.cbp.gov/rss/trade` | RSS | `tariff`, `legislation` |
| **CBP Border** | `https://www.cbp.gov/rss/border-security` | RSS | `trump_effect`, `legislation` |
| **NY Fed Rates** | `https://markets.newyorkfed.org/api/rates/all/latest.json` | JSON API | `fed` |

### Agriculture News - RSS

| Source | Endpoint | Type | Tags |
|--------|----------|------|------|
| **AgWeb Soybeans** | `https://www.agweb.com/news/crops/soybeans/rss` | RSS | `crush` |
| **DTN Progressive Farmer** | `https://www.dtnpf.com/agriculture/web/rss/news` | RSS | `crush`, `china` |
| **Farm Progress** | `https://www.farmprogress.com/soybeans/feed/` | RSS | `crush` |
| **Agriculture.com** | `https://www.agriculture.com/markets-commodities.rss` | RSS | `crush`, `energy` |
| **Agrimoney Grains** | `https://www.agrimoney.com/rss/news` | RSS | `crush`, `palm` |
| **World-Grain** | `https://www.world-grain.com/rss` | RSS | `crush`, `substitutes` |
| **CONAB Brazil** | `https://www.conab.gov.br/rss` | RSS | `crush`, `china` |
| **Farmdoc Ag Policy** | `https://farmdocdaily.illinois.edu/category/areas/agricultural-policy/feed/` | RSS | `crush`, `tariff` |
| **Farmdoc RINs** | `https://farmdocdaily.illinois.edu/category/areas/biofuels/rins/feed/` | RSS | `biofuel` |

### Think Tanks - RSS

| Source | Endpoint | Type | Tags |
|--------|----------|------|------|
| **AEI Trade Policy** | `https://www.aei.org/tag/trade-policy/feed/` | RSS | `tariff`, `trump_effect` |
| **Heritage Agriculture** | `https://www.heritage.org/agriculture/rss` | RSS | `crush`, `tariff` |
| **America First Policy** | `https://americafirstpolicy.com/feed/` | RSS | `trump_effect`, `tariff` |
| **Tax Foundation Trade** | `https://taxfoundation.org/research/all/federal/trade/feed/` | RSS | `tariff` |
| **PIIE** | `https://www.piie.com/rss` | RSS | `tariff`, `china` |
| **CSIS Trade** | `https://www.csis.org/rss/programs` | RSS | `tariff`, `china` |
| **US-China Business** | `https://www.uschina.org/rss` | RSS | `china`, `tariff` |

### Social Media - API (Have SCRAPECREATORS_API_KEY)

| Source | Endpoint | Type | Tags |
|--------|----------|------|------|
| **Truth Social** | `https://api.scrapecreators.com/v1/truthsocial` | REST API | `trump_effect` |
| **Facebook Pages** | `https://api.scrapecreators.com/v1/facebook/post` | REST API | varies |
| **Reddit Agriculture** | `https://www.reddit.com/r/agriculture.json` | JSON | `crush` |

### Farm Organizations - RSS

| Source | Endpoint | Type | Tags |
|--------|----------|------|------|
| **American Farm Bureau** | `https://www.fb.org/feed/` | RSS | `crush`, `legislation` |
| **Soygrowers** | `https://soygrowers.com/feed/` | RSS | `crush` |
| **Farm Action** | `https://farmaction.us/feed/` | RSS | `crush`, `china` |
| **Western Growers** | `https://www.wga.com/rss.xml` | RSS | `crush` |

### Campaign/Political - RSS

| Source | Endpoint | Type | Tags |
|--------|----------|------|------|
| **Trump Campaign** | `https://www.donaldjtrump.com/news/feed/` | RSS | `trump_effect` |

### Market Data - API

| Source | Endpoint | Type | Tags |
|--------|----------|------|------|
| **TradingEconomics** | `https://api.tradingeconomics.com/calendar/country/{country}` | REST API | `fed`, `china` |
| **Polygon.io** | `https://api.polygon.io/v2/aggs/ticker/{ticker}/...` | REST API | `crush`, `energy` |

---

## URLS BY JOB

### whitehouse.ts
- https://www.whitehouse.gov/briefing-room/statements-releases/feed/ (RSS)
- https://www.whitehouse.gov/presidential-actions/ (scrape)

### federal-register.ts
- https://www.federalregister.gov/api/v1/documents.json?conditions[type][]=RULE&conditions[type][]=PRORULE&conditions[type][]=NOTICE&conditions[type][]=PRESDOCU

### ustr.ts
- https://ustr.gov/about-us/policy-offices/press-office (scrape)
- https://ustr.gov/issue-areas/enforcement/section-301-investigations

### epa.ts
- https://www.epa.gov/newsreleases (RSS)
- https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information

### congress.ts
- https://api.congress.gov/v3/bill (API key required)

### ice.ts
- https://www.ice.gov/news/releases (RSS)
- https://www.dhs.gov/news-releases (RSS)

### nopa.ts
- https://nopa.org/nopa-crush-report/ (PDF scrape - monthly)

### conab.ts
- https://www.conab.gov.br/info-agro/safras (scrape)

### eia-inventories.ts
- https://api.eia.gov/v2/petroleum/sum/sndw/data/ (API key required)

### eia-production.ts
- https://api.eia.gov/v2/petroleum/supply/monthly/ (API key required)

### gacc.ts
- http://43.248.49.97/ (China customs portal - complex)

### mpob.ts
- http://bepi.mpob.gov.my/index.php/en/statistics/sectoral-status.html (scrape)

### usitc.ts
- https://dataweb.usitc.gov/ (API or scrape)

### social.ts
- Twitter via ScrapeCreators API (analysts: @kannbwx, @ArlanFF101, etc.)
- TruthSocial via ScrapeCreators API

### polymarket.ts
- https://gamma-api.polymarket.com/events (REST API)

---

## SCHEMA CHANGES NEEDED

Add to Prisma schema:
1. `raw.legislation_whitehouse_1d`
2. `raw.legislation_federal_register_1d`
3. `raw.legislation_ustr_1d`
4. `raw.legislation_epa_1d`
5. `raw.legislation_congress_1d`
6. `raw.legislation_ice_1d`
7. `raw.agriculture_nopa_1m`
8. `raw.agriculture_conab_1w`
9. `raw.energy_eia_inventories_1w`
10. `raw.energy_eia_production_1m`
11. `raw.trade_gacc_china_1m`
12. `raw.trade_mpob_palm_1m`
13. `raw.trade_usitc_1m`
14. `raw.sentiment_social_1d`
15. `raw.sentiment_prediction_1d`

All tables include:
```prisma
specialist_tags String[] @map("specialist_tags")
```

---

## NEXT ACTIONS

1. Add `specialist_tags[]` column to existing raw tables
2. Create 15 new raw table schemas
3. Build 15 Inngest jobs
4. Fix crowd-beliefs.ts → polymarket.ts (no cross-routing)
5. Update feature engineering to SELECT WHERE specialist_tags @> ARRAY['crush']

---

*LOCKED - Kirk Authority*
