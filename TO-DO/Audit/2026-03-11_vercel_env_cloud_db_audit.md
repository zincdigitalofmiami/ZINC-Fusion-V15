# Vercel Environment & Cloud DB Audit — 2026-03-11

> Historical context note: Sections referencing `db-guard-*` and `CLOUD_DATABASE_URL` capture pre-remediation state from 2026-03-11.
> Current workflow uses `DATABASE_URL` directly and the `db-guard-*` targets are removed.

## Context

Section 3 of `reports/stale_review_2026-03-11.md` requires cloud DB access to run stale SQL metrics and compute cloud-vs-local drift deltas. This audit documents all findings from the Vercel environment investigation.

---

## 0. Root Cause — Why `CLOUD_DATABASE_URL` is missing and `db-guard-cloud` fails

### The local env file

`.env.local.audit` (lines 8-12) routes **all** runtime DB aliases to localhost:

```
DIRECT_DATABASE_URL → postgresql://zincdigital@localhost:5432/zinc_fusion_v15_local
POSTGRES_URL        → postgresql://zincdigital@localhost:5432/zinc_fusion_v15_local
DATABASE_URL        → postgresql://zincdigital@localhost:5432/zinc_fusion_v15_local
```

There is no `CLOUD_DATABASE_URL` defined anywhere in that file.

### The guard's fallback chain

When `make db-guard-cloud` runs, `scripts/db_identity_guard.py` (lines 49-57) tries these env vars in order:

1. `CLOUD_DATABASE_URL` → **not set**
2. `DIRECT_DATABASE_URL` → resolves to `localhost:5432/zinc_fusion_v15_local`
3. `POSTGRES_URL` → same localhost
4. `DATABASE_URL` → same localhost

It falls through to a localhost URL. The guard checks `LOCAL_HOSTS = {"localhost", "127.0.0.1", ...}`, detects localhost is not a cloud host, and correctly fails:
> `[FAIL] mode=cloud endpoint=localhost:5432/zinc_fusion_v15_local ... message=cloud mode resolved to localhost endpoint.`

### Why this happened

`.env.local.audit` was set up purely for local audit work — it deliberately routes everything to the local Postgres. Nobody ever added a `CLOUD_DATABASE_URL` line pointing to the real cloud endpoint.

The `.env.local.audit.example` (line 12) shows the expected format:
```
CLOUD_DATABASE_URL="postgresql://<cloud_user>:<cloud_pass>@db.prisma.io:5432/postgres?sslmode=require&gssencmode=disable"
```

### Where the real URL lives

Not anywhere in this workspace. The cloud connection string is stored in Vercel's environment variables on the `zinc-fusion-v15` project (not the `frontend` project the workspace is linked to). It was confirmed present via `npx vercel env pull` against the correct project — see Section 3 below.

`frontend/.env.vercel.local` was also checked — contains only a Vercel OIDC token, no DB URL.

---

## 1. Vercel Auth & Identity

- `npx vercel whoami` → `zincdigitalofmiami` (confirmed working)
- Team: `zincdigitalofmiamis-projects`
- CLI version: 50.23.2

## 2. Project Inventory

| Project | Production URL | Updated | Node |
|---|---|---|---|
| `zinc-fusion-v15` | https://zinc-fusion-v15.vercel.app | 4h ago | 22.x |
| `external-project` | https://external-project.vercel.app | 3m ago | 24.x |
| `frontend` | (none) | 24h ago | 24.x |

### Critical finding: Local workspace linked to wrong project

`frontend/.vercel/project.json` links to the **`frontend`** project (`prj_CM8TbV6B7lnDJkeIOWcWrJwWrBEG`), which has **zero environment variables** and no production deployment.

The real production app is **`zinc-fusion-v15`** (`prj_FZgRHHVaqmjzhgk3aUayD8QxyASx`), which holds all 44 env var entries across production/preview/development.

This mismatch is why `npx vercel env pull` from the workspace returns no DB keys.

## 3. Production Environment Variables (zinc-fusion-v15)

Full inventory pulled via `npx vercel env pull` against `zinc-fusion-v15` project (temp file deleted immediately after read).

### DB-related keys (3 present)

| Variable | Host | Value shape | Environments |
|---|---|---|---|
| `DATABASE_URL` | `db.prisma.io:5432` | `postgres://<hash>:<sk_key>@db.prisma.io:5432/postgres?sslmode=require` | Prod, Preview, Dev |
| `POSTGRES_URL` | `db.prisma.io:5432` | Identical to `DATABASE_URL` | Prod, Preview, Dev |
| `PRISMA_DATABASE_URL` | `accelerate.prisma-data.net` | `prisma+postgres://accelerate.prisma-data.net/?api_key=<JWT>` (Accelerate proxy) | Prod, Preview, Dev |

### DB-related keys NOT present

| Variable | Status |
|---|---|
| `DIRECT_DATABASE_URL` | **Missing** — typically needed for Prisma migrations bypassing Accelerate proxy |
| `CLOUD_DATABASE_URL` | **Missing** — local audit convention, never added to Vercel |

### Non-DB keys (18 additional)

