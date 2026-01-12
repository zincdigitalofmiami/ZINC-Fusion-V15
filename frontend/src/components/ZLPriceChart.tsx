'use client'

import React, { useEffect, useRef, useState } from 'react'
import { createChart, ColorType, CrosshairMode, IChartApi, ISeriesApi, Time, CandlestickSeries } from 'lightweight-charts'

interface PriceData {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface ZLPriceChartProps {
  height?: number
}

// Yahoo Finance API intervals and ranges - LIVE DATA
const TIME_RANGES = [
  { id: '1M', label: '1M', interval: '15m', range: '1mo' },
  { id: '3M', label: '3M', interval: '1d', range: '3mo' },
  { id: '6M', label: '6M', interval: '1d', range: '6mo' },
  { id: '12M', label: '12M', interval: '1d', range: '1y' },
]

export function ZLPriceChart({ height = 700 }: ZLPriceChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null)

  const [selectedRange, setSelectedRange] = useState(TIME_RANGES[0])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [priceData, setPriceData] = useState<PriceData[]>([])
  const [livePrice, setLivePrice] = useState<number | null>(null)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)

  // Calculate current stats
  const latestPrice = livePrice || (priceData.length > 0 ? priceData[priceData.length - 1].close : null)
  const firstPrice = priceData.length > 0 ? priceData[0].close : null
  const priceChange = latestPrice && firstPrice ? latestPrice - firstPrice : 0
  const pctChange = firstPrice ? (priceChange / firstPrice) * 100 : 0
  const isPositive = pctChange >= 0

  // 1. Fetch LIVE Data from Yahoo Finance API
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      setError(null)
      try {
        // Hit Yahoo Finance DIRECTLY via our proxy endpoint
        const endpoint = `/api/zl/yahoo?interval=${selectedRange.interval}&range=${selectedRange.range}`
        
        const res = await fetch(endpoint)
        if (!res.ok) throw new Error('Failed to fetch live ZL data')
        const json = await res.json()
        
        if (json.error) throw new Error(json.error)
        
        const parsed = (json.data || []).map((d: any) => ({
          timestamp: d.timestamp,
          open: parseFloat(String(d.open)),
          high: parseFloat(String(d.high)),
          low: parseFloat(String(d.low)),
          close: parseFloat(String(d.close)),
          volume: parseFloat(String(d.volume || 0)),
        }))
        
        // Already sorted from Yahoo
        setPriceData(parsed)
        setLivePrice(json.regularMarketPrice)
        setLastUpdate(json.lastUpdate)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
        setPriceData([])
      } finally {
        setLoading(false)
      }
    }
    fetchData()
    
    // Refresh every 60 seconds for live data
    const interval = setInterval(fetchData, 60000)
    return () => clearInterval(interval)
  }, [selectedRange])

  // 2. Initialize & Update Chart
  useEffect(() => {
    if (!chartContainerRef.current) return

    // Create Chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: 'rgba(255, 255, 255, 0.7)',
        fontFamily: 'Inter, system-ui, sans-serif',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
      },
      width: chartContainerRef.current.clientWidth,
      height: height,
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 12, // Space between last bar and right edge
        barSpacing: 8, // Even spacing between bars
        minBarSpacing: 4,
        fixLeftEdge: true,
        fixRightEdge: false,
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
        scaleMargins: {
            top: 0.1,
            bottom: 0.1,
        },
      },
      // SCROLL PROTECTION: Disable wheel zoom and scroll by default
      // This prevents the chart from hijacking the page scroll
      handleScale: {
        mouseWheel: false,
      },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
    })

    // 3D dimensional effect: main body with border for depth
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#ffffff',
      downColor: '#2962FF',
      borderVisible: true,
      borderUpColor: 'rgba(255, 255, 255, 0.3)', // Subtle highlight edge
      borderDownColor: 'rgba(20, 70, 180, 0.8)', // Darker edge for depth
      wickUpColor: 'rgba(255, 255, 255, 0.7)',
      wickDownColor: 'rgba(41, 98, 255, 0.7)',
    })

    chartRef.current = chart
    seriesRef.current = candlestickSeries

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    // Interaction Logic: Ctrl to Zoom
    const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Control' || e.metaKey) {
            chart.applyOptions({ handleScale: { mouseWheel: true } })
        }
    }
    const handleKeyUp = (e: KeyboardEvent) => {
        if (e.key === 'Control' || e.metaKey) {
            chart.applyOptions({ handleScale: { mouseWheel: false } })
        }
    }
    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('keyup', handleKeyUp)

    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('keyup', handleKeyUp)
      chart.remove()
    }
  }, [height])

  // 3. Update Data Effect
  useEffect(() => {
    if (!seriesRef.current || priceData.length === 0) return

    const data = priceData.map(d => {
        const ts = new Date(d.timestamp).getTime() / 1000
        return {
            time: ts as Time,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
        }
    })

    seriesRef.current.setData(data)
    
    if (chartRef.current && data.length > 0) {
        // Show ~180 bars (6M density) with consistent spacing across all horizons
        // User can scroll left to see more history
        const VISIBLE_BARS = 180
        const barsToShow = Math.min(data.length, VISIBLE_BARS)
        const from = data.length - barsToShow - 0.5
        const to = data.length + 10 // padding on right
        chartRef.current.timeScale().setVisibleLogicalRange({ from, to })
    }
  }, [priceData])


  if (error) {
    return (
      <div className="flex items-center justify-center text-slate-400" style={{ height }}>
        {error}
      </div>
    )
  }

  return (
    <div className="relative group">
      {/* Time Range Selector */}
      <div className="absolute top-4 left-6 z-10 flex gap-1 items-center">
        {TIME_RANGES.map(range => (
          <button
            key={range.id}
            onClick={() => setSelectedRange(range)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all backdrop-blur-sm ${
              selectedRange.id === range.id
                ? 'bg-white text-black'
                : 'bg-white/5 text-slate-400 hover:bg-white/10 hover:text-white'
            }`}
          >
            {range.label}
          </button>
        ))}
        {loading && <span className="text-xs text-slate-500 flex items-center ml-2">Loading...</span>}
        <span className="ml-3 px-2 py-0.5 text-[10px] font-mono bg-emerald-500/20 text-emerald-400 rounded">
          LIVE
        </span>
      </div>

      {/* Price Stats */}
      <div className="absolute top-4 right-6 z-10 text-right pointer-events-none">
        <div className="text-2xl font-bold text-white font-mono tracking-tight">
          ${latestPrice?.toFixed(2)}
        </div>
        <div className={`text-sm font-mono ${isPositive ? 'text-emerald-400' : 'text-[#2962FF]'}`}>
          {isPositive ? '▲' : '▼'} {Math.abs(pctChange).toFixed(2)}% ({selectedRange.label})
        </div>
        {lastUpdate && (
          <div className="text-[10px] text-white/40 font-mono mt-1">
            {new Date(lastUpdate).toLocaleTimeString()}
          </div>
        )}
      </div>

      {/* Chart Container */}
      <div ref={chartContainerRef} className="w-full" style={{ height }} />
      
      {/* Scroll Tip */}
      <div className="absolute bottom-2 right-2 text-[10px] text-white/20 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity font-mono">
        Hold Ctrl to Zoom
      </div>
    </div>
  )
}
