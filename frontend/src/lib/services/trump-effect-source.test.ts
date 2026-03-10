import { describe, expect, it } from "vitest";

import { resolveTrumpEffectSnapshot } from "./trump-effect-source";

const NOW = new Date("2026-03-09T00:00:00Z");

const validFeatures = {
  weighted_action_score: 1.2,
  action_velocity: 0.8,
  action_acceleration: 0.1,
  total_actions_7d: 5,
  total_actions_30d: 18,
  eo_count_7d: 2,
  proclamation_count_7d: 1,
  memorandum_count_7d: 1,
  nomination_count_7d: 1,
  avg_sentiment_7d: 0.05,
  avg_sentiment_30d: 0.03,
  neural_signal: 0.42,
  neural_confidence: 0.67,
  epu_7d: 120.5,
};

function makeDbQuery({
  tableExists = true,
  rows = [],
  signalRows = [],
}: {
  tableExists?: boolean;
  rows?: Array<{ as_of_date: string; features: Record<string, unknown> | null }>;
  signalRows?: Array<{ as_of_date: string; signal_1: number; confidence: number | null }>;
}) {
  return async <T = Record<string, unknown>>(sql: string): Promise<T[]> => {
    if (sql.includes("to_regclass('training.specialist_features_trump_effect')")) {
      return [
        {
          table_name: tableExists
            ? "training.specialist_features_trump_effect"
            : null,
        },
      ] as T[];
    }
    if (sql.includes("FROM training.specialist_features_trump_effect")) {
      return rows as T[];
    }
    if (sql.includes("FROM training.specialist_signals_1d")) {
      return signalRows as T[];
    }
    throw new Error(`Unexpected SQL in test mock: ${sql}`);
  };
}

describe("resolveTrumpEffectSnapshot", () => {
  it("returns signal_proxy when table is missing", async () => {
    const snapshot = await resolveTrumpEffectSnapshot(
      makeDbQuery({
        tableExists: false,
        signalRows: [{ as_of_date: "2026-03-08", signal_1: 0.4, confidence: 0.8 }],
      }),
      { now: NOW, ttlDays: 14 },
    );

    expect(snapshot.meta.source).toBe("signal_proxy");
    expect(snapshot.meta.reasonCode).toBe("MISSING_TABLE");
    expect(snapshot.values.weighted_action_score).toBeCloseTo(0.4, 6);
  });

  it("returns unavailable when table is empty and no proxy exists", async () => {
    const snapshot = await resolveTrumpEffectSnapshot(
      makeDbQuery({ tableExists: true, rows: [], signalRows: [] }),
      { now: NOW, ttlDays: 14 },
    );

    expect(snapshot.meta.source).toBe("unavailable");
    expect(snapshot.meta.reasonCode).toBe("NO_ROWS");
  });

  it("falls back to signal_proxy on key drift", async () => {
    const drifted = { ...validFeatures };
    delete (drifted as Record<string, unknown>).neural_confidence;

    const snapshot = await resolveTrumpEffectSnapshot(
      makeDbQuery({
        rows: [{ as_of_date: "2026-03-09", features: drifted }],
        signalRows: [{ as_of_date: "2026-03-09", signal_1: 0.6, confidence: 0.7 }],
      }),
      { now: NOW, ttlDays: 14 },
    );

    expect(snapshot.meta.source).toBe("signal_proxy");
    expect(snapshot.meta.reasonCode).toBe("MISSING_KEYS");
  });

  it("falls back to signal_proxy on non-numeric keys", async () => {
    const castDrift = {
      ...validFeatures,
      weighted_action_score: "",
    };

    const snapshot = await resolveTrumpEffectSnapshot(
      makeDbQuery({
        rows: [{ as_of_date: "2026-03-09", features: castDrift }],
        signalRows: [{ as_of_date: "2026-03-09", signal_1: 0.5, confidence: 0.6 }],
      }),
      { now: NOW, ttlDays: 14 },
    );

    expect(snapshot.meta.source).toBe("signal_proxy");
    expect(snapshot.meta.reasonCode).toBe("NON_NUMERIC_KEYS");
  });

  it("returns feature_payload when data is fresh", async () => {
    const snapshot = await resolveTrumpEffectSnapshot(
      makeDbQuery({
        rows: [{ as_of_date: "2026-03-07", features: validFeatures }],
      }),
      { now: NOW, ttlDays: 14 },
    );

    expect(snapshot.meta.source).toBe("feature_payload");
    expect(snapshot.meta.reasonCode).toBeNull();
    expect(snapshot.values.weighted_action_score).toBe(1.2);
  });

  it("returns last_known when feature payload is stale but within TTL", async () => {
    const snapshot = await resolveTrumpEffectSnapshot(
      makeDbQuery({
        rows: [{ as_of_date: "2026-02-28", features: validFeatures }],
      }),
      { now: NOW, ttlDays: 14 },
    );

    expect(snapshot.meta.source).toBe("last_known");
    expect(snapshot.meta.staleDays).toBe(9);
  });

  it("returns unavailable when payload and proxy are both past TTL", async () => {
    const snapshot = await resolveTrumpEffectSnapshot(
      makeDbQuery({
        rows: [{ as_of_date: "2026-02-15", features: validFeatures }],
        signalRows: [{ as_of_date: "2026-02-20", signal_1: 0.4, confidence: 0.5 }],
      }),
      { now: NOW, ttlDays: 14 },
    );

    expect(snapshot.meta.source).toBe("unavailable");
    expect(snapshot.meta.reasonCode).toBe("STALE_EXPIRED");
  });

  it("uses signal_proxy when payload is unavailable but signal exists", async () => {
    const snapshot = await resolveTrumpEffectSnapshot(
      makeDbQuery({
        rows: [],
        signalRows: [{ as_of_date: "2026-03-06", signal_1: 0.25, confidence: 0.4 }],
      }),
      { now: NOW, ttlDays: 14 },
    );

    expect(snapshot.meta.source).toBe("signal_proxy");
    expect(snapshot.meta.reasonCode).toBe("NO_ROWS");
  });
});
