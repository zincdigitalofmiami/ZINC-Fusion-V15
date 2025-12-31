# Railway Cron Configuration for ZINC-Fusion-V15

## Overview

This document describes how to set up Railway cron jobs for automated data ingestion.

## Services to Create

Create these services in your Railway project, all pointing to this GitHub repo.

---

### 1. ZL Price Ticker (Every 15 minutes)

| Setting | Value |
|---------|-------|
| **Service Name** | `cron-zl-price` |
| **Start Command** | `pip install -r requirements.txt && python scripts/update_zl_price.py` |
| **Cron Schedule** | `*/15 * * * *` |

**Purpose**: Updates ZL futures price for chart display.

---

### 2. Polygon Options (Daily)

| Setting | Value |
|---------|-------|
| **Service Name** | `cron-polygon-options` |
| **Start Command** | `pip install -r requirements.txt && python scripts/ingest_polygon_options.py` |
| **Cron Schedule** | `0 0 * * 2-6` |

**Purpose**: Full options chain with Greeks for ZL, ZS, ZM, CL.
**Timing**: 7:00 PM ET (after market close)

---

### 3. FRED Economic Data (Daily)

| Setting | Value |
|---------|-------|
| **Service Name** | `cron-fred-data` |
| **Start Command** | `pip install -r requirements.txt && python scripts/pull_all_fred.py` |
| **Cron Schedule** | `0 11 * * 1-5` |

**Purpose**: Economic indicators (FX, rates, VIX, etc.)
**Timing**: 6:00 AM ET

---

### 4. NOAA Weather (Daily)

| Setting | Value |
|---------|-------|
| **Service Name** | `cron-noaa-weather` |
| **Start Command** | `pip install -r requirements.txt && python scripts/backfill_noaa_weather.py --all` |
| **Cron Schedule** | `0 13 * * *` |

**Purpose**: Agricultural region weather data
**Timing**: 8:00 AM ET

---

### 5. USDA Data (Weekly)

| Setting | Value |
|---------|-------|
| **Service Name** | `cron-usda-data` |
| **Start Command** | `pip install -r requirements.txt && python scripts/backfill_usda_data.py --all` |
| **Cron Schedule** | `0 21 * * 5` |

**Purpose**: Crop progress, conditions, WASDE
**Timing**: Fridays 4:00 PM ET

---

## Environment Variables

Add these to **each service** (or use Railway's shared variables):

```
DATABASE_URL=postgresql://...
POLYGON_API_KEY=your_polygon_key
FRED_API_KEY=your_fred_key
NOAA_API_TOKEN=your_noaa_token
USDA_NASS_API_KEY=your_usda_key
```

---

## How to Set Up in Railway

1. Go to your project: https://railway.com/project/02c13f56-bbb1-401d-a129-4501f613aa50

2. Click **"+ New"** → **"GitHub Repo"** → Select `ZINC-Fusion-V15`

3. In the new service, go to **Settings**:
   - Set **Start Command**
   - Set **Cron Schedule** (in Deploy section)

4. Go to **Variables** tab and add environment variables

5. Repeat for each cron service

---

## Cron Schedule Reference

All times are UTC.

| Expression | Meaning |
|------------|---------|
| `*/15 * * * *` | Every 15 minutes |
| `0 0 * * 2-6` | Midnight UTC, Tue-Sat (7pm ET Mon-Fri) |
| `0 11 * * 1-5` | 11am UTC, Mon-Fri (6am ET) |
| `0 13 * * *` | 1pm UTC daily (8am ET) |
| `0 21 * * 5` | 9pm UTC Fridays (4pm ET) |

---

## Notes

- Railway minimum cron interval is 5 minutes
- All schedules are in UTC
- Scripts must exit after completion (no long-running processes)
- Each service is billed only for execution time
