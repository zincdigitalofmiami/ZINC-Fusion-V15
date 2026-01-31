'use client'

import React, { useEffect, useState, useCallback } from 'react'

// =============================================================================
// CHRIS'S TOP 4 KEY MARKET DRIVERS
// Real domain-specific pressure indicators for soybean oil markets
// =============================================================================

interface DriverData {
  name: string
  score: number
  level: string
  regime: string
  headline: string
  components: Record<string, number | null>
}

interface MarketDriversResponse {
  as_of_date: string
  drivers: {
    vix_stress: DriverData
    crush_pressure: DriverData
    china_tension: DriverData
    tariff_threat: DriverData
  }
  summary: {
    average_pressure: number
    highest_pressure: { name: string; score: number }
    alert_count: number
  }
}

// Arc gauge colors by variant
const VARIANTS = {
  stress: { stroke: '#EF4444', glow: 'rgba(239, 68, 68, 0.4)' },    // Red - VIX
  crush: { stroke: '#22C55E', glow: 'rgba(34, 197, 94, 0.4)' },     // Green - Crush
  tension: { stroke: '#F59E0B', glow: 'rgba(245, 158, 11, 0.4)' },  // Amber - China
  threat: { stroke: '#00D4FF', glow: 'rgba(0, 212, 255, 0.4)' },    // Cyan - Tariff
}

type VariantKey = keyof typeof VARIANTS

function ArcGauge({ score, variant }: { score: number; variant: VariantKey }) {
  const percentage = Math.min(Math.max(score, 0), 100)
  const radius = 40
  const strokeWidth = 3
  const circumference = Math.PI * radius
  const strokeDashoffset = circumference - (circumference * percentage / 100)
  const colors = VARIANTS[variant]

  return (
    <svg viewBox="0 0 100 55" className="w-full h-auto">
      <path
        d="M 10 50 A 40 40 0 0 1 90 50"
        fill="none"
        stroke="rgba(255, 255, 255, 0.05)"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
      <path
        d="M 10 50 A 40 40 0 0 1 90 50"
        fill="none"
        stroke={colors.stroke}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={strokeDashoffset}
        style={{
          transition: 'stroke-dashoffset 0.8s ease-out',
          filter: `drop-shadow(0 0 6px ${colors.glow})`
        }}
      />
    </svg>
  )
}

interface DriverCardProps {
  label: string
  data: DriverData | null
  metricKey: string
  metricLabel: string
  metricFormat?: (val: number | null) => string
  variant: VariantKey
  loading: boolean
}

function DriverCard({
  label,
  data,
  metricKey,
  metricLabel,
  metricFormat,
  variant,
  loading
}: DriverCardProps) {
  const score = data?.score ?? 0
  const level = data?.level ?? '--'
  const metricValue = data?.components?.[metricKey] ?? null
  const formattedMetric = metricFormat
    ? metricFormat(metricValue)
    : metricValue?.toString() ?? '--'

  // Score-based border glow
  const borderColor = score >= 65
    ? 'border-red-500/30 shadow-[0_0_15px_rgba(239,68,68,0.15)]'
    : score >= 50
      ? 'border-amber-500/20'
      : 'border-white/5'

  return (
    <div className={`bg-[#0a0a0a] border rounded-xl p-5 flex flex-col items-center hover:border-white/10 transition-all ${borderColor}`}>
      {/* Label */}
      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] mb-2">
        {label}
      </div>

      {/* Arc Gauge */}
      <div className="w-28 -mb-3">
        <ArcGauge score={score} variant={variant} />
      </div>

      {/* Score */}
      <div className={`text-3xl font-bold tabular-nums -mt-1 transition-all ${
        loading ? 'text-slate-600 animate-pulse' : 'text-white'
      }`}>
        {loading ? '--' : Math.round(score)}
      </div>

      {/* Level */}
      <div className={`text-xs mt-1 ${
        score >= 65 ? 'text-red-400' : score >= 50 ? 'text-amber-400' : 'text-slate-400'
      }`}>
        {loading ? '...' : level}
      </div>

      {/* Metric */}
      <div className="text-[10px] text-slate-500 mt-2 text-center">
        {metricLabel}: <span className="text-slate-300 font-mono">{loading ? '--' : formattedMetric}</span>
      </div>
    </div>
  )
}

