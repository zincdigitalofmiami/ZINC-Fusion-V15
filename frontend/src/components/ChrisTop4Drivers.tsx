'use client'

import React, { useEffect, useState, useCallback } from 'react'

// =============================================================================
// MARKET RISK FACTORS
// 4 key pressure indicators for soybean oil procurement
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
  dataDate?: string
}

interface ComprehensiveReport {
  tldr: string
  currentSnapshot: string
  keyDrivers: string
  forecasts: string
  correlations: string
  technicalOutlook: string
}

interface IntelligenceData {
  headline: string
  summary: string
  drivers: { label: string; outlook: string; detail: string }[]
  zlOutlook: 'BULLISH' | 'NEUTRAL' | 'CAUTIOUS' | 'BEARISH'
  zlColor: string
  tradingImplication?: string
  comprehensiveReport?: ComprehensiveReport
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
// PROCUREMENT-FRIENDLY LABEL MAPPINGS
// =============================================================================

const DRIVER_NAMES: Record<string, string> = {
  'VIX Stress': 'Market Volatility',
  'Crush Pressure': 'Crush Margins',
  'China Tension': 'China / Trade Risk',
  'Tariff Threat': 'Policy Risk',
}

const LEVEL_LABELS: Record<string, string> = {
  // VIX Stress levels
  'Gap Risk': 'Extreme Risk',
  'Fund Exit': 'High Risk',
  'Spread Widening': 'Elevated',
  'Compressing': 'Very Calm',
  'Risk Off': 'Risk Off',
  'High Alert': 'High Alert',
  'Elevated': 'Elevated',
  'Normal': 'Normal',
  'Calm': 'Calm',
  // Crush Pressure levels
  'Plant Idling': 'Margins Collapsing',
  'Margin Squeeze': 'Margins Squeezed',
  'Max Utilization': 'Strong Margins',
  'Breakeven Risk': 'Breakeven Risk',
  'Comfortable': 'Comfortable',
  'Strong': 'Strong Margins',
  // China Tension levels
  'Monitor Flows': 'Watch Closely',
  'Brazil Favored': 'Low Risk',
  'Brazil Dominates': 'Stable',
  'Trade Diversion': 'Trade Diversion',
  'Active Conflict': 'Active Conflict',
  // Tariff Threat levels
  'Active War': 'Active Trade War',
  'Retaliation Risk': 'High Risk',
  'Elevated Noise': 'Elevated',
  'Background Noise': 'Background',
  'Minimal Threat': 'Quiet',
}

function mapDriverName(name: string): string {
  return DRIVER_NAMES[name] ?? name
}

function mapLevel(level: string): string {
  return LEVEL_LABELS[level] ?? level
}

// =============================================================================
// DYNAMIC COLOR BASED ON SCORE
// =============================================================================

function getScoreColor(score: number): { stroke: string; glow: string } {
  const s = Math.max(0, Math.min(100, score))
  if (s <= 25) return { stroke: '#22C55E', glow: 'rgba(34, 197, 94, 0.5)' }
  if (s <= 40) {
    const t = (s - 25) / 15
    return {
      stroke: `rgb(${Math.round(34 + (234 - 34) * t)}, ${Math.round(197 - (197 - 179) * t)}, ${Math.round(94 - (94 - 8) * t)})`,
      glow: `rgba(${Math.round(34 + (234 - 34) * t)}, ${Math.round(197 - (197 - 179) * t)}, ${Math.round(94 - (94 - 8) * t)}, 0.5)`
    }
  }
  if (s <= 55) return { stroke: '#EAB308', glow: 'rgba(234, 179, 8, 0.5)' }
  if (s <= 70) {
    const t = (s - 55) / 15
    return {
      stroke: `rgb(${Math.round(234 + (239 - 234) * t)}, ${Math.round(179 - (179 - 115) * t)}, ${Math.round(8 + (0 - 8) * t)})`,
      glow: `rgba(${Math.round(234 + (239 - 234) * t)}, ${Math.round(179 - (179 - 115) * t)}, ${Math.round(8 + (0 - 8) * t)}, 0.5)`
    }
  }
  if (s <= 85) return { stroke: '#EF7300', glow: 'rgba(239, 115, 0, 0.5)' }
  return { stroke: '#EF4444', glow: 'rgba(239, 68, 68, 0.6)' }
}

function getScoreTextColor(score: number): string {
  if (score >= 70) return 'text-red-400'
  if (score >= 55) return 'text-orange-400'
  if (score >= 40) return 'text-amber-400'
  return 'text-green-400'
}

// =============================================================================
// HORIZONTAL METER (replaces ArcGauge)
// =============================================================================

function HorizontalMeter({ score }: { score: number }) {
  const percentage = Math.min(Math.max(score, 0), 100)
  const colors = getScoreColor(score)

  return (
    <div className="flex items-center gap-4 w-full">
      <div className="flex-1 h-3 bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{
            width: `${percentage}%`,
            backgroundColor: colors.stroke,
            boxShadow: `0 0 8px ${colors.glow}`,
          }}
        />
      </div>
      <span
        className="text-3xl font-bold tabular-nums min-w-[3ch] text-right"
        style={{ color: colors.stroke }}
      >
        {Math.round(score)}
      </span>
    </div>
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
  metrics: MetricDisplay[]
  loading: boolean
}

