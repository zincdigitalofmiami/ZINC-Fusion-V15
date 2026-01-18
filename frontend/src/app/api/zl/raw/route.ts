/**
 * GET /api/zl/raw
 * Clean ZL OHLCV straight from mkt.futures_1d
 * Query params: days (default 365)
 */
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'

interface PriceRow {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export async function GET(request: NextRequest) {
  const days = parseInt(request.nextUrl.searchParams.get('days') || '365', 10)

  try {
    const rows = await query<PriceRow>(`
      SELECT 
        event_date::text as date,
        open,
        high,
        low,
        close,
        volume::int
      FROM mkt.futures_1d
      WHERE symbol = 'ZL'
      ORDER BY event_date DESC
      LIMIT $1
    `, [days])

    return NextResponse.json({
      symbol: 'ZL',
      source: 'mkt.futures_1d',
      count: rows.length,
      data: rows.reverse()
    })
  } catch (error) {
    console.error('Database error:', error)
    return NextResponse.json({ error: 'Query failed' }, { status: 500 })
  }
}
