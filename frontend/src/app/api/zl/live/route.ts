/**
 * GET /api/zl/live
 *
 * Returns the latest ZL price.
 * Primary: mkt.futures_1d (always available, updated daily by Inngest)
 * Enhancement: Databento historical API (minute bars, ~24h delay)
 *
 * DB-first approach ensures the dashboard ALWAYS gets a price,
 * even when Databento is slow, down, or API key is missing.
 */
import { NextResponse } from 'next/server'
import { query } from '@/lib/db'
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from '@/lib/databento'

// ---------------------------------------------------------------------------
// DB fallback: fast, always works
// ---------------------------------------------------------------------------
interface DbPriceRow {
  event_date: string
  close: number
  open: number
  high: number
  low: number
  volume: number
}

async function getDbPrice(): Promise<{
  price: number
  timestamp: string
  change: number
  change_pct: number
  previous_close: number
  high: number
  low: number
  volume: number
} | null> {
  const rows = await query<DbPriceRow>(`
    SELECT event_date::text, close, open, high, low, volume::int
    FROM mkt.futures_1d
    WHERE symbol = 'ZL' AND close IS NOT NULL
    ORDER BY event_date DESC
    LIMIT 2
  `)
  if (rows.length === 0) return null
  const latest = rows[0]
  const prev = rows.length > 1 ? rows[1] : latest
  const change = latest.close - prev.close
  const changePct = prev.close !== 0 ? (change / prev.close) * 100 : 0
  return {
    price: latest.close,
    timestamp: latest.event_date,
    change,
    change_pct: changePct,
    previous_close: prev.close,
    high: latest.high,
    low: latest.low,
    volume: latest.volume,
  }
}

// ---------------------------------------------------------------------------
// Databento: richer minute-bar data but may be slow / stale / unavailable
// ---------------------------------------------------------------------------
async function getDatabento(): Promise<{
  price: number
  timestamp: string
  change: number
  change_pct: number
  previous_close: number
  volume: number
  forming_bars: Record<string, unknown>
} | null> {
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
  }, 5000) // 5s timeout

  const bars = parseDatabentoOhlcvCsv(csv)
  if (bars.length === 0) return null

  const latest = bars[bars.length - 1]
  const dayOpen = bars[0].open
  let dayHigh = latest.high
  let dayLow = latest.low
  let dayVolume = 0
  for (const bar of bars) {
    if (bar.high > dayHigh) dayHigh = bar.high
    if (bar.low < dayLow) dayLow = bar.low
    dayVolume += bar.volume
  }

  const bucket15m = Math.floor(latest.tsEvent.getTime() / (15 * 60 * 1000)) * (15 * 60 * 1000)
  const bucket1h = Math.floor(latest.tsEvent.getTime() / (60 * 60 * 1000)) * (60 * 60 * 1000)
  const dayStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))

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
  const f15m = agg(bars.filter(b => b.tsEvent.getTime() >= bucket15m))
  if (f15m) formingBars['15m'] = f15m
  const f1h = agg(bars.filter(b => b.tsEvent.getTime() >= bucket1h))
  if (f1h) formingBars['1h'] = f1h
  formingBars['1d'] = {
    bar_start: dayStart.toISOString(),
    open: dayOpen, high: dayHigh, low: dayLow, close: latest.close,
    volume: dayVolume, updated_at: new Date().toISOString(),
  }

  const change = latest.close - dayOpen
  const changePct = dayOpen !== 0 ? (change / dayOpen) * 100 : 0
  return {
    price: latest.close,
    timestamp: latest.tsEvent.toISOString(),
    change, change_pct: changePct,
    previous_close: dayOpen,
    volume: dayVolume,
    forming_bars: formingBars,
  }
}

// ---------------------------------------------------------------------------
// HANDLER — DB-first, Databento-enhanced
// ---------------------------------------------------------------------------
export async function GET() {
  try {
    // Race: DB is fast (~50ms), Databento can be slow (2-10s)
    // Always get DB price; try Databento in parallel with 5s timeout
    const [dbResult, dbentoResult] = await Promise.all([
      getDbPrice().catch((e) => { console.error('DB price error:', e); return null }),
      getDatabento().catch((e) => { console.error('Databento price error:', e); return null }),
    ])

    // Prefer Databento if it returned data (higher resolution)
    if (dbentoResult) {
      return NextResponse.json({
        symbol: 'ZL',
        price: dbentoResult.price,
        timestamp: dbentoResult.timestamp,
        volume: dbentoResult.volume,
        updated_at: new Date().toISOString(),
        previous_close: dbentoResult.previous_close,
        change: dbentoResult.change,
        change_pct: dbentoResult.change_pct,
        source: 'databento',
        forming_bars: dbentoResult.forming_bars,
      })
    }

    // Fallback to DB — always available
    if (dbResult) {
      return NextResponse.json({
        symbol: 'ZL',
        price: dbResult.price,
        timestamp: dbResult.timestamp,
        volume: dbResult.volume,
        updated_at: new Date().toISOString(),
        previous_close: dbResult.previous_close,
        change: dbResult.change,
        change_pct: dbResult.change_pct,
        source: 'mkt.futures_1d',
        forming_bars: {},
      })
    }

    // Both failed
    return NextResponse.json({
      symbol: 'ZL',
      price: null,
      timestamp: null,
      updated_at: new Date().toISOString(),
      source: 'none',
      error: 'No price data available from any source',
      forming_bars: {},
    })
  } catch (error) {
    console.error('ZL live price error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Price fetch failed' },
      { status: 500 }
    )
  }
}
