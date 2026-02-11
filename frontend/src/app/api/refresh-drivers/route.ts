/**
 * Manual Refresh Trigger for Key Market Drivers
 *
 * Triggers Inngest functions to refresh the data feeding the 4 driver cards:
 * - VIX: fredDailyVolatility (VIXCLS, VXVCLS, OVXCLS)
 * - Crush: boardCrushDaily
 * - China: fredDailyFx (DEXCHUS)
 * - Tariff: fredDailyTrumpEffect (USEPUINDXM, EMVTRADEPOLEMV)
 * - Trump Effect Signals: trumpEffectSignalSyncManual
 */

import { NextResponse } from 'next/server'
import { inngest } from '@/inngest/client'

export const dynamic = 'force-dynamic'

export async function POST() {
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
      // Sync trump_effect specialist signal rows for dashboard/API consumers
      inngest.send({
        name: 'trump-effect.signal-sync',
        data: { trigger: 'manual', timestamp: new Date().toISOString() },
      }),
    ])

    const summary = results.map((r, i) => {
      const names = ['volatility', 'crush', 'fx', 'trump-effect-fred', 'trump-effect-signals']
      return {
        function: names[i],
        status: r.status,
        error: r.status === 'rejected' ? String(r.reason) : undefined,
      }
    })

    const successCount = results.filter(r => r.status === 'fulfilled').length

    return NextResponse.json({
      status: successCount === results.length ? 'success' : 'partial',
      message: `Triggered ${successCount}/${results.length} refresh jobs`,
      note: 'Jobs run asynchronously - data will update in 1-5 minutes',
      details: summary,
      triggeredAt: new Date().toISOString(),
    })
  } catch (error) {
    console.error('Failed to trigger refresh:', error)
    return NextResponse.json(
      {
        status: 'error',
        message: 'Failed to trigger refresh jobs',
        error: error instanceof Error ? error.message : String(error),
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
    functions: [
      'fred-daily-volatility (VIX, VIX3M, OVX)',
      'board-crush-daily (Board Crush, Oil Share)',
      'fred-daily-fx (CNY/USD)',
      'fred-daily-trump-effect (TPU, EMV)',
      'trump-effect.signal-sync (specialist signal sync)',
    ],
    disabled: [],
  })
}
