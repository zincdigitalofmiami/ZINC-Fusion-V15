'use client'

import React, { useEffect, useRef, useState } from 'react'
import {
    createChart,
    LineSeries,
    AreaSeries,
    ColorType,
    IChartApi,
    UTCTimestamp,
    LineStyle,
} from 'lightweight-charts'

interface PriceData {
    timestamp: string
    open: number
    high: number
    low: number
    close: number
    volume: number
}

// Color Palette - Clean Neural Net Style
const COLORS = {
    priceLine: '#00D4FF',      // Cyan/teal for actual price
    forecast: '#84CC16',        // Lime green for forecast (dotted)
    bandFill: 'rgba(0, 212, 255, 0.06)',    // Very subtle cyan fill
    bandStroke: 'rgba(0, 212, 255, 0.15)',  // Subtle band border
    gridLine: 'rgba(255, 255, 255, 0.03)',  // Nearly invisible grid
    textColor: '#525252',       // Muted text
    crosshair: 'rgba(0, 212, 255, 0.3)',    // Cyan crosshair
    background: 'transparent',
}

export function ZLCandlestickChart({
    height = '70vh',
    showBands = true,
}: {
    height?: string | number
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
                          const res = await fetch('/api/zl/price-1d?days=120')
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

                // Get container dimensions
                const containerWidth = chartContainerRef.current.clientWidth
        const containerHeight = chartContainerRef.current.clientHeight

                // Chart Configuration - Clean, Minimal, Hi-Def
                const chart = createChart(chartContainerRef.current, {
                        width: containerWidth,
                        height: containerHeight,
                        layout: {
                                  background: { type: ColorType.Solid, color: COLORS.background },
                                  textColor: COLORS.textColor,
                                  attributionLogo: false,
                                  fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                        },
                        grid: {
                                  vertLines: { visible: false },
                                  horzLines: {
                                              color: COLORS.gridLine,
                                              style: LineStyle.Solid,
                                  },
                        },
                        handleScroll: { mouseWheel: true, pressedMouseMove: true },
                        handleScale: { mouseWheel: true, pinch: true },
                        crosshair: {
                                  vertLine: {
                                              color: COLORS.crosshair,
                                              width: 1,
                                              style: LineStyle.Dashed,
                                              labelVisible: true,
                                              labelBackgroundColor: '#0a0a0a',
                                  },
                                  horzLine: {
                                              color: COLORS.crosshair,
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
                                  barSpacing: 12,
                                  minBarSpacing: 4,
                        },
                        rightPriceScale: {
                                  borderVisible: false,
                                  scaleMargins: { top: 0.1, bottom: 0.1 },
                                  autoScale: true,
                        },
                })

                chartRef.current = chart

                // Transform data for line chart
                const lineData = priceData.map(d => ({
                        time: Math.floor(new Date(d.timestamp).getTime() / 1000) as UTCTimestamp,
                        value: d.close,
                })).sort((a, b) => (a.time as number) - (b.time as number))

                // Calculate P30/P70 bands (ATR-based)
                const atrPeriod = 14
        const bandMultiplier = 1.2

                const bandData: { time: UTCTimestamp; p30: number; p70: number; mid: number }[] = []

                      for (let i = atrPeriod; i < priceData.length; i++) {
                              let atrSum = 0
                              for (let j = i - atrPeriod; j < i; j++) {
                                        const tr = Math.max(
                                                    priceData[j].high - priceData[j].low,
                                                    Math.abs(priceData[j].high - priceData[j - 1]?.close || priceData[j].open),
                                                    Math.abs(priceData[j].low - priceData[j - 1]?.close || priceData[j].open)
                                                  )
                                        atrSum += tr
                              }
                              const atr = atrSum / atrPeriod
                              const time = Math.floor(new Date(priceData[i].timestamp).getTime() / 1000) as UTCTimestamp
                              bandData.push({
                                        time,
                                        p30: priceData[i].close - atr * bandMultiplier,
                                        p70: priceData[i].close + atr * bandMultiplier,
                                        mid: priceData[i].close,
                              })
                      }

                bandData.sort((a, b) => (a.time as number) - (b.time as number))

                // Add P30/P70 bands if enabled
                if (showBands && bandData.length > 0) {
                        // Upper band (P70) - thin line
          const upperBand = chart.addSeries(LineSeries, {
                    color: COLORS.bandStroke,
                    lineWidth: 1,
                    lineStyle: LineStyle.Dotted,
                    priceLineVisible: false,
                    crosshairMarkerVisible: false,
                    lastValueVisible: false,
          })
                        upperBand.setData(bandData.map(d => ({ time: d.time, value: d.p70 })))

          // Lower band (P30) - thin line
          const lowerBand = chart.addSeries(LineSeries, {
                    color: COLORS.bandStroke,
                    lineWidth: 1,
                    lineStyle: LineStyle.Dotted,
                    priceLineVisible: false,
                    crosshairMarkerVisible: false,
                    lastValueVisible: false,
          })
                        lowerBand.setData(bandData.map(d => ({ time: d.time, value: d.p30 })))

          // Fill area between bands
          const upperFill = chart.addSeries(AreaSeries, {
                    lineColor: 'transparent',
                    topColor: COLORS.bandFill,
                    bottomColor: 'transparent',
                    lineWidth: 1,
                    priceLineVisible: false,
                    crosshairMarkerVisible: false,
                    lastValueVisible: false,
          })
                        upperFill.setData(bandData.map(d => ({ time: d.time, value: d.p70 })))
                }

                // Main price line - SOLID CYAN
                const priceLine = chart.addSeries(LineSeries, {
                        color: COLORS.priceLine,
                        lineWidth: 2,
                        priceLineVisible: true,
                        priceLineColor: COLORS.priceLine,
                        priceLineWidth: 1,
                        priceLineStyle: LineStyle.Dashed,
                        crosshairMarkerVisible: true,
                        crosshairMarkerRadius: 4,
                        crosshairMarkerBackgroundColor: COLORS.priceLine,
                        crosshairMarkerBorderColor: '#ffffff',
                        crosshairMarkerBorderWidth: 1,
                        lastValueVisible: true,
                })
        priceLine.setData(lineData)

                // Forecast line - LIME GREEN DOTTED (extending into future)
                if (lastPrice !== null && lineData.length > 0) {
                        const lastTime = lineData[lineData.length - 1].time
                        const firstTime = lineData[0].time
                        const timeSpan = (lastTime as number) - (firstTime as number)
                        const futureTime = ((lastTime as number) + Math.floor(timeSpan * 0.3)) as UTCTimestamp

          // Simple forecast: slight upward trend for visual
          const forecastEndPrice = lastPrice * 1.02 // 2% up as placeholder

          const forecastLine = chart.addSeries(LineSeries, {
                    color: COLORS.forecast,
                    lineWidth: 2,
                    lineStyle: LineStyle.Dotted,
                    priceLineVisible: false,
                    crosshairMarkerVisible: false,
                    lastValueVisible: false,
          })
                        forecastLine.setData([
                          { time: lastTime, value: lastPrice },
                          { time: futureTime, value: forecastEndPrice },
                                ])
                }

                // Fit content
                chart.timeScale().fitContent()

                // Resize observer
                const resizeObserver = new ResizeObserver((entries) => {
                        if (entries.length === 0 || !entries[0].target) return
                        const newRect = entries[0].contentRect
                        chart.applyOptions({ width: newRect.width, height: newRect.height })
                        chart.timeScale().fitContent()
                })
        resizeObserver.observe(chartContainerRef.current)

                return () => {
                        resizeObserver.disconnect()
                        chart.remove()
                }
  }, [priceData, lastPrice, showBands])

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
                                    P30/P70 BANDS
                      </span>
                                )}
                      </div>
              </div>
        
          {/* Chart Container - MASSIVE */}
              <div 
                        ref={chartContainerRef} 
                className="w-full relative"
                        style={{ height: typeof height === 'number' ? `${height}px` : height }}
                      >
                {/* Watermark */}
                      <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
                                <div className="text-6xl font-bold text-white/[0.02] tracking-widest">ZL</div>
                      </div>
              </div>
        
          {/* Legend */}
              <div className="flex items-center justify-center gap-6 py-3 border-t border-white/5">
                      <div className="flex items-center gap-2">
                                <div className="w-4 h-0.5 bg-[#84CC16]" style={{ borderStyle: 'dashed' }}></div>
                                <span className="text-[10px] text-slate-500">P50 Forecast</span>
                      </div>
                      <div className="flex items-center gap-2">
                                <div className="w-4 h-0.5 bg-[#00D4FF]"></div>
                                <span className="text-[10px] text-slate-500">ZL Price</span>
                      </div>
              </div>
        </div>
      )
}
