'use client'

import dynamic from 'next/dynamic'
import { useState, useEffect, useMemo } from 'react'
import type Plotly from 'plotly.js'

// Dynamic import to avoid SSR issues with Plotly
const Plot = dynamic(() => import('react-plotly.js'), { 
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[700px] text-slate-500 animate-pulse">
      Loading ZL Price Data...
    </div>
  )
})

// TradingView-style: 1M uses hourly, longer uses daily
const TIME_RANGES = [
  { id: '1M', label: '1M', interval: '1h', param: 720 },      // 30 days of hourly
  { id: '3M', label: '3M', interval: '1d', param: 90 },       // 90 daily bars
  { id: '6M', label: '6M', interval: '1d', param: 180 },      // 180 daily bars
  { id: '12M', label: '12M', interval: '1d', param: 365 },    // 365 daily bars
]

interface PriceBar {
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

export default function ZLPriceChart({ height = 700 }: ZLPriceChartProps) {
  const [selectedRange, setSelectedRange] = useState(TIME_RANGES[1]) // Default 3M
  const [isMobile, setIsMobile] = useState(false)
  const [priceData, setPriceData] = useState<PriceBar[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // Fetch ZL price data - hourly for 1M, daily for 3M/6M/12M
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      setError(null)
      try {
        // Choose endpoint based on interval
        const endpoint = selectedRange.interval === '1h' 
          ? `/api/zl/price-1h?hours=${selectedRange.param}`
          : `/api/zl/price-1d?days=${selectedRange.param}`
        
        const res = await fetch(endpoint)
        if (!res.ok) throw new Error('Failed to fetch ZL data')
        const json = await res.json()
        // Parse numeric fields (PostgreSQL returns them as strings)
        const parsed = (json.data || []).map((d: Record<string, unknown>) => ({
          timestamp: d.timestamp,
          open: parseFloat(String(d.open)),
          high: parseFloat(String(d.high)),
          low: parseFloat(String(d.low)),
          close: parseFloat(String(d.close)),
          volume: parseFloat(String(d.volume || 0)),
        }))
        setPriceData(parsed)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
        setPriceData([])
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [selectedRange])

  // Format dates for display (TradingView style - no gaps)
  // Use bar index for x-axis, format date for hover/labels
  const chartData = useMemo(() => {
    if (priceData.length === 0) return null

    // For hourly data (1M), limit to ~400 bars. Daily data already fits.
    const maxCandles = selectedRange.interval === '1h' ? 400 : priceData.length
    const displayData = priceData.length > maxCandles 
      ? priceData.slice(-maxCandles) 
      : priceData

    // Format timestamp for display
    const formatDate = (ts: string) => {
      const d = new Date(ts)
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    }

    // Use sequential indices for x-axis (eliminates gaps like TradingView)
    const indices = displayData.map((_, i) => i)
    const opens = displayData.map(d => d.open)
    const highs = displayData.map(d => d.high)
    const lows = displayData.map(d => d.low)
    const closes = displayData.map(d => d.close)
    
    // Create tick labels - show ~6 evenly spaced dates
    const tickInterval = Math.floor(displayData.length / 6) || 1
    const tickvals: number[] = []
    const ticktext: string[] = []
    for (let i = 0; i < displayData.length; i += tickInterval) {
      tickvals.push(i)
      ticktext.push(formatDate(displayData[i].timestamp))
    }

    // Determine candle colors: white UP, blue DOWN
    const colors = displayData.map(d => d.close >= d.open ? '#ffffff' : '#2962FF')
    const lineColors = displayData.map(d => d.close >= d.open ? '#ffffff' : '#2962FF')

    return {
      indices,
      opens,
      highs,
      lows,
      closes,
      colors,
      lineColors,
      tickvals,
      ticktext,
      timestamps: displayData.map(d => d.timestamp),
      totalBars: displayData.length,
    }
  }, [priceData, selectedRange])

  // Calculate stats
  const latestPrice = priceData.length > 0 ? priceData[priceData.length - 1].close : null
  const firstPrice = priceData.length > 0 ? priceData[0].close : null
  const priceChange = latestPrice && firstPrice ? latestPrice - firstPrice : 0
  const pctChange = firstPrice ? (priceChange / firstPrice) * 100 : 0

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[700px] text-slate-500 animate-pulse">
        Loading ZL Price Data...
      </div>
    )
  }

