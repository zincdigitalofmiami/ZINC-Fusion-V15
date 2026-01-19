'use client'

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Clock,
  Crown,
  Database,
  Layers,
  Trophy,
} from 'lucide-react'

type QuantStats = {
  running: number
  completed_7d: number
  failed_7d: number
  last_started_at: string | null
  registry_total: number
  champion_total: number
}

type RunRow = {
  run_id: string
  run_name: string | null
  model_type: string
  specialist_name: string | null
  horizon: number | null
  status: string | null
  started_at: string | null
  completed_at: string | null
  duration_seconds: number | null
  error_message: string | null
}

type LeaderboardRow = {
  run_id: string
  model_name: string
  rank: number | null
  score_val: number | null
  score_test: number | null
  fit_time_seconds: number | null
  pred_time_seconds: number | null
  model_type: string | null
  specialist_name: string | null
  horizon: number | null
}

type RegistryRow = {
  model_id: string
  model_name: string
  model_type: string
  horizon: number | null
  version: number
  trained_at: string
  status: string
  is_champion: boolean
  mase: number | null
  rmse: number | null
  mae: number | null
}

type QuantOverview = {
  stats: QuantStats
  running: RunRow[]
  recent: RunRow[]
  leaderboard: LeaderboardRow[]
  registry: RegistryRow[]
}

const REFRESH_MS = 30000