function DriverCard({ label, data, metrics, loading }: DriverCardProps) {
  const [expanded, setExpanded] = useState(false)
  const score = data?.score ?? 0
  const level = data?.level ? mapLevel(data.level) : '--'
  const colors = getScoreColor(score)
  const wh = data?.whatsHappening

  const borderStyle = score >= 65
    ? { borderColor: colors.stroke, boxShadow: `0 0 20px ${colors.glow}` }
    : { borderColor: 'rgba(255,255,255,0.08)' }

  return (
    <div
      className="bg-[#0a0a0a] border rounded-2xl p-6 md:p-8 flex flex-col hover:border-white/20 transition-all duration-300"
      style={borderStyle}
    >
      {/* Label */}
      <div className="text-base font-bold text-slate-300 uppercase tracking-wider mb-4 flex items-center gap-2">
        {mapDriverName(label)}
        {data?.aiPowered && (
          <span className="px-1.5 py-0.5 rounded text-xs bg-violet-500/20 text-violet-400">AI</span>
        )}
      </div>

      {/* Horizontal Meter */}
      <div className="w-full mb-2">
        {loading ? (
          <div className="h-3 bg-slate-700/50 rounded-full animate-pulse" />
        ) : (
          <HorizontalMeter score={score} />
        )}
      </div>

      {/* Level */}
      <div className={`text-lg font-medium mt-1 mb-4 ${loading ? 'text-slate-600' : getScoreTextColor(score)}`}>
        {loading ? '...' : level}
      </div>

      {/* Metrics List */}
      <div className="w-full space-y-2 border-t border-white/5 pt-4">
        {metrics.map((metric) => {
          const value = data?.components?.[metric.key] ?? null
          return (
            <div key={metric.key} className="flex justify-between items-center text-sm">
              <span className="text-slate-400">{metric.label}</span>
              <span className="text-slate-200 font-mono">
                {loading ? '--' : metric.format(value)}
              </span>
            </div>
          )
        })}
      </div>

      {/* Headline */}
      <div className="mt-4 text-sm text-slate-300 leading-relaxed min-h-[40px]">
        {loading ? '...' : (data?.headline ?? '--')}
      </div>

      {/* Data Freshness */}
      {!loading && data?.dataDate && (
        <div className="mt-2 text-xs text-slate-500 font-mono">
          Data as of: {data.dataDate}
        </div>
      )}

      {/* What's Happening Button */}
      {wh && !loading && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-4 w-full px-4 py-2 rounded-lg text-sm font-medium bg-slate-800/80 hover:bg-slate-700/80 text-slate-400 hover:text-slate-200 transition-all flex items-center justify-center gap-2 border border-slate-700/50"
        >
          <span>{expanded ? '▼' : '▶'}</span>
          What&apos;s Happening?
        </button>
      )}

      {/* Expanded Intel Panel */}
      {expanded && wh && (
        <div className="mt-4 w-full text-left space-y-3 animate-in slide-in-from-top-2 duration-200">
          <div className="text-sm text-slate-300 leading-relaxed border-l-2 pl-3" style={{ borderColor: colors.stroke }}>
            {wh.whatsHappening}
          </div>
          <div className="space-y-2 pt-1">
            <IntelSection title="Macro Context" content={wh.macroContext} />
            <IntelSection title="Supply & Demand" content={wh.supplyDemand} />
            <IntelSection title="Geopolitical" content={wh.geopolitical} />
            <IntelSection title="Market Sentiment" content={wh.investorSentiment} />
            <IntelSection title="Near-Term Outlook" content={wh.nearTermOutlook} />
          </div>
          <div className="mt-3 p-3 rounded-lg bg-slate-800/50 border border-slate-700/50">
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">What This Means For You</div>
            <div className="text-sm text-slate-200">{wh.zlImplication}</div>
          </div>
        </div>
      )}
    </div>
  )
}

