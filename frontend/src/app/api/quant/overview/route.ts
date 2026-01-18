import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

export const dynamic = 'force-dynamic'

type StatsRow = {
  running: number
  completed_7d: number
  failed_7d: number
  last_started_at: string | null
}

type RunRow = {
  run_id: string
  run_name: string | null
  model_type: string
  specialist_name: string | null
  horizon: number | null
  status: string
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

export async function GET() {
  try {
    const [
      statsRows,
      registryTotalRows,
      championTotalRows,
      runningRows,
      recentRows,
      leaderboardRows,
      registryRows,
    ] = await Promise.all([
      query<StatsRow>(`
        SELECT
          COUNT(*) FILTER (WHERE status IN ('running', 'queued', 'in_progress'))::int AS running,
          COUNT(*) FILTER (WHERE status IN ('completed', 'success') AND completed_at >= NOW() - INTERVAL '7 days')::int AS completed_7d,
          COUNT(*) FILTER (WHERE status IN ('failed', 'error') AND started_at >= NOW() - INTERVAL '7 days')::int AS failed_7d,
          MAX(started_at) AS last_started_at
        FROM ops.training_runs
      `),
      query<{ total: number }>(`
        SELECT COUNT(*)::int AS total
        FROM model.model_registry
      `),
      query<{ total: number }>(`
        SELECT COUNT(*)::int AS total
        FROM model.model_registry
        WHERE is_champion = true
      `),
      query<RunRow>(`
        SELECT
          run_id,
          run_name,
          model_type,
          specialist_name,
          horizon::int,
          status,
          started_at,
          completed_at,
          duration_seconds::float8 AS duration_seconds,
          error_message
        FROM ops.training_runs
        WHERE status IN ('running', 'queued', 'in_progress')
        ORDER BY started_at DESC
        LIMIT 10
      `),
      query<RunRow>(`
        SELECT
          run_id,
          run_name,
          model_type,
          specialist_name,
          horizon::int,
          status,
          started_at,
          completed_at,
          duration_seconds::float8 AS duration_seconds,
          error_message
        FROM ops.training_runs
        ORDER BY started_at DESC
        LIMIT 20
      `),
      query<LeaderboardRow>(`
        SELECT
          l.run_id,
          l.model_name,
          l.rank::int,
          l.score_val::float8 AS score_val,
          l.score_test::float8 AS score_test,
          l.fit_time_seconds::float8 AS fit_time_seconds,
          l.pred_time_seconds::float8 AS pred_time_seconds,
          r.model_type,
          r.specialist_name,
          r.horizon::int
        FROM model.model_leaderboard l
        LEFT JOIN ops.training_runs r ON r.run_id = l.run_id
        ORDER BY l.rank ASC NULLS LAST, l.score_val ASC NULLS LAST
        LIMIT 20
      `),
      query<RegistryRow>(`
        SELECT
          model_id,
          model_name,
          model_type,
          horizon::int,
          version::int,
          trained_at,
          status,
          is_champion,
          mase::float8 AS mase,
          rmse::float8 AS rmse,
          mae::float8 AS mae
        FROM model.model_registry
        ORDER BY trained_at DESC
        LIMIT 20
      `),
    ])

    const stats = statsRows[0] || {
      running: 0,
      completed_7d: 0,
      failed_7d: 0,
      last_started_at: null,
    }

    return NextResponse.json({
      stats: {
        running: stats.running ?? 0,
        completed_7d: stats.completed_7d ?? 0,
        failed_7d: stats.failed_7d ?? 0,
        last_started_at: stats.last_started_at ?? null,
        registry_total: registryTotalRows[0]?.total ?? 0,
        champion_total: championTotalRows[0]?.total ?? 0,
      },
      running: runningRows ?? [],
      recent: recentRows ?? [],
      leaderboard: leaderboardRows ?? [],
      registry: registryRows ?? [],
    })
  } catch (error) {
    console.error('Quant overview query failed:', error)
    return NextResponse.json({ error: 'Quant overview query failed' }, { status: 500 })
  }
}
