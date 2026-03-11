/**
 * Vegas Glide Sync API
 * POST /api/vegas/sync - Queue a manual Inngest sync
 *
 * Data Flow: Glide API (READ ONLY) → Inngest writer → vegas.vegas_* tables
 * Guardrail: local/dev runtimes must not trigger Vegas syncs.
 */
import { NextResponse } from 'next/server'
import { inngest } from '@/inngest/client'
import { GLIDE_VEGAS_SYNC_EVENT } from '@/inngest/glide-vegas'
import { isVegasSyncBlocked } from '@/lib/vegas-sync-guard'

const VEGAS_GLIDE_TABLES = [
  'restaurants',
  'casinos',
  'fryers',
  'export_list',
  'shifts',
]

export async function POST() {
  if (isVegasSyncBlocked()) {
    return NextResponse.json(
      {
        success: false,
        status: 'disabled_local',
        error: 'Vegas sync is cloud-only and disabled in local/dev runtime',
      },
      { status: 403 }
    )
  }

  try {
    await inngest.send({
      name: GLIDE_VEGAS_SYNC_EVENT,
      data: {
        trigger: 'manual_api',
        requested_at: new Date().toISOString(),
      },
    })

    return NextResponse.json(
      {
        success: true,
        status: 'queued',
        event: GLIDE_VEGAS_SYNC_EVENT,
        message: 'Vegas sync queued in Inngest',
        tables: VEGAS_GLIDE_TABLES,
      },
      { status: 202 }
    )
  } catch (error) {
    console.error('Vegas sync trigger error:', error)
    return NextResponse.json(
      { success: false, error: 'Failed to queue vegas sync' },
      { status: 500 }
    )
  }
}

export async function GET() {
  const blocked = isVegasSyncBlocked()
  return NextResponse.json({
    endpoint: '/api/vegas/sync',
    method: 'POST to queue a manual sync event',
    event: GLIDE_VEGAS_SYNC_EVENT,
    tables: VEGAS_GLIDE_TABLES,
    scope: 'cloud_only',
    enabled: !blocked,
    status: blocked ? 'disabled_local' : 'enabled',
    note: 'Local/dev runtimes must not trigger Vegas syncs.',
  })
}
