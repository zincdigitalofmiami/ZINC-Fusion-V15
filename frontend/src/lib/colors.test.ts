import { describe, expect, it } from "vitest";

import TV, { getAreaGradient } from "./colors";

describe("TV color constants", () => {
  it("TV.bull.primary is a valid hex", () => {
    expect(TV.bull.primary).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it("TV.bear.primary is a valid hex", () => {
    expect(TV.bear.primary).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it("TV.blue.primary is a valid hex", () => {
    expect(TV.blue.primary).toMatch(/^#[0-9a-f]{6}$/i);
  });
});

describe("specialist driver color map", () => {
  it("has 11 entries", () => {
    expect(Object.keys(TV.drivers)).toHaveLength(11);
  });

  it("includes all expected specialists", () => {
    const keys = Object.keys(TV.drivers);
    expect(keys).toContain("crush");
    expect(keys).toContain("china");
    expect(keys).toContain("volatility");
    expect(keys).toContain("trump");
  });
});

describe("getAreaGradient", () => {
  it("returns a linear-gradient string", () => {
    const result = getAreaGradient("#ff0000");
    expect(result).toContain("linear-gradient");
  });
});
