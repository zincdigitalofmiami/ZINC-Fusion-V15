'use client'

import dynamic from 'next/dynamic'
import { useMemo } from 'react'

// Dynamic import to avoid SSR issues with Plotly
const Plot = dynamic(() => import('react-plotly.js'), { 
  ssr: false,
  loading: () => (
    <div style={{ 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center', 
      height: 320,
      opacity: 0.4 
    }}>
      Loading chart...
    </div>
  )
})

interface ZLPriceChartProps {
  data?: {
    dates: string[]
    prices: number[]
    p10?: number[]
    p50?: number[]
    p90?: number[]
  }
}

export default function ZLPriceChart({ data }: ZLPriceChartProps) {
  // Sample data if none provided
  const chartData = useMemo(() => {
    if (data) return data
    return {
      dates: ['2025-12-26', '2025-12-27', '2025-12-30', '2025-12-31', '2026-01-02', '2026-01-03', '2026-01-06', '2026-01-07', '2026-01-08'],
      prices: [44.2, 44.8, 45.1, 45.9, 46.3, 46.9, 47.8, 47.2, 47.5],
      // Forecast cone (P10/P50/P90)
      p10: [null, null, null, null, null, null, 47.8, 46.5, 45.8, 45.2, 44.8],
      p50: [null, null, null, null, null, null, 47.8, 48.2, 48.8, 49.1, 49.5],
      p90: [null, null, null, null, null, null, 47.8, 49.8, 50.5, 51.2, 52.0],
    }
  }, [data])

  const forecastDates = ['2026-01-06', '2026-01-07', '2026-01-08', '2026-01-09', '2026-01-10']

  return (
    <Plot
      data={[
        // Historical price line
        {
          x: chartData.dates,
          y: chartData.prices,
          type: 'scatter',
          mode: 'lines',
          name: 'ZL Price',
          line: { color: '#2962FF', width: 2 },
          hovertemplate: '%{x}<br>$%{y:.2f}<extra></extra>',
        },
        // P90 upper bound (forecast)
        {
          x: forecastDates,
          y: [47.8, 49.8, 50.5, 51.2, 52.0],
          type: 'scatter',
          mode: 'lines',
          name: 'P90 Ceiling',
          line: { color: 'rgba(41, 98, 255, 0.3)', width: 1, dash: 'dot' },
          showlegend: false,
        },
        // P10 lower bound (forecast) with fill
        {
          x: forecastDates,
          y: [47.8, 46.5, 45.8, 45.2, 44.8],
          type: 'scatter',
          mode: 'lines',
          name: 'P10 Floor',
          line: { color: 'rgba(41, 98, 255, 0.3)', width: 1, dash: 'dot' },
          fill: 'tonexty',
          fillcolor: 'rgba(41, 98, 255, 0.1)',
          showlegend: false,
        },
        // P50 forecast line
        {
          x: forecastDates,
          y: [47.8, 48.2, 48.8, 49.1, 49.5],
          type: 'scatter',
          mode: 'lines',
          name: 'P50 Forecast',
          line: { color: '#81c784', width: 2, dash: 'dash' },
          hovertemplate: '%{x}<br>Forecast: $%{y:.2f}<extra></extra>',
        },
      ]}
      layout={{
        autosize: true,
        height: 320,
        margin: { l: 50, r: 20, t: 20, b: 40 },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { color: 'rgba(209, 212, 220, 0.9)', size: 11 },
        xaxis: {
          gridcolor: 'rgba(255,255,255,0.06)',
          linecolor: 'rgba(255,255,255,0.10)',
          tickformat: '%b %d',
        },
        yaxis: {
          gridcolor: 'rgba(255,255,255,0.06)',
          linecolor: 'rgba(255,255,255,0.10)',
          tickprefix: '$',
          tickformat: '.2f',
        },
        legend: {
          orientation: 'h',
          y: -0.15,
          x: 0.5,
          xanchor: 'center',
        },
        hovermode: 'x unified',
        dragmode: 'pan',
      }}
      config={{
        displayModeBar: false,
        responsive: true,
      }}
      style={{ width: '100%', height: 320 }}
      useResizeHandler={true}
    />
  )
}
