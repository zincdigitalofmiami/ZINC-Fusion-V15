'use client'

import React, { useEffect, useState, useCallback } from 'react'

// =============================================================================
// CHRIS'S TOP 4 KEY MARKET DRIVERS
// Real domain-specific pressure indicators for soybean oil markets
// Gauges turn RED as pressure increases
// =============================================================================

interface WhatsHappening {
  whatsHappening: string
  macroContext: string
  supplyDemand: string
  geopolitical: string
  investorSentiment: string
  nearTermOutlook: string
  zlImplication: string
}

interface DriverData {
  name: string
  score: number
  level: string
  regime: string
  headline: string
  components: Record<string, number | null>
  whatsHappening?: WhatsHappening
  aiPowered?: boolean
  dataDate?: string  // Source data freshness (e.g., "2026-01-30")
}

// Comprehensive report sections (Opus 4.5 institutional-grade output)
interface ComprehensiveReport {
  tldr: string                // Quick summary with price targets and timeframes
  currentSnapshot: string     // Current market snapshot with prices
  keyDrivers: string          // Detailed breakdown of all key drivers
  forecasts: string           // Time-horizon forecasts (1 week, 1 month, 1 quarter, 6 months)
  correlations: string        // Correlation summary with specific coefficients
  technicalOutlook: string    // Support/resistance, trends, key levels
}

interface IntelligenceData {
  headline: string
  summary: string
  drivers: { label: string; outlook: string; detail: string }[]
  zlOutlook: 'BULLISH' | 'NEUTRAL' | 'CAUTIOUS' | 'BEARISH'
  zlColor: string
  tradingImplication?: string
  comprehensiveReport?: ComprehensiveReport  // Institutional-grade full report
  aiPowered?: boolean
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
  intelligence: IntelligenceData
}

// =============================================================================
// DYNAMIC COLOR BASED ON SCORE
// Green (safe) → Yellow → Orange → Red (danger)
// =============================================================================

function getScoreColor(score: number): { stroke: string; glow: string } {
  // Clamp score to 0-100
  const s = Math.max(0, Math.min(100, score))

  if (s <= 25) {
    // Green zone: 0-25
    return { stroke: '#22C55E', glow: 'rgba(34, 197, 94, 0.5)' }
  } else if (s <= 40) {
    // Green to Yellow transition: 25-40
    const t = (s - 25) / 15
    return {
      stroke: `rgb(${Math.round(34 + (234 - 34) * t)}, ${Math.round(197 - (197 - 179) * t)}, ${Math.round(94 - (94 - 8) * t)})`,
      glow: `rgba(${Math.round(34 + (234 - 34) * t)}, ${Math.round(197 - (197 - 179) * t)}, ${Math.round(94 - (94 - 8) * t)}, 0.5)`
    }
  } else if (s <= 55) {
    // Yellow/Amber zone: 40-55
    return { stroke: '#EAB308', glow: 'rgba(234, 179, 8, 0.5)' }
  } else if (s <= 70) {
    // Orange zone: 55-70
    const t = (s - 55) / 15
    return {
      stroke: `rgb(${Math.round(234 + (239 - 234) * t)}, ${Math.round(179 - (179 - 115) * t)}, ${Math.round(8 + (0 - 8) * t)})`,
      glow: `rgba(${Math.round(234 + (239 - 234) * t)}, ${Math.round(179 - (179 - 115) * t)}, ${Math.round(8 + (0 - 8) * t)}, 0.5)`
    }
  } else if (s <= 85) {
    // Orange-Red zone: 70-85
    return { stroke: '#EF7300', glow: 'rgba(239, 115, 0, 0.5)' }
  } else {
    // Red danger zone: 85-100
    return { stroke: '#EF4444', glow: 'rgba(239, 68, 68, 0.6)' }
  }
}

// Get text color based on score
function getScoreTextColor(score: number): string {
  if (score >= 70) return 'text-red-400'
  if (score >= 55) return 'text-orange-400'
  if (score >= 40) return 'text-amber-400'
  return 'text-green-400'
}

// =============================================================================
// ARC GAUGE COMPONENT
// =============================================================================

