import { describe, expect, it } from "vitest";

import { classifySentiment, scoreZlSentiment } from "./sentiment-scorer";

describe("scoreZlSentiment", () => {
  it("empty/null returns neutral", () => {
    const result = scoreZlSentiment(null);
    expect(result.sentiment).toBe("neutral");
    expect(result.confidence).toBe(0);
  });

  it("short text returns neutral", () => {
    const result = scoreZlSentiment("hi");
    expect(result.sentiment).toBe("neutral");
  });

  it("bullish headline scores bullish", () => {
    const result = scoreZlSentiment("Soybean oil prices surge on tight supply");
    expect(result.sentiment).toBe("bullish");
    expect(result.bullScore).toBeGreaterThan(0);
  });

  it("bearish headline scores bearish", () => {
    const result = scoreZlSentiment("Palm oil glut crashes vegetable oil prices");
    expect(result.sentiment).toBe("bearish");
    expect(result.bearScore).toBeGreaterThan(0);
  });

  it("confidence capped at 1.0", () => {
    const result = scoreZlSentiment(
      "Massive surge rally breakout soaring new high record demand bullish"
    );
    expect(result.confidence).toBeLessThanOrEqual(1.0);
  });
});

describe("classifySentiment", () => {
  it("returns a valid sentiment string", () => {
    const result = classifySentiment("oil prices drop sharply");
    expect(["bullish", "bearish", "neutral"]).toContain(result);
  });
});
