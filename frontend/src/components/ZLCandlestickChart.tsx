'use client'

import React, { useEffect, useRef, useState } from 'react'
import { 
  createChart, 
  CandlestickSeries, 
  LineSeries, 
  AreaSeries,
  ColorType, 
  IChartApi, 
  UTCTimestamp, 
  LineStyle,
  CandlestickData
} from 'lightweight-charts'

interface PriceData {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

// Neural Net Blue Color Palette
const COLORS = {
  primary: '#00D4FF',      // Cyan/teal neural net blue
  bullish: '#22C55E',      // Green
  bearish: '#EF4444',      // Red
  neutral: '#6B7280',      // Gray
  bandFill: 'rgba(0, 212, 255, 0.08)',  // Soft neural blue fill
  bandStroke: 'rgba(0, 212, 255, 0.25)', // Band border
  wickColor: '#525252',    // Thin wick color
  background: 'transparent',
}

export function ZLCandlestickChart({ 
  height = 500,
  showBands = true,
}: { 
  height?: number
  showBands?: boolean 
}) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  
  const [priceData, setPriceData] = useState<PriceData[]>([])
  const [lastPrice, setLastPrice] = useState<number | null>(null)

  // Fetch data
  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(`/api/zl/price-1d?days=120`)
        if (!res.ok) throw new Error('Failed to fetch')
        const json = await res.json()
        if (json.data) {
          setPriceData(json.data)
          if (json.data.length > 0) {
            setLastPrice(json.data[json.data.length - 1].close)
          }
        }
      } catch (err) {
        console.error('Fetch error:', err)
      }
    }
    fetchData()
    const interval = setInterval(fetchData, 900000) // 15 min refresh
    return () => clearInterval(interval)
  }, [])

  // Initialize & Update Chart
  useEffect(() => {
    if (!chartContainerRef.current || priceData.length === 0) return

    if (chartRef.current) {
      chartRef.current.remove()
    }

    // Chart Configuration - Clean, Minimal, Hi-Def
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: height,
      layout: {
        background: { type: ColorType.Solid, color: COLORS.background },
        textColor: '#525252',
        attributionLogo: false,
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { 
          color: 'rgba(255, 255, 255, 0.04)',
          style: LineStyle.Solid,
        },
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
      crosshair: {
        vertLine: { 
          color: 'rgba(0, 212, 255, 0.3)',
          width: 1,
          style: LineStyle.Dashed,
          labelVisible: true,
          labelBackgroundColor: '#0a0a0a',
        },
        horzLine: { 
          color: 'rgba(0, 212, 255, 0.3)',
          width: 1,
          style: LineStyle.Dashed,
          labelVisible: true,
          labelBackgroundColor: '#0a0a0a',
        },
      },
      timeScale: {
        visible: true,
        borderVisible: false,
        fixLeftEdge: true,
        fixRightEdge: false,
        timeVisible: true,
        rightOffset: 12,
        barSpacing: 8, // Tighter spacing
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
    })
    
    chartRef.current = chart

    // Transform Data for Candlesticks
    const candleData: CandlestickData[] = priceData.map(d => ({
      time: Math.floor(new Date(d.timestamp).getTime() / 1000) as UTCTimestamp,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    })).sort((a, b) => (a.time as number) - (b.time as number))

    // Calculate P10/P90 bands (simple ATR-based for now)
    // In production, this comes from L3 Monte Carlo
    const atrPeriod = 14
    const bandMultiplier = 1.5
    
    const bandData: { time: UTCTimestamp; p10: number; p90: number; mid: number }[] = []
    
    for (let i = atrPeriod; i < candleData.length; i++) {
      let atrSum = 0
      for (let j = i - atrPeriod; j < i; j++) {
        const tr = Math.max(
          candleData[j].high - candleData[j].low,
          Math.abs(candleData[j].high - candleData[j - 1]?.close || candleData[j].open),
          Math.abs(candleData[j].low - candleData[j - 1]?.close || candleData[j].open)
        )
        atrSum += tr
      }
      const atr = atrSum / atrPeriod
      const mid = candleData[i].close
      bandData.push({
        time: candleData[i].time as UTCTimestamp,
        p10: mid - (atr * bandMultiplier),
        p90: mid + (atr * bandMultiplier),
        mid: mid,
      })
    }

    // Add Probability Bands (P90 upper, P10 lower)
    if (showBands && bandData.length > 0) {
      // Upper band (P90) - thin line
      const upperBand = chart.addSeries(LineSeries, {
        color: COLORS.bandStroke,
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
      })
      upperBand.setData(bandData.map(d => ({ time: d.time, value: d.p90 })))

      // Lower band (P10) - thin line
      const lowerBand = chart.addSeries(LineSeries, {
        color: COLORS.bandStroke,
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
      })
      lowerBand.setData(bandData.map(d => ({ time: d.time, value: d.p10 })))

      // Fill area between bands using area series
      const upperFill = chart.addSeries(AreaSeries, {
        lineColor: 'transparent',
        topColor: COLORS.bandFill,
        bottomColor: 'transparent',
        lineWidth: 1,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
      })
      upperFill.setData(bandData.map(d => ({ time: d.time, value: d.p90 })))
    }

    // Add Candlestick Series - TradingView Style (thin, crisp)
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.bullish,
      downColor: COLORS.bearish,
      borderUpColor: COLORS.bullish,
      borderDownColor: COLORS.bearish,
      wickUpColor: COLORS.bullish,
      wickDownColor: COLORS.bearish,
      // Thinner candles for that hi-def look
      priceLineVisible: true,
      priceLineColor: COLORS.primary,
      priceLineWidth: 1,
      priceLineStyle: LineStyle.Dashed,
    })

    candlestickSeries.setData(candleData)

    // Last price line extending to right
    if (lastPrice !== null && candleData.length > 0) {
      const lastTime = candleData[candleData.length - 1].time
      const firstTime = candleData[0].time
      const timeSpan = (lastTime as number) - (firstTime as number)
      const futureTime = ((lastTime as number) + Math.floor(timeSpan * 0.3)) as UTCTimestamp

      const priceLine = chart.addSeries(LineSeries, {
        color: 'rgba(255, 255, 255, 0.4)',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
      })
      priceLine.setData([
        { time: firstTime, value: lastPrice },
        { time: futureTime, value: lastPrice },
      ])
    }

    // Fit content
    chart.timeScale().fitContent()

    // Resize observer
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0 || !entries[0].target) return
      const newRect = entries[0].contentRect
      chart.applyOptions({ width: newRect.width })
      chart.timeScale().fitContent()
    })
    resizeObserver.observe(chartContainerRef.current)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
    }
  }, [priceData, height, lastPrice, showBands])

  return (
    <div className="relative w-full bg-[#0a0a0a] rounded-xl overflow-hidden border border-white/5">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-slate-500 uppercase tracking-wider">ZL1!</span>
          <span className="text-xs text-slate-600">Soybean Oil Futures • 1D</span>
        </div>
        <div className="flex items-center gap-2">
          {showBands && (
            <span className="px-2 py-0.5 bg-cyan-500/10 border border-cyan-500/20 rounded text-[10px] font-mono text-cyan-400">
              P10/P90 BANDS
            </span>
          )}
        </div>
      </div>

      {/* Chart Container */}
      <div ref={chartContainerRef} className="w-full relative" style={{ height }}>
        {/* Watermark */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
          <div className="text-6xl font-bold text-white/[0.02] tracking-widest">ZL</div>
        </div>
      </div>

      {/* Footer Stats */}
      {lastPrice && (
        <div className="flex items-center justify-between px-4 py-2 border-t border-white/5 bg-white/[0.02]">
          <div className="flex items-center gap-4 text-xs">
            <div>
              <span className="text-slate-500">Last: </span>
              <span className="font-mono text-white">${lastPrice.toFixed(2)}</span>
            </div>
          </div>
          <div className="text-[10px] text-slate-600 font-mono">
            lightweight-charts™
          </div>
        </div>
      )}
    </div>
  )
}
