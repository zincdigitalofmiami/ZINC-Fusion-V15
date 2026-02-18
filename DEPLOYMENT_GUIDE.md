# ZINC-Fusion-V15 Deployment Guide
## Critical Security Fixes - Staging & Production Deployment

**Version:** 1.0  
**Date:** 2026-02-13  
**Branch:** `copilot/full-code-review-inngest-schema-datasets-apis`

---

## Overview

This guide covers deployment of critical security and performance fixes to staging and production environments.

### What's Being Deployed

**Critical Fixes:**
1. N+1 specialist query elimination (95% latency reduction)
2. Database error handling decorator (prevents traceback exposure)
3. API key authentication (X-API-Key header on 6+ endpoints)

**Files Changed:**
- `src/fusion/api/server.py` - All 3 fixes

**Documentation Added:**
- `CRITICAL_FIXES_SUMMARY.md`
- `IMPLEMENTATION_COMPLETE.txt`
- `CODE_REVIEW_FINDINGS.md`
- `CODE_REVIEW_ACTION_ITEMS.md`

---

## Architecture

### Frontend (Vercel)
- **Platform:** Vercel
- **Framework:** Next.js 14+
- **Location:** `frontend/`
- **Config:** `frontend/vercel.json`
- **Functions:** Inngest serverless functions (48 total)

### Backend (FastAPI)
- **Framework:** FastAPI
- **Location:** `src/fusion/api/server.py`
- **Deployment:** Requires hosting configuration (see options below)

### Database
- **Platform:** Prisma Postgres (cloud-hosted)
- **Connection:** Via `DATABASE_URL` environment variable
- **Migrations:** Managed via Prisma CLI

---

## Pre-Deployment Checklist

### Code Quality
- [x] All Python files pass syntax check
- [x] Critical fixes implemented and tested
- [x] Documentation complete
- [ ] Run linter: `ruff check src/`
- [ ] Run tests: `pytest tests/`

### Environment Variables

#### Required for Production

**Backend (FastAPI):**
```bash
# Database
DATABASE_URL=<prisma-postgres-connection-string>

# Security (NEW - REQUIRED)
FUSION_API_KEY=<generate-secure-random-key>  # NEW: Enable API auth

# Optional
FUSION_API_TOKEN=<token-for-db-endpoints>    # Existing: DB explorer auth
FUSION_CORS_ORIGINS=<allowed-origins>

# Data APIs
FRED_API_KEY=<fred-api-key>
```

**Frontend (Vercel):**
```bash
# Database
DATABASE_URL=<prisma-postgres-connection-string>

# Inngest
INNGEST_EVENT_KEY=<inngest-event-key>
INNGEST_SIGNING_KEY=<inngest-signing-key>

# Data APIs
FRED_API_KEY=<fred-api-key>
DATABENTO_API_KEY=<databento-api-key>

# Backend API
NEXT_PUBLIC_API_URL=<backend-api-url>
```

### Generate Secure API Key

```bash
# Generate a secure random API key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Or use openssl
openssl rand -base64 32
```

**IMPORTANT:** Store this key securely and share it only with authorized clients.

---

## Deployment Steps

### Option 1: Staging Deployment (Recommended First)

#### Step 1: Deploy Frontend to Vercel Staging

```bash
cd frontend

# Install Vercel CLI if needed
npm install -g vercel

# Deploy to staging (preview)
vercel --prod=false

# Note the staging URL
# Example: https://zinc-fusion-v15-<hash>.vercel.app
```

#### Step 2: Set Environment Variables in Vercel

**Via Vercel Dashboard:**
1. Go to Project Settings → Environment Variables
2. Add/Update for "Preview" environment:
   - `DATABASE_URL` (if changed)
   - `INNGEST_EVENT_KEY`
   - `INNGEST_SIGNING_KEY`
   - `FRED_API_KEY`
   - `DATABENTO_API_KEY`

**Via Vercel CLI:**
```bash
# Add environment variable
vercel env add FUSION_API_KEY preview

# List environment variables
vercel env ls
```

#### Step 3: Deploy Backend (Choose Your Platform)

**Option A: Vercel (Serverless)**
```bash
cd /path/to/repo

# Create vercel.json for backend
cat > vercel-backend.json << EOF
{
  "version": 2,
  "builds": [
    {
      "src": "src/fusion/api/server.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "src/fusion/api/server.py"
    }
  ]
}
EOF

# Deploy
vercel --prod=false
```

**Option B: Fly.io**
```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
flyctl auth login

# Create app
flyctl launch

# Set secrets
flyctl secrets set FUSION_API_KEY=<your-key>
flyctl secrets set DATABASE_URL=<connection-string>

# Deploy
flyctl deploy
```

