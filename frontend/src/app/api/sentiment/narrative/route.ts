import { NextResponse } from "next/server";
import { MODEL_DRIVER_INTEL } from "@/lib/ai-config";
import { hasOpenRouterApiKey, openRouterCompleteText } from "@/lib/openrouter";
import { parseAIJson } from "@/lib/parse-ai-json";
import {
  buildSentimentNarratives,
  type FearGreedNarrativePayload,
  type TrumpEffectNarrativePayload,
  type VolatilityNarrativePayload,
} from "@/lib/sentiment-narratives";

export const dynamic = "force-dynamic";

type NarrativeRequest = {
  fearGreed?: FearGreedNarrativePayload;
  trumpEffect?: TrumpEffectNarrativePayload;
  volatility?: VolatilityNarrativePayload;
};

type NarrativeResponse = {
  fearGreedNarrative: string | null;
  trumpEffectNarrative: string | null;
  volatilityNarrative: string | null;
  source: "ai" | "deterministic";
  model: string | null;
};

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
- Keep each narrative to at most 2 short sentences.
- Keep the tone direct and analytical.
- If a section has no usable data, return null for that field.`;

function trimToTwoSentences(value: string | null | undefined): string | null {
  if (typeof value !== "string") return null;
  const compact = value.replace(/\s+/g, " ").trim();
  if (!compact) return null;

  const matches = compact.match(/[^.!?]+[.!?]+|[^.!?]+$/g);
  if (!matches || matches.length === 0) return compact;

  return matches
    .slice(0, 2)
    .map((part) => part.trim())
    .join(" ");
}

export async function POST(request: Request) {
  let payload: NarrativeRequest = {};
  try {
    payload = (await request.json()) as NarrativeRequest;
  } catch {
    // Keep empty payload; return null narratives instead of failing the page.
  }

  const fallback = buildSentimentNarratives(payload);
  let response: NarrativeResponse = {
    ...fallback,
    source: "deterministic",
    model: null,
  };

  if (hasOpenRouterApiKey()) {
    try {
      const text = await openRouterCompleteText({
        model: MODEL_DRIVER_INTEL,
        maxTokens: 220,
        temperature: 0.0,
        reasoning: { effort: "low" },
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          {
            role: "user",
            content: `Summarize this verified payload for the sentiment page cards:\n${JSON.stringify(payload, null, 2)}`,
          },
        ],
      });

      const parsed = parseAIJson<{
        fearGreedNarrative?: string | null;
        trumpEffectNarrative?: string | null;
        volatilityNarrative?: string | null;
      }>(text);

      if (parsed) {
        response = {
          fearGreedNarrative:
            trimToTwoSentences(parsed.fearGreedNarrative) ?? fallback.fearGreedNarrative,
          trumpEffectNarrative:
            trimToTwoSentences(parsed.trumpEffectNarrative) ?? fallback.trumpEffectNarrative,
          volatilityNarrative:
            trimToTwoSentences(parsed.volatilityNarrative) ?? fallback.volatilityNarrative,
          source: "ai",
          model: MODEL_DRIVER_INTEL,
        };
      }
    } catch (error) {
      console.error("[/api/sentiment/narrative] AI generation failed:", error);
    }
  }

  return NextResponse.json(
    response,
    {
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}
