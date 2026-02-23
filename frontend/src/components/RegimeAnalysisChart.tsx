'use client'

import React, { useEffect, useRef, useState } from 'react'
import {
  createChart,
  LineSeries,
  ColorType,
  IChartApi,
  UTCTimestamp,
  LineStyle,
  HistogramSeries,
} from 'lightweight-charts'

// Market Regime Types
type MarketRegime = 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'SUPPLY_CRISIS' | 'DEMAND_SHOCK'

interface RegimeZone {
  start: UTCTimestamp
  end: UTCTimestamp
  regime: MarketRegime
}

// Regime Colors - Semi-transparent zones
const REGIME_COLORS: Record<MarketRegime, { bg: string; border: string }> = {
  BULLISH: { bg: 'rgba(34, 197, 94, 0.15)', border: '#22C55E' },
  BEARISH: { bg: 'rgba(239, 68, 68, 0.15)', border: '#EF4444' },
  NEUTRAL: { bg: 'rgba(107, 114, 128, 0.1)', border: '#6B7280' },
  SUPPLY_CRISIS: { bg: 'rgba(239, 68, 68, 0.25)', border: '#DC2626' },
  DEMAND_SHOCK: { bg: 'rgba(34, 197, 94, 0.25)', border: '#16A34A' },
}

interface PriceData {
  timestamp: string
  close: number
}

