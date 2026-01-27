/**
 * GET /api/zl/live
 * Real-time ZL price from analytics.zl_latest + forming bars
 * Updated every ~1 min by Databento live connector on Fly.io
 */
import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

interface ZlLatest {
  price: number
  timestamp: string
  volume: number
  updated_at: string
}

interface FormingBar {
  timeframe: string
  bar_start: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  updated_at: string
}

export async function GET() {
  try {
    // Get latest price
    const latestRows = await query<ZlLatest>(`
      SELECT price, timestamp, volume, updated_at
      FROM analytics.zl_latest
      WHERE id = 1
    `)

    // Get forming bars (incomplete candles)
    const formingRows = await query<FormingBar>(`
      SELECT timeframe, bar_start, open, high, low, close, volume, updated_at
      FROM analytics.zl_forming_bar
      ORDER BY timeframe
    `)

    // Get previous day close for change calculation
    const prevCloseRows = await query<{ close: number }>(`
      SELECT close
      FROM analytics.zl_price_1d
      ORDER BY event_date DESC
      LIMIT 1 OFFSET 1
    `)

    if (!latestRows.length) {
      // Fallback to 15m table if live not available yet
      const fallbackRows = await query<{ close: number; timestamp: string }>(`
        SELECT close, timestamp
        FROM analytics.zl_price_15m
        ORDER BY timestamp DESC
        LIMIT 1
      `)
      if (fallbackRows.length) {
        return NextResponse.json({
          symbol: 'ZL',
          price: fallbackRows[0].close,
          timestamp: fallbackRows[0].timestamp,
          source: 'fallback_15m',
          forming_bars: {},
        })
      }
      return NextResponse.json(
        { error: 'No price data available' },
        { status: 404 }
      )
    }

    const latest = latestRows[0]
    const prevClose = prevCloseRows[0]?.close || null
    const change = prevClose ? latest.price - prevClose : null
    const changePct = prevClose ? ((latest.price - prevClose) / prevClose) * 100 : null

    // Build forming bars object keyed by timeframe
    const formingBars: Record<string, {
      bar_start: string
      open: number
      high: number
      low: number
      close: number
      volume: number
      updated_at: string
    }> = {}
    
    for (const bar of formingRows) {
      formingBars[bar.timeframe] = {
        bar_start: bar.bar_start,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume,
        updated_at: bar.updated_at,
      }
    }

    return NextResponse.json({
      symbol: 'ZL',
      price: latest.price,
      timestamp: latest.timestamp,
      volume: latest.volume,
      updated_at: latest.updated_at,
      previous_close: prevClose,
      change: change,
      change_pct: changePct,
      source: 'databento_live',
      forming_bars: formingBars,
    })
  } catch (error) {
    console.error('Database error:', error)
    return NextResponse.json(
      { error: 'Database query failed' },
      { status: 500 }
    )
  }
}
