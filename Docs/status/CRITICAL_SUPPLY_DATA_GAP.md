# CRITICAL SUPPLY DATA GAP - IMMEDIATE ACTION REQUIRED

**Date**: January 31, 2026  
**Priority**: 🚨 **HIGHEST** - These are the MOST IMPORTANT tables in the entire system

---

## 🚨 THE 3 MOST CRITICAL TABLES ARE EMPTY

These tables drive fundamental soybean oil supply/demand and are MORE IMPORTANT than all news/alt data:

### 1. `supply.conab_production_1m` - **0 rows** ❌
**Why Critical**: Brazil = #1 global soybean producer (177 MMT/year)
- CONAB monthly forecasts are market-moving events
- Brazil production = global soybean supply anchor
- Directly affects crush margins and ZL prices

### 2. `supply.argentina_crush_1m` - **0 rows** ❌  
**Why Critical**: Argentina = #1 soybean oil exporter (45% global market share)
- Argentina crush capacity = global soy oil supply
- 43 MMT crush capacity
- Crush margins drive ZL export prices

### 3. `supply.mpob_palm_1m` - **0 rows** ❌
**Why Critical**: Malaysia = 50% of global palm oil production
- Palm oil = largest substitute to soybean oil
- MPOB monthly data on 10th of each month
- Malaysia production (19 MMT) sets palm/soy price spread

---

## STATUS: Tables Created, Jobs Created, BUT NO DATA

### What's Done ✅
- ✅ Tables created with proper schema
- ✅ Inngest job skeletons created
- ✅ Prisma models added
- ✅ Exported in functions.ts

### What's NOT Done ❌
- ❌ Working data ingestion (USDA PSD API returns 403/404)
- ❌ Alternative scraping not implemented
- ❌ Zero historical data loaded

---

## IMMEDIATE OPTIONS

### Option 1: Manual CSV Upload (FASTEST)
1. Go to https://apps.fas.usda.gov/psdonline/
2. Download CSVs for:
   - Brazil Soybeans (production)
   - Argentina Soybeans (crush)
   - Malaysia Palm Oil (production)
3. Parse and insert via script

### Option 2: Use Alternative Data Sources
1. **Brazil**: USDA FAS GAIN reports (https://gain.fas.usda.gov)
   - Search "Brazil soybean" → Download PDFs → Parse
2. **Argentina**: USDA FAS Buenos Aires attaché reports
3. **Malaysia**: IndexMundi API (requires registration)

### Option 3: Web Scraping (Most Reliable Long-term)
1. **MPOB**: Scrape http://bepi.mpob.gov.my/ (monthly releases on 10th)
2. **CONAB**: Scrape https://www.conab.gov.br/ (monthly Boletim)
3. **Argentina**: USDA FAS or Oil World data

---

## IMPACT OF MISSING DATA

Without these tables, the system CANNOT properly model:

### Crush Specialist
- ❌ No Argentina crush capacity (biggest soy oil exporter)
- ❌ No Brazil production (biggest soy producer)
- ⚠️ Only has US WASDE data (incomplete global picture)

### Palm Specialist  
- ❌ No Malaysia palm production (50% of global supply)
- ⚠️ Only has CPO futures prices (not production fundamentals)

### Substitutes Specialist
- ❌ Cannot model palm/soy substitution dynamics
- ❌ Missing key supply-side driver

### Result
**Forecasts will be systematically biased** - missing the PRIMARY supply drivers for ZL pricing.

---

## WHAT I'M DOING NOW

Creating working implementations using multiple fallback approaches:

1. ✅ Try USDA PSD API (failed - 403 Forbidden)
2. ⏳ Try USDA PSD CSV downloads (testing)
3. ⏳ Create web scrapers for MPOB/CONAB/CIARA
4. ⏳ Research all available proxies

**User requested**: "go deeper than just those for the supply, find and pull any and all proxies"

---

## CRITICAL SUPPLY PROXIES TO ADD

After populating the main 3, add these supply indicators:

### Brazil Supply Proxies
- Brazilian port loading data (export pace)
- Safras e Mercado production estimates
- Brazil weather (rainfall in Mato Grosso)
- Brazil planting progress (% complete)

### Argentina Supply Proxies
- Buenos Aires Grain Exchange estimates
- Argentine port strikes/logistics
- Rosario Board of Trade crush data
- Paraná River water levels (affects exports)

### Palm Oil Supply Proxies
- Indonesia palm production (GAPKI)
- Malaysia weather (El Niño impact)
- CPO export duties (Indonesia/Malaysia policy)
- Palm/soy price spread (substitution signal)

---

**STATUS**: 🚨 CRITICAL GAP - Working on multiple data source approaches
