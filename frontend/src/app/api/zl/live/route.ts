/**
 * GET /api/zl/live
 * Returns latest ZL price from public.latest_prices
 * Runtime query - no repo dependency
 */
import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

interface LatestPrice {
  symbol: string
  price: number
  previous_close: number
  change: number
  change_percent: number
  day_high: number
  day_low: number
  day_open: number
  volume: number
  timestamp: string
  market_state: string
  source: string
  updated_at: string
}

export async function GET() {
  try {
    const rows = await query<LatestPrice>(`
      SELECT 
        symbol,
        price,
        previous_close,
        change,
        change_percent,
        day_high,
        day_low,
        day_open,
        volume,
        timestamp,
        market_state,
        source,
        updated_at
      FROM public.latest_prices
      WHERE symbol = 'ZL'
      LIMIT 1
    `)

    if (!rows.length) {
      return NextResponse.json(
        { error: 'No price data available' },
        { status: 404 }
      )
    }

    return NextResponse.json(rows[0])
  } catch (error) {
    console.error('Database error:', error)
    return NextResponse.json(
      { error: 'Database query failed' },
      { status: 500 }
    )
  }
}
