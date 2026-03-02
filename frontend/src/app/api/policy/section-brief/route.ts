/**
 * Per-section AI brief — streams 1-2 sentence analysis for a policy section.
 *
 * Called once per section (agency, executive, news). Each gets its own
 * tailored prompt. Returns streamed text, not JSON.
 */

import { streamText } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { MODEL_DRIVER_INTEL } from "@/lib/ai-config";

export const dynamic = "force-dynamic";

interface SectionRequest {
  section: "agency" | "executive" | "news";
  regime: { score: number; label: string };
  data: Array<Record<string, unknown>>;
}

const SECTION_PROMPTS: Record<string, string> = {
  agency: `You analyze which US government agencies are filing ZL-relevant regulations. Given agency filing counts (trade, biofuel, energy, agriculture), write ONE sentence: name the most active agency, what they're doing, and what it means for soybean oil. No hedging.`,
  executive: `You analyze presidential executive actions for ZL (soybean oil futures) impact. Given recent executive orders/memoranda with price impact data, write ONE sentence: name the most impactful action, its causal chain to ZL, and directional call. No hedging.`,
  news: `You analyze policy news headlines for ZL (soybean oil futures). Given recent headlines from Google News and trade publications, write ONE sentence: identify the dominant narrative theme and state whether it's bullish or bearish for ZL and why. No hedging.`,
};

export async function POST(request: Request) {
  let payload: SectionRequest;
  try {
    payload = (await request.json()) as SectionRequest;
  } catch {
    return new Response("Invalid request", { status: 400 });
  }

  if (!process.env.ANTHROPIC_API_KEY) {
    return new Response("AI unavailable", { status: 503 });
  }

  const lines: string[] = [];
  lines.push(`Policy Threat: ${payload.regime.score}/100 — "${payload.regime.label}"`);
  lines.push("");

  for (const item of payload.data.slice(0, 8)) {
    const parts = Object.entries(item)
      .map(([k, v]) => `${k}: ${v}`)
      .join(" | ");
    lines.push(`- ${parts}`);
  }

  const result = streamText({
    model: anthropic(MODEL_DRIVER_INTEL),
    maxOutputTokens: 120,
    system: SECTION_PROMPTS[payload.section] ?? SECTION_PROMPTS.agency,
    prompt: lines.join("\n"),
  });

  return result.toTextStreamResponse();
}
