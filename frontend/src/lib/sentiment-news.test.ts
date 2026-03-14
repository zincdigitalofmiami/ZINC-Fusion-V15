import { describe, expect, it } from "vitest";

import {
  computeNetSentimentScore,
  resolveZlSentiment,
  summarizeSentiments,
} from "./sentiment-news";

describe("resolveZlSentiment", () => {
  it("prefers explicit stored ZL sentiment labels", () => {
    const result = resolveZlSentiment(
      "bearish",
      "Soybean oil prices surge on tight supply",
      null,
    );

    expect(result).toBe("bearish");
  });

  it("falls back to keyword classification when explicit sentiment is missing", () => {
    const result = resolveZlSentiment(
      null,
      "Soybean oil prices surge on tight supply",
      null,
    );

    expect(result).toBe("bullish");
  });
});

describe("summarizeSentiments", () => {
  it("counts bullish, bearish, and neutral rows exactly", () => {
    expect(
      summarizeSentiments(["bullish", "neutral", "bearish", "bullish"]),
    ).toEqual({
      total: 4,
      bullish: 2,
      bearish: 1,
      neutral: 1,
    });
  });
});

describe("computeNetSentimentScore", () => {
  it("returns a signed net score on a -100 to 100 scale", () => {
    expect(
      computeNetSentimentScore({
        total: 10,
        bullish: 6,
        bearish: 2,
        neutral: 2,
      }),
    ).toBe(40);
  });

  it("returns null when there are no scored rows", () => {
    expect(
      computeNetSentimentScore({
        total: 0,
        bullish: 0,
        bearish: 0,
        neutral: 0,
      }),
    ).toBeNull();
  });
});