| Variable | Environments | Notes |
|---|---|---|
| `AUTH_SECRET` | All | HMAC auth key |
| `AUTH_PASSWORD` | All | Plaintext `5150` — weak |
| `INNGEST_SIGNING_KEY` | Prod | Production signing key |
| `INNGEST_EVENT_KEY` | Prod, Preview | Event delivery key |
| `INNGEST_ENV` | Prod | Value: `production` |
| `WORKFLOW_INNGEST_SIGNING_KEY` | Prod, Preview, Dev | Duplicate of INNGEST_SIGNING_KEY? |
| `DATABENTO_API_KEY` | All | Market data API |
| `EIA_API_KEY` | All | Energy data |
| `FRED_API_KEY` | All | Federal Reserve data |
| `USDA_API_KEY` | All | Agriculture data |
| `NOAA_TOKEN` | All | Weather data |
| `NOAA_API_TOKEN` | All | Duplicate of NOAA_TOKEN |
| `PROFARMER_USERNAME` | All | Scraper credentials |
| `PROFARMER_PASSWORD` | All | Scraper credentials |
| `SCRAPECREATORS_API_KEY` | All | Scraping service |
| `AUTONOMA_CLIENT_ID` | All | Autonoma integration |
| `AUTONOMA_SECRET_ID` | All | Autonoma integration |
| `APP_ORIGIN` | Prod, Preview | `https://zinc-fusion-v15.vercel.app` |
| `GLIDE_BEARER_TOKEN` | Prod, Preview | Glide API |

## 4. Anomalies & Concerns

### 4.1 Trailing `\n` in values

These production env vars have literal `\n` appended to their values:
- `APP_ORIGIN`
- `EIA_API_KEY`
- `GLIDE_BEARER_TOKEN`
- `NOAA_API_TOKEN`
- `PROFARMER_PASSWORD`
- `PROFARMER_USERNAME`
- `USDA_API_KEY`

**Risk:** APIs with strict input validation may reject these. Could cause intermittent auth failures that are hard to debug.

### 4.2 Duplicate/redundant keys

- `NOAA_TOKEN` and `NOAA_API_TOKEN` — same value, two vars
- `INNGEST_SIGNING_KEY` and `WORKFLOW_INNGEST_SIGNING_KEY` — same value, two vars
- `DATABASE_URL` and `POSTGRES_URL` — identical values

### 4.3 Weak auth

- `AUTH_PASSWORD = "5150"` — 4-digit plaintext password in production

### 4.4 No git repo connected

All `VERCEL_GIT_*` fields are empty strings. Project is not connected to a Git provider on Vercel. Deployments are CLI-only or manual.

### 4.5 Missing `DIRECT_DATABASE_URL`

Standard Prisma setup uses `DIRECT_DATABASE_URL` for migrations (bypassing the Accelerate proxy). This is absent, meaning either:
- Migrations run locally only (not in production CI)
- Migrations go through Accelerate (not recommended)
- Migrations are applied manually

## 5. User-confirmed deltas (folded in)

- `npx vercel env pull --environment=production` from the **workspace context** (linked to `frontend` project) returns 21 keys but **no DB keys at all** — confirming the project mismatch is the root cause.
- Cloud guard passes when the `db.prisma.io` URL is explicitly injected as `CLOUD_DATABASE_URL` in the command.
- Direct `psql` execution still blocks when the credential is redacted or incomplete (password prompt).

## 6. Remediation completed (2026-03-11)

### Done

1. **Deleted orphan `frontend` Vercel project** — 0 deployments, 0 env vars, created by rogue AI session ~Mar 5. `npx vercel project rm frontend`.
2. **Re-linked workspace** — `frontend/.vercel/project.json` now points to `zinc-fusion-v15` (`prj_FZgRHHVaqmjzhgk3aUayD8QxyASx`). `vercel env ls` returns all 44 vars.
3. **Removed `CLOUD_DATABASE_URL` concept entirely** — the env var was a local audit convention used only by `db_identity_guard.py`. Deleted:
   - `scripts/db_identity_guard.py`
   - `.env.local.audit` (untracked) and `.env.local.audit.example` (tracked)
   - Makefile targets: `db-guard-cloud`, `db-guard-local`, `db-guard-shadow`
   - `.gitignore` entry for `.env.local.audit`
   - References in `scripts/load_db_env.sh`, `scripts/prisma.sh`, `scripts/prisma_status.sh`
   - `scripts/sync_cloud_to_local_db.py` default changed from `CLOUD_DATABASE_URL` to `DATABASE_URL`
4. **Removed active audit block from `AGENTS.md`** — blocker resolved.

### Remaining recommendations

1. ~~Clean up trailing `\n` from 7 affected Vercel env vars~~ **DONE 2026-03-11** — All 7 vars (`APP_ORIGIN`, `EIA_API_KEY`, `GLIDE_BEARER_TOKEN`, `NOAA_API_TOKEN`, `PROFARMER_USERNAME`, `PROFARMER_PASSWORD`, `USDA_API_KEY`) removed and re-added with clean values across all affected environments (production, preview, development). Verified via fresh `vercel env pull`. **Note:** `PROFARMER_USERNAME` and `PROFARMER_PASSWORD` both had `\n` — this likely caused login failures on the ProFarmer scraper independent of the Puppeteer module fix.
2. Consider deduplicating `NOAA_TOKEN`/`NOAA_API_TOKEN` and `INNGEST_SIGNING_KEY`/`WORKFLOW_INNGEST_SIGNING_KEY`
3. Strengthen `AUTH_PASSWORD` or move to a proper auth provider
4. Connect git repo to Vercel project for deployment traceability
5. Consolidate dual `prisma.config.ts` files (`config/` vs `prisma/`) into one
