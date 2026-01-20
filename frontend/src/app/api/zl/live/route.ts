/**
 * GET /api/zl/live
 * Current ZL price from analytics.zl_price_15m (latest bar)
 * Updated every ~15 min by Yahoo job
 */
import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

interface ZlLive {
  close: number
  previous_close: number
  change: number
  change_percent: number
  day_high: number
  day_low: number
  open: number
  volume: number
  timestamp: string
  source: string
}

export async function GET() {
  try {
    const rows = await query<ZlLive>(`
      SELECT
        close,
        previous_close,
        change,
        change_percent,
        day_high,
        day_low,
        open,
        volume,
        timestamp,
        source
      FROM analytics.zl_price_15m
      ORDER BY timestamp DESC
      LIMIT 1
    `)

    if (!rows.length) {
      return NextResponse.json(
        { error: 'No price data available' },
        { status: 404 }
      )
    }

    const row = rows[0]
    return NextResponse.json({
      symbol: 'ZL',
      price: row.close,
      previous_close: row.previous_close,
      change: row.change,
      change_pct: row.change_percent,
      day_high: row.day_high,
      day_low: row.day_low,
      day_open: row.open,
      volume: row.volume,
      timestamp: row.timestamp,
      source: row.source
    })
  } catch (error) {
    console.error('Database error:', error)
    return NextResponse.json(
      { error: 'Database query failed' },
      { status: 500 }
    )
  }
}
