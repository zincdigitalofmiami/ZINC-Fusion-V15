import { createHash, randomUUID } from "crypto";
import { spawn } from "child_process";
import type { PoolClient } from "pg";

import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;
const LOOKBACK_DAYS = 120;
const TRUMP_PRODUCER_JOB_NAME = "trump_effect_feature_refresh";
const TRUMP_PRODUCER_BASE_SLA_HOURS = Number(
	process.env.TRUMP_PRODUCER_BASE_SLA_HOURS ?? 36,
);
const TRUMP_PRODUCER_WEEKEND_BUFFER_HOURS = Number(
	process.env.TRUMP_PRODUCER_WEEKEND_BUFFER_HOURS ?? 48,
);
const TRUMP_PRODUCER_EXECUTION_MODE =
	process.env.TRUMP_PRODUCER_EXECUTION_MODE ?? "disabled";
const TRUMP_PRODUCER_COMMAND =
	process.env.TRUMP_PRODUCER_COMMAND ??
	"python scripts/refresh_trump_effect_features.py";
const TRUMP_PRODUCER_TIMEOUT_MS = Number(
	process.env.TRUMP_PRODUCER_TIMEOUT_MS ?? 600_000,
);
const PRODUCER_REASON_PATTERN =
	/\[(SOURCE_MISSING|SOURCE_STALE|CONTRACT_FAIL|UNKNOWN_ERROR)\]/;

interface BucketConfig {
	bucket: string;
	featureTable: string;
	modelType: string;
	signalKeys: [string, string];
	confidenceKey: string | null;
	fallbackConfidence: number;
	requiredKeys?: string[];
}

/**
 * All 11 specialist buckets — treated equally.
 *
 * Each bucket has a pre-computed composite signal in its feature table JSONB.
 * This job extracts those composites as a lightweight daily signal sync.
 * Full ML inference is done by the Python scripts/generate_specialist_signals.py.
 *
 * Static table references (for sql-table-contract hook):
 *   training.specialist_features_crush
 *   training.specialist_features_china
 *   training.specialist_features_fx
 *   training.specialist_features_fed
 *   training.specialist_features_tariff
 *   training.specialist_features_energy
 *   training.specialist_features_biofuel
 *   training.specialist_features_palm
 *   training.specialist_features_volatility
 *   training.specialist_features_substitutes
 *   training.specialist_features_trump_effect
 *   training.specialist_signals_1d
 */
