import { createHash, randomUUID } from "crypto";

import { inngest, DB_CONCURRENCY } from "./client";
import { getIngestPool } from "@/lib/db";

const pool = getIngestPool();
const LOOKBACK_DAYS = 120;

interface BucketConfig {
	bucket: string;
	featureTable: string;
	modelType: string;
	signalKeys: [string, string];
	confidenceKey: string | null;
	fallbackConfidence: number;
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
		signalKeys: ["trump_bucket_signal", "policy_uncertainty_zscore"],
		confidenceKey: null,
		fallbackConfidence: 0.5,
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

interface SyncResult {
	status: string;
	synced: number;
	latest_date?: string | null;
	reason?: string;
	error?: string;
}

async function syncBucket(cfg: BucketConfig): Promise<SyncResult> {
	const client = await pool.connect();

	try {
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
			return { status: "no_data", synced: 0, reason: `No rows in ${cfg.featureTable}` };
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

		for (const row of rows) {
			const f = row.features ?? {};
			const dateKey = toDateKey(row.as_of_date);

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
			}

		return {
			status: "success",
			synced: rows.length,
			latest_date: toDateKey(rows[rows.length - 1].as_of_date),
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
	{ cron: "0 7 * * *" },
	async ({ step, logger }) => {
		const results: Record<string, SyncResult> = {};
		for (const cfg of BUCKETS) {
			results[cfg.bucket] = await step.run(`sync-${cfg.bucket}`, () =>
				syncBucket(cfg),
			);
		}
		logger.info("Specialist signals sync complete", results);
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
		const results: Record<string, SyncResult> = {};
		for (const cfg of BUCKETS) {
			results[cfg.bucket] = await step.run(`sync-${cfg.bucket}`, () =>
				syncBucket(cfg),
			);
		}
		logger.info("Specialist signals manual sync complete", results);
		return results;
	},
);