function IntelSection({ title, content }: { title: string; content: string }) {
  return (
    <div>
      <div className="text-xs text-slate-500 uppercase tracking-wider">{title}</div>
      <div className="text-sm text-slate-400 leading-snug">{content}</div>
    </div>
  )
}

// =============================================================================
// COMPREHENSIVE REPORT SECTION
// =============================================================================

function ComprehensiveReportSection({ report }: { report: ComprehensiveReport }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="mt-6 border-t border-slate-800 pt-6">
      <div className="mb-4">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-1 h-4 bg-cyan-500 rounded-full" />
          <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">TL;DR</span>
        </div>
        <p className="text-base text-slate-300 leading-relaxed">{report.tldr}</p>
      </div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-slate-800/60 hover:bg-slate-700/60 border border-slate-700/50 transition-all text-sm font-medium text-slate-400 hover:text-slate-200"
      >
        <span>{expanded ? '▼' : '▶'}</span>
        <span>{expanded ? 'Hide Full Analysis' : 'Show Full Market Analysis'}</span>
        <span className="px-2 py-0.5 rounded text-xs bg-violet-500/20 text-violet-400 ml-1">AI</span>
      </button>
      {expanded && (
        <div className="mt-5 space-y-5 animate-in slide-in-from-top-2 duration-300">
          <ReportSection title="Current Market Snapshot" content={report.currentSnapshot} icon="📊" color="slate" />
          <ReportSection title="Key Drivers Analysis" content={report.keyDrivers} icon="⚡" color="amber" />
          <ReportSection title="Time-Horizon Forecasts" content={report.forecasts} icon="📈" color="green" />
          <ReportSection title="Market Connections" content={report.correlations} icon="🔗" color="blue" />
          <ReportSection title="Key Price Levels" content={report.technicalOutlook} icon="📉" color="purple" />
        </div>
      )}
    </div>
  )
}

