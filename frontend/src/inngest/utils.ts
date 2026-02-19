/**
 * Shared Inngest Job Utilities
 *
 * Extracts common patterns used across 45+ ingestion jobs:
 * - Row hash computation (idempotency)
 * - Ingest run lifecycle (create/finalize)
 * - Pool client helpers
 * - Data normalization
 *
 * IMPORTANT: All DB operations use pool.connect()/release() inside step.run()
 * closures to prevent stale connections across Inngest durable execution boundaries.
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.0.0
 * @date 2026-02-18
 */

import { createHash } from "crypto";
import type { Pool, PoolClient } from "pg";

// =============================================================================
// ROW HASH — idempotency key for append-only ingestion
// =============================================================================

/**
 * Compute SHA-256 hash from a JSON payload (object).
 * Used by: cftc-weekly, profarmer-daily, eia-biodiesel-monthly, etc.
 */
export function hashPayload(payload: Record<string, unknown>): string {
	return createHash("sha256").update(JSON.stringify(payload)).digest("hex");
}

/**
 * Compute SHA-256 hash from pipe-delimited fields.
 * Used by: nyfed-daily, fx-spot-daily, epa-rin-prices-daily, etc.
 */
export function hashFields(...fields: (string | number | boolean | null | undefined)[]): string {
	return createHash("sha256")
		.update(fields.map((f) => String(f ?? "")).join("|"))
		.digest("hex");
}

// =============================================================================
// INGEST RUN LIFECYCLE — ops.ingest_run tracking
// =============================================================================

/**
 * Create an ingest run record and return its ID.
 *
 * Usage inside step.run():
 *   const runId = await step.run("create-ingest-run", async () => {
 *     return createIngestRun(pool, "my-job-name");
 *   });
 */
export async function createIngestRun(pool: Pool, jobName: string): Promise<string> {
	const client = await pool.connect();
	try {
		const result = await client.query(
			`INSERT INTO ops.ingest_run (job_name, status, started_at)
       VALUES ($1, 'running', NOW()) RETURNING id`,
			[jobName],
		);
		return result.rows[0].id as string;
	} finally {
		client.release();
	}
}

/** Counters for finalizing an ingest run. */
export interface IngestRunSummary {
	status: "success" | "error" | "partial" | "timeout";
	rowsAttempted: number;
	rowsInserted: number;
	rowsSkipped?: number;
	rowsQuarantined?: number;
	errorMessage?: string;
}

/**
 * Finalize an ingest run with status and counters.
 *
 * Usage inside step.run():
 *   await step.run("finalize-ingest-run", async () => {
 *     await finalizeIngestRun(pool, runId, {
 *       status: "success",
 *       rowsAttempted: 100,
 *       rowsInserted: 95,
 *       rowsSkipped: 5,
 *     });
 *   });
 */
export async function finalizeIngestRun(
	pool: Pool,
	runId: string,
	summary: IngestRunSummary,
): Promise<void> {
	const client = await pool.connect();
	try {
		await client.query(
			`UPDATE ops.ingest_run
       SET status = $2,
           completed_at = NOW(),
           rows_attempted = $3,
           rows_inserted = $4,
           rows_skipped = $5,
           rows_quarantined = $6
       WHERE id = $1`,
			[
				runId,
				summary.status,
				summary.rowsAttempted,
				summary.rowsInserted,
				summary.rowsSkipped ?? 0,
				summary.rowsQuarantined ?? 0,
			],
		);
	} finally {
		client.release();
	}
}

/**
 * Mark an ingest run as failed with an error message.
 * Convenience wrapper for the common error-finalization pattern.
 */
export async function failIngestRun(
	pool: Pool,
	runId: string,
	error: unknown,
): Promise<void> {
	const message = error instanceof Error ? error.message : String(error);
	const client = await pool.connect();
	try {
		await client.query(
			`UPDATE ops.ingest_run
       SET status = 'error',
           completed_at = NOW(),
           error_message = $2
       WHERE id = $1`,
			[runId, message.slice(0, 2000)],
		);
	} finally {
		client.release();
	}
}

// =============================================================================
// POOL CLIENT HELPER
// =============================================================================

/**
 * Execute a function with an auto-releasing pool client.
 *
 * Usage:
 *   const rows = await withClient(pool, async (client) => {
 *     const res = await client.query("SELECT 1");
 *     return res.rows;
 *   });
 */
export async function withClient<T>(
	pool: Pool,
	fn: (client: PoolClient) => Promise<T>,
): Promise<T> {
	const client = await pool.connect();
	try {
		return await fn(client);
	} finally {
		client.release();
	}
}

// =============================================================================
// DATA NORMALIZATION — common parsing helpers
// =============================================================================

/**
 * Normalize whitespace: collapse \r, \n, and multiple spaces to single space.
 * Used by: usda-wasde-monthly, argentina-crush-monthly, conab-production-monthly, etc.
 */
export function normalizeWhitespace(value: string): string {
	return value.replace(/\r/g, " ").replace(/\n/g, " ").replace(/\s+/g, " ").trim();
}

/**
 * Parse ISO datetime string to YYYY-MM-DD date.
 * Used by: fred-daily, eia-today, usda-press, etc.
 */
export function parseIsoDate(isoDateTime: string): string {
	const match = /^(\d{4}-\d{2}-\d{2})/.exec(isoDateTime);
	if (!match) {
		throw new Error(`Unexpected datetime format: ${JSON.stringify(isoDateTime)}`);
	}
	return match[1];
}

/**
 * Strict float parsing with NaN/Infinity rejection.
 * Used by: conab-production-monthly, argentina-crush-monthly, etc.
 */
export function parseFloatStrict(value: string): number {
	const trimmed = value.trim();
	const num = Number(trimmed);
	if (!Number.isFinite(num)) {
		throw new Error(`Non-numeric value: ${JSON.stringify(value)}`);
	}
	return num;
}
