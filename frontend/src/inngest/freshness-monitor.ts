/**
 * Data Freshness Monitor
 *
 * Runs daily and checks for stale data across the most critical pipeline tables.
 * Writes an alert row to ops.pipeline_alerts for each source that is stale beyond
 * its expected SLA.
 *
 * Static table references (for sql-table-contract hook):
 *   training.specialist_signals_1d
 *   training.specialist_features_trump_effect
 *   mkt.futures_1d
 *   mkt.fx_1d
 *   analytics.price_1d
 *   analytics.latest_price
 *   analytics.board_crush_1d
 *   econ.vol_indices_1d
 *   pos.cftc_1w
 *   ops.ingest_run
 *   ops.pipeline_alerts
 */

import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

interface SlaCheck {
	name: string;
	query: string;
	maxStaleDays: number;
}

const SPECIALIST_BUCKET_SLAS: Array<{ bucket: string; maxStaleDays: number }> = [
	{ bucket: "crush", maxStaleDays: 3 },
	{ bucket: "china", maxStaleDays: 3 },
	{ bucket: "fx", maxStaleDays: 3 },
	{ bucket: "fed", maxStaleDays: 3 },
	{ bucket: "tariff", maxStaleDays: 3 },
	{ bucket: "energy", maxStaleDays: 3 },
	{ bucket: "biofuel", maxStaleDays: 3 },
	{ bucket: "palm", maxStaleDays: 3 },
	{ bucket: "volatility", maxStaleDays: 3 },
	{ bucket: "substitutes", maxStaleDays: 3 },
	{ bucket: "trump_effect", maxStaleDays: 7 },
];

