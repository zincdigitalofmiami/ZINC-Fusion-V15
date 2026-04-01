import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("api/inngest route registration", () => {
  it("all functions are paused — functions array is empty", () => {
    const source = readFileSync(new URL("./route.ts", import.meta.url), "utf8");

    // Functions are intentionally paused to stop billing (PR #12).
    // Imports are retained for easy restoration.
    expect(source).toMatch(/functions:\s*\[\s*\]/);
  });
});
