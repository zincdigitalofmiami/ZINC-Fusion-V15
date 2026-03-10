/**
 * Manual Refresh Trigger for Key Market Drivers
 *
 * Triggers Inngest functions to refresh the data feeding the 4 driver cards:
 * - VIX: fredDailyVolatility (VIXCLS, VXVCLS, OVXCLS)
 * - Crush: boardCrushDaily
 * - China: fredDailyFx (DEXCHUS)
 * - Tariff: fredDailyTrumpEffect (USEPUINDXM, EMVTRADEPOLEMV)
 * - Trump orchestration gate: trumpEffectRefreshAndSync
 * - Specialist Signals: triggered by orchestration only after producer SLA passes
 */

import { NextResponse } from 'next/server'
import { inngest } from '@/inngest/client'
import { query } from '@/lib/db'

export const dynamic = 'force-dynamic'

const REFRESH_GATE_JOB_NAME = 'manual_refresh_drivers'
const MIN_REFRESH_INTERVAL_MS = 60_000 // 1 minute
// Process-local fallback only used when DB gate is unavailable.
let lastRefreshAt = 0

async function acquireRefreshGate(): Promise<{
  allowed: boolean
  runId: string | null
  mode: 'db' | 'memory'
}> {
  const dbRows = await query<{ id: string }>(
    `
      WITH latest AS (
        SELECT started_at
        FROM ops.ingest_run
        WHERE job_name = $1
        ORDER BY started_at DESC
        LIMIT 1
      ),
      inserted AS (
        INSERT INTO ops.ingest_run (
          job_name,
          status,
          started_at,
          rows_attempted,
          rows_inserted,
          rows_skipped,
          rows_quarantined,
          cursor_position
        )
        SELECT
          $1,
          'running',
          NOW(),
          0,
          0,
          0,
          0,
          jsonb_build_object('trigger', 'api.refresh-drivers')
        WHERE NOT EXISTS (
          SELECT 1
          FROM latest
          WHERE started_at > NOW() - INTERVAL '60 seconds'
        )
        RETURNING id
      )
      SELECT id FROM inserted
    `,
    [REFRESH_GATE_JOB_NAME],
  ).catch(() => null)

  if (dbRows !== null) {
    return { allowed: Boolean(dbRows[0]?.id), runId: dbRows[0]?.id ?? null, mode: 'db' }
  }

  const now = Date.now()
  if (now - lastRefreshAt < MIN_REFRESH_INTERVAL_MS) {
    return { allowed: false, runId: null, mode: 'memory' }
  }
  lastRefreshAt = now
  return { allowed: true, runId: null, mode: 'memory' }
}

async function finalizeRefreshGate({
  runId,
  successCount,
  totalCount,
  status,
  errorMessage,
}: {
  runId: string | null
  successCount: number
  totalCount: number
  status: 'success' | 'partial' | 'failed'
  errorMessage?: string
}) {
  if (!runId) return
  await query(
    `
      UPDATE ops.ingest_run
      SET
        status = $2,
        completed_at = NOW(),
        rows_attempted = $3,
        rows_inserted = $4,
        rows_skipped = $5,
        error_message = $6
      WHERE id = $1
    `,
    [
      runId,
      status,
      totalCount,
      successCount,
      Math.max(0, totalCount - successCount),
      errorMessage ?? null,
    ],
  ).catch(() => {
    // no-op: manual refresh should still return even if ingest run finalization fails
  })
}

export async function POST() {
  const gate = await acquireRefreshGate()
  if (!gate.allowed) {
    return NextResponse.json(
      { status: 'rate_limited', message: 'Please wait 60s between refreshes' },
      { status: 429 },
    )
  }

  try {
    // Send events to trigger the key Inngest functions
    // These functions will run asynchronously and update the database
    const results = await Promise.allSettled([
      // VIX/Volatility data
      inngest.send({
        name: 'fred-daily-volatility',
        data: { trigger: 'manual', timestamp: new Date().toISOString() },
      }),
      // Crush margin data
      inngest.send({
        name: 'board-crush-daily',
        data: { trigger: 'manual', timestamp: new Date().toISOString() },
      }),
      // FX data (CNY for China driver)
      inngest.send({
        name: 'fred-daily-fx',
        data: { trigger: 'manual', timestamp: new Date().toISOString() },
      }),
      // Trade policy uncertainty data
      inngest.send({
        name: 'fred-daily-trump-effect',
        data: { trigger: 'manual', timestamp: new Date().toISOString() },
      }),
      // Producer-first orchestration gate (verifies recent successful
      // trump_effect_feature_refresh run before dispatching specialist sync).
      inngest.send({
        name: 'trump-effect.refresh-and-sync',
        data: { trigger: 'manual', timestamp: new Date().toISOString() },
      }),
    ])

    const summary = results.map((r, i) => {
      const names = ['volatility', 'crush', 'fx', 'trump-effect-fred', 'trump-effect-orchestrator']
      return {
        function: names[i],
        status: r.status,
        error: r.status === 'rejected' ? String(r.reason) : undefined,
      }
    })

    const successCount = results.filter(r => r.status === 'fulfilled').length
    const finalStatus = successCount === results.length ? 'success' : 'partial'
    await finalizeRefreshGate({
      runId: gate.runId,
      successCount,
      totalCount: results.length,
      status: finalStatus,
      errorMessage: finalStatus === 'partial' ? 'One or more refresh events failed' : undefined,
    })

    return NextResponse.json({
      status: finalStatus,
      message: `Triggered ${successCount}/${results.length} refresh jobs`,
      gateMode: gate.mode,
      note: 'Jobs run asynchronously - data will update in 1-5 minutes',
      details: summary,
      triggeredAt: new Date().toISOString(),
    })
  } catch (error) {
    await finalizeRefreshGate({
      runId: gate.runId,
      successCount: 0,
      totalCount: 5,
      status: 'failed',
      errorMessage: String(error).slice(0, 500),
    })

    console.error('Failed to trigger refresh:', error)
    return NextResponse.json(
      {
        status: 'error',
        message: 'Failed to trigger refresh jobs',
        error: 'Internal server error',
      },
      { status: 500 }
    )
  }
}

// GET endpoint to check last refresh times
export async function GET() {
  return NextResponse.json({
    available: true,
    method: 'POST',
    description: 'Triggers manual refresh of driver data (VIX, Crush, China, Tariff)',
    rateLimit: '60s cooldown (DB-backed, process-local fallback)',
    functions: [
      'fred-daily-volatility (VIX, VIX3M, OVX)',
      'board-crush-daily (Board Crush, Oil Share)',
      'fred-daily-fx (CNY/USD)',
      'fred-daily-trump-effect (TPU, EMV)',
      'trump-effect.refresh-and-sync (producer SLA gate -> specialist.signals-sync)',
    ],
    disabled: [],
  })
}