const BUCKETS: BucketConfig[] = [
	{
		bucket: "crush",
		featureTable: "training.specialist_features_crush",
		modelType: "gbm",
		signalKeys: ["crush_bucket_signal", "oil_share_zscore"],
		confidenceKey: "crush_bucket_confidence",
		fallbackConfidence: 0.6,
	},
	{
		bucket: "china",
		featureTable: "training.specialist_features_china",
		modelType: "gbm",
		signalKeys: ["china_bucket_signal", "cny_zscore"],
		confidenceKey: "china_bucket_confidence",
		fallbackConfidence: 0.5,
	},
	{
		bucket: "fx",
		featureTable: "training.specialist_features_fx",
		modelType: "ardl",
		signalKeys: ["fx_bucket_signal", "dxy_zscore"],
		confidenceKey: "fx_signal_strength",
		fallbackConfidence: 0.5,
	},
	{
		bucket: "fed",
		featureTable: "training.specialist_features_fed",
		modelType: "ridge",
		signalKeys: ["fed_bucket_signal", "yield_curve_zscore"],
		confidenceKey: "fed_signal_strength",
		fallbackConfidence: 0.5,
	},
	{
		bucket: "tariff",
		featureTable: "training.specialist_features_tariff",
		modelType: "tree",
		signalKeys: ["tariff_bucket_signal", "epu_zscore"],
		confidenceKey: "tariff_signal_strength",
		fallbackConfidence: 0.5,
	},
	{
		bucket: "energy",
		featureTable: "training.specialist_features_energy",
		modelType: "var",
		signalKeys: ["energy_bucket_signal", "boho_zscore"],
		confidenceKey: "energy_bucket_confidence",
		fallbackConfidence: 0.5,
	},
	{
		bucket: "biofuel",
		featureTable: "training.specialist_features_biofuel",
		modelType: "nlp_ema",
		signalKeys: ["biofuel_bucket_signal", "rin_d4_zscore"],
		confidenceKey: "biofuel_bucket_confidence",
		fallbackConfidence: 0.5,
	},
	{
		bucket: "palm",
		featureTable: "training.specialist_features_palm",
		modelType: "ridge",
		signalKeys: ["palm_zscore", "zl_palm_spread_zscore"],
		confidenceKey: "palm_bucket_confidence",
		fallbackConfidence: 0.5,
	},
	{
		bucket: "volatility",
		featureTable: "training.specialist_features_volatility",
		modelType: "garch",
		signalKeys: ["vol_bucket_signal", "vix_zscore"],
		confidenceKey: "vol_bucket_confidence",
		fallbackConfidence: 0.7,
	},
	{
		bucket: "substitutes",
		featureTable: "training.specialist_features_substitutes",
		modelType: "rf",
		signalKeys: ["substitutes_bucket_signal", "canola_zscore"],
		confidenceKey: "substitutes_signal_strength",
		fallbackConfidence: 0.5,
	},
	{
		bucket: "trump_effect",
		featureTable: "training.specialist_features_trump_effect",
		modelType: "event_study",
		signalKeys: ["neural_signal", "weighted_action_score"],
		confidenceKey: "neural_confidence",
		fallbackConfidence: 0.5,
		requiredKeys: [
			"weighted_action_score",
			"action_velocity",
			"action_acceleration",
			"total_actions_7d",
			"total_actions_30d",
			"eo_count_7d",
			"proclamation_count_7d",
			"memorandum_count_7d",
			"nomination_count_7d",
			"avg_sentiment_7d",
			"avg_sentiment_30d",
			"neural_signal",
			"neural_confidence",
			"epu_7d",
		],
	},
];

function clamp(v: number, min: number, max: number): number {
	return Math.min(max, Math.max(min, v));
}

function toDateKey(v: Date | string): string {
	const d = v instanceof Date ? v : new Date(v);
	return d.toISOString().split("T")[0];
}

function safeNum(raw: unknown, fallback: number): number {
	if (raw == null || raw === "") return fallback;
	const n = Number(raw);
	return Number.isFinite(n) ? n : fallback;
}

function isNumericLike(raw: unknown): boolean {
	if (raw == null || raw === "") return false;
	const n = Number(raw);
	return Number.isFinite(n);
}

interface SyncResult {
	status: string;
	synced: number;
	latest_date?: string | null;
	reason?: string;
	reason_code?: string;
	error?: string;
}

interface ProducerGuardResult {
	ok: boolean;
	reason_code: string | null;
	reason: string;
	producer_completed_at: string | null;
	producer_age_hours: number | null;
	max_age_hours: number;
	producer_last_status: string | null;
	producer_last_reason_code: string | null;
	producer_last_completed_at: string | null;
}

interface ProducerRunAttempt {
	attempted: boolean;
	status: "skipped" | "success" | "error" | "timeout";
	execution_mode: string;
	exit_code: number | null;
	duration_ms: number;
	reason_code: string | null;
	stdout_tail: string;
	stderr_tail: string;
}

function tailText(input: string, maxChars = 2_000): string {
	return input.length <= maxChars ? input : input.slice(input.length - maxChars);
}

function parseProducerReasonCode(stdout: string, stderr: string): string | null {
	const merged = `${stdout}\n${stderr}`;
	const match = PRODUCER_REASON_PATTERN.exec(merged);
	return match?.[1] ?? null;
}

