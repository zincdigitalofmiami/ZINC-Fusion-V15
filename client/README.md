# Fusion Client (Next.js)

This is the client UI for the locked 5-page app:

- `/dashboard`
- `/strategy`
- `/legislation`
- `/sentiment`
- `/vegas-intel`

## Chart Contract

- Area charts only (no candlesticks/OHLC).
- Hero chart is edge-to-edge and dominant.
- Data is read-only and pulled from the Fusion API.

## Configuration

Set the Fusion API base URL (server-side; used by the Next.js `/api/*` proxy routes):

- `FUSION_API_BASE` (example: `http://localhost:8000`)

## Deploy (Vercel)

- Ensure the Vercel project builds the `client/` app (this repo includes `vercel.json` at repo root to do that).
- Set `FUSION_API_BASE` in Vercel Project → Settings → Environment Variables to your deployed Fusion API base URL.

## Run (local)

1) Start the Fusion API (FastAPI):

- `uvicorn fusion.api.server:app --reload --port 8000`

2) Install and run the client:

- `npm install`
- `npm run dev`