// SLA thresholds — how many calendar days behind is acceptable.
const SLA_CHECKS: SlaCheck[] = [
	// Dashboard price tables (most critical — directly visible to users)
	{
		name: "analytics_price_1d_zl",
		query: `SELECT CURRENT_DATE - MAX(event_date)::date AS days_stale
		        FROM analytics.price_1d`,
		maxStaleDays: 1, // Daily bar should arrive by 06:05 CT every trading day
	},
	{
		name: "analytics_latest_price",
		query: `SELECT COALESCE(
		          EXTRACT(epoch FROM (NOW() - MAX(updated_at))) / 86400,
		          999
		        )::int AS days_stale
		        FROM analytics.latest_price
		        WHERE id = 1`,
		maxStaleDays: 1, // Updated by every live feed; should never be >1 day stale
	},
	// Specialist signals
	{
		name: "specialist_signals_any_bucket",
		query: `SELECT CURRENT_DATE - MAX(as_of_date)::date AS days_stale
		        FROM training.specialist_signals_1d`,
		maxStaleDays: 3,
	},
	...SPECIALIST_BUCKET_SLAS.map(({ bucket, maxStaleDays }) => ({
		name: `specialist_signal_${bucket}`,
		query: `SELECT CURRENT_DATE - MAX(as_of_date)::date AS days_stale
		        FROM training.specialist_signals_1d
		        WHERE bucket = '${bucket}'`,
		maxStaleDays,
	})),
	{
		name: "futures_zl_daily",
		query: `SELECT CURRENT_DATE - MAX(event_date)::date AS days_stale
		        FROM mkt.futures_1d
		        WHERE symbol = 'ZL'`,
		maxStaleDays: 3,
	},
	{
		name: "ingest_run_recent_success",
		query: `SELECT COALESCE(
		          EXTRACT(epoch FROM (NOW() - MAX(completed_at))) / 86400,
		          999
		        )::int AS days_stale
		        FROM ops.ingest_run
		        WHERE status = 'success'`,
		maxStaleDays: 2,
	},
	{
		name: "trump_effect_producer_recent_success",
		query: `SELECT CASE
		          WHEN NOT EXISTS (
		            SELECT 1
		            FROM ops.ingest_run
		            WHERE job_name = 'trump_effect_feature_refresh'
		              AND status = 'success'
		              AND completed_at IS NOT NULL
		          ) THEN 999
		          WHEN (
		            EXTRACT(
		              epoch FROM (
		                NOW() - (
		                  SELECT MAX(completed_at)
		                  FROM ops.ingest_run
		                  WHERE job_name = 'trump_effect_feature_refresh'
		                    AND status = 'success'
		                    AND completed_at IS NOT NULL
		                )
		              )
		            ) > (
		              (
		                36 +
		                CASE
		                  WHEN EXTRACT(DOW FROM NOW())::int IN (0, 1) THEN 48
		                  ELSE 0
		                END
		              ) * 3600
		            )
		          ) THEN 999
		          ELSE 0
		        END::int AS days_stale`,
		maxStaleDays: 0,
	},
	// ── Driver-specific freshness checks (added 2026-02-23) ──
	// Trade Policy Uncertainty — MONTHLY FRED series (USEPUINDXM)
	{
		name: "tpu_usepuindxm",
		query: `SELECT CURRENT_DATE - MAX(event_date)::date AS days_stale
		        FROM econ.vol_indices_1d
		        WHERE series_id = 'USEPUINDXM' AND value IS NOT NULL`,
		maxStaleDays: 45, // Monthly series: 30 days + 15 day publication lag
	},
	// Trade Policy Uncertainty — DAILY FRED series (USEPUINDXD)
	{
		name: "tpu_usepuindxd",
		query: `SELECT CURRENT_DATE - MAX(event_date)::date AS days_stale
		        FROM econ.vol_indices_1d
		        WHERE series_id = 'USEPUINDXD' AND value IS NOT NULL`,
		maxStaleDays: 7, // Daily series — 7+ days means ingestion is broken
	},
	// CNY/USD exchange rate (business-day cadence from FRED DEXCHUS)
	{
		name: "fx_cny_usd",
		query: `SELECT CURRENT_DATE - MAX(event_date)::date AS days_stale
		        FROM mkt.fx_1d
		        WHERE pair IN ('CNY/USD', 'USDCNY') AND rate IS NOT NULL`,
		maxStaleDays: 5, // Business days only, but 5+ calendar days = stale
	},
	// Board Crush spread (depends on ZS/ZL/ZM daily closes)
	{
		name: "board_crush_1d",
		query: `SELECT CURRENT_DATE - MAX(trade_date)::date AS days_stale
		        FROM analytics.board_crush_1d
		        WHERE board_crush IS NOT NULL`,
		maxStaleDays: 5, // Trading-day cadence, 5 calendar days = stale
	},
	// CFTC COT data (weekly Friday release)
	{
		name: "cftc_cot_zl",
		query: `SELECT CURRENT_DATE - MAX(event_date)::date AS days_stale
		        FROM pos.cftc_1w
		        WHERE symbol = 'ZL'`,
		maxStaleDays: 10, // Weekly: 7 days + 3 day buffer for holidays
	},
	// Trump Effect specialist features (populated by Python pipeline)
	{
		name: "trump_effect_features_table_exists",
		query: `SELECT CASE
		          WHEN to_regclass('training.specialist_features_trump_effect') IS NULL THEN 999
		          ELSE 0
		        END::int AS days_stale`,
		maxStaleDays: 0,
	},
	{
		name: "trump_effect_features",
		query: `SELECT CURRENT_DATE - MAX(as_of_date)::date AS days_stale
		        FROM training.specialist_features_trump_effect
		        WHERE features IS NOT NULL
		          AND features->>'weighted_action_score' IS NOT NULL`,
		maxStaleDays: 7, // Python pipeline should run at least weekly
	},
	{
		name: "trump_effect_features_contract",
		query: `SELECT CASE
		          WHEN to_regclass('training.specialist_features_trump_effect') IS NULL THEN 999
		          WHEN EXISTS (
		            SELECT 1
		            FROM training.specialist_features_trump_effect
		            WHERE NOT (
		              features ? 'weighted_action_score'
		              AND features ? 'action_velocity'
		              AND features ? 'action_acceleration'
		              AND features ? 'total_actions_7d'
		              AND features ? 'total_actions_30d'
		              AND features ? 'eo_count_7d'
		              AND features ? 'proclamation_count_7d'
		              AND features ? 'memorandum_count_7d'
		              AND features ? 'nomination_count_7d'
		              AND features ? 'avg_sentiment_7d'
		              AND features ? 'avg_sentiment_30d'
		              AND features ? 'neural_signal'
		              AND features ? 'neural_confidence'
		              AND features ? 'epu_7d'
		            )
		            OR (
		              features ? 'weighted_action_score'
		              AND COALESCE(NULLIF(features->>'weighted_action_score', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'action_velocity'
		              AND COALESCE(NULLIF(features->>'action_velocity', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'action_acceleration'
		              AND COALESCE(NULLIF(features->>'action_acceleration', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'total_actions_7d'
		              AND COALESCE(NULLIF(features->>'total_actions_7d', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'total_actions_30d'
		              AND COALESCE(NULLIF(features->>'total_actions_30d', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'eo_count_7d'
		              AND COALESCE(NULLIF(features->>'eo_count_7d', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'proclamation_count_7d'
		              AND COALESCE(NULLIF(features->>'proclamation_count_7d', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'memorandum_count_7d'
		              AND COALESCE(NULLIF(features->>'memorandum_count_7d', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'nomination_count_7d'
		              AND COALESCE(NULLIF(features->>'nomination_count_7d', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'avg_sentiment_7d'
		              AND COALESCE(NULLIF(features->>'avg_sentiment_7d', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'avg_sentiment_30d'
		              AND COALESCE(NULLIF(features->>'avg_sentiment_30d', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'neural_signal'
		              AND COALESCE(NULLIF(features->>'neural_signal', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'neural_confidence'
		              AND COALESCE(NULLIF(features->>'neural_confidence', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		            OR (
		              features ? 'epu_7d'
		              AND COALESCE(NULLIF(features->>'epu_7d', ''), '__EMPTY__') !~ '^-?[0-9]+(\\.[0-9]+)?$'
		            )
		          ) THEN 999
		          ELSE 0
		        END::int AS days_stale`,
		maxStaleDays: 0,
	},
	{
		name: "trump_effect_unavailable_persistent",
		query: `SELECT CASE
		          WHEN to_regclass('training.specialist_features_trump_effect') IS NULL THEN 999
		          WHEN (
		            NOT EXISTS (
		              SELECT 1
		              FROM training.specialist_features_trump_effect
		              WHERE as_of_date >= CURRENT_DATE - INTERVAL '14 days'
		                AND features ? 'weighted_action_score'
		                AND features ? 'action_velocity'
		                AND features ? 'action_acceleration'
		                AND features ? 'total_actions_7d'
		                AND features ? 'total_actions_30d'
		                AND features ? 'eo_count_7d'
		                AND features ? 'proclamation_count_7d'
		                AND features ? 'memorandum_count_7d'
		                AND features ? 'nomination_count_7d'
		                AND features ? 'avg_sentiment_7d'
		                AND features ? 'avg_sentiment_30d'
		                AND features ? 'neural_signal'
		                AND features ? 'neural_confidence'
		                AND features ? 'epu_7d'
		            )
		            AND NOT EXISTS (
		              SELECT 1
		              FROM training.specialist_signals_1d
		              WHERE bucket = 'trump_effect'
		                AND abstained = false
		                AND as_of_date >= CURRENT_DATE - INTERVAL '14 days'
		            )
		          ) THEN 999
		          ELSE 0
		        END::int AS days_stale`,
		maxStaleDays: 0,
	},
];

