import { Inngest } from "inngest";

const eventKey = process.env.INNGEST_EVENT_KEY ?? process.env.WORKFLOW_INNGEST_EVENT_KEY;
const signingKey = process.env.INNGEST_SIGNING_KEY ?? process.env.WORKFLOW_INNGEST_SIGNING_KEY;

export const inngest = new Inngest({
	id: "fusion-jobs",
	eventKey,
	signingKey,
});

/**
 * Shared concurrency limit for all DB-touching Inngest functions.
 *
 * Inngest plan allows 5 concurrent function executions.  Each Vercel Lambda
 * gets a pg.Pool with max=2, so 5 × 2 = 10 worst-case connections — well
 * within the 50-connection Postgres ceiling.
 *
 * IMPORTANT: This MUST match the Inngest plan limit.  Setting it higher
 * (e.g. 10) causes cascade failures when the plan rejects excess runs.
 *
 * Scope is "env" (not "account") so preview deploys get their own independent
 * limit and don't compete with production.
 *
 * Usage:  spread into the concurrency array of every createFunction call:
 *   concurrency: [DB_CONCURRENCY, ...otherLimits]
 */
export const DB_CONCURRENCY = {
	scope: "env" as const,
	key: '"db-pool"',
	limit: 5,
};

/**
 * Shared retry policy tiers for Inngest functions.
 *
 * - CRON_INGEST: recurring ingestion jobs pulling external/data sources
 * - EVENT_INGEST: event-driven ingestion/writers with idempotent upserts
 * - MANUAL: operator-triggered jobs (avoid excessive duplicate retries)
 * - MAINTENANCE: housekeeping/monitoring jobs
 */
export const RETRIES = {
	CRON_INGEST: 3,
	EVENT_INGEST: 2,
	MANUAL: 1,
	MAINTENANCE: 1,
} as const;

/**
 * Shared HTTP timeout policy for external calls in Inngest jobs.
 */
export const HTTP_TIMEOUT_MS = {
	STANDARD: 20_000,
	LONG: 30_000,
} as const;