function formatTimestamp(value?: string | null) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function formatDuration(
  seconds?: number | null,
  startedAt?: string | null,
  completedAt?: string | null
) {
  let totalSeconds = seconds ?? null
  if (totalSeconds === null && startedAt) {
    const start = new Date(startedAt).getTime()
    const end = completedAt ? new Date(completedAt).getTime() : Date.now()
    if (!Number.isNaN(start) && !Number.isNaN(end)) {
      totalSeconds = Math.max(0, Math.round((end - start) / 1000))
    }
  }
  if (totalSeconds === null) return '--'
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const secs = totalSeconds % 60
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m ${secs}s`
  return `${secs}s`
}

function formatNumber(value: number | null | undefined, digits = 4) {
  if (value === null || value === undefined) return '--'
  if (Number.isNaN(value)) return '--'
  return value.toFixed(digits)
}

function formatHorizon(value: number | null | undefined) {
  if (!value) return '--'
  return `${value}d`
}

function statusStyle(status?: string | null) {
  const normalized = (status || '').toLowerCase()
  if (['running', 'queued', 'in_progress'].includes(normalized)) {
    return 'bg-blue-500/10 text-blue-400 border-blue-500/30'
  }
  if (['completed', 'success'].includes(normalized)) {
    return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
  }
  if (['failed', 'error'].includes(normalized)) {
    return 'bg-red-500/10 text-red-400 border-red-500/30'
  }
  return 'bg-slate-500/10 text-slate-400 border-slate-500/30'
}

function truncate(value: string | null | undefined, max = 140) {
  if (!value) return ''
  if (value.length <= max) return value
  return `${value.slice(0, max - 3)}...`
}

export default function QuantPage() {
  const [data, setData] = useState<QuantOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    const load = async () => {
      try {
        const response = await fetch('/api/quant/overview', { cache: 'no-store' })
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const payload = (await response.json()) as QuantOverview
        if (!active) return
        setData(payload)
        setError(null)
        setLastUpdated(new Date().toISOString())
      } catch (err) {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        if (active) setLoading(false)
      }
    }

    load()
    const interval = setInterval(load, REFRESH_MS)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [])

  const stats: QuantStats = useMemo(
    () =>
      data?.stats || {
        running: 0,
        completed_7d: 0,
        failed_7d: 0,
        last_started_at: null,
        registry_total: 0,
        champion_total: 0,
      },
    [data]
  )

  const mlflowUrl = process.env.NEXT_PUBLIC_MLFLOW_UI_URL || 'http://localhost:5000'
  const grafanaUrl = process.env.NEXT_PUBLIC_GRAFANA_URL || 'http://localhost:3000'

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 p-6 pt-36 pb-20">
      <div className="flex flex-col gap-6 mb-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-5xl font-bold text-white tracking-tight">Quant Control</h1>
              <span className="inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.3em] text-blue-400">
                <span className="h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
                Live
              </span>
            </div>
            <p className="text-slate-400 text-sm font-mono mt-2">
              Training telemetry, live runs, and model leaderboard
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <a
              href={mlflowUrl}
              target="_blank"
              rel="noreferrer"
              className="px-3 py-2 rounded-lg border border-white/10 bg-white/5 text-slate-200 hover:text-white hover:border-white/20 transition-colors"
            >
              MLflow UI
            </a>
            <a
              href={grafanaUrl}
              target="_blank"
              rel="noreferrer"
              className="px-3 py-2 rounded-lg border border-white/10 bg-white/5 text-slate-200 hover:text-white hover:border-white/20 transition-colors"
            >
              Grafana
            </a>
            <div className="text-[11px] text-slate-500 font-mono">
              Auto refresh: {Math.round(REFRESH_MS / 1000)}s
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500">
          <span>Last update: {formatTimestamp(lastUpdated)}</span>
          <span>Last run start: {formatTimestamp(stats.last_started_at)}</span>
        </div>

        {error && (
          <div className="border border-red-500/30 bg-red-500/10 text-red-300 text-xs p-3 rounded-lg">
            Quant overview failed to load: {error}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-6 gap-4 mb-10">
        <StatCard
          title="Live Runs"
          value={loading ? '--' : stats.running.toString()}
          icon={<Activity size={18} />}
          accent="text-blue-400"
        />
        <StatCard
          title="Completed 7d"
          value={loading ? '--' : stats.completed_7d.toString()}
          icon={<BarChart3 size={18} />}
          accent="text-emerald-400"
        />
        <StatCard
          title="Failed 7d"
          value={loading ? '--' : stats.failed_7d.toString()}
          icon={<AlertTriangle size={18} />}
          accent="text-red-400"
        />
        <StatCard
          title="Registry Models"
          value={loading ? '--' : stats.registry_total.toString()}
          icon={<Database size={18} />}
          accent="text-slate-300"
        />
        <StatCard
          title="Champions"
          value={loading ? '--' : stats.champion_total.toString()}
          icon={<Crown size={18} />}
          accent="text-amber-400"
        />
        <StatCard
          title="Last Run Start"
          value={loading ? '--' : formatTimestamp(stats.last_started_at)}
          icon={<Clock size={18} />}
          accent="text-slate-300"
          compact
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-8">
        <Panel
          title="Live Training Runs"
          subtitle={`${data?.running?.length || 0} active`}
          icon={<Activity size={16} />}
        >
          <div className="space-y-3">
            {loading ? (
              <EmptyState message="Loading live runs..." />
            ) : data?.running?.length ? (
              data.running.map((run) => (
                <RunRowCard key={run.run_id} run={run} />
              ))
            ) : (
              <EmptyState message="No active training runs." />
            )}
          </div>
        </Panel>

        <Panel
          title="Recent Runs"
          subtitle={`${data?.recent?.length || 0} recent`}
          icon={<Layers size={16} />}
        >
          <div className="space-y-3">
            {loading ? (
              <EmptyState message="Loading recent runs..." />
            ) : data?.recent?.length ? (
              data.recent.map((run) => (
                <div
                  key={run.run_id}
                  className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2"
                >
                  <div>
                    <div className="flex items-center gap-2 text-sm font-semibold text-white">
                      <span className="capitalize">{run.model_type}</span>
                      {run.specialist_name && (
                        <span className="text-[10px] uppercase tracking-widest text-slate-500">
                          {run.specialist_name}
                        </span>
                      )}
                      {run.horizon && (
                        <span className="text-[10px] font-mono text-slate-400">
                          {formatHorizon(run.horizon)}
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-slate-500 font-mono">
                      {run.run_name || run.run_id}
                    </div>
                    {run.error_message && (
                      <div className="text-[11px] text-red-300 mt-1">
                        {truncate(run.error_message, 120)}
                      </div>
                    )}
                  </div>
                  <div className="text-right">
                    <span
                      className={`inline-flex items-center px-2 py-1 rounded border text-[10px] font-semibold uppercase ${statusStyle(
                        run.status
                      )}`}
                    >
                      {run.status || 'unknown'}
                    </span>
                    <div className="text-[11px] text-slate-500 mt-1">
                      {formatDuration(run.duration_seconds, run.started_at, run.completed_at)}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <EmptyState message="No recent runs yet." />
            )}
          </div>
        </Panel>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Panel
          title="Model Leaderboard"
          subtitle="Top 20 validation scores"
          icon={<Trophy size={16} />}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-slate-500 text-[10px] uppercase tracking-widest border-b border-white/5">
                  <th className="text-left py-2">Rank</th>
                  <th className="text-left py-2">Model</th>
                  <th className="text-left py-2">Score Val</th>
                  <th className="text-left py-2">Score Test</th>
                  <th className="text-left py-2">Horizon</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={5} className="py-3 text-slate-500">
                      Loading leaderboard...
                    </td>
                  </tr>
                ) : data?.leaderboard?.length ? (
                  data.leaderboard.map((row) => (
                    <tr key={`${row.run_id}-${row.model_name}`} className="border-b border-white/5">
                      <td className="py-2 text-slate-300">#{row.rank ?? '--'}</td>
                      <td className="py-2">
                        <div className="text-white font-semibold">{row.model_name}</div>
                        <div className="text-[10px] text-slate-500 uppercase tracking-widest">
                          {row.model_type || 'model'}
                          {row.specialist_name ? ` / ${row.specialist_name}` : ''}
                        </div>
                      </td>
                      <td className="py-2 text-slate-300">{formatNumber(row.score_val, 5)}</td>
                      <td className="py-2 text-slate-300">{formatNumber(row.score_test, 5)}</td>
                      <td className="py-2 text-slate-400">{formatHorizon(row.horizon)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="py-3 text-slate-500">
                      No leaderboard entries yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel
          title="Model Registry"
          subtitle="Latest trained models"
          icon={<Database size={16} />}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-slate-500 text-[10px] uppercase tracking-widest border-b border-white/5">
                  <th className="text-left py-2">Model</th>
                  <th className="text-left py-2">Version</th>
                  <th className="text-left py-2">Status</th>
                  <th className="text-left py-2">MAE</th>
                  <th className="text-left py-2">Trained</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={5} className="py-3 text-slate-500">
                      Loading registry...
                    </td>
                  </tr>
                ) : data?.registry?.length ? (
                  data.registry.map((row) => (
                    <tr key={`${row.model_id}-${row.version}`} className="border-b border-white/5">
                      <td className="py-2">
                        <div className="text-white font-semibold">{row.model_name}</div>
                        <div className="text-[10px] text-slate-500 uppercase tracking-widest">
                          {row.model_type} {row.horizon ? ` / ${formatHorizon(row.horizon)}` : ''}
                        </div>
                      </td>
                      <td className="py-2 text-slate-300">v{row.version}</td>
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <span
                            className={`inline-flex items-center px-2 py-1 rounded border text-[10px] font-semibold uppercase ${statusStyle(
                              row.status
                            )}`}
                          >
                            {row.status}
                          </span>
                          {row.is_champion && (
                            <span className="inline-flex items-center gap-1 text-[10px] text-amber-300">
                              <Crown size={12} />
                              Champion
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-2 text-slate-300">{formatNumber(row.mae, 4)}</td>
                      <td className="py-2 text-slate-400">{formatTimestamp(row.trained_at)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="py-3 text-slate-500">
                      No registry entries yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  )
}

function StatCard({
  title,
  value,
  icon,
  accent,
  compact,
}: {
  title: string
  value: string
  icon: ReactNode
  accent: string
  compact?: boolean
}) {
  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-widest text-slate-500">{title}</div>
        <div className={accent}>{icon}</div>
      </div>
      <div className={`mt-3 ${compact ? 'text-sm text-slate-300' : 'text-2xl font-semibold text-white'}`}>
        {value}
      </div>
    </div>
  )
}

function Panel({
  title,
  subtitle,
  icon,
  children,
}: {
  title: string
  subtitle?: string
  icon: ReactNode
  children: ReactNode
}) {
  return (
    <div className="rounded-xl border border-white/5 bg-[#0a0a0a] p-5">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-400">
            {icon}
            {title}
          </div>
          {subtitle && <div className="text-[11px] text-slate-500 mt-1">{subtitle}</div>}
        </div>
      </div>
      {children}
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return <div className="text-[11px] text-slate-500">{message}</div>
}

function RunRowCard({ run }: { run: RunRow }) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between rounded-lg border border-white/5 bg-white/[0.02] px-3 py-3">
      <div>
        <div className="flex items-center gap-2 text-sm font-semibold text-white">
          <span className="capitalize">{run.model_type}</span>
          {run.specialist_name && (
            <span className="text-[10px] uppercase tracking-widest text-slate-500">
              {run.specialist_name}
            </span>
          )}
          {run.horizon && (
            <span className="text-[10px] font-mono text-slate-400">{formatHorizon(run.horizon)}</span>
          )}
        </div>
        <div className="text-[11px] text-slate-500 font-mono">{run.run_name || run.run_id}</div>
        <div className="text-[11px] text-slate-500 mt-1">
          Started: {formatTimestamp(run.started_at)}
        </div>
      </div>
      <div className="text-right">
        <span
          className={`inline-flex items-center px-2 py-1 rounded border text-[10px] font-semibold uppercase ${statusStyle(
            run.status
          )}`}
        >
          {run.status || 'unknown'}
        </span>
        <div className="text-[11px] text-slate-500 mt-1">
          {formatDuration(run.duration_seconds, run.started_at, run.completed_at)}
        </div>
      </div>
    </div>
  )
}
