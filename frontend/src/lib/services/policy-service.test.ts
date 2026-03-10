import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PolicyService } from "./policy-service";
import { query } from "@/lib/db";
import { resolveTrumpEffectSnapshot } from "@/lib/services/trump-effect-source";

vi.mock("@/lib/db", () => ({
  query: vi.fn(),
}));

vi.mock("@/lib/services/trump-effect-source", () => ({
  TRUMP_EFFECT_LIVE_MAX_AGE_DAYS: 7,
  TRUMP_EFFECT_DEFAULT_TTL_DAYS: 14,
  resolveTrumpEffectSnapshot: vi.fn(),
}));

const queryMock = vi.mocked(query);
const resolveSnapshotMock = vi.mocked(resolveTrumpEffectSnapshot);

describe("PolicyService.getTrumpEffectMetrics", () => {
  beforeEach(() => {
    queryMock.mockReset();
    resolveSnapshotMock.mockReset();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-10T00:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("falls back to snapshot when in-TTL rows fail contract validation", async () => {
    queryMock.mockResolvedValue([
      {
        date: "2026-03-09",
        velocity: 0.8,
        acceleration: 0.1,
        score: 1.2,
        neural_signal: 0.42,
        neural_confidence: null,
        epu_7d: 120.5,
      },
    ]);

    resolveSnapshotMock.mockResolvedValue({
      values: {
        weighted_action_score: 1.1,
        action_velocity: 0.7,
        action_acceleration: 0.2,
        total_actions_7d: null,
        total_actions_30d: null,
        eo_count_7d: null,
        proclamation_count_7d: null,
        memorandum_count_7d: null,
        nomination_count_7d: null,
        avg_sentiment_7d: null,
        avg_sentiment_30d: null,
        neural_signal: 0.55,
        neural_confidence: 0.6,
        epu_7d: 130,
      },
      meta: {
        source: "signal_proxy",
        asOf: "2026-03-09",
        staleDays: 1,
        ttlDays: 14,
        reasonCode: "MISSING_KEYS",
      },
    });

    const result = await PolicyService.getTrumpEffectMetrics(5);

    expect(resolveSnapshotMock).toHaveBeenCalledTimes(1);
    expect(result).toEqual([
      {
        date: "2026-03-09",
        velocity: 0.7,
        acceleration: 0.2,
        score: 1.1,
        neural_signal: 0.55,
        neural_confidence: 0.6,
        epu_7d: 130,
        source: "signal_proxy",
        staleDays: 1,
        reasonCode: "MISSING_KEYS",
      },
    ]);
  });

  it("returns valid feature payload rows without fallback", async () => {
    queryMock.mockResolvedValue([
      {
        date: "2026-03-09",
        velocity: 0.8,
        acceleration: 0.1,
        score: 1.2,
        neural_signal: 0.42,
        neural_confidence: 0.67,
        epu_7d: 120.5,
      },
    ]);

    const result = await PolicyService.getTrumpEffectMetrics(5);

    expect(resolveSnapshotMock).not.toHaveBeenCalled();
    expect(result).toEqual([
      {
        date: "2026-03-09",
        velocity: 0.8,
        acceleration: 0.1,
        score: 1.2,
        neural_signal: 0.42,
        neural_confidence: 0.67,
        epu_7d: 120.5,
        source: "feature_payload",
        staleDays: 1,
        reasonCode: undefined,
      },
    ]);
  });
});
