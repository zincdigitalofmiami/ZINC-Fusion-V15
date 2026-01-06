# Data Availability by Horizon

Single source of truth for data availability constraints across training horizons.

## Core Principle

**Strategic training (63d/126d) uses ALL data from 2000+. The ONLY exceptions are series that fundamentally did not exist before a certain date.**

| Horizon | Mode | Data Window | Rule |
|---------|------|-------------|------|
| 5d | Tactical | Rolling 7yr | Use all available data |
| 21d | Tactical | Rolling 7yr | Use all available data |
| 63d | Strategic | 2000+ full history | Use all series with data from 2000 |
| 126d | Strategic | 2000+ full history | Use all series with data from 2000 |

## Series Classification

### Tier 1: Available from 2000+ — Use for ALL horizons

These series have data from 2000 or earlier and should be used for both tactical and strategic training:

**Market Futures:** ZL (1970+), ZS (1968+), CL (2000), HO (2000), etc.

**FRED - Rates:** DFF (1954+), FEDFUNDS (1954+), DGS2/5/10/30 (1976+), SOFR proxy via FEDFUNDS

**FRED - FX:** DEXCAUS, DEXCHUS, DEXBZUS, etc. (most from 2000+)

**FRED - Commodities:** DCOILWTICO (1986+), VIXCLS (1990+), PSOILUSDM (1990+)

**FRED - Macro:** CPIAUCSL (1947+), UNRATE (1948+), GDP (1947+), M2SL (1959+), NFCI (1971+)

### Tier 2: Fundamentally Limited — Cannot be backfilled

These series DID NOT EXIST before their start date. No backfill possible:

| Series | Start Date | Reason | Strategic Proxy |
|--------|------------|--------|-----------------|
| **SOFR** | 2018-04-03 | Created by Fed to replace LIBOR | Use **FEDFUNDS** |
| **VXGSCLS** | 2020-07-24 | CBOE Gold VIX launched then | Use **VIXCLS** |

### Tier 3: GAPS TO FILL — Data exists but not yet ingested

**CRITICAL:** These series have historical data available that we need to pull:

| Series | DB Has | FRED Has | Gap | Action |
|--------|--------|----------|-----|--------|
| **M2SL** | 2023-12 | **1959-01** | 64 years | **BACKFILL URGENT** |
| **OVXCLS** | 2023-12 | **2007-05** | 16 years | **BACKFILL URGENT** |
| **EIA biofuel** | 2020+ | Varies | Check each | Research availability |

## Backfill Priority Queue

### Priority 1: Strategic Training Blockers

| Series | FRED Start | Current DB Start | Strategic Impact |
|--------|------------|------------------|------------------|
| M2SL | 1959-01-01 | 2023-12-01 | High - monetary policy driver |
| OVXCLS | 2007-05-10 | 2023-12-28 | High - oil vol for energy specialist |

### Priority 2: USDA Data (Downloaded but not ingested)

| Source | File | DB Start | Available History |
|--------|------|----------|-------------------|
| WASDE | `WASDE_DATA_*.zip` | 2020-01 | 2010+ in download |
| CFTC CITS | `QDL_CITS_*.zip` | 2006-06 | 2013+ in download |

## Implementation Rules

### Training Scripts Must:

1. **Use all available data for strategic horizons:**
```python
# Strategic (63d/126d) - use full history
if horizon in [63, 126]:
    data_start = "2000-01-01"
    # Include ALL series that have data from 2000
    # Only exclude if series fundamentally didn't exist
```

2. **Apply proxies only for fundamentally limited series:**
```python
# SOFR didn't exist before 2018 - use proxy
if series == "SOFR" and as_of_date < "2018-04-03":
    use_proxy("FEDFUNDS")  # SOFR proxy

# OVXCLS has data from 2007 - use it!
if series == "OVXCLS":
    # Data exists from 2007-05-10, use it for strategic
    pass
```

3. **Log gaps that need backfill:**
```python
if db_start > "2000-01-01" and fred_actual_start < "2000-01-01":
    logger.warning(f"GAP: {series} has {db_start} but FRED has {fred_actual_start}")
```

## Proxy Relationships (Only for Fundamentally Limited Series)

| Missing Series | When Missing | Proxy | Correlation |
|----------------|--------------|-------|-------------|
| SOFR | Before 2018-04-03 | FEDFUNDS | ~0.99 post-2018 |
| VXGSCLS | Before 2020-07-24 | VIXCLS | ~0.70 |

## References

- [train_core_v15.py](../../../scripts/train_core_v15.py) - Implements tactical/strategic split
- [horizon_encoding.md](horizon_encoding.md) - Horizon integer standards
- [AGENTS.md](../../../AGENTS.md) - Data domain ownership
