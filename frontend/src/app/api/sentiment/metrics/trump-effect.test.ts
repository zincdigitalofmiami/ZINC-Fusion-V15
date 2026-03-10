import { describe, expect, it } from "vitest";

import {
  buildTrumpEffectPayload,
  type ExecutiveActionRow,
  type TrumpFeatureRow,
} from "./trump-effect";

describe("buildTrumpEffectPayload", () => {
  const featureRow: TrumpFeatureRow = {
    as_of_date: "2026-03-10",
    latest_any_as_of: "2026-03-10",
    selection_mode: "latest_valid",
    weighted_action_score: 1.75,
    action_velocity: 1.14,
    action_acceleration: 0.21,
    total_actions_7d: 8,
    total_actions_30d: 23,
    eo_count_7d: 2,
  };

  it("derives 7d counts and 7d/30d sentiment from executive action rows without stale feature keys", () => {
    const rows: ExecutiveActionRow[] = [
      {
        event_date: "2026-03-10",
        document_type: "proclamation",
        zl_sentiment: null,
        headline: "Soybean oil prices surge on tight supply",
        content: null,
      },
      {
        event_date: "2026-03-09",
        document_type: "presidential_memorandum",
        zl_sentiment: "bearish",
        headline: "Memorandum text",
        content: null,
      },
      {
        event_date: "2026-03-08",
        document_type: "nomination_appointment",
        zl_sentiment: "neutral",
        headline: "Nomination text",
        content: null,
      },
      {
        event_date: "2026-02-20",
        document_type: "proclamation",
        zl_sentiment: "bullish",
        headline: "Outside 7d but inside 30d",
        content: null,
      },
    ];

    const payload = buildTrumpEffectPayload(featureRow, rows);

    expect(payload).not.toBeNull();
    expect(payload?.eo_count_7d).toBe(2);
    expect(payload?.proclamation_count_7d).toBe(1);
    expect(payload?.memorandum_count_7d).toBe(1);
    expect(payload?.nomination_count_7d).toBe(1);
    expect(payload?.avg_sentiment_7d).toBeCloseTo(0, 6);
    expect(payload?.avg_sentiment_30d).toBeCloseTo(0.25, 6);
  });

  it("returns null sentiment averages when no qualifying rows exist", () => {
    const payload = buildTrumpEffectPayload(featureRow, []);
    expect(payload).not.toBeNull();
    expect(payload?.proclamation_count_7d).toBe(0);
    expect(payload?.memorandum_count_7d).toBe(0);
    expect(payload?.nomination_count_7d).toBe(0);
    expect(payload?.avg_sentiment_7d).toBeNull();
    expect(payload?.avg_sentiment_30d).toBeNull();
  });

  it("returns null when the latest feature row does not exist", () => {
    expect(buildTrumpEffectPayload(null, [])).toBeNull();
  });

  it("derives score and dynamics from actions when selected feature row is partial", () => {
    const partialRow: TrumpFeatureRow = {
      as_of_date: "2026-03-10",
      latest_any_as_of: "2026-03-10",
      selection_mode: "latest_fallback",
      weighted_action_score: null,
      action_velocity: null,
      action_acceleration: null,
      total_actions_7d: null,
      total_actions_30d: null,
      eo_count_7d: null,
    };
    const rows: ExecutiveActionRow[] = [
      {
        event_date: "2026-03-10",
        document_type: "executive_order",
        zl_sentiment: "bullish",
        headline: "Executive order announced",
        content: null,
      },
      {
        event_date: "2026-03-08",
        document_type: "proclamation",
        zl_sentiment: "neutral",
        headline: "Proclamation update",
        content: null,
      },
      {
        event_date: "2026-03-05",
        document_type: "presidential_memorandum",
        zl_sentiment: "bearish",
        headline: "Memo update",
        content: null,
      },
      {
        event_date: "2026-03-07",
        document_type: "nomination_appointment",
        zl_sentiment: "neutral",
        headline: "Nomination update",
        content: null,
      },
    ];

    const payload = buildTrumpEffectPayload(partialRow, rows);

    expect(payload).not.toBeNull();
    expect(payload?.total_actions_7d).toBe(4);
    expect(payload?.total_actions_30d).toBe(4);
    expect(payload?.eo_count_7d).toBe(1);
    expect(payload?.weighted_action_score).toBeCloseTo(0.8, 6); // (3 + 1.5 + 2.5 + 1)/10
    expect(payload?.action_velocity).toBe(0.5714);
    expect(payload?.action_acceleration).toBe(0.5714);
  });

  it("uses canonical weights and inclusive windows for legislation-mapped action types", () => {
    const partialRow: TrumpFeatureRow = {
      as_of_date: "2026-03-10",
      latest_any_as_of: "2026-03-10",
      selection_mode: "latest_fallback",
      weighted_action_score: null,
      action_velocity: null,
      action_acceleration: null,
      total_actions_7d: null,
      total_actions_30d: null,
      eo_count_7d: null,
    };
    const rows: ExecutiveActionRow[] = [
      // Current 7-day window: anchor-6 through anchor (inclusive)
      {
        event_date: "2026-03-10",
        document_type: "executive_order",
        zl_sentiment: "bullish",
        headline: "EO",
        content: null,
      },
      {
        event_date: "2026-03-09",
        document_type: "proclamation",
        zl_sentiment: "neutral",
        headline: "Proclamation",
        content: null,
      },
      {
        event_date: "2026-03-08",
        document_type: "memorandum",
        zl_sentiment: "bearish",
        headline: "Presidential memorandum",
        content: null,
      },
      {
        event_date: "2026-03-07",
        document_type: "nomination",
        zl_sentiment: "neutral",
        headline: "Nomination",
        content: null,
      },
      {
        event_date: "2026-03-06",
        document_type: "presidential_document",
        zl_sentiment: "bullish",
        headline: "Federal Register presidential document",
        content: null,
      },
      // Previous-week velocity window: anchor-13 through anchor-7 (inclusive)
      {
        event_date: "2026-03-02",
        document_type: "executive_order",
        zl_sentiment: "bearish",
        headline: "Previous-week EO",
        content: null,
      },
      {
        event_date: "2026-02-28",
        document_type: "presidential_document",
        zl_sentiment: "neutral",
        headline: "Previous-week presidential document",
        content: null,
      },
      // Outside 30-day window; must be excluded
      {
        event_date: "2026-02-08",
        document_type: "executive_order",
        zl_sentiment: "bullish",
        headline: "Outside 30d",
        content: null,
      },
    ];

    const payload = buildTrumpEffectPayload(partialRow, rows);

    expect(payload).not.toBeNull();
    expect(payload?.total_actions_7d).toBe(5);
    expect(payload?.total_actions_30d).toBe(7);
    expect(payload?.eo_count_7d).toBe(1);
    expect(payload?.proclamation_count_7d).toBe(1);
    expect(payload?.memorandum_count_7d).toBe(1);
    expect(payload?.nomination_count_7d).toBe(1);
    expect(payload?.weighted_action_score).toBe(1.0); // (3 + 1.5 + 2.5 + 1 + 2) / 10
    expect(payload?.action_velocity).toBe(0.7143); // 5 / 7
    expect(payload?.action_acceleration).toBe(0.4286); // (5 / 7) - (2 / 7)
    expect(payload?.avg_sentiment_7d).toBeCloseTo(0.2, 6); // (1 + 0 - 1 + 0 + 1) / 5
    expect(payload?.avg_sentiment_30d).toBe(0); // (+1 + 0 -1 +0 +1 -1 +0) / 7
  });

  it("does not invent non-null sentiment averages when source rows are absent", () => {
    const partialRow: TrumpFeatureRow = {
      as_of_date: "2026-03-10",
      latest_any_as_of: "2026-03-10",
      selection_mode: "latest_fallback",
      weighted_action_score: null,
      action_velocity: null,
      action_acceleration: null,
      total_actions_7d: null,
      total_actions_30d: null,
      eo_count_7d: null,
    };

    const payload = buildTrumpEffectPayload(partialRow, []);

    expect(payload).not.toBeNull();
    expect(payload?.total_actions_7d).toBe(0);
    expect(payload?.total_actions_30d).toBe(0);
    expect(payload?.eo_count_7d).toBe(0);
    expect(payload?.weighted_action_score).toBe(0);
    expect(payload?.action_velocity).toBe(0);
    expect(payload?.action_acceleration).toBe(0);
    expect(payload?.avg_sentiment_7d).toBeNull();
    expect(payload?.avg_sentiment_30d).toBeNull();
  });
});