async function getDbFingerprint(client: PoolClient): Promise<{
	database: string;
	schema: string;
	host: string | null;
	port: number | null;
}> {
	const result = await client.query<{
		database: string;
		schema: string;
		host: string | null;
		port: number | null;
	}>(
		`SELECT
		   current_database()::text AS database,
		   current_schema()::text AS schema,
		   inet_server_addr()::text AS host,
		   inet_server_port()::int AS port`,
	);
	return (
		result.rows[0] ?? {
			database: "unknown",
			schema: "unknown",
			host: null,
			port: null,
		}
	);
}

function getTrumpProducerMaxAgeHours(now: Date): number {
	// Calendar buffer avoids false-negatives around weekend and holiday windows.
	const weekday = now.getUTCDay(); // Sun=0 ... Sat=6
	const weekendBuffer =
		weekday === 0 || weekday === 1 ? TRUMP_PRODUCER_WEEKEND_BUFFER_HOURS : 0;
	return TRUMP_PRODUCER_BASE_SLA_HOURS + weekendBuffer;
}

async function checkTrumpProducerRun(
	client: PoolClient,
	now: Date = new Date(),
): Promise<ProducerGuardResult> {
	const maxAgeHours = getTrumpProducerMaxAgeHours(now);
	const [runResult, latestRunResult] = await Promise.all([
		client.query<{ completed_at: string | null }>(
			`SELECT completed_at::text
			 FROM ops.ingest_run
			 WHERE job_name = $1
			   AND status = 'success'
			   AND completed_at IS NOT NULL
			 ORDER BY completed_at DESC
			 LIMIT 1`,
			[TRUMP_PRODUCER_JOB_NAME],
		),
		client.query<{
			status: string | null;
			completed_at: string | null;
			reason_code: string | null;
		}>(
			`SELECT status::text,
			        completed_at::text,
			        COALESCE(cursor_position->>'reason_code', NULL)::text AS reason_code
			 FROM ops.ingest_run
			 WHERE job_name = $1
			 ORDER BY COALESCE(completed_at, started_at) DESC
			 LIMIT 1`,
			[TRUMP_PRODUCER_JOB_NAME],
		),
	]);

	const latestRun = latestRunResult.rows[0];
	const latestRunStatus = latestRun?.status ?? null;
	const latestRunReasonCode = latestRun?.reason_code ?? null;
	const latestRunCompletedAt = latestRun?.completed_at ?? null;

	const completedAt = runResult.rows[0]?.completed_at ?? null;
	if (!completedAt) {
		return {
			ok: false,
			reason_code: latestRunReasonCode ?? "PRODUCER_RUN_MISSING",
			reason: latestRunReasonCode
				? `No successful ${TRUMP_PRODUCER_JOB_NAME} run found; latest producer reason: ${latestRunReasonCode}.`
				: `No successful ${TRUMP_PRODUCER_JOB_NAME} run found.`,
			producer_completed_at: null,
			producer_age_hours: null,
			max_age_hours: maxAgeHours,
			producer_last_status: latestRunStatus,
			producer_last_reason_code: latestRunReasonCode,
			producer_last_completed_at: latestRunCompletedAt,
		};
	}

	const ageHours = Math.max(
		0,
		(now.getTime() - new Date(completedAt).getTime()) / 3_600_000,
	);
	if (ageHours > maxAgeHours) {
		return {
			ok: false,
			reason_code: latestRunReasonCode ?? "PRODUCER_RUN_STALE",
			reason:
				`Latest successful ${TRUMP_PRODUCER_JOB_NAME} run is ${ageHours.toFixed(1)}h old ` +
				`(max ${maxAgeHours}h with calendar buffer).`,
			producer_completed_at: completedAt,
			producer_age_hours: Number(ageHours.toFixed(2)),
			max_age_hours: maxAgeHours,
			producer_last_status: latestRunStatus,
			producer_last_reason_code: latestRunReasonCode,
			producer_last_completed_at: latestRunCompletedAt,
		};
	}

	return {
		ok: true,
		reason_code: null,
		reason: "Producer SLA satisfied.",
		producer_completed_at: completedAt,
		producer_age_hours: Number(ageHours.toFixed(2)),
		max_age_hours: maxAgeHours,
		producer_last_status: latestRunStatus,
		producer_last_reason_code: latestRunReasonCode,
		producer_last_completed_at: latestRunCompletedAt,
	};
}

