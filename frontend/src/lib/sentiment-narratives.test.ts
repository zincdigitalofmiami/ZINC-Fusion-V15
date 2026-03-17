import { describe, expect, it } from "vitest";

import { buildTrumpNarrative } from "./sentiment-narratives";

const BASE_PAYLOAD = {
  title: "Impact on Soybean Oil Futures",
  total_actions_7d: 4,
  executive_orders_7d: 1,
  other_actions_7d: 3,
  weighted_action_score: 1.2,
  corroboration_score: 52,
  corroboration_band: "mixed",
  supporting_policy_items_7d: 3,
  market_news_items_7d: 2,
  regulatory_follow_through_7d: 1,
  response_signal: "active",
} as const;

describe("buildTrumpNarrative movement wording", () => {
  it("renders positive return as rose", () => {
    const narrative = buildTrumpNarrative({
      ...BASE_PAYLOAD,
      zl_return_7d_pct: 2.5,
      zl_response_1d_pct: null,
    });

    expect(narrative).toContain("rose 2.50% in the 7d policy window");
  });

  it("renders negative return as fell", () => {
    const narrative = buildTrumpNarrative({
      ...BASE_PAYLOAD,
      zl_return_7d_pct: -1.25,
      zl_response_1d_pct: null,
    });

    expect(narrative).toContain("fell 1.25% in the 7d policy window");
  });

  it("renders exact zero 7d return as unchanged and never fell 0.00%", () => {
    const narrative = buildTrumpNarrative({
      ...BASE_PAYLOAD,
      zl_return_7d_pct: 0,
      zl_response_1d_pct: null,
    });

    expect(narrative).toContain("was unchanged (0.00%) in the 7d policy window");
    expect(narrative).not.toContain("fell 0.00%");
  });

  it("renders exact zero 1d return as unchanged and never fell 0.00%", () => {
    const narrative = buildTrumpNarrative({
      ...BASE_PAYLOAD,
      zl_return_7d_pct: 1,
      zl_response_1d_pct: 0,
    });

    expect(narrative).toContain("and was unchanged (0.00%) in 1d");
    expect(narrative).not.toContain("fell 0.00% in 1d");
  });

  it("keeps null 7d return unavailable wording", () => {
    const narrative = buildTrumpNarrative({
      ...BASE_PAYLOAD,
      zl_return_7d_pct: null,
      zl_response_1d_pct: 1.1,
    });

    expect(narrative).toContain("ZL response unavailable");
  });
});