export function RegimeAnalysisChart({
  height = 400,
  timeRange = '3M',
}: {
  height?: number
  timeRange?: '1M' | '3M' | '6M' | '1Y'
}) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const [selectedRange, setSelectedRange] = useState(timeRange)
  const [priceData, setPriceData] = useState<PriceData[]>([])
  const [currentRegime, setCurrentRegime] = useState<MarketRegime>('NEUTRAL')

  const days = { '1M': 30, '3M': 90, '6M': 180, '1Y': 365 }[selectedRange]

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(`/api/zl/price-1d?days=${days}`)
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
  }, [days])

  useEffect(() => {
    if (!chartContainerRef.current || priceData.length === 0) return

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
        horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
      },
      handleScroll: false,
      handleScale: false,
      crosshair: {
        vertLine: {
          color: 'rgba(0, 212, 255, 0.2)',
          width: 1,
          style: LineStyle.Dashed,
          labelVisible: true,
        },
        horzLine: { visible: false, labelVisible: false },
      },
      timeScale: {
        visible: true,
        borderVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      rightPriceScale: {
        borderVisible: false,
        visible: false,
      },
      leftPriceScale: {
        visible: true,
        borderVisible: false,
      },
    })

    chartRef.current = chart

    // Transform price data
    const lineData = priceData.map(d => ({
      time: Math.floor(new Date(d.timestamp).getTime() / 1000) as UTCTimestamp,
      value: parseFloat(String(d.close)),
    })).sort((a, b) => (a.time as number) - (b.time as number))

    // SMA-based regime estimate — L1 meta-learner pending
    const regimeZones: RegimeZone[] = []
    let currentZoneStart = lineData[0]?.time
    let prevRegime: MarketRegime = 'NEUTRAL'

    const sma20: number[] = []
    const sma50: number[] = []

    for (let i = 0; i < lineData.length; i++) {
      // Calculate SMAs
      if (i >= 19) {
        const sum20 = lineData.slice(i - 19, i + 1).reduce((s, d) => s + d.value, 0)
        sma20.push(sum20 / 20)
      }
      if (i >= 49) {
        const sum50 = lineData.slice(i - 49, i + 1).reduce((s, d) => s + d.value, 0)
        sma50.push(sum50 / 50)
      }
    }

    // Determine regime zones
    for (let i = 50; i < lineData.length; i++) {
      const sma20Idx = i - 20
      const sma50Idx = i - 50

      if (sma20Idx >= 0 && sma50Idx >= 0 && sma20[sma20Idx] && sma50[sma50Idx]) {
        const price = lineData[i].value
        const s20 = sma20[sma20Idx]
        const s50 = sma50[sma50Idx]

        let regime: MarketRegime = 'NEUTRAL'

        if (s20 > s50 * 1.02 && price > s20) {
          regime = 'BULLISH'
        } else if (s20 < s50 * 0.98 && price < s20) {
          regime = 'BEARISH'
        } else if (price < s50 * 0.95) {
          regime = 'SUPPLY_CRISIS'
        } else if (price > s50 * 1.08) {
          regime = 'DEMAND_SHOCK'
        }

        if (regime !== prevRegime) {
          if (currentZoneStart) {
            regimeZones.push({
              start: currentZoneStart,
              end: lineData[i].time,
              regime: prevRegime,
            })
          }
          currentZoneStart = lineData[i].time
          prevRegime = regime
        }
      }
    }

    // Add final zone
    if (currentZoneStart && lineData.length > 0) {
      regimeZones.push({
        start: currentZoneStart,
        end: lineData[lineData.length - 1].time,
        regime: prevRegime,
      })
      setCurrentRegime(prevRegime)
    }

    // Draw regime background zones using histogram series
    // Create data points for each regime zone
    for (const zone of regimeZones) {
      const zoneData = lineData
        .filter(d => d.time >= zone.start && d.time <= zone.end)
        .map(d => ({
          time: d.time,
          value: 1,
          color: REGIME_COLORS[zone.regime].bg,
        }))

      if (zoneData.length > 0) {
        const zoneSeries = chart.addSeries(HistogramSeries, {
          priceLineVisible: false,
          lastValueVisible: false,
          priceScaleId: 'regime',
          color: REGIME_COLORS[zone.regime].bg,
        })

        // Scale histogram to fill chart height
        const maxPrice = Math.max(...lineData.map(d => d.value))
        const minPrice = Math.min(...lineData.map(d => d.value))
        const range = maxPrice - minPrice

        zoneSeries.setData(zoneData.map(d => ({
          time: d.time,
          value: maxPrice + range * 0.1, // Fill to top
          color: REGIME_COLORS[zone.regime].bg,
        })))
      }
    }

    // Add price line on top
    const priceLine = chart.addSeries(LineSeries, {
      color: '#ffffff',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      priceScaleId: 'left',
    })
    priceLine.setData(lineData)

    chart.timeScale().fitContent()

    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0) return
      const newRect = entries[0].contentRect
      chart.applyOptions({ width: newRect.width })
    })
    resizeObserver.observe(chartContainerRef.current)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [priceData, height])

  return (
    <div className="bg-[#0a0a0a] border border-white/5 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-bold text-white">ZL Futures - Regime Analysis</h3>
          <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-amber-500/20 text-amber-400 border border-amber-500/30">
            Beta
          </span>
          <span
            className="px-2 py-0.5 rounded text-[10px] font-bold uppercase"
            style={{
              backgroundColor: REGIME_COLORS[currentRegime].bg,
              color: REGIME_COLORS[currentRegime].border,
              border: `1px solid ${REGIME_COLORS[currentRegime].border}30`,
            }}
          >
            {currentRegime.replace('_', ' ')}
          </span>
        </div>

        {/* Time Range Toggle */}
        <div className="flex items-center bg-white/5 rounded-lg p-0.5">
          {(['1M', '3M', '6M', '1Y'] as const).map((range) => (
            <button
              key={range}
              onClick={() => setSelectedRange(range)}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${
                selectedRange === range
                  ? 'bg-white/10 text-white'
                  : 'text-slate-500 hover:text-white'
              }`}
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div ref={chartContainerRef} style={{ height }} />

      {/* Legend */}
      <div className="flex items-center justify-center gap-6 py-2 border-t border-white/5 bg-white/[0.02]">
        {Object.entries(REGIME_COLORS).slice(0, 4).map(([regime, colors]) => (
          <div key={regime} className="flex items-center gap-1.5">
            <div
              className="w-3 h-3 rounded-sm"
              style={{ backgroundColor: colors.bg, border: `1px solid ${colors.border}40` }}
            />
            <span className="text-[10px] text-slate-500 uppercase">
              {regime.replace('_', ' ')}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
