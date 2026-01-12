/**
 * GET /api/zl/yahoo
 * LIVE data directly from Yahoo Finance Chart API
 * 
 * Query params:
 *   interval: 15m, 1h, 1d (default: 15m)
 *   range: 1d, 5d, 1mo, 3mo, 6mo, 1y (default: 1mo)
 * 
 * This hits Yahoo directly - no database, no calculated data, REAL market data
 */
import { NextRequest, NextResponse } from 'next/server'

const YAHOO_SYMBOL = 'ZL=F' // Soybean Oil Futures

interface YahooQuote {
  timestamp: number[]
  indicators: {
    quote: [{
      open: (number | null)[]
      high: (number | null)[]
      low: (number | null)[]
      close: (number | null)[]
      volume: (number | null)[]
    }]
  }
}

interface YahooResponse {
  chart: {
    result: [{
      meta: {
        symbol: string
        regularMarketPrice: number
        previousClose: number
        currency: string
        exchangeName: string
        instrumentType: string
        regularMarketTime: number
      }
      timestamp: number[]
      indicators: {
        quote: [{
          open: (number | null)[]
          high: (number | null)[]
          low: (number | null)[]
          close: (number | null)[]
          volume: (number | null)[]
        }]
      }
    }]
    error: null | { code: string; description: string }
  }
}

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const interval = searchParams.get('interval') || '15m'
  const range = searchParams.get('range') || '1mo'
  
  // Validate interval
  const validIntervals = ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo']
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

  try {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${YAHOO_SYMBOL}?interval=${interval}&range=${range}&includePrePost=false`
    
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
      },
      next: { revalidate: 60 } // Cache for 60 seconds
    })
    
    if (!res.ok) {
      throw new Error(`Yahoo API returned ${res.status}`)
    }
    
    const json: YahooResponse = await res.json()
    
    if (json.chart.error) {
      throw new Error(json.chart.error.description)
    }
    
    const result = json.chart.result[0]
    const { meta, timestamp, indicators } = result
    const quote = indicators.quote[0]
    
    // Build OHLCV array, filtering out null bars
    const data = timestamp
      .map((ts, i) => ({
        timestamp: new Date(ts * 1000).toISOString(),
        open: quote.open[i],
        high: quote.high[i],
        low: quote.low[i],
        close: quote.close[i],
        volume: quote.volume[i],
      }))
      .filter(bar => bar.open !== null && bar.close !== null)
    
    return NextResponse.json({
      symbol: meta.symbol,
      currency: meta.currency,
      exchange: meta.exchangeName,
      interval,
      range,
      regularMarketPrice: meta.regularMarketPrice,
      previousClose: meta.previousClose,
      lastUpdate: new Date(meta.regularMarketTime * 1000).toISOString(),
      count: data.length,
      data,
    })
  } catch (error) {
    console.error('Yahoo API error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Yahoo API request failed' },
      { status: 500 }
    )
  }
}
