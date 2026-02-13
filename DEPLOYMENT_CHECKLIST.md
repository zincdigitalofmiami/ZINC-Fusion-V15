# Deployment Checklist
## Quick Reference for Deploying Critical Security Fixes

**Branch:** `copilot/full-code-review-inngest-schema-datasets-apis`  
**Date:** 2026-02-13

---

## Pre-Deployment (5-10 minutes)

### Code Quality
- [ ] Run linter: `ruff check src/ --select F401,F403,F405,F821,F841`
- [ ] Run tests: `pytest tests/ -q`
- [ ] Verify Python syntax: `python3 -m py_compile src/fusion/api/server.py`
- [ ] Review git diff: `git diff main...HEAD`

### Environment Setup
- [ ] Generate API key: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- [ ] Store key securely (1Password, Vault, etc.)
- [ ] Prepare environment variables (see `.env.example`)

---

## Staging Deployment (15-30 minutes)

### 1. Frontend (Vercel)
- [ ] Deploy to staging: `cd frontend && vercel --prod=false`
- [ ] Note staging URL: ___________________________
- [ ] Set environment variables in Vercel dashboard:
  - [ ] `FUSION_API_KEY` (NEW)
  - [ ] `DATABASE_URL`
  - [ ] `INNGEST_EVENT_KEY`
  - [ ] `INNGEST_SIGNING_KEY`
  - [ ] `FRED_API_KEY`
  - [ ] `DATABENTO_API_KEY`

### 2. Backend (Choose Platform)
- [ ] Deploy FastAPI server (Railway/Vercel/Fly.io/Docker)
- [ ] Set `FUSION_API_KEY` environment variable
- [ ] Set `DATABASE_URL` environment variable
- [ ] Note backend URL: ___________________________

### 3. Verification
- [ ] Health check: `curl <backend-url>/health`
- [ ] Auth test (no key): Should return 401
- [ ] Auth test (valid key): Should return data
- [ ] Performance test: `/api/overview/models` < 100ms
- [ ] Frontend loads: Visit staging URL
- [ ] No console errors in browser

---

## Staging Validation (30-60 minutes)

### Automated Tests
```bash
# Set variables
export BACKEND_URL="https://your-backend-staging.com"
export API_KEY="your-staging-api-key"

# Run tests
./scripts/test-deployment.sh
```

### Manual Tests
- [ ] Dashboard loads and displays data
- [ ] Latest price data visible
- [ ] Forecasts display correctly
- [ ] No JavaScript errors
- [ ] API authentication working
- [ ] Error messages user-friendly (no tracebacks)

### Performance Tests
- [ ] `/api/overview/models` response time: _______ ms (target: <100ms)
- [ ] `/api/dashboard/summary` response time: _______ ms
- [ ] Database query count: _______ (target: <5 per request)

### Security Tests
- [ ] No API key in browser console/network logs
- [ ] 401 returned for invalid keys
- [ ] Database errors don't expose tracebacks
- [ ] CORS configured correctly

---

## Production Deployment (After Staging Success)

### 1. Final Review
- [ ] All staging tests passed
- [ ] Performance targets met
- [ ] Security review completed
- [ ] Rollback procedure documented
- [ ] Team notified of deployment

### 2. Merge to Main
```bash
git checkout main
git merge copilot/full-code-review-inngest-schema-datasets-apis
git push origin main
```

### 3. Deploy Frontend (Vercel)
- [ ] Auto-deploy from main branch, OR
- [ ] Manual: `cd frontend && vercel --prod`
- [ ] Set production environment variables
- [ ] Verify deployment URL

### 4. Deploy Backend
- [ ] Deploy to production platform
- [ ] Set production `FUSION_API_KEY` (different from staging)
- [ ] Set production `DATABASE_URL`
- [ ] Verify health check

### 5. Smoke Tests
- [ ] Production health check passes
- [ ] API authentication working
- [ ] Dashboard accessible
- [ ] Key endpoints responding

---

## Post-Deployment (30 minutes)

### Monitoring Setup
- [ ] Configure performance alerts (response time >500ms)
- [ ] Configure security alerts (auth failures >10/hour)
- [ ] Configure error alerts (500 errors >1%)
- [ ] Set up log aggregation

### Validation
- [ ] Monitor error logs for 30 minutes
- [ ] Check performance metrics
- [ ] Verify no increased error rates
- [ ] Test from multiple locations/devices

### Documentation
- [ ] Update deployment history in DEPLOYMENT_GUIDE.md
- [ ] Document any issues encountered
- [ ] Share API key with authorized team members
- [ ] Update runbook with any new findings

---

## Rollback (If Needed)

### Vercel Rollback
```bash
# List deployments
vercel ls

# Rollback
vercel rollback <previous-deployment-url>
```

### Emergency Actions
- [ ] Rollback frontend to previous deployment
- [ ] Rollback backend to previous version
- [ ] Verify rollback successful
- [ ] Investigate root cause
- [ ] Document issue for post-mortem

---

## Sign-Off

**Staging Deployment:**
- Deployed by: _________________
- Date: _________________
- Status: ☐ Success  ☐ Issues  ☐ Rolled Back

**Production Deployment:**
- Deployed by: _________________
- Date: _________________
- Status: ☐ Success  ☐ Issues  ☐ Rolled Back

**Notes:**
___________________________________________________________________
___________________________________________________________________
___________________________________________________________________

---

## Quick Commands Reference

```bash
# Generate API key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Test auth (no key - should fail)
curl https://backend-url.com/api/dashboard/summary

# Test auth (valid key - should succeed)
curl -H "X-API-Key: your-key" https://backend-url.com/api/dashboard/summary

# Measure response time
time curl -H "X-API-Key: your-key" https://backend-url.com/api/overview/models

# Health check
curl https://backend-url.com/health

# Vercel deploy staging
cd frontend && vercel --prod=false

# Vercel deploy production
cd frontend && vercel --prod

# Vercel set env var
vercel env add FUSION_API_KEY production

# Vercel list deployments
vercel ls

# Vercel rollback
vercel rollback <deployment-url>
```

---

**For detailed instructions, see DEPLOYMENT_GUIDE.md**
