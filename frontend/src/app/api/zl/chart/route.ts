/**
 * GET /api/zl/chart
 * Returns ZL daily OHLCV from silver.futures_prices_1d
 * Query params: days (default 365)
 * Runtime query - no repo dependency
 */
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'

interface PriceRow {
  trade_date: string
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
    const rows = await query<PriceRow>(`
      SELECT 
        trade_date,
        open,
        high,
        low,
        close,
        volume
      FROM silver.futures_prices_1d
      WHERE canonical_id = 'ZL'
      ORDER BY trade_date DESC
      LIMIT $1
    `, [days])

    // Reverse to chronological order and format for lightweight-charts
    const series = rows.reverse().map(row => ({
      time: row.trade_date,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
      volume: row.volume,
    }))

    return NextResponse.json({
      symbol: 'ZL',
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
