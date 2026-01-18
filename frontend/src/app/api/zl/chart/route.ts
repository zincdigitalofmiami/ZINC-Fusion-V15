/**
 * GET /api/zl/chart
 * Returns ZL daily OHLCV from mkt.futures_1d (freshest daily data)
 * Query params: days (default 365)
 * Runtime query - no repo dependency
 */
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'

interface DailyRow {
  event_date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const days = parseInt(searchParams.get('days') || '365', 10)

  try {
    const rows = await query<DailyRow>(`
      SELECT 
        event_date,
        open,
        high,
        low,
        close,
        volume
      FROM mkt.futures_1d
      WHERE symbol = 'ZL'
      ORDER BY event_date DESC
      LIMIT $1
    `, [days])

    // Reverse to chronological order and format for lightweight-charts
    const series = rows.reverse().map(row => ({
      time: row.event_date,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
      volume: row.volume,
    }))

    return NextResponse.json({
      symbol: 'ZL',
      interval: '1d',
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
