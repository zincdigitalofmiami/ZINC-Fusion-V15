/**
 * GET /api/zl/yahoo
 * (Legacy route) Returns ZL data from analytics tables populated by Databento jobs.
 *
 * Query params:
 *   interval: 15m, 1h, 1d (default: 15m)
 *   range: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max (default: 1mo)
 */
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const interval = searchParams.get('interval') || '15m'
  const range = searchParams.get('range') || '1mo'
  
  // Validate interval
  const validIntervals = ['15m', '1h', '1d']
  if (!validIntervals.includes(interval)) {
    return NextResponse.json(
      { error: `Invalid interval. Valid: ${validIntervals.join(', ')}` },
      { status: 400 }
    )
  }
  
  // Validate range
  const validRanges = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max']
  if (!validRanges.includes(range)) {
    return NextResponse.json(
      { error: `Invalid range. Valid: ${validRanges.join(', ')}` },
      { status: 400 }
    )
  }

  const rangeDays: Record<string, number | null> = {
    '1d': 1,
    '5d': 5,
    '1mo': 30,
    '3mo': 90,
    '6mo': 180,
    '1y': 365,
    '2y': 730,
    '5y': 1825,
    '10y': 3650,
    'ytd': null,
    'max': null,
  }

  try {
    const now = new Date()
    let startDate: Date | null = null
    if (range === 'ytd') {
      startDate = new Date(Date.UTC(now.getUTCFullYear(), 0, 1))
    } else if (rangeDays[range] != null) {
      startDate = new Date(now.getTime() - (rangeDays[range] as number) * 24 * 60 * 60 * 1000)
    }

    if (interval === '15m') {
      const rows = await query<{
        timestamp: string
        open: number
        high: number
        low: number
        close: number
        volume: number | null
      }>(
        `
        SELECT timestamp, open, high, low, close, volume
        FROM analytics.zl_price_15m
        ${startDate ? 'WHERE timestamp >= $1' : ''}
        ORDER BY timestamp ASC
        `,
        startDate ? [startDate.toISOString()] : undefined
      )

      return NextResponse.json({
        symbol: 'ZL',
        currency: 'USD',
        exchange: 'CME Globex',
        interval,
        range,
        count: rows.length,
        data: rows.map((r) => ({
          timestamp: new Date(r.timestamp).toISOString(),
          open: r.open,
          high: r.high,
          low: r.low,
          close: r.close,
          volume: r.volume ?? 0,
        })),
      })
    }

    if (interval === '1h') {
      const rows = await query<{
        timestamp: string
        open: number
        high: number
        low: number
        close: number
        volume: number | null
      }>(
        `
        SELECT timestamp, open, high, low, close, volume
        FROM analytics.zl_price_1h
        ${startDate ? 'WHERE timestamp >= $1' : ''}
        ORDER BY timestamp ASC
        `,
        startDate ? [startDate.toISOString()] : undefined
      )

      return NextResponse.json({
        symbol: 'ZL',
        currency: 'USD',
        exchange: 'CME Globex',
        interval,
        range,
        count: rows.length,
        data: rows.map((r) => ({
          timestamp: new Date(r.timestamp).toISOString(),
          open: Number(r.open),
          high: Number(r.high),
          low: Number(r.low),
          close: Number(r.close),
          volume: r.volume ?? 0,
        })),
      })
    }

    const rows = await query<{
      event_date: string
      open: number
      high: number
      low: number
      close: number
      volume: number | null
    }>(
      `
      SELECT event_date, open, high, low, close, volume
      FROM analytics.zl_price_1d
      ${startDate ? 'WHERE event_date >= $1' : ''}
      ORDER BY event_date ASC
      `,
      startDate ? [startDate.toISOString().slice(0, 10)] : undefined
    )

    return NextResponse.json({
      symbol: 'ZL',
      currency: 'USD',
      exchange: 'CME Globex',
      interval,
      range,
      count: rows.length,
      data: rows.map((r) => ({
        timestamp: new Date(r.event_date).toISOString(),
        open: Number(r.open),
        high: Number(r.high),
        low: Number(r.low),
        close: Number(r.close),
        volume: r.volume ?? 0,
      })),
    })
  } catch (error) {
    console.error('ZL API error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'ZL API request failed' },
      { status: 500 }
    )
  }
}