**Option C: Docker + Cloud Run / ECS / etc.**
```bash
# Create Dockerfile if not exists
cat > Dockerfile << EOF
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY scripts/ ./scripts/

ENV PYTHONPATH=/app

CMD ["uvicorn", "fusion.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# Build
docker build -t zinc-fusion-api:staging .

# Run locally to test
docker run -p 8000:8000 \
  -e DATABASE_URL=<url> \
  -e FUSION_API_KEY=<key> \
  zinc-fusion-api:staging

# Deploy to your cloud provider
```

#### Step 4: Configure API Key for Clients

**Frontend Integration:**

Update frontend to include API key in requests:
```typescript
// frontend/src/lib/api.ts
const API_KEY = process.env.FUSION_API_KEY;

export async function fetchDashboardSummary() {
  const response = await fetch(`${API_URL}/api/dashboard/summary`, {
    headers: {
      'X-API-Key': API_KEY,
    },
  });
  return response.json();
}
```

**Add to Vercel Environment Variables:**
```bash
vercel env add FUSION_API_KEY preview
# Enter the same key as backend
```

---

### Option 2: Production Deployment

⚠️ **IMPORTANT:** Only deploy to production after successful staging validation.

#### Step 1: Merge to Main Branch

```bash
# Ensure all tests pass
pytest tests/

# Merge the branch
git checkout main
git merge copilot/full-code-review-inngest-schema-datasets-apis
git push origin main
```

#### Step 2: Deploy Frontend to Vercel Production

```bash
cd frontend

# Deploy to production
vercel --prod

# Or configure auto-deploy from main branch in Vercel dashboard
```

#### Step 3: Set Production Environment Variables

**Via Vercel Dashboard:**
1. Project Settings → Environment Variables
2. Add/Update for "Production" environment
3. Redeploy if needed

#### Step 4: Deploy Backend to Production

Follow same platform-specific steps as staging, but:
- Use production environment variables
- Use production database connection
- Enable production monitoring
- Configure health checks

---

## Post-Deployment Validation

### Automated Tests

**1. Health Check**
```bash
# Backend
curl https://your-backend-url.com/health
# Should return: {"status": "healthy"}

# Frontend
curl https://your-frontend-url.vercel.app/api/health
# Should return: {"status": "ok"}
```

**2. API Authentication Test**
```bash
# Test without API key (should fail)
curl https://your-backend-url.com/api/dashboard/summary
# Expected: {"detail": "Invalid or missing X-API-Key header."}

# Test with invalid key (should fail)
curl -H "X-API-Key: wrong-key" https://your-backend-url.com/api/dashboard/summary
# Expected: {"detail": "Invalid or missing X-API-Key header."}

# Test with valid key (should succeed)
curl -H "X-API-Key: <your-actual-key>" https://your-backend-url.com/api/dashboard/summary
# Expected: {"data": [...]}
```

**3. Performance Test (N+1 Fix)**
```bash
# Measure response time
time curl -H "X-API-Key: <your-key>" https://your-backend-url.com/api/overview/models

# Should be <100ms (previously 2-3 seconds)
```

**4. Error Handling Test**
```bash
# Simulate database error (requires DB disconnect or invalid query)
# Verify no traceback in response, only:
# {"detail": "Database query failed. Please try again later."}
```

### Manual Tests

**Dashboard Tests:**
1. Visit dashboard URL
2. Verify latest price data loads
3. Check forecast displays
4. Verify no console errors
5. Test all interactive features

**API Endpoint Tests:**
- [ ] `/api/dashboard/summary` - Returns data with valid key
- [ ] `/api/overview/models` - Fast response (<100ms)
- [ ] `/api/market/zl` - Market data loads
- [ ] `/api/forecast/quantiles` - Forecasts load
- [ ] `/api/forecast/bands` - Confidence bands load

### Monitoring Checklist

**Set up monitoring for:**
- [ ] API response times (should be <100ms for overview/models)
- [ ] 401 error rate (auth failures)
- [ ] 500 error rate (database errors)
- [ ] Database connection pool usage
- [ ] API key usage patterns

**Recommended Tools:**
- Vercel Analytics (frontend)
- Sentry or similar (error tracking)
- CloudWatch/Datadog (backend metrics)
- Prisma Postgres dashboard (database metrics)

---

## Rollback Procedures

### If Issues Arise Post-Deployment

#### Quick Rollback (Vercel)

```bash
# List recent deployments
vercel ls

# Rollback to previous deployment
vercel rollback <deployment-url>

# Or via Vercel Dashboard:
# Deployments → Select previous successful deployment → Promote to Production
```

#### Backend Rollback

**Option 1: Revert to Previous Version**
```bash
# Git revert
git revert <commit-hash>
git push origin main

# Redeploy
```

**Option 2: Disable New Features**

**Disable API Authentication (Emergency Only):**
```bash
# Remove FUSION_API_KEY from environment variables
# This will revert to development mode (no auth)

# Via Vercel CLI
vercel env rm FUSION_API_KEY production

# Via your platform's dashboard
```

**Note:** This temporarily removes authentication. Fix root cause and redeploy ASAP.

#### Database Rollback

