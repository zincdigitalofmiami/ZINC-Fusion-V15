# Plan: Fix Data Pipeline + Retrain Model

## Status: READY TO EXECUTE

## Context

The model can't be cleanly retrained because 4 data sources are dead/broken, and Inngest reliability on Vercel is a chronic issue. The AI feedback loop plan (ai-feedback-loop.md) depends on having a healthy model — this plan unblocks that.

## Phase 1: Immediate — Unblock Retrain (today)

### 1A. Vercel Redeploy

**Impact:** Fixes ProFarmer (dead 16 days), picks up all code changes from this branch.

The `serverExternalPackages` fix in `next.config.ts` is already in the codebase but has NOT been deployed. ProFarmer scraper crashes on every run because turbopack tree-shakes `is-plain-object` out of the bundle.

**Action:**
- Merge `feat/legislation-real-data-scoring` → `main` (or deploy this branch)
- Verify ProFarmer runs on next cron fire (weekdays 7 AM CT)
- Check Vercel dashboard for function success

### 1B. Verify Fluid Compute is Active

**Impact:** All Inngest functions get 300s default timeout (up from 60s), configurable to 800s.

**Action:**
- Vercel Dashboard → Project Settings → Functions → check "Fluid" toggle
- If not enabled, enable it
- Set `maxDuration` on heavy scrapers:

```typescript
// In next.config.ts or per-route:
export const maxDuration = 300; // 5 minutes for scraper routes
```

Or in `vercel.json`:
```json
{
  "functions": {
    "frontend/src/app/api/inngest/route.ts": {
      "maxDuration": 800
    }
  }
}
```

### 1C. Verify ETF Backfill Landed

**Impact:** ETF data has been dead 28 days. Yahoo fallback was created + backfill triggered 2026-02-27.

**Action:**
```sql
SELECT MAX(trade_date), COUNT(*) FROM mkt.etf_1d WHERE trade_date >= '2026-02-01';
```
- If data exists through Feb 28+: backfill worked, ETF is green
- If data stops at Feb 2: backfill failed, need to manually trigger Yahoo fallback

### 1D. Fix USDA_API_KEY on Vercel

**Impact:** MPOB palm monthly function returns 403 on every run. Palm specialist has no fresh data.

**Action:**
- Get valid FAS OpenData API key from https://apps.fas.usda.gov/opendataweb/home
- Update `USDA_API_KEY` in Vercel Environment Variables
- Manually trigger `mpobPalmMonthly` to verify

**Alternative:** If FAS API key is unobtainable, remove MPOB from the palm specialist and rely on Dalian soy oil futures as the Asia palm proxy (already in matrix).

### 1E. Confirm Empty Tables

**Action:**
```sql
SELECT 'eia_biodiesel_1w' AS tbl, COUNT(*) FROM supply.eia_biodiesel_1w
UNION ALL
SELECT 'uco_prices_1w', COUNT(*) FROM supply.uco_prices_1w;
```
- If 0 rows: these loaders in build_matrix.py will produce NaN columns. Confirm they have `min_periods` guards or will silently skip.
- Consider removing from matrix if data source is fundamentally broken.

---

## Phase 2: Stability — Docker Inngest for Dev (this week)

### 2A. Run Inngest Dev Server Locally via Docker

**Why:** Debugging Inngest functions on Vercel is blind — you can't see logs in real-time, can't step through failures, can't test scrapers against live endpoints. Docker gives you a local Inngest server with full UI.

**Action:**
```bash
# Start Inngest dev server (Docker must be running)
docker run -d --name inngest-dev \
  -p 8288:8288 \
  inngest/inngest:latest \
  inngest dev -u http://host.docker.internal:3000/api/inngest

# Dev UI at http://localhost:8288
# Trigger any function manually from the UI
```

**Connect Next.js dev server:**
```bash
# In frontend/.env.local, add:
INNGEST_DEV=1
INNGEST_BASE_URL=http://localhost:8288
```