function ArcGauge({ score }: { score: number }) {
  const percentage = Math.min(Math.max(score, 0), 100)
  const radius = 40
  const strokeWidth = 4
  const circumference = Math.PI * radius
  const strokeDashoffset = circumference - (circumference * percentage / 100)
  const colors = getScoreColor(score)

  return (
    <svg viewBox="0 0 100 55" className="w-full h-auto">
      {/* Background arc */}
      <path
        d="M 10 50 A 40 40 0 0 1 90 50"
        fill="none"
        stroke="rgba(255, 255, 255, 0.08)"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
      {/* Colored arc based on score */}
      <path
        d="M 10 50 A 40 40 0 0 1 90 50"
        fill="none"
        stroke={colors.stroke}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={strokeDashoffset}
        style={{
          transition: 'stroke-dashoffset 0.8s ease-out, stroke 0.5s ease',
          filter: `drop-shadow(0 0 8px ${colors.glow})`
        }}
      />
    </svg>
  )
}

// =============================================================================
// DRIVER CARD COMPONENT
// =============================================================================

interface MetricDisplay {
  key: string
  label: string
  format: (val: number | null) => string
}

interface DriverCardProps {
  label: string
  data: DriverData | null
  metrics: MetricDisplay[]  // Show multiple metrics per card
  loading: boolean
}

function DriverCard({ label, data, metrics, loading }: DriverCardProps) {
  const [expanded, setExpanded] = useState(false)
  const score = data?.score ?? 0
  const level = data?.level ?? '--'
  const colors = getScoreColor(score)
  const wh = data?.whatsHappening

  // Dynamic border based on score
  const borderStyle = score >= 65
    ? { borderColor: colors.stroke, boxShadow: `0 0 20px ${colors.glow}` }
    : { borderColor: 'rgba(255,255,255,0.05)' }

  return (
    <div
      className="bg-[#0a0a0a] border rounded-xl p-5 flex flex-col items-center hover:border-white/20 transition-all duration-300"
      style={borderStyle}
    >
      {/* Label */}
      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] mb-2 flex items-center gap-1.5">
        {label}
        {data?.aiPowered && (
          <span className="px-1 py-0.5 rounded text-[7px] bg-violet-500/20 text-violet-400">AI</span>
        )}
      </div>

      {/* Arc Gauge */}
      <div className="w-28 -mb-3">
        <ArcGauge score={score} />
      </div>

      {/* Score - colored by severity */}
      <div
        className={`text-3xl font-bold tabular-nums -mt-1 transition-all duration-300 ${
          loading ? 'text-slate-600 animate-pulse' : ''
        }`}
        style={{ color: loading ? undefined : colors.stroke }}
      >
        {loading ? '--' : Math.round(score)}
      </div>

      {/* Level - colored by severity */}
      <div className={`text-xs mt-1 ${loading ? 'text-slate-600' : getScoreTextColor(score)}`}>
        {loading ? '...' : level}
      </div>

      {/* Metrics List - Multiple metrics per card */}
      <div className="mt-2 w-full space-y-0.5">
        {metrics.map((metric) => {
          const value = data?.components?.[metric.key] ?? null
          return (
            <div key={metric.key} className="flex justify-between items-center text-[10px] px-1">
              <span className="text-slate-500">{metric.label}</span>
              <span className="text-slate-300 font-mono">
                {loading ? '--' : metric.format(value)}
              </span>
            </div>
          )
        })}
      </div>

      {/* Headline */}
      <div className="mt-3 text-[11px] text-slate-300 text-center leading-snug min-h-[28px]">
        {loading ? '...' : (data?.headline ?? '--')}
      </div>

      {/* Data Freshness Indicator */}
      {!loading && data?.dataDate && (
        <div className="mt-1 text-[8px] text-slate-600 font-mono">
          Data as of: {data.dataDate}
        </div>
      )}

      {/* What's Happening Button */}
      {wh && !loading && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-3 w-full px-3 py-1.5 rounded-lg text-[10px] font-medium bg-slate-800/80 hover:bg-slate-700/80 text-slate-400 hover:text-slate-200 transition-all flex items-center justify-center gap-1.5 border border-slate-700/50"
        >
          <span>{expanded ? '▼' : '▶'}</span>
          What's Happening?
        </button>
      )}

      {/* Expanded Intel Panel */}
      {expanded && wh && (
        <div className="mt-3 w-full text-left space-y-2 animate-in slide-in-from-top-2 duration-200">
          {/* Summary */}
          <div className="text-[11px] text-slate-300 leading-relaxed border-l-2 pl-2" style={{ borderColor: colors.stroke }}>
            {wh.whatsHappening}
          </div>

          {/* Sections */}
          <div className="space-y-1.5 pt-1">
            <IntelSection title="Macro Context" content={wh.macroContext} />
            <IntelSection title="Supply & Demand" content={wh.supplyDemand} />
            <IntelSection title="Geopolitical" content={wh.geopolitical} />
            <IntelSection title="Investor Sentiment" content={wh.investorSentiment} />
            <IntelSection title="Near-Term Outlook" content={wh.nearTermOutlook} />
          </div>

          {/* ZL Implication - highlighted */}
          <div className="mt-2 p-2 rounded-lg bg-slate-800/50 border border-slate-700/50">
            <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">ZL Implication</div>
            <div className="text-[11px] text-slate-200">{wh.zlImplication}</div>
          </div>
        </div>
      )}
    </div>
  )
}

