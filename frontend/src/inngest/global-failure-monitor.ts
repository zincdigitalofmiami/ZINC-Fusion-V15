/**
 * Global Failure Monitor
 *
 * Catches ALL Inngest function failures via the system event `inngest/function.failed`.
 * Fires after a function exhausts all its retries.
 *
 * Writes to ops.pipeline_alerts so failures are visible in SQL without checking the
 * Inngest dashboard manually.
 *
 * Static table references (for sql-table-contract hook):
 *   ops.pipeline_alerts
 */

import { inngest } from "./client";
import { getIngestPool } from "@/lib/db";

const pool = getIngestPool();

export const globalFailureMonitor = inngest.createFunction(
	{ id: "global-failure-monitor", name: "Global Failure Monitor", retries: 1 },
	{ event: "inngest/function.failed" },
	async ({ event, step, logger }) => {
		const { error, function_id, run_id } = event.data as {
			error: { message: string; name?: string; stack?: string };
			function_id: string;
			run_id: string;
		};

		await step.run("log-failure", async () => {
			const client = await pool.connect();
			try {
				await client.query(
					`INSERT INTO ops.pipeline_alerts
					   (function_id, run_id, error_message, error_name, created_at)
					 VALUES ($1, $2, $3, $4, NOW())
					 ON CONFLICT (run_id) DO NOTHING`,
					[function_id, run_id, error.message ?? "unknown", error.name ?? "Error"],
				);
			} finally {
				client.release();
			}

			logger.error(
				{ function_id, run_id, error_name: error.name, error_message: error.message },
				"Pipeline function exhausted all retries",
			);
		});

		return { function_id, run_id };
	},
);
