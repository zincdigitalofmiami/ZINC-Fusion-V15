'use client'

import React, { useEffect, useRef, useState } from 'react'
import { createChart, CandlestickSeries } from 'lightweight-charts'

interface PriceData {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

// Yahoo Finance API intervals and ranges
const TIME_RANGES = [
  { id: '1D', label: '1D', interval: '5m', range: '1d' },
  { id: '1W', label: '1W', interval: '15m', range: '5d' },
  { id: '1M', label: '1M', interval: '1h', range: '1mo' },
  { id: '3M', label: '3M', interval: '1d', range: '3mo' },
  { id: '6M', label: '6M', interval: '1d', range: '6mo' },
  { id: '1Y', label: '1Y', interval: '1wk', range: '1y' },
]

export function ZLPriceChart({ height = 600 }: { height?: number }) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const [selectedRange, setSelectedRange] = useState(TIME_RANGES[2])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [priceData, setPriceData] = useState<PriceData[]>([])
  const [livePrice, setLivePrice] = useState<number | null>(null)

  const latestPrice = livePrice || (priceData.length > 0 ? priceData[priceData.length - 1].close : null)
  const firstPrice = priceData.length > 0 ? priceData[0].close : null
  const pctChange = firstPrice ? ((latestPrice! - firstPrice) / firstPrice) * 100 : 0
  const isPositive = pctChange >= 0

  // Fetch data
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(`/api/zl/yahoo?interval=${selectedRange.interval}&range=${selectedRange.range}`)
        if (!res.ok) throw new Error('Failed to fetch')
        const json = await res.json()
        if (json.error) throw new Error(json.error)
        setPriceData(json.data || [])
        setLivePrice(json.regularMarketPrice)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error')
        setPriceData([])
      } finally {
        setLoading(false)
      }
    }
    fetchData()
    const interval = setInterval(fetchData, 60000)
    return () => clearInterval(interval)
  }, [selectedRange])

  // Create chart
  useEffect(() => {
    if (!chartContainerRef.current || priceData.length === 0) return

    const containerWidth = chartContainerRef.current.clientWidth

    // Dedupe and sort data
    const dataMap = new Map<number, { time: number; open: number; high: number; low: number; close: number }>()
    for (const d of priceData) {
      const time = Math.floor(new Date(d.timestamp).getTime() / 1000)
      dataMap.set(time, { time, open: d.open, high: d.high, low: d.low, close: d.close })
    }
    const sortedData = Array.from(dataMap.values()).sort((a, b) => a.time - b.time)
    const barCount = sortedData.length

    // Calculate bar spacing to fill width consistently (like TradingView)
    // Target: bars should use ~80% of width, leave some padding
    const targetBarWidth = (containerWidth * 0.85) / barCount
    const barSpacing = Math.max(2, Math.min(12, targetBarWidth))

    const chart = createChart(chartContainerRef.current, {
      width: containerWidth,
      height: height,
      layout: {
        background: { type: 'solid' as const, color: '#131722' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: '#1e222d' },
        horzLines: { color: '#1e222d' },
      },
      timeScale: {
        barSpacing: barSpacing,
        rightOffset: 5,
      },
    })

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })

    candlestickSeries.setData(sortedData as any)
    chart.timeScale().fitContent()

    // Resize handler
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [priceData, height])

  if (error) {
    return <div className="flex items-center justify-center text-red-400" style={{ height }}>{error}</div>
  }

  return (
    <div className="relative bg-[#131722]">
      {/* Range buttons */}
      <div className="absolute top-2 left-2 z-10 flex gap-1">
        {TIME_RANGES.map(range => (
          <button
            key={range.id}
            onClick={() => setSelectedRange(range)}
            className={`px-2 py-1 text-xs rounded ${
              selectedRange.id === range.id
                ? 'bg-blue-600 text-white'
                : 'bg-[#2a2e39] text-gray-300 hover:bg-[#363a45]'
            }`}
          >
            {range.label}
          </button>
        ))}
        {loading && <span className="text-xs text-gray-500 ml-2">Loading...</span>}
      </div>

      {/* Price display */}
      <div className="absolute top-2 right-2 z-10 text-right">
        <div className="text-xl font-bold text-white">${latestPrice?.toFixed(2)}</div>
        <div className={`text-sm ${isPositive ? 'text-[#26a69a]' : 'text-[#ef5350]'}`}>
          {isPositive ? '+' : ''}{pctChange.toFixed(2)}%
        </div>
      </div>

      {/* Chart */}
      <div ref={chartContainerRef} />
    </div>
  )
}