export function ChrisTop4Drivers() {
  const [data, setData] = useState<MarketDriversResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)

  const fetchDrivers = useCallback(async () => {
    try {
      const res = await fetch('/api/market-drivers')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      if (json.error) throw new Error(json.error)
      setData(json)
      setError(null)
      setLastUpdate(new Date().toLocaleTimeString())
    } catch (e) {
      console.error('Failed to fetch market drivers:', e)
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDrivers()
    const interval = setInterval(fetchDrivers, 5 * 60 * 1000) // Refresh every 5 min
    return () => clearInterval(interval)
  }, [fetchDrivers])

  const d = data?.drivers

  return (
    <div className="w-full">
      {/* Section Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 pl-1 border-l-4 border-cyan-500">
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
          {data?.summary?.alert_count && data.summary.alert_count > 0 && (
            <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-red-500/20 text-red-400 border border-red-500/30 animate-pulse">
              {data.summary.alert_count} ALERT{data.summary.alert_count > 1 ? 'S' : ''}
            </span>
          )}
        </div>
        {lastUpdate && (
          <span className="text-[9px] text-slate-600">
            Updated {lastUpdate}
          </span>
        )}
      </div>

      {/* 4 Driver Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <DriverCard
          label="VIX Stress"
          data={d?.vix_stress ?? null}
          metricKey="vix_value"
          metricLabel="VIX"
          metricFormat={(v) => v?.toFixed(1) ?? '--'}
          variant="stress"
          loading={loading}
        />
        <DriverCard
          label="Crush Pressure"
          data={d?.crush_pressure ?? null}
          metricKey="board_crush_value"
          metricLabel="Board Crush"
          metricFormat={(v) => v ? `$${v.toFixed(2)}` : '--'}
          variant="crush"
          loading={loading}
        />
        <DriverCard
          label="China Tension"
          data={d?.china_tension ?? null}
          metricKey="cny_rate"
          metricLabel="CNY/USD"
          metricFormat={(v) => v?.toFixed(2) ?? '--'}
          variant="tension"
          loading={loading}
        />
        <DriverCard
          label="Tariff Threat"
          data={d?.tariff_threat ?? null}
          metricKey="tpu_value"
          metricLabel="TPU Index"
          metricFormat={(v) => v?.toFixed(0) ?? '--'}
          variant="threat"
          loading={loading}
        />
      </div>

      {/* Summary Bar */}
      {data?.summary && (
        <div className="mt-4 flex items-center justify-between text-[10px] text-slate-500 px-2">
          <div>
            Avg Pressure: <span className="text-slate-300 font-mono">{data.summary.average_pressure}</span>
          </div>
          <div>
            Highest: <span className="text-slate-300">{data.summary.highest_pressure?.name}</span>
            {' '}(<span className="font-mono">{data.summary.highest_pressure?.score}</span>)
          </div>
          <div>
            As of: <span className="text-slate-400">{data.as_of_date}</span>
          </div>
        </div>
      )}
    </div>
  )
}

// Compact version for header/sidebar
export function ChrisTop4Compact() {
  const [data, setData] = useState<MarketDriversResponse | null>(null)

  useEffect(() => {
    fetch('/api/market-drivers')
      .then(res => res.json())
      .then(setData)
      .catch(console.error)
  }, [])

  const drivers = [
    { label: 'VIX', score: data?.drivers?.vix_stress?.score ?? 0, color: VARIANTS.stress.stroke },
    { label: 'Crush', score: data?.drivers?.crush_pressure?.score ?? 0, color: VARIANTS.crush.stroke },
    { label: 'China', score: data?.drivers?.china_tension?.score ?? 0, color: VARIANTS.tension.stroke },
    { label: 'Tariff', score: data?.drivers?.tariff_threat?.score ?? 0, color: VARIANTS.threat.stroke },
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
          <span className={`text-xs font-mono ${d.score >= 65 ? 'text-red-400' : 'text-white'}`}>
            {Math.round(d.score)}
          </span>
        </div>
      ))}
    </div>
  )
}
