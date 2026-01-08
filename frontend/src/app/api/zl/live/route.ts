/**
 * GET /api/zl/live
 * Current ZL price from analytics.zl_live
 * Updated every ~15 min by Yahoo job
 */
import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

interface ZlLive {
  price: number
  previous_close: number
  change: number
  change_pct: number
  day_high: number
  day_low: number
  day_open: number
  volume: number
  timestamp: string
  source: string
  updated_at: string
}

export async function GET() {
  try {
    const rows = await query<ZlLive>(`
      SELECT 
        price,
        previous_close,
        change,
        change_pct,
        day_high,
        day_low,
        day_open,
        volume,
        timestamp,
        source,
        updated_at
      FROM analytics.zl_live
      LIMIT 1
    `)

    if (!rows.length) {
      return NextResponse.json(
        { error: 'No price data available' },
        { status: 404 }
      )
    }

    return NextResponse.json({
      symbol: 'ZL',
      ...rows[0]
    })
  } catch (error) {
    console.error('Database error:', error)
    return NextResponse.json(
      { error: 'Database query failed' },
      { status: 500 }
    )
  }
}