function IntelSection({ title, content }: { title: string; content: string }) {
  return (
    <div>
      <div className="text-[9px] text-slate-500 uppercase tracking-wider">{title}</div>
      <div className="text-[10px] text-slate-400 leading-snug">{content}</div>
    </div>
  )
}

// =============================================================================
// COMPREHENSIVE REPORT SECTION (Institutional Grade)
// Renders full Opus 4.5 analysis with expandable sections
// =============================================================================

function ComprehensiveReportSection({ report }: { report: ComprehensiveReport }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="mt-4 border-t border-slate-800 pt-4">
      {/* TL;DR - Always visible */}
      <div className="mb-3">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-1 h-4 bg-cyan-500 rounded-full" />
          <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider">TL;DR</span>
        </div>
        <p className="text-[12px] text-slate-300 leading-relaxed">{report.tldr}</p>
      </div>

      {/* Expand/Collapse Button */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-slate-800/60 hover:bg-slate-700/60 border border-slate-700/50 transition-all text-[10px] font-medium text-slate-400 hover:text-slate-200"
      >
        <span>{expanded ? '▼' : '▶'}</span>
        <span>{expanded ? 'Hide Full Analysis' : 'Show Full Institutional Analysis'}</span>
        <span className="px-1.5 py-0.5 rounded text-[8px] bg-violet-500/20 text-violet-400 ml-1">OPUS 4.5</span>
      </button>

      {/* Expanded Sections */}
      {expanded && (
        <div className="mt-4 space-y-4 animate-in slide-in-from-top-2 duration-300">
          {/* Current Snapshot */}
          <ReportSection
            title="Current Market Snapshot"
            content={report.currentSnapshot}
            icon="📊"
            color="slate"
          />

          {/* Key Drivers */}
          <ReportSection
            title="Key Drivers Analysis"
            content={report.keyDrivers}
            icon="⚡"
            color="amber"
          />

          {/* Forecasts */}
          <ReportSection
            title="Time-Horizon Forecasts"
            content={report.forecasts}
            icon="📈"
            color="green"
          />

          {/* Correlations */}
          <ReportSection
            title="Correlation Summary"
            content={report.correlations}
            icon="🔗"
            color="blue"
          />

          {/* Technical Outlook */}
          <ReportSection
            title="Technical Outlook"
            content={report.technicalOutlook}
            icon="📉"
            color="purple"
          />
        </div>
      )}
    </div>
  )
}

