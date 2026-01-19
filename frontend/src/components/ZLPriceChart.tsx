'use client'

import React, { useEffect, useRef, useState } from 'react'
import { createChart, AreaSeries, LineSeries, ColorType, IChartApi, UTCTimestamp, LineStyle } from 'lightweight-charts'

interface PriceData {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export function ZLPriceChart({ height = 350 }: { height?: number }) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  
  const [priceData, setPriceData] = useState<PriceData[]>([])
  const [lastPrice, setLastPrice] = useState<number | null>(null)

  // Fetch data
  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(`/api/zl/price-1d?days=90`)
        if (!res.ok) throw new Error('Failed to fetch')
        const json = await res.json()
        if (json.data) {
          setPriceData(json.data)
          // Get last price for the horizontal line
          if (json.data.length > 0) {
            setLastPrice(json.data[json.data.length - 1].close)
          }
        }
      } catch (err) {
        console.error('Fetch error:', err)
      }
    }
    fetchData()
    
    // Refresh every 15 minutes (900000ms) to update current day bar
    const interval = setInterval(fetchData, 900000)
    return () => clearInterval(interval)
  }, [])

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
        horzLines: { color: 'rgba(255, 255, 255, 0.06)' },
      },
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
        fixRightEdge: false,
        timeVisible: true,
        rightOffset: 6, // Reduced padding on right
      },
      rightPriceScale: {
        borderVisible: false,
      },
    })
    
    chartRef.current = chart

    // 2. Add Area Series (Pink #ef4444 with gradient)
    const areaSeries = chart.addSeries(AreaSeries, {
      lineColor: '#ef4444', 
      topColor: 'rgba(239, 68, 68, 0.4)',
      bottomColor: 'rgba(239, 68, 68, 0.0)',
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    })

    // 3. Transform Data
    const dataMap = new Map<number, { time: UTCTimestamp; value: number }>()
    for (const d of priceData) {
      const time = Math.floor(new Date(d.timestamp).getTime() / 1000) as UTCTimestamp
      dataMap.set(time, { time, value: d.close })
    }
    const sortedData = Array.from(dataMap.values()).sort((a, b) => a.time - b.time)
    
    areaSeries.setData(sortedData)

    // 4. Add horizontal price line (dotted behind, solid forward to axis)
    if (sortedData.length > 0 && lastPrice !== null) {
      const lastDataTime = sortedData[sortedData.length - 1].time
      const firstDataTime = sortedData[0].time
      
      // Calculate future time - extend to reach right axis edge
      const timeSpan = lastDataTime - firstDataTime
      const futureTime = (lastDataTime + Math.floor(timeSpan * 1.0)) as UTCTimestamp

      // Dotted line for historical (behind) - thicker dots
      const dottedLine = chart.addSeries(LineSeries, {
        color: 'rgba(255, 255, 255, 0.5)',
        lineWidth: 3,
        lineStyle: LineStyle.Dotted,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
      })
      dottedLine.setData([
        { time: firstDataTime, value: lastPrice },
        { time: lastDataTime, value: lastPrice },
      ])

      // Solid line for future (forward to vertical axis)
      const solidLine = chart.addSeries(LineSeries, {
        color: 'rgba(255, 255, 255, 0.9)',
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
      })
      solidLine.setData([
        { time: lastDataTime, value: lastPrice },
        { time: futureTime, value: lastPrice },
      ])
    }

    // 5. Auto-Adjust to fill view
    chart.timeScale().fitContent()

    // 6. Reactive Resize
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
  }, [priceData, height, lastPrice])

  return (
    <div className="relative w-full border border-white/5 bg-[#0b0f1a] rounded-xl overflow-hidden">
      
      {/* Chart Container */}
      <div ref={chartContainerRef} className="w-full relative" style={{ height }}>
        {/* Watermark */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
          <img src="/chart_watermark.svg" alt="" className="opacity-[0.03] h-1/2" style={{ aspectRatio: 'auto' }} />
        </div>
      </div>
    </div>
  )
}
