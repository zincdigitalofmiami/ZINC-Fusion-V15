'use client'

import { createChart, LineSeries, type IChartApi, type ISeriesApi, type LineData } from 'lightweight-charts'
import { useEffect, useRef } from 'react'

export default function ZLPriceChart() {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const el = containerRef.current

    const chart = createChart(el, {
      width: el.clientWidth,
      height: 320,
      layout: {
        background: { color: 'transparent' },
        textColor: 'rgba(209, 212, 220, 0.9)',
      },
      grid: {
        vertLines: { color: 'rgba(255,255,255,0.06)' },
        horzLines: { color: 'rgba(255,255,255,0.06)' },
      },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.10)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.10)' },
      crosshair: {
        vertLine: { color: 'rgba(255,255,255,0.10)' },
        horzLine: { color: 'rgba(255,255,255,0.10)' },
      },
    })

    chartRef.current = chart

    const accent = getComputedStyle(el).getPropertyValue('--accent').trim() || '#2962ff'

    const series = chart.addSeries(LineSeries, {
      color: accent,
      lineWidth: 2,
    })

    seriesRef.current = series

    const data: LineData[] = [
      { time: '2025-12-26', value: 44.2 },
      { time: '2025-12-27', value: 44.8 },
      { time: '2025-12-30', value: 45.1 },
      { time: '2025-12-31', value: 45.9 },
      { time: '2026-01-02', value: 46.3 },
      { time: '2026-01-03', value: 46.9 },
      { time: '2026-01-06', value: 47.8 },
    ]

    series.setData(data)
    chart.timeScale().fitContent()

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth })
    })
    ro.observe(el)

    return () => {
      ro.disconnect()
      chart.remove()
      seriesRef.current = null
      chartRef.current = null
    }
  }, [])

  return <div ref={containerRef} style={{ width: '100%', height: 320 }} />
}
