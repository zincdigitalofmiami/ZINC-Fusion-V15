import { query as defaultQuery } from "@/lib/db";

export const TRUMP_EFFECT_LIVE_MAX_AGE_DAYS = 7;
export const TRUMP_EFFECT_DEFAULT_TTL_DAYS = 14;

export type TrumpEffectSource =
  | "feature_payload"
  | "last_known"
  | "signal_proxy"
  | "unavailable";

export type TrumpEffectReasonCode =
  | "MISSING_TABLE"
  | "NO_ROWS"
  | "MISSING_KEYS"
  | "NON_NUMERIC_KEYS"
  | "STALE_EXPIRED";

export interface TrumpEffectMeta {
  source: TrumpEffectSource;
  asOf: string | null;
  staleDays: number | null;
  ttlDays: number;
  reasonCode: TrumpEffectReasonCode | null;
}

export interface TrumpEffectValues {
  weighted_action_score: number | null;
  action_velocity: number | null;
  action_acceleration: number | null;
  total_actions_7d: number | null;
  total_actions_30d: number | null;
  eo_count_7d: number | null;
  proclamation_count_7d: number | null;
  memorandum_count_7d: number | null;
  nomination_count_7d: number | null;
  avg_sentiment_7d: number | null;
  avg_sentiment_30d: number | null;
  neural_signal: number | null;
  neural_confidence: number | null;
  epu_7d: number | null;
}

export interface TrumpEffectSnapshot {
  values: TrumpEffectValues;
  meta: TrumpEffectMeta;
}

type DbQuery = <T = Record<string, unknown>>(
  sql: string,
  params?: unknown[],
) => Promise<T[]>;

interface TrumpFeatureRow {
  as_of_date: string;
  features: Record<string, unknown> | null;
}

interface TrumpSignalRow {
  as_of_date: string;
  signal_1: number;
  confidence: number | null;
}

interface NumericParse {
  value: number | null;
  missing: boolean;
  nonNumeric: boolean;
}

const REQUIRED_KEYS = [
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
] as const;

function emptyValues(): TrumpEffectValues {
  return {
    weighted_action_score: null,
    action_velocity: null,
    action_acceleration: null,
    total_actions_7d: null,
    total_actions_30d: null,
    eo_count_7d: null,
    proclamation_count_7d: null,
    memorandum_count_7d: null,
    nomination_count_7d: null,
    avg_sentiment_7d: null,
    avg_sentiment_30d: null,
    neural_signal: null,
    neural_confidence: null,
    epu_7d: null,
  };
}

function asDateOnly(isoDate: string): Date {
  return new Date(`${isoDate}T00:00:00Z`);
}

function staleDaysFrom(asOf: string, now: Date): number {
  return Math.max(
    0,
    Math.floor((now.getTime() - asDateOnly(asOf).getTime()) / 86_400_000),
  );
}

function parseNumeric(raw: unknown): NumericParse {
  if (raw === undefined || raw === null) {
    return { value: null, missing: true, nonNumeric: false };
  }
  if (typeof raw === "number") {
    return Number.isFinite(raw)
      ? { value: raw, missing: false, nonNumeric: false }
      : { value: null, missing: false, nonNumeric: true };
  }
  if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (trimmed.length === 0) {
      return { value: null, missing: false, nonNumeric: true };
    }
    const parsed = Number(trimmed);
    return Number.isFinite(parsed)
      ? { value: parsed, missing: false, nonNumeric: false }
      : { value: null, missing: false, nonNumeric: true };
  }
  return { value: null, missing: false, nonNumeric: true };
}

function buildFeatureValues(
  features: Record<string, unknown> | null,
): {
  values: TrumpEffectValues;
  missingKeys: string[];
  nonNumericKeys: string[];
} {
  const values = emptyValues();
  const missingKeys: string[] = [];
  const nonNumericKeys: string[] = [];
  const featureObj = features ?? {};

  for (const key of REQUIRED_KEYS) {
    const parsed = parseNumeric(featureObj[key]);
    if (parsed.missing) {
      missingKeys.push(key);
      continue;
    }
    if (parsed.nonNumeric) {
      nonNumericKeys.push(key);
      continue;
    }
    values[key] = parsed.value;
  }

  return { values, missingKeys, nonNumericKeys };
}

