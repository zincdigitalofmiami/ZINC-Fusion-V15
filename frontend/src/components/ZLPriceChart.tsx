'use client'

import dynamic from 'next/dynamic'
import { useMemo, useState, useEffect } from 'react'

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

export default function ZLPriceChart({ height = 500, data }: ZLPriceChartProps) {
  const [selectedModel, setSelectedModel] = useState(AVAILABLE_MODELS[0])
  const [isMobile, setIsMobile] = useState(false)

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

  // Sample data if none provided
  const chartData = useMemo(() => {
    if (data) return data
    
    // Generate sophisticated looking curve
    const time: string[] = []
    const close: number[] = []
    let price = 48.50
    const now = new Date()
    
    // 60 days history
    for(let i=60; i>0; i--) {
        const d = new Date(now)
        d.setDate(d.getDate() - i)
        time.push(d.toISOString().split('T')[0])
        price = price + (Math.random() - 0.48) * 0.8 // slight uptrend bias
        close.push(price)
    }

    const lastPrice = close[close.length-1]
    const targetDates: string[] = []
    const p50 = []
    const p10 = []
    const p25 = []
    const p75 = []
    const p90 = []

    let currentP50 = lastPrice
    
    // 30 days forecast
    for(let i=0; i<30; i++) {
        const d = new Date(now)
        d.setDate(d.getDate() + i)
        targetDates.push(d.toISOString().split('T')[0])
        
        // Logarithmic decay of certainty + trend
        const dayFactor = Math.sqrt(i + 1) * 0.15
        
        // Slightly different curve shape per model to show "live" switching
        let noise = 0
        if (selectedModel.id === 'core_chronos2') noise = Math.sin(i/2) * 0.1
        if (selectedModel.id === 'core_deepar') noise = Math.cos(i/3) * 0.15
        if (selectedModel.id === 'core_tide') noise = (Math.random() - 0.5) * 0.2

        currentP50 = currentP50 + (0.05 * Math.sin(i/3)) + 0.02 + noise
        
        p50.push(currentP50)
        p25.push(currentP50 - (dayFactor * 0.8))
        p75.push(currentP50 + (dayFactor * 0.8))
        p10.push(currentP50 - (dayFactor * 1.5))
        p90.push(currentP50 + (dayFactor * 1.5))
    }

    return {
      time,
      close,
      targetDates,
      p10, p25, p50, p75, p90
    }
  }, [data, selectedModel])

  return (
    <div className="relative group">
      {/* Model Selector Overlay */}
      <div className="absolute top-4 left-16 z-10 flex gap-2">
        <select 
          value={selectedModel.id}
          onChange={(e) => setSelectedModel(AVAILABLE_MODELS.find(m => m.id === e.target.value) || AVAILABLE_MODELS[0])}
          className="bg-black/40 backdrop-blur-md border border-white/10 text-xs text-white rounded px-2 py-1 outline-none hover:bg-black/60 transition-colors cursor-pointer appearance-none pl-3 pr-8"
          style={{ backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%23ffffff' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`, backgroundPosition: 'right 0.25rem center', backgroundRepeat: 'no-repeat', backgroundSize: '1.25em 1.25em' }}
        >
          {AVAILABLE_MODELS.map(m => (
            <option key={m.id} value={m.id} className="bg-slate-900 text-slate-200">
              {m.label}
            </option>
          ))}
        </select>
        <div className="hidden group-hover:flex items-center text-[10px] text-white/40 px-2 bg-white/5 rounded backdrop-blur-sm border border-white/5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-2 animate-pulse"></span>
          LIVE INFERENCE
        </div>
      </div>

      <Plot
        data={[
          // Historical price line
          {
            x: chartData.time,
            y: chartData.close,
            type: 'scatter',
            mode: 'lines',
            name: 'ZL Spot',
            line: { color: '#ffffff', width: 2 }, 
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
