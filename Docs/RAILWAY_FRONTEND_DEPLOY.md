# Railway Deploy — Frontend (Next.js)

This repo contains multiple apps. The client UI you just built lives in `frontend/`.

## 1) Railway: pick the correct service root

In Railway:
- Project → select the **service** that should run the UI
- Service → **Settings** (or **Deployments → Build & Deploy**, depending on UI)
- Set **Root Directory** (a.k.a. Source/Root Dir) to:
  - `frontend`

This is the single most important step. Without it, Railway may build a different folder and you’ll see “wrong lockfile / wrong Next version” style failures.

## 2) Environment variables (Service → Variables)

Required:
- `AUTH_PASSWORD` — shared client password
- `AUTH_SECRET` — long random string used to sign the cookie (32+ chars recommended)

Optional (Nixpacks tuning, only if you need it):
- `NIXPACKS_INSTALL_CMD` = `npm ci`

## 3) Health check

This app exposes:
- `/api/health`

It is wired in `frontend/railway.json` so Railway can mark deploys healthy.

## 4) Build/start expectations

- Build: `npm run build`
- Start: `npm run start`

Note: `frontend/package.json` start script binds to `$PORT` (Railway injects this), falling back to `3000` locally.

## 5) Quick verification after deploy

- Hit `https://<your-service-domain>/api/health` → returns `{ ok: true }`
- Hit `https://<your-service-domain>/dashboard` → should redirect to `/login`
- Login with `AUTH_PASSWORD` → should land on `/dashboard` and render the chart
