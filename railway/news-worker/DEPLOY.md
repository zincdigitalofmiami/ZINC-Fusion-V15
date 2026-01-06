# News Ingestion Worker - Railway Deployment Guide

## Overview

This worker runs as a scheduled cron job to ingest news from **46 sources** across all 11 Big-11 specialists.

**Schedule:** Every 4 hours (configurable in `railway.toml`)
**Runtime:** ~5-10 minutes per execution
**Cost:** ~$5-10/month on Railway

### Source Coverage by Specialist

| Specialist | Sources | Priority Split |
|------------|---------|----------------|
| crush | 11 | P0: 6, P1: 3, P2: 2 |
| china | 3 | P1: 2, P2: 1 |
| fx | 1 | P2: 1 |
| fed | 2 | P1: 1, P2: 1 |
| tariff | 3 | P1: 2, P2: 1 |
| energy | 2 | P1: 1, P2: 1 |
| biofuel | 2 | P1: 1, P2: 1 |
| palm | 5 | P1: 2, P2: 3 |
| volatility | 1 | P2: 1 |
| substitutes | 7 | P1: 2, P2: 5 |
| trump_effect | 4 | P1: 3, P2: 1 |
| **TOTAL** | **46** | **P0: 6, P1: 17, P2: 18** |

---

## Deployment Steps

### 1. Create New Railway Service

```bash
# Option A: Via Railway CLI
cd /path/to/ZINC-FUSION-V15
railway login
railway link  # Link to existing project
railway up --service news-worker --path railway/news-worker

# Option B: Via Railway Dashboard
# 1. Go to https://railway.app/dashboard
# 2. Open your ZINC-FUSION project
# 3. Click "New Service" → "Empty Service"
# 4. Name it "news-worker"
# 5. Connect your GitHub repo
# 6. Set root directory to "railway/news-worker"
```

### 2. Configure Environment Variables

In Railway Dashboard → news-worker → Variables:

```env
# Required
DATABASE_URL=postgres://...your-prisma-postgres-url...

# Optional (for Twitter/Truth Social)
SCRAPECREATORS_API_KEY=your-api-key-here
```

**IMPORTANT:** Use the same `DATABASE_URL` as your main Prisma Postgres instance.

### 3. Configure Cron Schedule

Edit `railway.toml` or set in Dashboard → Settings → Cron:

```toml
# Every 4 hours (default)
cronSchedule = "0 */4 * * *"

# Every 2 hours (more frequent)
cronSchedule = "0 */2 * * *"

# Specific times: 6 AM, 12 PM, 6 PM ET (adjust for UTC)
cronSchedule = "0 11,17,23 * * *"

# Daily at 5 AM ET (10 AM UTC)
cronSchedule = "0 10 * * *"
```

### 4. Deploy

```bash
# Via CLI
railway up

# Or push to GitHub - Railway auto-deploys
git add railway/news-worker
git commit -m "Add news worker for Railway"
git push
```

---

## Monitoring

### View Logs

```bash
# Via CLI
railway logs --service news-worker

# Or in Dashboard → news-worker → Deployments → View Logs
```

### Check Ingestion Stats

Stats are written to the database. Query:

```sql
-- Recent articles by source
SELECT source, COUNT(*), MAX(as_of_date) as latest
FROM "raw"."news_articles_1d"
WHERE ingested_at > NOW() - INTERVAL '24 hours'
GROUP BY source
ORDER BY COUNT(*) DESC;

-- Articles by specialist
SELECT bucket_name as specialist, COUNT(*)
FROM "raw"."news_articles_1d"
WHERE ingested_at > NOW() - INTERVAL '7 days'
GROUP BY bucket_name
ORDER BY COUNT(*) DESC;
```

---

## Manual Execution

### Run Full Ingestion

```bash
# In Railway
railway run --service news-worker python scripts/ingest_news_sources.py --mode full --days 30

# Locally (for testing)
DATABASE_URL="your-url" python scripts/ingest_news_sources.py --mode quick --dry-run
```

### Run Single Specialist

```bash
railway run --service news-worker python scripts/ingest_news_sources.py --specialist trump_effect --days 7
```

---

## Troubleshooting

### No Articles Inserted

1. Check DATABASE_URL is correct
2. Check source RSS/scrape URLs are accessible
3. Run with `--dry-run` to see what would be fetched

### Rate Limiting

The script has 1.5s delays between sources. If you get blocked:
- Reduce frequency in cron schedule
- Add User-Agent rotation
- Use proxy (not implemented yet)

### Memory Issues

If the worker runs out of memory:
- Reduce `--days` parameter
- Increase Railway instance size
- Process sources in batches

---

## Cost Estimate

| Usage | Monthly Cost |
|-------|--------------|
| 6 executions/day × 10 min | ~$3-5 |
| With larger instance | ~$5-10 |
| + Prisma Postgres | Included |

---

## Alternative: GitHub Actions

If you prefer GitHub Actions over Railway:

```yaml
# .github/workflows/news-ingest.yml
name: News Ingestion

on:
  schedule:
    - cron: '0 */4 * * *'  # Every 4 hours
  workflow_dispatch:  # Manual trigger

jobs:
  ingest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r railway/news-worker/requirements-worker.txt

      - name: Run ingestion
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          SCRAPECREATORS_API_KEY: ${{ secrets.SCRAPECREATORS_API_KEY }}
        run: python scripts/ingest_news_sources.py --mode full --days 7
```

---

## Files in This Directory

```
railway/news-worker/
├── Dockerfile           # Container build
├── requirements-worker.txt  # Python dependencies
├── railway.toml         # Railway config + cron schedule
└── DEPLOY.md           # This guide
```

---

## How It Works

1. Railway reads `railway.toml` → sees `cronSchedule = "0 */4 * * *"`
2. Every 4 hours, Railway spins up the Docker container
3. Container runs `python scripts/ingest_news_sources.py --mode full --days 7`
4. Script fetches 46 news sources, dedupes via SHA256 hash, inserts to Prisma Postgres
5. Container exits, Railway logs the execution
6. Dashboard shows execution history with timestamps and logs

---

## Monitoring in Railway Dashboard

Navigate to **news-worker** service:

- **Deployments tab**: See each cron execution with status
- **Logs tab**: Real-time output from each run
- **Metrics tab**: Memory/CPU usage per execution

---

*Last Updated: January 2026*
