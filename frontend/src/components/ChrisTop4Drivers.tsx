'use client'

import React, { useEffect, useState } from 'react'

// Chris's TOP 4 Key Drivers - Real domain-specific market pressure indicators
// VIX Stress, Crush Pressure, China Tension, Tariff Threat

interface DriverGaugeProps {
  label: string
  score: number
  level: string
  metric: string
  metricLabel: string
  variant?: 'stress' | 'crush' | 'tension' | 'threat'
  loading?: boolean
}

// Arc gauge colors by variant
const VARIANTS = {
  stress: { stroke: '#EF4444', bg: 'rgba(239, 68, 68, 0.1)' },   // Red - VIX
  crush: { stroke: '#22C55E', bg: 'rgba(34, 197, 94, 0.1)' },    // Green - Crush
  tension: { stroke: '#F59E0B', bg: 'rgba(245, 158, 11, 0.1)' }, // Amber - China
  threat: { stroke: '#00D4FF', bg: 'rgba(0, 212, 255, 0.1)' },   // Cyan - Tariff
}

function ArcGauge({ score, variant = 'stress' }: { score: number; variant: DriverGaugeProps['variant'] }) {
  // Score 0-100
  const percentage = Math.min(Math.max(score, 0), 100)

  const radius = 40
  const strokeWidth = 3
  const circumference = Math.PI * radius
  const strokeDasharray = circumference
  const strokeDashoffset = circumference - (circumference * percentage / 100)

  const colors = VARIANTS[variant || 'stress']

  return (
    <svg viewBox="0 0 100 55" className="w-full h-auto">
      {/* Background arc */}
      <path
        d="M 10 50 A 40 40 0 0 1 90 50"
        fill="none"
        stroke="rgba(255, 255, 255, 0.05)"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
      {/* Value arc */}
      <path
        d="M 10 50 A 40 40 0 0 1 90 50"
        fill="none"
        stroke={colors.stroke}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={strokeDasharray}
        strokeDashoffset={strokeDashoffset}
        style={{
          transition: 'stroke-dashoffset 0.8s ease-out',
          filter: `drop-shadow(0 0 6px ${colors.stroke}40)`
        }}
      />
    </svg>
  )
}

function DriverGaugeCard({ label, score, level, metric, metricLabel, variant = 'stress', loading }: DriverGaugeProps) {
  return (
    <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-5 flex flex-col items-center hover:border-white/10 transition-colors">
      {/* Label */}
      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] mb-2">
        {label}
      </div>

      {/* Arc Gauge */}
      <div className="w-28 -mb-3">
        <ArcGauge score={score} variant={variant} />
      </div>

      {/* Main Score */}
      <div className={`text-3xl font-bold tabular-nums -mt-1 ${loading ? 'text-slate-600 animate-pulse' : 'text-white'}`}>
        {loading ? '--' : score}
      </div>

      {/* Level */}
      <div className="text-xs text-slate-400 mt-1">
        {loading ? '...' : level}
      </div>

      {/* Metric */}
      <div className="text-[10px] text-slate-500 mt-2 text-center">
        {metricLabel}: <span className="text-slate-300">{loading ? '--' : metric}</span>
      </div>
    </div>
  )
}

interface MarketDriversData {
  drivers: {
    vix_stress: {
      score: number
      level: string
      components: { vix_value?: number }
    }
    crush_pressure: {
      score: number
      level: string
      components: { board_crush_value?: number }
    }
    china_tension: {
      score: number
      level: string
      components: { cny_rate?: number; fxi_change_20d?: number }
    }
    tariff_threat: {
      score: number
      level: string
      components: { tpu_value?: number }
    }
  }
  summary: {
    average_pressure: number
    alert_count: number
  }
}

export function ChrisTop4Drivers() {
  const [data, setData] = useState<MarketDriversData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchDrivers() {
      try {
        const res = await fetch('/api/market-drivers')
        if (!res.ok) throw new Error('Failed to fetch')
        const json = await res.json()
        setData(json)
        setError(null)
      } catch (e) {
        console.error('Failed to fetch market drivers:', e)
        setError('Failed to load')
      } finally {
        setLoading(false)
      }
    }
    fetchDrivers()
    // Refresh every 5 minutes
    const interval = setInterval(fetchDrivers, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [])

  const d = data?.drivers

  return (
    <div className="w-full">
      {/* Section Header */}
      <div className="flex items-center gap-2 mb-4 pl-1 border-l-4 border-cyan-500">
        <h3 className="text-sm font-bold text-white uppercase tracking-wider">
          Key Market Drivers
        </h3>
        <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
          CHRIS'S TOP 4
        </span>
        {error && (
          <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-red-500/10 text-red-400 border border-red-500/20">
            ERROR
          </span>
        )}
      </div>

      {/* 4 Gauge Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <DriverGaugeCard
          label="VIX Stress"
          score={d?.vix_stress?.score ?? 0}
          level={d?.vix_stress?.level ?? '--'}
          metric={d?.vix_stress?.components?.vix_value?.toFixed(1) ?? '--'}
          metricLabel="VIX"
          variant="stress"
          loading={loading}
        />
        <DriverGaugeCard
          label="Crush Pressure"
          score={d?.crush_pressure?.score ?? 0}
          level={d?.crush_pressure?.level ?? '--'}
          metric={d?.crush_pressure?.components?.board_crush_value ? `$${d.crush_pressure.components.board_crush_value.toFixed(2)}` : '--'}
          metricLabel="Board Crush"
          variant="crush"
          loading={loading}
        />
        <DriverGaugeCard
          label="China Tension"
          score={d?.china_tension?.score ?? 0}
          level={d?.china_tension?.level ?? '--'}
          metric={d?.china_tension?.components?.cny_rate?.toFixed(2) ?? '--'}
          metricLabel="CNY/USD"
          variant="tension"
          loading={loading}
        />
        <DriverGaugeCard
          label="Tariff Threat"
          score={d?.tariff_threat?.score ?? 0}
          level={d?.tariff_threat?.level ?? '--'}
          metric={d?.tariff_threat?.components?.tpu_value?.toFixed(0) ?? '--'}
          metricLabel="TPU Index"
          variant="threat"
          loading={loading}
        />
      </div>
    </div>
  )
}

// Compact version for sidebar/secondary placement
export function ChrisTop4Compact() {
  const [data, setData] = useState<MarketDriversData | null>(null)

  useEffect(() => {
    fetch('/api/market-drivers')
      .then(res => res.json())
      .then(setData)
      .catch(console.error)
  }, [])

  const drivers = [
    { label: 'VIX', score: data?.drivers?.vix_stress?.score ?? 0, color: '#EF4444' },
    { label: 'Crush', score: data?.drivers?.crush_pressure?.score ?? 0, color: '#22C55E' },
    { label: 'China', score: data?.drivers?.china_tension?.score ?? 0, color: '#F59E0B' },
    { label: 'Tariff', score: data?.drivers?.tariff_threat?.score ?? 0, color: '#00D4FF' },
  ]

  return (
    <div className="flex items-center gap-4">
      {drivers.map((d) => (
        <div key={d.label} className="flex items-center gap-1.5">
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: d.color }}
          />
          <span className="text-[10px] text-slate-500 uppercase">{d.label}</span>
          <span className="text-xs font-mono text-white">{d.score}</span>
        </div>
      ))}
    </div>
  )
}
