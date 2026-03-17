import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildNarrativeResponse,
  resetNarrativeCacheForTests,
  type NarrativeRequest,
} from "./route";

const basePayload: NarrativeRequest = {
  fearGreed: {
    score: 58,
    zone: "neutral",
    label: "Neutral",
  },
};

function parseJson<T>(value: string): T | null {
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

describe("sentiment narrative caching", () => {
  beforeEach(() => {
    resetNarrativeCacheForTests();
  });

  it("reuses cached response for identical payloads", async () => {
    const completeText = vi.fn().mockResolvedValue(
      JSON.stringify({
        fearGreedNarrative: "FG",
        trumpEffectNarrative: "Trump",
        volatilityNarrative: "Vol",
      }),
    );

    const deps = {
      hasApiKey: () => true,
      completeText,
      parseJson,
      buildFallback: () => ({
        fearGreedNarrative: "fallback-fg",
        trumpEffectNarrative: "fallback-trump",
        volatilityNarrative: "fallback-vol",
      }),
      now: () => 1_000,
    };

    const first = await buildNarrativeResponse(basePayload, deps);
    const second = await buildNarrativeResponse(basePayload, deps);

    expect(completeText).toHaveBeenCalledTimes(1);
    expect(first).toEqual(second);
    expect(first.source).toBe("ai");
    expect(first.model).not.toBeNull();
  });

  it("does not collide cache entries for different payloads", async () => {
    const completeText = vi
      .fn()
      .mockResolvedValueOnce(
        JSON.stringify({
          fearGreedNarrative: "payload-1",
          trumpEffectNarrative: null,
          volatilityNarrative: null,
        }),
      )
      .mockResolvedValueOnce(
        JSON.stringify({
          fearGreedNarrative: "payload-2",
          trumpEffectNarrative: null,
          volatilityNarrative: null,
        }),
      );

    const deps = {
      hasApiKey: () => true,
      completeText,
      parseJson,
      buildFallback: () => ({
        fearGreedNarrative: "fallback-fg",
        trumpEffectNarrative: "fallback-trump",
        volatilityNarrative: "fallback-vol",
      }),
      now: () => 2_000,
    };

    const first = await buildNarrativeResponse(
      { fearGreed: { score: 40, zone: "fear", label: "Fear" } },
      deps,
    );
    const second = await buildNarrativeResponse(
      { fearGreed: { score: 70, zone: "greed", label: "Greed" } },
      deps,
    );

    expect(completeText).toHaveBeenCalledTimes(2);
    expect(first.fearGreedNarrative).not.toBe(second.fearGreedNarrative);
  });

  it("returns deterministic fallback when API key is absent", async () => {
    const completeText = vi.fn();
    const fallback = {
      fearGreedNarrative: "fallback-fg",
      trumpEffectNarrative: "fallback-trump",
      volatilityNarrative: "fallback-vol",
    };

    const response = await buildNarrativeResponse(basePayload, {
      hasApiKey: () => false,
      completeText,
      parseJson,
      buildFallback: () => fallback,
      now: () => 3_000,
    });

    expect(completeText).not.toHaveBeenCalled();
    expect(response).toEqual({
      ...fallback,
      source: "deterministic",
      model: null,
    });
  });

  it("falls back cleanly when AI generation fails", async () => {
    const completeText = vi.fn().mockRejectedValue(new Error("boom"));
    const fallback = {
      fearGreedNarrative: "fallback-fg",
      trumpEffectNarrative: "fallback-trump",
      volatilityNarrative: "fallback-vol",
    };

    const first = await buildNarrativeResponse(basePayload, {
      hasApiKey: () => true,
      completeText,
      parseJson,
      buildFallback: () => fallback,
      now: () => 4_000,
    });
    const second = await buildNarrativeResponse(basePayload, {
      hasApiKey: () => true,
      completeText,
      parseJson,
      buildFallback: () => fallback,
      now: () => 4_000,
    });

    expect(first).toEqual({
      ...fallback,
      source: "deterministic",
      model: null,
    });
    expect(second).toEqual({
      ...fallback,
      source: "deterministic",
      model: null,
    });
    expect(completeText).toHaveBeenCalledTimes(2);
  });

  it("treats parsed empty AI JSON as deterministic and does not cache it", async () => {
    const completeText = vi.fn().mockResolvedValue("{}");
    const fallback = {
      fearGreedNarrative: "fallback-fg",
      trumpEffectNarrative: "fallback-trump",
      volatilityNarrative: "fallback-vol",
    };

    const first = await buildNarrativeResponse(basePayload, {
      hasApiKey: () => true,
      completeText,
      parseJson,
      buildFallback: () => fallback,
      now: () => 4_250,
    });
    const second = await buildNarrativeResponse(basePayload, {
      hasApiKey: () => true,
      completeText,
      parseJson,
      buildFallback: () => fallback,
      now: () => 4_250,
    });

    expect(first).toEqual({
      ...fallback,
      source: "deterministic",
      model: null,
    });
    expect(second).toEqual({
      ...fallback,
      source: "deterministic",
      model: null,
    });
    expect(completeText).toHaveBeenCalledTimes(2);
  });

  it("allows a later successful AI call after an earlier failure for the same payload", async () => {
    const completeText = vi
      .fn()
      .mockRejectedValueOnce(new Error("transient"))
      .mockResolvedValueOnce(
        JSON.stringify({
          fearGreedNarrative: "AI fg",
          trumpEffectNarrative: "AI trump",
          volatilityNarrative: "AI vol",
        }),
      );
    const fallback = {
      fearGreedNarrative: "fallback-fg",
      trumpEffectNarrative: "fallback-trump",
      volatilityNarrative: "fallback-vol",
    };

    const first = await buildNarrativeResponse(basePayload, {
      hasApiKey: () => true,
      completeText,
      parseJson,
      buildFallback: () => fallback,
      now: () => 4_500,
    });
    const second = await buildNarrativeResponse(basePayload, {
      hasApiKey: () => true,
      completeText,
      parseJson,
      buildFallback: () => fallback,
      now: () => 4_500,
    });

    expect(first).toEqual({
      ...fallback,
      source: "deterministic",
      model: null,
    });
    expect(second.source).toBe("ai");
    expect(second.model).not.toBeNull();
    expect(second.fearGreedNarrative).toBe("AI fg");
    expect(completeText).toHaveBeenCalledTimes(2);
  });

  it("allows parsed-empty response first, then caches a later AI success for the same payload", async () => {
    const completeText = vi
      .fn()
      .mockResolvedValueOnce("{}")
      .mockResolvedValueOnce(
        JSON.stringify({
          fearGreedNarrative: "AI fg",
          trumpEffectNarrative: null,
          volatilityNarrative: null,
        }),
      );
    const fallback = {
      fearGreedNarrative: "fallback-fg",
      trumpEffectNarrative: "fallback-trump",
      volatilityNarrative: "fallback-vol",
    };

    const first = await buildNarrativeResponse(basePayload, {
      hasApiKey: () => true,
      completeText,
      parseJson,
      buildFallback: () => fallback,
      now: () => 4_750,
    });
    const second = await buildNarrativeResponse(basePayload, {
      hasApiKey: () => true,
      completeText,
      parseJson,
      buildFallback: () => fallback,
      now: () => 4_750,
    });
    const third = await buildNarrativeResponse(basePayload, {
      hasApiKey: () => true,
      completeText,
      parseJson,
      buildFallback: () => fallback,
      now: () => 4_750,
    });

    expect(first).toEqual({
      ...fallback,
      source: "deterministic",
      model: null,
    });
    expect(second.source).toBe("ai");
    expect(second.fearGreedNarrative).toBe("AI fg");
    expect(third).toEqual(second);
    expect(completeText).toHaveBeenCalledTimes(2);
  });

  it("preserves the narrative response shape", async () => {
    const response = await buildNarrativeResponse(basePayload, {
      hasApiKey: () => false,
      completeText: vi.fn(),
      parseJson,
      buildFallback: () => ({
        fearGreedNarrative: null,
        trumpEffectNarrative: null,
        volatilityNarrative: null,
      }),
      now: () => 5_000,
    });

    expect(Object.keys(response).sort()).toEqual([
      "fearGreedNarrative",
      "model",
      "source",
      "trumpEffectNarrative",
      "volatilityNarrative",
    ]);
  });
});