function proxyWeightedActionScore(signal: number): number {
  return Math.min(2, Math.max(0, Math.abs(signal)));
}

async function trySignalProxy(
  dbQuery: DbQuery,
  ttlDays: number,
  now: Date,
  reasonCode: TrumpEffectReasonCode,
): Promise<TrumpEffectSnapshot> {
  const signalRows = await dbQuery<TrumpSignalRow>(
    `SELECT as_of_date::text, signal_1::float8, confidence::float8
     FROM training.specialist_signals_1d
     WHERE bucket = 'trump_effect' AND abstained = false
     ORDER BY as_of_date DESC
     LIMIT 1`,
  ).catch(() => [] as TrumpSignalRow[]);

  const signal = signalRows[0];
  if (!signal) {
    return {
      values: emptyValues(),
      meta: {
        source: "unavailable",
        asOf: null,
        staleDays: null,
        ttlDays,
        reasonCode,
      },
    };
  }

  const staleDays = staleDaysFrom(signal.as_of_date, now);
  if (staleDays > ttlDays) {
    return {
      values: emptyValues(),
      meta: {
        source: "unavailable",
        asOf: signal.as_of_date,
        staleDays,
        ttlDays,
        reasonCode: "STALE_EXPIRED",
      },
    };
  }

  return {
    values: {
      ...emptyValues(),
      weighted_action_score: proxyWeightedActionScore(signal.signal_1),
      neural_signal: signal.signal_1,
      neural_confidence: signal.confidence,
    },
    meta: {
      source: "signal_proxy",
      asOf: signal.as_of_date,
      staleDays,
      ttlDays,
      reasonCode,
    },
  };
}

export async function resolveTrumpEffectSnapshot(
  dbQuery: DbQuery = defaultQuery,
  {
    now = new Date(),
    ttlDays = TRUMP_EFFECT_DEFAULT_TTL_DAYS,
    liveMaxAgeDays = TRUMP_EFFECT_LIVE_MAX_AGE_DAYS,
    lookbackRows = 120,
  }: {
    now?: Date;
    ttlDays?: number;
    liveMaxAgeDays?: number;
    lookbackRows?: number;
  } = {},
): Promise<TrumpEffectSnapshot> {
  const tableCheck = await dbQuery<{ table_name: string | null }>(
    `SELECT to_regclass('training.specialist_features_trump_effect')::text AS table_name`,
  ).catch(() => [] as { table_name: string | null }[]);

  if (!tableCheck[0]?.table_name) {
    return trySignalProxy(dbQuery, ttlDays, now, "MISSING_TABLE");
  }

  const rows = await dbQuery<TrumpFeatureRow>(
    `SELECT as_of_date::text, features
     FROM training.specialist_features_trump_effect
     ORDER BY as_of_date DESC
     LIMIT $1`,
    [lookbackRows],
  ).catch(() => [] as TrumpFeatureRow[]);

  if (!rows.length) {
    return trySignalProxy(dbQuery, ttlDays, now, "NO_ROWS");
  }

  let hasMissingKeys = false;
  let hasNonNumericKeys = false;
  let hasExpiredOnly = false;

  for (const row of rows) {
    const { values, missingKeys, nonNumericKeys } = buildFeatureValues(row.features);

    if (missingKeys.length > 0) {
      hasMissingKeys = true;
      continue;
    }
    if (nonNumericKeys.length > 0) {
      hasNonNumericKeys = true;
      continue;
    }

    const staleDays = staleDaysFrom(row.as_of_date, now);
    if (staleDays > ttlDays) {
      hasExpiredOnly = true;
      continue;
    }

    return {
      values,
      meta: {
        source: staleDays <= liveMaxAgeDays ? "feature_payload" : "last_known",
        asOf: row.as_of_date,
        staleDays,
        ttlDays,
        reasonCode: null,
      },
    };
  }

  const fallbackReason: TrumpEffectReasonCode = hasMissingKeys
    ? "MISSING_KEYS"
    : hasNonNumericKeys
      ? "NON_NUMERIC_KEYS"
      : hasExpiredOnly
        ? "STALE_EXPIRED"
        : "NO_ROWS";

  return trySignalProxy(dbQuery, ttlDays, now, fallbackReason);
}
