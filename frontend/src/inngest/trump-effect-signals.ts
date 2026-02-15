import { createHash, randomUUID } from "crypto";

import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

const SOURCE_BUCKET = "trump_effect";
const SOURCE_TABLE = "training.specialist_features_trump_effect";
const LOOKBACK_DAYS = 120;

interface TrumpSourceRow {
  as_of_date: string;
  signal: number | null;
  confidence: number | null;
  features: Record<string, unknown> | null;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function toDateKey(value: Date | string): string {
  const d = value instanceof Date ? value : new Date(value);
  return d.toISOString().split("T")[0];
}

function parseFeatures(features: unknown): Record<string, unknown> {
  if (!features) {
    return {};
  }

  if (typeof features === "object") {
    return features as Record<string, unknown>;
  }

  if (typeof features === "string") {
    try {
      return JSON.parse(features) as Record<string, unknown>;
    } catch {
      return {};
    }
  }

  return {};
}

async function runTrumpEffectSignalSync() {
  const client = await pool.connect();

  try {
    const sourceResult = await client.query<{
      as_of_date: Date;
      features: unknown;
    }>(
      `SELECT as_of_date, features
       FROM training.specialist_features_trump_effect
       WHERE as_of_date >= CURRENT_DATE - $1::interval
       ORDER BY as_of_date ASC`,
      [`${LOOKBACK_DAYS} days`],
    );

    if (!sourceResult.rows.length) {
      return {
        status: "no_data",
        reason: `No rows in ${SOURCE_TABLE}`,
        synced: 0,
      };
    }

    const sourceRows: TrumpSourceRow[] = sourceResult.rows.map((row) => ({
      as_of_date: toDateKey(row.as_of_date),
      signal: null,
      confidence: null,
      features: parseFeatures(row.features),
    }));

    const latestSignalResult = await client.query<{ max_date: Date | null }>(
      `SELECT MAX(as_of_date) AS max_date
       FROM training.specialist_signals_1d
       WHERE bucket = $1`,
      [SOURCE_BUCKET],
    );

    const latestSynced = latestSignalResult.rows[0]?.max_date
      ? toDateKey(latestSignalResult.rows[0].max_date)
      : null;

    const rowsToSync = latestSynced
      ? sourceRows.filter((row) => row.as_of_date >= latestSynced)
      : sourceRows;

    if (!rowsToSync.length) {
      return {
        status: "up_to_date",
        latest_source_date: sourceRows[sourceRows.length - 1]?.as_of_date ?? null,
        latest_signal_date: latestSynced,
        synced: 0,
      };
    }

    const now = new Date();

    for (const row of rowsToSync) {
      const features = row.features ?? {};
      const sourceSignal = Number(features.neural_signal ?? features.signal ?? 0);
      const sourceConfidence = Number(
        features.neural_confidence ?? features.confidence ?? 0.55,
      );

      const eventRisk = clamp(Number.isFinite(sourceSignal) ? sourceSignal : 0, 0, 1);
      const confidence = clamp(
        Number.isFinite(sourceConfidence) ? sourceConfidence : 0.55,
        0.2,
        0.95,
      );
      const signedSignal = clamp(1 - 2 * eventRisk, -2, 2);

      const accelValue = Number(features.action_acceleration ?? 0);
      const signal2 = Number.isFinite(accelValue) ? clamp(accelValue, -5, 5) : 0;

      const ageDays = Math.max(
        0,
        Math.floor(
          (now.getTime() - new Date(`${row.as_of_date}T00:00:00Z`).getTime()) /
            86_400_000,
        ),
      );

      const hasEpu =
        features.epu_7d !== undefined && features.epu_7d !== null && features.epu_7d !== "";

      const hasVix =
        features.vix_7d !== undefined && features.vix_7d !== null && features.vix_7d !== "";

      const runHash = createHash("sha256")
        .update(
          `${row.as_of_date}|${signedSignal.toFixed(6)}|${confidence.toFixed(6)}|trump-effect-sync-v1`,
        )
        .digest("hex")
        .slice(0, 16);

      const degradedLevel = hasEpu && hasVix ? 0 : 1;

      await client.query(
        `INSERT INTO training.specialist_signals_1d
          (as_of_date, bucket, signal_1, signal_2, confidence, model_type, run_hash,
          max_input_age_days, source_tag, degraded_level, conf, data_quality,
           run_id, abstained, warmup, signal_type)
         VALUES
          ($1::date, $2, $3, $4, $5, 'event_study', $6,
           $7, $8, $9, $10, $11::jsonb,
           $12::uuid, false, false, 'continuous')
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
           created_at = NOW()`,
        [
          row.as_of_date,
          SOURCE_BUCKET,
          signedSignal,
          signal2,
          confidence,
          runHash,
          ageDays,
          SOURCE_TABLE,
          degradedLevel,
          confidence,
          JSON.stringify({
            source: SOURCE_TABLE,
            scoring_version: features.scoring_version ?? null,
            has_epu: hasEpu,
            has_vix: hasVix,
            synced_at: now.toISOString(),
          }),
          randomUUID(),
        ],
      );
    }

    return {
      status: "success",
      latest_source_date: sourceRows[sourceRows.length - 1]?.as_of_date ?? null,
      latest_signal_date: rowsToSync[rowsToSync.length - 1]?.as_of_date ?? null,
      synced: rowsToSync.length,
    };
  } finally {
    client.release();
  }
}

export const trumpEffectSignalSync = inngest.createFunction(
  {
    id: "trump-effect-signal-sync",
    name: "Trump Effect Signal Sync",
    retries: 2,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { cron: "50 6 * * *" },
  async ({ step, logger }) => {
    const result = await step.run("sync-trump-effect-signals", async () =>
      runTrumpEffectSignalSync(),
    );

    logger.info("Trump Effect signal sync complete", result);
    return result;
  },
);

export const trumpEffectSignalSyncManual = inngest.createFunction(
  {
    id: "trump-effect-signal-sync-manual",
    name: "Trump Effect Signal Sync (Manual)",
    retries: 1,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { event: "trump-effect.signal-sync" },
  async ({ step, logger }) => {
    const result = await step.run("sync-trump-effect-signals-manual", async () =>
      runTrumpEffectSignalSync(),
    );

    logger.info("Trump Effect manual signal sync complete", result);
    return result;
  },
);
