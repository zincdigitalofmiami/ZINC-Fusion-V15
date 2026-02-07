/**
 * GET /api/zl/live
 *
 * Returns the latest ZL price directly from Databento HTTP API.
 * Pure Databento - no database queries.
 */
import { NextResponse } from 'next/server'
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from '@/lib/databento'

export async function GET() {
  try {
    // Databento historical API has ~24h delay - data available up to midnight UTC
    // Fetch last 48 hours ending at midnight UTC today to get most recent data
    const now = new Date()
    const endOfYesterday = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))
    const start = new Date(endOfYesterday.getTime() - 48 * 60 * 60 * 1000)

    const csv = await fetchDatabentoCsv({
      dataset: 'GLBX.MDP3',
      schema: 'ohlcv-1m',
      symbols: 'ZL.n.0',
      stype_in: 'continuous',
      start: start.toISOString(),
      end: endOfYesterday.toISOString(),
      encoding: 'csv',
      pretty_ts: 'true',
      pretty_px: 'true',
    })

    const bars = parseDatabentoOhlcvCsv(csv)

    if (bars.length === 0) {
      return NextResponse.json({
        symbol: 'ZL',
        price: null,
        timestamp: null,
        source: 'databento',
        error: 'No data - market may be closed',
        forming_bars: {},
      })
    }

    const latest = bars[bars.length - 1]

    let dayHigh = latest.high
    let dayLow = latest.low
    const dayOpen = bars[0].open
    let dayVolume = 0

    for (const bar of bars) {
      if (bar.high > dayHigh) dayHigh = bar.high
      if (bar.low < dayLow) dayLow = bar.low
      dayVolume += bar.volume
    }

    const bucket15m = Math.floor(latest.tsEvent.getTime() / (15 * 60 * 1000)) * (15 * 60 * 1000)
    const bucket1h = Math.floor(latest.tsEvent.getTime() / (60 * 60 * 1000)) * (60 * 60 * 1000)
    const dayStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))

    const bars15m = bars.filter(b => b.tsEvent.getTime() >= bucket15m)
    const bars1h = bars.filter(b => b.tsEvent.getTime() >= bucket1h)

    const agg = (subset: typeof bars) => {
      if (subset.length === 0) return null
      return {
        bar_start: subset[0].tsEvent.toISOString(),
        open: subset[0].open,
        high: Math.max(...subset.map(b => b.high)),
        low: Math.min(...subset.map(b => b.low)),
        close: subset[subset.length - 1].close,
        volume: subset.reduce((sum, b) => sum + b.volume, 0),
        updated_at: new Date().toISOString(),
      }
    }

    const formingBars: Record<string, unknown> = {}
    const f15m = agg(bars15m)
    if (f15m) formingBars['15m'] = f15m
    const f1h = agg(bars1h)
    if (f1h) formingBars['1h'] = f1h
    formingBars['1d'] = {
      bar_start: dayStart.toISOString(),
      open: dayOpen,
      high: dayHigh,
      low: dayLow,
      close: latest.close,
      volume: dayVolume,
      updated_at: new Date().toISOString(),
    }

    const change = latest.close - dayOpen
    const changePct = dayOpen !== 0 ? (change / dayOpen) * 100 : 0

    return NextResponse.json({
      symbol: 'ZL',
      price: latest.close,
      timestamp: latest.tsEvent.toISOString(),
      volume: latest.volume,
      updated_at: new Date().toISOString(),
      previous_close: dayOpen,
      change,
      change_pct: changePct,
      source: 'databento',
      forming_bars: formingBars,
    })
  } catch (error) {
    console.error('Databento fetch error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Databento fetch failed' },
      { status: 500 }
    )
  }
}
