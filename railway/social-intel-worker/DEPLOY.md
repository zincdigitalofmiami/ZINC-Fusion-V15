# Social Intelligence Worker - Railway Deployment Guide

## Overview

This worker scrapes social media platforms for commodity market intelligence using the **ScrapeCreators API**.

**Platforms:** Twitter/X, Truth Social, Facebook, LinkedIn
**Handles:** 120+ sources across all priority tiers
**Runtime:** ~10-15 minutes per full execution
**Cost:** ~$10-20/month on Railway + ScrapeCreators API costs

### Source Coverage by Tier

| Tier | Sources | Platforms | Schedule |
|------|---------|-----------|----------|
| HIGH_ALPHA | 19 | Twitter/X, Truth Social | Every 5 min |
| REGULATORY | 45 | Twitter/X, Facebook | Every 15 min |
| DISCOVERY | 55 | Twitter/X, LinkedIn, Facebook | Every 60 min |
| **TOTAL** | **119** | All | Varies |

### High-Alpha Sources (Market-Moving)

- **Trump Admin:** @realDonaldTrump, @POTUS, @WhiteHouse, Truth Social
- **Trade Policy:** @USTR, @USTreasury, @ICEgov, @CBP
- **China:** @MOFCOMChina, @GACC_China, @cofcointl, @sinograin_china

---

## Prerequisites

### 1. ScrapeCreators API Key

