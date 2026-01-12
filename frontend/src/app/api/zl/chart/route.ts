/**
 * GET /api/zl/chart
 * Returns ZL 15m OHLCV from analytics.zl_intraday
 * Query params: hours (default 168 = 7 days)
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
  const hours = parseInt(searchParams.get('hours') || '168', 10) // 7 days default

  try {
    const rows = await query<IntradayRow>(`
      SELECT 
        timestamp,
        open,
        high,
        low,
        close,
        volume
      FROM analytics.zl_intraday
      WHERE timestamp > NOW() - INTERVAL '${hours} hours'
      ORDER BY timestamp ASC
    `)

    // Format for lightweight-charts
    const series = rows.map(row => ({
      time: row.timestamp,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
      volume: row.volume,
    }))

    return NextResponse.json({
      symbol: 'ZL',
      interval: '15m',
      count: series.length,
      series,
    })
  } catch (error) {
    console.error('Database error:', error)
    return NextResponse.json(
      { error: 'Database query failed' },
      { status: 500 }
    )
  }
}
