import { describe, expect, it } from "vitest";

import { parseAIJson } from "./parse-ai-json";

describe("parseAIJson", () => {
  it("parses raw JSON", () => {
    const result = parseAIJson<{ a: number }>('{"a": 1}');
    expect(result).toEqual({ a: 1 });
  });

  it("parses markdown-fenced JSON", () => {
    const result = parseAIJson<{ b: string }>('```json\n{"b": "hello"}\n```');
    expect(result).toEqual({ b: "hello" });
  });

  it("parses fenced JSON without json label", () => {
    const result = parseAIJson<{ c: boolean }>('```\n{"c": true}\n```');
    expect(result).toEqual({ c: true });
  });

  it("extracts JSON from prose", () => {
    const result = parseAIJson<{ x: number }>(
      'Here is the result: {"x": 42} and some trailing text.'
    );
    expect(result).toEqual({ x: 42 });
  });

  it("returns null for invalid JSON", () => {
    expect(parseAIJson("not json at all")).toBeNull();
  });

  it("returns null for empty string", () => {
    expect(parseAIJson("")).toBeNull();
  });
});