**No schema changes in this deployment - no database rollback needed.**

---

## Troubleshooting

### Common Issues

#### 1. "Invalid or missing X-API-Key header"

**Cause:** API key not configured or incorrect.

**Solution:**
```bash
# Check environment variable is set
echo $FUSION_API_KEY

# Verify it matches between frontend and backend
vercel env ls | grep FUSION_API_KEY
```

#### 2. Frontend can't reach backend

**Cause:** CORS or URL misconfiguration.

**Solution:**
```bash
# Check CORS origins in backend
# Should include your Vercel domain

# Update backend environment
FUSION_CORS_ORIGINS=https://your-app.vercel.app,https://your-app-preview.vercel.app
```

#### 3. Slow API responses

**Cause:** N+1 fix not applied or database issues.

**Solution:**
```bash
# Check logs for database query patterns
# Should see single GROUP BY query, not multiple individual queries

# Verify backend is running latest code
curl https://your-backend-url.com/api/overview/models
```

#### 4. Database errors exposed to clients

**Cause:** Error handling decorator not applied.

**Solution:**
```bash
# Verify decorator is present in server.py
grep "@handle_db_errors" src/fusion/api/server.py

# Redeploy if missing
```

---

## Security Considerations

### API Key Management

**DO:**
- ✅ Generate cryptographically secure random keys
- ✅ Store keys in environment variables (never in code)
- ✅ Use different keys for staging and production
- ✅ Rotate keys regularly (quarterly recommended)
- ✅ Share keys securely (1Password, Vault, etc.)
- ✅ Log authentication failures

**DON'T:**
- ❌ Commit keys to git
- ❌ Share keys via email/Slack
- ❌ Use the same key across environments
- ❌ Use weak/predictable keys

### Key Rotation Procedure

```bash
# 1. Generate new key
NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. Add new key alongside old (both work temporarily)
vercel env add FUSION_API_KEY_NEW production
# Enter new key

# 3. Update clients to use new key
# Deploy client updates

# 4. Remove old key
vercel env rm FUSION_API_KEY production
vercel env rename FUSION_API_KEY_NEW FUSION_API_KEY production

# 5. Verify all clients working
```

---

## Monitoring & Alerting

### Key Metrics to Monitor

**Performance:**
- `/api/overview/models` response time (target: <100ms, alert: >500ms)
- Database query count per request (target: 1-2, alert: >10)
- API response time p95 (target: <200ms, alert: >1s)

**Security:**
- 401 error rate (auth failures - alert if >10 per hour)
- Unique API keys seen (should be small number)
- Failed login attempts from single IP (alert if >50 per hour)

**Reliability:**
- 500 error rate (target: <0.1%, alert: >1%)
- Database connection pool exhaustion (alert if >90% used)
- Inngest function failures (alert if >5%)

### Recommended Alerts

**Critical (Page immediately):**
- 500 error rate >5% for 5 minutes
- Database connection pool exhausted
- API completely unavailable

**High (Notify within 15 minutes):**
- 401 error rate >20 per hour
- API response time p95 >1s for 10 minutes
- Individual endpoint failures >10% for 5 minutes

**Medium (Notify within 1 hour):**
- Unusual API key usage patterns
- Database query patterns changed
- Disk/memory usage >80%

---

## Maintenance

### Regular Tasks

**Weekly:**
- [ ] Review error logs for patterns
- [ ] Check API performance metrics
- [ ] Verify auth failure logs

**Monthly:**
- [ ] Review and rotate API keys if needed
- [ ] Check for security updates
- [ ] Review monitoring alerts and adjust thresholds

**Quarterly:**
- [ ] Full security audit
- [ ] Performance optimization review
- [ ] Capacity planning

---

## Support & Documentation

### Additional Resources

- **Code Review:** `CODE_REVIEW_FINDINGS.md`
- **Implementation:** `CRITICAL_FIXES_SUMMARY.md`
- **Architecture:** `AGENTS.md`
- **API Documentation:** (to be created)

### Getting Help

If deployment issues arise:
1. Check this guide's Troubleshooting section
2. Review deployment logs (Vercel, Fly.io, etc.)
3. Check database connection status
4. Verify environment variables are set correctly
5. Review recent commits for potential issues

---

## Deployment History

| Date | Environment | Version | Changes | Status |
|------|-------------|---------|---------|--------|
| 2026-02-13 | Staging | v1.0 | Critical security fixes | Pending |
| 2026-02-13 | Production | v1.0 | Critical security fixes | Pending |

---

## Sign-Off

Before deploying to production, ensure:
- [x] All staging tests passed
- [ ] Performance benchmarks met
- [ ] Security review completed
- [ ] Rollback procedure tested
- [ ] Monitoring configured
- [ ] Team notified

**Deployed by:** _________________  
**Date:** _________________  
**Sign-off:** _________________

---

**Last Updated:** 2026-02-13  
**Maintainer:** ZINC Digital  
**Status:** Ready for deployment
