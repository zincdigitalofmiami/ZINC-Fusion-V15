import { describe, expect, it } from "vitest";

import {
  computeNetSentimentScore,
  resolveZlSentimentForAggregation,
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

describe("resolveZlSentimentForAggregation", () => {
  it("preserves explicit stored sentiment labels", () => {
    expect(
      resolveZlSentimentForAggregation(
        "bearish",
        "Congress bill sparks a market rally",
        null,
        "google_news/trump_actions/Reuters",
        ["lane_trump_actions", "trump_effect"],
      ),
    ).toEqual({
      sentiment: "bearish",
      includeInCounts: true,
    });
  });

  it("keeps clearly soybean-oil headlines eligible for fallback classification", () => {
    expect(
      resolveZlSentimentForAggregation(
        null,
        "Soybean oil prices surge on tight supply",
        null,
        "Federal Register",
        [],
      ),
    ).toEqual({
      sentiment: "bullish",
      includeInCounts: true,
    });
  });

  it("keeps Google News soybean lanes eligible even when source is canonicalized", () => {
    expect(
      resolveZlSentimentForAggregation(
        null,
        "Biofuel demand surge supports soybean oil feedstock",
        null,
        "google_news/Reuters",
        ["lane_soybean_agriculture", "china"],
      ),
    ).toEqual({
      sentiment: "bullish",
      includeInCounts: true,
    });
  });

  it("excludes generic legislation/politics fallback rows from counts", () => {
    const genericHeadline = "Congress vote triggers a broad market rally";
    expect(resolveZlSentiment(null, genericHeadline, null)).toBe("bullish");

    expect(
      resolveZlSentimentForAggregation(
        null,
        genericHeadline,
        null,
        "google_news/legislation/Reuters",
        ["lane_legislation", "tariff", "trump_effect"],
      ),
    ).toEqual({
      sentiment: "neutral",
      includeInCounts: false,
    });
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
