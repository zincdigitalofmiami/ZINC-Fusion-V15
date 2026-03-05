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
import { getIngestPool } from "@/lib/db";

const pool = getIngestPool();

interface SlaCheck {
	name: string;
	query: string;
	maxStaleDays: number;
}

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
		name: "trump_effect_features",
		query: `SELECT CURRENT_DATE - MAX(as_of_date)::date AS days_stale
		        FROM training.specialist_features_trump_effect
		        WHERE features IS NOT NULL
		          AND features->>'weighted_action_score' IS NOT NULL`,
		maxStaleDays: 7, // Python pipeline should run at least weekly
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