  if (error || !chartData) {
    return (
      <div className="flex items-center justify-center h-[700px] text-slate-400">
        {error || 'No price data available'}
      </div>
    )
  }

  return (
    <div className="relative group">
      {/* Time Range Selector */}
      <div className="absolute top-4 left-6 z-10 flex gap-1">
        {TIME_RANGES.map(range => (
          <button
            key={range.id}
            onClick={() => setSelectedRange(range)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
              selectedRange.id === range.id
                ? 'bg-white text-black'
                : 'bg-white/5 text-slate-400 hover:bg-white/10 hover:text-white'
            }`}
          >
            {range.label}
          </button>
        ))}
      </div>

      {/* Price Stats */}
      <div className="absolute top-4 right-6 z-10 text-right">
        <div className="text-2xl font-bold text-white font-mono tracking-tight">
          ${latestPrice?.toFixed(2)}
        </div>
        <div className={`text-sm font-mono ${pctChange >= 0 ? 'text-emerald-400' : 'text-[#2962FF]'}`}>
          {pctChange >= 0 ? '▲' : '▼'} {Math.abs(pctChange).toFixed(2)}% ({selectedRange.label})
        </div>
      </div>

      <Plot
        data={[
          // Modern Candlestick trace
          {
            type: 'candlestick',
            x: chartData.indices,
            open: chartData.opens,
            high: chartData.highs,
            low: chartData.lows,
            close: chartData.closes,
            increasing: {
              line: { color: '#ffffff', width: 1 },
              fillcolor: '#ffffff',
            },
            decreasing: {
              line: { color: '#2962FF', width: 1 },
              fillcolor: '#2962FF',
            },
            whiskerwidth: 0.1,
            hoverinfo: 'text',
            text: chartData.timestamps.map((ts, i) => {
              const d = new Date(ts)
              const dateStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
              const timeStr = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
              return `${dateStr} ${timeStr}<br>O: $${chartData.opens[i].toFixed(2)}<br>H: $${chartData.highs[i].toFixed(2)}<br>L: $${chartData.lows[i].toFixed(2)}<br>C: $${chartData.closes[i].toFixed(2)}`
            }),
            xperiod: 1,
          } as Plotly.Data,
        ]}
        layout={{
          autosize: true,
          height: height,
          margin: { l: 10, r: 70, t: 60, b: 50 },
          paper_bgcolor: 'transparent',
          plot_bgcolor: 'transparent',
          font: { color: 'rgba(255, 255, 255, 0.7)', family: 'Inter, system-ui, sans-serif', size: 11 },
          bargap: 0.3,
          images: [
            {
              source: "/chart_watermark.svg",
              xref: "paper",
              yref: "paper",
              x: 0.5,
              y: 0.5,
              sizex: isMobile ? 1 : 0.5,
              sizey: 1,
              sizing: "contain",
              opacity: 0.05,
              xanchor: "center",
              yanchor: "middle",
              layer: "below"
            }
          ],
          xaxis: {
            type: 'linear',
            tickmode: 'array',
            tickvals: chartData.tickvals,
            ticktext: chartData.ticktext,
            gridcolor: 'rgba(255,255,255,0.03)',
            linecolor: 'rgba(255,255,255,0.08)',
            tickcolor: 'rgba(255,255,255,0.1)',
            showgrid: true,
            gridwidth: 1,
            zeroline: false,
            rangeslider: { visible: false },
            range: [-5, chartData.totalBars + 15], // Padding: left and right
          },
          yaxis: {
            gridcolor: 'rgba(255,255,255,0.03)',
            linecolor: 'rgba(255,255,255,0.08)',
            tickcolor: 'rgba(255,255,255,0.1)',
            tickprefix: '$',
            showgrid: true,
            gridwidth: 1,
            zeroline: false,
            side: 'right',
          },
          hovermode: 'x',
          dragmode: 'pan',
          showlegend: false,
        }}
        config={{
          displayModeBar: false,
          responsive: true,
          scrollZoom: true,
        }}
        style={{ width: '100%', height: height }}
        useResizeHandler={true}
      />
    </div>
  )
}
