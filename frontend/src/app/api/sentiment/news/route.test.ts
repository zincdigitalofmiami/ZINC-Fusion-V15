import { describe, expect, it } from "vitest";

import { countSentimentRows } from "../metrics/route";
import { buildSentimentNewsPayload, laneLabelsFromRow } from "./route";

describe("sentiment/news lane attribution", () => {
  it("derives multiple lane labels from canonical lane tags", () => {
    const labels = laneLabelsFromRow("google_news/Reuters", [
      "energy",
      "lane_war_military",
      "lane_biofuel",
    ]);

    expect(labels).toContain("War Military");
    expect(labels).toContain("Biofuel");
  });

  it("supports legacy lane encoded source rows", () => {
    const labels = laneLabelsFromRow("google_news/soybean_oil/Reuters", [
      "crush",
    ]);

    expect(labels).toContain("Soybean Oil");
  });

  it("ignores unknown lane tags", () => {
    const labels = laneLabelsFromRow("google_news/Reuters", [
      "lane_not_real",
      "energy",
    ]);

    expect(labels).toHaveLength(0);
  });
});

describe("sentiment/news aggregation contract", () => {
  it("uses the same fallback relevance gating as metrics sentiment counts", () => {
    const sharedRows = [
      {
        id: 1,
        event_date: "2026-03-15",
        headline: "Soybean oil prices surge on tight supply",
        summary: null,
        content: null,
        source: "google_news/soybean_oil/Reuters",
        zl_sentiment: null,
        specialist_tags: ["lane_soybean_oil", "crush"],
        table_source: "policy",
      },
      {
        id: 2,
        event_date: "2026-03-15",
        headline: "Congress vote triggers a broad market rally",
        summary: null,
        content: null,
        source: "google_news/legislation/Reuters",
        zl_sentiment: null,
        specialist_tags: ["lane_legislation", "tariff", "trump_effect"],
        table_source: "legislation",
      },
      {
        id: 3,
        event_date: "2026-03-15",
        headline: "Executive memo language remains mixed",
        summary: null,
        content: null,
        source: "White House",
        zl_sentiment: "bearish",
        specialist_tags: ["lane_trump_actions"],
        table_source: "executive",
      },
    ];

    const newsPayload = buildSentimentNewsPayload(sharedRows);
    const metricsCounts = countSentimentRows(sharedRows);

    expect(newsPayload.stats).toEqual({
      total: 2,
      bullish: 1,
      bearish: 1,
      neutral: 0,
    });
    expect(metricsCounts).toEqual({
      bullish: 1,
      bearish: 1,
    });

    const filteredHeadline = newsPayload.headlines.find((row) => row.id === "legislation-2");
    expect(filteredHeadline?.sentiment).toBe("neutral");
  });
});
