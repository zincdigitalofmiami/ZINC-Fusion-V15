/**
 * GET /api/live/zl1h?backfill=96
 *
 * SSE endpoint for ZL 1-hour candlestick data.
 *
 * On connect:
 *   1. Forced Databento refresh (instant fresh snapshot)
 *   2. Read `backfill` bars from DB, emit as snapshot event
 *
 * Then every 15 s:
 *   - Non-forced refresh (gated at 90 s by zl1h-refresh.ts)
 *   - Emit only bars newer than the last emitted timestamp
 *   - SSE comment keepalive when nothing new
 *
 * EventSource auto-reconnects when the stream closes (Vercel 5-min limit).
 */
import { query } from "@/lib/db";
import { refreshZl1hFromDatabento } from "@/lib/zl1h-refresh";

export const dynamic = "force-dynamic";
export const maxDuration = 300; // 5 min Vercel serverless ceiling

const POLL_INTERVAL_MS = 15_000;
const DEFAULT_BACKFILL = 96;
const MAX_BACKFILL = 720; // 30 days of 1h bars

export async function GET(req: Request) {
  const url = new URL(req.url);
  const parsed = parseInt(url.searchParams.get("backfill") || String(DEFAULT_BACKFILL), 10);
  const backfill = Math.max(1, Math.min(Number.isNaN(parsed) ? DEFAULT_BACKFILL : parsed, MAX_BACKFILL));

  const encoder = new TextEncoder();
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  let closed = false;
  let latestTs: string | null = null;

  function cleanup() {
    closed = true;
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  }

  const stream = new ReadableStream({
    async start(controller) {
      // Helper to enqueue an SSE data frame
      const send = (payload: string) => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(`data: ${payload}\n\n`));
        } catch {
          // Stream already closed
          cleanup();
        }
      };

      const keepalive = () => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(`: keepalive\n\n`));
        } catch {
          cleanup();
        }
      };

      // ── Phase 1: Connect ──────────────────────────────────────────
      // Force a Databento refresh so DB is up-to-date before snapshot read
      try {
        await refreshZl1hFromDatabento({ force: true });
      } catch (err) {
        console.error("[zl1h-sse] Forced refresh failed, continuing with DB data:", err);
      }

      // Read backfill snapshot from DB (may span more history than the 18 h
      // Databento lookback, e.g. backfill=96 = 4 days)
      try {
        const rows = await query<{
          timestamp: string;
          open: number;
          high: number;
          low: number;
          close: number;
          volume: number;
        }>(
          `SELECT timestamp::text, open::float8, high::float8, low::float8,
                  close::float8, volume::bigint
           FROM analytics.price_1h
           WHERE symbol = 'ZL' AND close IS NOT NULL
           ORDER BY timestamp DESC
           LIMIT $1`,
          [backfill],
        );

        // Reverse to chronological order for the client
        rows.reverse();

        if (rows.length > 0) {
          latestTs = rows[rows.length - 1].timestamp;
        }

        send(JSON.stringify({ type: "snapshot", bars: rows, count: rows.length }));
      } catch (err) {
        console.error("[zl1h-sse] Snapshot query failed:", err);
        send(JSON.stringify({ type: "snapshot", bars: [], count: 0, error: "db_read_failed" }));
      }

      // ── Phase 2: Poll loop (recursive setTimeout to prevent overlap) ──
      async function poll() {
        if (closed) return;

        try {
          const result = await refreshZl1hFromDatabento({ force: false });

          if (result.skipped || result.bars.length === 0) {
            keepalive();
          } else {
            // Filter for bars newer than the last emitted
            let newBars = result.bars;
            if (latestTs) {
              const cutoff = new Date(latestTs).getTime();
              newBars = result.bars.filter((b) => b.tsEvent.getTime() > cutoff);
            }

            if (newBars.length === 0) {
              keepalive();
            } else {
              const mapped = newBars.map((b) => ({
                timestamp: b.tsEvent.toISOString(),
                open: b.open,
                high: b.high,
                low: b.low,
                close: b.close,
                volume: b.volume,
              }));

              latestTs = mapped[mapped.length - 1].timestamp;
              send(JSON.stringify({ type: "update", bars: mapped, count: mapped.length }));
            }
          }
        } catch (err) {
          console.error("[zl1h-sse] Poll error:", err);
          keepalive();
        }

        // Schedule next tick only after current completes (no overlap)
        if (!closed) {
          timeoutId = setTimeout(poll, POLL_INTERVAL_MS);
        }
      }

      timeoutId = setTimeout(poll, POLL_INTERVAL_MS);
    },

    cancel() {
      cleanup();
    },
  });

  // Also listen for client abort (browser tab close, etc.)
  req.signal.addEventListener("abort", cleanup);

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
