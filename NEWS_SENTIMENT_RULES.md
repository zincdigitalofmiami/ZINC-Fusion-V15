# News Sentiment Rules for Soybean Oil Analysis

This document defines the classification rules for news sentiment analysis in ZINC-Fusion-V15.

---

## Alert Buckets

Primary buckets for the dashboard "News & Geopolitical Sentiment":

- US Regulatory Filings
- Political Changes
- Tariff Updates
- China Relations
- Legislation Changes
- Biofuel Mandates
- Logistics/Chokepoints
- ESG/Deforestation
- Labor Actions
- Fertilizer/Energy
- Animal Disease

---

## Classification Categories

### 1. China Demand Levers (Sinograin/COFCO/NDRC/MOF)

**Specialist Bucket:** `china`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Reserve stockpiles rebuild, import quota boosts, crush-margin subsidies |
| **Bearish** | Biosecurity import slowdowns, tighter import licenses, state reserve releases |

**Keywords:** Sinograin, COFCO, NDRC soybean, state reserves, crush margins, Dalian

---

### 2. Argentina Policy + FX (Rosario Core)

**Specialist Bucket:** `fx`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Export taxes up, "soy dollar" FX carrot ends, port blockades, trucker strikes |
| **Bearish** | Temporary export tax cuts, FX incentives to sell, swift IMF-driven liberalization |

**Keywords:** sojadólar, retenciones, Rosario strike, CIARA-CEC, Puerto San Lorenzo

---

### 3. Brazil Policy + Infrastructure (BR-163, Santos, Northern Arc)

**Specialist Bucket:** `substitutes`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Export licensing hiccups, environmental enforcement slowing Amazon expansion, barge/rail bottlenecks |
| **Bearish** | Logistics upgrades (Ferrogrão/rail), port privatizations that speed flow, BRL strengthening |

**Keywords:** CONAB, MAPA, Santos, Arco Norte, Ferrogrão, Ibama embargo, USD/BRL

---

### 4. U.S. Policy (Tariffs, Farm Bill, RFS, Logistics)

**Specialist Bucket:** `tariff`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Higher China tariffs/retaliation risk, tougher EUDR alignment costs, rail/port strikes, Mississippi draft limits |
| **Bearish** | Export credit guarantees expanded, grain inspection streamlining, lower RFS volumes |

**Keywords:** USTR, RFS volumes, Jones Act waiver, USACE Mississippi, ILWU, STB rail

---

### 5. Biofuels Policy Swings (Price of Oil ↔ Soy Oil Demand)

**Specialist Bucket:** `biofuel`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Indonesia B35→B40, Brazil biodiesel blend hikes, U.S. LCFS/SAF/45Z sweeteners |
| **Bearish** | EU/US pushback on feedstock ILUC, weaker LCFS credit prices, cap on crop-based biofuels |

**Keywords:** B40 Indonesia, RenovaBio, CBIO, LCFS, SAF, EPA RVO

---

### 6. Palm Oil Geopolitics (Direct Cross with Soy Oil)

**Specialist Bucket:** `palm`

| Direction | Signals |
|-----------|---------|
| **Bullish (for soy)** | Indonesia/Malaysia export levies/bans, labor shortages in estates, ESG import hurdles |
| **Bearish (for soy)** | Levy cuts or export liberalization, bumper output, India import duty cuts on palm |

**Keywords:** CPO export levy, DMO, MPOB, India edible oil duty

---

### 7. Black Sea Vegoils & War Spillovers

**Specialist Bucket:** `substitutes`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Corridor disruptions, port strikes, sanctions on Russian/Belarus agrichemicals affecting global cost/yields |
| **Bearish** | Corridor re-openings, insured shipping expands, sunflower oil floods market (pressuring soy oil) |

**Keywords:** Black Sea corridor, Danube ports, sunflower oil export, marine insurance

---

### 8. Global Chokepoints & Freight

**Specialist Bucket:** `energy`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Red Sea/Suez risk, Panama Canal draft/slot cuts, South China Sea tension, insurance exclusions |
| **Bearish** | Reroute subsidies, canal rainfall recovery, naval escorts restore throughput |

**Keywords:** Panama Canal transit, Bab el-Mandeb, Houthi, war risk premiums

---

### 9. Fertilizer & Energy Sanctions (Input-Cost Transmission)

**Specialist Bucket:** `energy`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Sanctions/plant outages in ammonia, potash restrictions (Russia/Belarus), natgas spikes in EU |
| **Bearish** | Sanction carve-outs, new supply (Africa/Middle East ammonia), cheap gas |

**Keywords:** Belarus potash, CF Industries outage, ammonia pipeline, urea tender

---

### 10. Animal Disease Shocks (Demand for Meal)

**Specialist Bucket:** `crush`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Poultry/pork disease waves that reduce feed demand → bearish meal, but if culling triggers policy stockpiles, price paths can flip |
| **Bearish** | Herd rebuilds in China/SEA boosting meal demand steadily |

