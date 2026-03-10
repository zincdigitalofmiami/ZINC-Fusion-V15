import { describe, expect, it } from "vitest";

import {
  buildTrumpEffectPayload,
  type ConfirmationInputs,
  type ExecutiveActionRow,
  type TrumpFeatureRow,
  type ZlResponseInputs,
} from "./trump-effect";

const BASE_FEATURE_ROW: TrumpFeatureRow = {
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

const BASE_CONFIRMATION: ConfirmationInputs = {
  independent_policy_items_7d: 6,
  market_news_items_7d: 5,
  regulatory_follow_through_7d: 2,
};

const BASE_ZL_RESPONSE: ZlResponseInputs = {
  close_anchor: 50,
  close_prev_1d: 49,
  close_prev_5d: 48,
  close_start_7d: 47,
  realized_vol_21d: 22,
  anchor_price_date: "2026-03-10",
};

describe("buildTrumpEffectPayload", () => {
  it("builds a ZL-anchored policy card with canonical weights, windows, and confirmation", () => {
    const rows: ExecutiveActionRow[] = [
      // Current 7-day window (anchor-6 through anchor inclusive)
      {
        event_date: "2026-03-10",
        document_type: "executive_order",
        zl_sentiment: "bullish",
        headline: "Executive order",
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
        headline: "Presidential document",
        content: null,
      },
      // Previous-week velocity window (anchor-13 through anchor-7 inclusive)
      {
        event_date: "2026-03-02",
        document_type: "executive_order",
        zl_sentiment: "bearish",
        headline: "Previous week EO",
        content: null,
      },
      {
        event_date: "2026-02-28",
        document_type: "presidential_document",
        zl_sentiment: "neutral",
        headline: "Previous week presidential document",
        content: null,
      },
      // Outside 30-day window and excluded
      {
        event_date: "2026-02-08",
        document_type: "executive_order",
        zl_sentiment: "bullish",
        headline: "Outside 30d",
        content: null,
      },
    ];

    const payload = buildTrumpEffectPayload(
      BASE_FEATURE_ROW,
      rows,
      BASE_CONFIRMATION,
      BASE_ZL_RESPONSE,
    );

    expect(payload).not.toBeNull();
    expect(payload?.title).toBe("Policy Impact on ZL");

    expect(payload?.policy_activity.executive_orders_7d).toBe(1);
    expect(payload?.policy_activity.total_presidential_actions_7d).toBe(5);
    expect(payload?.policy_activity.other_presidential_actions_7d).toBe(4);
    expect(payload?.policy_activity.weighted_action_score).toBe(1); // (3 + 1.5 + 2.5 + 1 + 2) / 10
    expect(payload?.policy_activity.action_velocity).toBe(0.7143); // 5 / 7
    expect(payload?.policy_activity.action_acceleration).toBe(0.4286); // (5 / 7) - (2 / 7)
    expect(payload?.policy_activity.avg_sentiment_7d).toBeCloseTo(0.2, 6);
    expect(payload?.policy_activity.avg_sentiment_30d).toBe(0);

    expect(payload?.zl_response.zl_return_7d_pct).toBe(6.38);
    expect(payload?.zl_response.zl_response_1d_pct).toBe(2.04);
    expect(payload?.zl_response.zl_response_5d_pct).toBe(4.17);
    expect(payload?.zl_response.realized_vol_21d_pct).toBe(22);
    expect(payload?.zl_response.response_signal).toBe("active");

    expect(payload?.independent_confirmation.independent_policy_items_7d).toBe(6);
    expect(payload?.independent_confirmation.market_news_items_7d).toBe(5);
    expect(payload?.independent_confirmation.regulatory_follow_through_7d).toBe(2);
    expect(payload?.independent_confirmation.confirmation_score).toBe(66);
    expect(payload?.independent_confirmation.confirmation_band).toBe("mixed");

    // Legacy compatibility fields remain populated.
    expect(payload?.total_actions_7d).toBe(5);
    expect(payload?.eo_count_7d).toBe(1);
    expect(payload?.other_actions_7d).toBe(4);
  });

  it("classifies confirmed pressure when confirmation is strong and ZL move is elevated", () => {
    const rows: ExecutiveActionRow[] = [
      {
        event_date: "2026-03-10",
        document_type: "executive_order",
        zl_sentiment: "bullish",
        headline: "EO",
        content: null,
      },
      {
        event_date: "2026-03-09",
        document_type: "presidential_document",
        zl_sentiment: "bullish",
        headline: "PD",
        content: null,
      },
      {
        event_date: "2026-03-08",
        document_type: "executive_order",
        zl_sentiment: "bullish",
        headline: "EO 2",
        content: null,
      },
    ];

    const strongConfirmation: ConfirmationInputs = {
      independent_policy_items_7d: 8,
      market_news_items_7d: 8,
      regulatory_follow_through_7d: 4,
    };

    const elevatedMove: ZlResponseInputs = {
      close_anchor: 52,
      close_prev_1d: 49,
      close_prev_5d: 47,
      close_start_7d: 46,
      realized_vol_21d: 20,
      anchor_price_date: "2026-03-10",
    };

    const payload = buildTrumpEffectPayload(
      BASE_FEATURE_ROW,
      rows,
      strongConfirmation,
      elevatedMove,
    );

    expect(payload).not.toBeNull();
    expect(payload?.independent_confirmation.confirmation_band).toBe("strong");
    expect(payload?.zl_response.response_signal).toBe("elevated");
    expect(payload?.buyer_meaning.procurement_signal).toBe("confirmed_pressure");
    expect(payload?.buyer_meaning.label).toContain("Confirmed pressure");
  });

  it("does not invent sentiment averages when action rows are absent", () => {
    const payload = buildTrumpEffectPayload(
      BASE_FEATURE_ROW,
      [],
      {
        independent_policy_items_7d: 0,
        market_news_items_7d: 0,
        regulatory_follow_through_7d: 0,
      },
      {
        close_anchor: 50,
        close_prev_1d: 50,
        close_prev_5d: 50,
        close_start_7d: 50,
        realized_vol_21d: 18,
        anchor_price_date: "2026-03-10",
      },
    );

    expect(payload).not.toBeNull();
    expect(payload?.policy_activity.total_presidential_actions_7d).toBe(0);
    expect(payload?.policy_activity.executive_orders_7d).toBe(0);
    expect(payload?.policy_activity.other_presidential_actions_7d).toBe(0);
    expect(payload?.policy_activity.avg_sentiment_7d).toBeNull();
    expect(payload?.policy_activity.avg_sentiment_30d).toBeNull();
    expect(payload?.independent_confirmation.confirmation_band).toBe("low");
  });

  it("returns null when feature row is missing", () => {
    expect(
      buildTrumpEffectPayload(null, [], BASE_CONFIRMATION, BASE_ZL_RESPONSE),
    ).toBeNull();
  });
});
