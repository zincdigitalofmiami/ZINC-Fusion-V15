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
