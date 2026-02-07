# ⚠️ DEPRECATED - Fly.io Live Connector

**Status: DEPRECATED as of 2026-02-07**

## Why Deprecated

The Fly.io live connector has been replaced by a simpler architecture:

1. **Reliability Issues**: Fly.io machine stopped on Jan 29, 2026 and required manual restarts
2. **Data Staleness**: Analytics tables depending on live connector became 5-11 days stale
3. **Simpler Alternative**: Databento Historical API (via Inngest cron) is more reliable

## New Architecture

```
[Databento Historical API]
       ↓
  [Inngest cron jobs] (databento-futures-daily.ts, databento-futures-1h.ts)
       ↓
  [mkt.futures_1d, mkt.futures_1h] (reliable source of truth)
       ↓
  [API endpoints] (/api/zl/price-1d, /api/zl/price-1h)
       ↓
  [Dashboard Charts]
```

## Migration Notes

- `/api/zl/price-1d` now reads from `mkt.futures_1d` directly
- `/api/zl/price-1h` now reads from `mkt.futures_1h` directly
- Databento Historical API runs via Inngest every 8 hours (sufficient for daily trading)
- Real-time 1-minute data available via `/api/zl/price-1m` when backfilled

## If You Need Real-Time Data

For true real-time (sub-minute) updates, consider:
1. WebSocket connection to Databento from frontend (client-side)
2. Server-Sent Events from a Vercel Edge function
3. Polling `/api/zl/price-1m` every minute

The Fly.io approach added operational complexity without proportional benefit for this use case.
