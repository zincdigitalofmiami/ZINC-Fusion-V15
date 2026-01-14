'use client'

import React, { useEffect, useRef, useState } from 'react'
import { createChart, AreaSeries, ColorType, IChartApi, UTCTimestamp } from 'lightweight-charts'

interface PriceData {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

// Simplified ranges as requested: 1M, 3M, 6M
const TIME_RANGES = [
  { id: '1M', label: '1 Month', interval: '1h', range: '1mo' },
  { id: '3M', label: '3 Month', interval: '1d', range: '3mo' },
  { id: '6M', label: '6 Month', interval: '1d', range: '6mo' },
]

export function ZLPriceChart({ height = 350 }: { height?: number }) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  
  // Default to 1 Month view to match short-term focus usually, or 3M as requested
  const [selectedRange, setSelectedRange] = useState(TIME_RANGES[1])
  const [priceData, setPriceData] = useState<PriceData[]>([])

  // Fetch data
  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(`/api/zl/yahoo?interval=${selectedRange.interval}&range=${selectedRange.range}`)
        if (!res.ok) throw new Error('Failed to fetch')
        const json = await res.json()
        if (json.data) {
          setPriceData(json.data)
        }
      } catch (err) {
        console.error('Fetch error:', err)
      }
    }
    fetchData()
  }, [selectedRange])

  // Initialize & Update Chart
  useEffect(() => {
    if (!chartContainerRef.current || priceData.length === 0) return

    // Clean up previous chart
    if (chartRef.current) {
      chartRef.current.remove()
    }

    // 1. Configure Chart (No interactions, clean style)
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#525252',
        attributionLogo: false,
      },
      grid: {
        vertLines: { visible: false },
        // Very light grid (barely visible)
        horzLines: { color: 'rgba(255, 255, 255, 0.06)' },
      },
      // Disable ALL mouse control
      handleScroll: false,
      handleScale: false,
      crosshair: {
        vertLine: { visible: false, labelVisible: false },
        horzLine: { visible: false, labelVisible: false },
      },
      timeScale: {
        visible: true,
        borderVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
        timeVisible: true,
      },
      rightPriceScale: {
        borderVisible: false,
      },
    })
    
    chartRef.current = chart

    // 2. Add Area Series (Pink #ef4444 with gradient)
    const areaSeries = chart.addSeries(AreaSeries, {
      lineColor: '#ef4444', 
      topColor: 'rgba(239, 68, 68, 0.4)',  // Pink 40% opacity
      bottomColor: 'rgba(239, 68, 68, 0.0)', // Fade to transparent
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    })

    // 3. Transform Data
    const dataMap = new Map<number, { time: UTCTimestamp; value: number }>()
    for (const d of priceData) {
      const time = Math.floor(new Date(d.timestamp).getTime() / 1000) as UTCTimestamp
      // AreaSeries uses 'value'
      dataMap.set(time, { time, value: d.close })
    }
    const sortedData = Array.from(dataMap.values()).sort((a, b) => a.time - b.time)
    
    areaSeries.setData(sortedData)

    // 4. Auto-Adjust to fill view
    chart.timeScale().fitContent()

    // 5. Reactive Resize
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
  }, [priceData, height])

  return (
    <div className="relative w-full border border-white/5 bg-[#0b0f1a] rounded-xl overflow-hidden">
      
      {/* Header / Controls */}
      <div className="absolute top-4 right-4 z-10 flex gap-2">
        {TIME_RANGES.map((range) => (
          <button
            key={range.id}
            onClick={() => setSelectedRange(range)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
              selectedRange.id === range.id
                ? 'bg-[#ef4444] text-white shadow-lg' // Active Pink
                : 'bg-white/5 text-slate-400 hover:text-white hover:bg-white/10'
            }`}
          >
            {range.label}
          </button>
        ))}
      </div>

      {/* Chart Container */}
      <div ref={chartContainerRef} className="w-full" style={{ height }} />
    </div>
  )
}