function ReportSection({
  title,
  content,
  icon,
  color
}: {
  title: string
  content: string
  icon: string
  color: 'slate' | 'amber' | 'green' | 'blue' | 'purple'
}) {
  const colorClasses = {
    slate: 'border-slate-600 text-slate-400',
    amber: 'border-amber-600 text-amber-400',
    green: 'border-green-600 text-green-400',
    blue: 'border-cyan-600 text-cyan-400',
    purple: 'border-violet-600 text-violet-400',
  }

  return (
    <div className={`border-l-2 pl-3 ${colorClasses[color]}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-sm">{icon}</span>
        <span className="text-[10px] font-bold uppercase tracking-wider">{title}</span>
      </div>
      <p className="text-[11px] text-slate-300 leading-relaxed whitespace-pre-line">{content}</p>
    </div>
  )
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function ChrisTop4Drivers() {
  const [data, setData] = useState<MarketDriversResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null)

  const fetchDrivers = useCallback(async () => {
    try {
      const res = await fetch('/api/market-drivers')
      if (!res.ok) {
        // Handle timeout (504) or server error (500) gracefully
        const errorText = res.status === 504 ? 'Request timed out - AI analysis takes longer on first load'
          : res.status === 500 ? 'Server error - using fallback data'
          : `HTTP ${res.status}`
        throw new Error(errorText)
      }
      const text = await res.text()
      if (!text) throw new Error('Empty response from server')
      let json
      try {
        json = JSON.parse(text)
      } catch {
        throw new Error('Invalid response format')
      }
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

  const triggerRefresh = useCallback(async () => {
    setRefreshing(true)
    setRefreshMessage(null)
    try {
      const res = await fetch('/api/refresh-drivers', { method: 'POST' })
      const json = await res.json()
      setRefreshMessage(json.message || 'Refresh triggered')
      // Refetch data after a short delay to show updated values
      setTimeout(() => {
        fetchDrivers()
        setRefreshMessage(null)
      }, 3000)
    } catch {
      setRefreshMessage('Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }, [fetchDrivers])

  useEffect(() => {
    fetchDrivers()
    const interval = setInterval(fetchDrivers, 5 * 60 * 1000)
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
        <div className="flex items-center gap-3">
          {refreshMessage && (
            <span className="text-[9px] text-cyan-400 animate-pulse">
              {refreshMessage}
            </span>
          )}
          {lastUpdate && (
            <span className="text-[9px] text-slate-600">
              Updated {lastUpdate}
            </span>
          )}
          <button
            onClick={triggerRefresh}
            disabled={refreshing}
            className={`px-2 py-1 rounded text-[9px] font-medium border transition-all ${
              refreshing
                ? 'bg-slate-800/50 text-slate-500 border-slate-700/50 cursor-wait'
                : 'bg-slate-800/80 hover:bg-slate-700/80 text-slate-400 hover:text-slate-200 border-slate-700/50'
            }`}
            title="Trigger manual data refresh via Inngest"
          >
            {refreshing ? '⟳ Refreshing...' : '⟳ Refresh Data'}
          </button>
        </div>
      </div>

      {/* 4 Driver Cards - Multiple metrics per card for institutional-grade display */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <DriverCard
          label="VIX Stress"
          data={d?.vix_stress ?? null}
          metrics={[
            { key: 'vix_value', label: 'VIX', format: (v) => v?.toFixed(1) ?? '--' },
            { key: 'vix3m_value', label: 'VIX3M', format: (v) => v?.toFixed(1) ?? '--' },
            { key: 'vix_ratio', label: 'VIX/VIX3M', format: (v) => v ? (v > 1 ? `${v.toFixed(2)} (Backwd)` : `${v.toFixed(2)} (Contango)`) : '--' },
            { key: 'ovx_value', label: 'OVX (Oil Vol)', format: (v) => v?.toFixed(1) ?? '--' },
          ]}
          loading={loading}
        />
        <DriverCard
          label="Crush Pressure"
          data={d?.crush_pressure ?? null}
          metrics={[
            { key: 'board_crush_value', label: 'Board Crush', format: (v) => v ? `$${v.toFixed(2)}/bu` : '--' },
            { key: 'oil_share_value', label: 'Oil Share', format: (v) => v !== null ? `${v.toFixed(1)}%` : '--' },
            { key: 'oil_share_5d_change', label: 'Oil Share 5d Δ', format: (v) => v !== null ? `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` : '--' },
          ]}
          loading={loading}
        />
        <DriverCard
          label="China Tension"
          data={d?.china_tension ?? null}
          metrics={[
            { key: 'cny_rate', label: 'CNY/USD', format: (v) => v?.toFixed(2) ?? '--' },
            { key: 'fxi_change_20d', label: 'FXI 20d', format: (v) => v !== null ? `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` : '--' },
            { key: 'fxi_change_5d', label: 'FXI 5d', format: (v) => v !== null ? `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` : '--' },
            { key: 'bdry_change_20d', label: 'BDRY (Shipping)', format: (v) => v !== null ? `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` : '--' },
          ]}
          loading={loading}
        />
        <DriverCard
          label="Tariff Threat"
          data={d?.tariff_threat ?? null}
          metrics={[
            { key: 'tpu_value', label: 'TPU Index', format: (v) => v?.toFixed(0) ?? '--' },
            { key: 'emv_value', label: 'EMV Trade', format: (v) => v?.toFixed(0) ?? '--' },
            { key: 'soy_tariff_news_count', label: 'Soy Tariff News', format: (v) => v !== null ? `${v} articles` : '--' },
          ]}
          loading={loading}
        />
      </div>

      {/* Summary Bar */}
      {data?.summary && (
        <div className="mt-4 flex items-center justify-between text-[10px] text-slate-500 px-2">
          <div>
            Avg Pressure: <span className="font-mono" style={{ color: getScoreColor(data.summary.average_pressure).stroke }}>
              {data.summary.average_pressure}
            </span>
          </div>
          <div>
            Highest: <span className="text-slate-300">{data.summary.highest_pressure?.name}</span>
            {' '}(<span className="font-mono" style={{ color: getScoreColor(data.summary.highest_pressure?.score ?? 0).stroke }}>
              {data.summary.highest_pressure?.score}
            </span>)
          </div>
          <div>
            As of: <span className="text-slate-400">{data.as_of_date}</span>
          </div>
        </div>
      )}

      {/* Market Intelligence Card */}
      {data?.intelligence && (
        <div className="mt-4 bg-[#0a0a0a] border border-white/5 rounded-xl p-4">
          {/* Header with ZL Outlook Badge */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="w-1 h-6 rounded-full" style={{ backgroundColor: data.intelligence.zlColor }} />
              <h4 className="text-sm font-semibold text-white">{data.intelligence.headline}</h4>
              {data.intelligence.aiPowered && (
                <span className="px-1.5 py-0.5 rounded text-[8px] font-bold bg-violet-500/20 text-violet-400 border border-violet-500/30">
                  AI
                </span>
              )}
            </div>
            <span
              className="px-2 py-1 rounded text-[10px] font-bold tracking-wider"
              style={{
                backgroundColor: `${data.intelligence.zlColor}20`,
                color: data.intelligence.zlColor,
                border: `1px solid ${data.intelligence.zlColor}40`
              }}
            >
              ZL {data.intelligence.zlOutlook}
            </span>
          </div>

          {/* Summary Paragraph */}
          <p className="text-[12px] text-slate-400 leading-relaxed mb-3">
            {data.intelligence.summary}
          </p>

          {/* Trading Implication (AI-powered only) */}
          {data.intelligence.tradingImplication && (
            <div className="mb-3 px-3 py-2 rounded-lg bg-slate-800/50 border border-slate-700/50">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider">Trading Implication</span>
              <p className="text-[12px] text-slate-300 mt-0.5">{data.intelligence.tradingImplication}</p>
            </div>
          )}

          {/* Driver Bullets */}
          {data.intelligence.drivers && data.intelligence.drivers.length > 0 && (
          <div className="grid grid-cols-2 gap-2">
            {data.intelligence.drivers.map((driver, idx) => (
              <div key={`${driver.label}-${idx}`} className="flex items-start gap-2 text-[11px]">
                <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold shrink-0 ${
                  driver.outlook === 'BEARISH' || driver.outlook === 'PRESSURE' ? 'bg-red-500/20 text-red-400' :
                  driver.outlook === 'BULLISH' || driver.outlook === 'SUPPORTIVE' || driver.outlook === 'CALM' ? 'bg-green-500/20 text-green-400' :
                  driver.outlook === 'MIXED' || driver.outlook === 'WATCH SUPPLY' ? 'bg-amber-500/20 text-amber-400' :
                  'bg-slate-500/20 text-slate-400'
                }`}>
                  {driver.label}
                </span>
                <span className="text-slate-500">{driver.detail}</span>
              </div>
            ))}
          </div>
          )}

          {/* Comprehensive Report (Institutional Grade) */}
          {data.intelligence.comprehensiveReport && (
            <ComprehensiveReportSection report={data.intelligence.comprehensiveReport} />
          )}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// COMPACT VERSION
// =============================================================================

export function ChrisTop4Compact() {
  const [data, setData] = useState<MarketDriversResponse | null>(null)

  useEffect(() => {
    fetch('/api/market-drivers')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(json => {
        if (json.error) throw new Error(json.error)
        setData(json)
      })
      .catch(console.error)
  }, [])

  const drivers = [
    { label: 'VIX', score: data?.drivers?.vix_stress?.score ?? 0 },
    { label: 'Crush', score: data?.drivers?.crush_pressure?.score ?? 0 },
    { label: 'China', score: data?.drivers?.china_tension?.score ?? 0 },
    { label: 'Tariff', score: data?.drivers?.tariff_threat?.score ?? 0 },
  ]

  return (
    <div className="flex items-center gap-4">
      {drivers.map((d) => (
        <div key={d.label} className="flex items-center gap-1.5">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: getScoreColor(d.score).stroke }}
          />
          <span className="text-[10px] text-slate-500 uppercase">{d.label}</span>
          <span
            className="text-xs font-mono font-bold"
            style={{ color: getScoreColor(d.score).stroke }}
          >
            {Math.round(d.score)}
          </span>
        </div>
      ))}
    </div>
  )
}