interface FreshnessResult {
	name: string;
	days_stale: number;
	max_stale_days: number;
	is_stale: boolean;
}

export const freshnessMonitor = inngest.createFunction(
	{
		id: "freshness-monitor",
		name: "Data Freshness Monitor",
		retries: 1,
		concurrency: [DB_CONCURRENCY],
	},
	{ cron: "TZ=America/Chicago 0 8 * * *" }, // Daily at 08:00 CT (after most ingestion crons)
	async ({ step, logger }) => {
		const results = await step.run("check-freshness", async () => {
			const client = await pool.connect();
			const checks: FreshnessResult[] = [];
			try {
				for (const check of SLA_CHECKS) {
					const res = await client.query<{ days_stale: number | null }>(check.query);
					const dayStale = res.rows[0]?.days_stale ?? 999;
					checks.push({
						name: check.name,
						days_stale: dayStale,
						max_stale_days: check.maxStaleDays,
						is_stale: dayStale > check.maxStaleDays,
					});
				}
			} finally {
				client.release();
			}
			return checks;
		});

		const stale = results.filter((r) => r.is_stale);

		if (stale.length > 0) {
			await step.run("write-alerts", async () => {
				const client = await pool.connect();
				try {
					for (const s of stale) {
						await client.query(
							`INSERT INTO ops.pipeline_alerts
							   (function_id, run_id, error_message, error_name, created_at)
							 VALUES ('freshness-monitor', $1, $2, 'SlaViolation', NOW())
							 ON CONFLICT (run_id) DO NOTHING`,
							[
								`freshness-${s.name}-${new Date().toISOString().split("T")[0]}`,
								`${s.name} is ${s.days_stale} days stale (SLA: ${s.max_stale_days} days)`,
							],
						);
						logger.error(
							{ source: s.name, days_stale: s.days_stale, max_stale_days: s.max_stale_days },
							"Data freshness SLA violation",
						);
					}
				} finally {
					client.release();
				}
			});
		} else {
			logger.info({ checks: results.length }, "All data freshness checks passed");
		}

		return {
			checks: results.length,
			stale_count: stale.length,
			stale_sources: stale.map((s) => s.name),
		};
	},
);
