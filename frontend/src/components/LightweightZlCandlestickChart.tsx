'use client'

import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  CandlestickSeries,
  AreaSeries,
  LineSeries,
  ColorType,
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
  LineStyle,
  CandlestickData,
} from 'lightweight-charts'

interface PriceData {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface ForecastPoint {
  horizon_days: number
  price_p30: number | null
  price_p50: number | null
  price_p70: number | null
}

// Interval configuration
type IntervalKey = '15m' | '1h' | '1m' | '3m' | '6m' | '1y' | '2y'

interface IntervalConfig {
  label: string
  endpoint: string
  barLabel: string
  visibleBars: number
  isIntraday: boolean
}

const INTERVALS: Record<IntervalKey, IntervalConfig> = {
  '15m': { label: '15m', endpoint: '/api/zl/intraday?hours=72', barLabel: '15m', visibleBars: 96, isIntraday: true },
  '1h':  { label: '1H',  endpoint: '/api/zl/intraday?hours=168', barLabel: '1H', visibleBars: 72, isIntraday: true },
  '1m':  { label: '1M',  endpoint: '/api/zl/price-1d?days=30', barLabel: '1D', visibleBars: 30, isIntraday: false },
  '3m':  { label: '3M',  endpoint: '/api/zl/price-1d?days=90', barLabel: '1D', visibleBars: 90, isIntraday: false },
  '6m':  { label: '6M',  endpoint: '/api/zl/price-1d?days=180', barLabel: '1D', visibleBars: 150, isIntraday: false },
  '1y':  { label: '1Y',  endpoint: '/api/zl/price-1d?days=365', barLabel: '1D', visibleBars: 150, isIntraday: false },
  '2y':  { label: '2Y',  endpoint: '/api/zl/price-1d?days=730', barLabel: '1D', visibleBars: 150, isIntraday: false },
}

// TradingView exact settings (from user screenshots)
const THEME = {
  // Candle body colors
  upColor: '#26C6DA',
  downColor: '#FF0000',
  // Borders: 0% opacity (transparent per TradingView settings)
  borderUpColor: 'transparent',
  borderDownColor: 'transparent',
  // Wicks: White/light gray (NOT body color - per TradingView)
  wickUpColor: '#FFFFFF',
  wickDownColor: 'rgba(178,181,190,0.83)',
  // Grid: 4-7% opacity (TradingView default)
  gridColor: 'rgba(255,255,255,0.04)',
  // Crosshair
  crosshairColor: 'rgba(139,92,246,0.6)',
  labelBgColor: 'rgba(20,10,40,0.9)',
  textColor: 'rgba(255,255,255,0.4)',
  // Forecast band (pink/magenta)
  forecastBandColor: 'rgba(236, 72, 153, 0.15)',
  forecastLineColor: 'rgba(236, 72, 153, 0.4)',
  forecastCenterColor: 'rgba(236, 72, 153, 0.8)',
}

// Aggregate 15m bars into 1h bars
function aggregate15mTo1h(bars: PriceData[]): PriceData[] {
  const hourlyBars: PriceData[] = []

  for (let i = 0; i < bars.length; i += 4) {
    const chunk = bars.slice(i, i + 4)
    if (chunk.length === 0) continue

    const hourBar: PriceData = {
      timestamp: chunk[0].timestamp,
      open: chunk[0].open,
      high: Math.max(...chunk.map(b => b.high)),
      low: Math.min(...chunk.map(b => b.low)),
      close: chunk[chunk.length - 1].close,
      volume: chunk.reduce((sum, b) => sum + b.volume, 0),
    }
    hourlyBars.push(hourBar)
  }

  return hourlyBars
}

export function LightweightZlCandlestickChart({
  height = '70vh',
}: {
  height?: string | number
}) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const fitContentCalledRef = useRef(false)

  const [selectedInterval, setSelectedInterval] = useState<IntervalKey>('6m')
  const [priceData, setPriceData] = useState<PriceData[]>([])
  const [forecastData, setForecastData] = useState<ForecastPoint[]>([])
  const [lastPrice, setLastPrice] = useState<number | null>(null)
  const [priceChange, setPriceChange] = useState<number>(0)
  const [volatility, setVolatility] = useState<string>('--')
  const [highPrice, setHighPrice] = useState<number | null>(null)
  const [lowPrice, setLowPrice] = useState<number | null>(null)
  const [isLive, setIsLive] = useState<boolean>(false)
  const [lastUpdate, setLastUpdate] = useState<string>('')
  const [hasForecast, setHasForecast] = useState<boolean>(false)

  const intervalConfig = INTERVALS[selectedInterval]