**Keywords:** ASF China, avian influenza, hog herd, MOA China

---

### 11. Trade Disputes & Quotas (WTO/AD/CVD/TQs)

**Specialist Bucket:** `tariff`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Antidumping/CVD on oils/meals, new quotas or SPS barriers |
| **Bearish** | Fresh bilateral deals (tariff-rate quotas), Phase-style purchase commitments |

**Keywords:** antidumping soybean oil, WTO panel, TRQ soybeans, SPS measures

---

### 12. ESG/Deforestation Rules (EUDR & Copycats)

**Specialist Bucket:** `palm`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Strict traceability deadlines causing shipment delays/cargo rejections |
| **Bearish** | Phased enforcement or exemptions easing flow |

**Keywords:** EUDR soy, traceability polygon, due diligence regulation

---

### 13. Labor & Civil Unrest

**Specialist Bucket:** `crush`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Argentina/Brazil port strikes, U.S./EU trucker protests, French farmer blockades |
| **Bearish** | Strike settlements with throughput guarantees |

**Keywords:** port strike Santos, Rosario piquete, Gulf export elevators, blockade

---

### 14. Cyber/Infrastructure Surprises

**Specialist Bucket:** `volatility`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Ransomware at a major port/grain trader, AIS spoofing incidents, customs system outages |

**Keywords:** ransomware port, terminal outage, customs IT failure, AIS spoofing

---

### 15. Regulatory Approvals of GM Traits & Agrochemicals

**Specialist Bucket:** `tariff`

| Direction | Signals |
|-----------|---------|
| **Bullish** | Bans/withdrawals (e.g., glyphosate), delayed trait approvals in China → planting/yield uncertainty |
| **Bearish** | Rapid approvals, alternative herbicide programs stabilized |

**Keywords:** soy trait approval China, glyphosate ban, CTNBio

---

### 16. Macro/FX (Flow-Through to Export Parity)

**Specialist Bucket:** `fx`

**Watch:** USD, BRL, ARS; emerging-market capital controls; sovereign downgrades

**Thumb Rule:**
- USD↑ often pressures commodities
- BRL/ARS↓ can boost South American exports

---

## Event → Impact Heuristics

| Event | Impact | Action |
|-------|--------|--------|
| Indonesia raises CPO export levy/B40 | Bullish soy oil | Check ZL front month |
| Rosario port strike/sojadólar ends | Bullish ZS/meal (near-term) | Watch crush spreads |
| Panama Canal transit cuts extended | Bullish export basis Brazil/U.S. Gulf | Watch freight spreads |
| EUDR enforcement date firmed | Bullish EU-imported soy | Logistics friction |
| ASF resurgence China | Bearish soy meal, neutral-to-bearish beans | Meal/oil spread |

---

## Scoring Logic

### Relevance
```
(producer/route/policy × soybean/veg-oil keyword density)
```

### Directional Prior
Attach a label per rule above:
- `bullish`
- `bearish`
- `uncertain`

### Conviction
```
source_quality + policy_specificity
```
Where:
- "proposal" < "decree published"
- Official sources > media reports

### Half-Life
| Category | Half-Life |
|----------|-----------|
| Strikes/chokepoints | Short (days) |
| Mandates/policy | Medium (weeks) |
| Legislation | Long (months) |

### Cross-Asset Boost
```python
if oil_bullish and biofuel_mandate_bullish:
    soy_oil_signal = "double-bullish"
```

---

## Institution Watchlist

**Government/Regulatory:**
- USTR, USDA FAS/ERS, EPA
- EU Commission, DG TRADE, WTO
- MAPA Brazil, CONAB, Ibama
- Argentina Economía/AFIP
- MOA China, NDRC
- Sinograin, COFCO
- MPOB (Malaysia)
- Indonesian Coordinating Ministry of Economic Affairs
- RenovaBio/ANP

**Places/Assets:**
- Santos, Paranaguá, Rosario/Up River
- Mississippi draft, BR-163, Arco Norte
- Panama Canal, Suez, Danube, Odessa

**Themes:**
- B40, LCFS, SAF, EUDR
- Antidumping, TRQ, retenciones, sojadólar
- Port strike, rail strike, export ban, state reserves

---

## Social Media Analysts to Monitor

Via ScrapeCreators API:

| Analyst | Handle | Focus |
|---------|--------|-------|
| Karen Braun | @kannbwx | Reuters commodities |
| Arlan Suderman | @ArlanFF101 | StoneX chief economist |
| Scott Irwin | @ScottIrwinUIUC | UIUC ag economics |
| Dr. Michael Cordonnier | @SoybeanCorn | South America crops |
| Javier Blas | @JavierBlas | Bloomberg commodities |

---

## Implementation Status

- [x] Basic keyword classification in `ingest_news.py`
- [x] Bucket routing to specialists
- [x] Daily sentiment aggregation
- [ ] Half-life decay scoring
- [ ] Cross-asset boost logic
- [ ] Source quality weighting
- [ ] ScrapeCreators analyst feed integration
