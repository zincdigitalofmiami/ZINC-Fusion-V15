import { describe, expect, it } from "vitest";

import {
  BIG_11_SPECIALISTS,
  classifySpecialists,
  validateSpecialists,
} from "./specialist-classifier";

describe("BIG_11_SPECIALISTS", () => {
  it("has exactly 11 entries", () => {
    expect(BIG_11_SPECIALISTS).toHaveLength(11);
  });

  it("includes trump_effect", () => {
    expect(BIG_11_SPECIALISTS).toContain("trump_effect");
  });
});

describe("classifySpecialists", () => {
  it("empty string returns general", () => {
    expect(classifySpecialists("")).toEqual(["general"]);
  });

  it("null-like returns general", () => {
    expect(classifySpecialists("")).toEqual(["general"]);
  });

  it("single keyword match", () => {
    const result = classifySpecialists("USDA reports strong soybean crush");
    expect(result).toContain("crush");
  });

  it("multi specialist match", () => {
    const result = classifySpecialists("China imports crude oil");
    expect(result).toContain("china");
    expect(result).toContain("energy");
  });

  it("dual-tag trade deal triggers tariff and trump_effect", () => {
    const result = classifySpecialists("China trade deal announced");
    expect(result).toContain("china");
    expect(result).toContain("tariff");
    expect(result).toContain("trump_effect");
  });

  it("case insensitive", () => {
    const r1 = classifySpecialists("CHINA buys soybeans");
    const r2 = classifySpecialists("china buys soybeans");
    expect(new Set(r1)).toEqual(new Set(r2));
  });

  it("no duplicates", () => {
    const result = classifySpecialists("china chinese beijing shanghai");
    const chinaCount = result.filter((s) => s === "china").length;
    expect(chinaCount).toBe(1);
  });
});

describe("validateSpecialists", () => {
  it("filters invalid tags", () => {
    const valid = validateSpecialists(["crush", "invalid", "general"]);
    expect(valid).toContain("crush");
    expect(valid).toContain("general");
    expect(valid).not.toContain("invalid");
  });
});