**Test workflow:**
1. `npm --prefix frontend run dev` (port 3000)
2. Open http://localhost:8288 — see all 57 registered functions
3. Trigger `profarmerDaily` manually — watch logs in real-time
4. Trigger `yahooEtfFallbackDaily` — verify ETF data lands
5. Trigger `eiaBiodieselWeekly` — see why it produces 0 rows

### 2B. Fix Chronically Failing Functions

With local Inngest running, debug and fix:

| Function | Issue | Expected Fix |
|----------|-------|-------------|
| `fasReportsDaily` | HTTP/2 stream errors from fas.usda.gov | Add retry with exponential backoff, or switch to RSS feed |
| `federalRegisterDaily` | 39% success rate | Debug locally — likely timeout or rate-limit issue. Fluid 300s may fix it. |
| `nassWeekly` | Stale since Feb 6 | Debug locally |
| `eiaBiodieselWeekly` | 0 rows ever produced | Debug locally — likely source URL or parsing issue |

---

## Phase 3: Retrain the Model (after Phase 1 verified)

### 3A. Generate Fresh Specialist Signals

```bash
cd "/Volumes/Satechi Hub/ZINC-FUSION-V15"
.venv/bin/python scripts/generate_specialist_features.py --bucket all --start-date 2025-01-01
.venv/bin/python scripts/generate_specialist_signals.py --bucket all --start-date 2025-01-01
```

### 3B. Run Full Training Pipeline

```bash
.venv/bin/python -m fusion.core_training.run_pipeline
```

This rebuilds the matrix (1,487 features), trains all 52 models across 4 horizons (7d, 21d, 63d, 126d), and promotes the best ensemble.

### 3C. Verify Model Output

```bash
# Check model artifacts
ls -la models/core_v2/126d/learner.pkl
# Check prediction quality
.venv/bin/python -m fusion.core_training.run_pipeline --skip-matrix  # train-only if matrix is fresh
```

### 3D. Deploy Updated Model

The trained model artifacts (`models/core_v2/`) need to be committed and deployed. The forecast API reads from these .pkl files.

---

## Phase 4: Medium-Term — Self-Hosted Inngest on Railway (optional)

If Vercel cron + Inngest cloud continues to be unreliable after Fluid Compute is enabled, consider moving orchestration to Railway:

- **Railway Inngest template:** One-click deploy with Postgres + Redis
- **Cost:** ~$5-10/month for the Inngest server + backing services
- **Benefit:** No Vercel serverless constraints, unlimited function duration, persistent state, proper retry queues
- **Your Next.js app stays on Vercel** — only the Inngest server moves to Railway

This is the nuclear option if Phases 1-2 don't stabilize things.

---

## Verification Checklist

After Phase 1:
- [ ] ProFarmer cron fires successfully (check Vercel function logs)
- [ ] `mkt.etf_1d` has data through current week
- [ ] Fluid Compute enabled (300s+ timeout)
- [ ] MPOB palm function succeeds or is removed from critical path

After Phase 2:
- [ ] Inngest dev UI accessible at localhost:8288
- [ ] All 57 functions visible in dev UI
- [ ] Can manually trigger and debug any function locally

After Phase 3:
- [ ] `training.matrix_1d` updated with fresh data
- [ ] Model retrained with updated artifacts in `models/core_v2/`
- [ ] Forecast API returns non-stale predictions
- [ ] Strategy page shows fresh model forecasts

---

## Files to Modify

| File | Change | Phase |
|------|--------|-------|
| `vercel.json` (or next.config.ts) | Set `maxDuration: 800` for Inngest route | 1B |
| Vercel Dashboard | Enable Fluid Compute, update USDA_API_KEY | 1B, 1D |
| `docker-compose.yml` (new) | Inngest dev server config | 2A |
| `frontend/.env.local` | Add INNGEST_DEV vars | 2A |
| Various Inngest functions | Fix retry logic, parsing bugs | 2B |
| `models/core_v2/` | Updated model artifacts after retrain | 3D |
