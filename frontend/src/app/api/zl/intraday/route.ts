/**
 * GET /api/zl/intraday
 * Returns ZL 15-minute bars from analytics.price_15m
 * Query params: hours (default 24)
 * Runtime query - no repo dependency
 */
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'

interface IntradayRow {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const hours = parseInt(searchParams.get('hours') || '24', 10)

  try {
    const rows = await query<IntradayRow>(`
      SELECT
        timestamp,
        open,
        high,
        low,
        close,
        volume
      FROM analytics.price_15m
      WHERE timestamp > NOW() - INTERVAL '${hours} hours'
      ORDER BY timestamp ASC
    `)

    // Format for lightweight-charts (unix timestamp)
    const bars = rows.map(row => ({
      time: Math.floor(new Date(row.timestamp).getTime() / 1000),
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
      volume: row.volume,
    }))

    return NextResponse.json({
      symbol: 'ZL',
      interval: '15m',
      count: bars.length,
      bars,
    })
  } catch (error) {
    console.error('Database error:', error)
    return NextResponse.json(
      { error: 'Database query failed' },
      { status: 500 }
    )
  }
}
