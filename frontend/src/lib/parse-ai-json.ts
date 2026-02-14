/**
 * Shared JSON parser for AI model responses.
 *
 * Handles three common response shapes from Claude:
 *   1. Raw JSON text
 *   2. JSON wrapped in markdown fences (```json ... ```)
 *   3. JSON embedded in prose (extract first { ... } block)
 */
export function parseAIJson<T>(rawText: string): T | null {
  const text = rawText.trim();
  const candidates = new Set<string>([text]);

  // Common case: model wraps JSON in markdown fences.
  const fenced = text.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  if (fenced?.[1]) candidates.add(fenced[1].trim());

  // Fallback: extract the first top-level JSON object from mixed text.
  const firstBrace = text.indexOf("{");
  const lastBrace = text.lastIndexOf("}");
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    candidates.add(text.slice(firstBrace, lastBrace + 1).trim());
  }

  for (const candidate of candidates) {
    try {
      return JSON.parse(candidate) as T;
    } catch {
      // Try next candidate.
    }
  }

  return null;
}