  // Fetch historical data based on selected interval
  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(intervalConfig.endpoint)
        if (!res.ok) {
          console.warn(`Endpoint ${intervalConfig.endpoint} returned ${res.status}`)
          return
        }
        const json = await res.json()

        // Handle different response shapes
        const rawData = json.data || json.bars || []
        if (rawData.length === 0) {
          console.warn(`No data returned for ${selectedInterval}`)
          return
        }

        let parsed = rawData.map((d: PriceData & { time?: number }) => ({
          timestamp: d.timestamp || new Date((d.time || 0) * 1000).toISOString(),
          open: parseFloat(String(d.open)),
          high: parseFloat(String(d.high)),
          low: parseFloat(String(d.low)),
          close: parseFloat(String(d.close)),
          volume: parseFloat(String(d.volume || 0)),
        }))

        // Aggregate to 1h if needed
        if (selectedInterval === '1h') {
          parsed = aggregate15mTo1h(parsed)
        }

        setPriceData(parsed)

        const latest = parsed[parsed.length - 1]
        const prev = parsed[parsed.length - 2]
        setLastPrice(latest.close)

        const highs = parsed.map((d: PriceData) => d.high)
        const lows = parsed.map((d: PriceData) => d.low)
        setHighPrice(Math.max(...highs))
        setLowPrice(Math.min(...lows))

        if (prev) {
          setPriceChange(((latest.close - prev.close) / prev.close) * 100)
        }

