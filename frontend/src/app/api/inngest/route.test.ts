import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("api/inngest route registration", () => {
  it("registers the managed ZL intraday refresher", () => {
    const source = readFileSync(new URL("./route.ts", import.meta.url), "utf8");

    expect(source).toMatch(/\bzl1mIntradayRefresh\b/);
    expect(source).toMatch(/functions:\s*\[[\s\S]*zl1mIntradayRefresh/);
  });
});
