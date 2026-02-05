/**
 * GET /api/options
 * Returns options on futures from mkt.options_1d (Databento-sourced).
 * Query params: underlying (default ZL), days (default 30), limit (default 500)
 */
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'

const ALLOWED_UNDERLYINGS = /^[A-Z0-9]{1,6}$/

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const underlying = (searchParams.get('underlying') || 'ZL').toUpperCase()
  const days = Math.max(1, Math.min(365, parseInt(searchParams.get('days') || '30', 10)))
  const limit = Math.max(1, Math.min(2000, parseInt(searchParams.get('limit') || '500', 10)))

  if (!ALLOWED_UNDERLYINGS.test(underlying)) {
    return NextResponse.json(
      { error: 'Invalid underlying; use 1–6 alphanumeric chars (e.g. ZL, ZS, CL)' },
      { status: 400 }
    )
  }

  try {
    const rows = await query<{
      event_date: string
      expiration: string
      strike: number
      option_type: string
      open: number | null
      high: number | null
      low: number | null
      close: number | null
      volume: number | null
      open_interest: number | null
      bid: number | null
      ask: number | null
      implied_volatility: number | null
      delta: number | null
    }>(
      `SELECT
        event_date,
        expiration,
        strike,
        option_type,
        open,
        high,
        low,
        close,
        volume,
        open_interest,
        bid,
        ask,
        implied_volatility,
        delta
      FROM mkt.options_1d
      WHERE underlying = $1
        AND event_date >= CURRENT_DATE - ($2::text || ' days')::interval
        AND event_date <= CURRENT_DATE
      ORDER BY event_date DESC, expiration, strike
      LIMIT $3`,
      [underlying, days, limit]
    )

    return NextResponse.json({
      underlying,
      source: 'mkt.options_1d',
      count: rows.length,
      days,
      limit,
      data: rows,
    })
  } catch (error) {
    console.error('Options API error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch options from mkt.options_1d' },
      { status: 500 }
    )
  }
}