async function runTrumpProducer(): Promise<ProducerRunAttempt> {
	if (TRUMP_PRODUCER_EXECUTION_MODE !== "subprocess") {
		return {
			attempted: false,
			status: "skipped",
			execution_mode: TRUMP_PRODUCER_EXECUTION_MODE,
			exit_code: null,
			duration_ms: 0,
			reason_code: "PRODUCER_EXECUTION_DISABLED",
			stdout_tail: "",
			stderr_tail: "",
		};
	}

	const startedAt = Date.now();
	return new Promise<ProducerRunAttempt>((resolve) => {
		let stdout = "";
		let stderr = "";
		let settled = false;
		let timedOut = false;

		const finalize = (result: ProducerRunAttempt) => {
			if (settled) return;
			settled = true;
			resolve(result);
		};

		const child = spawn(
			"bash",
			[
				"-lc",
				`source scripts/load_db_env.sh; load_db_env; ${TRUMP_PRODUCER_COMMAND}`,
			],
			{
				cwd: process.cwd(),
				env: process.env,
			},
		);

		const timeout = setTimeout(() => {
			timedOut = true;
			child.kill("SIGTERM");
			setTimeout(() => {
				if (!settled) child.kill("SIGKILL");
			}, 5_000).unref();
		}, TRUMP_PRODUCER_TIMEOUT_MS);

		child.stdout.on("data", (chunk: Buffer) => {
			stdout += chunk.toString("utf8");
			stdout = tailText(stdout, 8_000);
		});

		child.stderr.on("data", (chunk: Buffer) => {
			stderr += chunk.toString("utf8");
			stderr = tailText(stderr, 8_000);
		});

		child.on("error", (err) => {
			clearTimeout(timeout);
			const duration = Date.now() - startedAt;
			finalize({
				attempted: true,
				status: "error",
				execution_mode: TRUMP_PRODUCER_EXECUTION_MODE,
				exit_code: null,
				duration_ms: duration,
				reason_code:
					parseProducerReasonCode(stdout, `${stderr}\n${String(err)}`) ??
					"PRODUCER_EXEC_FAILED",
				stdout_tail: tailText(stdout),
				stderr_tail: tailText(`${stderr}\n${String(err)}`),
			});
		});

		child.on("close", (code) => {
			clearTimeout(timeout);
			const duration = Date.now() - startedAt;
			const parsedReason = parseProducerReasonCode(stdout, stderr);

			if (timedOut) {
				finalize({
					attempted: true,
					status: "timeout",
					execution_mode: TRUMP_PRODUCER_EXECUTION_MODE,
					exit_code: code ?? null,
					duration_ms: duration,
					reason_code: "PRODUCER_TIMEOUT",
					stdout_tail: tailText(stdout),
					stderr_tail: tailText(stderr),
				});
				return;
			}

			finalize({
				attempted: true,
				status: code === 0 ? "success" : "error",
				execution_mode: TRUMP_PRODUCER_EXECUTION_MODE,
				exit_code: code ?? null,
				duration_ms: duration,
				reason_code: code === 0 ? null : parsedReason ?? "PRODUCER_EXEC_FAILED",
				stdout_tail: tailText(stdout),
				stderr_tail: tailText(stderr),
			});
		});
	});
}

