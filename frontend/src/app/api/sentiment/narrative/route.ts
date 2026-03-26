import { NextResponse } from "next/server";
import { createHash } from "node:crypto";
import { AI_OUTPUT_VERSION, MODEL_DRIVER_INTEL } from "@/lib/ai-config";
import { hasOpenRouterApiKey, openRouterCompleteText } from "@/lib/openrouter";
import { parseAIJson } from "@/lib/parse-ai-json";
import {
  buildSentimentNarratives,
  type FearGreedNarrativePayload,
  type TrumpEffectNarrativePayload,
  type VolatilityNarrativePayload,
} from "@/lib/sentiment-narratives";

export const dynamic = "force-dynamic";

export type NarrativeRequest = {
  fearGreed?: FearGreedNarrativePayload;
  trumpEffect?: TrumpEffectNarrativePayload;
  volatility?: VolatilityNarrativePayload;
};

export type NarrativeResponse = {
  fearGreedNarrative: string | null;
  trumpEffectNarrative: string | null;
  volatilityNarrative: string | null;
  source: "ai" | "deterministic";
  model: string | null;
};

type ParseJsonFn = <T>(value: string) => T | null;

interface NarrativeRuntimeDeps {
  hasApiKey: () => boolean;
  completeText: typeof openRouterCompleteText;
  parseJson: ParseJsonFn;
  buildFallback: typeof buildSentimentNarratives;
  now: () => number;
}

const NARRATIVE_CACHE_TTL_MS = 10 * 60 * 1000;
const NARRATIVE_CACHE_MAX_ENTRIES = 200;
const NARRATIVE_CACHE = new Map<
  string,
  { expiresAtMs: number; response: NarrativeResponse }
>();

const SYSTEM_PROMPT = `You write soybean oil sentiment card summaries for a commercial buyer.

Return valid JSON only with exactly this shape:
{
  "fearGreedNarrative": "string or null",
  "trumpEffectNarrative": "string or null",
  "volatilityNarrative": "string or null"
}

Rules:
- Base every sentence only on the payload provided.
- Do not invent numbers, dates, or market facts.
- Write each non-null narrative as one detailed paragraph (minimum 4 sentences).
- Hyper-tune each paragraph to the specific card and section:
  - fearGreedNarrative: explain which Fear & Greed components are driving the score/zone and what that means for ZL risk posture.
  - trumpEffectNarrative: explain policy flow, corroboration, and observed ZL response in the same paragraph.
  - volatilityNarrative: explain VIX/OVX/realized vol regime and execution risk implications.
- Mention concrete metric names and values from the payload whenever available.
- Keep the tone direct, technical, and decision-useful.
- If a section has no usable data, return null for that field.`;

function normalizeParagraph(value: string | null | undefined): string | null {
  if (typeof value !== "string") return null;
  const compact = value.replace(/\s+/g, " ").trim();
  return compact.length > 0 ? compact : null;
}

function normalizeForHash(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => normalizeForHash(item));
  }
  if (value && typeof value === "object") {
    const normalizedEntries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, nested]) => [key, normalizeForHash(nested)]);
    return Object.fromEntries(normalizedEntries);
  }
  return value;
}

function payloadCacheKey(payload: NarrativeRequest, aiEnabled: boolean): string {
  const normalized = normalizeForHash(payload);
  const serialized = JSON.stringify(normalized);
  return createHash("sha256")
    .update(
      `${AI_OUTPUT_VERSION}:${MODEL_DRIVER_INTEL}:${aiEnabled ? "ai" : "det"}:${serialized}`,
    )
    .digest("hex");
}

function cacheGet(key: string, nowMs: number): NarrativeResponse | null {
  const hit = NARRATIVE_CACHE.get(key);
  if (!hit) return null;
  if (hit.expiresAtMs <= nowMs) {
    NARRATIVE_CACHE.delete(key);
    return null;
  }
  return hit.response;
}

function cacheSet(key: string, response: NarrativeResponse, nowMs: number): void {
  if (NARRATIVE_CACHE.size >= NARRATIVE_CACHE_MAX_ENTRIES) {
    const oldestKey = NARRATIVE_CACHE.keys().next().value;
    if (oldestKey) {
      NARRATIVE_CACHE.delete(oldestKey);
    }
  }
  NARRATIVE_CACHE.set(key, {
    expiresAtMs: nowMs + NARRATIVE_CACHE_TTL_MS,
    response,
  });
}

const DEFAULT_RUNTIME_DEPS: NarrativeRuntimeDeps = {
  hasApiKey: hasOpenRouterApiKey,
  completeText: openRouterCompleteText,
  parseJson: parseAIJson,
  buildFallback: buildSentimentNarratives,
  now: () => Date.now(),
};

export function resetNarrativeCacheForTests() {
  NARRATIVE_CACHE.clear();
}

export async function buildNarrativeResponse(
  payload: NarrativeRequest,
  overrides: Partial<NarrativeRuntimeDeps> = {},
): Promise<NarrativeResponse> {
  const deps = {
    ...DEFAULT_RUNTIME_DEPS,
    ...overrides,
  };
  const nowMs = deps.now();
  const aiEnabled = deps.hasApiKey();
  const key = payloadCacheKey(payload, aiEnabled);
  const cached = cacheGet(key, nowMs);
  if (cached) return cached;

  const fallback = deps.buildFallback(payload);
  let response: NarrativeResponse = {
    ...fallback,
    source: "deterministic",
    model: null,
  };

  if (aiEnabled) {
    try {
      const text = await deps.completeText({
        model: MODEL_DRIVER_INTEL,
        maxTokens: 700,
        temperature: 0.0,
        reasoning: { effort: "high" },
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          {
            role: "user",
            content: `Summarize this verified payload for the sentiment page cards:\n${JSON.stringify(payload, null, 2)}`,
          },
        ],
      });

      const parsed = deps.parseJson<{
        fearGreedNarrative?: string | null;
        trumpEffectNarrative?: string | null;
        volatilityNarrative?: string | null;
      }>(text);

      if (parsed) {
        const aiFearGreed = normalizeParagraph(parsed.fearGreedNarrative);
        const aiTrumpEffect = normalizeParagraph(parsed.trumpEffectNarrative);
        const aiVolatility = normalizeParagraph(parsed.volatilityNarrative);
        const hasUsableAiNarrative =
          aiFearGreed !== null || aiTrumpEffect !== null || aiVolatility !== null;

        if (hasUsableAiNarrative) {
          response = {
            fearGreedNarrative: aiFearGreed ?? fallback.fearGreedNarrative,
            trumpEffectNarrative: aiTrumpEffect ?? fallback.trumpEffectNarrative,
            volatilityNarrative: aiVolatility ?? fallback.volatilityNarrative,
            source: "ai",
            model: MODEL_DRIVER_INTEL,
          };
        }
      }
    } catch (error) {
      console.error("[/api/sentiment/narrative] AI generation failed:", error);
    }
  }

  if (response.source === "ai") {
    cacheSet(key, response, nowMs);
  }
  return response;
}

export async function POST(request: Request) {
  let payload: NarrativeRequest = {};
  try {
    payload = (await request.json()) as NarrativeRequest;
  } catch {
    // Keep empty payload; return null narratives instead of failing the page.
  }

  const response = await buildNarrativeResponse(payload);

  return NextResponse.json(
    response,
    {
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}