Get your API key from [ScrapeCreators](https://scrapecreators.com):

```bash
# Test your API key
curl -H "x-api-key: YOUR_KEY" \
  "https://api.scrapecreators.com/v2/twitter/user/tweets?username=USDA&limit=5"
```

---

## Deployment Options

### Option A: Single Service (Recommended for Start)

Run all tiers hourly in one service:

```bash
cd /path/to/ZINC-FUSION-V15
railway login
railway link
railway up --service social-intel-worker --path railway/social-intel-worker
```

### Option B: Multi-Service (High Frequency)

For near-real-time Trump/USTR monitoring, deploy multiple services:

| Service | Tier | Schedule |
|---------|------|----------|
| social-intel-high | high | `*/5 * * * *` |
| social-intel-reg | regulatory | `*/15 * * * *` |
| social-intel-disc | discovery | `0 * * * *` |

Create each with different `railway.toml`:

```toml
# social-intel-high/railway.toml
cronSchedule = "*/5 * * * *"

# In main.py or Procfile
CMD ["python", "main.py", "--tier", "high"]
```

---

## Environment Variables

In Railway Dashboard → social-intel-worker → Variables:

```env
# Required
DATABASE_URL=postgres://...your-prisma-postgres-url...
SCRAPECREATORS_API_KEY=your-scrapecreators-api-key

# Optional
LOG_LEVEL=INFO
```

**IMPORTANT:**
- Use the same `DATABASE_URL` as your main Prisma Postgres instance
- The `SCRAPECREATORS_API_KEY` is REQUIRED - script will exit without it

---

## API Endpoints Used

| Platform | Endpoint | Rate Limit |
|----------|----------|------------|
| Twitter/X | `/v2/twitter/user/tweets` | ~1000/day |
| Truth Social | `/v2/truthsocial/user/posts` | ~500/day |
| Facebook | `/v2/facebook/profile/posts` | ~500/day |
| LinkedIn | `/v2/linkedin/company/posts` | ~500/day |

---

## Monitoring

### View Logs

```bash
railway logs --service social-intel-worker
```

### Check Ingestion Stats

```sql
-- Recent social posts by source
SELECT source, COUNT(*), MAX(as_of_date) as latest
FROM "raw"."news_articles_1d"
WHERE source LIKE 'twitter_%'
  AND ingested_at > NOW() - INTERVAL '24 hours'
GROUP BY source
ORDER BY COUNT(*) DESC;

-- Trump-related posts
SELECT source, headline, as_of_date
FROM "raw"."news_articles_1d"
WHERE is_trump_related = true
  AND ingested_at > NOW() - INTERVAL '24 hours'
ORDER BY as_of_date DESC
LIMIT 20;

-- Posts by platform
SELECT
  CASE
    WHEN source LIKE 'twitter_%' THEN 'Twitter'
    WHEN source LIKE 'truthsocial_%' THEN 'Truth Social'
    WHEN source LIKE 'facebook_%' THEN 'Facebook'
    WHEN source LIKE 'linkedin_%' THEN 'LinkedIn'
    ELSE 'Other'
  END as platform,
  COUNT(*)
FROM "raw"."news_articles_1d"
WHERE ingested_at > NOW() - INTERVAL '7 days'
GROUP BY 1
ORDER BY 2 DESC;
```

---

## Manual Execution

```bash
# All tiers
railway run --service social-intel-worker python main.py --tier all

# High-alpha only
railway run --service social-intel-worker python main.py --tier high

# Backfill (100 posts per source)
railway run --service social-intel-worker python main.py --tier all --backfill

# Dry run (preview only)
railway run --service social-intel-worker python main.py --tier high --dry-run
```

---

## Cost Estimate

| Component | Monthly Cost |
|-----------|--------------|
| Railway (hourly cron) | ~$5-10 |
| Railway (5-min cron) | ~$15-25 |
| ScrapeCreators API | ~$50-100 (depending on volume) |
| **Total (basic)** | **~$60-110** |

---

## Handles by Specialist

### trump_effect (19 handles)
- @realDonaldTrump, @DonaldJTrumpJr, @EricTrump
- @POTUS, @VP, @WhiteHouse
- @ICEgov, @CBP, @DHSgov
- Truth Social: @realDonaldTrump

### tariff (15 handles)
- @USTR, @USTreasury, @SecYellen
- @SenateAg, @HouseAg, @ChairmanThompson
- @EU_Commission, @EU_CouncilEU

### china (12 handles)
- @MOFCOMChina, @GACC_China, @MFA_China
- @cofcointl, @sinochem_news, @sinograin_china
- @CCTVNews, @XinhuaNews, @PDChina

### crush (35 handles)
- @USDA, @SecVilsack, @USDA_NASS
- @ADMCorp, @BungeGlobal, @Cargill
- @ASA_Soybeans, @NOPA_News, @FarmBureau
- Brazil: @MinAgricultura, @abioveoficial, @conab_oficial
- Argentina: @CIARA_CEC, @BCRAmercados

### biofuel (12 handles)
- @EPA, @EnergyGov, @CleanFuelsDA
- @BiodieselNow, @EthanolRFA, @CARB

### palm (3 handles)
- @mpobmalaysia, @gapki_id, @icopalmoil

### volatility (6 handles)
- @CMEGroup, @ICE_Markets, @nasdaq
- @CNBC, @BloombergNews, @Reuters

---

## Troubleshooting

### "SCRAPECREATORS_API_KEY not set"

Add the key in Railway Variables. The worker cannot run without it.

### Rate Limiting

If you get 429 errors:
1. Reduce cron frequency
2. Use tier-specific services
3. Contact ScrapeCreators for higher limits

### Empty Results

1. Check the handle exists: `curl "https://twitter.com/HANDLE"`
2. Some accounts may be private or suspended
3. Try with `--dry-run` to see fetch attempts

---

## Files in This Directory

```
railway/social-intel-worker/
├── Dockerfile           # Container build
├── requirements.txt     # Python dependencies
├── railway.toml         # Railway config + cron schedule
├── main.py              # Entry point
├── Procfile             # Process definition
├── scripts/
│   └── scrape_social_intel.py  # Main scraping logic
├── src/fusion/
│   ├── __init__.py
│   ├── config.py
│   └── api/
│       ├── __init__.py
│       └── news_sentiment.py
└── DEPLOY.md            # This guide
```

---

*Last Updated: January 2026*