async function syncBucket(cfg: BucketConfig): Promise<SyncResult> {
	const client = await pool.connect();

	try {
		if (cfg.bucket === "trump_effect") {
			const producerGuard = await checkTrumpProducerRun(client);
			if (!producerGuard.ok) {
				return {
					status: "no_data",
					synced: 0,
					reason_code: producerGuard.reason_code ?? "PRODUCER_RUN_MISSING",
					reason: producerGuard.reason,
				};
			}
		}

		const featResult = await client.query<{
			as_of_date: Date;
			features: Record<string, unknown> | null;
		}>(
			`SELECT as_of_date, features
			 FROM ${cfg.featureTable}
			 WHERE as_of_date >= CURRENT_DATE - $1::interval
			 ORDER BY as_of_date ASC`,
			[`${LOOKBACK_DAYS} days`],
		);

		if (!featResult.rows.length) {
			return {
				status: "no_data",
				synced: 0,
				reason_code: "NO_ROWS",
				reason: `No rows in ${cfg.featureTable}`,
			};
		}

		const latestResult = await client.query<{ max_date: Date | null }>(
			`SELECT MAX(as_of_date) AS max_date
			 FROM training.specialist_signals_1d
			 WHERE bucket = $1`,
			[cfg.bucket],
		);

		const latestSynced = latestResult.rows[0]?.max_date
			? toDateKey(latestResult.rows[0].max_date)
			: null;

		const rows = latestSynced
			? featResult.rows.filter((r) => toDateKey(r.as_of_date) >= latestSynced)
			: featResult.rows;

		if (!rows.length) {
			return { status: "up_to_date", synced: 0, latest_date: latestSynced };
		}

		const now = new Date();
		const [sig1Key, sig2Key] = cfg.signalKeys;
		const sourceTag = "specialist-sync-v1";
		let syncedCount = 0;
		let contractSkipped = 0;
		let latestSyncedDate: string | null = null;

		for (const row of rows) {
			const f = row.features ?? {};
			const dateKey = toDateKey(row.as_of_date);

			const requiredKeys = cfg.requiredKeys ?? [];
			const missingRequired = requiredKeys.some((key) => f[key] == null || f[key] === "");
			const nonNumericRequired = requiredKeys.some((key) => !isNumericLike(f[key]));
			if (missingRequired || nonNumericRequired) {
				contractSkipped += 1;
				continue;
			}

			const hasSignal1 = f[sig1Key] != null && f[sig1Key] !== "";
			const signal1 = hasSignal1 ? clamp(safeNum(f[sig1Key], 0), -5, 5) : 0;
			const signal2 = hasSignal1 ? clamp(safeNum(f[sig2Key], 0), -5, 5) : 0;
			const abstained = !hasSignal1;

			let confidence: number;
			if (!abstained && cfg.confidenceKey && f[cfg.confidenceKey] != null) {
				const raw = safeNum(f[cfg.confidenceKey], cfg.fallbackConfidence);
				confidence = raw > 1 ? raw / 100 : raw;
			} else if (!abstained) {
				confidence = cfg.fallbackConfidence;
			} else {
				confidence = 0;
			}
			confidence = clamp(confidence, 0, 0.95);

			const ageDays = Math.max(
				0,
				Math.floor(
					(now.getTime() - new Date(`${dateKey}T00:00:00Z`).getTime()) / 86_400_000,
				),
			);

			const degradedLevel = hasSignal1 ? 0 : 2;

			const runHash = createHash("sha256")
				.update(
					`${dateKey}|${signal1.toFixed(6)}|${confidence.toFixed(6)}|specialist-sync-v1`,
				)
				.digest("hex")
				.slice(0, 16);

				await client.query(
					`INSERT INTO training.specialist_signals_1d
					  (as_of_date, bucket, signal_1, signal_2, confidence, model_type, run_hash,
					   max_input_age_days, source_tag, degraded_level, conf, data_quality,
					   run_id, abstained, warmup, signal_type)
					 VALUES
					  ($1::date, $2, $3, $4, $5, $6, $7,
					   $8, $9, $10, $11, $12::jsonb,
					   $13::uuid, $14, false, 'continuous')
					 ON CONFLICT (as_of_date, bucket)
					 DO UPDATE SET
					   signal_1 = EXCLUDED.signal_1,
					   signal_2 = EXCLUDED.signal_2,
					   confidence = EXCLUDED.confidence,
					   model_type = EXCLUDED.model_type,
					   run_hash = EXCLUDED.run_hash,
				   max_input_age_days = EXCLUDED.max_input_age_days,
				   source_tag = EXCLUDED.source_tag,
				   degraded_level = EXCLUDED.degraded_level,
					   conf = EXCLUDED.conf,
					   data_quality = EXCLUDED.data_quality,
					   run_id = EXCLUDED.run_id,
					   abstained = EXCLUDED.abstained,
					   warmup = EXCLUDED.warmup,
					   signal_type = EXCLUDED.signal_type,
					   created_at = NOW()
					 WHERE training.specialist_signals_1d.source_tag = EXCLUDED.source_tag
					    OR training.specialist_signals_1d.source_tag = $15`,
					[
						dateKey,
						cfg.bucket,
						signal1,
						signal2,
						confidence,
						cfg.modelType,
						runHash,
						ageDays,
						sourceTag,
						degradedLevel,
						confidence,
						JSON.stringify({
							source: cfg.featureTable,
							source_tag: sourceTag,
							signal_key: sig1Key,
							signal2_key: sig2Key,
							synced_at: now.toISOString(),
						}),
						randomUUID(),
						abstained,
						cfg.featureTable,
					],
				);
			syncedCount += 1;
			latestSyncedDate = dateKey;
			}

		if (!syncedCount && contractSkipped > 0) {
			return {
				status: "no_data",
				synced: 0,
				reason_code: "CONTRACT_DRIFT",
				reason: `Skipped ${contractSkipped} ${cfg.bucket} rows due to contract drift`,
			};
		}

		return {
			status: "success",
			synced: syncedCount,
			latest_date: latestSyncedDate,
		};
	} catch (err) {
		const msg = err instanceof Error ? err.message : String(err);
		return { status: "error", synced: 0, error: msg };
	} finally {
		client.release();
	}
}

