'use client'

import dynamic from 'next/dynamic'
import { useState, useEffect } from 'react'

// Dynamic import to avoid SSR issues with Plotly
const Plot = dynamic(() => import('react-plotly.js'), { 
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[500px] text-slate-500 animate-pulse">
      Initialising L1 Prediction Engine...
    </div>
  )
})

const AVAILABLE_MODELS = [
  { id: 'l1_ensemble', label: 'L1 Ensemble (Meta-Learner)', color: '#00E676' },
  { id: 'core_chronos2', label: 'Core Chronos2 (Foundation)', color: '#2979FF' },
  { id: 'core_deepar', label: 'Core DeepAR (Probabilistic)', color: '#FF9100' },
  { id: 'core_tide', label: 'Core TiDE (Transformer)', color: '#F50057' },
]

interface ZLPriceChartProps {
  height?: number
  data?: {
    time: string[]
    close: number[]
    targetDates: string[]
    p10?: number[]
    p25?: number[]
    p50?: number[]
    p75?: number[]
    p90?: number[]
  }
}

export default function ZLPriceChart({ height = 500 }: ZLPriceChartProps) {
  const [selectedModel, setSelectedModel] = useState(AVAILABLE_MODELS[0])
  const [isMobile, setIsMobile] = useState(false)
  const [chartData, setChartData] = useState<{
    time: string[]
    close: number[]
    targetDates: string[]
    p10: number[]
    p25: number[]
    p50: number[]
    p75: number[]
    p90: number[]
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768)
    }
    
    // Check initial
    checkMobile()
    
    // Add listener
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // Fetch real data from API (6 months fixed = ~4380 hours)
  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true)
        const res = await fetch('/api/zl/price-1h?hours=4380')
        if (!res.ok) throw new Error('Failed to fetch ZL data')
        const json = await res.json()
        
        // Transform API response to chart format
        const time = json.data.map((d: { timestamp: string }) => d.timestamp)
        const close = json.data.map((d: { close: number }) => d.close)
        
        setChartData({
          time,
          close,
          targetDates: [],
          p10: [],
          p25: [],
          p50: [],
          p75: [],
          p90: []
        })
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[500px] text-slate-500 animate-pulse">
        Loading ZL price data...
      </div>
    )
  }

  if (error || !chartData) {
    return (
      <div className="flex items-center justify-center h-[500px] text-red-500">
        ERROR: {error || 'No data available'}
      </div>
    )
  }

  return (
    <div className="relative group">
      <Plot
        data={[
          // Historical price line with red gradient fill
          {
            x: chartData.time,
            y: chartData.close,
            type: 'scatter',
            mode: 'lines',
            name: 'ZL Spot',
            line: { color: '#FF3B30', width: 2.5 },
            fill: 'tozeroy',
            fillcolor: 'rgba(255, 59, 48, 0.15)',
            hovertemplate: '%{x}<br>Spot: $%{y:.2f}<extra></extra>',
          },
          // P90 Bound (Invisible)
          {
            x: chartData.targetDates,
            y: chartData.p90,
            type: 'scatter',
            mode: 'lines',
            name: 'P90',
            line: { width: 0, shape: 'spline' },
            showlegend: false,
            hoverinfo: 'skip'
          },
          // P10 Bound (Fill to P90)
          {
            x: chartData.targetDates,
            y: chartData.p10,
            type: 'scatter',
            mode: 'lines',
            fill: 'tonexty',
            fillcolor: 'rgba(41, 98, 255, 0.08)', 
            name: 'Confidence (90%)',
            line: { width: 0, shape: 'spline' },
            showlegend: true,
            hoverinfo: 'skip'
          },
          // P75 Bound (Invisible)
          {
            x: chartData.targetDates,
            y: chartData.p75,
            type: 'scatter',
            mode: 'lines',
            name: 'P75',
            line: { width: 0, shape: 'spline' },
            showlegend: false,
            hoverinfo: 'skip'
          },
          // P25 Bound (Fill to P75)
          {
            x: chartData.targetDates,
            y: chartData.p25,
            type: 'scatter',
            mode: 'lines',
            fill: 'tonexty',
            fillcolor: 'rgba(41, 98, 255, 0.15)', 
            name: 'Likely Range (50%)',
            line: { width: 0, shape: 'spline' },
            showlegend: true,
            hoverinfo: 'skip'
          },
          // Prediction Line (Dynamic Color)
          {
            x: chartData.targetDates,
            y: chartData.p50,
            type: 'scatter',
            mode: 'lines',
            name: selectedModel.label.split('(')[0].trim(),
            line: { color: selectedModel.color, width: 3, dash: 'dot', shape: 'spline' },
            hovertemplate: `%{x}<br>${selectedModel.label}: $%{y:.2f}<extra></extra>`,
          },
        ]}
        layout={{
          autosize: true,
          height: height,
          margin: { l: 40, r: 20, t: 30, b: 40 },
          paper_bgcolor: 'transparent',
          plot_bgcolor: 'transparent',
          font: { color: 'rgba(255, 255, 255, 0.8)', family: 'monospace' },
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
              opacity: 0.1,
              xanchor: "center",
              yanchor: "middle",
              layer: "below"
            }
          ],
          xaxis: {
            gridcolor: 'rgba(255,255,255,0.03)',
            linecolor: 'rgba(255,255,255,0.1)',
            zerolinecolor: 'rgba(255,255,255,0.1)',
            showgrid: true,
            gridwidth: 1,
          },
          yaxis: {
            gridcolor: 'rgba(255,255,255,0.03)',
            linecolor: 'rgba(255,255,255,0.1)',
            zerolinecolor: 'rgba(255,255,255,0.1)',
            tickprefix: '$',
            showgrid: true,
            gridwidth: 1,
          },
          legend: {
            orientation: 'h',
            y: 1.05,
            x: 0.3, // Shifted to make room for dropdown
            font: { size: 10 },
            bgcolor: 'rgba(0,0,0,0)'
          },
          hovermode: 'x unified',
          dragmode: 'pan',
          showlegend: true,
        }}
        config={{
          displayModeBar: false,
          responsive: true,
          scrollZoom: false,
        }}
        style={{ width: '100%', height: height }}
        useResizeHandler={true}
      />
    </div>
  )
}