function ReportSection({
  title, content, icon, color
}: {
  title: string; content: string; icon: string
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
    <div className={`border-l-2 pl-4 ${colorClasses[color]}`}>
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-sm">{icon}</span>
        <span className="text-xs font-bold uppercase tracking-wider">{title}</span>
      </div>
      <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-line">{content}</p>
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
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2 pl-1 border-l-4 border-cyan-500">
          <h3 className="text-base font-bold text-white uppercase tracking-wider">
            Market Risk Factors
          </h3>
          <span className="px-2 py-0.5 rounded text-xs font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            KEY DRIVERS
          </span>
          {error && (
            <span className="px-2 py-0.5 rounded text-xs font-bold bg-red-500/10 text-red-400 border border-red-500/20">
              ERROR
            </span>
          )}
          {data?.summary?.alert_count && data.summary.alert_count > 0 && (
            <span className="px-2 py-0.5 rounded text-xs font-bold bg-red-500/20 text-red-400 border border-red-500/30 animate-pulse">
              {data.summary.alert_count} ALERT{data.summary.alert_count > 1 ? 'S' : ''}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {refreshMessage && (
            <span className="text-xs text-cyan-400 animate-pulse">{refreshMessage}</span>
          )}
          {lastUpdate && (
            <span className="text-xs text-slate-600">Updated {lastUpdate}</span>
          )}
          <button
            onClick={triggerRefresh}
            disabled={refreshing}
            className={`px-3 py-1.5 rounded text-xs font-medium border transition-all ${
              refreshing
                ? 'bg-slate-800/50 text-slate-500 border-slate-700/50 cursor-wait'
                : 'bg-slate-800/80 hover:bg-slate-700/80 text-slate-400 hover:text-slate-200 border-slate-700/50'
            }`}
          >
            {refreshing ? '⟳ Refreshing...' : '⟳ Refresh Data'}
          </button>
        </div>
      </div>

      {/* 4 Driver Cards — 2-column grid for bigger cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <DriverCard
          label="VIX Stress"
          data={d?.vix_stress ?? null}
          metrics={[
            { key: 'vix_value', label: 'VIX Index', format: (v) => v?.toFixed(1) ?? '--' },
            { key: 'ovx_value', label: 'Oil Volatility (OVX)', format: (v) => v?.toFixed(1) ?? '--' },
          ]}
          loading={loading}
        />
        <DriverCard
          label="Crush Pressure"
          data={d?.crush_pressure ?? null}
          metrics={[
            { key: 'board_crush_value', label: 'Crush Margin', format: (v) => v ? `$${v.toFixed(2)}/bu` : '--' },
            { key: 'oil_share_value', label: 'Oil Value Share', format: (v) => v !== null ? `${v?.toFixed(1)}%` : '--' },
            { key: 'oil_share_5d_change', label: '5-Day Change', format: (v) => v !== null ? `${v! >= 0 ? '+' : ''}${v?.toFixed(1)}%` : '--' },
          ]}
          loading={loading}
        />
        <DriverCard
          label="China Tension"
          data={d?.china_tension ?? null}
          metrics={[
            { key: 'cny_rate', label: 'Yuan Rate (CNY/USD)', format: (v) => v?.toFixed(2) ?? '--' },
            { key: 'soy_china_news_count', label: 'China/Soy Headlines', format: (v) => v !== null ? `${v} this week` : '--' },
          ]}
          loading={loading}
        />
        <DriverCard
          label="Tariff Threat"
          data={d?.tariff_threat ?? null}
          metrics={[
            { key: 'tpu_value', label: 'Policy Uncertainty', format: (v) => v?.toFixed(0) ?? '--' },
            { key: 'emv_value', label: 'Trade Policy Index', format: (v) => v?.toFixed(0) ?? '--' },
            { key: 'soy_tariff_news_count', label: 'Tariff Headlines', format: (v) => v !== null ? `${v} this week` : '--' },
          ]}
          loading={loading}
        />
      </div>

      {/* Summary Bar */}
      {data?.summary && (
        <div className="mt-6 flex items-center justify-between text-sm text-slate-500 px-2">
          <div>
            Average Risk: <span className="font-mono" style={{ color: getScoreColor(data.summary.average_pressure).stroke }}>
              {data.summary.average_pressure}
            </span>
          </div>
          <div>
            Top Concern: <span className="text-slate-300">{mapDriverName(data.summary.highest_pressure?.name ?? '')}</span>
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
        <div className="mt-6 bg-[#0a0a0a] border border-white/5 rounded-2xl p-6 md:p-8">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-1 h-6 rounded-full" style={{ backgroundColor: data.intelligence.zlColor }} />
              <h4 className="text-lg font-semibold text-white">{data.intelligence.headline}</h4>
              {data.intelligence.aiPowered && (
                <span className="px-2 py-0.5 rounded text-xs font-bold bg-violet-500/20 text-violet-400 border border-violet-500/30">
                  AI
                </span>
              )}
            </div>
            <span
              className="px-3 py-1.5 rounded text-xs font-bold tracking-wider"
              style={{
                backgroundColor: `${data.intelligence.zlColor}20`,
                color: data.intelligence.zlColor,
                border: `1px solid ${data.intelligence.zlColor}40`
              }}
            >
              ZL {data.intelligence.zlOutlook}
            </span>
          </div>

          <p className="text-base text-slate-400 leading-relaxed mb-4">
            {data.intelligence.summary}
          </p>

          {data.intelligence.tradingImplication && (
            <div className="mb-4 px-4 py-3 rounded-lg bg-slate-800/50 border border-slate-700/50">
              <span className="text-xs text-slate-500 uppercase tracking-wider">What This Means For You</span>
              <p className="text-base text-slate-300 mt-1">{data.intelligence.tradingImplication}</p>
            </div>
          )}

          {data.intelligence.drivers && data.intelligence.drivers.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {data.intelligence.drivers.map((driver, idx) => (
                <div key={`${driver.label}-${idx}`} className="flex items-start gap-2 text-sm">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold shrink-0 ${
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
    { label: 'Volatility', score: data?.drivers?.vix_stress?.score ?? 0 },
    { label: 'Crush', score: data?.drivers?.crush_pressure?.score ?? 0 },
    { label: 'China', score: data?.drivers?.china_tension?.score ?? 0 },
    { label: 'Policy', score: data?.drivers?.tariff_threat?.score ?? 0 },
  ]

  return (
    <div className="flex items-center gap-4">
      {drivers.map((d) => (
        <div key={d.label} className="flex items-center gap-1.5">
          <div
            className="w-2.5 h-2.5 rounded-full"
            style={{ backgroundColor: getScoreColor(d.score).stroke }}
          />
          <span className="text-xs text-slate-500 uppercase">{d.label}</span>
          <span
            className="text-sm font-mono font-bold"
            style={{ color: getScoreColor(d.score).stroke }}
          >
            {Math.round(d.score)}
          </span>
        </div>
      ))}
    </div>
  )
}
