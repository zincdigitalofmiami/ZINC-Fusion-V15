import { describe, expect, it } from "vitest";

import { resolveZlSentimentForAggregation } from "@/lib/sentiment-news";
import { buildTopicsFromRows } from "./route";

describe("sentiment/topics aggregation contract", () => {
  it("keeps explicit zl_sentiment as the source of truth", () => {
    const rows = [
      {
        tag: "tariff",
        headline: "Congress vote triggers broad market rally on fiscal plan",
        summary: null,
        source: "google_news/legislation/Reuters",
        zl_sentiment: "bearish",
        specialist_tags: ["lane_legislation", "tariff"],
      },
    ];

    const topics = buildTopicsFromRows(rows);
    expect(topics[0]?.topic).toBe("tariff");
    expect(topics[0]?.mentions).toBe(1);
    expect(topics[0]?.sentiment).toBe(-1);
  });

  it("keeps mention counts stable while applying relevance-aware sentiment scoring", () => {
    const rows = [
      {
        tag: "tariff",
        headline: "Executive order update from Washington",
        summary: null,
        source: "google_news/legislation/Reuters",
        zl_sentiment: "bearish",
        specialist_tags: ["lane_legislation", "tariff"],
      },
      {
        tag: "tariff",
        headline: "Congress vote triggers broad market rally on fiscal plan",
        summary: null,
        source: "google_news/legislation/Reuters",
        zl_sentiment: null,
        specialist_tags: ["lane_legislation", "tariff", "trump_effect"],
      },
      {
        tag: "biofuel",
        headline: "Renewable diesel demand lifts soybean oil feedstock prices",
        summary: null,
        source: "google_news/biofuel/Reuters",
        zl_sentiment: null,
        specialist_tags: ["lane_biofuel", "biofuel", "energy"],
      },
    ];

    const genericFallback = resolveZlSentimentForAggregation(
      rows[1].zl_sentiment,
      rows[1].headline,
      rows[1].summary,
      rows[1].source,
      rows[1].specialist_tags,
    );
    expect(genericFallback.includeInCounts).toBe(false);

    const relevantBiofuel = resolveZlSentimentForAggregation(
      rows[2].zl_sentiment,
      rows[2].headline,
      rows[2].summary,
      rows[2].source,
      rows[2].specialist_tags,
    );
    expect(relevantBiofuel.includeInCounts).toBe(true);
    expect(relevantBiofuel.sentiment).toBe("bullish");

    const topics = buildTopicsFromRows(rows);
    const tariff = topics.find((topic) => topic.topic === "tariff");
    const biofuel = topics.find((topic) => topic.topic === "biofuel");

    expect(tariff).toBeDefined();
    expect(tariff?.mentions).toBe(2);
    expect(tariff?.sentiment).toBe(-1);

    expect(biofuel).toBeDefined();
    expect(biofuel?.mentions).toBe(1);
    expect(biofuel?.sentiment).toBe(1);
  });
});