export const specialistSignalsSync = inngest.createFunction(
	{
		id: "specialist-signals-sync",
		name: "Specialist Signals Sync",
		retries: 2,
		concurrency: [DB_CONCURRENCY, { limit: 1 }],
	},
	// Run after canonical Trump payload producer window to preserve producer->sync ordering.
	{ cron: "30 8 * * *" },
	async ({ step, logger }) => {
		const dbFingerprint = await step.run("db-fingerprint", async () => {
			const client = await pool.connect();
			try {
				return await getDbFingerprint(client);
			} finally {
				client.release();
			}
		});
		const results: Record<string, SyncResult> = {};
		for (const cfg of BUCKETS) {
			results[cfg.bucket] = await step.run(`sync-${cfg.bucket}`, () =>
				syncBucket(cfg),
			);
		}
		logger.info("Specialist signals sync complete", { dbFingerprint, results });
		return results;
	},
);

export const specialistSignalsSyncManual = inngest.createFunction(
	{
		id: "specialist-signals-sync-manual",
		name: "Specialist Signals Sync (Manual)",
		retries: 1,
		concurrency: [DB_CONCURRENCY, { limit: 1 }],
	},
	{ event: "specialist.signals-sync" },
	async ({ step, logger }) => {
		const dbFingerprint = await step.run("db-fingerprint", async () => {
			const client = await pool.connect();
			try {
				return await getDbFingerprint(client);
			} finally {
				client.release();
			}
		});
		const results: Record<string, SyncResult> = {};
		for (const cfg of BUCKETS) {
			results[cfg.bucket] = await step.run(`sync-${cfg.bucket}`, () =>
				syncBucket(cfg),
			);
		}
		logger.info("Specialist signals manual sync complete", {
			dbFingerprint,
			results,
		});
		return results;
	},
);

