# Data Ingestion Worker - Railway Deployment Guide

## Overview

This worker handles all scheduled data ingestion for the Big-11 specialists:

| Frequency | Data Sources | Schedule |
|-----------|--------------|----------|
| **Daily** | FRED (rates, FX, VIX), EPA RIN | 8 AM UTC |
| **Weekly** | CFTC COT, USDA Export Sales, USDA NASS | Wednesday (auto-detect) |
| **Monthly** | USDA WASDE | 13th of month (auto-detect) |

**Cost:** ~$5-10/month on Railway

---

## Data Sources

### Daily Sources

| Source | API/Method | API Key Required |
|--------|------------|------------------|
| **FRED** | REST API | `FRED_API_KEY` (free) |
| **EPA RIN** | OPIS API | `OPIS_API_KEY` (paid ~$2000/yr) |

FRED Series ingested:
- FED: DFF, DGS10, DGS2, T10Y2Y, T10Y3M
- FX: DEXBZUS, DEXCHUS, DTWEXBGS
- Energy: DCOILWTICO, DCOILBRENTEU, DHHNGSP
- Volatility: VIXCLS
- Trump Effect: USEPUINDXD

### Weekly Sources

| Source | API/Method | API Key Required |
|--------|------------|------------------|
| **CFTC COT** | Direct download | None |
| **USDA Export Sales** | Web scrape | None |
| **USDA NASS** | Quick Stats API | `USDA_NASS_API_KEY` (free) |

### Monthly Sources

| Source | API/Method | API Key Required |
|--------|------------|------------------|
| **USDA WASDE** | PSD API | `USDA_PSD_API_KEY` (free) |

---

## Deployment Steps

### 1. Create New Railway Service

```bash
# Via Railway CLI
cd /path/to/ZINC-FUSION-V15
railway login
railway link
railway up --service data-worker --path railway/data-worker
```

### 2. Configure Environment Variables

In Railway Dashboard → data-worker → Variables:

```env
# Required
DATABASE_URL=postgres://...your-prisma-postgres-url...

# Required for daily FRED ingestion (free)
FRED_API_KEY=your-fred-api-key

# Optional - USDA NASS for crop progress/condition (free)
USDA_NASS_API_KEY=your-nass-api-key

# Optional - USDA PSD for WASDE (free)
USDA_PSD_API_KEY=your-psd-api-key

# Optional - EPA RIN prices (paid subscription)
OPIS_API_KEY=your-opis-api-key
```

**Get free API keys:**
- FRED: https://fredaccount.stlouisfed.org/
- USDA NASS: https://quickstats.nass.usda.gov/api
- USDA PSD: https://apps.fas.usda.gov/PSDOnlineSubscription/

### 3. Deploy

```bash
railway up
```

---

## Manual Execution

### Run Specific Mode

```bash
# Daily ingestion
railway run --service data-worker python main.py --mode daily

# Weekly ingestion
railway run --service data-worker python main.py --mode weekly

# Monthly ingestion
railway run --service data-worker python main.py --mode monthly

# All sources
railway run --service data-worker python main.py --mode all --dry-run
```

### Local Testing

```bash
cd railway/data-worker
DATABASE_URL="your-url" FRED_API_KEY="your-key" python main.py --mode daily --dry-run
```

---

## Cron Schedule

The worker runs daily at 8 AM UTC. Mode is auto-detected:

| Day | Mode | Sources |
|-----|------|---------|
| Monday | daily | FRED, EPA RIN |
| Tuesday | daily | FRED, EPA RIN |
| **Wednesday** | **weekly** | FRED, EPA RIN, CFTC COT, USDA Export, USDA NASS |
| Thursday | daily | FRED, EPA RIN |
| Friday | daily | FRED, EPA RIN |
| Saturday | daily | FRED, EPA RIN |
| Sunday | daily | FRED, EPA RIN |
| **13th of month** | **monthly** | FRED, EPA RIN, USDA WASDE |

---

## Monitoring

### Check Recent Ingestion

```sql
-- FRED observations (last 7 days)
SELECT series_id, COUNT(*), MAX(as_of_date)
FROM raw.fred_observations_1d
WHERE ingested_at > NOW() - INTERVAL '7 days'
GROUP BY series_id
ORDER BY series_id;

-- CFTC COT (last 4 weeks)
SELECT symbol, COUNT(*), MAX(report_date)
FROM raw.cftc_cot_1w
WHERE ingested_at > NOW() - INTERVAL '28 days'
GROUP BY symbol;

-- EPA RIN (last 7 days)
SELECT rin_type, COUNT(*), MAX(as_of_date)
FROM raw.epa_rin_prices_1d
WHERE ingested_at > NOW() - INTERVAL '7 days'
GROUP BY rin_type;
```

---

## Troubleshooting

### No FRED Data
1. Check `FRED_API_KEY` is set correctly
2. Verify API key at https://fred.stlouisfed.org/

### No CFTC Data
1. Check https://www.cftc.gov/dea/newcot/deafut.txt is accessible
2. CFTC releases data on Tuesday afternoons

### No WASDE Data
1. WASDE requires `USDA_PSD_API_KEY`
2. Register at https://apps.fas.usda.gov/PSDOnlineSubscription/

---

## Files

```
railway/data-worker/
├── main.py              # Entry point with mode auto-detection
├── scripts/
│   └── ingest_all_sources.py  # Main ingestion logic
├── requirements.txt     # Python dependencies
├── railway.toml         # Railway config + cron
├── nixpacks.toml        # Build config
└── DEPLOY.md           # This guide
```

---

*Last Updated: January 2026*
