import { describe, expect, it } from "vitest";

import {
  GOOGLE_NEWS_LANES,
  MAX_NEWS_ITEM_AGE_DAYS,
  buildCanonicalSourceValue,
  evaluateLaneRelevance,
  parseRssXml,
  prepareCanonicalRows,
} from "./google-news-daily";

describe("google-news-daily lane + date contracts", () => {
  it("defines all required explicit lane slugs", () => {
    const slugs = new Set(GOOGLE_NEWS_LANES.map((lane) => lane.slug));

    expect(slugs.has("ice_immigration")).toBe(true);
    expect(slugs.has("war_military")).toBe(true);
    expect(slugs.has("soybean_oil")).toBe(true);
    expect(slugs.has("soybean_agriculture")).toBe(true);
    expect(slugs.has("trump_actions")).toBe(true);
    expect(slugs.has("legislation")).toBe(true);
    expect(slugs.has("biofuel")).toBe(true);
  });

  it("rejects RSS rows that do not include valid pubDate", () => {
    const xml = `
      <rss><channel>
        <item>
          <title>Valid dated story</title>
          <link>https://example.com/valid</link>
          <description><![CDATA[<div>Trade policy and soybean oil feedstock coverage</div>]]></description>
          <pubDate>Tue, 10 Mar 2026 14:00:00 GMT</pubDate>
          <source>Example Wire</source>
        </item>
        <item>
          <title>Missing date story</title>
          <link>https://example.com/missing</link>
          <source>Example Wire</source>
        </item>
        <item>
          <title>Invalid date story</title>
          <link>https://example.com/invalid</link>
          <pubDate>not-a-date</pubDate>
          <source>Example Wire</source>
        </item>
      </channel></rss>
    `;

    const rows = parseRssXml(xml);

    expect(rows).toHaveLength(1);
    expect(rows[0].headline).toBe("Valid dated story");
    expect(rows[0].description).toBe("Trade policy and soybean oil feedstock coverage");
    expect(rows[0].eventDate).toBe("2026-03-10");
  });

  it("filters stale rows and keeps one canonical row across matched lanes", () => {
    const soybeanLane = GOOGLE_NEWS_LANES.find((entry) => entry.slug === "soybean_oil");
    const biofuelLane = GOOGLE_NEWS_LANES.find((entry) => entry.slug === "biofuel");
    if (!soybeanLane || !biofuelLane) throw new Error("lane missing in test");

    const now = new Date("2026-03-10T18:00:00.000Z");

    const duplicatedAcrossLanes = {
      headline: "Fresh soybean oil biofuel policy article",
      url: "https://example.com/fresh",
      description: "Renewable diesel feedstock demand keeps soybean oil in focus.",
      publishedAt: "2026-03-08T15:00:00.000Z",
      eventDate: "2026-03-08",
      pubSource: "Example News",
    };

    const stale = {
      headline: "Stale soybean oil policy article",
      url: "https://example.com/stale",
      description: "Older soybean oil market coverage.",
      publishedAt: "2025-11-01T12:00:00.000Z",
      eventDate: "2025-11-01",
      pubSource: "Example News",
    };

    const { rows, stats } = prepareCanonicalRows(
      [
        { lane: soybeanLane, rawItems: [duplicatedAcrossLanes, stale] },
        { lane: biofuelLane, rawItems: [duplicatedAcrossLanes] },
      ],
      now,
    );

    expect(rows).toHaveLength(1);
    expect(stats.attempted).toBe(3);
    expect(stats.stale).toBe(1);
    expect(stats.invalidDate).toBe(0);
    expect(stats.deduped).toBe(1);
    expect(rows[0].source.startsWith("google_news/")).toBe(true);
    expect(rows[0].source.includes("/")).toBe(true);
    expect(rows[0].specialistTags).toContain(`lane_${soybeanLane.slug}`);
    expect(rows[0].specialistTags).toContain(`lane_${biofuelLane.slug}`);

    const maxAgeMs = MAX_NEWS_ITEM_AGE_DAYS * 24 * 60 * 60 * 1000;
    const acceptedAgeMs = now.getTime() - Date.parse(rows[0].publishedAt);
    expect(acceptedAgeMs).toBeLessThanOrEqual(maxAgeMs);
  });

  it("rejects lane noise and semantic misses before insert", () => {
    const immigrationLane = GOOGLE_NEWS_LANES.find((entry) => entry.slug === "ice_immigration");
    const legislationLane = GOOGLE_NEWS_LANES.find((entry) => entry.slug === "legislation");
    if (!immigrationLane || !legislationLane) throw new Error("lane missing in test");

    const weatherNoise = {
      headline: "Ice storm closes schools across the Midwest",
      url: "https://example.com/weather",
      description: "Road conditions worsen after overnight snow storm warnings.",
      publishedAt: "2026-03-10T12:00:00.000Z",
      eventDate: "2026-03-10",
      pubSource: "Example News",
    };
    const semanticMiss = {
      headline: "Congress celebrates opening day ceremony",
      url: "https://example.com/ceremony",
      description: "Members gathered for a ceremonial photo and tribute.",
      publishedAt: "2026-03-10T12:10:00.000Z",
      eventDate: "2026-03-10",
      pubSource: "Example News",
    };

    expect(evaluateLaneRelevance(weatherNoise, immigrationLane)).toEqual({
      accepted: false,
      reason: "noise",
    });
    expect(evaluateLaneRelevance(semanticMiss, legislationLane)).toEqual({
      accepted: false,
      reason: "semantic_miss",
    });

    const { rows, stats } = prepareCanonicalRows(
      [
        { lane: immigrationLane, rawItems: [weatherNoise] },
        { lane: legislationLane, rawItems: [semanticMiss] },
      ],
      new Date("2026-03-10T18:00:00.000Z"),
    );

    expect(rows).toHaveLength(0);
    expect(stats.noiseRejected).toBe(1);
    expect(stats.semanticRejected).toBe(1);
  });

  it("caps source value length to fit schema field", () => {
    const longSource = "A".repeat(300);
    const source = buildCanonicalSourceValue(longSource);

    expect(source.length).toBeLessThanOrEqual(100);
    expect(source.startsWith("google_news/")).toBe(true);
  });
});