        // Calculate volatility (only meaningful for daily data)
        if (!intervalConfig.isIntraday) {
          const last20 = parsed.slice(-20)
          if (last20.length >= 2) {
            const returns: number[] = []
            for (let i = 1; i < last20.length; i++) {
              returns.push(Math.log(last20[i].close / last20[i - 1].close))
            }
            const mean = returns.reduce((a: number, b: number) => a + b, 0) / returns.length
            const variance = returns.reduce((a: number, b: number) => a + Math.pow(b - mean, 2), 0) / returns.length
            const dailyVol = Math.sqrt(variance)
            const annualizedVol = dailyVol * Math.sqrt(252) * 100
            setVolatility(annualizedVol.toFixed(1) + '%')
          }
        } else {
          setVolatility('--')
        }
      } catch (err) {
        console.error('Fetch error:', err)
      }
    }

    // Reset fit flag when interval changes
    fitContentCalledRef.current = false

    fetchData()
    const interval = setInterval(fetchData, intervalConfig.isIntraday ? 60000 : 900000)
    return () => clearInterval(interval)
  }, [selectedInterval, intervalConfig])

  // Fetch forecast data (only for daily intervals)
  useEffect(() => {
    if (intervalConfig.isIntraday) {
      setHasForecast(false)
      return
    }

    const fetchForecast = async () => {
      try {
        const res = await fetch('/api/zl/forecast')
        if (!res.ok) {
          setHasForecast(false)
          return
        }
        const json = await res.json()
        if (json.forecasts && json.forecasts.length > 0) {
          setForecastData(json.forecasts)
          setHasForecast(true)
        } else {
          setHasForecast(false)
        }
      } catch (err) {
        console.error('Forecast fetch error:', err)
        setHasForecast(false)
      }
    }
    fetchForecast()
    const interval = setInterval(fetchForecast, 300000)
    return () => clearInterval(interval)
  }, [intervalConfig.isIntraday])

  // Fetch live data (forming candle) - every 10 seconds
  useEffect(() => {
    const fetchLive = async () => {
      try {
        const res = await fetch('/api/zl/live')
        if (!res.ok) return
        const json = await res.json()

        if (json.price) {
          setLastPrice(json.price)
          setIsLive(json.source === 'databento_live')
          if (json.updated_at) {
            const updated = new Date(json.updated_at)
            setLastUpdate(updated.toLocaleTimeString())
          }
          if (json.change_pct !== null) {
            setPriceChange(json.change_pct)
          }

          // Update forming bar in chart (only for daily)
          if (!intervalConfig.isIntraday && json.forming_bars?.['1d'] && candleSeriesRef.current && priceData.length > 0) {
            const forming = json.forming_bars['1d']
            const lastBar = priceData[priceData.length - 1]
            const time = Math.floor(new Date(lastBar.timestamp).getTime() / 1000) as UTCTimestamp

            candleSeriesRef.current.update({
              time,
              open: forming.open,
              high: forming.high,
              low: forming.low,
              close: forming.close,
            })

            if (forming.high > (highPrice || 0)) setHighPrice(forming.high)
            if (forming.low < (lowPrice || Infinity)) setLowPrice(forming.low)
          }
        }
      } catch {
        // Silent fail for live updates
      }
    }

    fetchLive()
    const liveInterval = setInterval(fetchLive, 10000)
    return () => clearInterval(liveInterval)
  }, [priceData, highPrice, lowPrice, intervalConfig.isIntraday])

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current || priceData.length === 0) return

    // Clean up previous chart safely
    if (chartRef.current) {
      try {
        chartRef.current.remove()
      } catch {
        // Chart already disposed, ignore
      }
      chartRef.current = null
      candleSeriesRef.current = null
    }

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: THEME.textColor,
        fontFamily: 'Inter, sans-serif',
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: THEME.gridColor },
        horzLines: { color: THEME.gridColor },
      },
      crosshair: {
        vertLine: {
          color: THEME.crosshairColor,
          width: 1,
          style: LineStyle.Solid,
          labelBackgroundColor: THEME.labelBgColor,
        },
        horzLine: {
          color: THEME.crosshairColor,
          width: 1,
          style: LineStyle.Solid,
          labelBackgroundColor: THEME.labelBgColor,
        },
      },
      rightPriceScale: {
        borderColor: 'transparent',
        autoScale: true,
        scaleMargins: {
          top: 0.05,
          bottom: 0.05,
        },
      },
      timeScale: {
        borderColor: 'transparent',
        timeVisible: intervalConfig.isIntraday,
        fixLeftEdge: false,
        fixRightEdge: false,
        rightOffset: 20,
      },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        mouseWheel: false,
        pinch: true,
        axisPressedMouseMove: { time: true, price: true },
        axisDoubleClickReset: { time: true, price: true },
      },
    })

    chartRef.current = chart

    // Transform price data to LWC format
    const candleData: CandlestickData<UTCTimestamp>[] = priceData.map((d) => ({
      time: Math.floor(new Date(d.timestamp).getTime() / 1000) as UTCTimestamp,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }))

    // Sort chronologically
    candleData.sort((a, b) => (a.time as number) - (b.time as number))

    // Add forecast band if available (only for daily, rendered first behind candles)
    if (hasForecast && forecastData.length > 0 && candleData.length > 0 && !intervalConfig.isIntraday) {
      const lastCandleTime = candleData[candleData.length - 1].time as number
      const currentPrice = candleData[candleData.length - 1].close

      const forecastTimes: UTCTimestamp[] = [lastCandleTime as UTCTimestamp]
      const forecastP30: number[] = [currentPrice]
      const forecastP50: number[] = [currentPrice]
      const forecastP70: number[] = [currentPrice]

      for (const fc of forecastData) {
        if (fc.price_p30 !== null && fc.price_p50 !== null && fc.price_p70 !== null) {
          const futureTime = (lastCandleTime + fc.horizon_days * 86400) as UTCTimestamp
          forecastTimes.push(futureTime)
          forecastP30.push(fc.price_p30)
          forecastP50.push(fc.price_p50)
          forecastP70.push(fc.price_p70)
        }
      }

      if (forecastTimes.length > 1) {
        const upperBand = chart.addSeries(AreaSeries, {
          topColor: THEME.forecastBandColor,
          bottomColor: 'transparent',
          lineColor: THEME.forecastLineColor,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        })
        upperBand.setData(forecastTimes.map((t, i) => ({ time: t, value: forecastP70[i] })))

        const lowerBand = chart.addSeries(AreaSeries, {
          topColor: 'transparent',
          bottomColor: THEME.forecastBandColor,
          lineColor: THEME.forecastLineColor,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        })
        lowerBand.setData(forecastTimes.map((t, i) => ({ time: t, value: forecastP30[i] })))

        const centerLine = chart.addSeries(LineSeries, {
          color: THEME.forecastCenterColor,
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        })
        centerLine.setData(forecastTimes.map((t, i) => ({ time: t, value: forecastP50[i] })))
      }
    }

    // Add candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: THEME.upColor,
      downColor: THEME.downColor,
      borderUpColor: THEME.borderUpColor,
      borderDownColor: THEME.borderDownColor,
      wickUpColor: THEME.wickUpColor,
      wickDownColor: THEME.wickDownColor,
      priceLineVisible: true,
    })

    candleSeries.setData(candleData)
    candleSeriesRef.current = candleSeries

    // Set initial visible range
    if (!fitContentCalledRef.current && candleData.length > 0) {
      const totalBars = candleData.length
      const visibleBars = Math.min(intervalConfig.visibleBars, totalBars)
      chart.timeScale().setVisibleLogicalRange({
        from: totalBars - visibleBars,
        to: totalBars + 10,
      })
      fitContentCalledRef.current = true
    }

    // Resize observer
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0 || !entries[0].target) return
      const newRect = entries[0].contentRect
      chart.applyOptions({ width: newRect.width, height: newRect.height })
    })
    resizeObserver.observe(chartContainerRef.current)

    return () => {
      resizeObserver.disconnect()
      try {
        chart.remove()
      } catch {
        // Chart already disposed, ignore
      }
    }
  }, [priceData, forecastData, hasForecast, intervalConfig])

  return (
    <div
      className="relative w-full rounded-xl overflow-hidden border border-white/5 flex flex-col"
      style={{
        background: 'linear-gradient(180deg, #131722 0%, #0d1117 100%)',
        height: typeof height === 'number' ? `${height}px` : height,
      }}
    >
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                isLive
                  ? 'bg-green-400 animate-pulse shadow-lg shadow-green-400/50'
                  : 'bg-cyan-400 animate-pulse shadow-lg shadow-cyan-400/50'
              }`}
            />
            <span className="text-sm font-semibold text-white tracking-tight">ZL1!</span>
            {isLive && (
              <span className="px-1.5 py-0.5 text-[8px] font-bold bg-green-500/20 text-green-400 border border-green-500/30 rounded uppercase tracking-wider">
                LIVE
              </span>
            )}
          </div>
          <span className="text-[11px] text-white/30 font-medium">Soybean Oil • {intervalConfig.barLabel}</span>
          {lastUpdate && (
            <span className="text-[9px] text-white/20 font-mono">{lastUpdate}</span>
          )}
          {hasForecast && (
            <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-pink-500/10 border border-pink-500/20">
              <span className="text-[8px] text-pink-400 uppercase tracking-wider font-medium">
                Core Model
              </span>
            </div>
          )}
        </div>

        {/* Interval Tabs + Stats */}
        <div className="flex items-center gap-4">
          {/* Interval Tabs */}
          <div className="flex items-center bg-white/5 rounded-md p-0.5">
            {(Object.keys(INTERVALS) as IntervalKey[]).map((key) => (
              <button
                key={key}
                onClick={() => setSelectedInterval(key)}
                className={`px-2 py-1 text-[10px] font-medium rounded transition-all ${
                  selectedInterval === key
                    ? 'bg-violet-500/30 text-violet-300'
                    : 'text-white/40 hover:text-white/60'
                }`}
              >
                {INTERVALS[key].label}
              </button>
            ))}
          </div>

          <div className="h-3 w-px bg-white/10" />

          {highPrice && lowPrice && (
            <div className="flex items-center gap-3 text-[11px]">
              <div className="flex items-center gap-1">
                <span className="text-white/30">H</span>
                <span className="text-white/60 font-mono">{highPrice.toFixed(2)}</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="text-white/30">L</span>
                <span className="text-white/60 font-mono">{lowPrice.toFixed(2)}</span>
              </div>
            </div>
          )}
          <div className="h-3 w-px bg-white/10" />
          <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/5">
            <span className="text-[9px] text-white/30 uppercase">IV</span>
            <span className="text-[11px] font-mono text-violet-400">{volatility}</span>
          </div>
          {lastPrice && (
            <div className="flex items-center gap-2">
              <span className="text-xl font-semibold text-white tabular-nums">
                {lastPrice.toFixed(2)}
              </span>
              <span
                className="text-xs font-medium tabular-nums"
                style={{ color: priceChange >= 0 ? '#26C6DA' : '#EC0000' }}
              >
                {priceChange >= 0 ? '+' : ''}
                {priceChange.toFixed(2)}%
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Chart area */}
      <div className="relative w-full flex-1 min-h-0">
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
          <img
            src="/chart_watermark.svg"
            alt=""
            className="w-[280px] h-auto opacity-[0.10]"
            style={{ filter: 'grayscale(100%)' }}
          />
        </div>
        <div
          ref={chartContainerRef}
          style={{ width: '100%', height: '100%', position: 'absolute', top: 0, left: 0 }}
        />
      </div>

      {/* Legend */}
      <div className="flex-shrink-0 flex items-center justify-center gap-6 px-4 py-1.5 border-t border-white/5 bg-black/20">
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-3 rounded-sm" style={{ backgroundColor: '#26C6DA' }} />
          <span className="text-[9px] text-white/40 uppercase">Bull</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-3 rounded-sm" style={{ backgroundColor: '#EC0000' }} />
          <span className="text-[9px] text-white/40 uppercase">Bear</span>
        </div>
        {hasForecast && (
          <>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-1.5 rounded-sm bg-pink-500/30 border border-pink-500/50" />
              <span className="text-[9px] text-white/40 uppercase">P30-P70</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div
                className="w-3 h-0.5 bg-pink-400"
                style={{ borderTop: '2px dashed' }}
              />
              <span className="text-[9px] text-white/40 uppercase">P50 (Median)</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
