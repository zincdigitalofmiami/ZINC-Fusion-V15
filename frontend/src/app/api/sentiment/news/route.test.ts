import { describe, expect, it } from "vitest";

import { laneLabelsFromRow } from "./route";

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