export const trumpEffectRefreshAndSync = inngest.createFunction(
	{
		id: "trump-effect-refresh-and-sync",
		name: "Trump Effect Refresh And Sync Gate",
		retries: 1,
		concurrency: [DB_CONCURRENCY, { limit: 1 }],
	},
	{ event: "trump-effect.refresh-and-sync" },
	async ({ step, logger, event }) => {
		const readProducerGuard = async () => {
			const client = await pool.connect();
			try {
				const dbFingerprint = await getDbFingerprint(client);
				const guard = await checkTrumpProducerRun(client);
				return { dbFingerprint, guard };
			} finally {
				client.release();
			}
		};

		const producerGuardPre = await step.run(
			"verify-producer-sla-pre",
			readProducerGuard,
		);

		const producerRun = await step.run(
			"run-trump-producer-if-needed",
			async () => {
				if (producerGuardPre.guard.ok) {
					return {
						attempted: false,
						status: "skipped",
						execution_mode: "not_needed",
						exit_code: null,
						duration_ms: 0,
						reason_code: null,
						stdout_tail: "",
						stderr_tail: "",
					} as ProducerRunAttempt;
				}
				return runTrumpProducer();
			},
		);

		const producerGuardPost = await step.run(
			"verify-producer-sla-post",
			readProducerGuard,
		);

		if (!producerGuardPost.guard.ok) {
			logger.warn(
				{
					precheck: producerGuardPre.guard,
					postcheck: producerGuardPost.guard,
					producerRun,
					dbFingerprint: producerGuardPost.dbFingerprint,
				},
				"Trump producer SLA not satisfied after orchestration; dispatching specialist sync with trump bucket guard",
			);
		} else {
			logger.info(
				{
					precheck: producerGuardPre.guard,
					postcheck: producerGuardPost.guard,
					producerRun,
					dbFingerprint: producerGuardPost.dbFingerprint,
				},
				"Trump producer orchestration succeeded; dispatching specialist sync",
			);
		}

		const dispatchResult = await step.run("trigger-specialist-sync", async () =>
			inngest.send({
				name: "specialist.signals-sync",
				data: {
					trigger: event.data?.trigger ?? "manual",
					timestamp: new Date().toISOString(),
					orchestrator: "trump-effect.refresh-and-sync",
					producerCompletedAt: producerGuardPost.guard.producer_completed_at,
					producerAgeHours: producerGuardPost.guard.producer_age_hours,
					producerReasonCode:
						producerGuardPost.guard.reason_code ?? producerRun.reason_code,
					producerRunAttempted: producerRun.attempted,
					producerRunStatus: producerRun.status,
				},
			}),
		);

		return {
			status: producerGuardPost.guard.ok
				? "triggered"
				: "triggered_with_trump_guard",
			reason_code: producerGuardPost.guard.reason_code ?? producerRun.reason_code,
			reason: producerGuardPost.guard.reason,
			producer_completed_at: producerGuardPost.guard.producer_completed_at,
			producer_age_hours: producerGuardPost.guard.producer_age_hours,
			max_age_hours: producerGuardPost.guard.max_age_hours,
			producer_last_status: producerGuardPost.guard.producer_last_status,
			producer_last_reason_code: producerGuardPost.guard.producer_last_reason_code,
			producer_last_completed_at:
				producerGuardPost.guard.producer_last_completed_at,
			precheck: producerGuardPre.guard,
			producerRun,
			postcheck: producerGuardPost.guard,
			dbFingerprint: producerGuardPost.dbFingerprint,
			dispatchResult,
		};
	},
);
